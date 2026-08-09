"""`Board` (this turn's facts), `Context` (one option against them), `ShedPlan` (what a forced discard takes).

Assembled by `board_build` / `context_build`; living here rather than in `pilot.py` lets a decider module
annotate them without importing the Pilot."""
from __future__ import annotations


from dataclasses import dataclass, field
from typing import NamedTuple

from common.scouting.briefs import Brief
from common.scouting.matchup_plan import MatchupPlan
from common.scouting.read import Read
from common.strategy import GamePlan, Plan


class ShedPlan(NamedTuple):
    """`hand_indices` are REAL hand positions; `row_indices` are the resolver's ordinals. NOT interchangeable —
    `_needs_hand_rows` drops one copy first, so every later row sits one short of its hand position."""
    hand_indices: tuple
    row_indices: tuple
    rows: list
    cost: float

@dataclass
class Board:
    my_bench: int = 0
    bench_full: bool = False
    my_active_id: int | None = None
    my_active_energy: int = 0
    my_active_hp: int = 0
    opp_bench: tuple = ()          # ((cardId, hp), …)
    known_top: tuple = ()          # ((serial, cardId), …) known ordered top of my deck, head first
    turn: int = 0
    energy_attached: bool = False
    supporter_played: bool = False # a Supporter grabbed now cannot be PLAYED until next turn; an Item can
    hand_startable: bool = False   # a card in hand can take the Active Spot (opener tag / starter role)
    active_doomed: bool = False    # opponent can KO my Active NEXT turn
    incoming_active_damage: int = 0  # their biggest attack vs my Active, weakness-doubled (closed-form)
    active_cheap_attack_kos: bool = False  # my Active's CHEAPEST attack KOs their Active this turn
    active_can_ko: bool = False    # my Active's BEST affordable attack (CURRENT Energy) KOs their Active
    active_maxed_kos: bool = False # my BIGGEST attack fully powered KOs — False = un-KO-able even maxed
    gust_best_ko_prizes: int = 0   # best prizes among their bench my Active could KO after gusting one up
    active_ko_prizes: int = 0      # prizes from KOing their CURRENT Active — the baseline a gust must beat
    gust_best_total_prizes: int = 0  # + the same-attack snipe rider on the post-gust bench (ADR-0066)
    menu_attack_total_prizes: int = 0  # best one-attack total WITHOUT a gust, riders included (ADR-0066)
    gust_ko_energy_swing: int = 0  # Energy sunk on the gust target MINUS what the baseline KO destroys
    stall_swap_pointless: bool = False  # the famine stall swaps one stranded wall for an equal-or-worse one
    my_prizes_remaining: int = 0   # 0 when obs doesn't populate it
    opp_prizes_remaining: int = 0  # 0 when obs doesn't populate it
    reusable_energy_in_hand: bool = False  # an Energy that does NOT discard at end of turn
    wincon_in_play: bool = False
    wincon_prize_value: int = 0    # max over my wincon bodies (Mega ex 3 / ex 2 / else 1); 0 if none
    wincon_in_hand: bool = False
    top_fetch_priority_id: int | None = None  # at a TO_HAND search, the top id PRESENT by fetch_priority
    top_starter_id: int | None = None  # at SETUP_ACTIVE, the top id PRESENT by starter_priority (ADR-0079)
    line_preevo_in_play: bool = False
    line_preevo_in_hand: bool = False  # NO READER since ADR-0065 retired the rung
    wincon_base_deployable: bool = False  # the IMMEDIATE pre-evo is in play or hand — a Stage-0 base is NOT
    wincon_in_hand_undeployable: bool = False  # an EVOLUTION wincon with no base anywhere: dead, so shuffle it
    accel_recipient_missing: bool = False
    support_in_play: bool = False      # a draw/accel/search Ability body (`_ENGINE_TAGS`) on Active/Bench
    in_play_ids: frozenset = field(default_factory=frozenset)
    in_play_attack_colors: frozenset = field(default_factory=frozenset)
                                       # colors my in-play attackers' attacks require (`AttackStat.energyTypes`)
    in_play_required_colors: frozenset = field(default_factory=frozenset)
                                       # attack colors UNION ability-fuel colors of my in-play bodies
    in_play_unfueled_ability_colors: frozenset = field(default_factory=frozenset)
                                       # ability-fuel colors of in-play bodies with none of that colour attached
    setup_placed_ids: frozenset = field(default_factory=frozenset)
                                       # placed during PREGAME setup, read from MOVE_CARD logs. NO READER
    hand_duplicate_ids: frozenset = field(default_factory=frozenset)
                                       # held 2+ times, EXCLUDING fungible Energy
    energy_placeable: bool = False     # some in-play body can still absorb Energy productively. Fail-open
    weakest_bench_hp: int | None = None  # least HP among THEIR benched snipe targets at a DAMAGE select
    strongest_forward_bench: int | None = None  # greatest forward-evolution damage among those targets
    snipe_ko_available: bool = False    # some benched target dies to the rider, so POSITIONAL rungs stand down
    snipe_damage: int = 0              # the rider my Active's attack deals, max over its attacks; ignores W/R
    best_counter_slot: tuple | None = None  # (area, index, playerIndex) at ctx 14/13 — knapsack-optimal
    best_counter_source_slot: tuple | None = None  # (area, index, playerIndex) of OUR most-damaged body, ctx 16
    max_counter_move_number: int = 0    # largest count offered at ctx 40
    stadium_in_play: int | None = None  # card id of the Stadium in play (`current.stadium`)
    opp_stadium_in_play: bool = False
    bench_wincon_ready: bool = False
    best_promote_slot: tuple | None = None  # (AreaType, index): READY and most-Energy, not a bare copy
    ko_promote_slot: tuple | None = None  # (AreaType, index) of the benched body whose affordable attack KOs
    evolve_to_ready_wincon_available: bool = False  # evolving THIS turn would yield a ready attacker
    bench_wincon_prize_value: int = 0
    bench_wincon_underpowered: bool = False  # carries fewer Energy than its highest-damage attack costs
    opp_cannot_punish_wincon: bool = False  # ADR-0064 D4: their Incoming can't KO it next turn. Fails CLOSED
    basic_energy_in_deck: bool = False  # not known-exhausted
    opp_has_played_gust: bool = False  # a `gust`-tagged card sits in their discard
    active_is_wincon: bool = False
    active_is_weak_preevo: bool = False  # printed output far below the body it evolves into
    can_wall_line_with_disruptor: bool = False  # fragile line-preevo Active + benched `item_lock` + damage NOW
    can_lock_line_with_disruptor: bool = False  # the OFFENSIVE variant, minus the incoming-damage premise
    priority_wincon_slot: tuple | None = None  # (AreaType, index) of the ONE wincon to concentrate Energy on
    attach_from_concentrate_slot: tuple | None = None  # (AreaType, index): most Energy still short of payoff
    stall_target_exists: bool = False  # they have an energyless, high-retreat benched Pokémon (ADR-0022)
    stall_target_is_keystone: bool = False  # that target is an ex / Mega ex
    deny_relevance_best: float | None = None
                                       # ADR-0080 best relevance on their board, [0,1]. **`None` means ABSENT,
                                       # not zero** (ADR-0093 d2) — it fails CLOSED to a recompute
    deny_relevance_rows: tuple | None = None
                                       # per-body `(area, bi, {EnergyType: relevance}, strip_shift)`; None = ABSENT.
                                       # Keyed by TYPE never position: `energyIndex` indexes CARDS, `energies` UNITS
    opp_has_energy_in_play: bool = False
    opp_active_has_energy: bool = False   # NOT the `play-energy-denial` gate (ADR-0062): that card hits either
                                          # area, and this fires on surplus Energy besides
    opp_active_can_damage_us: bool = False  # oracle-resolved, so a conditional 0-damage attack is NO threat
    opp_hand_size: int = 0
    my_hand_size: int = 0                 # the don't-gift-a-refresh comparator: strip only when theirs is bigger
    # Opponent RESOURCES (ADR-0047) flattened onto the Board so a `when()` can trigger without reaching
    # through `board.opponent.resources`. Every value fails OPEN (unknown -> the no-fire default).
    opp_took_ko_this_turn: bool = False   # so their post-KO disruptor (Unfair Stamp) is now enabled
    my_pokemon_koed_last_turn: bool = False  # THE MIRROR — MY Unfair Stamp's own play condition
    opp_hand_size_delta: int | None = None  # vs their previous distinct turn. POSITIVE = they GREW it = FRESH
    opp_last_turn_dumped: bool = False    # their discard grew ≥2 — they have COMMITTED to what they kept
    opp_deckout_in_turns: int | None = None  # None until ≥2 samples show a net decrease. SOUND (deck-count is public)
    opp_comeback_disruptor: bool = False  # a Brief property, γ-gated. False when unrecognized
    opp_hand_strip_odds: float = 0.0      # P(their deck holds a `hand_disruption` card). One held in HAND is
                                          # not in-deck, so this UNDER-counts — the safe direction
    deck_empty_ids: frozenset = field(default_factory=frozenset)
                                          # MY ids the deck is PROVABLY empty of. Sound, never probabilistic
    deck_known_counts: dict | None = None  # EXACT counts, once the tracker anchored prizes; None until then
    deck_contains_odds: dict | None = None  # {cardId: P(deck still holds ≥1 copy)} (ADR-0029)
    opp_active_condition_gift: bool = False  # gusting it to bench would CLEAR the condition (ADR-0022 #10)
    active_condition_ko_prizes: int = 0   # prizes from their Active dying to poison/burn at the next Checkup
    read: Read | None = None              # None = Posture off
    opponent: object = None               # the Opponent Model facade (ADR-0047); None = direct Board (tests)
    posture_confidence: float = 0.0       # γ ∈ [0,1] from the Read; 0 = unrecognized / no Scout
    favorability: float = 0.5             # compiled matchup win-rate vs the Read's candidates (0.5 = neutral)
    matchup_coverage: float = 0.0         # share of the posterior that hit a real cell — low means trust it less
    brief: Brief | None = None            # matched Matchup Brief (ADR-0027, covers-routed)
    brief_threat_ids: frozenset = field(default_factory=frozenset)
    brief_target_roles: dict = field(default_factory=dict)  # {opp id: Dossier role}
    matchup_plan: MatchupPlan = field(default_factory=MatchupPlan)
                                          # ADR-0051 target-priority spine; empty (all-0) default = inert
    opp_discard_energy: dict = field(default_factory=dict)
                                          # {EnergyType: count} in THEIR discard — a discard-fuelled forward line
    my_discard_basic_energy: dict = field(default_factory=dict)
                                          # {EnergyType: count} in MY discard — the ONE truth for it (ADR-0061)
    active_best_attack_locked: bool = False  # transient-locked this turn (Mega Brave class, ADR-0033)
    opp_has_stage2: bool = False          # the Gravity Mountain tech read
    opp_has_colorless_ability: bool = False  # the Team Rocket's Watchtower read
    hand_ids: frozenset = field(default_factory=frozenset)
    search_deck_ids: frozenset | None = None  # the CURRENT search's revealed pool — an EXACT within-frame
                                          # reachability test; None off a deck-revealing select
    hand_basic_energy: dict = field(default_factory=dict)  # {EnergyType: count} in MY hand
    recycle_dead_only: bool = False       # the recycle pool is non-empty yet every member is a dead pick
    active_fully_powered: bool = False    # carries its highest-damage attack's cost. Fail-closed when unknown
    active_famine: bool = False           # cannot attack this turn under the FULL Attach Budget, or is blocked
    active_attack_provable: bool = True   # can PAY and legally attack on the PROVABLE Budget. True when unknown
    active_unarmed_but_able: bool = False  # ZERO Energy yet can still REACH an attack this turn
    immediate_preevo_in_play: bool = False  # so a hand copy of it is redundant
    deploy_now_ids: frozenset = field(default_factory=frozenset)
                                          # hand evolutions with an ELIGIBLE in-play base THIS turn (ADR-0065)
    active_arm_available: bool = False    # a real ATTACKER whose biggest attack ONE Energy would COMPLETE, and
                                          # no ready benched wincon to retreat into
    no_supporter_in_hand: bool = False
    my_path_turns: float | None = None    # ADR-0040 feasibility turns over their VISIBLE bodies; None = runs
                                          # through bodies not yet in play
    their_path_turns: float | None = None # their cheapest path over MY bodies — worst-case (uncharged)
    race_ahead: float | None = None       # their_path_turns − my_path_turns
    path_target_ids: frozenset = field(default_factory=frozenset)  # opp ids on MY cheapest Prize Path
    path_target_keys: frozenset = field(default_factory=frozenset)
                                          # the same as `id(body)` — duplicate-species-safe (ADR-0044)
    opp_active_doomed: bool = False       # so a promotion is FORCED next turn (ADR-0044)
    forced_promotion_key: int | None = None  # `id(body)` of the one they will then promote (ADR-0044)
    their_path_my_ids: frozenset = field(default_factory=frozenset)  # MY ids on THEIR cheapest path
    line_ready: bool = False              # a wincon payoff is in play with enough Energy to attack
    bench_line_member_needs: bool = False  # a benched Line body still needs Energy for its cheapest attack
    phase: Plan = Plan.SETUP              # ADVISORY ONLY (ADR-0040) — band weights + trace, never a gate
    game_plan: GamePlan | None = None     # COMPUTE-ONLY (ADR-0045): nothing scores off it yet
    turn_goal_satisfied: bool = False     # the directed goal is met and nothing is still searching, so a
                                          # Supporter can be HELD. Must FAIL SAFE to False

    def deck_definitely_empty_of(self, card_id: int) -> bool:
        """PROVABLY absent from my deck — certain, never probabilistic (a copy that could still be prized
        leaves this False, unless the deck-tracker has resolved the prizes)."""
        return card_id in self.deck_empty_ids

    def deck_definitely_has(self, card_id: int) -> bool:
        """PROVABLY still in my deck; needs the tracker's exact counts. False when unknown — positive
        certainty is never asserted on a guess."""
        return bool(self.deck_known_counts) and self.deck_known_counts.get(card_id, 0) > 0

    def deck_contains_probability(self, card_id: int) -> float:
        """PROBABILISTIC P(my deck still contains `card_id`) ∈ [0,1] (ADR-0029). Returns **1.0** when the odds
        are uncomputable, so a consumer never SUPPRESSES on missing data."""
        if self.deck_contains_odds is None:
            return 1.0
        return self.deck_contains_odds.get(card_id, 0.0)

    def opp_property(self, key: str, default=None):
        """Opponent-property ``key`` off the matched Brief, else ``default``. Never raises; the Brief is
        assert-true-only, so an omitted key reads as ``default``. Routed through the facade when present."""
        if self.opponent is not None:
            return self.opponent.disposition(key, default)
        if self.brief is None:
            return default
        return self.brief.opponent_properties.get(key, default)

    def brief_is_threat(self, card_id: int) -> bool:
        """Does the matched Brief list ``card_id`` as a threat (ADR-0027)? UNCONSUMED: no `src/` caller —
        kept as a Brief-consumption seam."""
        return card_id in self.brief_threat_ids

    def brief_target_role(self, card_id: int):
        """The Brief's target role for ``card_id`` (``fragile_preevo`` / ``prize_liability`` / ``engine``).
        UNCONSUMED: no `src/` caller."""
        return self.brief_target_roles.get(card_id)

    def brief_target_ids(self, role: str | None = None) -> frozenset[int]:
        """Brief disruption/snipe targets, filtered to ``role`` when given. UNCONSUMED: no `src/` caller."""
        if role is None:
            return frozenset(self.brief_target_roles)
        return frozenset(cid for cid, r in self.brief_target_roles.items() if r == role)

@dataclass
class Context:
    """What the Score layer knows about one option — the input a Hypothesis trigger reads."""
    plan: Plan
    select_context: int | None
    option_type: int | None
    card_id: int | None
    option_area: int | None = None  # AreaType of the option's target (4=active, 5=bench)
    card_stranded_evolution: bool = False  # its `evolvesFrom` chain reaches no Basic on THIS deck list
    params: dict = field(default_factory=dict)  # deck's `Strategy.params`, read-only
    attach_target_area: int | None = None  # 4=active can attack this turn, 5=bench cannot
    attach_target_roles: list = field(default_factory=list)
    attach_target_needs: bool = False  # recipient carries fewer Energy than its cheapest attack cost
    attach_is_energy: bool = True      # not a Tool — the engine sends both as `ATTACH`. Fail-open on unknown
    attach_target_is_utility_body: bool = False  # NO READER: ADR-0069 moved the gate into `_attach_value`
    attach_target_under_max: bool = False  # fewer Energy than its HIGHEST-damage attack costs. Fail-CLOSED
    attach_target_is_priority_wincon: bool = False  # == board.priority_wincon_slot. NO READER (ADR-0069)
    attach_fuels_dormant_ability: bool = False  # a colour the target's ABILITY needs, with none attached
    attach_feeds_firing_accel: bool = False  # an ACTIVE accelerator that still NEEDS it, with a bench recipient
    attach_target_is_line_member: bool = False  # read into `OptionTrace.attach_to_needy_line`, a decide() tie-break
    attach_target_is_draw_engine: bool = False  # its job is cards, not attacking (or it evolves into one)
    attach_from_target_needs: bool = False  # at an ATTACH_FROM recipient-select. False off ATTACH_FROM
    attach_from_target_is_concentrate: bool = False  # == board.attach_from_concentrate_slot — build ONE body
    card_is_line_preevo: bool = False  # a non-payoff member of a Line's path
    card_is_recognized_line_preevo: bool = False  # of ANY declared attacker Line (ADR-0048); narrows when off
    card_forward_payoff_prize: int = 0  # max prize value this card BECOMES over it + forward evolutions
    card_evolution_baseless: bool = False  # no base in my play or hand — a dead grab
    card_base_unreachable: bool = False  # its base is provably UNGETTABLE this game
    card_is_wincon: bool = False
    card_is_starter: bool = False      # a startable Basic Pokémon (hp > 0, no `evolvesFrom`)
    card_is_support: bool = False      # hp > 0 with a draw/accel/search Ability (`_ENGINE_TAGS`)
    card_is_utility_body: bool = False  # draws/tutors/stalls and never attacks
    card_is_top_fetch_priority: bool = False  # == board.top_fetch_priority_id
    card_is_top_starter: bool = False  # == board.top_starter_id; retained metadata after Issue #459 retired its scorer
    card_is_redundant: bool = False    # duplicates a Pokémon already in play
    card_is_hand_duplicate: bool = False  # held 2+ times (fungible Energy excluded)
    card_already_in_hand: bool = False  # at a TO_HAND search (fungible Energy excluded)
    card_unplayable_this_turn: bool = False  # a SUPPORTER while the quota is spent — an Item could still be played
    card_chain_value: float = 0.0      # discounted tutor-chain closure value; 0.0 in `_grab_value_of`'s Context
    card_spends_last_evolution_route: bool = False  # the LAST free tutor reaching an evolution whose base I hold
    fetch_fills_a_need: bool = False   # its reachable deck set still holds a card I lack
    fetch_target_deferred: bool = False  # ...AND every needed target is provably UNPLAYABLE this turn
    refresh_shuffles_deferred_fetch: bool = False  # a refresh while a held fetch's grab is deferred past this turn
    target_energy: int | None = None  # Energy on the targeted benched Pokémon (None off a Damage option)
    target_is_threat: bool = False  # target already carries Energy
    target_hp: int | None = None    # None off a Damage option
    target_is_weakest: bool = False
    target_is_strongest_forward: bool = False  # its line reaches the greatest forward damage on the Bench
    target_forward_form_in_play: bool = False  # its EVOLVED form is ALREADY out — chip that instead (ADR-0044)
    target_kos: bool = False           # riders ignore W/R. Never true for a benched Tera body
    target_is_bench_tera: bool = False  # takes no attack damage at all — backs the STRUCTURAL `_snipe_tera_veto`
    promote_target_kos: bool = False   # the body brought up can KO their Active this turn
    is_best_promote_target: bool = False  # == board.best_promote_slot. NO READER since ADR-0100
    is_ko_promote_target: bool = False  # == board.ko_promote_slot
    card_prize_value: int = 1          # prizes a KO of THIS card yields (Mega ex 3 / ex 2 / else 1)
    promote_target_can_attack: bool = False  # a live attacker to interpose, not a dead wall
    promote_target_hits_weakness: bool = False  # it would strike their Active on its Weakness (×2)
    target_forward_damage: int | None = None  # max damage its evolution line eventually reaches (ADR-0020)
    target_on_path: bool = False        # on MY cheapest Prize Path. No PRODUCTION reader since ADR-0085
    target_prize_redundant: bool = False  # OFF my committed cheapest path (ADR-0044) — suppresses the threat snipe
    target_is_forced_promotion: bool = False  # their Active is dead and THIS is the body they'll promote
    target_promotion_mirage: bool = False  # ...and this is NOT that body, so its threat is a mirage
    bench_shortens_their_path: bool = False  # benching THIS strictly improves their cheapest path (ADR-0040)
    bench_path_delta: float = 0.0       # ...and by HOW MUCH, in turns; 0 when `objectives_path` is off
    promote_target_on_their_path: bool = False  # rung DELETED as subsumed (ADR-0100 §7c)
    counter_is_best_placement: bool = False   # == board.best_counter_slot
    counter_is_source_pick: bool = False      # == board.best_counter_source_slot
    is_max_counter_move: bool = False         # the largest count at a REMOVE_DAMAGE_COUNTER_COUNT select
    evolve_body_energy: int | None = None     # energy on the body an EVOLVE option would evolve
    roles: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    stat: object | None = None     # option card's engine CardStat
    board: Board = field(default_factory=Board)
    context_card_id: int | None = None  # the select's OWNER (`select.contextCard`) — an ACTIVATE's bare
                                   # YES/NO carries no card itself
    search_targets_exhausted: bool = False  # every legal fetch target is PROVABLY gone from deck. SOUND
    search_redundant_wincon: bool = False  # a wincon-only tutor with no productive landing for the payoff
    search_baseless_wincon: bool = False  # ...payoff neither in hand nor in play AND no deployable base
    search_targets_unlikely: bool = False  # PROBABLY prized (ADR-0029) — mutually exclusive with `_exhausted`
    search_confirmed_hit: bool = False  # PROVABLY hits and fills a need (ADR-0029)
    # The three COST-NETTING bands, all read off ONE number: what the keep-value v2 assignment says the two
    # cards it would actually shed cost (`_shed_signals` -> `needs.removal_score`) — the deciding equation.
    fetch_sheds_junk: bool = False  # a cost_discard fetch whose sheds cost ≤ 0 and are dead or replaceable
    fetch_sheds_live: bool = False  # ...the predicted shed costs > 0
    fetch_sheds_key: bool = False   # ...it costs at least ACE_SPEC_TIER
    refresh_probable_miss: bool = False  # its N-card draw PROBABLY misses every needed card (ADR-0024)

def _slot_cid(slot):
    """The card id a `line:<cid>` slot belongs to, or None for any other slot kind."""
    key = getattr(slot, "key", "") or ""
    if getattr(slot, "kind", "") != "line" or not key.startswith("line:"):
        return None
    head = key.split(":")[1]
    return int(head) if head.isdigit() else None
