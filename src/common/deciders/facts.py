"""The three records the whole Pilot reads: `Board` (this turn's facts), `Context` (one option against them) and
`ShedPlan` (what a forced discard would take).

They are DATA — assembled by `board_build` / `context_build`, consumed by every decider. Living here rather than in
`pilot.py` is what lets a decider module annotate them without importing the Pilot."""
from __future__ import annotations


from dataclasses import dataclass, field
from typing import NamedTuple

from common.scouting.briefs import Brief
from common.scouting.matchup_plan import MatchupPlan
from common.scouting.read import Read
from common.strategy import GamePlan, Plan


class ShedPlan(NamedTuple):
    """What a forced ``picks``-card discard would actually take, and what it costs — the return of
    :meth:`Pilot._cost_shed`.

    ``hand_indices`` are positions in the REAL hand (each row's ``hand_i``) and are what a caller
    outside the Pilot wants; ``row_indices`` and ``rows`` are the resolver's own coordinates, kept so
    the fetch doctrine can read the per-card facts (``pitch``, ``dup_hand``, ``in_play``) its three
    bands need without resolving the assignment a second time.

    The two are NOT interchangeable and conflating them is a live defect, not a tidiness point:
    `_needs_hand_rows` drops one copy of the played card before enumerating, so every row after it
    has a row ordinal one short of its hand position."""
    hand_indices: tuple
    row_indices: tuple
    rows: list
    cost: float

@dataclass
class Board:
    """Per-decision board summary (shared by every option) — the cross-option signals a
    Hypothesis trigger reads (bench size, my/opp Active, opponent bench, energy/turn)."""
    my_bench: int = 0
    bench_full: bool = False       # my Bench holds the 5-slot maximum — a fetched Basic has nowhere
                                   # to go, so a bench-filler / Pokemon tutor buys nothing (ml f114)
    my_active_id: int | None = None
    my_active_energy: int = 0
    my_active_hp: int = 0
    opp_bench: tuple = ()          # ((cardId, hp), …) of the opponent's benched Pokémon
    known_top: tuple = ()          # ((serial, cardId), ...) known ordered top of my deck; head first
    turn: int = 0
    energy_attached: bool = False  # already attached Energy this turn?
    supporter_played: bool = False # the one-per-turn Supporter is already spent (`current.supporterPlayed`)
                                   # — so a Supporter grabbed now cannot be PLAYED until next turn,
                                   # while an Item still can (ml f71).
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
    gust_best_total_prizes: int = 0  # gust_best_ko_prizes PLUS the same-attack snipe rider on the
                                   # post-gust bench — the gust line's FULL take (ADR-0066)
    menu_attack_total_prizes: int = 0  # best one-attack total WITHOUT a gust: Active KO + that
                                   # attack's own snipe/spread rider KOs — the snipe-aware baseline
                                   # a gust must beat (ADR-0066; ep86091435 f119). ≥ active_ko_prizes
    gust_ko_energy_swing: int = 0  # sunk Energy on the best-prize KO-able gust target MINUS the
                                   # Energy the baseline Active KO destroys — what an equal-prize
                                   # gust actually buys (ADR-0066; ep85163079 f30: +3)
    stall_swap_pointless: bool = False  # the famine stall would swap one stranded wall for an
                                   # equal-or-worse one — their Active is itself an energyless
                                   # high-retreat body no tamer than any stall candidate (ADR-0066)
    my_prizes_remaining: int = 0   # prizes I still need to take (len of my prize pile); 0 when obs
                                   # doesn't populate it. A gust KO reaching this count WINS (ADR-0022)
    opp_prizes_remaining: int = 0  # prizes OPPONENT still needs (len of their prize pile); 0 when
                                   # obs doesn't populate it. A recoil KOing my Active + handing them
                                   # THIS many prizes simultaneously with my own lethal is a DRAW (ADR-0022 #2)
    reusable_energy_in_hand: bool = False  # a plain (non-discard) Energy in hand — reusable
                                           # alternative to a discard-at-end-of-turn Energy
    wincon_in_play: bool = False   # my win-condition (a Line payoff / win_condition role) already
                                   # on my Active or Bench — search needn't fetch another copy
    wincon_prize_value: int = 0    # greatest prize value among my win-condition bodies (Mega ex 3 / ex 2
                                   # / else 1) — the multi-prize payoff a cheap secondary line makes the
                                   # opponent take MORE, smaller KOs than (ADR-0048); 0 if no wincon
    wincon_in_hand: bool = False   # win-condition card already in my hand — tutor needn't
                                   # dig for another copy
    top_fetch_priority_id: int | None = None  # at a TO_HAND search, highest-priority candidate id
                                       # present, by deck's explicit Strategy.fetch_priority list
                                       # (None off a search / no list / none present) — Tier-3 override
    top_starter_id: int | None = None  # at the pregame SETUP_ACTIVE pick, the highest-ranked card id
                                       # PRESENT among the options, by deck's Strategy.starter_priority
                                       # (None off that select / no list / none present). The whole
                                       # ordering collapses into this one id because SETUP_ACTIVE is a
                                       # forced single pick — argmax reads only the winner (ADR-0079).
                                       # Twin of `top_fetch_priority_id`; gates `open-the-declared-starter`
    line_preevo_in_play: bool = False  # a non-payoff member of a Line's path (a pre-evolution) is in
                                       # play — so there's something a rush-evolve tutor can evolve
    line_preevo_in_hand: bool = False  # a non-payoff Line member (a base/mid-line pre-evolution) is in
                                       # my HAND — a piece to deploy, so a hand-shuffle refresh would bury
                                       # it (Riolu/Drakloak). NO READER since ADR-0065 retired the rung (ep83686860 f13).
    wincon_base_deployable: bool = False  # the payoff's IMMEDIATE pre-evolution (one hop below it) is
                                       # in play OR in hand — evolved payoff deployable soon. False -> fetching
                                       # payoff strands it: prefer base (`fetch-base-before-stranded-payoff`).
                                       # Distance-aware: on a 2-stage line a lone Stage-0 base is NOT enough
    wincon_in_hand_undeployable: bool = False  # an EVOLUTION win-condition sits in my hand with NO base
                                       # anywhere (not in play, and its Line pre-evolution is neither in play
                                       # nor in hand) — a DEAD card I can't deploy this turn or set up to. So
                                       # `hold-wincon-dont-shuffle` should NOT keep it: shuffle it away and
                                       # dig for a base (ep83966336 f44). False for a Basic-payoff wincon
                                       # (directly benchable, so still worth holding).
    accel_recipient_missing: bool = False  # my Active is a bench-accelerator (an `accel_source`-role
                                       # Pokémon, e.g. Cinderace Turbo Flare) AND no Line member on my Bench
                                       # to receive it — accel wasted, developing a recipient is top priority
    support_in_play: bool = False      # an engine/support Pokémon (a draw/accel/search Ability, see
                                       # _ENGINE_TAGS) on my Active/Bench — gap gate for
                                       # `fetch-the-support` (with an engine online, no need to tutor one)
    in_play_ids: frozenset = field(default_factory=frozenset)  # card ids of my in-play Pokémon
                                       # (Active + Bench) — a hand copy of one is a redundant duplicate
    in_play_attack_colors: frozenset = field(default_factory=frozenset)  # specific Energy-type colors my
                                       # IN-PLAY attackers' attacks require (via AttackStat.energyTypes) — the
                                       # colors a fetched Energy can be USED for now; an off-color one no body
                                       # in play needs (dragapult's {D} while Munkidori is in deck) isn't in it
    in_play_required_colors: frozenset = field(default_factory=frozenset)  # attack colors UNION ability-fuel
                                       # colors of my in-play bodies (Munkidori's Adrena-Brain {D}) — the colors
                                       # SOME in-play body can use. An energy outside it is dead weight regardless
                                       # of recipient: backs the ATTACH_TO off-color demote (dragapult f86)
    in_play_unfueled_ability_colors: frozenset = field(default_factory=frozenset)  # ability-fuel colors of
                                       # in-play bodies that LACK that colour attached now — fetching one switches
                                       # a dormant Ability ON (grab {D} for a bare Munkidori); backs `fetch-the-ability-fuel-color`
    setup_placed_ids: frozenset = field(default_factory=frozenset)  # card ids already placed on my Active/Bench
                                       # during the PREGAME setup, read from MOVE_CARD logs (the just-placed Active
                                       # shows only in logs, obs still reads active=[None]) — the setup-aware
                                       # redundancy test the ADR-0086 Deploy Marginal replaced. NO READER (dragapult f4).
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
    # `evolving_wincon_on_bench` was DELETED by ADR-0085 Amendment G. It marked a DEVELOPING
    # win-condition pre-evolution on the opponent bench so the current-attacker rungs would stand
    # down and their SUM could not bury `snipe-the-evolving-threat` (+45). Both the rungs and the sum
    # are gone, so the field had ZERO readers; the scalar reaches the same pick through the `forward`
    # leg ordering rather than through a stand-down. Witness: ms 85164131 f22.
    snipe_ko_available: bool = False    # at a DAMAGE select, SOME benched target is knocked out by the
                                        # snipe rider — so every POSITIONAL snipe rung must stand down and
                                        # let `snipe-for-the-ko` take the free prize. Three positional
                                        # bonuses used to SUM past it (ms 82754241 f45, 82753102 f63)
    snipe_damage: int = 0              # at a DAMAGE select, bench-snipe rider my Active's attack
                                       # deals (max over my Active's attacks) — closed-form KO test for a
                                       # snipe target (rider >= target HP; ignores W/R). 0 off a Damage select
    # `strongest_threat_rank` was DELETED with `target_is_top_threat` (ADR-0085): a whole-bench max
    # computed every DAMAGE decision that existed only to answer that one equality.
    best_counter_slot: tuple | None = None  # (area, index, playerIndex) of the OPPONENT Pokémon to place
                                        # the current counter on at a DAMAGE_COUNTER_ANY(14) spread OR a
                                        # counter-mover's DAMAGE_COUNTER(13) ADD target — knapsack-optimal
                                        # (finish a KO set, else pre-load lowest-HP). Backs `place-counter-to-convert`
    best_counter_source_slot: tuple | None = None  # (area, index, playerIndex) of OUR most-damaged body to
                                        # REMOVE counters from at a REMOVE_DAMAGE_COUNTER(16) source select
                                        # (Munkidori) — the biggest heal. Backs `move-counters-off-the-damaged`
    max_counter_move_number: int = 0    # largest count offered at a REMOVE_DAMAGE_COUNTER_COUNT(40) select —
                                        # move as many counters as possible. Backs `move-max-counters`. 0 off ctx 40
    stadium_in_play: int | None = None  # card id of the Stadium currently in play (`current.stadium`), else None
    opp_stadium_in_play: bool = False   # that Stadium was played by the OPPONENT — replacing it disrupts them
                                        # (a stadium-play net-value signal; backs `play-risky-ruins-when-net-positive`)
    bench_wincon_ready: bool = False   # a benched win-condition / primary attacker already carries
                                       # enough Energy to attack — a finisher to retreat into
    best_promote_slot: tuple | None = None  # (AreaType, index) of MY benched win-condition best to bring
                                       # to Active at a promote/switch — READY (Energy >= cheapest attack)
                                       # AND most-Energy, not a bare copy/slot-0 (ep83007714 f92/f104). Backed
                                       # `promote-the-powered-attacker` (RETIRED); still read by the promote equation.
    ko_promote_slot: tuple | None = None  # (AreaType, index) of the benched body whose affordable attack —
                                       # given this turn's attachable Energy + a playable {F} damage-boost —
                                       # KOs the opp Active (`promote_ko_aware`; None when off / no KO-body).
                                       # Backed `promote-the-ko-attacker` (DELETED, ADR-0100 §11 -> `_promote_ko_tactical`)
    evolve_to_ready_wincon_available: bool = False  # win-condition in hand AND the payoff's IMMEDIATE
                                       # pre-evo on the Bench already carries enough Energy that evolving THIS turn
                                       # yields a ready attacker — worth promoting to evolve. False -> bare/too-deep
                                       # pre-evo, promote staller/accel instead (ep82753102 f120; dragapult f31)
    bench_wincon_prize_value: int = 0  # greatest prize value among my BENCHED win-conditions (Mega ex 3 /
                                       # ex 2 / else 1), 0 if none — prize I keep OFF the front line by
                                       # interposing a cheaper attacker at a forced promote (prize denial)
    bench_wincon_underpowered: bool = False  # a benched win-condition carries fewer Energy than its
                                       # highest-damage attack costs — can't yet fire payoff, so an accel
                                       # promote can power it off-Bench, which promoting the finisher directly can't
    opp_cannot_punish_wincon: bool = False  # ADR-0064 Decision 4: the opponent's reachable Incoming
                                       # (charged safety read) cannot KO my best benched win-condition next
                                       # turn — the return-KO reachability veto. Stands down interpose /
                                       # the prize-reach brake; both rungs are DELETED (ADR-0100 §11, now Exposure)
                                       # (scenario 3: they literally can't afford to punish). Fails CLOSED
    basic_energy_in_deck: bool = False  # my deck can still yield a Basic Energy (a Basic-Energy id not
                                       # known-exhausted) — fuel gate for an accelerator promote
                                       # (Cinderace's Turbo Flare fetches Basic Energy to the Bench)
    opp_has_played_gust: bool = False  # opponent has played a gust (Boss's Orders-style forced switch)
                                       # this game — a `gust`-tagged card in their discard; can drag my
                                       # benched finisher out, so interposing a cheap body taxes that gust
    active_is_wincon: bool = False     # my Active IS the win-condition / primary attacker
    active_is_weak_preevo: bool = False  # my Active is a WIN-CONDITION line pre-evolution whose own printed
                                       # output is a minor chip far below the body it evolves into — an Energy
                                       # on it buys little tempo (Riolu's 30 vs Mega Lucario ex 130/270). Read
                                       # by mega_lucario's `dont-lunar-cycle-away-the-last-attachable-f`
                                       # stand-down: with the engine online, discard the last {F} to draw 3
                                       # rather than sink it into the weak pre-evo (ml 85058574 f16). False for
                                       # a real-attacker pre-evo (Makuhita→Hariyama 210) or a non-preevo active
    can_wall_line_with_disruptor: bool = False  # dragapult f32/f20: my Active is a fragile developing
                                       # win-condition LINE pre-evo, a benched `item_lock` disruptor
                                       # (Budew) can be promoted as a sacrificial wall, and the opp
                                       # Active can damage the line NOW — retreat to wall it and develop
                                       # the line on the Bench behind cover (retreat-to-promote maneuver)
    can_lock_line_with_disruptor: bool = False  # dragapult f20 OFFENSIVE variant: early game, a fragile
                                       # line-preevo Active with nothing better to do + a benched
                                       # `item_lock` opener + a cheap reachable retreat — retreat into
                                       # Budew to DENY the opp's Item turn (no incoming-damage premise)
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
    deny_relevance_best: float | None = None
                                       # **Deny Relevance** (ADR-0080, Issue #187): the best relevance
                                       # achievable anywhere on their board, in [0,1]. 0.0 = no Energy is
                                       # doing work worth denying (no Energy at all, surplus Energy, or
                                       # the only live body dies to my Knock Out this turn) — HOLD.
                                       # Replaces `opp_denial_best` on the fire-now rung when armed.
                                       # **`None` means ABSENT, not zero** (ADR-0093 decision 2;
                                       # `CONTEXT.md`, ABSENT is not ZERO): the read is OFF, or this
                                       # board never went through `_board()`. The default was `0.0`
                                       # until Issue #228, which made absence indistinguishable from a
                                       # measured whiff — and mid-sim absence was routine, so the fire
                                       # rung declined strips worth +22.50 and +74.50. A `None` fails
                                       # CLOSED to a RECOMPUTE (`_deny_relevance_best`'s ladder),
                                       # never to a whiff — it used to fall back to `opp_denial_best`,
                                       # which Issue #228 deleted along with the rest of that oracle.
    deny_relevance_rows: tuple | None = None
                                       # per-body `(area, bi, {EnergyType: relevance}, strip_shift)` —
                                       # what the TARGET pick ranks on, plus the ADR-0084 clock DELTA
                                       # its lexicographic tiebreak reads (None when `deny_strip_delta`
                                       # is off — absence, NOT a measured zero). `None` on the
                                       # FIELD is the same distinction one level up: not
                                       # measured, versus measured and empty (Issue #228
                                       # applied it to `deny_relevance_best`; it is the same
                                       # rule here). Consumers already re-compute on falsy,
                                       # so this is a typing correction, not a behaviour
                                       # change. One row set, so the
                                       # rank and its tiebreak can never drift apart.
                                       # Keyed by TYPE, never by position: a
                                       # `DISCARD_ENERGY` option's `energyIndex` indexes attached CARDS
                                       # while `energies` counts the units they PROVIDE, so the two
                                       # indexes diverge on any multi-unit Energy (see `_relevance_terms`).
    opp_has_energy_in_play: bool = False  # opponent has Energy on any Pokémon (Active or Bench) —
                                          # a target an energy-denial Item (Crushing Hammer) can strip
    opp_active_has_energy: bool = False   # opponent's ACTIVE carries Energy. NO LONGER the
                                          # `play-energy-denial` gate (ADR-0062): Crushing Hammer targets
                                          # "1 of your opponent's POKEMON" — Active OR Bench — so this was
                                          # narrower than the card, and it fired on SURPLUS Energy besides.
                                          # `opp_denial_best` (what the strip actually takes away) replaced it.
    opp_active_can_damage_us: bool = False  # opponent's ACTIVE has an AFFORDABLE attack (current Energy)
                                          # dealing >0 to my Active — oracle-resolved, so a conditional
                                          # 0-damage attack (Kyogre's Riptide off an empty discard) or an
                                          # all-unaffordable set is NO threat. `play-energy-denial` stand-down:
                                          # don't strip a body that can't actually hurt us (dragapult f6)
    # `opp_has_hand_size_attacker` DELETED (ADR-0102, Issue #261 item 2c) with the two rungs that were
    # its only readers. Nothing re-asks the question: `_hand_size_relief_tactical` puts the hand
    # counts into the Damage Formula's own `atk_hand` / `def_hand` context keys and lets the survival
    # clock answer. The retired boolean read the `hand_size_attacker` Function Tag, which was a second
    # reading of a fact the damage oracle already holds as a scaler (ADR-0102 decision 5).
    opp_hand_size: int = 0                # opponent's current hand size (`handCount`) — the resource
                                          # STACK a hand-disruption Supporter strips; the refresh swing
                                          # oracle's opponent leg (ADR-0060). Sound off handCount.
    my_hand_size: int = 0                 # my current hand size — the don't-gift-a-refresh comparator
                                          # (only strip when theirs exceeds mine, so we net-strip rather than hand them a fresh hand)
    # `opp_draw_engine_in_play` DELETED (ADR-0102) with `strip-the-stacked-engine-hand`, its only
    # reader. The general MatchupPlan tier survives as `_general_body_facts` (Issue #395 D4/D5,
    # which superseded the id-set `_draw_engine_ids`); its ONE caller is `_matchup_plan`, which
    # feeds it to `derive_general_roles`.
    # -- Opponent RESOURCES (ADR-0047) flattened onto the Board so a `when()` can trigger off them
    #    without reaching through `board.opponent.resources`. Sourced from the match-scoped tracker
    #    (opponent_resources.OpponentResourceModel); every value fails OPEN (unknown -> the no-fire
    #    default). The consuming cluster is the strategy-ingest deferrals unblocked once the tracker
    #    landed (learnthetcg / kou 30-deck) — see data/strategy/proposals/*.
    opp_took_ko_this_turn: bool = False   # I took a prize (KO'd an opponent Pokémon) THIS turn — so I
                                          # have just ENABLED their post-KO comeback disruptor (Unfair
                                          # Stamp). Sound when True; False when unknown. `unfair-stamp-comeback-posture` gate.
    my_pokemon_koed_last_turn: bool = False  # THE MIRROR: the opponent took ≥1 prize across their last
                                          # turn (one of MY Pokémon was KO'd) — MY Unfair Stamp's own
                                          # play condition; gates the gamble's drawn-Stamp refresh
                                          # chain. Sound-when-fired (rare self-recoil edge fails open).
    opp_hand_size_delta: int | None = None  # change in opponent hand size since their previous distinct
                                          # turn; None until a prior turn is known. SIGN (settled ADR-0060,
                                          # the two docstrings used to contradict each other): POSITIVE = they
                                          # GREW their hand = it is FRESH. Consumed by the hand-swing oracle's
                                          # `fresh_cards` — stripping cards they just drew denies live
                                          # resources; stripping ones they have been stuck holding for three
                                          # turns denies cards they demonstrably cannot play.
    opp_last_turn_dumped: bool = False    # opponent's discard grew >=2 since the previous distinct turn
                                          # (an Ultra-Ball-class discard-cost play last turn) — they have
                                          # COMMITTED to the few cards they kept. Conservative proxy; False when unknown.
    opp_deckout_in_turns: int | None = None  # estimated game-turns until the opponent's deck is exhausted
                                          # (from the observed deck-count trajectory); None until >=2
                                          # distinct-turn samples show a net decrease. SOUND (deck-count is public). Feeds the grind-to-deckout read.
    opp_comeback_disruptor: bool = False  # Disposition: the recognized opponent runs a post-KO hand
                                          # disruptor (Unfair Stamp class) — `opp_comeback_disruptor` Brief
                                          # property (opponent_properties.json), γ-gated. False when unrecognized / no Brief asserts it.
    opp_hand_strip_odds: float = 0.0      # P(the opponent's deck still holds a card that SHUFFLES MY HAND
                                          # AWAY — `hand_disruption`: Judge/Harlequin/Unfair Stamp): max
                                          # `copies_left_odds` over the matched Read's rep build (their
                                          # observed plays already subtracted). The held-card-risk exposure
                                          # leg (spec §Round 8 §5). Fails OPEN to 0.0 (no facade / no
                                          # confident Read → no exposure claimed → no veto); a strip card
                                          # held in their HAND is not in-deck, so this UNDER-counts — the
                                          # safe direction for a suppressor.
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
    opponent: object = None               # the Opponent Model facade (ADR-0047) — all opponent KNOWLEDGE:
                                          # Identity (=read), Resources (deck-out/copies-odds/hand-delta/
                                          # took-KO), Dispositions (=opp_property). None = direct Board
                                          # (tests) / no facade. Behavior-neutral: nothing scores off the
                                          # new Resources surface yet (the deferred cluster consumes it).
    posture_confidence: float = 0.0       # γ ∈ [0,1] from the Read (ADR-0026): continuous strength the
                                          # generic-core Posture levers scale by; 0 = unrecognized / no Scout.
    favorability: float = 0.5             # compiled matchup win-rate vs Read's candidate opponents
                                          # (0.5 = neutral / no data) — lever-A aggression signal (ADR-0026).
    matchup_coverage: float = 0.0         # share of Read's posterior that hit a real matchup cell; low
                                          # coverage = favorability mostly the 0.5 default -> trust it less.
    brief: Brief | None = None            # matched hand-authored Matchup Brief for the recognized
                                          # opponent (ADR-0027, covers-routed); None = unrecognized / no
                                          # covering Brief / Posture off. Behavior-neutral: nothing scores off it yet.
    brief_threat_ids: frozenset = field(default_factory=frozenset)  # opp card ids the matched Brief lists
                                          # as THREATS to respect (attackers), resolved from brief.threats
                                          # via the provider name->id (ADR-0027 consumer). Empty = no Brief.
    brief_target_roles: dict = field(default_factory=dict)  # {opp card id: Dossier role} the Brief lists as
                                          # disruption/snipe TARGETS (fragile_preevo/prize_liability/engine).
                                          # Behavior-neutral: the surface exists; nothing scores off it yet.
    matchup_plan: MatchupPlan = field(default_factory=MatchupPlan)  # ADR-0051 unified opponent target-
                                          # priority spine: composes Brief + Read-Intel (γ-gated) + the
                                          # general draw-engine card fact. `priority(opp_id)` steers
                                          # snipe/gust. Empty (all-0) default = inert (kill-switch/no Read).
    opp_discard_energy: dict = field(default_factory=dict)  # {EnergyType: count} of Basic Energy in the
                                          # OPPONENT's (fully visible) discard — the discard-fuel gauge read
                                          # (coverage-review item #2: "their discard holds N energy of type
                                          # T"). A discard-fuelled forward line — Mega Lucario ex Aura Jab
                                          # re-attaches Basic {F} FROM discard (678), a self-KO'd Wild Press
                                          # {F}{F}{F} (674) is only re-castable while the {F} is recoverable —
                                          # is a realer threat when its type sits here. Pure data; consumed
                                          # by the (armed-off) `snipe_discard_fuel` threat-rank lift.
    my_discard_basic_energy: dict = field(default_factory=dict)  # {EnergyType: count} of Basic Energy in
                                          # MY open discard — the recover-rider fuel (Aura Jab class), and the
                                          # ONE truth for it since ADR-0061 (`_recover_units` reads it here).
                                          # `_damage_context` keeps its own attacker-relative copy: that one
                                          # must also serve the INCOMING direction, so they are not duplicates.
    active_best_attack_locked: bool = False  # my Active's HIGHEST-damage attack is transient-locked this
                                          # turn (Mega Brave class, ADR-0033) — the swap trigger
    opp_has_stage2: bool = False          # opponent has a Stage 2 in play (CardStat.stage2) — the
                                          # Gravity Mountain tech read
    opp_has_colorless_ability: bool = False  # opponent has a {C} Pokémon WITH an Ability in play —
                                          # the Team Rocket's Watchtower read
    hand_ids: frozenset = field(default_factory=frozenset)  # card ids in MY hand — generic hold/
                                          # sequencing read (e.g. Watchtower waits while Meowth's in hand)
    search_deck_ids: frozenset | None = None  # ids in the CURRENT search's revealed deck pool
                                          # (`select.deck`) — an EXACT within-frame reachability test (a
                                          # card absent here is unreachable this search), or None off a
                                          # deck-revealing select; fall back to `deck_definitely_empty_of`
    hand_basic_energy: dict = field(default_factory=dict)  # {EnergyType: count} of Basic Energy in MY
                                          # hand — the last-attachable-F read (Lunar Cycle guard)
    recycle_dead_only: bool = False       # my discard's recycle pool (Pokémon/Basic Energy) is non-empty
                                          # yet every member is a dead pick (a stranded, hand-unplayable
                                          # evolution; no Energy) — gates `dont-recycle-the-dead` (f33)
    active_fully_powered: bool = False    # my Active already carries its HIGHEST-damage attack's cost
                                          # (attached ≥ maxDamageCost) — a burst Energy has no urgent
                                          # job; False when unknown (fail-closed keeps the keep rules)
    active_famine: bool = False           # **Famine** (#142): my Active cannot attack this turn — NO attack
                                          # reachable under the FULL Attach Budget, or the rules forbid it one
                                          # at all (Asleep/Paralyzed/turn-1-going-first, `attack_blocked`).
                                          # The corrected premise the stall-gust family reads; False when
                                          # unknown, so only a demonstrable famine stands anything down
    active_attack_provable: bool = True   # my Active can PAY and legally use an attack this turn on the
                                          # **Provable Budget** — the sound deck leg, plus the engine's own
                                          # attack menu. The read for a consumer about to SPEND something that
                                          # expires unused (a this-turn damage boost); True when unknown
    active_unarmed_but_able: bool = False  # my Active carries ZERO Energy yet can still REACH an attack
                                          # this turn (not `active_famine`) — the descriptive fact behind
                                          # "go down swinging rather than stall-gust" (ml f19, dragapult
                                          # f70). Derived once because two stall-gust rules need the
                                          # identical clause
    immediate_preevo_in_play: bool = False  # the payoff's immediate pre-evo (e.g. Drakloak) is ALREADY on
                                          # my board, so a hand copy of it is redundant — refuel over it
    deploy_now_ids: frozenset = field(default_factory=frozenset)  # hand card ids that are evolutions with
                                          # an ELIGIBLE in-play base THIS turn (deploy-now spike, ADR-0065):
                                          # pitching/shuffling forfeits a live tempo play re-access can't
                                          # restore, so keep spikes to full worth (`_gate_closing`)
    active_arm_available: bool = False    # go-down-swinging is on the table: the Active is a real ATTACKER
                                          # (not a utility body) whose biggest attack ONE more Energy would
                                          # COMPLETE, and no ready benched win-condition to retreat into —
                                          # arm+attack beats banking/drawing the Energy (ml f21 Solrock),
                                          # unlike a body one short (f42 Makuhita) or a utility engine (f54)
    no_supporter_in_hand: bool = False   # MY hand holds NO Supporter (cardType 3) — the
                                          # `supporter_tutor` bench trigger (bench Meowth ex to fetch one)
    my_path_turns: float | None = None    # Tier-3 Prize Path (ADR-0040): total feasibility turns of MY
                                          # cheapest path to my remaining prizes over their VISIBLE bodies;
                                          # None = runs through bodies not yet in play (consumers silent)
    their_path_turns: float | None = None # their cheapest path over MY bodies (the denial side) — the
                                          # worst-case ceiling read (affordability not charged, like Incoming)
    race_ahead: float | None = None       # their_path_turns − my_path_turns: positive = I'm ahead in the
                                          # race; None when either side's path is unknown. Feeds phases.
    path_target_ids: frozenset = field(default_factory=frozenset)  # opp card ids on MY cheapest Prize
                                          # Path — the on-path KO/snipe preference (`target_on_path`)
    path_target_keys: frozenset = field(default_factory=frozenset)  # ADR-0044: on-path body IDENTITIES
                                          # (id(body)) — duplicate-species-safe keying for `_target_on_path`
    opp_active_doomed: bool = False       # ADR-0044: the opponent's Active is dead (hp<=0 / no live active),
                                          # so a promotion is FORCED next turn — the Forced-Promotion Read trigger
    forced_promotion_key: int | None = None  # ADR-0044: id(body) of the bench Pokémon they will promote when
                                          # doomed = the highest OWN-damage ready attacker (energy-independent)
    their_path_my_ids: frozenset = field(default_factory=frozenset)  # MY card ids on THEIR cheapest path —
                                          # the bodies whose exposure/denial matters ("force 7, not 6")
    line_ready: bool = False              # a win-condition Line payoff is in play with enough Energy to
                                          # attack (the `choose_plan` readiness core) — the REAL signal the
                                          # old plan==SETUP/RACE gates migrated to (ADR-0040 gate ban)
    bench_line_member_needs: bool = False  # a BENCHED win-condition Line-path body still needs Energy for
                                          # its cheapest attack — an un-powered line waits on the bench, so
                                          # `prefer-active-attach-in-setup` stands down for a role-less
                                          # off-Line Active and the tie-break develops the line (86091728 f19)
    phase: Plan = Plan.SETUP              # the DERIVED advisory phase (ADR-0040): readiness SETUP→RACE +
                                          # objective overrides (behind+doomed→STABILIZE, ≤2-prizes+ready→
                                          # CLOSE), hysteretic, memoryless backwards. ADVISORY ONLY — small
                                          # band weights (baseline_phases) + trace; never an eligibility gate
    game_plan: GamePlan | None = None     # the Match Planner's Game Plan for this turn (ADR-0045): route +
                                          # mode + confidence + directed Turn Goal. Set by `_board` after the
                                          # objective signals resolve; COMPUTE-ONLY (S2) — nothing scores off
                                          # it yet (the seam S3 wires the directed goal into the Turn Planner)
    turn_goal_satisfied: bool = False     # BUILD 4 (`dont-spend-unneeded-supporter`): the turn's directed
                                          # goal is ALREADY met and nothing is still being searched/tutored,
                                          # so a draw/gust/evolution Supporter can be HELD for a later decisive
                                          # turn rather than spent now. Must FAIL SAFE to False (holding a
                                          # NEEDED supporter loses tempo) — populated conservatively in `_board`.

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

    def opp_property(self, key: str, default=None):
        """Value of opponent-property ``key`` from the matched Matchup Brief (ADR-0027,
        ``brief.opponent_properties``), or ``default`` when no Brief is matched (unrecognized
        opponent / Posture off) or the key isn't asserted. Never raises. The Brief is
        assert-true-only, so an omitted key (e.g. ``opp_is_engine_dependent``) reads as ``default``.
        Routed through the Opponent Model facade's Dispositions (ADR-0047) when present — the same matched
        Brief, so identical values — else the direct Brief read (a Board built without the facade)."""
        if self.opponent is not None:
            return self.opponent.disposition(key, default)
        if self.brief is None:
            return default
        return self.brief.opponent_properties.get(key, default)

    def brief_is_threat(self, card_id: int) -> bool:
        """True if the matched Brief lists ``card_id`` as a threat to respect (ADR-0027).

        UNCONSUMED: no `src/` caller. Its sibling `brief_target_roles` IS live (it feeds
        `_matchup_plan`), which is what makes the threat half easy to miss. Kept as a Brief-consumption
        seam; delete it if the matchup layer settles without one."""
        return card_id in self.brief_threat_ids

    def brief_target_role(self, card_id: int):
        """The matched Brief's target role for ``card_id`` (``fragile_preevo`` / ``prize_liability`` /
        ``engine``), or None if it isn't a Brief target (or no Brief matched).

        UNCONSUMED: no `src/` caller (tests only). See `brief_is_threat`."""
        return self.brief_target_roles.get(card_id)

    def brief_target_ids(self, role: str | None = None) -> frozenset[int]:
        """Card ids the matched Brief lists as disruption/snipe targets — filtered to ``role`` when
        given, else all of them. Empty when no Brief matched.

        UNCONSUMED: no `src/` caller (tests only). See `brief_is_threat`."""
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
    attach_is_energy: bool = True      # this ATTACH option's CARD is an Energy, not a Pokémon Tool.
                                       # The engine sends both as OptionType.ATTACH, so every Energy
                                       # hypothesis must test this or it prices Air Balloon (ml f87).
                                       # Fail-open (True when the card's stat is unknown)
    attach_target_is_utility_body: bool = False  # the body this attach would FUND draws/tutors/stalls,
                                       # never attacks (`Pilot._is_utility_body`) — Lunatone, Meowth ex,
                                       # Dunsparce→Dudunsparce. Set at BOTH funding seams: the manual
                                       # ATTACH and the accel ATTACH_FROM recipient pick (ml f121/f84,
                                       # dragapult f21). NO READER: ADR-0069 moved the role gate inside `_attach_value`.
    attach_target_under_max: bool = False  # receiving Pokémon carries fewer Energy than its
                                           # HIGHEST-damage attack costs — can't yet fire its big attack
                                           # (1 W can Jetting Blow but not Nebula Beam CCC). Fail-CLOSED (False when unknown).
    attach_target_is_priority_wincon: bool = False  # this attach option puts Energy on the ONE
                                           # win-condition to concentrate on (== board.priority_wincon_slot)
                                           # — most-built buildable wincon. NO READER: ADR-0069 folded concentrate into the attack axis.
    attach_fuels_dormant_ability: bool = False  # this ATTACH's typed Basic Energy is a colour the target's
                                           # ABILITY needs as fuel (CardStat.abilityEnergyTypes) and none is
                                           # attached — the attach switches a dormant Ability on (Adrena-Brain's
                                           # {D}). Attach-side sibling of `fetch-the-ability-fuel-color`
    attach_feeds_firing_accel: bool = False  # this ATTACH puts Energy on an ACTIVE accelerator
                                           # (`accel_source` Role, e.g. Cinderace) that still NEEDS it to fire
                                           # its accel attack, w/ a bench recipient and no ready wincon to retreat into. Multiplies Energy even if doomed (ep83037962 f70); off if a ready attacker exists (ep83007714 f65).
    attach_target_is_line_member: bool = False  # this attach option's recipient is on a win-condition
                                           # Line (a pre-evolution or the payoff) — building it advances the
                                           # wincon. Read into `OptionTrace.attach_to_needy_line`, the decide()-only tie-break (Line base over off-line opener)
    attach_target_is_draw_engine: bool = False  # this attach option's recipient is a DRAW-ENGINE body (a
                                           # `draw`/`stall` tag, or evolves into one: Dunsparce → Dudunsparce) —
                                           # its job is cards, not attacking, so don't sink the turn's Energy into it (dragapult f21)
    attach_from_target_needs: bool = False  # at an ATTACH_FROM target-select (engine's pick-a-
                                           # recipient step for a multi-attach effect, e.g. Turbo Flare),
                                           # THIS recipient still NEEDS Energy — spread to the bare body, not an online one. False off ATTACH_FROM (cf attach_target_needs)
    attach_from_target_is_concentrate: bool = False  # at ATTACH_FROM, THIS option's recipient is the Line
                                           # body to concentrate accelerated Energy on (== board.attach_from_
                                           # concentrate_slot) — build ONE body, the counterpart of attach_from_target_needs' spread
    card_is_line_preevo: bool = False  # this option's card is a non-payoff member of a Line's path (a
                                       # pre-evolution that builds toward the win-condition)
    card_is_recognized_line_preevo: bool = False  # this option's card is a pre-evo of ANY declared attacker
                                       # Line — win-condition OR secondary-attacker (ADR-0048); the broadened
                                       # line-piece credit, narrows to card_is_line_preevo when kill-switched off
    card_forward_payoff_prize: int = 0  # greatest prize value this option's card BECOMES (max over it +
                                       # forward evolutions) — Riolu→Mega 3, Makuhita→Hariyama 1 (ADR-0048)
    card_evolution_baseless: bool = False  # this grab candidate is an EVOLUTION with NO base to evolve
                                       # it onto in my play or hand — a dead grab (a 3rd Drakloak, every
                                       # Dreepy evolved/gone). Board-sound; gates `dont-grab-a-baseless-mid-evolution`
    card_base_unreachable: bool = False  # this grab candidate is an EVOLUTION whose pre-evolution base
                                       # is provably UNGETTABLE this game (not in play/hand AND absent
                                       # from the search's revealed pool / provably empty from deck) — a
                                       # dead card (Mega ex with every Riolu gone); `dont-fetch-an-unplayable-evolution-payoff`
    card_is_wincon: bool = False       # this option's card IS the win-condition (a Line payoff /
                                       # win_condition / primary_attacker)
    card_is_starter: bool = False      # this option's card is a startable Basic Pokémon (hp > 0, no
                                       # evolvesFrom) — a body that develops an underdeveloped board
                                       # (`fetch-a-starter` grab rung). Derived off CardStat.
    card_is_support: bool = False      # this option's card is an engine/support Pokémon (hp > 0 with a
                                       # draw/accel/search Ability, see _ENGINE_TAGS) —
                                       # `fetch-the-support` grab rung. Derived off CardStat + tags.
    card_is_utility_body: bool = False  # this option's card is a body that draws/tutors/stalls and never
                                       # attacks (`Pilot._is_utility_body`) — the card-side read of
                                       # `attach_target_is_utility_body`. (Backed `dont-open-with-the-engine`
                                       # until ADR-0079 deleted it; the attach-side readers remain.)
    card_is_top_fetch_priority: bool = False  # this candidate IS deck's highest-priority fetch
                                       # target present (== board.top_fetch_priority_id) — Tier-3
                                       # explicit-list grab override (`fetch-deck-priority`)
    card_is_top_starter: bool = False  # at the pregame SETUP_ACTIVE pick, this option IS the deck's
                                       # highest-ranked startable body on offer (== board.top_starter_id)
                                       # — the sole scorer at that seam, gating the general
                                       # `open-the-declared-starter` (ADR-0079). The card-side twin of
                                       # `card_is_top_fetch_priority`
    card_is_redundant: bool = False    # this option's card duplicates a Pokémon already in play (its
                                       # need is met) — lowest keep-value, preferred at a forced
                                       # discard (`discard-the-redundant`)
    card_is_hand_duplicate: bool = False  # this option's card is one I hold 2+ copies of in hand (a
                                       # redundant effect card; fungible Energy excluded) — keep-value
                                       # floor `discard-the-hand-duplicate` pitches it before a singleton
    card_already_in_hand: bool = False  # at a TO_HAND search, an identical copy of this candidate is
                                       # ALREADY in my hand (fungible Energy excluded) — tutoring a
                                       # second one buys nothing (ml f9: grabbed a 3rd Lillie's over the
                                       # Petrel that opens the tutor chain). The FETCH-side mirror of the
                                       # shipped `discard-the-hand-duplicate`
    card_unplayable_this_turn: bool = False  # at a TO_HAND search, this candidate is a SUPPORTER and my
                                       # one-per-turn Supporter is already spent (`board.supporter_played`)
                                       # — it cannot be played until next turn, while an Item can be
                                       # played now (ml f71: took a Lillie's on the turn Petrel fetched it)
    card_chain_value: float = 0.0      # at a TO_HAND search, the discounted tutor-chain closure value of
                                       # this candidate (`_chain_grab_value`, seam C: δ/hop × MAX reachable
                                       # `_grab_value_of`, 2-hop cap, Item-only descent) — a tutor is worth
                                       # what it reaches (ml f9: Petrel → Fighting Gong → Solrock). Stays
                                       # 0.0 in `_grab_value_of`'s reduced Context (no self-recursion);
                                       # gates `grab-the-chain-opener` above `_CHAIN_OPENER_FLOOR`
    card_spends_last_evolution_route: bool = False  # this chain-hop grab would consume the LAST free
                                       # tutor reaching an evolution whose base is in my play/hand
                                       # (count-aware over the revealed pool) — preserve it, take the
                                       # closure-cheap hop (`dont-spend-the-last-route-to-a-wanted-evolution`)
    fetch_fills_a_need: bool = False   # this option PLAYS a fetch whose reachable deck set still holds a
                                       # card I currently lack (best grab value > 0, same grab rungs) —
                                       # whether-to-play endorsement (`fetch-when-it-fills-a-need`). False off a non-fetch/need-less fetch
    fetch_target_deferred: bool = False  # ...AND every needed target is provably UNPLAYABLE this turn
                                       # (evolution with no eligible base / my first turn, rules.md §4; a
                                       # Basic w/ Bench full) — fetch-late dominates fetch-early (held-card
                                       # risk, spec §Round 8 §5). Gates `dont-fetch-before-the-deadline`
    refresh_shuffles_deferred_fetch: bool = False  # this option PLAYS a shuffle_hand refresh while a HELD
                                       # fetch's needed grab is deferred past this turn — the self-refresh
                                       # would strip the deferred plan's vehicle exactly like the
                                       # opponent's Judge would. Gates `dont-shuffle-away-the-deferred-fetch`
    target_energy: int | None = None  # attack-target snipe signal: Energy on the targeted benched
                                      # Pokémon (None off a Damage/bench-target option)
    target_is_threat: bool = False  # attack target already carries Energy -> closest to attacking
    target_hp: int | None = None    # HP of targeted benched Pokémon (None off a Damage option)
    target_is_weakest: bool = False  # this snipe target has least HP on opponent's Bench
    target_is_strongest_forward: bool = False  # this snipe target's evolution line is the most
                                               # dangerous on the Bench (forward damage greatest, real
                                               # threat) — priority evolving snipe (Riolu→Mega Lucario over Hariyama)
    target_forward_form_in_play: bool = False  # the snipe target is a pre-evolution whose EVOLVED
                                               # wincon form is ALREADY on the opponent's board — so chip
                                               # the ready form directly, not the redundant pre-evo
                                               # (the ADR-0044 discriminator for snipe-the-evolving-threat)
    target_kos: bool = False           # the bench snipe KNOCKS OUT this target (rider >= its HP; bench
                                       # snipes ignore Weakness/Resistance) — a free PRIZE, top snipe.
                                       # Never true for a benched Tera body (it takes no damage at all)
    target_is_bench_tera: bool = False  # this snipe target is a BENCHED Tera Pokemon — "prevent all damage
                                       # done to this Pokemon by attacks" while Benched (CardStat.tera), so
                                       # the rider does literally nothing. Backs the STRUCTURAL
                                       # `_snipe_tera_veto` (KO_SCORE-class, Tactical) — it superseded the
                                       # tuner-mutable `dont-snipe-a-benched-tera` (−60), which a positional
                                       # stack could outvote. Also excluded from `target_kos` and
                                       # `_forced_promotion_key`.
    # `snipe_relevance_armed` was DELETED here by ADR-0085's deletion pass. It existed for exactly one
    # purpose — carrying the `not c.snipe_relevance_armed` stand-down into the six DAMAGE target rungs
    # so the additive stack could go quiet while the scalar decided. Those rungs are gone, so nothing
    # reads it and the Context stops advertising a switch no rule consults.
    promote_target_kos: bool = False   # at a TO_ACTIVE promote, benched Pokémon this option brings
                                       # up can KNOCK OUT opp's Active this turn (cheapest attack reaches
                                       # HP) — promote it to take the prize from the front (esp. an accelerator that also loads the bench)
    is_best_promote_target: bool = False  # at a TO_ACTIVE promote OR a SWITCH (my retreat's new-Active
                                       # pick), this option brings up board.best_promote_slot — most-built
                                       # ready wincon. NO READER: ADR-0100 replaced the promote rungs with `promote_value`.
    is_ko_promote_target: bool = False  # at a promote/switch, this option brings up board.ko_promote_slot —
                                       # the benched body whose (boost-inclusive) attack KOs the opp Active
                                       # (`promote_ko_aware`). Backed `promote-the-ko-attacker`, now DELETED
    card_prize_value: int = 1          # prizes a KO of THIS option's card yields (Mega ex 3 / ex 2
                                       # / else 1) — cost of exposing it; interpose rule promotes a
                                       # body whose value is below the benched wincon's
    promote_target_can_attack: bool = False  # at a TO_ACTIVE promote, benched Pokémon this option
                                       # brings up can use an attack this turn (Energy >= cheapest attack
                                       # cost) — a live attacker to interpose, not a dead wall
    promote_target_hits_weakness: bool = False  # at a TO_ACTIVE promote, this option's body would strike
                                       # opponent's Active on its Weakness (x2 chip) — a favourable
                                       # sacrifice (Cinderace's Fire into a Fire-weak Archaludon/Duraludon)
    # `target_is_top_threat` was DELETED by ADR-0085's deletion pass — the only rule that ever read
    # it was `snipe-the-top-threat` (+30). It was an ARGMAX-EQUALITY flag (`target_rank ==
    # board.strongest_threat_rank`), i.e. a boolean standing in for "is this the biggest?", which is
    # precisely the shape decision 1 replaced: the scalar orders targets continuously, so the biggest
    # threat wins by scoring highest rather than by being flagged.
    target_forward_damage: int | None = None  # Evolving Threat signal (ADR-0020): max damage
                                              # snipe target's evolution line eventually reaches
                                              # (None off a Damage option / no chain / no provider)
    target_on_path: bool = False        # Tier-3 (ADR-0040): this damage/snipe target sits on MY
                                        # cheapest Prize Path — its KO advances the MATCH win
                                        # False when the path is unknown. No PRODUCTION reader since ADR-0085 folded the snipe stack.
    target_prize_redundant: bool = False  # ADR-0044: a snipe target OFF my committed cheapest Prize Path
                                        # — chip here doesn't advance it ("deny the 2nd Mega"). A high-prize
                                        # body I never need is flagged ALWAYS; a low-prize one only when I'm
                                        # not under pressure (else deny the threat). Suppresses the threat snipe
    target_is_forced_promotion: bool = False  # ADR-0044: their Active is dead and THIS bench body is the
                                        # ready wincon they'll promote — pre-chip it (`snipe-the-forced-promotion`)
    target_promotion_mirage: bool = False  # ADR-0044: their Active is dead and THIS body is NOT the one
                                        # they'll promote — its threat/imminence is a mirage, suppress it
    bench_shortens_their_path: bool = False  # Tier-3 Path Denial (ADR-0040): benching THIS Pokémon
                                        # strictly improves the opponent's cheapest Prize Path
                                        # (completes/shortens their route) — `dont-bench-onto-their-path`
    bench_path_delta: float = 0.0       # ...and by HOW MUCH, in turns (ADR-0086 decision 5). The
                                        # Deploy Marginal's exposure leg: the magnitude the boolean
                                        # above is merely the sign of. `HORIZON`-graded when the play
                                        # completes a previously-uncompletable route; 0 when the
                                        # `objectives_path` switch is off, so exposure is DEFINED
                                        # rather than estimated when the machinery is dark.
    promote_target_on_their_path: bool = False  # Tier-3 Path Denial (ADR-0040): this promote/switch
                                        # candidate sits on THEIR cheapest path — bringing it up walks
                                        # it into the KO they want (rung DELETED as subsumed, ADR-0100 §7c)
    counter_is_best_placement: bool = False   # this option puts the current counter on the knapsack-
                                              # optimal opp target at a DAMAGE_COUNTER_ANY/DAMAGE_COUNTER
                                              # select (== board.best_counter_slot) — `place-counter-to-convert`
    counter_is_source_pick: bool = False      # this option removes counters from OUR most-damaged body at
                                              # a REMOVE_DAMAGE_COUNTER select (== board.best_counter_source_slot)
    is_max_counter_move: bool = False         # this NUMBER option is the largest count at a
                                              # REMOVE_DAMAGE_COUNTER_COUNT select — `move-max-counters`
    evolve_body_energy: int | None = None     # energy on the in-play Pokémon an EVOLVE option would evolve
                                              # (its inPlayArea/inPlayIndex body) — a wincon-evolution can be
                                              # held until the payoff can attack. None off an EVOLVE option
    roles: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    stat: object | None = None     # option card's engine CardStat (hp/weakness/prize value/…)
    board: Board = field(default_factory=Board)   # per-decision board summary (same for all options)
    context_card_id: int | None = None  # the select's OWNER (`select.contextCard`): the card whose effect/
                                   # Ability resolves (an ACTIVATE's bare YES/NO carries no card itself)
    search_targets_exhausted: bool = False  # this option PLAYS a deck-search/tutor whose every legal
                                   # fetch target (its FETCH clauses, `_search_deck_set`) is PROVABLY gone from
                                   # deck — so it whiffs. SOUND (Board.deck_empty_ids); False off a search / no clause
    search_redundant_wincon: bool = False  # this option PLAYS a tutor that can fetch ONLY the
                                   # win-condition AND that payoff has no productive landing — wincon already in
                                   # hand, OR no deployable base for it (its immediate pre-evo neither in play nor
                                   # in hand). So the tutor only digs a redundant copy (Mega Signal with a Mega in
                                   # hand) or a dead card it can't deploy (Mega Signal with the Mega already in play).
                                   # False off a search / a tutor that can fetch anything else / when a base IS deployable
    search_baseless_wincon: bool = False  # this option PLAYS a wincon-ONLY tutor whose payoff is NEITHER
                                   # in hand NOR in play AND has no deployable base (its immediate pre-evo is
                                   # not in play/hand), and the tutor can't fetch that base — the fetched wincon
                                   # sits dead. DISTINCT from search_redundant_wincon (which needs the wincon
                                   # in play/hand). The turn-1 premature-tutor shape (85164605:f6);
                                   # `dont-tutor-the-baseless-wincon-turn-one` reads it, gated on turn<=1 + a held Energy.
    search_targets_unlikely: bool = False  # this option PLAYS a search whose every still-REACHABLE
                                   # fetch target is PROBABLY (not provably) prized — P(deck contains it)
                                   # below whiff threshold (ADR-0029). PROBABILISTIC complement to search_targets_exhausted; mutually exclusive with it.
    search_confirmed_hit: bool = False  # this option PLAYS a search that PROVABLY hits: a fetch target
                                   # certainly still in deck (`Board.deck_definitely_has`, post-anchor) AND filling
                                   # a need (positive grab value). POSITIVE complement of the two whiff signals (ADR-0029); sound-or-silent. Drives `search-the-confirmed-hit`.
    # The three COST-NETTING bands, all read off ONE number: what the keep-value v2 assignment says
    # the two cards it would actually shed cost (`_shed_signals` -> `needs.removal_score`). Priced by
    # the equation that DECIDES the discard since Issue #261 item 2h retired the ladder they used to
    # be scored against — a predictor and a decider that disagree is the drift that rots a signal.
    fetch_sheds_junk: bool = False  # this option PLAYS a cost_discard fetch whose 2 predicted sheds
                                   # cost <= 0 AND are each dead or replaceable — junk cost, so dig at the free band (`costly-fetch-sheds-junk`)
    fetch_sheds_live: bool = False  # ...the predicted shed costs > 0 — a live card pays for the dig
                                   # (`dont-shed-a-live-card`)
    fetch_sheds_key: bool = False   # ...it costs at least ACE_SPEC_TIER — an irreplaceable card is
                                   # forced into the pitch (`dont-shed-a-key-card`)
    refresh_probable_miss: bool = False  # this option PLAYS a shuffle_hand refresh whose N-card draw
                                   # PROBABLY misses every needed card (post-anchor hypergeometric over the
                                   # shuffle-grown pool, ADR-0024 amendment). Drives `dont-refresh-into-a-probable-miss`.

def _slot_cid(slot):
    """The card id a `line:<cid>` slot belongs to, or None for any other slot kind."""
    key = getattr(slot, "key", "") or ""
    if getattr(slot, "kind", "") != "line" or not key.startswith("line:"):
        return None
    head = key.split(":")[1]
    return int(head) if head.isdigit() else None
