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

from common import deck_odds
from common.strategy import Plan, Strategy
from common.scouting.read import Read
from common.scouting.matchup import matchup_favorability
from common.scouting.briefs import Brief, match_brief

# Engine vocab (enum mirrors, KO_SCORE, _ENGINE_TAGS) shared w/ doctrines -> common.strategy.context.
# Doctrines own their Hypotheses + Pilot-side `*Mixin` code — see those modules.
from common.strategy.context import *  # noqa: F401,F403  (the engine-vocabulary constants + _fires/Board live there or below)
from common.strategy.doctrines import FetchMixin, GustMixin, ShuffleRefreshMixin, ToolMixin
from common.strategy.planner import PlannerMixin, TurnLine

# Tactical-only scalars — used SOLELY by the closed-form combat evaluator below, never by a doctrine.
_EFFICIENCY = 0.1          # per-Energy tiebreak: among equal-outcome attacks prefer cheaper one;
                           # far below prize granularity (1) so never overrides prize value
_BENCH_SNIPE = 0.005       # per-point value of an attack's bench-snipe rider, capped below — a sub-prize
_BENCH_SNIPE_CAP = 0.9     # tiebreak so among equal-outcome KO attacks the one that ALSO snipes a benched
                           # target wins (best total board value), without ever overriding a prize (ADR-0022 #14)
_ENERGY_RECOVER = 75       # per-Energy value of a recover rider (Aura Jab: "attach up to N Basic {X}
                           # from discard") on a NON-KO turn — chip-scale, so fueled Aura Jab beats bare Mega Brave
_RECOVER_KO = 0.25         # KO-branch sub-prize variant: "the cheaper KO that also develops" —
_RECOVER_KO_CAP = 0.75     # capped < 1, never overrides a real prize difference (like bench-snipe)
_LOCK_COST = 40            # charge a self-locking attack (Mega Brave) when a LOCK-FREE one is affordable;
                           # never charged on the only affordable attack (chipping still beats passing)
_LOCK_KO = 0.3             # KO-branch sub-prize variant: among equal-prize KOs keep the nuke off cooldown
_RECOIL_DOOM = 100         # charge a NON-KO attack whose recoil FLIPS a safe Active doomed (Wild Press at
                           # 80 HP) — combat-scale; a KO/snipe-KO or already-doomed Active is never charged
_ENERGIZED_SNIPE_TIER = 100000  # energized benched target is strictly higher snipe TIER than any
                           # bare one — attacks SOONER (imminence), sniped before a bigger latent
                           # threat (ADR-0020). Within a tier, threat magnitude orders the choice.
_HAND_SIZE_ATTACKER_BOOST = 500  # snipe-rank boost for a benched body whose evolution line CERTAINLY
                           # reaches a hand-size attacker (Kadabra→Alakazam "Powerful Hand") — latent
                           # win-condition hidden by low printed damage. `hand_size_attacker` Function Tag.
_PREVENT_EX_SNIPE_BOOST = 500  # snipe-rank boost for a benched body whose line reaches a Pokémon that
                           # PREVENTS my ex attacker's damage (`prevent_ex_damage`, e.g. Dwebble→Crustle) —
                           # hard counter once evolved, snipe the fragile pre-evo NOW (ep82225138 f46).
_RETREAT_POSITION_EPS = 0.001  # positioning tie-break for retreat-to-lethal lookahead: when retreating
                           # into a ready wincon takes the SAME KO the spent Active could, prefer it (wincon
                           # ends up Active) — tiny, only breaks exact ties, never beats a real edge.
_RESISTANCE = 30           # damage Resistance subtracts when defender resists attacker's type.
                           # Printed per-card fact, not in CSV (type only) — verified uniform -30 across 47
                           # resistant Pokémon via tools/sim/probe_resistance.py. Applied AFTER Weakness.

# Posture confidence (ADR-0026): continuous γ ∈ [0,1] the generic-core levers scale by. Ramp the
# Read's top posterior over [LO, HI], discount by unmatched mass -> unknown opponent → γ≈0.
_POSTURE_GAMMA_LO = 0.5     # below this top-posterior, Posture off (recognition too weak to act on)
_POSTURE_GAMMA_HI = 0.85    # at/above this, Posture at full strength


def _posture_gamma(read) -> float:
    """Posture confidence γ ∈ [0,1] from the Read (ADR-0026): ramp the top posterior over
    [_POSTURE_GAMMA_LO, _POSTURE_GAMMA_HI], discounted by the unmatched (unknown) mass. 0 when there is no
    Read or it is unrecognized — so an unknown opponent makes Posture contribute nothing (no-regression)."""
    if read is None or not read.candidates:
        return 0.0
    top = read.confidence[0] if read.confidence else 0.0
    ramp = max(0.0, min(1.0, (top - _POSTURE_GAMMA_LO) / (_POSTURE_GAMMA_HI - _POSTURE_GAMMA_LO)))
    return ramp * (1.0 - read.unknown_mass)


def choose_plan(state: dict, strategy, stats=None) -> Plan:
    """Pick this turn's Plan. SETUP until a win-condition Line's payoff is in play with enough
    energy to attack; then RACE. A Line's `ready.energy` is the threshold; when unset (None) it is
    derived from the engine — the payoff's cheapest attack cost, so a 1-Energy attack counts.
    (STABILIZE / CLOSE arrive with their own signals.)"""
    me = state["players"][state["yourIndex"]]
    board = [p for p in (me.get("active") or []) + (me.get("bench") or []) if p]
    for line in strategy.lines:
        threshold = line.ready.energy
        if threshold is None:                          # derive "online" from cheapest attack
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
    opp_bench: tuple = ()          # ((cardId, hp), …) of the opponent's benched Pokémon
    turn: int = 0
    energy_attached: bool = False  # already attached Energy this turn?
    hand_startable: bool = False   # a card in hand can take Active Spot (opener tag / starter role)
    active_doomed: bool = False    # opponent can KO my Active next turn (incoming-KO estimate)
    incoming_active_damage: int = 0  # closed-form estimate of opponent's biggest attack vs my
                                     # Active (weakness-doubled) — margin behind active_doomed,
                                     # exposed so a +HP tool can test it crosses a survival breakpoint
    active_cheap_attack_kos: bool = False  # my Active's CHEAPEST attack would KO opponent's Active
                                           # this turn (closed-form) — costly burst Energy
                                           # (e.g. Ignition->Nebula) unnecessary; cheap attack does it
    active_can_ko: bool = False    # my Active's BEST affordable attack (given CURRENT Energy) would
                                   # KO opp Active this turn — superset of active_cheap_attack_kos, sees BIG
                                   # attacks too. Gates `hold-clutch-heal`: KO on board -> take it, no heal-stall (ep83037962 f78)
    active_maxed_kos: bool = False # my Active's BIGGEST attack (fully powered, ignoring current Energy)
                                   # would KO opp Active — False means un-KO-able even maxed. Gates whether
                                   # a burst (Ignition) is worth spending; if maxed can't KO, conserve it (ep83116501 f70)
    gust_best_ko_prizes: int = 0   # best prizes among opponent's benched Pokémon my Active could KO
                                   # after gusting one to Active Spot (0 if none) — whether-to-play
                                   # gate for a gust Supporter (Boss's Orders). ADR-0022.
    active_ko_prizes: int = 0      # prizes from KOing opponent's CURRENT Active with my cheapest
                                   # attack (0 if can't) — baseline a gust must beat (gusting
                                   # removes this Active, only worth the Supporter for a bigger KO)
    my_prizes_remaining: int = 0   # prizes I still need to take (len of my prize pile); 0 when obs
                                   # doesn't populate it. A gust KO reaching this count WINS (ADR-0022)
    opp_prizes_remaining: int = 0  # prizes OPPONENT still needs (len of their prize pile); 0 when
                                   # obs doesn't populate it. A recoil KOing my Active + handing them
                                   # THIS many prizes simultaneously with my own lethal is a DRAW (ADR-0022 #2)
    reusable_energy_in_hand: bool = False  # a plain (non-discard) Energy in hand — reusable
                                           # alternative to a discard-at-end-of-turn Energy
    wincon_in_play: bool = False   # my win-condition (a Line payoff / win_condition role) already
                                   # on my Active or Bench — search needn't fetch another copy
    wincon_in_hand: bool = False   # win-condition card already in my hand — tutor needn't
                                   # dig for another copy
    top_fetch_priority_id: int | None = None  # at a TO_HAND search, highest-priority candidate id
                                       # present, by deck's explicit Strategy.fetch_priority list
                                       # (None off a search / no list / none present) — Tier-3 override
    line_preevo_in_play: bool = False  # a non-payoff member of a Line's path (a pre-evolution) is in
                                       # play — so there's something a rush-evolve tutor can evolve
    wincon_base_deployable: bool = False  # a Line pre-evolution (a base to evolve payoff from) is in
                                       # play OR in hand — evolved payoff deployable. False -> fetching
                                       # payoff strands it: prefer base (`fetch-base-before-stranded-payoff`)
    accel_recipient_missing: bool = False  # my Active is a bench-accelerator (an `accel_source`-role
                                       # Pokémon, e.g. Cinderace Turbo Flare) AND no Line member on my Bench
                                       # to receive it — accel wasted, developing a recipient is top priority
    support_in_play: bool = False      # an engine/support Pokémon (a draw/accel/search Ability, see
                                       # _ENGINE_TAGS) on my Active/Bench — gap gate for
                                       # `fetch-the-support` (with an engine online, no need to tutor one)
    in_play_ids: frozenset = field(default_factory=frozenset)  # card ids of my in-play Pokémon
                                       # (Active + Bench) — a hand copy of one is a redundant duplicate
                                       # (need already met), keep-value floor `discard-the-redundant`
    hand_duplicate_ids: frozenset = field(default_factory=frozenset)  # card ids I hold 2+ copies of in
                                       # hand, EXCLUDING fungible Energy — lowest-keep pitch at a forced
                                       # discard (`discard-the-hand-duplicate`); singleton never shed over dup
    energy_placeable: bool = False     # some in-play Pokémon can still absorb Energy productively (it
                                       # carries fewer Energy than its highest-damage attack costs). False ->
                                       # no useful home this turn, `attach-before-hand-shuffle` can't veto a needed refresh (ep83038055 f40). Fail-open.
    weakest_bench_hp: int | None = None  # least HP among opponent's benched snipe targets at a
                                         # DAMAGE select — target closest to a knockout
    strongest_forward_bench: int | None = None  # greatest forward-evolution damage among opponent's
                                                # benched snipe targets at a DAMAGE select — most dangerous
                                                # latent evolving threat (Riolu→Mega Lucario over Hariyama). None off a Damage select
    bench_threat_present: bool = False  # at a DAMAGE select, some benched snipe target already carries
                                        # Energy (an imminent attacker) — evolving-threat snipe
                                        # stands down: snipe-the-threat (energized) is the priority
    snipe_damage: int = 0              # at a DAMAGE select, bench-snipe rider my Active's attack
                                       # deals (max over my Active's attacks) — closed-form KO test for a
                                       # snipe target (rider >= target HP; ignores W/R). 0 off a Damage select
    strongest_threat_rank: float = 0.0  # at a DAMAGE select, greatest snipe THREAT RANK among
                                        # benched targets (`_target_threat_rank`: max own/forward damage,
                                        # +boost for a hand-size-attacker line) — snipe pick when none KO'd. 0 off a Damage select
    bench_wincon_ready: bool = False   # a benched win-condition / primary attacker already carries
                                       # enough Energy to attack — a finisher to retreat into
    best_promote_slot: tuple | None = None  # (AreaType, index) of MY benched win-condition best to bring
                                       # to Active at a promote/switch — READY (Energy >= cheapest attack)
                                       # AND most-Energy. Backs `promote-the-powered-attacker`, not a bare copy/slot-0 (ep83007714 f92/f104)
    evolve_to_ready_wincon_available: bool = False  # win-condition in hand AND a benched
                                       # pre-evo already carries enough Energy that evolving THIS turn yields
                                       # a ready attacker — worth promoting to evolve. False -> bare pre-evo, promote staller/accel instead (ep82753102 f120)
    bench_wincon_prize_value: int = 0  # greatest prize value among my BENCHED win-conditions (Mega ex 3 /
                                       # ex 2 / else 1), 0 if none — prize I keep OFF the front line by
                                       # interposing a cheaper attacker at a forced promote (prize denial)
    bench_wincon_underpowered: bool = False  # a benched win-condition carries fewer Energy than its
                                       # highest-damage attack costs — can't yet fire payoff, so an accel
                                       # promote can power it off-Bench, which promoting the finisher directly can't
    basic_energy_in_deck: bool = False  # my deck can still yield a Basic Energy (a Basic-Energy id not
                                       # known-exhausted) — fuel gate for an accelerator promote
                                       # (Cinderace's Turbo Flare fetches Basic Energy to the Bench)
    opp_has_played_gust: bool = False  # opponent has played a gust (Boss's Orders-style forced switch)
                                       # this game — a `gust`-tagged card in their discard; can drag my
                                       # benched finisher out, so interposing a cheap body taxes that gust
    active_is_wincon: bool = False     # my Active IS the win-condition / primary attacker
    tool_deploy_slot: tuple | None = None  # (AreaType, inPlayIndex) of body to equip my held +HP
                                       # Tool this turn — survival-turns target picker (ADR-0028);
                                       # None when no +HP Tool in hand / no body worth equipping
    irreplaceable_tool_in_hand: bool = False  # an ACE SPEC (one-per-deck, unrecoverable) Tool is in
                                       # my hand — anti-shuffle belt (never shuffle it away)
    priority_wincon_slot: tuple | None = None  # (AreaType, index) of the ONE win-condition Pokémon to
                                       # concentrate Energy on — most-Energy wincon still short of biggest
                                       # attack. Active skipped if it can already KO. None when no buildable wincon
    attach_from_concentrate_slot: tuple | None = None  # (AreaType, index) of the Line body to load at an
                                       # ATTACH_FROM (Turbo Flare recipient) select — Line member with MOST
                                       # Energy still short of payoff cost, so accel CONCENTRATES not spreads. None when none exists.
    stall_target_exists: bool = False  # opponent has an energyless, high-retreat benched Pokémon —
                                       # candidate to strand Active with a defensive stall-gust (ADR-0022)
    stall_target_is_keystone: bool = False  # that stall target is opponent's KEY attacker (an ex /
                                       # Mega ex) — stranding their win-condition Active is high-value
                                       # disruption, worth the Supporter over a redundant dig (ADR-0022)
    opp_has_energy_in_play: bool = False  # opponent has Energy on any Pokémon (Active or Bench) —
                                          # a target an energy-denial Item (Crushing Hammer) can strip
    opp_active_has_energy: bool = False   # opponent's ACTIVE carries Energy — the imminent attacker,
                                          # the worthwhile energy-denial target. Gate for `play-energy-denial`:
                                          # stripping a benched SUPPORT's lone Energy is a wasted Item (ep82753102 f37)
    opp_has_hand_size_attacker: bool = False  # opponent has a Pokémon in play (or in a committed
                                          # evolution line) that SCALES damage with hand size (a
                                          # `hand_size_attacker`, e.g. Alakazam) — `play-harlequin-vs-hand-size` gate. Card-fact, not meta guess
    deck_empty_ids: frozenset = field(default_factory=frozenset)  # MY card ids the deck is PROVABLY
                                          # empty of. Stateless: every copy seen OUTSIDE the deck reaches the
                                          # 60-count. With `obs['own_prizes']` it's EXACT. Sound, never probabilistic. Queried by `deck_definitely_empty_of`.
    deck_known_counts: dict | None = None  # EXACT count of each card still in my deck, once the
                                          # deck-tracker anchored prizes (decklist − visible − prizes); None
                                          # until first search reveal. Backs the POSITIVE `deck_definitely_has`;
                                          # its decision reader is `search-the-confirmed-hit` (`Context.search_confirmed_hit`, doctrine_fetch).
    deck_contains_odds: dict | None = None  # PROBABILISTIC {cardId: P(deck still holds ≥1 copy)} —
                                          # complement to the SOUND deck_definitely_empty_of (ADR-0029): unseen
                                          # copies split hypergeometrically over hidden prizes; collapses to 1.0/0.0 once resolved. Feeds `dont-search-a-probable-whiff`.
    opp_active_condition_gift: bool = False  # opponent's Active carries ANY special condition
                                          # (poison/burn/sleep/paralyze/confuse) — gusting it to bench would
                                          # CLEAR it (free cure). Guard suppresses stall-gust so we never rescue a condition. ADR-0022 #10
    active_condition_ko_prizes: int = 0   # prizes from opponent's CURRENT Active dying to poison/burn
                                          # at upcoming Checkup, else 0 — free KO without attacking, so an
                                          # offensive gust must beat THIS too (gusting cures it). ADR-0022 #10
    read: Read | None = None              # per-decision Scouting Read (ADR-0026); None = Posture off
                                          # (no Scout wired / pregame). One Read shared by every option;
                                          # consumed γ-modulated by the snipe threat rank (lever C) — `posture=True` ships.
    posture_confidence: float = 0.0       # γ ∈ [0,1] from the Read (ADR-0026): continuous strength the
                                          # generic-core Posture levers scale by; 0 = unrecognized / no Scout.
    favorability: float = 0.5             # compiled matchup win-rate vs Read's candidate opponents
                                          # (0.5 = neutral / no data) — lever-A aggression signal (ADR-0026).
    matchup_coverage: float = 0.0         # share of Read's posterior that hit a real matchup cell; low
                                          # coverage = favorability mostly the 0.5 default -> trust it less.
    brief: Brief | None = None            # matched hand-authored Matchup Brief for the recognized
                                          # opponent (ADR-0027, covers-routed); None = unrecognized / no
                                          # covering Brief / Posture off. Behavior-neutral: nothing scores off it yet.
    my_discard_basic_energy: dict = field(default_factory=dict)  # {EnergyType: count} of Basic Energy in
                                          # MY open discard — the recover-rider fuel (Aura Jab class)
    active_best_attack_locked: bool = False  # my Active's HIGHEST-damage attack is transient-locked this
                                          # turn (Mega Brave class, ADR-0033) — the swap trigger
    opp_has_stage2: bool = False          # opponent has a Stage 2 in play (CardStat.stage2) — the
                                          # Gravity Mountain tech read
    opp_has_colorless_ability: bool = False  # opponent has a {C} Pokémon WITH an Ability in play —
                                          # the Team Rocket's Watchtower read
    hand_ids: frozenset = field(default_factory=frozenset)  # card ids in MY hand — generic hold/
                                          # sequencing read (e.g. Watchtower waits while Meowth's in hand)
    hand_basic_energy: dict = field(default_factory=dict)  # {EnergyType: count} of Basic Energy in MY
                                          # hand — the last-attachable-F read (Lunar Cycle guard)

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

    def deck_contains_probability(self, card_id: int) -> float:
        """PROBABILISTIC P(my deck still contains `card_id`) ∈ [0,1] — the complement to the SOUND
        `deck_definitely_empty_of` (ADR-0029, `deck_contains_odds` / common/deck_odds.py). Agrees with
        the sound oracle at the extremes (a provably-empty card → 0.0; a pigeonhole-certain or
        prize-resolved card → exactly 1.0) and estimates the uncertain middle. Returns **1.0** when the
        odds are uncomputable (no deck / no deckCount) so a consumer never SUPPRESSES on missing data —
        the conservative "assume present" default."""
        if self.deck_contains_odds is None:
            return 1.0
        return self.deck_contains_odds.get(card_id, 0.0)


@dataclass
class Context:
    """What the Score layer knows about one option — the input a Hypothesis trigger reads."""
    plan: Plan
    select_context: int | None
    option_type: int | None
    card_id: int | None
    option_area: int | None = None  # AreaType of option's target (4=active, 5=bench) — attach targeting
    card_stranded_evolution: bool = False  # this option's card is an evolution that can NEVER be
                                       # deployed from hand in THIS deck: its evolvesFrom chain can't reach a
                                       # Basic on the deck list (Stage-2 opener with no Stage 1). Deck-static; gates `dont-fetch-the-setup-only-opener`.
    params: dict = field(default_factory=dict)  # deck's Strategy.params, passed through so a
                                       # general rule can honor a deck-declared intent (e.g.
                                       # `preferred_start` -> `honor-preferred-start`). Read-only.
    attach_target_area: int | None = None  # for an attach, AreaType of Pokémon receiving the
                                           # Energy (4=active can attack this turn, 5=bench cannot)
    attach_target_roles: list = field(default_factory=list)  # deck Roles of that receiving Pokémon
    attach_target_needs: bool = False  # receiving Pokémon still needs Energy to attack (fewer
                                       # than its cheapest attack cost) — gates "attach to the needy"
    attach_target_under_max: bool = False  # receiving Pokémon carries fewer Energy than its
                                           # HIGHEST-damage attack costs — can't yet fire its big attack
                                           # (1 W can Jetting Blow but not Nebula Beam CCC). Fail-CLOSED (False when unknown).
    attach_target_is_priority_wincon: bool = False  # this attach option puts Energy on the ONE
                                           # win-condition to concentrate on (== board.priority_wincon_slot)
                                           # — most-built buildable wincon. Gates `concentrate-energy-on-wincon` (load one, not spread).
    attach_is_tool_deploy_target: bool = False  # this ATTACH option puts a +HP Tool on the body the
                                           # survival-turns picker chose (== board.tool_deploy_slot) —
                                           # proactive deploy endorsement (`deploy-hp-tool`, ADR-0028)
    attach_feeds_firing_accel: bool = False  # this ATTACH puts Energy on an ACTIVE accelerator
                                           # (`accel_source` Role, e.g. Cinderace) that still NEEDS it to fire
                                           # its accel attack, w/ a bench recipient and no ready wincon to retreat into. Multiplies Energy even if doomed (ep83037962 f70); off if a ready attacker exists (ep83007714 f65).
    attach_target_is_line_member: bool = False  # this attach option's recipient is on a win-condition
                                           # Line (a pre-evolution or the payoff) — building it advances the
                                           # wincon. Read into `OptionTrace.attach_to_needy_line`, the decide()-only tie-break (Line base over off-line opener)
    attach_from_target_needs: bool = False  # at an ATTACH_FROM target-select (engine's pick-a-
                                           # recipient step for a multi-attach effect, e.g. Turbo Flare),
                                           # THIS recipient still NEEDS Energy — spread to the bare body, not an online one. False off ATTACH_FROM (cf attach_target_needs)
    attach_from_target_is_concentrate: bool = False  # at ATTACH_FROM, THIS option's recipient is the Line
                                           # body to concentrate accelerated Energy on (== board.attach_from_
                                           # concentrate_slot) — build ONE body, the counterpart of attach_from_target_needs' spread
    card_is_line_preevo: bool = False  # this option's card is a non-payoff member of a Line's path (a
                                       # pre-evolution that builds toward the win-condition)
    card_is_wincon: bool = False       # this option's card IS the win-condition (a Line payoff /
                                       # win_condition / primary_attacker)
    card_is_starter: bool = False      # this option's card is a startable Basic Pokémon (hp > 0, no
                                       # evolvesFrom) — a body that develops an underdeveloped board
                                       # (`fetch-a-starter` grab rung). Derived off CardStat.
    card_is_support: bool = False      # this option's card is an engine/support Pokémon (hp > 0 with a
                                       # draw/accel/search Ability, see _ENGINE_TAGS) —
                                       # `fetch-the-support` grab rung. Derived off CardStat + tags.
    card_is_top_fetch_priority: bool = False  # this candidate IS deck's highest-priority fetch
                                       # target present (== board.top_fetch_priority_id) — Tier-3
                                       # explicit-list grab override (`fetch-deck-priority`)
    card_is_redundant: bool = False    # this option's card duplicates a Pokémon already in play (its
                                       # need is met) — lowest keep-value, preferred at a forced
                                       # discard (`discard-the-redundant`)
    card_is_hand_duplicate: bool = False  # this option's card is one I hold 2+ copies of in hand (a
                                       # redundant effect card; fungible Energy excluded) — keep-value
                                       # floor `discard-the-hand-duplicate` pitches it before a singleton
    fetch_fills_a_need: bool = False   # this option PLAYS a fetch whose reachable deck set still holds a
                                       # card I currently lack (best grab value > 0, same grab rungs) —
                                       # whether-to-play endorsement (`fetch-when-it-fills-a-need`). False off a non-fetch/need-less fetch
    target_energy: int | None = None  # attack-target snipe signal: Energy on the targeted benched
                                      # Pokémon (None off a Damage/bench-target option)
    target_is_threat: bool = False  # attack target already carries Energy -> closest to attacking
    target_hp: int | None = None    # HP of targeted benched Pokémon (None off a Damage option)
    target_is_weakest: bool = False  # this snipe target has least HP on opponent's Bench
    target_is_strongest_forward: bool = False  # this snipe target's evolution line is the most
                                               # dangerous on the Bench (forward damage greatest, real
                                               # threat) — priority evolving snipe (Riolu→Mega Lucario over Hariyama)
    target_kos: bool = False           # the bench snipe KNOCKS OUT this target (rider >= its HP; bench
                                       # snipes ignore Weakness/Resistance) — a free PRIZE, top snipe
    promote_target_kos: bool = False   # at a TO_ACTIVE promote, benched Pokémon this option brings
                                       # up can KNOCK OUT opp's Active this turn (cheapest attack reaches
                                       # HP) — promote it to take the prize from the front (esp. an accelerator that also loads the bench)
    is_best_promote_target: bool = False  # at a TO_ACTIVE promote OR a SWITCH (my retreat's new-Active
                                       # pick), this option brings up board.best_promote_slot — most-built
                                       # ready wincon. `promote-the-powered-attacker` fires so it's the built Mega, not a bare copy
    card_prize_value: int = 1          # prizes a KO of THIS option's card yields (Mega ex 3 / ex 2
                                       # / else 1) — cost of exposing it; interpose rule promotes a
                                       # body whose value is below the benched wincon's
    promote_target_can_attack: bool = False  # at a TO_ACTIVE promote, benched Pokémon this option
                                       # brings up can use an attack this turn (Energy >= cheapest attack
                                       # cost) — a live attacker to interpose, not a dead wall
    promote_target_hits_weakness: bool = False  # at a TO_ACTIVE promote, this option's body would strike
                                       # opponent's Active on its Weakness (x2 chip) — a favourable
                                       # sacrifice (Cinderace's Fire into a Fire-weak Archaludon/Duraludon)
    target_is_top_threat: bool = False  # this snipe target carries greatest threat rank on the Bench
                                        # (== board.strongest_threat_rank) — biggest (or latent) attacker to
                                        # chip when no KO available. Sees evolved ex/hand-size lines, never picks a SUPPORT body
    target_forward_damage: int | None = None  # Evolving Threat signal (ADR-0020): max damage
                                              # snipe target's evolution line eventually reaches
                                              # (None off a Damage option / no chain / no provider)
    roles: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    stat: object | None = None     # option card's engine CardStat (hp/weakness/prize value/…)
    board: Board = field(default_factory=Board)   # per-decision board summary (same for all options)
    # NOTE: is_attack/tactical/is_ko = documented deck-Hypothesis trigger surface (deck-genie
    # authoring.md); no shipped rule reads them yet — don't prune as dead without updating that doc.
    is_attack: bool = False
    attack_id: int | None = None   # engine attackId of an ATTACK option (None otherwise) — deck rules
                                   # keying an attack-specific condition; prefer stat/tags/board reads
    context_card_id: int | None = None  # the select's OWNER (`select.contextCard`): the card whose effect/
                                   # Ability resolves (an ACTIVATE's bare YES/NO carries no card itself)
    tactical: float = 0.0          # option's closed-form combat value (>= KO_SCORE on a knockout)
    is_ko: bool = False            # this option is an attack that knocks out opponent's Active
    search_targets_exhausted: bool = False  # this option PLAYS a deck-search/tutor whose every legal
                                   # fetch target (see doctrine_fetch._FETCH_FILTERS) is PROVABLY gone from
                                   # deck — so it whiffs. SOUND (Board.deck_empty_ids); False off a search / unknown filter
    search_redundant_wincon: bool = False  # this option PLAYS a tutor that can fetch ONLY the
                                   # win-condition AND wincon already in hand — so it'd only dig a redundant
                                   # copy (Mega Signal with a Mega in hand). False off a search / a tutor that can fetch anything else
    search_targets_unlikely: bool = False  # this option PLAYS a search whose every still-REACHABLE
                                   # fetch target is PROBABLY (not provably) prized — P(deck contains it)
                                   # below whiff threshold (ADR-0029). PROBABILISTIC complement to search_targets_exhausted; mutually exclusive with it.
    search_confirmed_hit: bool = False  # this option PLAYS a search that PROVABLY hits: a fetch target
                                   # certainly still in deck (`Board.deck_definitely_has`, post-anchor) AND filling
                                   # a need (positive grab value). POSITIVE complement of the two whiff signals (ADR-0029); sound-or-silent. Drives `search-the-confirmed-hit`.
    fetch_sheds_junk: bool = False  # this option PLAYS a cost_discard fetch whose 2 predicted sheds
                                   # (top-2 pitch over hand minus the fetch, same discard rungs) BOTH score > 0 — junk cost, dig at the free band (`costly-fetch-sheds-junk`)
    fetch_sheds_live: bool = False  # ...a predicted shed scores < 0 — a live card pays the cost
                                   # (`dont-shed-a-live-card`)
    fetch_sheds_key: bool = False   # ...`keep-key-cards-at-discard` fires on a predicted shed — an
                                   # irreplaceable card is forced into the pitch (`dont-shed-a-key-card`)
    refresh_probable_miss: bool = False  # this option PLAYS a shuffle_hand refresh whose N-card draw
                                   # PROBABLY misses every needed card (post-anchor hypergeometric over the
                                   # shuffle-grown pool, ADR-0024 amendment). Drives `dont-refresh-into-a-probable-miss`.


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
    attach_to_needy_line: bool = False  # this option attaches Energy to a NEEDY win-condition Line body
                                 # (a base that builds the payoff) — decide()-only ORDERING tie-break: among
                                 # EQUAL-score attaches, feed Line base first. W-route-invisible, never enters weight fit. ep82867148 f87


@dataclass
class Decision:
    """A scored decision: the chosen option indices and the per-option OptionTrace."""
    chosen: list
    options: list = field(default_factory=list)
    read: Read | None = None     # the per-decision Scouting Read (ADR-0026), surfaced for legibility
    planned: TurnLine | None = None   # the committed Turn Line this turn (ADR-0031/0037), or None.
                                      # goal "win" = the Lethal Solver's LOCK (the sound top rung;
                                      # telemetry serialises it under the wire-compatible `lethal`
                                      # key); any other goal = a below-win heuristic Goal-Ladder plan
    lethal_refuted: int = 0      # direct lethal candidates the engine backstop REFUTED this plan
                                 # (`lethal_verify`, ADR-0030) — nonzero means closed-form claimed a win
                                 # the engine denied, the exact divergence an A/B or correction wants
    lethal_lost: bool = False    # a locked verified line DIVERGED from the live game and was dropped
                                 # (`lethal_veto`, ADR-0037 stage 3) — sparse telemetry key


class Pilot(PlannerMixin, GustMixin, FetchMixin, ShuffleRefreshMixin, ToolMixin):
    """Composed from the Turn Planner — whose sound top rung IS the Lethal Solver (ADR-0030/0031/0037,
    one entry point) — and four doctrine mixins (gust / fetch / shuffle-refresh / tool) — each
    contributes its closed-form Pilot-side methods; the shared Sense→Plan→Score→Act core is defined
    here. See common/strategy/."""

    def __init__(self, strategy, deck, *, general_strategy=None, overrides=None, stats=None,
                 functions=None, effects=None, attacks=None, attack_costs=None, recoil=None,
                 bench_snipe=None, ignores_active_effects=None, attack_stats=None,
                 search_budget=0, scout=None, briefs=None, posture=True, lethal_verify=False,
                 planner_engine_rank=False, planner_key_threat=False, lethal_family=False,
                 lethal_veto=False):
        self.strategy = strategy
        self.general = general_strategy or Strategy()   # deck-agnostic shared hypotheses (ADR-0008)
        self.overrides = overrides or {}                # machine-written weight overrides, by hyp id
        self.deck = list(deck)
        self.stats = stats
        self.functions = functions
        self.effects = effects                          # CardEffects (ADR-0032 Effect Clauses) —
                                                        # parametric card-tier facts (heal amounts,
                                                        # riders, restrictions); None = clause-blind
        self.attacks = attacks or {}                    # attackId -> printed damage
        self.attack_costs = attack_costs or {}          # attackId -> Energy count (efficiency tiebreak)
        self.recoil = recoil or {}                      # attackId -> unconditional self-damage (ADR-0022 #2)
        self.bench_snipe = bench_snipe or {}            # attackId -> opp-bench snipe rider (ADR-0022 #14)
        self.ignores_active_effects = ignores_active_effects or {}   # attackId -> True if its damage
                                            # ignores EFFECTS on opp's Active (Nebula Beam) — narrow
                                            # pre-compendium signal; LEGACY feed for `_attack_stat`'s synth when attack_stats absent
        self.attack_stats = attack_stats or {}          # attackId -> AttackStat (ADR-0032) — effect
                                                        # record behind damage oracle; when absent the
                                                        # legacy dicts synthesize an equivalent
        self.search_budget = search_budget
        self.scout = scout                              # opponent Scout (ADR-0026); None = Posture off
        self.briefs = list(briefs) if briefs else []    # hand-authored Matchup Briefs (ADR-0027), covers-routed
        self.posture = posture                          # ADR-0026 kill-switch: False forces γ=0 + neutral
                                                        # favorability → both levers off (the A/B baseline)
        self.lethal_verify = lethal_verify              # ADR-0030 kill-switch: engine-confirm a DIRECT
                                                        # lethal lock before trusting it (refute → no lock)
        self.planner_engine_rank = planner_engine_rank  # ADR-0031 kill-switch: engine-sim RANKS the
                                                        # Planner's candidate lines (off = closed-form pick,
                                                        # engine only sharpens the committed line's value)
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
        self._turn_boosts = TurnBoostTracker(            # this-turn flat damage-boost plays (Power Pro
            lambda cid: self.stats.get(cid) if (self.stats and cid is not None) else None)
                                                        # class) — OHKO-line model's play half
        self._fetch_cache: dict = {}                    # memo: fetch-filter tag -> deck ids it can fetch
        self._turn_plan = None                          # ADR-0031 turn-scoped committed plan:
                                                        # (fingerprint, TurnLine|None); re-planned on a reveal
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

    def _evaluate(self, obs: dict) -> Decision:
        select = obs.get("select")
        if select is None:                       # initial deck-submission step
            return Decision(chosen=list(self.deck))
        if not self._planning:                   # ADR-0033: consume the REAL log stream only —
            self._transients.observe(obs)        # engine-sim future must never mutate match state
            self._turn_boosts.observe(obs)
        options = select.get("option") or []
        board = self._board(obs, select)
        traces = [self._option_trace(obs, select, board, o, i) for i, o in enumerate(options)]
        replayed = self.replay_locked_line(obs, select)   # ADR-0037 stage 3: a verified locked line
        if replayed is not None:                          # owns the turn — identity-matched replay,
            chosen, line = replayed                       # any divergence falls through below
            return Decision(chosen=chosen, options=traces, read=board.read, planned=line,
                            lethal_refuted=self._lethal_refutes)
        planned = self.plan_turn(obs, select, board, options, traces)  # ADR-0037: the ONE planning
        refuted = self._lethal_refutes                  # entry — win rung (take the win now) first, then
        if planned is not None:                         # the below-win Goal Ladder. Refutes kept on every
            return Decision(chosen=planned.next_step,   # Decision shape so a lethal_verify drop is countable
                            options=traces, read=board.read, planned=planned,
                            lethal_refuted=refuted, lethal_lost=self._lethal_lost)
        max_count = select.get("maxCount", 0)
        # Primary key = score; secondary key breaks an EXACT tie toward an attach feeding a needy Line
        # body (ep82867148 f87). decide()-only ordering nicety, W-route-invisible, never enters weight fit.
        order = sorted(range(len(options)),
                       key=lambda i: (traces[i].score, traces[i].attach_to_needy_line), reverse=True)
        order = self._finish_turn_last(obs, board, options, traces, order, max_count,
                                       select.get("context"))
        if max_count > 1 and select.get("context") in _GRAB_CONTEXTS:   # greedy gap-update + take-fewer
            chosen = self._greedy_grab(obs, select, board, traces, options,
                                       select.get("minCount", 0), max_count)
        else:
            chosen = order[:max_count]
        return Decision(chosen=chosen, options=traces, read=board.read, lethal_refuted=refuted,
                        lethal_lost=self._lethal_lost)

    def _finish_turn_last(self, obs: dict, board: Board, options: list, traces: list, order: list,
                          max_count: int, select_context: int | None) -> list:
        """Sequence the turn's commitments LAST. The engine re-presents the open turn menu after each
        non-ending action, so the whole turn still happens — which means you should take the most
        informative, reversible actions first and the irreversible ones last:

          tier 0  free informative development — draw / search, fill the Bench, evolve a benched
                  Pokémon, play a Pokémon (and an attach / gust that UNLOCKS a KO — take the win). A
                  GAME-WINNING attack (a KO that takes my last prize) also sits here: when this action
                  wins the match there is nothing to develop FOR, so take it immediately rather than
                  dig/develop first (a non-winning KO still develops-first — the whole point of
                  attack-last is intact; ep83037962 f78).
                  Free, and reveals a better target before you commit.
          tier 1  your one-per-turn SUPPORTER (non-shuffle) — informative (draws / searches / tutors),
                  so commit it AFTER the free Item digs (a Pokégear may upgrade which Supporter you
                  play) but before the blind attach. A KO-enabling gust Supporter stays in tier 0.
          tier 2  the blind / costly COMMITMENTS — the Energy attach, and a discard-COST search
                  (`cost_discard`, e.g. Ultra Ball: pays 2 cards from hand).
          tier 3  a hand-SHUFFLE Supporter (`shuffle_hand`, e.g. Lillie's / Harlequin) — it nukes the
                  hand, so attach your held Energy (tier 2) FIRST, then shuffle the dregs away.
          tier 4  the turn-ENDING attack, plus Retreat / End / non-beneficial options.

        An option is sequenced early only when a Hypothesis endorses it (score > 0). A knockout is
        never forfeited: an Evolve of the Active drops to the last tier when a KO is on the menu, and
        the KO attack outscores everything else there. Stable within a tier (keeps the score order).
        Only at a single-pick MAIN menu; every other context (snipe, search, mulligan) is untouched."""
        if max_count != 1 or len(order) < 2 or select_context != _MAIN:
            return order
        ko_available = any(options[i].get("type") == _ATTACK and traces[i].tactical >= KO_SCORE
                           for i in order)

        def _wins_now(i: int) -> bool:
            """This ATTACK is a KO that takes my LAST prize — it wins the match, so it goes first
            (nothing to develop for). Conservative: the opponent's Active KO for prizes >= mine
            (a snipe-only win falls back to develop-first — no regression, just unoptimised)."""
            if options[i].get("type") != _ATTACK or traces[i].tactical < KO_SCORE:
                return False
            return (board.my_prizes_remaining > 0
                    and self._prize_value(self._opp_active(obs)) >= board.my_prizes_remaining)

        def _cost_discard(i: int) -> bool:
            cid = traces[i].card_id
            return bool(self.functions) and cid is not None and "cost_discard" in self.functions.tags(cid)

        def _is_supporter(i: int) -> bool:
            cid = traces[i].card_id
            st = self.stats.get(cid) if (self.stats and cid is not None) else None
            return bool(st and getattr(st, "cardType", None) == _SUPPORTER)

        def _is_shuffle_refresh(i: int) -> bool:                     # a hand-nuke Supporter (shuffle_hand)
            cid = traces[i].card_id
            return bool(self.functions) and cid is not None and "shuffle_hand" in self.functions.tags(cid)

        def _tier(i: int) -> int:
            o = options[i]
            t = o.get("type")
            if t in (_ATTACH, _PLAY, _RETREAT) and traces[i].tactical >= KO_SCORE:  # a lethal play/attach
                return 0    # unlocks a KO, or a gust/retreat-to-lethal swap — take the win, don't dig first (REQ-GUST-0001)
            if t == _ATTACK and _wins_now(i):                        # a game-winning KO: take the win now,
                return 0                                             # don't dig/develop first (ep83037962 f78)
            if t in (_ATTACK, _END, _RETREAT):                       # turn-ender / swaps the Active
                return 4
            if t == _EVOLVE and o.get("inPlayArea") == _ACTIVE and ko_available:
                return 4                                             # would forfeit an available KO
            if traces[i].score <= 0:                                 # only an endorsed action sequences early
                return 4
            if t == _PLAY and _is_shuffle_refresh(i):                # hand-nuke: AFTER the Energy attach, so
                return 3                                             # held Energy placed before the shuffle
            if t == _PLAY and _is_supporter(i):                      # one-per-turn Supporter: after the
                return 1                                             # free Item digs, before the blind attach
            if t == _ATTACH or (t == _PLAY and _cost_discard(i)):    # blind/costly commitment: after free dev
                return 2
            return 0

        if any(_tier(i) < 4 for i in order):                         # legibility: mark the held-back attacks
            for i in order:
                if options[i].get("type") == _ATTACK and _tier(i) == 4:  # a winning attack (tier 0) not held
                    traces[i].deferred = True
        return sorted(order, key=_tier)                             # stable -> within a tier, score order

    def _option_trace(self, obs: dict, select: dict, board: Board, option: dict,
                      index: int) -> OptionTrace:
        tactical = (self._tactical(obs, board, option)
                    + self._gust_tactical(obs, select, board, option)
                    + self._gust_target_tactical(obs, select, board, option)
                    + self._gust_stall_target_tactical(obs, select, board, option)
                    + self._attach_lethal_tactical(obs, select, board, option)
                    + self._boost_lethal_tactical(obs, select, board, option)
                    + self._retreat_to_lethal_tactical(obs, board, option))
        ctx = self._context(obs, select, board, option, tactical)
        hyps = (*self.general.hypotheses, *self.strategy.hypotheses)
        fired = [(h, self._weight(h)) for h in hyps if _fires(h, ctx)]
        score = sum(w for _, w in fired) + tactical
        return OptionTrace(index=index, score=score, plan=ctx.plan, card_id=ctx.card_id,
                           fired=fired, tactical=tactical,
                           attach_to_needy_line=ctx.attach_target_is_line_member and ctx.attach_target_needs)

    def _weight(self, h) -> float:
        """Effective weight, resolved by id (0 disables): the learned override (tuned.json) over
        the deck's authored seed override (Strategy.weight_overrides, ADR-0035) over the authored
        default. ADR-0008 tunables: shared defaults -> per-deck/machine overrides."""
        if h.id in self.overrides:
            return self.overrides[h.id]
        return self.strategy.weight_overrides.get(h.id, h.weight)

    def _tactical(self, obs: dict, board: Board, option: dict) -> float:
        """Closed-form combat value (Tier-0): printed damage (x2 on Weakness) vs the opponent
        Active's HP. A knockout dominates; otherwise the chip is worth its damage. A bench-snipe rider
        that KNOCKS OUT a benched Pokémon banks a full PRIZE — it is a knockout, scored KO_SCORE-class
        like any other (ADR-0022 #14, ep82749168 f62: a 120+50-snipe that finishes a benched Dreepy
        beats a 210 chip on an un-KO-able Active); a rider that only chips adds a sub-prize tiebreak. A
        game-winning KO whose forced recoil is a SIMULTANEOUS double-KO is a draw, not a win (#2)."""
        if option.get("type") != _ATTACK:
            return 0
        attack_id = option.get("attackId")
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        # Damage oracle (ADR-0032): prevention/W/R pierced by the attack's own ignore flags; a
        # prevented ACTIVE hit (0) no longer hides bench-snipe credit below. Context scores scalers exactly.
        dmg_ctx = self._damage_context(obs)
        dmg = self.predicted_damage(self._my_active_id(obs), attack_id, opp, context=dmg_ctx)
        eff = _EFFICIENCY * self.attack_costs.get(attack_id, 0)   # cheaper of equal outcomes wins
        recover = self._recover_units(attack_id, dmg_ctx, board)  # re-attachable discard fuel (Aura Jab)
        locks = self._lock_cost_applies(attack_id, board)         # burns a cooldown a free attack avoids
        snipe_ko = self._snipe_ko_prizes(board.opp_bench, self._rider_snipe(attack_id))
        if hp and dmg >= hp:
            if self._is_simultaneous_draw(board, attack_id, self._prize_value(opp)):
                return dmg - eff                            # a simultaneous double-KO is a DRAW, not a win
            bonus = snipe_ko or self._bench_snipe_bonus(board, attack_id)  # snipe-KO is a full prize;
            bonus += min(_RECOVER_KO_CAP, _RECOVER_KO * recover)  # sub-prize: the KO that also develops
            bonus -= _LOCK_KO if locks else 0                     # sub-prize: keep the nuke off cooldown
            return KO_SCORE + self._prize_value(opp) - eff + bonus        # else a sub-prize chip tiebreak
        if snipe_ko:                                        # Active survives, but snipe rider KOs a
            return KO_SCORE + snipe_ko - eff                # benched Pokémon — a guaranteed PRIZE this turn
        return (dmg - eff + _ENERGY_RECOVER * recover - (_LOCK_COST if locks else 0)
                - (_RECOIL_DOOM if self._recoil_flips_doom(attack_id, obs, board) else 0))

    def _bench_snipe_bonus(self, board: Board, attack_id) -> float:
        """Sub-prize tiebreak (ADR-0022 #14): an attack that ALSO snipes one of the opponent's Benched
        Pokémon is worth a little extra board value — so among equal-outcome KO attacks the agent prefers
        the one with a useful rider (e.g. Jetting Blow 120 + 50 bench snipe over a 210 overkill). Scaled by
        the rider amount, capped below a prize; 0 when the attack has no clean rider or there's no benched
        target to hit."""
        rider = self._rider_snipe(attack_id)
        if rider <= 0 or not board.opp_bench:
            return 0
        return min(_BENCH_SNIPE_CAP, _BENCH_SNIPE * rider)

    def _snipe_ko_prizes(self, opp_bench, rider: int) -> int:
        """Max prize among the opponent's benched Pokémon a bench-snipe ``rider`` KNOCKS OUT — bench HP
        ``<= rider`` (bench snipes ignore Weakness/Resistance, ADR-0022). A snipe that finishes a benched
        Pokémon banks a PRIZE this turn, so the Tactical layer credits it as a knockout. ``opp_bench`` is
        the ``Board.opp_bench`` ``((cardId, hp), …)`` snapshot. 0 when the rider hits nothing.

        Args:
            opp_bench: the opponent's bench as ``((cardId, hp), …)``.
            rider: the attack's bench-snipe damage.

        Returns:
            The greatest prize value among the benched Pokémon the rider KOs (0 if none).
        """
        if rider <= 0:
            return 0
        return max((self._prize_value({"id": cid}) for cid, hp in opp_bench
                    if hp and hp <= rider and not self._is_tera(cid)),   # Tera: no dmg while benched
                   default=0)

    def _is_tera(self, card_id) -> bool:
        """True if the card is a Tera Pokémon — takes NO damage from attacks while BENCHED (engine
        `CardData.tera`), so no bench-snipe/spread math may ever credit damage against it there.
        Fail-open (False) without stats: a phantom snipe-prize vs Tera could lock a false Lethal."""
        st = self.stats.get(card_id) if (self.stats and card_id is not None) else None
        return bool(getattr(st, "tera", False))

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
        recoil = self._rider_recoil(attack_id)
        if not board.my_active_hp or recoil < board.my_active_hp:   # recoil doesn't self-KO my Active
            return False
        my_prize = self._prize_value({"id": board.my_active_id})
        return my_prize >= op                                # my self-KO gives them their last prize too

    # Gust doctrine's whether-to-play lethal, SWITCH target-select, and Board signals live in
    # doctrine_gust (GustMixin). `_attach_lethal_tactical` below is the general (non-gust) lethal-ATTACH lookahead.
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
        if board.turn <= 1:        # turn 1 going first: can't attack this turn (rules.md §first-turn),
            return 0               # so no attach is lethal — burst would just be discarded
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
            # per-attack oracle (ADR-0032): adjust-then-max, so an ignore-flag attack is seen and a
            # prevented (ex-locked) defender correctly yields 0 — no lethal-attach onto a whiff
            return max((self.predicted_damage(board.my_active_id, aid, opp)
                        for aid in (active_stat.attacks or ())
                        if self.attack_costs.get(aid, 99) <= energy), default=0)

        cur = board.my_active_energy
        if best_affordable(cur) >= opp_hp:                  # already lethal — no attach needed
            return 0
        if best_affordable(cur + provided) >= opp_hp:
            return KO_SCORE + self._prize_value(opp)
        return 0

    def _retreat_to_lethal_tactical(self, obs: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for a RETREAT that brings a READY benched win-condition to the Active
        Spot where its now-affordable attack KOs the opponent's Active THIS turn — the closed-form
        lookahead that lets the agent retreat a spent opener (e.g. a 1-Energy Cinderace) into the
        powered win-condition and TAKE the knockout with the right attacker, instead of chipping it
        away with the spent body. Mirrors `_attach_lethal_tactical` (a develop that unlocks a KO is
        KO-class), so `_finish_turn_last` and the score compare it on the SAME scale as the Active's
        own attack:

          - it returns the BEST KO value an affordable attack of a ready benched wincon reaches
            (KO_SCORE + prize − efficiency + bench-snipe rider), so when that wincon's KO is strictly
            better (a Jetting Blow 120+50-snipe over a plain chip-KO) the retreat outscores the spent
            Active's attack and wins; when the Active's own attack is the better KO it stays ahead.
          - a tiny positioning epsilon breaks an EXACT tie toward the retreat (the wincon ends up
            Active), never overriding a real tactical edge.

        Never forfeits a knockout: it fires ONLY when a benched attacker KOs the current opponent
        Active for a KO STRICTLY BETTER than the one my CURRENT Active can already take (so the prize is
        still taken, by the better attacker). Fires for a SPENT opener Active that can't KO swapping into
        the ready wincon, AND for any Active that CAN'T KO the opponent — e.g. its damage is prevented by
        an Ability (Crustle's ex-lock): retreat into a benched NON-ex attacker (a Cinderace) that can. So
        it stands down whenever my current Active can ALREADY take this KO (or a better one) — just
        attack, don't waste the retreat (and don't strand a fragile body / its own attack), the
        ep82867148 f62 shape: a Cinderace that already KOs must not retreat into an energised Staryu it
        would rather evolve. Also stands down when no benched body KOs, or stats are missing."""
        if option.get("type") != _RETREAT:
            return 0
        opp = self._opp_active(obs)
        if not (opp and opp.get("hp")):
            return 0
        # Best KO the CURRENT Active can already take (0 if not, incl. ex-immune). Retreat is worth it
        # ONLY for a strictly better KO; same prize via a benched body wastes the Active's attack + turn.
        my_active_ko = self._best_affordable_ko_value(
            obs, board, opp, board.my_active_id, board.my_active_energy)
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        best = 0.0
        for p in (me.get("bench") or []):
            if not p:
                continue
            energy = len((p.get("energies") or []))
            best = max(best, self._best_affordable_ko_value(obs, board, opp, p.get("id"), energy))
        if best <= my_active_ko:                         # the Active already takes this KO (or better):
            return 0                                     # just attack — don't waste the retreat
        return best + _RETREAT_POSITION_EPS

    def _best_affordable_ko_value(self, obs: dict, board: Board, opp: dict, attacker_id: int | None,
                                  energy: int, *, bound: str = "exact") -> float:
        """The best KO value `attacker_id` (carrying `energy` Energy) reaches against the opponent's
        Active — KO_SCORE + prize − efficiency + bench-snipe rider, mirroring `_tactical`'s KO branch
        so a hypothetical attacker is valued exactly like the real one. 0 if no affordable attack
        knocks the defender out. The shared KO-valuation behind the retreat lookahead; the Lethal
        Solver's evolve rung passes ``bound="min"`` so a coin-conditional KO never locks a phantom."""
        stat = self.stats.get(attacker_id) if (self.stats and attacker_id is not None) else None
        opp_hp = (opp or {}).get("hp", 0)
        if not (stat and opp_hp):
            return 0.0
        best = 0.0
        for aid in (stat.attacks or ()):
            cost = self.attack_costs.get(aid, 99)
            if cost > energy:                                   # can't afford this attack right now
                continue
            # per-attack oracle (ADR-0032): prevention is attack-scoped now — a benched non-ex (or an
            # ignore-flag attack) still registers its KO against a prevent_ex_damage wall
            dmg = self.predicted_damage(attacker_id, aid, opp, bound=bound)
            if dmg >= opp_hp:
                val = (KO_SCORE + self._prize_value(opp) - _EFFICIENCY * cost
                       + self._bench_snipe_bonus(board, aid))
                best = max(best, val)
        return best

    def _boost_lethal_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for a damage-boost Trainer that UNLOCKS a knockout this turn — the
        executable core of the damage-boost OHKO-line model: playing this Premium Power Pro class
        Item/Supporter (+N this turn, an Item stacks across the copies I hold) or attaching this
        Maximum Belt class Tool (+N while attached, vs an ex Active) lifts my Active's best
        affordable attack over the defender's HP (Mega Brave 270 + Belt 50 = 320 = the Dragapult ex
        OHKO). Mirrors `_attach_lethal_tactical`: Tactical-layer (never a tunable weight), fires
        only when the boost is NECESSARY (no affordable attack already KOs — else just attack) and
        the crossing is exact oracle arithmetic (context-priced, so boosts ALREADY played this turn
        are in the base; each further copy's play re-passes this check on the updated context).
        `_finish_turn_last` then sequences the lethal play tier-0, ahead of the attack it enables.
        Skips a crossing whose forced recoil would be a simultaneous draw. 0 otherwise."""
        t = option.get("type")
        if board.turn <= 1:            # turn 1 going first: can't attack, no boost is lethal
            return 0
        cid = self._option_card_id(obs, select, option)
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if st is None or not getattr(st, "damageBoost", 0):
            return 0
        if t == _PLAY and st.cardType in (1, 3):            # Item stacks; a Supporter is one/turn
            copies = 1 if st.cardType == _SUPPORTER else self._hand_count_of(obs, cid)
        elif (t == _ATTACH and st.cardType == 2
              and option.get("inPlayArea") == _ACTIVE):     # a boost Tool onto my attacker
            copies = 1
        else:
            return 0
        opp = self._opp_active(obs)
        opp_hp = (opp or {}).get("hp", 0)
        active = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        if not (active and opp and opp_hp):
            return 0
        if st.damageBoostType is not None and active.energyType != st.damageBoostType:
            return 0                                        # "your {F} Pokémon" — attacker-type gate
        opp_stat = self.stats.get(opp.get("id")) if self.stats else None
        if st.damageBoostVsEx and not (opp_stat and (opp_stat.ex or opp_stat.megaEx)):
            return 0                                        # "{ex}" defender gate (incl. Mega ex)
        ctx = self._damage_context(obs)
        for aid in (active.attacks or ()):
            cost = self.attack_costs.get(aid, 99)
            if cost > board.my_active_energy:
                continue
            dmg = self.predicted_damage(board.my_active_id, aid, opp, context=ctx)
            if dmg >= opp_hp:
                return 0                                    # an affordable KO already exists — just attack
        best = 0.0
        for aid in (active.attacks or ()):
            cost = self.attack_costs.get(aid, 99)
            if cost > board.my_active_energy:
                continue
            dmg = self.predicted_damage(board.my_active_id, aid, opp, context=ctx)
            if dmg <= 0:                                    # a boost never lifts a does-nothing attack
                continue
            if (dmg + st.damageBoost * copies >= opp_hp
                    and not self._is_simultaneous_draw(board, aid, self._prize_value(opp))):
                best = max(best, KO_SCORE + self._prize_value(opp) - _EFFICIENCY * cost)
        return best

    def _hand_count_of(self, obs: dict, card_id) -> int:
        """Copies of `card_id` in MY hand (the stacking read for a Power-Pro-class crossing)."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        return sum(1 for c in (me.get("hand") or []) if c and c.get("id") == card_id)

    def _prize_value(self, poke: dict | None) -> int:
        """Prizes a knockout yields — Mega ex 3, ex 2, else 1 (read off the engine CardStat)."""
        stat = self.stats.get((poke or {}).get("id")) if self.stats else None
        if stat and stat.megaEx:
            return 3
        if stat and stat.ex:
            return 2
        return 1

    def _attack_stat(self, attack_id):
        """The attack's ``AttackStat`` (ADR-0032), or a synth from the legacy per-mechanic dicts when
        the table isn't wired — reproducing pre-oracle behavior (the narrow ``ignores_active_effects``
        feed maps onto ``ignoresEffects``, so a legacy-wired Pilot still pierces Crustle with Nebula
        Beam). None for an unknown attack (no record, no damage)."""
        st = self.attack_stats.get(attack_id)
        if st is not None:
            return st
        if attack_id not in self.attacks:
            return None
        from common.scouting.provider import AttackStat
        return AttackStat(attackId=attack_id, damage=self.attacks.get(attack_id, 0),
                          cost=self.attack_costs.get(attack_id, 0),
                          recoil=self.recoil.get(attack_id, 0),
                          benchSnipe=self.bench_snipe.get(attack_id, 0),
                          ignoresEffects=bool(self.ignores_active_effects.get(attack_id)))

    def _stranded_evolution_set(self) -> frozenset:
        """Deck card ids that can NEVER be deployed from hand in this deck: evolutions whose
        previous-stage chain (`CardStat.evolvesFrom` names, walked to full depth) can't reach a
        Basic using only cards on the deck list — e.g. a Stage-2 Explosiveness opener with no
        Stage 1 in the deck (Cinderace without Raboot): in hand it is a dead card. Deck-static,
        so computed once; empty without a stats provider (fail-open — no card is called dead
        on unknown facts)."""
        cached = getattr(self, "_stranded_cache", None)
        if cached is not None:
            return cached
        stats = {cid: self.stats.get(cid) for cid in set(self.deck)} if self.stats else {}
        by_name = {st.name: st for st in stats.values() if st and st.name}

        def deployable(st, seen=()) -> bool:
            if st is None or not st.evolvesFrom:      # unknown facts fail-open; a Basic grounds out
                return True
            if st.evolvesFrom in seen:                # a name cycle can't ground out in a Basic
                return False
            prev = by_name.get(st.evolvesFrom)
            return prev is not None and deployable(prev, (*seen, st.evolvesFrom))

        self._stranded_cache = frozenset(
            cid for cid, st in stats.items() if st and st.evolvesFrom and not deployable(st))
        return self._stranded_cache

    def _rider_snipe(self, attack_id) -> int:
        """The attack's unconditional bench-snipe rider — read off the ONE attack record
        (`_attack_stat`), so `AttackStat` is the single source and the legacy `bench_snipe` dict
        only feeds the synth fallback."""
        st = self._attack_stat(attack_id)
        return st.benchSnipe if st else 0

    def _rider_recoil(self, attack_id) -> int:
        """The attack's unconditional self-damage — single-sourced like `_rider_snipe`."""
        st = self._attack_stat(attack_id)
        return st.recoil if st else 0

    def _recover_units(self, attack_id, dmg_ctx: dict, board: Board) -> int:
        """Energy this attack's recover rider would actually re-attach from my discard — the
        development the Tactical layer credits (Aura Jab: attack + accelerate). min(recoverN, the
        matching Basic-Energy fuel in my open discard), 0 when the rider's target scope has no
        recipient (a bench-targeted recover with an empty Bench attaches nothing). Fuel comes off
        the already-built damage context (`atk_discard_basic_by_type`), so the count is the same
        one the discard-scaler oracle prices."""
        st = self._attack_stat(attack_id)
        if not st or not getattr(st, "recoverN", 0):
            return 0
        if st.recoverTarget == "bench" and not board.my_bench:
            return 0
        by_type = dmg_ctx.get("atk_discard_basic_by_type") or {}
        fuel = (by_type.get(st.recoverEnergyType, 0) if st.recoverEnergyType is not None
                else sum(by_type.values()))
        return min(st.recoverN, fuel)

    def _board_has_stage2(self, player: dict | None) -> bool:
        """True when this player has a Stage 2 Pokémon in play (`CardStat.stage2`) — the Gravity
        Mountain tech read (its −30 HP hits exactly Stage 2s, both sides)."""
        if not (self.stats and player):
            return False
        for p in ((player.get("active") or []) + (player.get("bench") or [])):
            st = self.stats.get((p or {}).get("id")) if p else None
            if st is not None and getattr(st, "stage2", False):
                return True
        return False

    def _board_has_colorless_ability(self, player: dict | None) -> bool:
        """True when this player has a Colorless Pokémon WITH an Ability in play — the Team Rocket's
        Watchtower read ({C} Pokémon lose their Abilities under it, both sides)."""
        if not (self.stats and player):
            return False
        for p in ((player.get("active") or []) + (player.get("bench") or [])):
            st = self.stats.get((p or {}).get("id")) if p else None
            if (st is not None and st.hp > 0 and st.energyType == 0
                    and getattr(st, "hasAbility", False)):
                return True
        return False

    def _hand_basic_energy(self, hand: list) -> dict:
        """{EnergyType: count} of Basic Energy cards in my hand — the last-attachable-Energy read
        (`CardStat.cardType` BASIC_ENERGY=5, mirroring `_discard_energy_counts`)."""
        counts: dict = {}
        for c in hand:
            st = self.stats.get((c or {}).get("id")) if (self.stats and c) else None
            if st is not None and getattr(st, "cardType", None) == 5 and st.energyType is not None:
                counts[st.energyType] = counts.get(st.energyType, 0) + 1
        return counts

    def _recoil_flips_doom(self, attack_id, obs: dict, board: Board) -> bool:
        """True when this NON-KO attack's unconditional recoil turns my currently-SAFE Active into a
        free KO for the opponent — outright self-KO (recoil >= my HP on a chip attack), or the
        post-recoil HP falls inside their next-turn reach (`_active_doomed` re-asked at hp−recoil).
        The Wild-Press survival guard: 210 self-70 is fine as a prize trade (the KO branch is never
        charged) but not as a chip that leaves an 80-HP Psychic-weak body for nothing. Stands down
        when the Active is ALREADY doomed — chipping big before it dies is right."""
        recoil = self._rider_recoil(attack_id)
        hp = board.my_active_hp
        if recoil <= 0 or not hp or board.active_doomed:
            return False
        if recoil >= hp:                                   # a non-KO suicide: a free body, no prize
            return True
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        ma = next((p for p in (me.get("active") or []) if p), None)
        oa = next((p for p in (opp.get("active") or []) if p), None)
        if not ma:
            return False
        return bool(self._active_doomed(dict(ma, hp=hp - recoil), oa, opp))

    def _active_best_attack_locked(self, ma: dict | None) -> bool:
        """True when my Active's HIGHEST-damage attack is transient-locked this turn — it used a
        "can't use <this attack> next turn" attack last turn (Mega Brave class; a blanket self-lock
        counts too). Read off the ADR-0033 tracker, serial-gated: a body that left the Active carries
        a new serial, so the grant expires with the swap — which is exactly why swapping in a fresh
        benched copy (`swap-out-the-locked-attacker`) restores the attack."""
        grant = self._transients.grant_for_serial((ma or {}).get("serial"))
        if not grant:
            return False
        if grant.get("self_lock"):
            return True
        same = grant.get("same_lock")
        if same is None:
            return False
        stat = self.stats.get((ma or {}).get("id")) if self.stats else None
        aids = getattr(stat, "attacks", None) or ()
        if not aids:
            return False
        best = max(aids, key=lambda aid: self.attacks.get(aid, 0))
        return same == best

    def _lock_cost_applies(self, attack_id, board: Board) -> bool:
        """True when this attack locks itself (or all attacks) for my next turn AND my Active could
        have used a lock-free affordable attack instead — the flexibility cost of burning a cooldown
        (Mega Brave: next turn it can't nuke, exactly when the next body arrives). Never True when
        it's the Active's only affordable attack: attacking still beats passing (a lock charge must
        never push the lone chip below END). Closed-form off the attack table + current Energy."""
        st = self._attack_stat(attack_id)
        if not st or not (getattr(st, "nextTurnSelfLock", False)
                          or getattr(st, "nextTurnSameAttackLock", False)):
            return False
        active = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        for aid in (getattr(active, "attacks", None) or ()):
            if aid == attack_id or self.attack_costs.get(aid, 99) > board.my_active_energy:
                continue
            alt = self._attack_stat(aid)
            if alt and not (alt.nextTurnSelfLock or alt.nextTurnSameAttackLock):
                return True                                  # a lock-free attack was affordable
        return False

    def _damage_context(self, obs: dict, *, attacker_is_me: bool = True) -> dict:
        """Visible-state counts for the oracle's scaling term (ADR-0032 Damage Formula),
        ATTACKER-relative: ``attacker_is_me=True`` prices MY attack this decision;
        ``False`` mirrors every key for the opponent-as-attacker (the Incoming direction —
        their hand/bench/Active-Energy AND their discard, all open information). Includes the
        attacker's discard Energy histograms (Riptide-class scalers)."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        atk, dfn = (me, opp) if attacker_is_me else (opp, me)
        aa = next((p for p in (atk.get("active") or []) if p), None)
        da = next((p for p in (dfn.get("active") or []) if p), None)
        total, by_type = self._discard_energy_counts(atk.get("discard") or [])
        bench_names = tuple(                                    # bench-partner conditions (Cosmic
            (self.stats.get(b.get("id")).name if self.stats and self.stats.get(b.get("id")) else "")
            for b in (atk.get("bench") or []) if b)             # Beam needs Lunatone benched)
        # flat damage-boosts live for the attacker's attacks: this-turn Trainer plays (tracker) +
        # Tools ATTACHED to the attacking Active (visible board state; Maximum Belt). Both open
        # information in either direction — the opponent's Power Pro play and their Belt are as
        # visible as mine, so Incoming prices them too.
        side = yi if attacker_is_me else 1 - yi
        boosts = list(self._turn_boosts.boosts_for(side))
        for tool in ((aa or {}).get("tools") or []):
            t_stat = self.stats.get((tool or {}).get("id")) if self.stats else None
            if t_stat is not None and getattr(t_stat, "damageBoost", 0):
                boosts.append((t_stat.damageBoost, t_stat.damageBoostType, t_stat.damageBoostVsEx))
        def _counters(p):
            return max(0, ((p or {}).get("maxHp", 0) or 0) - ((p or {}).get("hp", 0) or 0)) // 10

        def _taken(player):
            prize = player.get("prize")
            return max(0, 6 - len(prize)) if prize is not None else 0

        ctx = {"atk_hand": atk.get("handCount", len(atk.get("hand") or [])),
               "def_hand": dfn.get("handCount", len(dfn.get("hand") or [])),
               "def_active_energy": len((da or {}).get("energies") or []),
               "atk_active_energy": len((aa or {}).get("energies") or []),
               "atk_bench": sum(1 for p in (atk.get("bench") or []) if p),
               "def_bench": sum(1 for p in (dfn.get("bench") or []) if p),
               "atk_discard_energy_total": total,
               "atk_discard_basic_by_type": by_type,
               "atk_bench_names": bench_names,
               "atk_boosts": tuple(boosts),
               "atk_self_counters": _counters(aa),      # damage counters on attacking Active
               "def_counters": _counters(da),           # ... and on defending Active
               "atk_prizes_taken": _taken(atk),         # prizes each side taken (6 - remaining)
               "def_prizes_taken": _taken(dfn)}
        if attacker_is_me:
            # exact deck facts for hidden deck-discard scalers (only MY deck can be exact —
            # tracker-anchored): oracle turns them into a pigeonhole floor / hypergeometric EV
            known = self._deck_known_counts(atk, obs.get("own_prizes")
                                            and {int(k): v for k, v in obs["own_prizes"].items()})
            if known:
                deck_by_type: dict = {}
                for cid, n in known.items():
                    st = self.stats.get(cid) if self.stats else None
                    if getattr(st, "cardType", None) == 5 and st.energyType is not None:
                        deck_by_type[st.energyType] = deck_by_type.get(st.energyType, 0) + n
                ctx["atk_deck_count"] = sum(known.values())
                ctx["atk_deck_basic_by_type"] = deck_by_type
        return ctx

    def _discard_energy_counts(self, discard: list) -> tuple[int, dict]:
        """Energy histograms of a (fully visible) discard pile: ``(all Energy cards,
        {energyType: Basic-Energy count})`` — the units behind the Riptide-class discard scalers.
        Resolved via CardStat.cardType (BASIC_ENERGY=5, SPECIAL_ENERGY=6); unknown cards count 0."""
        total, by_type = 0, {}
        for c in discard:
            cid = (c or {}).get("id")
            st = self.stats.get(cid) if (self.stats and cid is not None) else None
            ct = getattr(st, "cardType", None)
            if ct in (5, 6):                              # any Energy card
                total += 1
            if ct == 5 and st.energyType is not None:     # Basic Energy, by type
                by_type[st.energyType] = by_type.get(st.energyType, 0) + 1
        return total, by_type

    def predicted_damage(self, attacker_id: int | None, attack_id, defender: dict | None, *,
                         bound: str = "exact", context: dict | None = None) -> float:
        """The damage oracle (ADR-0032 E1): damage `attack_id` deals to the defending Active —
        the ONE closed-form path every Tier-0 damage estimate routes through. Resolves ids to
        stats/tags, then delegates to the pure ``compute_active_damage`` (the unit the engine
        audit diffs). Honors the attack's ignore flags: Nebula Beam lands 210 through Crustle's
        ex-prevention; Jetting Blow is zeroed (its bench rider is a separate path). ``bound``
        picks a conditional attack's floor/ceiling/printed — Lethal reads "min", Incoming "max"."""
        from common.strategy.damage import compute_active_damage
        d_id = (defender or {}).get("id")
        return compute_active_damage(
            self._attack_stat(attack_id),
            self.stats.get(attacker_id) if (self.stats and attacker_id is not None) else None,
            self.stats.get(d_id) if (self.stats and d_id is not None) else None,
            frozenset(self.functions.tags(d_id)) if (self.functions and d_id is not None) else frozenset(),
            bound=bound, context=context,
            # a live transient shield on the defending BODY (ADR-0033, serial-gated: a body that
            # left the Active presents a new serial, never matches a stale grant)
            defender_transient=self._transients.grant_for_serial((defender or {}).get("serial")))

    def _predicted_max_damage(self, attacker_stat, defender: dict | None, *,
                              exclude_attack=None) -> float:
        """The worst damage `attacker_stat`'s attacks deal to `defender` — max over the per-attack
        oracle when EVERY attack's record resolves (so a partially-known table never SHRINKS a
        worst-case), else the legacy card-level ``maxDamage`` × W/R. The shared magnitude behind
        every Incoming estimate (ADR-0032): per-attack, so an opponent's ignore-flag attack is
        priced full vs my resist body, my prevent_ex_damage wall fears only what pierces it, and
        their SCALERS price off the per-decision opponent context (`_opp_attack_context`, set by
        `_board`) — hand size, bench, attached Energy, and their open discard (Riptide-exact)."""
        if not attacker_stat:
            return 0
        aids = tuple(a for a in (attacker_stat.attacks or ()) if a != exclude_attack)
        if aids and all(self._attack_stat(a) is not None for a in aids):
            # bound="max": Incoming is the WORST case — a coin/conditional attack threatens its
            # ceiling ("If heads, +20" counts the 20), so survival math never under-plans
            ctx = getattr(self, "_opp_attack_context", None)
            return max(self.predicted_damage(attacker_stat.cardId, a, defender, bound="max",
                                             context=ctx)
                       for a in aids)
        d_stat = (self.stats.get((defender or {}).get("id"))
                  if (self.stats and (defender or {}).get("id") is not None) else None)
        return self._wr_adjusted(attacker_stat, d_stat, attacker_stat.maxDamage or 0)

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
        card_is_hand_duplicate = cid is not None and cid in board.hand_duplicate_ids
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
        target_kos = bool(board.snipe_damage and target_hp and board.snipe_damage >= target_hp)
        target_rank = self._target_threat_rank(obs, select, option, board.read, board.posture_confidence)
        target_is_top_threat = (target_rank is not None and target_rank > 0
                                and board.strongest_threat_rank > 0
                                and target_rank == board.strongest_threat_rank)
        promote_target_kos = (select.get("context") == _TO_ACTIVE
                              and self._promote_target_kos(obs, select, option))
        is_best_promote_target = (
            select.get("context") in (_TO_ACTIVE, _SWITCH) and board.best_promote_slot is not None
            and option.get("playerIndex", state.get("yourIndex", 0)) == state.get("yourIndex", 0)
            and (option.get("area"), option.get("index")) == board.best_promote_slot)
        card_prize_value = self._prize_value({"id": cid}) if cid is not None else 1
        promote_target_can_attack = self._promote_target_can_attack(obs, select, option)
        promote_target_hits_weakness = self._promote_target_hits_weakness(obs, select, option)
        at_target = self._attach_target(obs, option)   # Pokémon an attach option puts Energy on
        at_roles = self.strategy.roles.get(at_target.get("id"), []) if at_target else []
        at_is_line_member = bool(
            at_target and at_target.get("id") in (self._line_preevo_set() | self._wincon_set()))
        attach_target_is_priority_wincon = (
            option.get("type") == _ATTACH and board.priority_wincon_slot is not None
            and (option.get("inPlayArea"), option.get("inPlayIndex")) == board.priority_wincon_slot)
        attach_is_tool_deploy_target = (
            option.get("type") == _ATTACH and board.tool_deploy_slot is not None
            and "tool" in tags and getattr(stat, "hpBonus", 0) > 0
            and (option.get("inPlayArea"), option.get("inPlayIndex")) == board.tool_deploy_slot)
        attach_feeds_firing_accel = (
            option.get("type") == _ATTACH and option.get("inPlayArea") == _ACTIVE
            and "accel_source" in at_roles and self._attach_target_needs(at_target)
            and not board.accel_recipient_missing and not board.bench_wincon_ready)
        search_exhausted, redundant_wincon = self._search_signals(option, tags, board)
        search_unlikely = self._search_probable_whiff(option, tags, board)
        search_confirmed = self._search_confirmed_hit(option, tags, board, plan)
        sheds_junk, sheds_live, sheds_key = self._shed_signals(obs, option, tags, board, plan)
        refresh_miss = self._refresh_probable_miss(option, cid, tags, board, obs, plan)
        attach_from_needs = self._attach_from_target_needs(obs, select, option)
        attach_from_concentrate = (select.get("context") == _ATTACH_FROM
                                   and board.attach_from_concentrate_slot is not None
                                   and (option.get("area"), option.get("index"))
                                   == board.attach_from_concentrate_slot)   # ATTACH_FROM encodes
                                   # recipient in area/index (not inPlayArea/inPlayIndex — cf _option_pokemon)
        return Context(plan=plan, select_context=select.get("context"),
                       option_type=option.get("type"), card_id=cid, option_area=option.get("area"),
                       attach_target_area=option.get("inPlayArea"), attach_target_roles=at_roles,
                       attach_target_needs=self._attach_target_needs(at_target),
                       attach_target_under_max=self._attach_target_under_max(at_target),
                       attach_target_is_priority_wincon=attach_target_is_priority_wincon,
                       attach_is_tool_deploy_target=attach_is_tool_deploy_target,
                       attach_feeds_firing_accel=attach_feeds_firing_accel,
                       attach_target_is_line_member=at_is_line_member,
                       attach_from_target_needs=attach_from_needs,
                       attach_from_target_is_concentrate=attach_from_concentrate,
                       card_is_line_preevo=card_is_line_preevo, card_is_wincon=card_is_wincon,
                       card_is_starter=card_is_starter, card_is_support=card_is_support,
                       card_is_top_fetch_priority=card_is_top_fetch_priority,
                       card_is_redundant=card_is_redundant,
                       card_is_hand_duplicate=card_is_hand_duplicate,
                       fetch_fills_a_need=fetch_fills_a_need,
                       target_energy=target_energy, target_is_threat=bool(target_energy),
                       target_hp=target_hp, target_is_weakest=target_is_weakest,
                       target_is_strongest_forward=target_is_strongest_forward,
                       target_forward_damage=target_forward_damage,
                       target_kos=target_kos, target_is_top_threat=target_is_top_threat,
                       promote_target_kos=promote_target_kos,
                       is_best_promote_target=is_best_promote_target,
                       card_prize_value=card_prize_value,
                       promote_target_can_attack=promote_target_can_attack,
                       promote_target_hits_weakness=promote_target_hits_weakness,
                       card_stranded_evolution=(cid is not None
                                                and cid in self._stranded_evolution_set()),
                       roles=roles, tags=tags, stat=stat, board=board, params=self.strategy.params,
                       is_attack=is_attack,
                       attack_id=(option.get("attackId") if is_attack else None),
                       context_card_id=((select.get("contextCard") or {}).get("id")),
                       tactical=tactical, is_ko=is_attack and tactical >= KO_SCORE,
                       search_targets_exhausted=search_exhausted,
                       search_redundant_wincon=redundant_wincon,
                       search_targets_unlikely=search_unlikely,
                       search_confirmed_hit=search_confirmed,
                       fetch_sheds_junk=sheds_junk, fetch_sheds_live=sheds_live,
                       fetch_sheds_key=sheds_key, refresh_probable_miss=refresh_miss)

    # Fetch doctrine's comparator/oracle, deck-knowledge whiff/redundant signals, whether-to-play
    # lookahead, and greedy multi-pick live in doctrine_fetch (FetchMixin).
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

    def _attach_from_target_needs(self, obs: dict, select: dict, option: dict) -> bool:
        """At an ATTACH_FROM target-select (the engine's recipient-pick step for a multi-attach
        effect — e.g. Turbo Flare's 'attach a Basic Energy to a Benched Pokémon'), True if the
        Pokémon THIS option would put the Energy on still needs Energy to attack (carries fewer than
        its cheapest attack cost). The mirror of `_attach_target_needs` for the target-pick context,
        so the agent spreads a forced/searched attach to a bare body instead of an already-online one.

        Fail-CLOSED: False off an ATTACH_FROM select or when the recipient can't be resolved — only
        a positively-needy recipient is endorsed, so an unknown target never steals the attach."""
        if select.get("context") != _ATTACH_FROM:
            return False
        poke = self._option_pokemon(obs, select, option)
        if not poke:
            return False
        return len((poke.get("energies") or [])) < _min_attack_cost(self.stats, poke.get("id"))

    def _attach_from_concentrate_slot(self, me: dict) -> tuple | None:
        """(AreaType, index) of the win-condition-Line body to CONCENTRATE accelerated Energy on at an
        ATTACH_FROM (Turbo Flare recipient) select — among my in-play Line members (`_line_member_set`:
        Staryu AND Mega Starmie ex) still short of the payoff's biggest-attack cost, the one ALREADY
        carrying the most Energy, so the deck loads ONE body toward the Mega payoff (Nebula Beam, 3
        Energy) instead of dribbling one Energy onto each bare Staryu (`spread-attach-to-the-needy`
        reads a 1-Energy Staryu as 'done' because it clears Staryu's OWN 1-cost attack — the wrong
        frame for a Line whose real payoff is the evolved Mega). A body at/over the payoff cost is
        skipped (don't over-stack a ready attacker). None when no buildable Line body exists (ep83116081
        f21). Deterministic: most-Energy wins, index breaks a tie."""
        members = self._line_member_set()
        if not members:
            return None
        wincon = self._wincon_set()
        payoff_cost = 0
        for line in self.strategy.lines:                  # how much Energy the built body ultimately wants
            st = self.stats.get(line.payoff) if self.stats else None
            payoff_cost = max(payoff_cost, (getattr(st, "maxDamageCost", 0) or 0) if st else 0)
        best = None                                       # ((is_wincon, energy), area, index)
        for area, bodies in ((_ACTIVE, me.get("active") or []), (_BENCH, me.get("bench") or [])):
            for i, p in enumerate(bodies):
                if not p or p.get("id") not in members:
                    continue
                e = len((p.get("energies") or []))
                if payoff_cost and e >= payoff_cost:      # already at payoff cost — don't over-stack it
                    continue
                # prefer the EVOLVED win-condition (actual attacker, no evolution step) over a
                # pre-evolution, then the one carrying most Energy (ep83007714 f22 wants the Mega).
                rank = (p.get("id") in wincon, e)
                if best is None or rank > best[0]:
                    best = (rank, area, i)
        return (best[1], best[2]) if best else None

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
        # OPPONENT-as-attacker context, cached per decision (ADR-0032 P1): Incoming estimates price
        # their scalers off THEIR visible state — hand/bench/Energy/discard (opp Kyogre's Riptide is exact)
        self._opp_attack_context = self._damage_context(obs, attacker_is_me=False)
        prizes = obs.get("own_prizes")             # exact prize multiset from deck-tracker, or None
        if prizes:                                 # keys are card ids: coerce str->int so a JSON-captured
            prizes = {int(k): v for k, v in prizes.items()}   # obs (a Correction) matches the int decklist

        deck_empty = self._deck_empty_ids(me, prizes)
        deck_known = self._deck_known_counts(me, prizes)
        deck_odds_map = self._deck_contains_prob(me, deck_known)   # probabilistic complement (ADR-0029)
        read = self.scout.observe(obs) if self.scout else None   # the Read (M2.0); γ/favorability derive from it
        gamma = _posture_gamma(read) if self.posture else 0.0    # γ threads into snipe rank; kill-switch zeroes it
        my_arch = self.strategy.params.get("my_archetype")
        fav, cov = (matchup_favorability(self.scout.artifact, my_arch, read.candidates)
                    if (self.posture and self.scout and read and my_arch) else (0.5, 0.0))
        # covers-routed (ADR-0027), γ-gated to a RECOGNIZED opponent: on an empty early board the Read's
        # top candidate is just the prior favourite -> gate on γ>0 to keep board.brief off until recognized.
        brief = match_brief(self.briefs, read) if (self.posture and read and gamma > 0) else None
        active_doomed = self._active_doomed(ma, oa, opp)
        active_lethal = self._active_cheap_attack_kos(ma, oa)   # its turn is done — build the successor
        board = Board(
            my_bench=sum(1 for b in (me.get("bench") or []) if b),
            my_active_id=(ma or {}).get("id"),
            my_active_energy=len((ma or {}).get("energies") or []),
            my_active_hp=(ma or {}).get("hp", 0),
            opp_bench=tuple((b.get("id"), b.get("hp", 0)) for b in (opp.get("bench") or []) if b),
            turn=state.get("turn", 0),
            energy_attached=bool(state.get("energyAttached")),
            hand_startable=self._hand_startable(me.get("hand") or []),
            active_doomed=active_doomed,
            incoming_active_damage=self._incoming_active_damage(ma, oa),
            active_cheap_attack_kos=active_lethal,
            active_can_ko=self._active_can_ko(ma, oa),
            active_maxed_kos=self._active_maxed_kos(ma, oa),
            gust_best_ko_prizes=self._gust_best_ko_prizes(ma, opp),
            active_ko_prizes=self._active_ko_prizes(ma, oa),
            my_prizes_remaining=len(me.get("prize") or []),
            opp_prizes_remaining=len(opp.get("prize") or []),
            reusable_energy_in_hand=self._has_reusable_energy(me.get("hand") or []),
            energy_placeable=self._energy_placeable(me),
            wincon_in_play=self._wincon_in_play(me),
            wincon_in_hand=self._wincon_in_hand(me),
            line_preevo_in_play=self._line_preevo_in_play(me),
            wincon_base_deployable=(self._line_preevo_in_play(me)
                                    or self._line_preevo_in_hand(me)),
            accel_recipient_missing=self._accel_recipient_missing(me),
            support_in_play=self._support_in_play(me),
            in_play_ids=frozenset(p.get("id") for p in ((me.get("active") or []) + (me.get("bench") or []))
                                  if p and p.get("id") is not None),
            hand_duplicate_ids=self._hand_duplicate_ids(me),
            top_fetch_priority_id=self._top_fetch_priority_id(select),
            weakest_bench_hp=self._weakest_snipe_hp(obs, select),
            strongest_forward_bench=self._strongest_forward_snipe(obs, select),
            bench_threat_present=self._bench_threat_present(obs, select),
            snipe_damage=self._snipe_damage(obs, (ma or {}).get("id"), select),
            strongest_threat_rank=self._strongest_threat_rank(obs, select, read, gamma),
            bench_wincon_ready=self._bench_wincon_ready(me),
            best_promote_slot=self._best_promote_slot(me),
            evolve_to_ready_wincon_available=self._evolve_to_ready_wincon_available(me),
            bench_wincon_prize_value=self._bench_wincon_prize_value(me),
            bench_wincon_underpowered=self._bench_wincon_underpowered(me),
            basic_energy_in_deck=self._basic_energy_in_deck(deck_empty),
            my_discard_basic_energy=self._discard_energy_counts(me.get("discard") or [])[1],
            active_best_attack_locked=self._active_best_attack_locked(ma),
            opp_has_stage2=self._board_has_stage2(opp),
            opp_has_colorless_ability=self._board_has_colorless_ability(opp),
            hand_ids=frozenset(c.get("id") for c in (me.get("hand") or [])
                               if c and c.get("id") is not None),
            hand_basic_energy=self._hand_basic_energy(me.get("hand") or []),
            opp_has_played_gust=self._opp_has_played_gust(opp),
            active_is_wincon=bool(ma) and ma.get("id") in self._wincon_set(),
            priority_wincon_slot=self._priority_wincon_slot(
                me, active_lethal, active_doomed),
            attach_from_concentrate_slot=self._attach_from_concentrate_slot(me),
            stall_target_exists=self._stall_target_exists(opp),
            stall_target_is_keystone=self._stall_target_is_keystone(opp),
            opp_has_energy_in_play=self._opp_has_energy_in_play(opp),
            opp_active_has_energy=bool(oa and (oa.get("energies") or [])),
            opp_has_hand_size_attacker=self._opp_has_hand_size_attacker(opp),
            deck_empty_ids=deck_empty,
            deck_known_counts=deck_known,
            deck_contains_odds=deck_odds_map,
            opp_active_condition_gift=self._opp_active_condition_gift(opp),
            active_condition_ko_prizes=self._active_condition_ko_prizes(opp, oa),
            read=read,                                              # Posture Read (ADR-0026); None = off
            posture_confidence=gamma,                               # γ ∈ [0,1] the levers scale by
            favorability=fav, matchup_coverage=cov,                 # lever-A signal + its reliability
            brief=brief,                                            # matched Matchup Brief (ADR-0027); None = off
        )
        if self._tool_in_hand(me):                      # Tool doctrine signals (ADR-0028) — only when a
            board = replace(board,                      # Tool is in hand (common case pays nothing)
                            tool_deploy_slot=self._tool_deploy_slot(obs, me, board),
                            irreplaceable_tool_in_hand=self._irreplaceable_tool_in_hand(me))
        return board

    # Shuffle-Refresh doctrine's signals live in doctrine_shuffle_refresh (ShuffleRefreshMixin); `_board` calls them.

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

    def _line_preevo_in_hand(self, me: dict) -> bool:
        """True if a Line pre-evolution (a base to evolve the payoff from) is in my hand — so I can
        bench it and deploy the payoff. The hand-side companion of `_line_preevo_in_play`."""
        preevos = self._line_preevo_set()
        if not preevos:
            return False
        return any(c and c.get("id") in preevos for c in (me.get("hand") or []))

    def _line_member_set(self) -> set:
        """Every card id on a Line's path — pre-evolutions AND the payoff. The Pokémon a bench
        accelerator (e.g. Cinderace's Turbo Flare) can usefully load Energy onto."""
        return {cid for line in self.strategy.lines for cid in line.path}

    def _accel_recipient_missing(self, me: dict) -> bool:
        """True if my Active is a bench-accelerator (an `accel_source`-Role Pokémon, e.g. Cinderace)
        but NO Line member sits on my Bench to receive the accelerated Energy — so Turbo Flare would
        attach to nothing. The trigger for developing a recipient first. False with no `accel_source`
        Role declared, no such Active, or any Line member already benched."""
        accel = {cid for cid, r in self.strategy.roles.items() if "accel_source" in r}
        ma = next((p for p in (me.get("active") or []) if p), None)
        if not (accel and ma and ma.get("id") in accel):
            return False
        members = self._line_member_set()
        return not any(b and b.get("id") in members for b in (me.get("bench") or []))

    # (Fetch doctrine greedy multi-pick + gap helpers are in doctrine_fetch.FetchMixin, above.)
    def _evolve_to_ready_wincon_available(self, me: dict) -> bool:
        """True if the win-condition is in hand AND a benched pre-evolution can become a READY attacker
        THIS turn — its Energy (which the evolved Pokémon inherits) PLUS the one manual attach you can
        still make this turn (a reusable Basic in hand) reaches the win-condition's cheapest attack cost.
        So at a promote it is worth bringing up that pre-evolution to evolve. False when the only
        pre-evolution stays bare even after that attach (no Energy on it AND none in hand) — evolving it
        would just expose a dead 0-Energy win-condition, so a staller/accelerator should be promoted
        instead (ep82753102 f120: bare Staryu, no Energy in hand -> Cinderace; ep82226116 f94: bare
        Staryu but a Water in hand -> evolve, the Mega comes online)."""
        if not self._wincon_in_hand(me):
            return False
        preevos = self._line_preevo_set()
        wincon = self._wincon_set()
        if not (preevos and wincon):
            return False
        thresh = min((_min_attack_cost(self.stats, w) for w in wincon), default=1)
        extra = 1 if self._has_reusable_energy(me.get("hand") or []) else 0   # one manual attach this turn
        return any(p and p.get("id") in preevos and len(p.get("energies") or []) + extra >= thresh
                   for p in (me.get("bench") or []))

    def _promote_target_kos(self, obs: dict, select: dict, option: dict) -> bool:
        """At a TO_ACTIVE promote, True if the benched Pokémon this option brings up can Knock Out the
        opponent's Active this turn — its cheapest attack reaches the defender's HP (shared `_can_ko`
        oracle). Promoting it takes the prize from the front (and, for an accelerator, also loads the
        Bench). Fail-closed when stats / the target are missing."""
        poke = self._option_pokemon(obs, select, option)
        if not poke:
            return False
        stat = self.stats.get(poke.get("id")) if self.stats else None
        return self._can_ko(stat, self._opp_active(obs))

    def _promote_target_can_attack(self, obs: dict, select: dict, option: dict) -> bool:
        """At a TO_ACTIVE promote, True if the benched Pokémon this option brings up can use an attack
        this turn (Energy >= its cheapest attack cost) — a live attacker worth interposing in front of a
        win-condition, not a dead wall. Fail-closed when the context / stats / target are missing."""
        if select.get("context") != _TO_ACTIVE:
            return False
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (poke and stat and stat.minAttackCost is not None):
            return False
        return len(poke.get("energies") or []) >= stat.minAttackCost

    def _promote_target_hits_weakness(self, obs: dict, select: dict, option: dict) -> bool:
        """At a TO_ACTIVE promote, True if the benched Pokémon this option brings up would strike the
        opponent's Active on its Weakness — its type (`energyType`) equals the defender's Weakness type, so
        its attack is doubled (rules.md §5). Makes a cheap interposed attacker a favourable trade (Cinderace's
        Fire into a Fire-weak Archaludon/Duraludon). Fail-closed when the context / stats / Active are missing."""
        if select.get("context") != _TO_ACTIVE:
            return False
        poke = self._option_pokemon(obs, select, option)
        stat = self.stats.get((poke or {}).get("id")) if (self.stats and poke) else None
        oa = self._opp_active(obs)
        opp_stat = self.stats.get((oa or {}).get("id")) if (self.stats and oa) else None
        return bool(stat and opp_stat and stat.energyType is not None
                    and opp_stat.weakness is not None and opp_stat.weakness == stat.energyType)

    def _priority_wincon_slot(self, me: dict, active_lethal: bool,
                              active_doomed: bool = False) -> tuple | None:
        """(AreaType, index) of the ONE win-condition Pokémon to concentrate Energy on — among my
        win-condition bodies still short of their biggest attack (`_attach_target_under_max`), the one
        ALREADY carrying the most Energy (closest to firing its payoff hit). The Active is skipped when
        it can already Knock Out the opponent's Active (`active_lethal` — its turn is done, build the
        successor) OR when it is `active_doomed` (it won't survive to fire the payoff, so building it
        for the future is wasted — hand the Energy to a healthy benched wincon instead; a this-turn
        attack off the doomed Active is the Tactical/Planner layer's job, not this positional rule).
        So a powered/dying Active hands the Energy to the benched wincon. None when no buildable wincon
        exists (e.g. only the doomed Active is short) — concentrate then stands down. Backs
        `concentrate-energy-on-wincon` (load one attacker, don't spread; ep83116501 f89)."""
        wincon = self._wincon_set()
        if not wincon:
            return None
        best = None                                  # (energy, area, index)
        active = (me.get("active") or [])
        if not active_lethal and not active_doomed:
            for i, p in enumerate(active):
                if p and p.get("id") in wincon and self._attach_target_under_max(p):
                    e = len(p.get("energies") or [])
                    if best is None or e > best[0]:
                        best = (e, _ACTIVE, i)
        for i, p in enumerate(me.get("bench") or []):
            if p and p.get("id") in wincon and self._attach_target_under_max(p):
                e = len(p.get("energies") or [])
                if best is None or e > best[0]:
                    best = (e, _BENCH, i)
        return (best[1], best[2]) if best else None

    def _bench_wincon_ready(self, me: dict) -> bool:
        """True if a benched win-condition / primary attacker already carries enough Energy to attack
        (>= its cheapest attack cost) — a powered finisher worth retreating into."""
        wincon = self._wincon_set()
        if not wincon:
            return False
        return any(p and p.get("id") in wincon
                   and len(p.get("energies") or []) >= _min_attack_cost(self.stats, p.get("id"))
                   for p in (me.get("bench") or []))

    def _best_promote_slot(self, me: dict) -> tuple | None:
        """(_BENCH, index) of the benched win-condition best to bring to the Active Spot — the READY
        one (Energy >= its cheapest attack cost) carrying the MOST Energy (closest to its payoff hit),
        so a promote/switch picks the built attacker over a bare same-name copy. None when no benched
        win-condition is ready. The per-option picker behind `promote-the-powered-attacker`; a bench-
        index tiebreak keeps it deterministic. Distinct from `_priority_wincon_slot` (which targets the
        one still UNDER its max attack for Energy concentration — the opposite end of the build)."""
        wincon = self._wincon_set()
        if not wincon:
            return None
        best = None                                   # (energy, index)
        for i, p in enumerate(me.get("bench") or []):
            if p and p.get("id") in wincon:
                e = len(p.get("energies") or [])
                if e >= _min_attack_cost(self.stats, p.get("id")) and (best is None or e > best[0]):
                    best = (e, i)
        return (_BENCH, best[1]) if best else None

    def _bench_wincon_prize_value(self, me: dict) -> int:
        """The greatest prize value among my BENCHED win-condition bodies (Mega ex 3 / ex 2 / else 1), 0 if
        none benched. At a forced promote it is the prize I keep OFF the front line by interposing a cheaper
        attacker (`interpose-the-cheap-attacker-to-preserve-the-wincon`)."""
        wincon = self._wincon_set()
        if not wincon:
            return 0
        return max((self._prize_value(p) for p in (me.get("bench") or [])
                    if p and p.get("id") in wincon), default=0)

    def _bench_wincon_underpowered(self, me: dict) -> bool:
        """True if a benched win-condition carries fewer Energy than its highest-damage attack costs
        (`CardStat.maxDamageCost`) — it can't yet fire its payoff hit. Promoting an accelerator (whose attack
        loads the Bench) rather than this finisher lets it reach full Energy off the Bench, which promoting it
        directly (one manual attach/turn) can't. False when every benched wincon is fully powered / costs unknown."""
        wincon = self._wincon_set()
        if not (wincon and self.stats):
            return False
        for p in (me.get("bench") or []):
            if not (p and p.get("id") in wincon):
                continue
            stat = self.stats.get(p.get("id"))
            cost = getattr(stat, "maxDamageCost", None) if stat else None
            if cost is not None and len(p.get("energies") or []) < cost:
                return True
        return False

    def _basic_energy_in_deck(self, deck_empty) -> bool:
        """True if my deck can still yield a Basic Energy — a Basic-Energy card id in my decklist is not
        known-exhausted (`deck_empty`, the sound emptiness oracle). The fuel gate for an accelerator promote:
        Cinderace's Turbo Flare fetches Basic Energy to the Bench, so with none left the acceleration whiffs.
        Fail-open (True) early when nothing is known-exhausted; False with no stats."""
        if not self.stats:
            return False
        empty = deck_empty or frozenset()
        for cid in set(self.deck or ()):
            stat = self.stats.get(cid)
            if stat and getattr(stat, "cardType", None) == _BASIC_ENERGY and cid not in empty:
                return True
        return False

    def _opp_has_played_gust(self, opp: dict) -> bool:
        """True if the opponent has played a gust (a Boss's Orders-style forced-switch) this game — a
        `gust`-tagged card sits in their discard. It means they CAN drag my benched win-condition into the
        Active and Knock it Out, so hiding the finisher on the Bench is less safe: interposing a cheap attacker
        at a promote taxes their next gust and denies the free front-line prize. False with no functions."""
        if not self.functions:
            return False
        for c in (opp.get("discard") or []):
            cid = c.get("id") if c else None
            if cid is not None and "gust" in self.functions.tags(cid):
                return True
        return False

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

    def _snipe_damage(self, obs: dict, my_active_id: int | None, select: dict | None) -> int:
        """The bench-snipe rider my Active's attack deals at a DAMAGE select — max over my Active's
        attacks (Jetting Blow 50). The DAMAGE select carries no attackId, but a snipe always comes
        from my Active, so its biggest snipe rider is the damage a chosen target would take. 0 off a
        Damage select / no Active / no snipe attack. Bench snipes ignore Weakness/Resistance, so this
        is the exact KO test (`rider >= target HP`)."""
        if not select or select.get("context") != _DAMAGE:
            return 0
        stat = self.stats.get(my_active_id) if (self.stats and my_active_id is not None) else None
        if not stat:
            return 0
        return max((self._rider_snipe(aid) for aid in (stat.attacks or ())), default=0)

    def _target_threat_rank(self, obs: dict, select: dict, option: dict,
                            read=None, gamma: float = 0.0) -> float | None:
        """Snipe-priority THREAT rank for a benched DAMAGE target (None off a Damage/bench option).

        Higher = snipe first when no KO is available. The rank is the body's eventual attack power —
        max of its OWN printed damage (so an already-evolved ex attacker like Dragapult ex 200 / Mega
        Lucario ex 270 is seen, which the descendants-only `forward_max_damage` misses) and its
        forward-evolution damage — plus two tiny tie-breaks (more-evolved by own damage so Drakloak >
        Dreepy on the same line; energized = sooner). A line that CERTAINLY reaches a hand-size
        attacker gets `_HAND_SIZE_ATTACKER_BOOST` (the latent Alakazam, hidden by its 10 printed
        damage). This is the single threat order behind `snipe-the-top-threat`; it never rewards a
        low-HP SUPPORT body the flat `snipe-the-weakest` would."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        poke = self._option_pokemon(obs, select, option)
        if (poke or {}).get("id") is None:
            return None
        return self._body_threat_rank(obs, poke, read, gamma)

    def _body_threat_rank(self, obs: dict, poke: dict, read=None, gamma: float = 0.0) -> float:
        """The select-independent threat-rank core behind `_target_threat_rank` — rank ANY benched
        opponent body (a raw player-dict Pokémon), so the Planner's KO-the-key-threat rung can rank
        the bench at the MAIN menu with exactly the same order the DAMAGE-select snipe uses. 0 when
        the id/provider is missing (an unknowable body never outranks a known threat)."""
        cid = (poke or {}).get("id")
        if cid is None:
            return 0.0
        stat = self.stats.get(cid) if self.stats else None
        own = stat.maxDamage if stat else 0
        fwd_fn = getattr(self.stats, "forward_max_damage", None)
        fwd = (fwd_fn(cid) or 0) if fwd_fn is not None else 0
        fwd = self._read_modulated_forward(cid, fwd, read, gamma)   # lever C (ADR-0026): Read-accurate forward
        rank = float(max(own, fwd))
        rank += 0.001 * own                                   # more-evolved tie-break (Drakloak>Dreepy)
        if self.functions:
            line = {cid} | self._forward_card_ids(cid)
            if any("hand_size_attacker" in self.functions.tags(i) for i in line):
                rank += _HAND_SIZE_ATTACKER_BOOST
            my_active = self.stats.get(self._my_active_id(obs)) if self.stats else None
            if (my_active and (my_active.ex or my_active.megaEx)      # I attack with an ex/Mega ex …
                    and any("prevent_ex_damage" in self.functions.tags(i) for i in line)):  # … can't touch
                rank += _PREVENT_EX_SNIPE_BOOST                        # this line once evolved — kill now
        if poke.get("energies"):                              # energized = imminent: a higher snipe tier
            rank += _ENERGIZED_SNIPE_TIER
        return rank

    def _forward_card_ids(self, cid: int | None) -> frozenset:
        """Card ids the snipe target's evolution line evolves INTO (provider primitive; empty when no
        provider / dead-end / unknown id)."""
        fci = getattr(self.stats, "forward_card_ids", None)
        return fci(cid) if (fci is not None and cid is not None) else frozenset()

    @staticmethod
    def _read_modulated_forward(cid: int, fwd: float, read, gamma: float) -> float:
        """Lever C (ADR-0026): scale M0's generic forward-evolution damage by the Read. Recognized (γ>0)
        and the Read predicts THIS body's line (it is a `seen_cardId` on an evolution_path) → trust the
        signal in full; recognized but the archetype runs no such line → suppress it (×(1−γ)); unknown
        (γ=0) or no Read → the generic signal, unchanged. Suppressing denied lines is the accuracy win —
        M0 ranks by the pool's scariest descendant; the Read says whether THIS deck actually runs it."""
        if not gamma or not fwd or read is None:
            return fwd
        confirmed = any(p.seen_cardId == cid for p in read.evolution_paths)
        return fwd if confirmed else fwd * (1.0 - gamma)

    def _strongest_threat_rank(self, obs: dict, select: dict | None, read=None, gamma: float = 0.0) -> float:
        """Greatest `_target_threat_rank` among the benched DAMAGE targets — the body to snipe when no KO
        is on the menu. 0 off a Damage select. read/γ thread lever C (ADR-0026) consistently with the
        per-option rank, so `target_is_top_threat` stays a valid equality."""
        if not select or select.get("context") != _DAMAGE:
            return 0.0
        best = 0.0
        for o in (select.get("option") or []):
            if o.get("type") == _CARD and o.get("area") == _BENCH:
                r = self._target_threat_rank(obs, select, o, read, gamma)
                if r is not None and r > best:
                    best = r
        return best

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

    def _energy_placeable(self, me: dict) -> bool:
        """True if any of my in-play Pokémon can still absorb Energy productively — it carries fewer
        Energy than its highest-damage attack costs (so a manual attach builds it toward a bigger
        attack). When False, a held Energy has no useful home this turn (every body is maxed, or the
        Bench is empty and the Active is fully powered), so shuffling it away with a hand-refresh costs
        nothing. Fail-OPEN (True) when stats are unavailable — only SUPPRESS the held-Energy guard when
        we can positively confirm no body can use the Energy (ep83038055 f40)."""
        if not self.stats:
            return True
        for p in (me.get("active") or []) + (me.get("bench") or []):
            if not p:
                continue
            stat = self.stats.get(p.get("id"))
            cost = getattr(stat, "maxDamageCost", None) if stat else None
            if cost and len(p.get("energies") or []) < cost:
                return True
        return False

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

    def _hand_duplicate_ids(self, me: dict) -> frozenset:
        """Card ids I hold 2+ copies of in hand, EXCLUDING fungible Energy (Basic / Special). The
        keep-value floor `discard-the-hand-duplicate` reads this: a second copy of an effect card
        (Supporter / Item / Pokémon) is the lowest-keep pitch at a forced discard — keep one, shed the
        rest — so a singleton disruptor (a lone Boss's Orders / Harlequin) is never discarded over a
        duplicate. Energy is excluded because a spare Energy is always a future attach, never redundant."""
        counts = Counter(c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None)
        out = set()
        for cid, n in counts.items():
            if n < 2:
                continue
            stat = self.stats.get(cid) if self.stats else None
            if stat and getattr(stat, "cardType", None) in (_BASIC_ENERGY, _SPECIAL_ENERGY):
                continue                                  # fungible Energy: spare is never a redundant pitch
            out.add(cid)
        return frozenset(out)

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
        # a live transient grant on THEIR Active (ADR-0033): a self-lock means it can't attack me
        # next turn at all; a same-attack lock excludes that one attack; a self-bonus raises the hit
        grant = self._transients.grant_for_serial(oa.get("serial")) or {}
        if grant.get("self_lock"):
            return 0
        # opponent attacks ME: opp Active = attacker, my Active = defender — per-attack oracle max
        dmg = self._predicted_max_damage(opp_stat, ma, exclude_attack=grant.get("same_lock"))
        return int(dmg + grant.get("self_bonus", 0)) if dmg else int(dmg)

    def _active_doomed(self, ma: dict | None, oa: dict | None, opp: dict | None = None) -> bool:
        """True if the opponent can Knock Out my Active next turn — its biggest CURRENT attack OR, by
        Posture, the attack its Active reaches by EVOLVING (play as if it will), >= my Active's HP. A
        closed-form threat estimate off engine stats. The forward term catches a hand_size_attacker
        (Alakazam) whose printed damage is 0 but whose Powerful Hand KOs through the evolution
        (ep82754875 f52); ``opp`` omitted → current-board only (the forward term needs the hand size)."""
        my_hp = (ma or {}).get("hp", 0)
        if not my_hp:
            return False
        threat = max(self._incoming_active_damage(ma, oa), self._forward_incoming_damage(ma, oa, opp))
        return threat >= my_hp

    def _forward_incoming_damage(self, ma: dict | None, oa: dict | None, opp: dict | None) -> int:
        """Worst-case incoming damage if the opponent EVOLVES their Active's line next turn — the
        Posture read (play AS IF they evolve; ep82754875 f52: Kadabra → Alakazam, whose Powerful Hand
        places 2 counters per card in hand = 20 dmg/card and KOs my 130-HP Cinderace, though Kadabra's
        own attack can't). For each form the opp Active evolves INTO that is a ``hand_size_attacker``,
        damage is ``handSizeDamage × the opp's hand`` (counters ignore Weakness/Resistance), gated to a
        forward attack the opp could afford next turn (its Active's Energy + one attach). The opp spends
        ≥1 card to play the evolution, so the hand is counted one short. 0 when unknown / no such line.

        Args:
            ma: my Active Pokémon dict.
            oa: the opponent's Active Pokémon dict (the line that would evolve).
            opp: the opponent player dict (for ``handCount``); None → 0 (no forward read).

        Returns:
            The greatest forward hand-size KO threat to my Active (0 if none).
        """
        if not (self.stats and self.functions and ma and oa and opp):
            return 0
        if not self.stats.get(ma.get("id")):
            return 0
        hand = max(0, (opp.get("handCount", 0) or 0) - 1)   # ≥1 card spent to play the evolution
        oa_energy = len(oa.get("energies") or [])
        best = 0
        for fid in self._forward_card_ids(oa.get("id")):
            fstat = self.stats.get(fid)
            if not fstat or "hand_size_attacker" not in self.functions.tags(fid):
                continue
            if (fstat.minAttackCost or 0) > oa_energy + 1:   # unaffordable even with next turn's attach
                continue
            best = max(best, (fstat.handSizeDamage or 0) * hand)   # counter dmg ignores Weakness/Resist
        return best

    def _ability_prevents_damage(self, attacker_stat, defender_id: int | None,
                                 attack_id: int | None = None) -> bool:
        """True if the DEFENDER's Ability prevents all damage from my attacker — the ex / Mega-ex
        damage lock (Function Tag `prevent_ex_damage`, e.g. Crustle's 'Mysterious Rock Inn': prevent
        all damage from your opponent's {ex} Pokémon). My ex / Mega-ex attacker does 0 to it, so the
        closed-form combat math must zero its damage (else the agent whiff-attacks an immune wall and
        the right answer — retreat to a NON-ex attacker — is never surfaced). False for a non-ex
        attacker, an untagged defender, or no function table.

        EXEMPTION (ep83054602 f17): when `attack_id` is given and that attack's damage IGNORES effects
        on the opponent's Active (`ignores_active_effects`, e.g. Mega Starmie's Nebula Beam — "isn't
        affected by any effects on your opponent's Active Pokémon"), the prevention Ability is such an
        effect, so it does NOT apply — the attack lands its full damage. Callers pass `attack_id` only
        when the defender IS the opponent's Active (where the 'on your opponent's Active' clause bites)."""
        if not (attacker_stat and (attacker_stat.ex or attacker_stat.megaEx)):
            return False
        if defender_id is None or not self.functions:
            return False
        if attack_id is not None and self.ignores_active_effects.get(attack_id):
            return False                                 # this attack bypasses the Active's effects
        return "prevent_ex_damage" in self.functions.tags(defender_id)

    def _can_ko(self, my_stat, defender: dict | None) -> bool:
        """My Active's CHEAPEST attack would Knock Out `defender` this turn — its cheapest-cost attack
        damage, doubled when the defender is Weak to my Active's type, >= the defender's remaining HP.
        The shared closed-form KO oracle (ADR-0022) behind both the current-Active KO checks and the
        gust whether-to-play signal. Fail-closed when stats / HP are missing, and 0 when the defender's
        Ability prevents my (ex) attacker's damage (`_ability_prevents_damage`)."""
        hp = (defender or {}).get("hp", 0)
        if not (my_stat and hp):
            return False
        # per-attack oracle over the cheapest-cost attacks (ADR-0032) when their records resolve …
        cheap = [aid for aid in (my_stat.attacks or ())
                 if self.attack_costs.get(aid) == my_stat.minAttackCost
                 and self._attack_stat(aid) is not None]
        if cheap:
            return any(self.predicted_damage(my_stat.cardId, aid, defender) >= hp for aid in cheap)
        # … else the legacy card-level path (stats-only callers): minCostDamage + blanket prevention
        if self._ability_prevents_damage(my_stat, (defender or {}).get("id")):
            return False
        d_stat = self.stats.get(defender.get("id")) if self.stats else None
        return self._wr_adjusted(my_stat, d_stat, my_stat.minCostDamage or 0) >= hp

    def _active_cheap_attack_kos(self, ma: dict | None, oa: dict | None) -> bool:
        """True if my Active's cheapest attack KOs the opponent's CURRENT Active this turn — so a costly
        burst Energy (e.g. Ignition -> Nebula Beam) is unnecessary. The mirror of `_active_doomed`
        (me attacking them, cheapest attack), via the shared `_can_ko` oracle."""
        if not (self.stats and ma and oa):
            return False
        return self._can_ko(self.stats.get(ma.get("id")), oa)

    def _active_can_ko(self, ma: dict | None, oa: dict | None) -> bool:
        """True if my Active's BEST attack it can currently AFFORD (given its attached Energy) KOs the
        opponent's Active this turn. Unlike `_active_cheap_attack_kos` (cheapest attack only), this scans
        every affordable attack — so a fully-loaded Active whose BIGGEST attack (not its cheapest) reaches
        the KO is seen: Mega Starmie at CCC KOs with Nebula Beam (210) though its cheapest Jetting Blow
        (120) can't. Weakness/Resistance-adjusted; 0 when the defender's Ability prevents my ex damage.
        Backs `Board.active_can_ko` (the survival-heal suppressor). Fail-closed on missing stats/HP."""
        if not (self.stats and ma and oa):
            return False
        stat = self.stats.get(ma.get("id"))
        opp_hp = oa.get("hp", 0)
        if not (stat and opp_hp):
            return False
        energy = len(ma.get("energies") or [])
        # per-attack oracle (ADR-0032): prevention is attack-scoped — an ignore-flag attack still KOs
        return any(self.predicted_damage(ma.get("id"), aid, oa) >= opp_hp
                   for aid in (stat.attacks or ()) if self.attack_costs.get(aid, 99) <= energy)

    def _active_maxed_kos(self, ma: dict | None, oa: dict | None) -> bool:
        """True if my Active's BIGGEST-damage attack (fully powered, IGNORING current Energy) would KO
        the opponent's Active — weakness-adjusted, respecting a damage-prevention Ability (with the
        per-attack ignore-effects exemption). Unlike `_active_can_ko` (best AFFORDABLE attack now), this
        asks 'could I KO if I loaded up?': when False the opponent's Active is un-KO-able this turn even
        maxed, so spending a one-shot discard-EOT burst (Ignition) to reach the big attack buys no KO —
        conserve it and use a reusable Energy for the cheap attack instead (ep83116501 f70). Fail-closed
        on missing stats/HP/attacks."""
        if not (self.stats and ma and oa):
            return False
        stat = self.stats.get(ma.get("id"))
        opp_hp = oa.get("hp", 0)
        if not (stat and opp_hp and stat.attacks):
            return False
        best_aid = max(stat.attacks, key=lambda a: self.attacks.get(a, 0))   # biggest printed attack
        # per-attack oracle (ADR-0032): prevention/W/R + attack's own ignore flags in one place
        return self.predicted_damage(ma.get("id"), best_aid, oa) >= opp_hp

    # (Gust Board-signal builders — _active_ko_prizes, _opp_active_condition_gift, etc. — are in
    # doctrine_gust.GustMixin; `_board` calls them as `self.…`.)
    def _opp_has_hand_size_attacker(self, opp: dict | None) -> bool:
        """True if the opponent has a Pokémon in play whose own card OR its forward-evolution line
        reaches a hand-size attacker (a `hand_size_attacker` Function Tag — e.g. Alakazam's Powerful
        Hand, '2 damage counters per card in your hand'). Detects both the revealed attacker AND a
        committed line still building toward it (Kadabra → Alakazam). Card-fact Posture for
        `play-harlequin-vs-hand-size`; needs the function table. False otherwise."""
        if not (self.functions and opp):
            return False
        for p in (opp.get("active") or []) + (opp.get("bench") or []):
            cid = p.get("id") if p else None
            if cid is None:
                continue
            for i in {cid} | self._forward_card_ids(cid):
                if "hand_size_attacker" in self.functions.tags(i):
                    return True
        return False

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

    def _deck_contains_prob(self, me: dict, deck_known: dict | None) -> dict | None:
        """PROBABILISTIC ``{cardId: P(deck still holds ≥1 copy)}`` — the complement to the sound
        ``_deck_empty_ids`` (ADR-0029, `Board.deck_contains_odds`). When the deck-tracker has resolved
        the prizes (`deck_known` given), there is no randomness left — collapse to exact certainty
        (1.0 for any in-deck card, 0.0 otherwise), reusing the SAME sound counts so the two signals
        cannot disagree. Otherwise split each card's unseen copies (`decklist − visible`) over the
        face-down prize slots hypergeometrically (`deck_odds.contains_odds`). None when uncomputable
        (no deck / no `deckCount`) → the signal stays silent. Never raises (grader safety)."""
        if not self.deck:
            return None
        try:
            if deck_known is not None:                    # prizes resolved -> exact certainty, no guess
                return {cid: 1.0 for cid in deck_known}
            deck_count = me.get("deckCount")
            if not isinstance(deck_count, int) or isinstance(deck_count, bool) or deck_count < 0:
                return None                               # no sound deck size -> stay silent
            prize_list = me.get("prize") or []            # face-DOWN prizes (a face-up prize visible)
            prizes_hidden = sum(1 for p in prize_list
                                if not (isinstance(p, dict) and p.get("id") is not None))
            seen = self._visible_card_counts(me)
            return deck_odds.contains_odds(Counter(self.deck), seen, deck_count, prizes_hidden)
        except Exception:
            return None

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
