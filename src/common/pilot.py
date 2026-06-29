"""The Pilot: a deck-agnostic Sense -> Plan -> Score -> Act decision engine (ADR-0008).

Tiny public interface (`decide`; `explain` adds the per-decision trace). Scoring merges a
deck-agnostic **General Strategy** (shared
hypotheses in `common/`) with the deck's own Strategy; per-hypothesis weights resolve by id
through machine-written `overrides` (0 disables). Operates on the raw observation dict the
engine passes, so the fast unit suite needs no native lib.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace

from common.strategy import Plan, Strategy

# Engine vocabulary (option/select/area enum mirrors, KO_SCORE, _ENGINE_TAGS, …) is shared with the
# doctrine modules, so it lives in common.strategy.context. The three card-archetype doctrines each
# own their Hypotheses AND their Pilot-side code (a `*Mixin` this Pilot inherits) — see those modules.
from common.strategy.context import *  # noqa: F401,F403  (the engine-vocabulary constants + _fires/Board live there or below)
from common.strategy.doctrines import FetchMixin, GustMixin, ShuffleRefreshMixin

# Tactical-only scalars — used SOLELY by the closed-form combat evaluator below, never by a doctrine.
_EFFICIENCY = 0.1          # per-Energy tiebreak: among equal-outcome attacks prefer the cheaper one;
                           # far below prize granularity (1) so it never overrides prize value
_BENCH_SNIPE = 0.005       # per-point value of an attack's bench-snipe rider, capped below — a sub-prize
_BENCH_SNIPE_CAP = 0.9     # tiebreak so among equal-outcome KO attacks the one that ALSO snipes a benched
                           # target wins (best total board value), without ever overriding a prize (ADR-0022 #14)
_RESISTANCE = 30           # damage Resistance subtracts when the defender resists the attacker's type. The
                           # amount is the card's PRINTED resistance (e.g. Slowking "Fighting -30") — a
                           # per-card fact, NOT in our data export (CardData/CSV are resistance-TYPE only).
                           # In THIS set it is a uniform -30: verified by probing 47 resistant Pokémon
                           # through the simulator (tools/sim/probe_resistance.py) + the printed cards, all
                           # -30. Applied AFTER Weakness (rules.md §5). Revisit if a card ever prints other.


def choose_plan(state: dict, strategy, stats=None) -> Plan:
    """Pick this turn's Plan. SETUP until a win-condition Line's payoff is in play with enough
    energy to attack; then RACE. A Line's `ready.energy` is the threshold; when unset (None) it is
    derived from the engine — the payoff's cheapest attack cost, so a 1-Energy attack counts.
    (STABILIZE / CLOSE arrive with their own signals.)"""
    me = state["players"][state["yourIndex"]]
    board = [p for p in (me.get("active") or []) + (me.get("bench") or []) if p]
    for line in strategy.lines:
        threshold = line.ready.energy
        if threshold is None:                          # derive "online" from the cheapest attack
            threshold = _min_attack_cost(stats, line.payoff)
        if any(p["id"] == line.payoff and len(p.get("energies", [])) >= threshold for p in board):
            return Plan.RACE
    return Plan.SETUP


def _min_attack_cost(stats, payoff: int, default: int = 1) -> int:
    """The payoff's cheapest attack's energy cost, read off the engine CardStat (`default` when
    unknown — never 0, so a Pokémon is never 'online' with no Energy)."""
    stat = stats.get(payoff) if stats else None
    cost = getattr(stat, "minAttackCost", None) if stat else None
    return cost if cost is not None else default


@dataclass
class Board:
    """Per-decision board summary (shared by every option) — the cross-option signals a
    Hypothesis trigger reads (bench size, my/opp Active, opponent bench, energy/turn)."""
    my_bench: int = 0
    my_active_id: int | None = None
    my_active_energy: int = 0
    my_active_hp: int = 0
    opp_active_id: int | None = None
    opp_active_hp: int = 0
    opp_bench: tuple = ()          # ((cardId, hp), …) of the opponent's benched Pokémon
    turn: int = 0
    energy_attached: bool = False  # have I already attached Energy this turn?
    hand_startable: bool = False   # a card in hand can take the Active Spot (opener tag / starter role)
    active_doomed: bool = False    # the opponent can Knock Out my Active next turn (incoming-KO estimate)
    incoming_active_damage: int = 0  # closed-form estimate of the opponent's biggest attack vs my
                                     # Active (weakness-doubled) — the margin behind active_doomed,
                                     # exposed so a +HP tool can test it crosses a survival breakpoint
    active_cheap_attack_kos: bool = False  # my Active's CHEAPEST attack would KO the opponent's Active
                                           # this turn (closed-form) — so a costly burst Energy
                                           # (e.g. Ignition->Nebula) is unnecessary; the cheap attack does it
    gust_best_ko_prizes: int = 0   # best prizes among the opponent's benched Pokémon my Active could KO
                                   # after gusting one to the Active Spot (0 if none) — the whether-to-play
                                   # gate for a gust Supporter (Boss's Orders). ADR-0022.
    active_ko_prizes: int = 0      # prizes from KOing the opponent's CURRENT Active with my cheapest
                                   # attack (0 if I can't) — the baseline a gust must beat (gusting
                                   # removes this Active, so it's only worth the Supporter for a bigger KO)
    my_prizes_remaining: int = 0   # prizes I still need to take (len of my prize pile); 0 when the obs
                                   # doesn't populate it. A gust KO reaching this count WINS (ADR-0022)
    opp_prizes_remaining: int = 0  # prizes the OPPONENT still needs (len of their prize pile); 0 when the
                                   # obs doesn't populate it. A recoil that KOs my Active and hands them
                                   # THIS many prizes simultaneously with my own lethal is a DRAW (ADR-0022 #2)
    reusable_energy_in_hand: bool = False  # a plain (non-discard) Energy is in hand — a reusable
                                           # alternative to a discard-at-end-of-turn Energy
    wincon_in_play: bool = False   # my win-condition (a Line payoff / win_condition role) is already
                                   # on my Active or Bench — so a search needn't fetch another copy
    wincon_in_hand: bool = False   # the win-condition card is already in my hand — so a tutor needn't
                                   # dig for another copy
    top_fetch_priority_id: int | None = None  # at a TO_HAND search, the highest-priority candidate id
                                       # present, by the deck's explicit Strategy.fetch_priority list
                                       # (None off a search / no list / none present) — Tier-3 override
    line_preevo_in_play: bool = False  # a non-payoff member of a Line's path (a pre-evolution) is in
                                       # play — so there's something a rush-evolve tutor can evolve
    support_in_play: bool = False      # an engine/support Pokémon (a draw/accel/search Ability, see
                                       # _ENGINE_TAGS) is on my Active/Bench — the gap gate for
                                       # `fetch-the-support` (with an engine online I needn't tutor one)
    in_play_ids: frozenset = field(default_factory=frozenset)  # card ids of my in-play Pokémon
                                       # (Active + Bench) — a hand copy of one is a redundant duplicate
                                       # (its need already met), the keep-value floor `discard-the-redundant`
    hand_is_dead: bool = False         # no non-refresh card in hand yields any positive-scoring play
                                       # this turn (each virtually scored through the real pipeline) — the
                                       # Shuffle-Refresh fallback gate (ADR-0024): refresh only a dead hand
    deck_holds_a_need: bool = False    # my deck still holds a card I currently LACK (some deck card has
                                       # positive grab-value, `_grab_value_of`) — the gain-exists guard for
                                       # `refresh-when-hand-is-dead` (don't refresh into a deck of dead cards)
    weakest_bench_hp: int | None = None  # least HP among the opponent's benched snipe targets at a
                                         # DAMAGE select — the target closest to a knockout
    strongest_forward_bench: int | None = None  # greatest forward-evolution damage among the opponent's
                                                # benched snipe targets at a DAMAGE select — the most
                                                # dangerous latent evolving threat (Riolu→Mega Lucario
                                                # 270 over Makuhita→Hariyama 210). None off a Damage select
    bench_threat_present: bool = False  # at a DAMAGE select, some benched snipe target already carries
                                        # Energy (an imminent attacker) — so the evolving-threat snipe
                                        # stands down: snipe-the-threat (energized) is the priority
    bench_wincon_ready: bool = False   # a benched win-condition / primary attacker already carries
                                       # enough Energy to attack — a finisher to retreat into
    active_is_wincon: bool = False     # my Active IS the win-condition / primary attacker
    stall_target_exists: bool = False  # the opponent has an energyless, high-retreat benched Pokémon —
                                       # a candidate to strand Active with a defensive stall-gust (ADR-0022)
    opp_has_energy_in_play: bool = False  # the opponent has Energy on any Pokémon (Active or Bench) — a
                                          # target an energy-denial Item (Crushing Hammer) can strip; the
                                          # whether-to-play gate for `play-energy-denial` (no Energy -> it whiffs)
    deck_empty_ids: frozenset = field(default_factory=frozenset)  # MY card ids the deck is PROVABLY
                                          # empty of. Stateless mode: every copy seen OUTSIDE the deck
                                          # (hand + discard + board incl. attached/stacks + a face-up
                                          # prize) reaches the 60-card count. With the deck-tracker
                                          # annotation (`obs['own_prizes']`) it is EXACT (prize-aware:
                                          # also includes cards that are entirely PRIZED). Either way
                                          # sound — never probabilistic. Queried by `deck_definitely_empty_of`.
    deck_known_counts: dict | None = None  # EXACT count of each card still in my deck, once the
                                          # deck-tracker has anchored the prizes (deck = decklist −
                                          # visible − prizes); None until the first search reveal.
                                          # Backs the POSITIVE `deck_definitely_has`.
    opp_active_condition_gift: bool = False  # the opponent's Active carries ANY special condition
                                          # (poison/burn/sleep/paralyze/confuse) — gusting it off to the
                                          # bench would CLEAR it (a free cure). The guard that suppresses
                                          # the stall-gust so we never rescue a condition. ADR-0022 #10
    active_condition_ko_prizes: int = 0   # prizes from the opponent's CURRENT Active dying to poison/burn
                                          # at the upcoming Checkup (0<hp<=10*poison+20*burn), else 0 — a
                                          # free KO I'd get without attacking, so an offensive gust must
                                          # beat THIS too (gusting it off cures it). ADR-0022 #10

    def deck_definitely_empty_of(self, card_id: int) -> bool:
        """True iff `card_id` is PROVABLY absent from my deck — every copy is accounted for outside it
        (hand + discard + board + a revealed prize) against the known 60-card list (see
        `deck_empty_ids`). Certain, never probabilistic: a copy that could still be in the hidden
        prizes leaves this False (unless the deck-tracker has resolved the prizes, when it's exact)."""
        return card_id in self.deck_empty_ids

    def deck_definitely_has(self, card_id: int) -> bool:
        """True iff `card_id` is PROVABLY still in my deck (a search CAN fetch it) — requires the
        deck-tracker's exact deck counts (`deck_known_counts`, available once a search has anchored
        the prizes). False when unknown: positive certainty is never asserted on a guess."""
        return bool(self.deck_known_counts) and self.deck_known_counts.get(card_id, 0) > 0


@dataclass
class Context:
    """What the Score layer knows about one option — the input a Hypothesis trigger reads."""
    plan: Plan
    select_context: int | None
    option_type: int | None
    card_id: int | None
    option_area: int | None = None  # AreaType of the option's target (4=active, 5=bench) — attach targeting
    attach_target_area: int | None = None  # for an attach, the AreaType of the Pokémon receiving the
                                           # Energy (4=active can attack this turn, 5=bench cannot)
    attach_target_roles: list = field(default_factory=list)  # deck Roles of that receiving Pokémon
    attach_target_needs: bool = False  # the receiving Pokémon still needs Energy to attack (has fewer
                                       # than its cheapest attack cost) — gates "attach to the needy"
    attach_target_under_max: bool = False  # the receiving Pokémon carries fewer Energy than its
                                           # HIGHEST-damage attack costs — i.e. it can't yet fire its
                                           # big attack (Mega Starmie at 1 W can Jetting Blow but not
                                           # Nebula Beam CCC). Gates "keep building the active attacker
                                           # toward its payoff attack". Fail-CLOSED (False when unknown).
    card_is_line_preevo: bool = False  # this option's card is a non-payoff member of a Line's path (a
                                       # pre-evolution that builds toward the win-condition)
    card_is_wincon: bool = False       # this option's card IS the win-condition (a Line payoff /
                                       # win_condition / primary_attacker)
    card_is_starter: bool = False      # this option's card is a startable Basic Pokémon (hp > 0, no
                                       # evolvesFrom) — a body that develops an underdeveloped board
                                       # (the `fetch-a-starter` grab rung). Derived off CardStat.
    card_is_support: bool = False      # this option's card is an engine/support Pokémon (hp > 0 with a
                                       # draw/accel/search Ability, see _ENGINE_TAGS) — the
                                       # `fetch-the-support` grab rung. Derived off CardStat + tags.
    card_is_top_fetch_priority: bool = False  # this candidate IS the deck's highest-priority fetch
                                       # target present (== board.top_fetch_priority_id) — the Tier-3
                                       # explicit-list grab override (`fetch-deck-priority`)
    card_is_redundant: bool = False    # this option's card duplicates a Pokémon already in play (its
                                       # need is met) — the lowest keep-value, preferred at a forced
                                       # discard (`discard-the-redundant`)
    fetch_fills_a_need: bool = False   # this option PLAYS a fetch whose reachable deck set still holds a
                                       # card I currently lack (best grab value > 0, scored by the SAME
                                       # grab rungs) — the whether-to-play endorsement (`fetch-when-it-
                                       # fills-a-need`). False off a PLAY / a non-fetch / a need-less fetch
    target_energy: int | None = None  # attack-target snipe signal: Energy on the targeted benched
                                      # Pokémon (None off a Damage/bench-target option)
    target_is_threat: bool = False  # the attack target already carries Energy -> closest to attacking
    target_hp: int | None = None    # HP of the targeted benched Pokémon (None off a Damage option)
    target_is_weakest: bool = False  # this snipe target has the least HP on the opponent's Bench
    target_is_strongest_forward: bool = False  # this snipe target's evolution line is the most
                                               # dangerous on the Bench (its forward damage is the
                                               # greatest, and a real threat) — the priority evolving
                                               # snipe (Riolu→Mega Lucario over Makuhita→Hariyama)
    target_forward_damage: int | None = None  # Evolving Threat signal (ADR-0020): max damage the
                                              # snipe target's evolution line eventually reaches
                                              # (None off a Damage option / no chain / no provider)
    roles: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    stat: object | None = None     # the option card's engine CardStat (hp/weakness/prize value/…)
    board: Board = field(default_factory=Board)   # per-decision board summary (same for all options)
    is_attack: bool = False
    tactical: float = 0.0          # the option's closed-form combat value (>= KO_SCORE on a knockout)
    is_ko: bool = False            # this option is an attack that knocks out the opponent's Active
    search_targets_exhausted: bool = False  # this option PLAYS a deck-search/tutor whose every legal
                                   # fetch target (by its fetch-filter, see doctrine_fetch._FETCH_FILTERS) is
                                   # PROVABLY gone from the deck — so it whiffs. SOUND (built on
                                   # Board.deck_empty_ids); False off a search / unknown filter
    search_redundant_wincon: bool = False  # this option PLAYS a tutor that can fetch ONLY the
                                   # win-condition AND the win-condition is already in hand — so it
                                   # would only dig a redundant copy (e.g. Mega Signal with a Mega in
                                   # hand). False off a search / a tutor that can fetch anything else


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


@dataclass
class Decision:
    """A scored decision: the chosen option indices and the per-option OptionTrace."""
    chosen: list
    options: list = field(default_factory=list)


class Pilot(GustMixin, FetchMixin, ShuffleRefreshMixin):
    """Composed from three doctrine mixins (gust / fetch / shuffle-refresh) — each contributes its closed-form
    Pilot-side methods; the shared Sense→Plan→Score→Act core is defined here. See common/strategy/."""

    def __init__(self, strategy, deck, *, general_strategy=None, overrides=None, stats=None,
                 functions=None, attacks=None, attack_costs=None, recoil=None, bench_snipe=None,
                 search_budget=0):
        self.strategy = strategy
        self.general = general_strategy or Strategy()   # deck-agnostic shared hypotheses (ADR-0008)
        self.overrides = overrides or {}                # machine-written weight overrides, by hyp id
        self.deck = list(deck)
        self.stats = stats
        self.functions = functions
        self.attacks = attacks or {}                    # attackId -> printed damage
        self.attack_costs = attack_costs or {}          # attackId -> Energy count (efficiency tiebreak)
        self.recoil = recoil or {}                      # attackId -> unconditional self-damage (ADR-0022 #2)
        self.bench_snipe = bench_snipe or {}            # attackId -> opp-bench snipe rider (ADR-0022 #14)
        self.search_budget = search_budget
        self._fetch_cache: dict = {}                    # memo: fetch-filter tag -> deck ids it can fetch

    def decide(self, obs: dict) -> list[int]:
        """The highest-scoring legal selection (the grader hot path): the deck on the initial
        selection, else option indices (count in [minCount, maxCount], unique, in range)."""
        return self._evaluate(obs).chosen

    def explain(self, obs: dict) -> Decision:
        """Same choice as `decide`, plus the per-option trace (which Hypotheses fired, the
        Plan, the card) — the legibility record the writeup is generated from (ADR-0008)."""
        return self._evaluate(obs)

    def _evaluate(self, obs: dict) -> Decision:
        select = obs.get("select")
        if select is None:                       # initial deck-submission step
            return Decision(chosen=list(self.deck))
        options = select.get("option") or []
        board = self._board(obs, select)
        traces = [self._option_trace(obs, select, board, o, i) for i, o in enumerate(options)]
        max_count = select.get("maxCount", 0)
        order = sorted(range(len(options)), key=lambda i: traces[i].score, reverse=True)
        order = self._finish_turn_last(options, traces, order, max_count, select.get("context"))
        if max_count > 1 and select.get("context") in _GRAB_CONTEXTS:   # greedy gap-update + take-fewer
            chosen = self._greedy_grab(obs, select, board, traces, options,
                                       select.get("minCount", 0), max_count)
        else:
            chosen = order[:max_count]
        return Decision(chosen=chosen, options=traces)

    def _finish_turn_last(self, options: list, traces: list, order: list, max_count: int,
                          select_context: int | None) -> list:
        """Sequence the turn's commitments LAST. The engine re-presents the open turn menu after each
        non-ending action, so the whole turn still happens — which means you should take the most
        informative, reversible actions first and the irreversible ones last:

          tier 0  informative development — draw / search, fill the Bench, evolve a benched Pokémon,
                  play a Pokémon. Free, and reveals a better target before you commit.
          tier 1  irreversible per-turn COMMITMENTS — the Energy attach, and a discard-COST search
                  (`cost_discard`, e.g. Ultra Ball: pays 2 cards from hand). Do the free digs first,
                  THEN spend the irreversible thing — a free tutor may find what it would, and you
                  pick the discards knowing more.
          tier 2  the turn-ENDING attack, plus Retreat / End / non-beneficial options.

        An option is sequenced early only when a Hypothesis endorses it (score > 0). A knockout is
        never forfeited: an Evolve of the Active drops to tier 2 when a KO is on the menu, and the KO
        attack outscores everything else in tier 2. Stable within a tier (keeps the score order).
        Only at a single-pick MAIN menu; every other context (snipe, search, mulligan) is untouched."""
        if max_count != 1 or len(order) < 2 or select_context != _MAIN:
            return order
        ko_available = any(options[i].get("type") == _ATTACK and traces[i].tactical >= KO_SCORE
                           for i in order)

        def _cost_discard(i: int) -> bool:
            cid = traces[i].card_id
            return bool(self.functions) and cid is not None and "cost_discard" in self.functions.tags(cid)

        def _tier(i: int) -> int:
            o = options[i]
            t = o.get("type")
            if t == _ATTACH and traces[i].tactical >= KO_SCORE:      # attach that UNLOCKS a KO this turn
                return 0                                             # take the win — don't dig first
            if t in (_ATTACK, _END, _RETREAT):                       # turn-ender / swaps the Active
                return 2
            if t == _EVOLVE and o.get("inPlayArea") == _ACTIVE and ko_available:
                return 2                                             # would forfeit an available KO
            if traces[i].score <= 0:                                 # only an endorsed action sequences early
                return 2
            if t == _ATTACH or (t == _PLAY and _cost_discard(i)):    # irreversible commitment: after free dev
                return 1
            return 0

        if any(_tier(i) < 2 for i in order):                         # legibility: mark the held-back attacks
            for i in order:
                if options[i].get("type") == _ATTACK:
                    traces[i].deferred = True
        return sorted(order, key=_tier)                             # stable -> within a tier, score order

    def _option_trace(self, obs: dict, select: dict, board: Board, option: dict,
                      index: int) -> OptionTrace:
        tactical = (self._tactical(obs, board, option)
                    + self._gust_tactical(obs, select, board, option)
                    + self._gust_target_tactical(obs, select, board, option)
                    + self._gust_stall_target_tactical(obs, select, board, option)
                    + self._attach_lethal_tactical(obs, select, board, option))
        ctx = self._context(obs, select, board, option, tactical)
        hyps = (*self.general.hypotheses, *self.strategy.hypotheses)
        fired = [(h, self._weight(h)) for h in hyps if _fires(h, ctx)]
        score = sum(w for _, w in fired) + tactical
        return OptionTrace(index=index, score=score, plan=ctx.plan, card_id=ctx.card_id,
                           fired=fired, tactical=tactical)

    def _weight(self, h) -> float:
        """Effective weight: a machine-written override by id, else the authored default
        (0 disables). ADR-0008 tunables: shared defaults -> per-deck/machine overrides."""
        return self.overrides.get(h.id, h.weight)

    def _tactical(self, obs: dict, board: Board, option: dict) -> float:
        """Closed-form combat value (Tier-0): printed damage (x2 on Weakness) vs the opponent
        Active's HP. A knockout dominates; otherwise the chip is worth its damage. Among equal-outcome
        KO attacks, a bench-snipe rider on a worthwhile target adds a sub-prize bonus (#14), and a
        game-winning KO whose forced recoil is a SIMULTANEOUS double-KO is a draw, not a win (#2)."""
        if option.get("type") != _ATTACK:
            return 0
        attack_id = option.get("attackId")
        dmg = self.attacks.get(attack_id, 0)
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        dmg = self._weakness_adjusted(obs, opp, dmg)
        eff = _EFFICIENCY * self.attack_costs.get(attack_id, 0)   # cheaper of equal outcomes wins
        if hp and dmg >= hp:
            if self._is_simultaneous_draw(board, attack_id, self._prize_value(opp)):
                return dmg - eff                            # a simultaneous double-KO is a DRAW, not a win
            return (KO_SCORE + self._prize_value(opp) - eff  # among KOs, prefer higher-prize then cheaper
                    + self._bench_snipe_bonus(board, attack_id))  # then the one that also snipes a bench
        return dmg - eff

    def _bench_snipe_bonus(self, board: Board, attack_id) -> float:
        """Sub-prize tiebreak (ADR-0022 #14): an attack that ALSO snipes one of the opponent's Benched
        Pokémon is worth a little extra board value — so among equal-outcome KO attacks the agent prefers
        the one with a useful rider (e.g. Jetting Blow 120 + 50 bench snipe over a 210 overkill). Scaled by
        the rider amount, capped below a prize; 0 when the attack has no clean rider or there's no benched
        target to hit."""
        rider = self.bench_snipe.get(attack_id, 0)
        if rider <= 0 or not board.opp_bench:
            return 0
        return min(_BENCH_SNIPE_CAP, _BENCH_SNIPE * rider)

    def _is_simultaneous_draw(self, board: Board, attack_id, opp_active_prize: int) -> bool:
        """True iff a game-winning KO with this attack is actually a DRAW (ADR-0022 #2): its UNCONDITIONAL
        recoil also Knocks Out my own Active and hands the opponent their LAST prize at the same Checkup as
        my own lethal — a simultaneous win, which the competition rules score as a draw (not a win, and not
        a loss). Requires both prize counts in the obs; conservative (only fires on a forced recoil that
        clears my Active's HP). Half (a) only — suppress the false win; valuing a forced draw above a loss
        is a noted refinement."""
        mp, op = board.my_prizes_remaining, board.opp_prizes_remaining
        if mp <= 0 or op <= 0:
            return False
        if opp_active_prize < mp:                            # this KO doesn't take my last prize -> not lethal
            return False
        recoil = self.recoil.get(attack_id, 0)
        if not board.my_active_hp or recoil < board.my_active_hp:   # recoil doesn't self-KO my Active
            return False
        my_prize = self._prize_value({"id": board.my_active_id})
        return my_prize >= op                                # my self-KO gives them their last prize too

    # The Gust doctrine's whether-to-play lethal (`_gust_tactical`), the SWITCH target-select, and the
    # gust Board signals live in common.strategy.doctrines.doctrine_gust (GustMixin). `_attach_lethal_tactical`
    # below is the general lethal-ATTACH lookahead (not gust) — it stays in the core Tactical layer.
    def _attach_lethal_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for an ATTACH that UNLOCKS a knockout this turn — attaching this Energy
        to my Active win-condition lets its best now-affordable attack KO the opponent's Active (e.g.
        Ignition → CCC → Nebula Beam 210 vs a 200-HP Active = win). Closed-form lethal lookahead the
        single-action tactical can't see: it models the post-attach Energy (a Basic provides 1; a
        discard-burst Energy — `discard_eot`, i.e. Ignition — provides CCC=3 on an Evolution, per the
        card text) and asks whether an affordable attack reaches the defender's HP (weakness-doubled).

        Fires only when the attach is NECESSARY (the Active can't ALREADY KO — else just attack, don't
        spend the attach) so it never rewards a needless attachment. Lives in the Tactical layer like
        the gust lethal, not as a tunable weight; `_finish_turn_last` then sequences a lethal attach
        first (take the win before digging). 0 otherwise."""
        if option.get("type") != _ATTACH or option.get("inPlayArea") != _ACTIVE:
            return 0
        opp = self._opp_active(obs)
        opp_hp = (opp or {}).get("hp", 0)
        active_stat = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        if not (active_stat and opp and opp_hp):
            return 0
        eid = self._option_card_id(obs, select, option)
        etags = self.functions.tags(eid) if (self.functions and eid is not None) else []
        is_evo = bool(getattr(active_stat, "evolvesFrom", None))   # Mega Starmie evolvesFrom Staryu
        provided = 3 if ("discard_eot" in etags and is_evo) else 1   # Ignition: CCC on an Evolution

        def best_affordable(energy: int) -> float:
            best = max((self.attacks.get(aid, 0) for aid in (active_stat.attacks or ())
                        if self.attack_costs.get(aid, 99) <= energy), default=0)
            return self._weakness_adjusted(obs, opp, best)

        cur = board.my_active_energy
        if best_affordable(cur) >= opp_hp:                  # already lethal — no attach needed
            return 0
        if best_affordable(cur + provided) >= opp_hp:
            return KO_SCORE + self._prize_value(opp)
        return 0

    def _prize_value(self, poke: dict | None) -> int:
        """Prizes a knockout yields — Mega ex 3, ex 2, else 1 (read off the engine CardStat)."""
        stat = self.stats.get((poke or {}).get("id")) if self.stats else None
        if stat and stat.megaEx:
            return 3
        if stat and stat.ex:
            return 2
        return 1

    def _wr_adjusted(self, attacker_stat, defender_stat, dmg: float) -> float:
        """The ONE Weakness/Resistance helper: adjust `dmg` for the DEFENDER's Weakness (x2, S&V) then
        Resistance (flat -30) vs the ATTACKER's type — in that order (rules.md §5). Direction-agnostic
        (attacker/defender are passed explicitly), so EVERY closed-form damage estimate — my attacks AND
        incoming damage — factors both modifiers identically. Closed-form Tier-0; Tier-1 Search resolves
        the exact figure. ADR-0022."""
        if not (dmg and attacker_stat and defender_stat and attacker_stat.energyType is not None):
            return dmg
        if defender_stat.weakness is not None and defender_stat.weakness == attacker_stat.energyType:
            dmg *= 2
        if defender_stat.resistance is not None and defender_stat.resistance == attacker_stat.energyType:
            dmg = max(0, dmg - _RESISTANCE)
        return dmg

    def _weakness_adjusted(self, obs: dict, opp: dict | None, dmg: float) -> float:
        """My Active's attack damage on the opponent's Active, Weakness/Resistance-adjusted — the
        obs-resolving convenience over `_wr_adjusted` (my Active = attacker, opp = defender)."""
        if not (self.stats and opp):
            return dmg
        return self._wr_adjusted(self.stats.get(self._my_active_id(obs)),
                                 self.stats.get(opp.get("id")), dmg)

    def _my_active_id(self, obs: dict) -> int | None:
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        if not (0 <= yi < len(players)) or players[yi] is None:
            return None
        actives = players[yi].get("active") or []
        return actives[0].get("id") if actives and actives[0] else None

    def _opp_active(self, obs: dict) -> dict | None:
        state = obs.get("current") or {}
        players = state.get("players") or []
        oi = 1 - state.get("yourIndex", 0)
        if not (0 <= oi < len(players)) or players[oi] is None:
            return None
        actives = players[oi].get("active") or []
        return actives[0] if actives else None

    def _context(self, obs: dict, select: dict, board: Board, option: dict,
                 tactical: float = 0.0) -> Context:
        state = obs.get("current") or {}
        plan = choose_plan(state, self.strategy, self.stats) if state.get("players") else Plan.SETUP
        cid = self._option_card_id(obs, select, option)
        roles = self.strategy.roles.get(cid, []) if cid is not None else []
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        card_is_line_preevo = cid is not None and cid in self._line_preevo_set()
        card_is_wincon = cid is not None and cid in self._wincon_set()
        card_is_starter = bool(stat and stat.hp > 0 and not stat.evolvesFrom)
        card_is_support = bool(stat and stat.hp > 0 and (_ENGINE_TAGS & set(tags)))
        card_is_top_fetch_priority = cid is not None and cid == board.top_fetch_priority_id
        card_is_redundant = cid is not None and cid in board.in_play_ids
        fetch_fills_a_need = (option.get("type") == _PLAY
                              and self._fetch_fills_a_need(board, tags, plan))
        is_attack = option.get("type") == _ATTACK
        target_energy = self._target_energy(obs, select, option)
        target_hp = self._target_hp(obs, select, option)
        target_is_weakest = (target_hp is not None and board.weakest_bench_hp is not None
                             and target_hp == board.weakest_bench_hp)
        target_forward_damage = self._target_forward_damage(obs, select, option)
        target_is_strongest_forward = (
            target_forward_damage is not None and board.strongest_forward_bench is not None
            and target_forward_damage == board.strongest_forward_bench
            and target_forward_damage >= _EVOLVING_THREAT_DMG)
        at_target = self._attach_target(obs, option)   # the Pokémon an attach option puts Energy on
        at_roles = self.strategy.roles.get(at_target.get("id"), []) if at_target else []
        search_exhausted, redundant_wincon = self._search_signals(option, tags, board)
        return Context(plan=plan, select_context=select.get("context"),
                       option_type=option.get("type"), card_id=cid, option_area=option.get("area"),
                       attach_target_area=option.get("inPlayArea"), attach_target_roles=at_roles,
                       attach_target_needs=self._attach_target_needs(at_target),
                       attach_target_under_max=self._attach_target_under_max(at_target),
                       card_is_line_preevo=card_is_line_preevo, card_is_wincon=card_is_wincon,
                       card_is_starter=card_is_starter, card_is_support=card_is_support,
                       card_is_top_fetch_priority=card_is_top_fetch_priority,
                       card_is_redundant=card_is_redundant, fetch_fills_a_need=fetch_fills_a_need,
                       target_energy=target_energy, target_is_threat=bool(target_energy),
                       target_hp=target_hp, target_is_weakest=target_is_weakest,
                       target_is_strongest_forward=target_is_strongest_forward,
                       target_forward_damage=target_forward_damage,
                       roles=roles, tags=tags, stat=stat, board=board, is_attack=is_attack,
                       tactical=tactical, is_ko=is_attack and tactical >= KO_SCORE,
                       search_targets_exhausted=search_exhausted,
                       search_redundant_wincon=redundant_wincon)

    # The Fetch doctrine's comparator/oracle (`_grab_value_of` = `fetch_value`), the deck-knowledge
    # whiff/redundant signals (`_search_signals`/`_search_deck_set`), the whether-to-play lookahead
    # (`_fetch_fills_a_need`), and the greedy multi-pick (`_greedy_grab`/`_virtual_grab_board` +
    # `_top_fetch_priority_id`/`_is_support_id`/`_support_in_play`) live in
    # common.strategy.doctrines.doctrine_fetch (FetchMixin).
    def _attach_target(self, obs: dict, option: dict) -> dict | None:
        """The Pokémon an attach option puts Energy on — encoded as `inPlayArea`/`inPlayIndex`
        (distinct from `area`/`index`, which point at the Energy card in hand). None when absent."""
        area, index = option.get("inPlayArea"), option.get("inPlayIndex")
        if area is None or index is None:
            return None
        state = obs.get("current") or {}
        players = state.get("players") or []
        pi = option.get("playerIndex", state.get("yourIndex", 0))
        if not (0 <= pi < len(players)) or players[pi] is None:
            return None
        cards = players[pi].get(_ZONE.get(area))
        if not cards or not (0 <= index < len(cards)) or cards[index] is None:
            return None
        return cards[index]

    def _attach_target_needs(self, target: dict | None) -> bool:
        """True if the Pokémon an attach option targets still needs Energy to attack — it carries
        fewer Energy than its cheapest attack cost. Lets `power-up-attacker` fire only on a Pokémon
        that benefits from the attachment, so the agent spreads Energy to the bare bench attacker
        instead of piling a needless surplus on an already-online one (the over-attach blunders).

        Fail-open: when the receiving Pokémon (or its attack cost) can't be resolved, assume it
        needs Energy — only SUPPRESS the attachment when we can positively confirm the target is
        already online, so a missing-target option keeps the default attach-every-turn behavior."""
        if not target:
            return True
        have = len((target.get("energies") or []))
        return have < _min_attack_cost(self.stats, target.get("id"))

    def _attach_target_under_max(self, target: dict | None) -> bool:
        """True if the Pokémon an attach option targets carries fewer Energy than its HIGHEST-damage
        attack costs — it can still build toward its big attack (Mega Starmie at 1 W can Jetting Blow
        but not yet Nebula Beam CCC). The mirror of `_attach_target_needs` against `maxDamageCost`,
        gating `build-active-wincon` (keep loading the active attacker toward its payoff attack).

        Fail-CLOSED: returns False when the target, its CardStat, or its max-damage cost is unknown —
        over-firing would pile a needless surplus, so only fire when we can positively confirm the
        target is still short of its biggest attack."""
        if not target:
            return False
        stat = self.stats.get(target.get("id")) if self.stats else None
        cost = getattr(stat, "maxDamageCost", None) if stat else None
        if cost is None:
            return False
        return len((target.get("energies") or [])) < cost

    def _target_energy(self, obs: dict, select: dict, option: dict) -> int | None:
        """Energy attached to the Pokémon an attack-target option points at — the snipe 'threat'
        signal: a benched Pokémon already carrying Energy is closest to attacking. Defined only for
        bench attack-target options (SelectContext DAMAGE, OptionType CARD, AreaType BENCH); None
        otherwise so non-target options carry no signal (cf. ``_option_card_id`` resolution)."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        poke = self._option_pokemon(obs, select, option)
        return len(poke.get("energies") or []) if poke else None

    def _target_hp(self, obs: dict, select: dict, option: dict) -> int | None:
        """Remaining HP of the benched Pokémon an attack-target option points at — the snipe
        'weakest' signal (lowest HP = closest to a knockout). Defined only for bench attack-target
        options (DAMAGE / CARD / BENCH); None otherwise (cf. ``_target_energy``)."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        poke = self._option_pokemon(obs, select, option)
        return (poke or {}).get("hp") if poke else None

    def _target_forward_damage(self, obs: dict, select: dict, option: dict) -> int | None:
        """Max damage the benched snipe target's evolution line eventually reaches — the Evolving
        Threat signal (ADR-0020): a fragile pre-evolution worth sniping before it comes online.
        Defined only for bench attack-target options (DAMAGE / CARD / BENCH).

        FAIL-CLOSED by construction (``_context`` is not exception-wrapped): returns None whenever
        the provider, the method, the target Pokémon, its card id, or a forward chain is missing —
        so a gap leaves the signal silent rather than crashing the decision."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        fwd = getattr(self.stats, "forward_max_damage", None)   # None if no/old provider
        if fwd is None:
            return None
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        return (fwd(cid) or None) if cid is not None else None

    def _board(self, obs: dict, select: dict | None = None) -> Board:
        """Summarise the shared board once per decision (see Board)."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        ma = next((p for p in (me.get("active") or []) if p), None)
        oa = next((p for p in (opp.get("active") or []) if p), None)
        prizes = obs.get("own_prizes")             # exact prize multiset from the deck-tracker, or None
        deck_empty = self._deck_empty_ids(me, prizes)
        deck_known = self._deck_known_counts(me, prizes)
        board = Board(
            my_bench=sum(1 for b in (me.get("bench") or []) if b),
            my_active_id=(ma or {}).get("id"),
            my_active_energy=len((ma or {}).get("energies") or []),
            my_active_hp=(ma or {}).get("hp", 0),
            opp_active_id=(oa or {}).get("id"),
            opp_active_hp=(oa or {}).get("hp", 0),
            opp_bench=tuple((b.get("id"), b.get("hp", 0)) for b in (opp.get("bench") or []) if b),
            turn=state.get("turn", 0),
            energy_attached=bool(state.get("energyAttached")),
            hand_startable=self._hand_startable(me.get("hand") or []),
            active_doomed=self._active_doomed(ma, oa),
            incoming_active_damage=self._incoming_active_damage(ma, oa),
            active_cheap_attack_kos=self._active_cheap_attack_kos(ma, oa),
            gust_best_ko_prizes=self._gust_best_ko_prizes(ma, opp),
            active_ko_prizes=self._active_ko_prizes(ma, oa),
            my_prizes_remaining=len(me.get("prize") or []),
            opp_prizes_remaining=len(opp.get("prize") or []),
            reusable_energy_in_hand=self._has_reusable_energy(me.get("hand") or []),
            wincon_in_play=self._wincon_in_play(me),
            wincon_in_hand=self._wincon_in_hand(me),
            line_preevo_in_play=self._line_preevo_in_play(me),
            support_in_play=self._support_in_play(me),
            in_play_ids=frozenset(p.get("id") for p in ((me.get("active") or []) + (me.get("bench") or []))
                                  if p and p.get("id") is not None),
            top_fetch_priority_id=self._top_fetch_priority_id(select),
            weakest_bench_hp=self._weakest_snipe_hp(obs, select),
            strongest_forward_bench=self._strongest_forward_snipe(obs, select),
            bench_threat_present=self._bench_threat_present(obs, select),
            bench_wincon_ready=self._bench_wincon_ready(me),
            active_is_wincon=bool(ma) and ma.get("id") in self._wincon_set(),
            stall_target_exists=self._stall_target_exists(opp),
            opp_has_energy_in_play=self._opp_has_energy_in_play(opp),
            deck_empty_ids=deck_empty,
            deck_known_counts=deck_known,
            opp_active_condition_gift=self._opp_active_condition_gift(opp),
            active_condition_ko_prizes=self._active_condition_ko_prizes(opp, oa),
        )
        # Shuffle-Refresh fallback signals (ADR-0024) — computed off the base board, so the hand-card
        # play-scan can read the rest of the board. Only `refresh-when-hand-is-dead` reads them, and it
        # fires only on a `shuffle_hand` option, so skip the (whole-menu) scan unless a refresh is in
        # hand — the common case pays nothing. plan gates the deck's grab-value.
        if not self._has_shuffle_refresh(me):
            return board
        plan = choose_plan(state, self.strategy, self.stats) if state.get("players") else Plan.SETUP
        return replace(board,
                       deck_holds_a_need=self._deck_holds_a_need(board, plan),
                       hand_is_dead=self._hand_is_dead(obs, select, board))

    # The Shuffle-Refresh doctrine's signals (`_has_shuffle_refresh`, `_deck_holds_a_need`,
    # `_hand_is_dead`) live in common.strategy.doctrines.doctrine_shuffle_refresh (ShuffleRefreshMixin);
    # `_board` calls them.

    def _wincon_set(self) -> set:
        """Card ids that ARE the win-condition — a Strategy Line payoff or a card carrying the
        `win_condition` / `primary_attacker` Role."""
        wincon = {line.payoff for line in self.strategy.lines}
        wincon |= {cid for cid, r in self.strategy.roles.items()
                   if {"win_condition", "primary_attacker"} & set(r)}
        return wincon

    def _wincon_in_hand(self, me: dict) -> bool:
        """True if the win-condition card is already in my hand — a tutor needn't dig for another."""
        wincon = self._wincon_set()
        return bool(wincon) and any(c and c.get("id") in wincon for c in (me.get("hand") or []))

    def _line_preevo_set(self) -> set:
        """Card ids that are a non-payoff member of a Line's path — a pre-evolution that builds
        toward the win-condition payoff (e.g. Staryu on the Staryu → Mega Starmie line)."""
        return {cid for line in self.strategy.lines for cid in line.path if cid != line.payoff}

    def _line_preevo_in_play(self, me: dict) -> bool:
        """True if a non-payoff member of any Line's path (a pre-evolution) is on my Active/Bench —
        so a rush-evolve tutor has something to evolve toward the payoff."""
        preevos = self._line_preevo_set()
        if not preevos:
            return False
        board = (me.get("active") or []) + (me.get("bench") or [])
        return any(p and p.get("id") in preevos for p in board)

    # (Fetch doctrine greedy multi-pick + its gap helpers are in doctrine_fetch.FetchMixin, above.)
    def _bench_wincon_ready(self, me: dict) -> bool:
        """True if a benched win-condition / primary attacker already carries enough Energy to attack
        (>= its cheapest attack cost) — a powered finisher worth retreating into."""
        wincon = self._wincon_set()
        if not wincon:
            return False
        return any(p and p.get("id") in wincon
                   and len(p.get("energies") or []) >= _min_attack_cost(self.stats, p.get("id"))
                   for p in (me.get("bench") or []))

    def _weakest_snipe_hp(self, obs: dict, select: dict | None) -> int | None:
        """Least HP among the benched Pokémon a DAMAGE select can snipe — the target closest to a
        knockout (a prize). None off a Damage select. Resolves each option's target the same way
        the snipe Hypotheses do, so the owner/zone indexing matches `target_energy`."""
        if not select or select.get("context") != _DAMAGE:
            return None
        hps = []
        for o in (select.get("option") or []):
            if o.get("type") == _CARD and o.get("area") == _BENCH:
                poke = self._option_pokemon(obs, select, o)
                hp = (poke or {}).get("hp") or 0
                if hp:
                    hps.append(hp)
        return min(hps) if hps else None

    def _strongest_forward_snipe(self, obs: dict, select: dict | None) -> int | None:
        """Greatest forward-evolution damage among the benched Pokémon a DAMAGE select can snipe — the
        most dangerous latent evolving threat (e.g. Riolu→Mega Lucario ex 270 over Makuhita→Hariyama
        210). None off a Damage select or when no provider/forward chain. Resolves each target the
        same way the snipe Hypotheses do, so the indexing matches `target_forward_damage`."""
        if not select or select.get("context") != _DAMAGE:
            return None
        best = None
        for o in (select.get("option") or []):
            if o.get("type") == _CARD and o.get("area") == _BENCH:
                fwd = self._target_forward_damage(obs, select, o)
                if fwd is not None and (best is None or fwd > best):
                    best = fwd
        return best

    def _bench_threat_present(self, obs: dict, select: dict | None) -> bool:
        """True if any benched Pokémon a DAMAGE select can snipe already carries Energy — an imminent
        attacker. When present, the evolving-threat snipe stands down (snipe-the-threat takes the
        energized body first; a not-yet-evolved threat is the lower priority). False off a Damage select."""
        if not select or select.get("context") != _DAMAGE:
            return False
        for o in (select.get("option") or []):
            if o.get("type") == _CARD and o.get("area") == _BENCH:
                if self._target_energy(obs, select, o):
                    return True
        return False

    def _wincon_in_play(self, me: dict) -> bool:
        """True if my win-condition is already in play — a Strategy Line payoff or a card carrying the
        `win_condition` / `primary_attacker` Role sitting on my Active or Bench. Lets a 'fetch the
        win-condition' Hypothesis stand down once the payoff is on the board (don't pull a dead copy)."""
        wincon = {line.payoff for line in self.strategy.lines}
        wincon |= {cid for cid, r in self.strategy.roles.items()
                   if {"win_condition", "primary_attacker"} & set(r)}
        if not wincon:
            return False
        board = (me.get("active") or []) + (me.get("bench") or [])
        return any(p and p.get("id") in wincon for p in board)

    def _has_reusable_energy(self, hand: list) -> bool:
        """True if a **reusable** (non-discard) Energy is in hand — a *typed* Energy card (hp 0 with a
        real `energyType`) that is not tagged `discard_eot`. Used to prefer a Basic over a
        discard-at-end-of-turn Energy when both are available (deck-agnostic). NB the engine reports
        `energyType == 0` for Trainers *and* colourless special energies (e.g. Ignition), so a typed
        basic Energy is `energyType not in (None, 0)` — that excludes Trainers and Ignition."""
        for c in hand:
            cid = c.get("id") if c else None
            if cid is None:
                continue
            stat = self.stats.get(cid) if self.stats else None
            tags = self.functions.tags(cid) if self.functions else []
            if stat and stat.hp == 0 and stat.energyType not in (None, 0) and "discard_eot" not in tags:
                return True
        return False

    def _incoming_active_damage(self, ma: dict | None, oa: dict | None) -> int:
        """Closed-form estimate of the damage the opponent's Active would deal to my Active next turn
        — its biggest attack, doubled when my Active is Weak to the attacker's type. 0 when unknown.
        The magnitude behind `_active_doomed`; exposed on the Board so a +HP tool (Hero's Cape) can
        test whether it crosses a survival breakpoint."""
        if not (self.stats and ma and oa):
            return 0
        opp_stat = self.stats.get(oa.get("id"))
        if not opp_stat:
            return 0
        # opponent attacks ME: opp Active = attacker, my Active = defender (Weakness AND Resistance).
        return int(self._wr_adjusted(opp_stat, self.stats.get(ma.get("id")), opp_stat.maxDamage or 0))

    def _active_doomed(self, ma: dict | None, oa: dict | None) -> bool:
        """True if the opponent's Active can Knock Out my Active next turn — its biggest attack
        (doubled when my Active is Weak to the attacker's type) >= my Active's remaining HP. A
        closed-form threat estimate off engine stats (attack-affordability refinement is future)."""
        my_hp = (ma or {}).get("hp", 0)
        return bool(my_hp) and self._incoming_active_damage(ma, oa) >= my_hp

    def _can_ko(self, my_stat, defender: dict | None) -> bool:
        """My Active's CHEAPEST attack would Knock Out `defender` this turn — its cheapest-cost attack
        damage, doubled when the defender is Weak to my Active's type, >= the defender's remaining HP.
        The shared closed-form KO oracle (ADR-0022) behind both the current-Active KO checks and the
        gust whether-to-play signal. Fail-closed when stats / HP are missing."""
        hp = (defender or {}).get("hp", 0)
        if not (my_stat and hp):
            return False
        d_stat = self.stats.get(defender.get("id")) if self.stats else None
        dmg = self._wr_adjusted(my_stat, d_stat, my_stat.minCostDamage or 0)
        return dmg >= hp

    def _active_cheap_attack_kos(self, ma: dict | None, oa: dict | None) -> bool:
        """True if my Active's cheapest attack KOs the opponent's CURRENT Active this turn — so a costly
        burst Energy (e.g. Ignition -> Nebula Beam) is unnecessary. The mirror of `_active_doomed`
        (me attacking them, cheapest attack), via the shared `_can_ko` oracle."""
        if not (self.stats and ma and oa):
            return False
        return self._can_ko(self.stats.get(ma.get("id")), oa)

    # (The gust Board-signal builders — `_active_ko_prizes`, `_opp_active_condition_gift`,
    # `_active_condition_ko_prizes`, `_gust_best_ko_prizes`, `_stall_target_exists` — are in
    # doctrine_gust.GustMixin; `_board` calls them as `self.…`.)
    def _opp_has_energy_in_play(self, opp: dict | None) -> bool:
        """True if any of the opponent's Pokémon (Active or Bench) carries Energy — a target an
        energy-denial Item (Function Tag `energy_denial`, e.g. Crushing Hammer) can strip. The
        whether-to-play gate for `play-energy-denial`: with no Energy in play the coin-flip denial
        whiffs, so hold the Item. Closed-form off the board snapshot, no Search."""
        if not opp:
            return False
        board = (opp.get("active") or []) + (opp.get("bench") or [])
        return any(p and (p.get("energies") or []) for p in board)

    def _deck_empty_ids(self, me: dict, prizes: dict | None = None) -> frozenset:
        """The card ids my deck is PROVABLY empty of. SOUND in both modes, never probabilistic.

        Stateless (``prizes`` None): every copy of the id is accounted for OUTSIDE the deck (hand,
        discard, board, a face-up prize), reaching the known 60-card count — so none can remain. The
        deck and FACE-DOWN prizes are the only unseen zones, so a count that falls short leaves the
        id out (it could be prized). Exact (``prizes`` given by the deck-tracker): the prizes are
        resolved, so ``deck = decklist − visible − prizes`` and the id is empty when that is 0 —
        which ALSO catches cards that are entirely prized. Empty when no deck list is configured."""
        if not self.deck:
            return frozenset()
        deck_counts = Counter(self.deck)
        seen = self._visible_card_counts(me)
        if prizes is not None:
            return frozenset(cid for cid, n in deck_counts.items()
                             if n - seen.get(cid, 0) - prizes.get(cid, 0) <= 0)
        return frozenset(cid for cid, n in deck_counts.items() if seen.get(cid, 0) >= n)

    def _deck_known_counts(self, me: dict, prizes: dict | None) -> dict | None:
        """EXACT count of each card still in my deck (``decklist − visible − prizes``), once the
        deck-tracker has anchored the prizes; None when the prizes are not yet resolved (no positive
        deck claim without certainty). Only positive counts are kept."""
        if not self.deck or prizes is None:
            return None
        deck_counts = Counter(self.deck)
        seen = self._visible_card_counts(me)
        return {cid: rem for cid, n in deck_counts.items()
                if (rem := n - seen.get(cid, 0) - prizes.get(cid, 0)) > 0}

    def _visible_card_counts(self, me: dict) -> Counter:
        """Count MY card copies that are provably OUTSIDE the deck: my hand, my discard, every board
        Pokémon (its own id + attached Energy cards + Tools + the `preEvolution` cards stacked under
        it — e.g. the Staryu under a Mega Starmie ex) and any FACE-UP prize. Face-down prizes (None)
        and the hidden deck are left uncounted — exactly the unknowns that keep `_deck_empty_ids`
        sound."""
        counts: Counter = Counter()
        for c in (me.get("hand") or []):
            if c and c.get("id") is not None:
                counts[c["id"]] += 1
        for c in (me.get("discard") or []):
            if c and c.get("id") is not None:
                counts[c["id"]] += 1
        for p in (me.get("prize") or []):
            if p and p.get("id") is not None:          # a revealed prize (face-down prizes are None)
                counts[p["id"]] += 1
        for poke in (me.get("active") or []) + (me.get("bench") or []):
            self._count_in_play(poke, counts)
        return counts

    @staticmethod
    def _count_in_play(poke: dict | None, counts: Counter) -> None:
        """Add a board Pokémon and everything attached to / stacked under it (its own id, attached
        Energy cards and Tools, and the `preEvolution` cards beneath it) to `counts` — all are out
        of the deck."""
        if not poke:
            return
        if poke.get("id") is not None:
            counts[poke["id"]] += 1
        for group in ("energyCards", "tools", "preEvolution"):
            for c in (poke.get(group) or []):
                cid = c.get("id") if isinstance(c, dict) else c
                if cid is not None:
                    counts[cid] += 1

    def _hand_startable(self, hand: list) -> bool:
        """True if a card in hand can take the Active Spot — a Pokémon with the `opener`
        Function Tag (Explosiveness-type) or the deck's `starter` Role — so a no-Basic hand is
        keepable (a Basic would prevent the mulligan prompt entirely)."""
        for c in hand:
            cid = c.get("id") if c else None
            if cid is None:
                continue
            if self.functions and _OPENER_TAG in self.functions.tags(cid):
                return True
            if _STARTER_ROLE in self.strategy.roles.get(cid, []):
                return True
        return False

    def _option_pokemon(self, obs: dict, select: dict, option: dict) -> dict | None:
        """The board card/Pokémon dict an option's (area, index, playerIndex) points at, or None.
        AreaType -> zone via ``_ZONE`` (2=hand, 3=discard, 4=active, 5=bench); the owner defaults to
        me. A play-from-hand option (OptionType PLAY) carries only a bare hand `index` (no `area`),
        so it resolves against the hand — without this every Trainer/Pokémon play would have no card
        id, and so no roles/tags/stat, silently disabling every such Hypothesis on plays. A DECK
        search option (TO_HAND/ToField etc.) carries `area=DECK`, but the deck is hidden from the
        player zones — its revealed candidates live in the select's own ``deck`` list, so resolve
        there (this is what lets a 'fetch the win-condition' Hypothesis see a search's targets)."""
        area, index = option.get("area"), option.get("index")
        if area is None and option.get("type") == _PLAY:
            area = _HAND
        if area is None or index is None:
            return None
        if area == _DECK:                                  # search candidates revealed on the select
            deck = (select or {}).get("deck") or []
            return deck[index] if 0 <= index < len(deck) else None
        state = obs.get("current") or {}
        players = state.get("players") or []
        pi = option.get("playerIndex", state.get("yourIndex", 0))
        if not (0 <= pi < len(players)) or players[pi] is None:
            return None
        cards = players[pi].get(_ZONE.get(area))
        if not cards or not (0 <= index < len(cards)) or cards[index] is None:
            return None
        return cards[index]

    def _option_card_id(self, obs: dict, select: dict, option: dict) -> int | None:
        poke = self._option_pokemon(obs, select, option)
        return poke.get("id") if poke else None


def _fires(h, ctx: Context) -> bool:
    try:
        return bool(h.when(ctx))
    except Exception:
        return False
