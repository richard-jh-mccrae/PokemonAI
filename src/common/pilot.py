"""The Pilot: a deck-agnostic Sense -> Plan -> Score -> Act decision engine (ADR-0008).

Tiny public interface (`decide`; `explain` adds the per-decision trace). Scoring merges a
deck-agnostic **General Strategy** (shared
hypotheses in `common/`) with the deck's own Strategy; per-hypothesis weights resolve by id
through machine-written `overrides` (0 disables). Operates on the raw observation dict the
engine passes, so the fast unit suite needs no native lib.
"""
from __future__ import annotations

import copy
import dataclasses

from collections import Counter
from dataclasses import dataclass, field
from typing import NamedTuple

from common import action_cost, board_delta, needs  # Stadium clause home (Issue #410/#424): its
                                                    # `stadium_hp_delta` + `applies_to` aren't re-derived
from common import deck_odds
from common.multi_pick import leaf_pick_indices
from common import retreat_cost                # ADR-0100 §8's grant-aware cost
from common.board_cards import body_card_ids   # the ONE walk over a body's attached CARDS
from common.evolve_value import EvolveBody, EvolveInputs, evolve_value
from common.promote_retreat_value import (PromoteBody, PromoteRetreatInputs, RetreatSide,
                                          promote_value)
from common.opponent_model import OpponentModel
from common.state_model import MySide, StateModel, TheirSide
from common.strategy.damage_context import damage_context as _assemble_damage_context
from common.strategy import GamePlan, Plan, Strategy
from common.scouting.read import Read
from common.scouting.matchup import matchup_favorability
from common.scouting.briefs import Brief, match_brief, resolve_brief_cards
from common.scouting.matchup_plan import (BodyFacts, MatchupPlan, build_matchup_plan,
                                          derive_general_roles)
from common.option_equivalence import canonical_keys   # ADR-0103: the ordering tie-break is a board
                                                       # fact, never the menu index

# Engine vocab (enum mirrors, KO_SCORE, _ENGINE_TAGS) shared w/ doctrines -> common.strategy.context.
# Doctrines own their Hypotheses + Pilot-side `*Mixin` code — see those modules.
from common.grading import HORIZON as _HORIZON, halve as _halve
from common.strategy.context import *  # noqa: F401,F403  (the engine-vocabulary constants + _fires/Board live there or below)
from common.strategy.doctrines import FetchMixin, GustMixin, ShuffleRefreshMixin
from common.strategy.objectives import ObjectivesMixin
from common.strategy.planner import PlannerMixin, TurnLine

# Tactical-only scalars — used SOLELY by the closed-form combat evaluator below, never by a doctrine.
# (_EFFICIENCY/_BENCH_SNIPE* moved to the KO oracle, ADR-0052 — the one home for combat valuation.)
from common.card_worth import ENERGY_TIER      # the attach decider's resource tie-break anchor
from common.deny_relevance import MAX_ATTACK_DAMAGE as _DENY_RELEVANCE_NORM  # noqa: E402
from common.snipe_relevance import K as _SNIPE_RELEVANCE_K  # noqa: E402
#                                             imported, not copied, so `_DENY_RELEVANCE_K` below is the
#                                             SAME number by construction and cannot drift
from common.strategy.combat import (Budget, CURRENT_FORMS_ONLY,  # noqa: E402  (re-used
                                    _EFFICIENCY, HARVEST_UNAVOIDABLE, UNCHARGED)  # by the tactical scorers)
from common.strategy.refresh import (fresh_cards, net_change, opponent_shuffles,  # noqa: E402
                                     refresh_branches)  # (ADR-0060 swing oracle)
from common.strategy.sequence import followup_damage  # noqa: E402  (ADR-0061 horizon-2 lock oracle)
from common.strategy.denial import coin_odds          # noqa: E402  (ADR-0062 energy denial)

# --- the families (`common/deciders/`) ---
from common.deciders.attach import (AttachMixin, _ATTACH_VALUE_SCALE,
                                    _ATTACH_ABILITY_FUEL, _ATTACH_RESOURCE_TIEBREAK)  # noqa: F401
from common.deciders.board_build import BoardMixin
from common.deciders.context_build import ContextMixin
from common.deciders.deck_view import DeckViewMixin
from common.deciders.deny import (DenyMixin, _DENIAL_PLAY_W, _DENIAL_TARGET_W, _DENY_RELEVANCE_K,
                                  _DENIAL_UNFAVORED, _DENIAL_FORWARD)  # noqa: F401
from common.deciders.deploy import DeployMixin
from common.deciders.doom import DoomMixin
from common.deciders.evolve import EvolveMixin
from common.deciders.facts import ShedPlan, Board, Context, _slot_cid  # noqa: F401
from common.deciders.hand import (HandMixin, _REFRESH_CYCLE, _REFRESH_OPPONENT_HAND_STRIP,
                                  _REFRESH_OPPONENT_HAND_GIFT, _REFRESH_OPPONENT_HAND_FRESH, _ENGINE_KEEP_TAGS,
                                  _ENGINE_SUPPORTER_KEEP)  # noqa: F401
from common.deciders.heal import HealMixin
from common.deciders.lethal import LethalMixin, _RETREAT_POSITION_EPS  # noqa: F401
from common.deciders.lines import LineMixin
from common.deciders.needs import NeedsMixin, _GENERAL_WORTH_W, _GENERAL_ILLIQUID_FLOOR  # noqa: F401
from common.deciders.opening import OpeningMixin
from common.deciders.order import (OrderMixin, _TIER_INFORMATIVE, _TIER_COMMIT_FREE, _TIER_SUPPORTER,
                                   _TIER_COMMITMENT, _TIER_SHUFFLE, _TIER_ENDER, _INFORMATIVE_TAGS)  # noqa: F401
from common.deciders.plan_choice import (_POSTURE_GAMMA_LO, _POSTURE_GAMMA_HI, _posture_gamma, choose_plan,
                                         _min_attack_cost)  # noqa: F401
from common.deciders.promote import PromoteRetreatMixin
from common.deciders.snipe import (SnipeMixin, _ENERGIZED_SNIPE_TIER, _SNIPE_THREAT_PRIZE_FLOOR,
                                   _PREVENT_EX_SNIPE_BOOST, _BRIEF_THREAT_BOOST)  # noqa: F401
from common.deciders.tactical import (TacticalMixin, _RECOIL_DOOM, _LOCK_KO, _RECOVER_KO, _RECOVER_KO_CAP,
                                      _RESISTANCE, _SELF_RETURN_ESCAPE)  # noqa: F401
from common.deciders.views import ViewsMixin

@dataclass
class OptionTrace:
    """Why one option scored what it did — the legibility record (ADR-0008)."""
    index: int
    score: float
    plan: Plan
    card_id: int | None
    fired: list                  # [(Hypothesis, effective_weight)] whose trigger fired
    tactical: float = 0.0
    deferred: bool = False       # a turn-ending attack held behind beneficial development (attack-last)
    attach_spend: float = 0.0    # ADR-0069 ACTION-referent SPEND: minus the scaled evaporation loss when
                                 # a `discard_eot` Energy buys nothing before end of turn. Negative or 0.
    attach_to_needy_line: bool = False  # ORDERING tie-break among EQUAL-score attaches, decide()-only
    # `hand_size_relief` DELETED (ADR-0102): the term is promoted INTO `score`, so a second copy of the
    # quantity beside it would shadow a live term.
    deploy_working: dict | None = None  # ADR-0086 per-leg breakdown. A human rules the Decision Gate by
                                 # reading it, so a bare total would make that gate unrulable.
    evolve_working: dict | None = None  # ADR-0070 per-option TERM row. This DECIDES, so there is no
                                 # agreement bit. Sparse: None off an EVOLVE option or with the switch OFF.
    promote_retreat_working: dict | None = None  # ADR-0100 per-option TERM row; `site` names which §9
                                 # call site priced it ("pick" | "whether"). This DECIDES. Sparse.


@dataclass
class Decision:
    """A scored decision: the chosen option indices and the per-option OptionTrace."""
    chosen: list
    options: list = field(default_factory=list)
    read: Read | None = None     # the per-decision Scouting Read (ADR-0026)
    posture: dict | None = None  # ADR-0041 telemetry; None when no Scout is wired
    planned: TurnLine | None = None   # ADR-0031/0037. goal "win" = the Lethal Solver's LOCK (telemetry
                                      # serialises it under the wire-compatible `lethal` key)
    lethal_refuted: int = 0      # direct lethal candidates the engine backstop REFUTED (ADR-0030):
                                 # nonzero = closed-form claimed a win the engine denied
    objectives: dict | None = None   # sparse ADR-0040 trace: {"race", "my", "their"}
    gamble: dict | None = None   # sparse ADR-0039 working-trace, or the rung's stand-down reason
    win_prob: float | None = None    # ADR-0042 P(win); None when the model is off (no learned claim)
    lethal_lost: bool = False    # a locked verified line DIVERGED from the live game and was dropped
    reordered: bool = False      # `chosen` came from `_finish_turn_last`, NOT argmax(score) — so a trace
                                 # reader doesn't misread "top-score not chosen" as a scoring bug
    grabbed: bool = False        # `chosen` is a `_greedy_grab` multi-pick set, NOT the top-N static scores
    game_plan: dict | None = None    # the Match Planner's Game Plan (ADR-0045), compact. Sparse.
    composer: dict | None = None     # the SEQUENCE COMPOSER's per-decision telemetry (POC-T4/5): the
                                     # margin block, run stats, the winner's `working()` legs and step
                                     # indices, plus any coverage-gap reasons. None unless it ran.
    attach_working: dict | None = None  # ADR-0069 §9 per-option AXES rows. This DECIDES, so there is no
                                     # agreement bit. A Tool no channel prices ABSTAINS and is counted.


class Pilot(
    # the facts, assembled once per decision
    BoardMixin, ContextMixin, ViewsMixin, DeckViewMixin, LineMixin, OpeningMixin, DoomMixin,
    # one decider per family of option
    AttachMixin, EvolveMixin, PromoteRetreatMixin, DeployMixin, SnipeMixin, DenyMixin, HealMixin,
    LethalMixin, HandMixin, NeedsMixin, TacticalMixin,
    # the sequencer, then the layers above a single option: the Turn Planner and the Match Objectives
    OrderMixin, PlannerMixin, ObjectivesMixin,
    # the archetype doctrines (ADR-0008)
    GustMixin, FetchMixin, ShuffleRefreshMixin,
):
    """The Sense→Plan→Score→Act spine. Every base above contributes closed-form methods to ONE class,
    so the base list is the index: read it to find which module owns a decision."""

    def __init__(self, strategy, deck, *, general_strategy=None, overrides=None, stats=None,
                 functions=None, effects=None,
                 search_budget=0, scout=None, briefs=None, posture=True, lethal_verify=False,
                 planner_key_threat=False, lethal_family=False,
                 lethal_veto=False, objectives_race=False,
                 objectives_path=False, objectives_phases=False, gamble_lines=False,
                 snipe_prize_redundant=False, snipe_prize_reach=False, forced_promotion=False,
                 value_model=None,
                 match_planner_steer=False, prize_economy_fetch=True,
                 lethal_seed_exact=True, promote_ko_aware=False, boost_lethal=False,
                 retreat_enabler_lethal=False, disruptor_lock_maneuver=False,
                 matchup_targeting=True,
                 ko_target_whiff=False, opp_resource_reads=False,
                 enabler_item_composer=False,
                 leaf_hand_value=False, attach_value=True, evolve_value=True, deploy_value=False,
                 promote_retreat_value=True, doom_matched_relax=False,
                 recur_fuel_relax=False, gust_target_slots=False,
                 deny_strip_delta=False, deny_relevance=False, scaled_threat_rank=False,
                 snipe_relevance=False, copy_top_value=False, leaf_followups=False):
        self.strategy = strategy
        self.general = general_strategy or Strategy()   # deck-agnostic shared hypotheses (ADR-0008)
        self.overrides = overrides or {}                # machine-written weight overrides, by hyp id
        self.deck = list(deck)
        self.stats = stats
        self.functions = functions
        self.effects = effects                          # CardEffects (ADR-0032); None = clause-blind
        self.search_budget = search_budget
        self.scout = scout                              # opponent Scout (ADR-0026); None = Posture off
        self.briefs = list(briefs) if briefs else []    # hand-authored Matchup Briefs (ADR-0027)
        self.opponent = OpponentModel(scout=scout,      # the Opponent Model facade (ADR-0047)
                                      artifact=getattr(scout, "artifact", None))
        self.posture = posture                          # ADR-0026: False forces γ=0 + neutral favorability
        self.lethal_verify = lethal_verify              # ADR-0030: engine-confirm a DIRECT lethal lock
        self.lethal_seed_exact = lethal_seed_exact      # ADR-0050: seed the verify's hidden zones from the
                                                        # EXACT own deck/prize split. OFF = id-sorted prefix.
        self.planner_key_threat = planner_key_threat    # ADR-0031: the KO-the-key-threat Goal-Ladder rung
        self.lethal_family = lethal_family              # ADR-0037: the ONE win-generator family; OFF = the
                                                        # legacy hook-trace rungs, direct-verify only
        self.lethal_veto = lethal_veto                  # ADR-0037 stage 3: materialize + REPLAY a verified
                                                        # lock (mismatch -> fall back); presumes lethal_family
        self.objectives_race = objectives_race          # ADR-0040: the Tier-3 KO Race
        self.objectives_path = objectives_path          # ADR-0040: the Prize-Path CONSUMERS (the Board
                                                        # signals themselves are always-on data)
        self.objectives_phases = objectives_phases      # ADR-0040: the derived ADVISORY phases
        self.snipe_prize_redundant = snipe_prize_redundant  # ADR-0044: Prize-Redundant Target suppression
        self.snipe_prize_reach = snipe_prize_reach      # snipe-grill: the prize-path rider-reach TIE-BREAK.
                                                        # Never moves my_path_turns. OFF = mask-order
        self.forced_promotion = forced_promotion        # ADR-0044: the Forced-Promotion Read
        self.match_planner_steer = match_planner_steer  # ADR-0045 S3: the Game Plan biases planner ranking
        self.promote_ko_aware = promote_ko_aware        # KO-aware, boost-inclusive promote pick
        self.boost_lethal = boost_lethal                # promote a benched {F} attacker -> boost Items ->
                                                        # swing lethal; presumes lethal_family
        self.retreat_enabler_lethal = retreat_enabler_lethal  # tutor a retreat-reduction Tool to free a
                                                        # retreat into an already-winning benched attacker
        self.disruptor_lock_maneuver = disruptor_lock_maneuver  # the OFFENSIVE retreat-into-a-benched-
                                                        # item_lock maneuver; feeds `can_lock_line_with_disruptor`
        self.prize_economy_fetch = prize_economy_fetch  # ADR-0048: prize-economy FETCH tie-break + broadened
                                                        # line recognition. OFF = win-condition-only
        self.matchup_targeting = matchup_targeting      # ADR-0051: the MatchupPlan target-priority spine.
                                                        # OFF = empty plan (every priority 0)
        self.ko_target_whiff = ko_target_whiff          # among EQUAL-value targets prefer the one they are
                                                        # least able to replace. Pure tiebreak.
        self.opp_resource_reads = opp_resource_reads    # sub-prize nudge on a known near-term opponent deck-out
        self.enabler_item_composer = enabler_item_composer  # the ko_for_prizes Item-tutor composer
        self.leaf_hand_value = leaf_hand_value          # ADR-0065 WP-N5b: the LEAF's actionable-resource term
        # `needs_keep_value` DELETED (Issue #319): keep-value v2 decides the forced discard
        # UNCONDITIONALLY. Rationale lives on `_discard_needs_pick`, deliberately not restated here.
        self.promote_retreat_value = promote_retreat_value   # ADR-0100, shipped ON. OFF is DEGRADED MODE,
                                                        # not a rollback — all twelve rungs it replaced are gone
        self.evolve_value = evolve_value                # ADR-0070, shipped ON. OFF is DEGRADED MODE — the four
                                                        # rungs it replaced are deleted
        self.deploy_value = deploy_value            # ADR-0086. Ctor default OFF keeps the raw-scoring
                                                    # substrate neutral; `make_agent` resolves the shipped ON
        self.attach_value = attach_value                # ADR-0069 §9, shipped ON. OFF is DEGRADED MODE — the
                                                        # 19 rungs it replaced are deleted. Never a baseline.
        self.copy_top_value = copy_top_value            # Issue #289: value Seek Inspiration only from a
                                                        # self-verified known top card
        self.doom_matched_relax = doom_matched_relax    # behind a γ-matched Brief with no recur fuel, a
                                                        # worst-case `active_doomed` stands only if the CHARGED
                                                        # curve confirms it. RELAX-ONLY: never adds doom.
        self.recur_fuel_relax = recur_fuel_relax        # ADR-0076 S2: quantifies `_doom_recur_fueled`'s
                                                        # all-or-nothing relax-block. ON only ever narrows.
        self.scaled_threat_rank = scaled_threat_rank    # Issue #213: price the threat rank through the Damage
                                                        # Formula instead of printed `maxDamage`
        self.gust_target_slots = gust_target_slots      # ADR-0076: gust rows route to `gust_target` INSTEAD of
                                                        # `deny` (never both). OFF = `deny`-only routing
        self.deny_strip_delta = deny_strip_delta        # ADR-0078 COMPUTE-ONLY: adds the per-instrument STRIP
                                                        # delta. Nothing reads the fields, so ON decides nothing.
        self.snipe_relevance = snipe_relevance          # ADR-0085: the Snipe Relevance scalar DECIDES the
                                                        # bench-target select; the six target rungs + the
                                                        # ADR-0051 steer stand down together while it is armed
        self.deny_relevance = deny_relevance            # ADR-0080: emits the Deny Relevance read and ARMS all
                                                        # three deny surfaces. OFF leaves ADR-0062's oracle live.
        self.leaf_followups = leaf_followups            # Issue #387: Mega Starmie's validated CARD and
                                                        # multi-pick leaf ownership; other decks defer.
        self._phase_prev = None                         # Carried State (ADR-0068): the phase hysteresis memory
                                                        # — read via `carried()`, never mutated by a hypothetical
        self.gamble_lines = gamble_lines                # ADR-0039: the Tier-2 Gamble rung
        self.value_model = value_model                  # ADR-0042 Tier-5; None / null model = off
        self._search_steps = 0                          # per-move Engine-Search step budget counter
        self._locked_line = None                        # turn-scoped {"turn": n, "queue": [entries]} or None
        self._lethal_lost = False                       # sparse telemetry key `lethal_lost`
        self._lethal_refutes = 0                        # per-plan; reset at each plan_turn (ADR-0037)
        from common.transients import TransientTracker, TurnBoostTracker
        self._transients = TransientTracker(self._attack_stat)   # ADR-0033: next-turn grants inferred from
                                                        # ATTACK logs — obs exposes no effect state
        self._incoming_budget = None                    # ADR-0064, set per decision in _board
                                                        # (None = worst-case ceiling)
        self._state_model = None                        # ADR-0068, built by `_board()`. DECLARED here so a
                                                        # consumer can ask "is there a snapshot?" rather than
                                                        # spell it `getattr(self, ..., None)`.
        self._opp_attack_context = None                 # the opponent-as-attacker Damage-Formula context,
                                                        # same lifecycle, declared for the same reason
        self._my_attack_context = None                  # ... and MY direction (see `_my_damage_context`),
        self._my_attack_context_obs = None              # anchored to the obs it was built from
        from common.strategy.combat import CombatMath
        self.combat = CombatMath(stats, functions, transients=self._transients,
                                 effects=self.effects)                            # the KO oracle
                                                        # (ADR-0052): the one closed-form combat home
        self._turn_boosts = TurnBoostTracker(            # this-turn flat damage-boost plays (Power Pro class)
            lambda cid: self.stats.get(cid) if (self.stats and cid is not None) else None)
        self._fetch_cache: dict = {}                    # memo: search card id -> the REACH set (ADR-0073)
        self._deadness_cache: dict = {}                 # memo: search card id -> the DEADNESS set (ADR-0073)
                                                        # — wider: every deck-zone target class
        self._chain_target_cache: dict = {}             # memo: tutor card id -> FULL-scope deck fetch targets
        self._item_hold_cache: dict = {}                # PER-DECISION (reset in `_board`), keyed by card id.
                                                        # Initialised here so a Pilot that never reaches
                                                        # `_board()` still resolves.
        self._derived_accel_cache = None                # memo: derived bench-accel body ids (deck-fixed)
        self._discard_fuel_cache = None                 # memo: energy types a discard-source accel attack
                                                        # wants IN the discard (deck-fixed; Aura Jab class)
        self._turn_plan = None                          # ADR-0031: (fingerprint, TurnLine|None); re-planned
                                                        # on a reveal
        self._composer_trace = None                     # POC-T4/5: the last composer run's margin + stats
        self._planning = False                          # reentrancy guard: True while an engine sim re-runs
                                                        # policy, so plan_turn stays closed-form
        self._bellman_registry = None                   # Mega Starmie's atomic post-setup planner boundary

    def decide(self, obs: dict) -> list[int]:
        """The highest-scoring legal selection (the grader hot path): the deck on the initial
        selection, else option indices (count in [minCount, maxCount], unique, in range)."""
        return self._evaluate(obs).chosen

    def explain(self, obs: dict) -> Decision:
        """Same choice as `decide`, plus the per-option trace (which Hypotheses fired, the
        Plan, the card) — the legibility record the writeup is generated from (ADR-0008)."""
        return self._evaluate(obs)

    def _evaluate(self, obs: dict, *, carried=None) -> Decision:
        """``carried`` forwards a Carried State snapshot to the board build, making the whole
        evaluation non-mutating in the two memories (ADR-0068 decision 2)."""
        select = obs.get("select")
        if select is None:                       # initial deck-submission step
            return Decision(chosen=list(self.deck))
        if not self._planning:                   # ADR-0033: consume the REAL log stream only —
            self._observe_known_top(obs)         # Issue #289: live, self-verifying top-deck belief
            self._transients.observe(obs)        # engine-sim future must never mutate match state
            self._turn_boosts.observe(obs)
        if (self.strategy.params.get("bellman_turn_planner") is True
                and int(select.get("context", -1))
                not in (_SETUP_ACTIVE, _SETUP_BENCH, _IS_FIRST, _MULLIGAN)):
            return self._bellman_evaluate(obs, carried=carried)
        options = select.get("option") or []
        board = self._board(obs, select, carried=carried)
        traces = [self._option_trace(obs, select, board, o, i) for i, o in enumerate(options)]
        starter_pick = self._declared_starter_pick(obs, select, board.top_starter_id)
        if starter_pick is not None:
            return Decision(chosen=[starter_pick], options=traces, read=board.read,
                            posture=self._posture_record(board),
                            objectives=self._objectives_trace(board), win_prob=self._win_prob(board),
                            game_plan=self._game_plan_record(board),
                            lethal_refuted=self._lethal_refutes)
        replayed = self.replay_locked_line(obs, select)   # ADR-0037 stage 3: a verified locked line
        if replayed is not None:                          # owns the turn — identity-matched replay,
            chosen, line = replayed                       # any divergence falls through below
            return Decision(chosen=chosen, options=traces, read=board.read, planned=line,
                            posture=self._posture_record(board),
                            objectives=self._objectives_trace(board), win_prob=self._win_prob(board),
                        game_plan=self._game_plan_record(board),
                            lethal_refuted=self._lethal_refutes)
        planned = self.plan_turn(obs, select, board, options, traces)  # ADR-0037: the ONE planning
        refuted = self._lethal_refutes                  # entry — win rung (take the win now) first, then
        if planned is not None:                         # the below-win Goal Ladder. Refutes kept on every
            # The empty-Bench guard applies HERE TOO (ADR-0086 decision 7). On override the line is
            # DROPPED: `planned.next_step == chosen` is a well-formedness invariant of the record.
            _rest = [i for i in range(len(options)) if i not in set(planned.next_step)]
            _guarded = self._empty_bench_forced(obs, select, board, options,
                                                list(planned.next_step) + _rest)
            _overridden = bool(_guarded) and _guarded[0] not in planned.next_step
            planned_steps = [_guarded[0]] if _overridden else list(planned.next_step)
            return Decision(chosen=planned_steps,       # Decision shape so a lethal_verify drop is countable
                            options=traces, read=board.read,
                            planned=None if _overridden else planned,
                            posture=self._posture_record(board),
                            objectives=self._objectives_trace(board), win_prob=self._win_prob(board),
                        game_plan=self._game_plan_record(board),
                            composer=(self._composer_trace                     # POC-T4/5: the margin
                                      if planned.goal == "compose" else None),   # telemetry (sparse)
                            gamble=getattr(self, "_gamble_trace", None),
                            attach_working=self._attach_working(obs, select, board, options),
                            lethal_refuted=refuted, lethal_lost=self._lethal_lost)
        max_count = select.get("maxCount", 0)
        by_score = self._score_order(obs, options, traces)
        by_score = self._prefer_soonest_arming_evolve(by_score, options, traces)
        order = self._finish_turn_last(obs, board, options, traces, by_score, max_count,
                                       select.get("context"))
        # The empty-Bench guard runs LAST, above the sequencer: it is a soundness FILTER, so
        # nothing downstream may re-order a deploy back below End (ADR-0086 decision 7).
        order = self._empty_bench_forced(obs, select, board, options, order)
        reordered = order != by_score
        grabbed = max_count > 1 and select.get("context") in _GRAB_CONTEXTS
        leaf_picks = None
        if self.leaf_followups and select.get("context") == _DISCARD and max_count > 0:
            leaf_picks = self._leaf_discard_picks(obs, select, options, max_count)
        elif select.get("context") == _DISCARD and max_count > 0:
            leaf_picks = self._deferred_deck_discard_picks(obs, select, board, options, max_count)
        if leaf_picks is not None:
            chosen = leaf_picks
        elif grabbed and self.leaf_followups and select.get("context") == _TO_BENCH:
            chosen = self._leaf_grab_picks(obs, select, board, options,
                                           select.get("minCount", 0), max_count)
            if chosen is None:
                chosen = self._greedy_grab(obs, select, board, traces, options,
                                           select.get("minCount", 0), max_count)
        elif grabbed:
            chosen = self._greedy_grab(obs, select, board, traces, options,
                                       select.get("minCount", 0), max_count)
        else:
            chosen = order[:max_count]
            # take-fewer at an OPTIONAL select: DECLINE a pick a Hypothesis actively discourages
            # (score < 0) — the single-pick analog of `_greedy_grab`'s take-fewer.
            min_count = select.get("minCount", 0)
            while len(chosen) > min_count and traces[chosen[-1]].score < 0:
                chosen = chosen[:-1]
        chosen = self._never_pre_bench(select, chosen)
        return Decision(chosen=chosen, options=traces, read=board.read, lethal_refuted=refuted,
                        posture=self._posture_record(board),
                        objectives=self._objectives_trace(board), win_prob=self._win_prob(board),
                        game_plan=self._game_plan_record(board),
                        gamble=getattr(self, "_gamble_trace", None),
                        # Emitted on the DEFER path too: a key that appeared only when the composer WON
                        # would answer "did it fire" with "did it agree".
                        composer=getattr(self, "_composer_trace", None),
                        attach_working=self._attach_working(obs, select, board, options),
                        lethal_lost=self._lethal_lost, reordered=reordered, grabbed=grabbed)

    def _bellman_evaluate(self, obs: dict, *, carried=None) -> Decision:
        """The isolated Mega Starmie route. No legacy score, planner, or chooser is consulted."""
        from common.bellman import (
            MegaStarmiePotential, MegaStarmieTurnPlanner, PlanRequest, ValueRegistry,
            opponent_belief,
        )

        read = self.opponent.observe(obs) if self.scout is not None else None
        gamma = _posture_gamma(read) if (self.posture and read is not None) else 0.0
        my_arch = self.strategy.params.get("my_archetype")
        favorability, coverage = (
            matchup_favorability(self.scout.artifact, my_arch, read.candidates)
            if self.posture and self.scout is not None and read is not None and my_arch
            else (0.5, 0.0)
        )
        brief = match_brief(self.briefs, read) if (self.posture and read and gamma > 0) else None
        state = obs.get("current") or {}
        seat = int(state.get("yourIndex", 0))
        players = state.get("players") or ()
        opponent = players[1 - seat] if len(players) > 1 and players[1 - seat] else {}
        ids_for_name = getattr(self.stats, "ids_for_name", None)
        brief_roles = (resolve_brief_cards(brief, ids_for_name)[1]
                       if brief is not None and ids_for_name is not None else {})
        matchup_plan = self._matchup_plan(opponent, brief_roles, read, gamma)
        belief = opponent_belief(
            obs, candidates=(read.candidates if read is not None else ()),
            properties=(brief.opponent_properties if brief is not None else None),
        )
        if self._bellman_registry is None:
            self._bellman_registry = ValueRegistry.from_strategy(
                strategy=self.strategy, stats=self.stats, functions=self.functions, deck=self.deck)
        planned = MegaStarmieTurnPlanner(
            registry=self._bellman_registry,
            family_evaluator=MegaStarmiePotential(
                self.stats, functions=self.functions,
                threat_roles={card_id: assignment.role for card_id, assignment
                                          in matchup_plan.assignments.items()}),
            belief=belief).decide(
                PlanRequest(obs, tuple(self.deck), self.strategy.name))
        select = obs.get("select") or {}
        menu = select.get("option") or ()
        chosen = list(planned.chosen)
        traces = [OptionTrace(
            index=index, score=(planned.value if index in chosen else 0.0), plan=Plan.RACE,
            card_id=None, fired=[], tactical=(planned.value if index in chosen else 0.0),
        ) for index, _option in enumerate(menu)]
        telemetry = {
            "bellman": True,
            "action": dataclasses.asdict(planned.action),
            "value": planned.value,
            "complete": planned.complete,
            "ledger": planned.diagnostics.get("ledger"),
            "production": planned.diagnostics.get("production"),
            "root": dataclasses.asdict(planned.diagnostics["root"]),
        }
        return Decision(chosen=chosen, options=traces, read=read,
                        posture={"gamma": gamma, "source": "scouting"}, composer=telemetry)

    def _leaf_discard_picks(self, obs: dict, select: dict, options: list, maximum: int) -> list[int] | None:
        """Mandatory discard picks, repriced after each removed visible hand card."""
        seat = int((obs.get("current") or {}).get("yourIndex") or 0)
        hand = ((obs.get("current") or {}).get("players") or [{}])[seat].get("hand") or []
        hand_indices = [option.get("index") for option in options]
        if (len(options) < maximum
                or any(not isinstance(index, int) or not 0 <= index < len(hand)
                       for index in hand_indices)
                or len(set(hand_indices)) != len(hand_indices)):
            return None
        try:
            model = self._leaf_state_model(obs, seat)
            root_needs = model.mine.needs
            if (root_needs is None or len(root_needs.eligibility) != len(hand)
                    or len(root_needs.hand_ids) != len(hand)):
                return None

            def project(indices):
                removed = {options[i]["index"] for i in indices}
                after = copy.deepcopy(obs)
                mine = after["current"]["players"][seat]
                mine["hand"] = [card for index, card in enumerate(hand) if index not in removed]
                mine["handCount"] = len(mine["hand"])
                mine["discard"] = list(mine.get("discard") or []) + [hand[index] for index in sorted(removed)]
                keep = [index for index in range(len(hand)) if index not in removed]
                latent_by_hand = tuple(root_needs.latent_by_hand[index] for index in keep) \
                    if len(root_needs.latent_by_hand) == len(hand) else ()
                projected_needs = needs.Resolution(
                    slots=root_needs.slots,
                    eligibility=tuple(root_needs.eligibility[index] for index in keep),
                    edge_values=tuple(root_needs.edge_values[index] for index in keep)
                    if len(root_needs.edge_values) == len(hand) else (),
                    resupply=root_needs.resupply,
                    hand_ids=tuple(root_needs.hand_ids[index] for index in keep),
                    latent_worth=sum(latent_by_hand),
                    latent_by_hand=latent_by_hand,
                    unknowns=root_needs.unknowns)
                return model.rebuilt(after, needs_override=projected_needs)

            return leaf_pick_indices(model, minimum=int(select.get("minCount", 0)), maximum=maximum,
                                     keys=canonical_keys(options, obs), project=project)
        except (IndexError, KeyError, TypeError, ValueError, board_delta.Unmodellable):
            return None

    def _deferred_deck_discard_picks(self, obs: dict, select: dict, board: Board,
                                     options: list, maximum: int) -> list[int] | None:
        """Preserve the validated Needs owner for decks deferred to Issue #388."""
        rows = self._discard_equation_rows(obs, select, board, options)
        if not rows:
            return None
        _keeps, picks = self._needs_v2(obs, board, rows, maximum)
        return picks or None

    def _leaf_grab_picks(self, obs: dict, select: dict, board: Board, options: list,
                         minimum: int, maximum: int) -> list[int] | None:
        """Fetch picks, repriced after each selected card enters the hypothetical hand or Bench."""
        seat = int((obs.get("current") or {}).get("yourIndex") or 0)
        bench_context = select.get("context") in _BENCH_PLACEMENT_CONTEXTS
        if bench_context:
            capacity = max(0, board_delta.bench_max(obs, seat) - int(board.my_bench or 0))
            maximum = min(maximum, capacity)
            minimum = min(minimum, maximum)
        if maximum <= 0:
            return []
        card_ids = [self._option_card_id(obs, select, option) for option in options]
        if any(card_id is None for card_id in card_ids):
            return None
        try:
            model = self._leaf_state_model(obs, seat)

            def project(indices):
                after = copy.deepcopy(obs)
                mine = after["current"]["players"][seat]
                if bench_context:
                    bench = list(mine.get("bench") or [])
                    for index in indices:
                        card_id = card_ids[index]
                        stat = self.stats.get(card_id) if self.stats else None
                        if stat is None:
                            raise board_delta.Unmodellable("selected Bench card has no stat")
                        bench.append(board_delta.bench_body(card_id, stat, seat_index=seat,
                                                           serial=-(index + 1)))
                    mine["bench"] = bench
                else:
                    hand = list(mine.get("hand") or [])
                    hand.extend({"id": card_ids[index], "playerIndex": seat} for index in indices)
                    mine["hand"] = hand
                    mine["handCount"] = len(hand)
                return model.rebuilt(after)

            return leaf_pick_indices(model, minimum=minimum, maximum=maximum,
                                     keys=canonical_keys(options, obs), project=project)
        except (IndexError, KeyError, TypeError, ValueError, board_delta.Unmodellable):
            return None

    @staticmethod
    def _posture_record(board: Board) -> dict | None:
        """Compact posture summary for Decision Telemetry (ADR-0041). None when no Scout is wired,
        so the wire key stays sparse. A belief snapshot, never decision input."""
        read = board.read
        if read is None:
            return None
        return {
            "cands": [[a, round(p, 3)] for a, p in read.candidates],            # believed archetype(s), top-k
            "conf": [round(read.confidence[0], 3), round(read.confidence[1], 3)],  # (top posterior, margin)
            "unknown": round(read.unknown_mass, 3),                             # unmatched posterior mass
            "gamma": round(board.posture_confidence, 3),   # APPLIED Posture strength (0 = off/unrecognized)
            "fav": round(board.favorability, 3),           # modeled matchup win-rate (lever A); 0.5 = neutral
            "cov": round(board.matchup_coverage, 3),       # posterior share behind `fav` (its reliability)
            "brief": board.brief.slug if board.brief else None,   # matched Matchup Brief (ADR-0027), or None
        }

    def _objectives_trace(self, board: Board) -> dict | None:
        """Sparse ADR-0040 trace; None when neither path resolves."""
        if board.my_path_turns is None and board.their_path_turns is None:
            return None
        return {"race": board.race_ahead, "my": board.my_path_turns, "their": board.their_path_turns}

    def _win_prob(self, board: Board) -> float | None:
        """ADR-0042 P(win), rounded for the wire; None when the model is off. Legibility only — the
        leaf blend is where it changes a decision."""
        vm = getattr(self, "value_model", None)
        if not vm or not vm.present:
            return None
        try:
            from common.value.features import features_from_board
            return round(vm.predict(features_from_board(board)), 4)
        except Exception:
            return None

    def _game_plan_record(self, board: Board) -> dict | None:
        """Compact Game Plan for Decision Telemetry (ADR-0045); None when no plan was computed. A
        belief snapshot, never decision input."""
        gp = board.game_plan
        if gp is None:
            return None
        return {"mode": gp.mode.name, "conf": round(gp.confidence, 3), "goal": gp.directed_goal,
                "route": len(gp.route), "route_turns": gp.route_turns}

    def _option_trace(self, obs: dict, select: dict, board: Board, option: dict,
                      index: int) -> OptionTrace:
        ctx = self._context(obs, select, board, option)   # built first: the matchup snipe steer
                                                           # respects its ADR-0044 redundancy flags
        attach_row = self._attach_decision(obs, select, board, option)   # priced ONCE: the score term
                                                           # and the planner's spend account read it
        evolve_row = self._evolve_decision(obs, board, ctx, option)      # the EVOLVE decider (ADR-0070)
        promote_row = self._promote_retreat_decision(obs, select, board, ctx, option)  # ADR-0100
        deploy_row = self._deploy_decision(obs, select, board, option)   # ADR-0086 (#197)
        tactical = (self._tactical(obs, board, option)
                    + self._snipe_tera_veto(ctx)      # card fact: a benched Tera takes NO damage
                    + self._refresh_swing_tactical(obs, board, ctx)
                    + self._hand_size_relief_tactical(obs, board, ctx)   # ADR-0102: the SURVIVAL leg
                    + self._grab_refresh_value(obs, board, ctx)          # of the same refresh, summed
                                                                         # ACROSS axes (cards vs damage)
                    + self._top_deck_tactical(obs, select, board, option)
                    + self._denial_play_tactical(obs, board, ctx)
                    + self._denial_target_tactical(obs, select, board, option)
                    + self._snipe_relevance_tactical(obs, select, board, option, ctx)
                    + self._snipe_brief_tiebreak(obs, select, board, option, ctx)
                    + self._snipe_ko_dominator(ctx)   # armed: the KO rung, as structure not a weight
                    + self._gust_tactical(obs, select, board, option)
                    + self._gust_target_tactical(obs, select, board, option)
                    + self._heal_target_tactical(obs, select, board, option)   # ctx 17 (Issue #409)
                    + self._evolve_target_tactical(obs, select, board, option, ctx)  # ctx 18: WHERE a
                                                                       # searched-out evolution lands
                    + self._gust_stall_target_tactical(obs, select, board, option)
                    + self._attach_lethal_tactical(obs, select, board, option)
                    + self._boost_lethal_tactical(obs, select, board, option)
                    + self._retreat_to_lethal_tactical(obs, board, option)
                    + self._promote_ko_tactical(obs, select, board, option)   # ADR-0100 §11
                    + self._grab_lethal_tactical(obs, select, board, option)
                    + self._grab_enabler_lethal_tactical(obs, select, board, option)
                    + self._grab_retreat_tool_lethal_tactical(obs, select, board, option)
                    + self._attach_retreat_tool_lethal_tactical(obs, select, board, option)
                    + (attach_row["tactical"] if attach_row is not None else 0.0)
                    + (evolve_row["tactical"] if evolve_row is not None else 0.0)
                    + (promote_row["tactical"] if promote_row is not None else 0.0)
                    + (deploy_row["total"] if deploy_row is not None else 0.0))
        hyps = (*self.general.hypotheses, *self.strategy.hypotheses)
        fired = [(h, self._weight(h)) for h in hyps if _fires(h, ctx)]
        # No attach fold set: the rungs the attach decider replaced are DELETED (ADR-0069 §7), not
        # shadowed, so nothing on an attach option can double-count with `_attach_value_tactical`.
        # Cards are costed by the shared hand/leaf Worth and Retreat by its dedicated equation.
        # Only the two remaining non-card resources need this strict ordinal residual: an attack
        # ends the turn and an activated Ability spends its allowance. End alone remains exact 0.
        score = (sum(w for _h, w in fired) + tactical
                 - action_cost.residual_cost_damage(option.get("type")))
        return OptionTrace(index=index, score=score, plan=ctx.plan, card_id=ctx.card_id,
                           fired=fired, tactical=tactical,
                           attach_to_needy_line=ctx.attach_target_is_line_member and ctx.attach_target_needs,
                           attach_spend=(-attach_row["evaporation_loss"] * _ATTACH_VALUE_SCALE
                                         if attach_row is not None else 0.0),
                           evolve_working=evolve_row,
                           deploy_working=deploy_row,
                           promote_retreat_working=promote_row)

    # ── the PROMOTE/RETREAT DECIDER (ADR-0100, Issue #141): ONE evaluator, three call sites (§9).
    # Every read routes through the StateModel snapshot, so no memoized clock shifts under a build.

    def _weight(self, h) -> float:
        """Resolved by id (0 disables): the learned override over the deck's authored seed override
        (ADR-0035) over the authored default."""
        if h.id in self.overrides:
            return self.overrides[h.id]
        return self.strategy.weight_overrides.get(h.id, h.weight)

    # `_rider_snipe` / `_rider_spread` / `_rider_recoil` DELETED (Issue #260): card knowledge belongs
    # on the oracle, so use `self.combat.rider_*`.

    # `_attach_provision` DELETED (Issue #418): it answered "how many units" and could not express the
    # COLOUR. Use `CombatMath.provision_codes`, which answers both halves.

    # ── the DEPLOY decider (ADR-0086, Issue #197) ────────────────────────────────────────────────

    @staticmethod
    def _known_top_log_key(log: dict) -> tuple | None:
        cid, serial = log.get("cardId"), log.get("serial")
        if cid is None or serial is None:
            return None
        return (int(serial), int(cid))

    @staticmethod
    def _known_top_reconcile(known: list, log: dict) -> list:
        key = Pilot._known_top_log_key(log)
        if key is None or not known:
            return []
        return known[1:] if tuple(known[0]) == key else []

    def carried(self):
        """The declared channel for facts persisting ACROSS decision points (ADR-0068 decision 2).
        Pass it to any HYPOTHETICAL board build so a simulated line cannot leak into live memory."""
        from common.state_model import CarriedState
        return CarriedState.of(phase_prev=getattr(self, "_phase_prev", None),
                               my_path_prev=getattr(self, "_my_path_prev", None),
                               known_top=getattr(self, "_known_top", None))

    def _snapshot(self, obs: dict, *, my_index=None, deck_empty=None,
                  read=None, brief=None, matchup_plan=None, gamma: float = 0.0,
                  favorability: float = 0.5, matchup_coverage: float = 0.0,
                  carried=None) -> StateModel:
        """Build (and stash) the per-decision :class:`StateModel` — **the ONE construction site**; a
        second would be a second opinion about what a snapshot IS (ADR-0092)."""
        state = obs.get("current") or {}
        mi = state.get("yourIndex", 0) if my_index is None else my_index
        if deck_empty is None:
            players = state.get("players") or []
            me = players[mi] if 0 <= mi < len(players) and players[mi] else {}
            raw_prizes = obs.get("own_prizes")
            prizes = {int(k): v for k, v in raw_prizes.items()} if raw_prizes else raw_prizes
            # `or None` collapses an EMPTY multiset, which is what this fallback has always done for
            # `deck_empty`. `_board` and `_damage_context` both keep `{}` as itself.
            deck_empty = self._deck_empty_ids(me, prizes or None)
        self._state_model = model = StateModel.build(
            obs, combat=self.combat, my_index=mi, deck=self.deck, deck_empty=deck_empty,
            role_worth=self._role_value,
            # THEIR half, fully threaded — the Read overlay (ADR-0026/0027/0047/0051) …
            read=read, brief=brief, matchup_plan=matchup_plan, posture_confidence=gamma,
            favorability=favorability, matchup_coverage=matchup_coverage, opponent=self.opponent,
            # … and the two clock parameters (see the docstring).
            forward_ids=self._forward_card_ids, charged=self._incoming_budget,
            # the this-turn flat damage-boost PLAYS, side-keyed: `build` resolves each side's tuple
            # because it is the only place that knows which seat is mine (POC-T3.5, Issue #279).
            turn_boosts=self._turn_boosts,
            carried=carried if carried is not None else self.carried())
        return model

    # Shuffle-Refresh doctrine's signals live in doctrine_shuffle_refresh (ShuffleRefreshMixin); `_board` calls them.

    # `_evolving_wincon_on_bench` was DELETED by ADR-0085 Amendment G along with the
    # `evolving_wincon_priority` kill-switch it gated. See the Board field note above.

    # `_snipe_matchup_tactical` DELETED (ADR-0085 decision 5): the steer travels as the Brief
    # MULTIPLIER inside `snipe_relevance.target_relevance`.

    # `_strongest_threat_rank` DELETED (ADR-0085). `_target_threat_rank` / `_body_threat_rank`
    # SURVIVE: the Planner's `ko_key_threat` rung consumes them.

    # STRICTER than `_incoming_budget`'s `base_attach: 1` because the survival boolean is
    # catastrophe-grade: 2 = the manual attach PLUS one generic supporter-accel (ADR-0064).
    _DOOM_CHARGED = {"base_attach": 2, "burst_on_evo": 2}

    #: INSTANTANEOUS policy for the deny Δ (ADR-0078 Amendment B): deny prices only Energy on their
    #: board NOW — at `base_attach: 1` a single strip is cancelled by construction.
    _DENY_CHARGED = {"base_attach": 0, "burst_on_evo": 0}

def _fires(h, ctx: Context) -> bool:
    try:
        return bool(h.when(ctx))
    except Exception:
        return False
