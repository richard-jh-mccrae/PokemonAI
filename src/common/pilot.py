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
from dataclasses import dataclass, field, replace
from typing import NamedTuple

from common import board_delta                # the Stadium clause home (Issue #410): its
                                              # `stadium_hp_delta` + `applies_to` predicate are what
                                              # `_stadium_hp_shift` reads, never re-derived
                                              # (Issue #424)
from common import deck_odds
from common import retreat_cost                # ADR-0100 §8's grant-aware cost, shared with
                                              # `board_choice`'s Energy-discard target space
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
                                                       # fact (the fingerprint), never the menu index

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
#                                             the relevance normalizer, imported so `_DENY_RELEVANCE_K`
#                                             below is the SAME number by construction rather than a
#                                             copy that could drift when a new set re-derives it
from common.strategy.combat import (Budget, CURRENT_FORMS_ONLY,  # noqa: E402  (re-used
                                    _EFFICIENCY, HARVEST_UNAVOIDABLE, UNCHARGED)  # by the tactical scorers)
from common.strategy.refresh import (fresh_cards, net_change, opponent_shuffles,  # noqa: E402
                                     refresh_branches)  # (ADR-0060 swing oracle)
from common.strategy.sequence import followup_damage  # noqa: E402  (ADR-0061 horizon-2 lock oracle)
from common.strategy.denial import coin_odds          # noqa: E402  (ADR-0062 energy denial)

# --- the families (`common/deciders/`) ---
from common.deciders.attach import (AttachMixin, _ATTACH_VALUE_SCALE, _ATTACH_RETREAT_EQUITY,
                                    _ATTACH_ABILITY_FUEL, _ATTACH_RESOURCE_TIEBREAK, _ATTACH_PREEVO_DISCOUNT)  # noqa: F401
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
    """Why one option scored what it did — the legibility record (ADR-0008): which
    Hypotheses fired (general + deck) with their effective weights, plus the combat term."""
    index: int
    score: float
    plan: Plan
    card_id: int | None
    fired: list                  # [(Hypothesis, effective_weight)] whose trigger fired
    tactical: float = 0.0
    deferred: bool = False       # a turn-ending attack held behind beneficial development (attack-last)
    attach_spend: float = 0.0    # the attach decider's ACTION-referent SPEND on this option (ADR-0069):
                                 # minus the scaled evaporation loss when a `discard_eot` Energy is
                                 # attached where it buys nothing before end of turn. Negative or 0.
                                 # Feeds the develop-rollout planner's Class-B spend account — a
                                 # consumed one-shot is invisible on the end board (spent cards don't
                                 # show), which is exactly the account's contract. It replaces the five
                                 # deleted burst rungs the account used to read out of `fired`.
    attach_to_needy_line: bool = False  # this option attaches Energy to a NEEDY win-condition Line body
                                 # (a base that builds the payoff) — decide()-only ORDERING tie-break: among
                                 # EQUAL-score attaches, feed Line base first. W-route-invisible, never enters weight fit. ep82867148 f87
    # `hand_size_relief` DELETED (ADR-0102, Issue #261 item 2c): the reporting-only field existed so
    # the hand-size calculation stayed VISIBLE while it earned promotion. It is promoted —
    # `_hand_size_relief_tactical` is IN `score` — so a second, differently-shaped copy of the same
    # quantity beside it would be a shadow of a live term, which is the surface this POC deletes.
    deploy_working: dict | None = None  # the DEPLOY DECIDER's legible working (ADR-0086): the per-leg
                                 # breakdown for a Bench deployment. The decider sweep prints it on
                                 # BOTH sides of a flip and a human rules the Decision Gate by
                                 # reading it, so a bare total would make that gate unrulable.
    evolve_working: dict | None = None  # the EVOLVE DECIDER's legible working (ADR-0070): the per-option
                                 # TERM row — deploy (with each body's this_turn / payoff / the two clocks),
                                 # income_gain, income_loss, and the `tactical` the option actually scored.
                                 # Like `attach_working` this DECIDES, so there is no agreement bit: one
                                 # emission path, one truth, and the substrate #146/#148 consume. Sparse:
                                 # None off an EVOLVE option or while the kill-switch is OFF.
    promote_retreat_working: dict | None = None  # the PROMOTE/RETREAT DECIDER's legible working
                                 # (ADR-0100, #141): the per-option TERM row — my_yield, closure,
                                 # exposure, tempo_denied, fatal, and (whether-site only) preservation
                                 # and retreat_cost, plus the `tactical` the option actually scored.
                                 # Like `attach_working`/`evolve_working` this DECIDES, so there is no
                                 # agreement bit: one emission path, one truth. `site` names which of
                                 # ADR-0100 §9's call sites priced it ("pick" | "whether"). Sparse:
                                 # None off a promote/retreat option or while the kill-switch is OFF.


@dataclass
class Decision:
    """A scored decision: the chosen option indices and the per-option OptionTrace."""
    chosen: list
    options: list = field(default_factory=list)
    read: Read | None = None     # the per-decision Scouting Read (ADR-0026), surfaced for legibility
    posture: dict | None = None  # compact posture summary for telemetry (ADR-0041): the believed
                                 # archetype(s) + how strongly Posture acted, sourced from the Board.
                                 # None when no Scout is wired; telemetry emits it under `posture`
    planned: TurnLine | None = None   # the committed Turn Line this turn (ADR-0031/0037), or None.
                                      # goal "win" = the Lethal Solver's LOCK (the sound top rung;
                                      # telemetry serialises it under the wire-compatible `lethal`
                                      # key); any other goal = a below-win heuristic Goal-Ladder plan
    lethal_refuted: int = 0      # direct lethal candidates the engine backstop REFUTED this plan
                                 # (`lethal_verify`, ADR-0030) — nonzero means closed-form claimed a win
                                 # the engine denied, the exact divergence an A/B or correction wants
    objectives: dict | None = None   # sparse Tier-3 trace (ADR-0040): {"race", "my", "their"} — the
                                     # live race delta + both cheapest-path turns; None off-board /
                                     # both paths unknown. Telemetry emits it for the writeup/tuner.
    gamble: dict | None = None   # sparse Tier-2 working-trace (ADR-0039): the gamble rung's full
                                 # calculation (pool/det/classes with the sought out-card ids/per-
                                 # option p·EV) or its stand-down reason — the blunder shell shows
                                 # it as a dropdown so shuffle/fetch corrections are fully analyzable
    win_prob: float | None = None    # Tier-5 (ADR-0042): the Automatic Value Model's P(win) on THIS
                                     # decision's board — emitted for calibration measurement on real
                                     # games; None when the model is off/absent (no learned claim)
    lethal_lost: bool = False    # a locked verified line DIVERGED from the live game and was dropped
                                 # (`lethal_veto`, ADR-0037 stage 3) — sparse telemetry key
    reordered: bool = False      # `chosen` came from the attack-last resequencer (`_finish_turn_last`)
                                 # changing the score order, NOT argmax(score) — sparse telemetry key so
                                 # a trace reader doesn't misread "top-score not chosen" as a scoring bug
    grabbed: bool = False        # `chosen` is a `_greedy_grab` multi-pick set (dynamic gap-scoring),
                                 # NOT the top-N static scores — sparse telemetry key, same legibility
    game_plan: dict | None = None    # the Match Planner's Game Plan (ADR-0045), compact for telemetry:
                                     # mode + confidence + route + directed goal. Sparse; `/blunder-buster`
                                     # ties a ladder misplay to this match-scale read
    composer: dict | None = None     # the SEQUENCE COMPOSER's per-decision telemetry (POC-T4/5): the
                                     # margin block Issue #263 § *Beam-quality package* item 3 REQUIRES
                                     # (the chosen first step's 1-ply rank relative to k and its margin to
                                     # the k-th candidate), the run stats, the winning candidate's
                                     # `working()` legs and its step indices, plus any coverage-gap
                                     # reasons. Sparse: None unless the composer ran. It REPLACES
                                     # `plan_candidates`, the develop rollout's top-K ranked end-boards,
                                     # which died with that rung — a near-miss at the beam cutoff is the
                                     # early warning the ranked list used to stand in for
    attach_working: dict | None = None  # the ENERGY-ATTACH DECIDER's legible working (ADR-0069 §9):
                                     # the per-option AXES rows — attack_axis (this_turn / build /
                                     # accel_value), retreat_equity, ability_fuel, evaporation_loss,
                                     # which gate fired, and the `tactical` each option actually
                                     # scored. This DECIDES (the rows are the decider's own arithmetic,
                                     # not a shadow's), so there is no agreement bit: one emission path,
                                     # one truth. A Pokémon Tool ABSTAINS (not Energy) and is counted.
                                     # Sparse: None off an attach menu / mid-sim


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
                 snipe_relevance=False, copy_top_value=False,
                 deferred_target_expansion=False):
        self.strategy = strategy
        self.general = general_strategy or Strategy()   # deck-agnostic shared hypotheses (ADR-0008)
        self.overrides = overrides or {}                # machine-written weight overrides, by hyp id
        self.deck = list(deck)
        self.stats = stats
        self.functions = functions
        self.effects = effects                          # CardEffects (ADR-0032 Effect Clauses) —
                                                        # parametric card-tier facts (heal amounts,
                                                        # riders, restrictions); None = clause-blind
        self.search_budget = search_budget
        self.scout = scout                              # opponent Scout (ADR-0026); None = Posture off
        self.briefs = list(briefs) if briefs else []    # hand-authored Matchup Briefs (ADR-0027), covers-routed
        self.opponent = OpponentModel(scout=scout,      # the Opponent Model facade (ADR-0047): composes the
                                      artifact=getattr(scout, "artifact", None))  # Scout (DI) + Resources +
        # Dispositions. One observe() fan-out per decision, one board.opponent read surface. Behavior-neutral.
        self.posture = posture                          # ADR-0026 kill-switch: False forces γ=0 + neutral
                                                        # favorability → both levers off (the A/B baseline)
        self.lethal_verify = lethal_verify              # ADR-0030 kill-switch: engine-confirm a DIRECT
                                                        # lethal lock before trusting it (refute → no lock)
        self.lethal_seed_exact = lethal_seed_exact      # ADR-0050 kill-switch: seed the engine verify's
                                                        # hidden zones from the EXACT own deck/prize split
                                                        # (own_prizes) vs the old id-sorted decklist prefix
                                                        # that hid the high-id enabler band. OFF = prefix.
        self.planner_key_threat = planner_key_threat    # ADR-0031 kill-switch: the KO-the-key-threat
                                                        # Goal-Ladder rung (snipe-KO the benched top threat)
        self.lethal_family = lethal_family              # ADR-0037 kill-switch: the ONE win-generator
                                                        # family (single+multi-develop, gust, tutor; all
                                                        # min-bound) + verify on EVERY win lock; OFF =
                                                        # the legacy hook-trace rungs, direct-verify only
        self.lethal_veto = lethal_veto                  # ADR-0037 stage-3 kill-switch: a VERIFIED win
                                                        # lock materializes its confirmed cascade and
                                                        # REPLAYS it (identity-matched; mismatch -> fall
                                                        # back + `lethal_lost`); presumes lethal_family
        self.objectives_race = objectives_race          # ADR-0040 kill-switch: the Tier-3 KO Race —
                                                        # vs a standing wall, price attacks by their
                                                        # best min-turn SEQUENCE (chip included), not
                                                        # the biggest single hit
        self.objectives_path = objectives_path          # ADR-0040 kill-switch: the Prize-Path
                                                        # CONSUMERS (snipe-on-the-path, bench denial,
                                                        # planner on-path bump) — the Board signals
                                                        # themselves are always-on data
        self.objectives_phases = objectives_phases      # ADR-0040 kill-switch: the derived ADVISORY
                                                        # phases (STABILIZE/CLOSE overrides + the
                                                        # baseline_phases bands); off = readiness
                                                        # SETUP→RACE exactly as before
        self.snipe_prize_redundant = snipe_prize_redundant  # ADR-0044 kill-switch: the Prize-Redundant
                                                        # Target snipe suppression (+ body-identity path
                                                        # keying) — don't chip an off-path body I don't
                                                        # need to KO ("deny the second Mega")
        self.snipe_prize_reach = snipe_prize_reach      # snipe-grill kill-switch: the Prize-Path
                                                        # rider-reach TIE-BREAK — among prize-completing
                                                        # subsets tied on turns, put the +1 on the bench
                                                        # body my repeatable snipe rider finishes soonest
                                                        # (rides free with my main KOs). Pure tie-break;
                                                        # never moves my_path_turns. OFF = mask-order
        self.forced_promotion = forced_promotion        # ADR-0044 kill-switch: the Forced-Promotion Read
                                                        # — when their Active is dead, pre-chip the ready
                                                        # wincon they'll promote, not the energized bench-sitter
        self.match_planner_steer = match_planner_steer  # ADR-0045 kill-switch (S3): the Match Planner's
                                                        # Game Plan directed goal biases the Turn Planner's
                                                        # candidate ranking (sub-prize, confidence-scaled).
                                                        # Default OFF — byte-identical; matured via ladder
        self.promote_ko_aware = promote_ko_aware        # kill-switch: KO-aware, boost-inclusive promote
                                                        # pick — prefer promoting the benched wincon whose
                                                        # affordable attack (given the attachable Energy +
                                                        # playable {F} damage-boost) KOs the opp Active,
                                                        # over the energy-ranked pick. OFF = byte-identical
        self.boost_lethal = boost_lethal                # kill-switch: the `_family_win_candidates` tier that
                                                        # composes promote-a-benched-{F}-attacker → play N
                                                        # damage-boost Items → swing lethal (presumes
                                                        # lethal_family; engine-confirmed on every lock)
        self.retreat_enabler_lethal = retreat_enabler_lethal  # kill-switch: the `_family_win_candidates` tier
                                                        # that plays/tutors a retreat-reduction Tool (Air
                                                        # Balloon) to free a retreat into an already-winning
                                                        # benched attacker (ml f15; presumes lethal_family,
                                                        # engine-confirmed on every lock)
        self.disruptor_lock_maneuver = disruptor_lock_maneuver  # kill-switch: the OFFENSIVE retreat-into-
                                                        # a-benched-item_lock T2 disruption maneuver (dragapult
                                                        # f20; feeds `can_lock_line_with_disruptor`).
                                                        # Ship-and-refine: matchup-dependent value
        self.prize_economy_fetch = prize_economy_fetch  # ADR-0048 kill-switch: prize-economy FETCH tie-break
                                                        # + broadened line recognition (credit a secondary
                                                        # attacker Line's pre-evo). Default ON; OFF reverts to
                                                        # win-condition-only recognition — a secondary Line is inert
        self.matchup_targeting = matchup_targeting      # ADR-0051 kill-switch (default ON): the MatchupPlan
                                                        # target-priority spine — Brief + Read-Intel (γ-gated)
                                                        # + general draw-engine card fact, read by snipe/gust.
                                                        # OFF = empty plan (every priority 0), byte-identical
        self.ko_target_whiff = ko_target_whiff          # BUILD 1 kill-switch (DEFAULT OFF): among EQUAL-value
                                                        # KO/snipe targets, prefer the body the opponent is
                                                        # LEAST able to replace (lowest `copies_left_odds`).
                                                        # Pure tiebreak — never reorders a prize/survival delta
        self.opp_resource_reads = opp_resource_reads    # BUILD 2 kill-switch (DEFAULT OFF): a sub-prize nudge
                                                        # toward pressing KO/grind lines when the opponent is
                                                        # near deck-out (`opp_deckout_in_turns`, SOUND). Silent
                                                        # unless on AND a near-term deck-out is known
        self.enabler_item_composer = enabler_item_composer  # BUILD 3 kill-switch (DEFAULT OFF): the ko_for_prizes
                                                        # Item-tutor composer — play an ITEM that fetches an
                                                        # evolution of an in-play, this-turn-evolvable body →
                                                        # evolve → attach → KO, preferring the cheaper Item
                                                        # enabler over the scarce Supporter tutor
        self.leaf_hand_value = leaf_hand_value          # ADR-0065 WP-N5b kill-switch (default OFF): the
                                                        # develop-rung LEAF's actionable-resource term —
                                                        # readiness CONSUMES the needs module (the hand's
                                                        # slot coverage), the board-state-valuation fold.
                                                        # Needs the sim to plumb my end-of-turn hand into
                                                        # the (opponent-perspective) end obs. Gated on the
                                                        # leaf-lab bench (SOLE-top / distinct-values / Gate 0).
        # `needs_keep_value` DELETED (Issue #319): the keep-value v2 needs-assignment decides the
        # forced discard UNCONDITIONALLY. The flag was assigned here and read NOWHERE once Issue #261
        # item 2h made `_discard_needs_pick`'s call site unconditional. Rationale lives on
        # `_discard_needs_pick`; it is deliberately NOT restated here.
        self.promote_retreat_value = promote_retreat_value   # the PROMOTE/RETREAT DECIDER's emergency
                                                        # lever (ADR-0100, shipped ON): the Sub-lethal
                                                        # Residual, one evaluator across the body pick, the
                                                        # whether-to-retreat question and the forced
                                                        # promote. OFF is DEGRADED MODE, not a rollback —
                                                        # eleven of the twelve rungs it replaced are
                                                        # deleted, and POC-T4/5 took the twelfth
                                                        # (`retreat-to-wall-the-line`), so OFF is now
                                                        # SILENCE rather than a thinner voice.
        self.evolve_value = evolve_value                # the EVOLVE DECIDER's emergency lever (ADR-0070,
                                                        # shipped ON): the body-substituted deploy delta
                                                        # + odds-priced income. OFF is DEGRADED MODE, not
                                                        # a rollback — the four rungs it replaced are
                                                        # deleted, so OFF silences evolve endorsements
                                                        # and only the _PLAY-side Gate speaks.
        self.deploy_value = deploy_value            # the DEPLOY DECIDER's emergency lever
                                                    # (ADR-0086, Issue #197). Ctor default OFF
                                                    # keeps the raw-scoring substrate neutral;
                                                    # `make_agent` resolves the shipped ON from
                                                    # PROFILE, like every other switch.
        self.attach_value = attach_value                # the ATTACH DECIDER's emergency lever (ADR-0069 §9,
                                                        # shipped ON): the axes-sum marginal (`_attach_value`)
                                                        # IS the energy-attach decision, scaled into the rung
                                                        # band by `_ATTACH_VALUE_SCALE`. OFF is DEGRADED MODE,
                                                        # not a rollback — the 19 rungs it replaced are deleted,
                                                        # so OFF means attach endorsements go silent and only
                                                        # the surviving structure rungs speak. An incident
                                                        # lever, never a comparison baseline.
        self.copy_top_value = copy_top_value            # Issue #289: Slowking's Seek Inspiration is valued
                                                        # only from a self-verified known top card.
        self.deferred_target_expansion = deferred_target_expansion   # ADR-0121 (Issue #392),
                                                        # armed-OFF: the apply seam returns a
                                                        # `common.board_choice` CHOICE node — the
                                                        # boards a Deferred-Target Option's target can
                                                        # reach — instead of the point transition
                                                        # whose 1-ply delta is a retreat's allowance
                                                        # bit alone. Read by the composer (Issue
                                                        # #385), which is what arms it; nothing on
                                                        # this Pilot consumes it yet, so OFF is
                                                        # byte-identical and ON changes no decision
                                                        # until that consumer exists.
        self.doom_matched_relax = doom_matched_relax    # doom-shadow grill kill-switch (2026-07-23): behind a
                                                        # γ-matched Brief (`_incoming_budget` set) AND no
                                                        # discard-recur fuel, a worst-case `active_doomed` cry
                                                        # stands only if the CHARGED Threat-Clock curve confirms
                                                        # it under `_DOOM_CHARGED` (base_attach=2: manual + one
                                                        # generic supporter-accel — Crispin/Waitress;
                                                        # burst_on_evo=2: Ignition on an Evolution). RELAX-ONLY:
                                                        # it clears phantom doom, never adds one. Unmatched/
                                                        # fueled/OFF = byte-identical worst-case (ADR-0064 §2)
        self.recur_fuel_relax = recur_fuel_relax        # ADR-0076 kill-switch (S2 live, survival-only):
                                                        # refines `_doom_recur_fueled`'s all-or-nothing
                                                        # relax-block into a QUANTIFIED one — instead of
                                                        # always standing down whenever a recur-fueled line
                                                        # is possible, augment its Energy with the actual
                                                        # `discard_recur_fuel` reload and let the CHARGED
                                                        # curve decide. OFF = today's behavior exactly (the
                                                        # boolean block fires); ON only ever narrows when
                                                        # relax is allowed (fail-scared preserved either way)
        self.scaled_threat_rank = scaled_threat_rank    # Issue #213 kill-switch: the threat rank and the
                                                        # forced-promotion read price a body through the
                                                        # Damage Formula against the live board instead of
                                                        # printed `maxDamage`, so a hand-size or
                                                        # combined-bench attacker ranks by what it would
                                                        # really hit for. Retires the flat
                                                        # `_HAND_SIZE_ATTACKER_BOOST` proxy, which covered
                                                        # exactly one card. OFF = the historical
                                                        # printed-only read, byte-for-byte.
        self.gust_target_slots = gust_target_slots      # ADR-0076 kill-switch: generalizes `deny_slot` to
                                                        # a second instrument — held gust-effect Trainer
                                                        # cards (Guzma/Boss's-Orders-class) keep-price
                                                        # against the real per-body `opponent_target_value`
                                                        # instead of riding the flat `deny` disruption tier.
                                                        # OFF = today's `deny`-only routing, byte-identical;
                                                        # ON = gust rows route to `gust_target` INSTEAD of
                                                        # `deny` for that decision (never both)
        self.deny_strip_delta = deny_strip_delta        # ADR-0078 / #199 (S3c) COMPUTE-ONLY switch: adds
                                                        # the per-instrument STRIP delta to
                                                        # `_opponent_target_rows`. #186 built only the
                                                        # REMOVAL delta (turns bought by the body LEAVING),
                                                        # which a Hammer never achieves — it strips one
                                                        # Energy off a body that stays. Nothing reads the
                                                        # new fields yet (#187 is the consumer), so ON
                                                        # changes no decision; it only costs one extra
                                                        # `turns_to_ko_me` per ENERGIZED opponent body.
                                                        # OFF by default so live play pays nothing until
                                                        # #199's gate 1 rules the read admissible
        self.snipe_relevance = snipe_relevance          # ADR-0085 / Issue #188 kill-switch: the
                                                        # **Snipe Relevance** scalar DECIDES the DAMAGE
                                                        # bench-target select in place of
                                                        # `baseline_snipe.py`'s six additive target
                                                        # rungs + the ADR-0051 MatchupPlan steer, which
                                                        # all stand down together while it is armed.
                                                        # Snipe is the SECOND instrument to reach
                                                        # ADR-0062's "no monotone pricing of magnitude
                                                        # alone can separate them" wall (`82756021-57`
                                                        # vs `83667237-107`: identical HP / prize /
                                                        # rider / turns-to-finish, opposite rulings), so
                                                        # it takes Deny Relevance's categorical shape.
        self.deny_relevance = deny_relevance            # ADR-0080 / Issue #199 switch: emits
                                                        # the **Deny Relevance** read (the value that
                                                        # REPLACED deny's damage magnitude — see
                                                        # `common/deny_relevance.py`) on
                                                        # `_opponent_target_rows`, and ARMS all three
                                                        # deny surfaces on it (Issue #187: the keep
                                                        # price, the fire-now rung, the target pick).
                                                        # OFF emits no fields, leaves the ADR-0062
                                                        # magnitude oracle live and is byte-identical
                                                        # to today
        self._phase_prev = None                         # Carried State (ADR-0068): the phase
                                                        # hysteresis memory (Schmitt trigger) — read
                                                        # via `carried()`, never mutated by a
                                                        # hypothetical build
        self.gamble_lines = gamble_lines                # ADR-0039 kill-switch: the Tier-2 Gamble rung —
                                                        # play a Hand Refresh FIRST when the draw's
                                                        # exact-odds EV beats the held (banked) line
        self.value_model = value_model                  # ADR-0042 Automatic Value Model (Tier-5): a loaded
                                                        # ValueModel refines the planner leaf + rides
                                                        # telemetry; None / null model = off (heuristic
                                                        # leaf unchanged), so it default-OFF until an A/B
        self._search_steps = 0                          # per-move Engine-Search step budget counter
        self._locked_line = None                        # the materialized verified line (turn-scoped):
                                                        # {"turn": n, "queue": [entries]} or None
        self._lethal_lost = False                       # this decision lost a locked line to a live
                                                        # mismatch (sparse telemetry key `lethal_lost`)
        self._lethal_refutes = 0                        # per-plan count of engine-refuted lethal
                                                        # candidates (rides in telemetry when > 0;
                                                        # reset at each plan_turn, ADR-0037)
        from common.transients import TransientTracker, TurnBoostTracker
        self._transients = TransientTracker(self._attack_stat)   # ADR-0033: live next-turn grants
                                                        # (Frost Barrier class) inferred from ATTACK
                                                        # logs — obs exposes no effect state
        self._incoming_budget = None                    # ADR-0064: reachable-Incoming energy policy,
                                                        # set per decision in _board (None = worst-case ceiling)
        self._state_model = None                        # ADR-0068: the per-decision two-sided snapshot,
                                                        # built by `_board()`. DECLARED here (POC-T1) rather
                                                        # than sprung into existence by the first build:
                                                        # once it is the SOLE data supplier every consumer
                                                        # must be able to ask "is there a snapshot?" and get
                                                        # an answer, and `getattr(self, ..., None)` at each
                                                        # site is that question spelled as a papered-over
                                                        # AttributeError.
        self._opp_attack_context = None                 # the opponent-as-attacker Damage-Formula context,
                                                        # same lifecycle, declared for the same reason
        self._my_attack_context = None                  # ... and MY direction (see `_my_damage_context`),
        self._my_attack_context_obs = None              # anchored to the obs it was built from
        from common.strategy.combat import CombatMath
        self.combat = CombatMath(stats, functions, transients=self._transients,
                                 effects=self.effects)                            # the KO oracle
                                                        # (ADR-0052): the one closed-form combat home;
                                                        # the Pilot's damage/KO methods delegate to it
        self._turn_boosts = TurnBoostTracker(            # this-turn flat damage-boost plays (Power Pro
            lambda cid: self.stats.get(cid) if (self.stats and cid is not None) else None)
                                                        # class) — OHKO-line model's play half
        self._fetch_cache: dict = {}                    # memo: search card id -> deck ids it can be
                                                        # RELIED ON to fetch (the REACH set, ADR-0073)
        self._deadness_cache: dict = {}                 # memo: search card id -> deck ids it could find
                                                        # AT ALL (the DEADNESS set, ADR-0073) — wider:
                                                        # every deck-zone target class, dig/trigger included
        self._chain_target_cache: dict = {}             # memo: tutor card id -> FULL-scope deck fetch
                                                        # targets (the tutor-chain graph leg, seam C)
        self._item_hold_cache: dict = {}                # PER-DECISION (reset in `_board`), keyed by card
                                                        # id: the free-Item hold price. Initialised here
                                                        # so a hand-built Pilot that scores an option
                                                        # without going through `_board()` still resolves
                                                        # — it then memoises for that Pilot's lifetime,
                                                        # which is the same contract every other
                                                        # per-decision cache gives such a caller.
        self._derived_accel_cache = None                # memo: derived bench-accel body ids (deck-fixed)
        self._discard_fuel_cache = None                 # memo: energy types a discard-source accel attack
                                                        # wants IN the discard (deck-fixed; Aura Jab class)
        self._turn_plan = None                          # ADR-0031 turn-scoped committed plan:
                                                        # (fingerprint, TurnLine|None); re-planned on a reveal
        self._composer_trace = None                     # POC-T4/5: the last composer run's margin +
                                                        # stats, lifted onto the Decision's `composer` key
        self._planning = False                          # reentrancy guard: True while an engine sim re-runs
                                                        # policy, so plan_turn stays closed-form (no nested search)

    def decide(self, obs: dict) -> list[int]:
        """The highest-scoring legal selection (the grader hot path): the deck on the initial
        selection, else option indices (count in [minCount, maxCount], unique, in range)."""
        return self._evaluate(obs).chosen

    def explain(self, obs: dict) -> Decision:
        """Same choice as `decide`, plus the per-option trace (which Hypotheses fired, the
        Plan, the card) — the legibility record the writeup is generated from (ADR-0008)."""
        return self._evaluate(obs)

    def _evaluate(self, obs: dict, *, carried=None) -> Decision:
        """Rank this decision's options. ``carried`` forwards a Carried State snapshot to the board
        build, making the whole evaluation non-mutating in the two memories (ADR-0068 decision 2) —
        what a re-score of the root inside a simulated line needs."""
        select = obs.get("select")
        if select is None:                       # initial deck-submission step
            return Decision(chosen=list(self.deck))
        if not self._planning:                   # ADR-0033: consume the REAL log stream only —
            self._observe_known_top(obs)         # Issue #289: live, self-verifying top-deck belief
            self._transients.observe(obs)        # engine-sim future must never mutate match state
            self._turn_boosts.observe(obs)
        options = select.get("option") or []
        board = self._board(obs, select, carried=carried)
        traces = [self._option_trace(obs, select, board, o, i) for i, o in enumerate(options)]
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
            # The empty-Bench guard applies HERE TOO. It is a soundness FILTER over the whole
            # decision, not a step of the scoring path, and this branch returns before the scoring
            # path reaches it — so without this the planner could end a post-setup turn with an empty
            # Bench while a deploy sat on the menu, which is the exact obligation ADR-0086 decision 7
            # places on the rung ("must ALSO prevent `_finish_turn_last` from ending a post-setup turn
            # with an empty Bench while a deploy was available"). Silent whenever it has nothing to
            # force, so a planned line that already benches, or one at a select with no legal body,
            # is returned untouched and the planner keeps its ordering.
            # Handed the FULL menu, not just `next_step`: the guard reorders within the order it is
            # given, and the planned step is precisely the case where the deploy is NOT in it. When
            # the guard moves a body to the front, that body becomes this decision's whole step and
            # the planner re-plans from the benched board next call.
            #
            # And when it overrides, the line is DROPPED (`planned=None`) rather than reported
            # alongside a pick it does not name. `planned.next_step == chosen` is a well-formedness
            # invariant of the emitted record — `test_planner_engine.py:275`, and the whole
            # `plan_candidates` / `committed` telemetry rests on it — so reporting a committed line we
            # did not follow would make every planner trace unreadable. Overridden IS "no line
            # committed this decision": the guard took the turn's next action, and the planner
            # re-plans from the benched board on the next call. Caught by the CI determinism backstop
            # on repeat 6 of 15, because whether a live drive reaches an empty Bench varies per run.
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
        # Telemetry legibility (ADR-0019): flag when `chosen` did NOT come from argmax(score), so a
        # trace reader doesn't misread "top-score not chosen" as a scoring bug. `reordered` = attack-last
        # resequenced the menu; `grabbed` = the greedy multi-pick chose a set by dynamic gap-scoring.
        reordered = order != by_score
        grabbed = max_count > 1 and select.get("context") in _GRAB_CONTEXTS
        # ADR-0065 SWAP: at a forced discard the keep-value v2 needs-assignment DECIDES — the
        # `picks` cheapest-to-lose cards (`_needs_v2`/`eq2_pick`). It STANDS ALONE (Issue #261 item
        # 2h): seam-D v1 (`discard_keep_value` / `_discard_equation_pick`) and the tuned `_DISCARD`
        # ladder under it are both DELETED, so there is nothing left to fall back to. Every ladder
        # case that was pinned as a corpus ruling is reproduced by v2 unchanged — measured, not
        # assumed (`test_discard_selection.py`, `test_discard_keep_rows.py`). When v2 returns None
        # (nothing priceable) the ordinary scored order takes the pick, which is what happens at any
        # other select with no equation to speak.
        eq_discard = None
        if select.get("context") == _DISCARD and max_count > 0:
            eq_discard = self._discard_needs_pick(obs, select, board, options, max_count)
        if eq_discard:
            chosen = eq_discard
        elif grabbed:                                   # greedy gap-update + take-fewer
            chosen = self._greedy_grab(obs, select, board, traces, options,
                                       select.get("minCount", 0), max_count)
        else:
            chosen = order[:max_count]
            # take-fewer at an OPTIONAL select (minCount 0): DECLINE a pick a Hypothesis actively
            # discourages (score < 0) rather than placing it — the single-pick analog of _greedy_grab's
            # take-fewer, so the Pilot can decline an optional bench placement it's told not to make
            # (ep83661652 f3: don't pre-bench Meowth ex — save Last-Ditch Catch for an in-game bench).
            min_count = select.get("minCount", 0)
            while len(chosen) > min_count and traces[chosen[-1]].score < 0:
                chosen = chosen[:-1]
        chosen = self._never_pre_bench(select, chosen)
        return Decision(chosen=chosen, options=traces, read=board.read, lethal_refuted=refuted,
                        posture=self._posture_record(board),
                        objectives=self._objectives_trace(board), win_prob=self._win_prob(board),
                        game_plan=self._game_plan_record(board),
                        gamble=getattr(self, "_gamble_trace", None),
                        # Emitted on the DEFER path too, and that is the point: the composer ran and
                        # declined (no scorable option, or a coverage-gap winner it refused to commit
                        # on an unknown), so this record is the only place the reason survives. A
                        # telemetry key that appeared only when the composer WON would answer
                        # "did it fire" with "did it agree", which is the column-misreading the lab's
                        # own caveat exists against.
                        composer=getattr(self, "_composer_trace", None),
                        attach_working=self._attach_working(obs, select, board, options),
                        lethal_lost=self._lethal_lost, reordered=reordered, grabbed=grabbed)

    @staticmethod
    def _posture_record(board: Board) -> dict | None:
        """Compact posture summary for Decision Telemetry (ADR-0041): WHAT the Read believed about
        the opponent at this decision + HOW strongly Posture acted, sourced from the Board. None when
        no Scout is wired (Posture structurally off) so the wire key stays sparse. Consumed by the
        blunder inspector (shows the believed archetype) and `/blunder-buster` (ties a correction to
        a matchup). Pure, total, never raises — a byte-cheap belief snapshot, not decision input."""
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
        """The sparse Tier-3 objectives record for this Decision (ADR-0040 trace): the live race
        delta + both cheapest-path turns. None when neither path resolves (early boards) — the
        telemetry line stays lean."""
        if board.my_path_turns is None and board.their_path_turns is None:
            return None
        return {"race": board.race_ahead, "my": board.my_path_turns, "their": board.their_path_turns}

    def _win_prob(self, board: Board) -> float | None:
        """The Automatic Value Model's P(win) on this decision's board (ADR-0042), rounded for the wire;
        None when the model is off/absent (no learned claim to emit). Legibility + calibration only
        — the leaf blend is where it changes a decision."""
        vm = getattr(self, "value_model", None)
        if not vm or not vm.present:
            return None
        try:
            from common.value.features import features_from_board
            return round(vm.predict(features_from_board(board)), 4)
        except Exception:
            return None

    def _game_plan_record(self, board: Board) -> dict | None:
        """Compact Game Plan for Decision Telemetry (ADR-0045): the Match Planner's mode, confidence,
        directed goal, and route size — so the blunder inspector shows the match-scale intent and
        `/blunder-buster` ties a ladder misplay to it. None when no plan was computed (early/empty board).
        Pure, total, never raises — a belief snapshot, not decision input."""
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
                    + self._heal_target_tactical(obs, select, board, option)   # ctx 17 (Issue #409):
                                                                       # the 4th target-select term
                    + self._evolve_target_tactical(obs, select, board, option, ctx)  # ctx 18 (#417 —
                                                                       # Issue #417): the 5th, and
                                                                       # WHERE a searched-out
                                                                       # evolution lands
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
        # No attach fold set and no per-option suppression plumbing: the rungs the attach decider
        # replaced are DELETED (ADR-0069 §7), not shadowed, so nothing on an energy-attach option can
        # double-count with `_attach_value_tactical`.
        score = sum(w for _h, w in fired) + tactical
        return OptionTrace(index=index, score=score, plan=ctx.plan, card_id=ctx.card_id,
                           fired=fired, tactical=tactical,
                           attach_to_needy_line=ctx.attach_target_is_line_member and ctx.attach_target_needs,
                           attach_spend=(-attach_row["evaporation_loss"] * _ATTACH_VALUE_SCALE
                                         if attach_row is not None else 0.0),
                           evolve_working=evolve_row,
                           deploy_working=deploy_row,
                           promote_retreat_working=promote_row)

    # ── the PROMOTE/RETREAT DECIDER (ADR-0100, #141) ───────────────────────────────────────────
    # ONE evaluator, three call sites (§9). Every read routes through the StateModel snapshot
    # (ADR-0068), so a memoized clock cannot shift under a hypothetical build, and the equation
    # itself stays pure over MEASUREMENTS — the Pilot fills `PromoteBody`/`RetreatSide`, exactly
    # ADR-0070's `EvolveBody` pattern.

    def _weight(self, h) -> float:
        """Effective weight, resolved by id (0 disables): the learned override (tuned.json) over
        the deck's authored seed override (Strategy.weight_overrides, ADR-0035) over the authored
        default. ADR-0008 tunables: shared defaults -> per-deck/machine overrides."""
        if h.id in self.overrides:
            return self.overrides[h.id]
        return self.strategy.weight_overrides.get(h.id, h.weight)

    # `_rider_snipe` / `_rider_spread` / `_rider_recoil` were DELETED by POC-T1 (Issue #260) and
    # every caller re-pointed at `self.combat.rider_*`. They were byte-identical copies of the
    # oracle's own accessors — an ADR-0052 consolidation leftover, and the shape
    # `docs/plans/TODO-dead-accessor-cleanup.md` §2 rules on: snipe and spread got away with the
    # duplication because both copies had callers, and recoil is where it became visible, because
    # the Pilot's copy won and `CombatMath.rider_recoil` got nothing. Deleting the oracle's method
    # (the literal reading of the T1 scope line) would have removed the EVIDENCE of the duplication
    # while leaving the duplication; card knowledge belongs on the oracle, so the copies went instead.

    # `_attach_provision` was DELETED by Issue #418. It answered *"how many units"* from
    # `(target_stat, burst)`, which cannot express the COLOUR — half the fact, and the half that
    # decides whether the provision pays the attack it is being credited for. Its whole reading is
    # `CombatMath.provision_codes`, which answers both halves at once and is the single home the four
    # hardcoded copies (3 on an Evolution holding a `discard_eot` card, 1 otherwise) now share.
    # ADR-0069 §5's ruling (the
    # PRINTED provision is a card fact, never falsified by a unit gate) is unchanged and is now
    # recorded on the seam.

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
        """A frozen :class:`~common.state_model.CarriedState` snapshot of the facts that persist
        ACROSS decision points (ADR-0068 decision 2).

        The declared channel, and the whole of it: the phase hysteresis and the Prize-Path stickiness
        today, #149's ``known_top`` later. Everything else the Pilot knows is either an observation
        fact or a recomputable memo, and belongs in neither this channel nor a derivation that
        mutates on read.

        Pass it to any build of a HYPOTHETICAL board (``_board(..., carried=...)`` /
        ``_evaluate(obs, carried=...)``): the carried values are then read from the snapshot and the
        new ones discarded, so a simulated line's phase or path can never leak into the live turn's
        memory. That guarantee used to be a hand-written snapshot/restore at each site that
        remembered to add one."""
        from common.state_model import CarriedState
        return CarriedState.of(phase_prev=getattr(self, "_phase_prev", None),
                               my_path_prev=getattr(self, "_my_path_prev", None),
                               known_top=getattr(self, "_known_top", None))

    def _snapshot(self, obs: dict, *, my_index=None, deck_empty=None,
                  read=None, brief=None, matchup_plan=None, gamma: float = 0.0,
                  favorability: float = 0.5, matchup_coverage: float = 0.0,
                  carried=None) -> StateModel:
        """Build (and stash) the per-decision :class:`StateModel` — **the ONE construction site**.

        `_board()` is the production caller and supplies the Read overlay it has just resolved; every
        other caller (a unit test exercising one instrument, a probe replaying a frame) gets the same
        snapshot with the overlay defaulted off. That the two share a constructor is the point: once
        the model is the SOLE data supplier (ADR-0092), a second build site is a second opinion about
        what a snapshot IS, and the first argument to drift would be the threaded clock policy —
        exactly the gap POC-T1 exists to close.

        Two arguments are read off `self` rather than passed, because they are the Pilot's own and
        have no per-caller reading: `forward_ids` is the POOL-level forward index (the same callable
        `CombatMath.forward_card_ids` defaults to, passed explicitly so a model route and the bypass
        it replaces are equal by construction rather than by coincidence), and `charged` is the Read's
        `_incoming_budget` — None on an unrecognized opponent, which is the worst-case ceiling per
        ADR-0064 Decision 1.

        A `deck_known` argument used to ride here too, carrying the tracker's anchored `{card id:
        copies left in my deck}` because the model's Damage Formula context reads it (POC-T3.5,
        Issue #279) and the model could not derive it. Issue #297 fixed the read it distrusted
        (`MySide.visible_counts`), so the model now derives the pair from the `own_prizes` anchor the
        observation already carries, and the sentinel that kept "derive it" distinguishable from the
        tracker's own "claim nothing" None went with it.
        """
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

    # `_snipe_matchup_tactical` (ADR-0051's MatchupPlan snipe steer) was DELETED by ADR-0085
    # decision 5, which put it in the fold's scope alongside the six target rungs. Armed it was
    # already inert, because the steer now travels as the Brief MULTIPLIER inside
    # `snipe_relevance.target_relevance` — only the SIGN crosses the seam, with `_BRIEF_THREAT_BOOST`
    # supplying the magnitude, so no rate is invented to map a damage-scale MatchupPlan priority into
    # the [0,1] band (ADR-0065's no-fudge rule). Its positive/negative asymmetry (a positive boost
    # stands down on an ADR-0044 redundant / mirage / Tera body; a negative `avoid` always applies)
    # lives in the pure scorer now, where it is unit-testable without a board.

    # `_strongest_threat_rank` was DELETED by ADR-0085's deletion pass. It walked every benched
    # DAMAGE option to find the greatest `_target_threat_rank`, solely so `target_is_top_threat` could
    # be computed as an equality against it — a full extra pass over the bench per decision to answer
    # a question the graded scalar answers by ordering. `_target_threat_rank` / `_body_threat_rank`
    # SURVIVE: the Planner's `ko_key_threat` rung consumes them (see `_body_threat_rank`).

    # The DOOM consumer's charged energy policy (doom-shadow grill, 2026-07-23) — STRICTER than
    # `_incoming_budget`'s `base_attach: 1` because the survival boolean is catastrophe-grade:
    # `base_attach: 2` budgets the manual attach PLUS one generic supporter-accel (Crispin/Waitress
    # are pool-generic `energy_accel` supporters any deck can hold — the 85058574 Munkidori opponent
    # had a Crispin visibly in its discard while the 1-budget read called its {P}● / ×2-weakness
    # Mind Bend unaffordable). `burst_on_evo: 2` is the Ignition {C}{C}{C}-on-an-Evolution allowance
    # (ADR-0064; colourless-only, so it never funds a typed {W}{W}).
    _DOOM_CHARGED = {"base_attach": 2, "burst_on_evo": 2}

    #: The **instantaneous** energy policy for the deny Δ (`_strip_delta_terms`).
    #:
    #: **USER RULING, 2026-07-28 (ADR-0078 Amendment B), settling gate 1's failure:** *"deny shall not
    #: calculate energy re-attached on a following turn. It shall only ever perform a calculation on
    #: opponent's Pokémon with energy during our own turn."* So `base_attach` is **0** — the strip is
    #: priced against the Energy actually on their board at the moment we hold the Hammer, with no
    #: credit for the attach they make next turn.
    #:
    #: This is deliberately NOT the design doc's "slow" policy for this consumer, and the difference
    #: is the whole ruling. At `base_attach: 1` the curve hands the opponent a replacement Energy every
    #: turn, so a single strip is cancelled by construction wherever the body can re-afford its attack
    #: — gate 1 measured that as `m = 0.000` on four of the five frames the corpus rules PLAY. Deny's
    #: question is "what does this strip take away NOW", which is the question ADR-0062's oracle has
    #: always answered (`best_affordable(E) − best_affordable(E−1)`, no re-attach credit).
    #:
    #: `burst_on_evo` stays 0 for the original reason: crediting the opponent a burst inflates what the
    #: strip appears to take away, the fail-fast direction for a consumer that must not over-spend a
    #: scarce Hammer.
    _DENY_CHARGED = {"base_attach": 0, "burst_on_evo": 0}

def _fires(h, ctx: Context) -> bool:
    try:
        return bool(h.when(ctx))
    except Exception:
        return False
