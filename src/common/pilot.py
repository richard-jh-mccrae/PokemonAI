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
from common.evolve_value import EvolveInputs, evolve_value
from common.promote_retreat_value import PromoteRetreatInputs, promote_retreat_value
from common.opponent_model import OpponentModel
from common.strategy import GamePlan, Plan, Strategy
from common.scouting.read import Read
from common.scouting.matchup import matchup_favorability
from common.scouting.briefs import Brief, match_brief, resolve_brief_cards
from common.scouting.matchup_plan import MatchupPlan, build_matchup_plan

# Engine vocab (enum mirrors, KO_SCORE, _ENGINE_TAGS) shared w/ doctrines -> common.strategy.context.
# Doctrines own their Hypotheses + Pilot-side `*Mixin` code — see those modules.
from common.strategy.context import *  # noqa: F401,F403  (the engine-vocabulary constants + _fires/Board live there or below)
from common.strategy.doctrines import FetchMixin, GustMixin, ShuffleRefreshMixin, ToolMixin
from common.strategy.objectives import ObjectivesMixin
from common.strategy.planner import PlannerMixin, TurnLine

# Tactical-only scalars — used SOLELY by the closed-form combat evaluator below, never by a doctrine.
# (_EFFICIENCY/_BENCH_SNIPE* moved to the KO oracle, ADR-0052 — the one home for combat valuation.)
from common.strategy.combat import _EFFICIENCY  # noqa: E402  (re-used by the tactical scorers)
from common.strategy.refresh import (fresh_cards, net_change, opponent_shuffles,  # noqa: E402
                                     own_draw_count, refresh_branches)  # (ADR-0060 swing oracle)
from common.strategy.sequence import followup_damage  # noqa: E402  (ADR-0061 horizon-2 lock oracle)
from common.strategy.denial import coin_odds, denial_value  # noqa: E402  (ADR-0062 energy denial)
# A shuffle-refresh moves cards in four directions and they are NOT worth the same per card. Pricing
# them symmetrically is what broke the guard family on the first cut: a per-card credit for cards I
# DRAW reached +76 and went straight through `hold-wincon-dont-shuffle` (−25),
# `hold-irreplaceable-tool-dont-shuffle` (−30) and `dont-refresh-into-a-probable-miss` (−25), which
# were all calibrated against `dig-before-commit`'s flat +20.
_REFRESH_CYCLE = 20        # the DRAW side, flat: cards I have not seen are speculative and only as
                           # good as what the deck can still supply — which is precisely what the
                           # `hold-*-dont-shuffle` / probable-miss guards adjudicate. Bounded and flat
                           # so those guards can still cancel it, exactly as they could cancel the +20
                           # `dig-before-commit` used to supply blindly.
# _REFRESH_SHED (the flat −8/card-lost shed) RETIRED 2026-07-18 (ADR-0065): the shed side is now the
# GRADED Σ keep_cost over the actual hand (`_refresh_shed_keepcost`) — a wincon costs its role value ×
# how UN-recoverable it is, a dreg ~0. ENERGY_TIER (8, `common.card_worth`) is the old flat anchor.
_REFRESH_STRIP = 4         # per card stripped from THEIR hand — certain denial (ms f43/f45/f100/f64).
_REFRESH_GIFT = 8          # per card HANDED to them: Judge into a 1-card opponent hand REFILLS them to
                           # 4. Priced like a shed — a card in their hand is as real as one in mine.
_REFRESH_FRESH = 2         # per stripped card THEY DREW LAST TURN (`opp_hand_size_delta` > 0): live
                           # resources denied, versus cards they have demonstrably been unable to play.
_REFRESH_BENCH_BODY = 12.0 # piece 2 (SHADOW-reported, decides nothing yet): per missing bench body the
                           # redraw can supply, the ADAPTIVE draw credit above the flat CYCLE. A thin
                           # board that the HAND cannot develop (no benchable body held) values the
                           # redraw by the open deploy need × P(deck supplies a body) — ep83038055 f40,
                           # "we desperately need a bench". A generic body-deploy tier (engine band);
                           # magnitude is an OPEN promotion question — measured in the refresh shadow
                           # before it ever touches the live CYCLE.
_GRAB_REFRESH_DRAW = 0.1   # SUB-POINT tie-break at a TO_HAND draw-Supporter grab: prefer the refresh
                           # with the bigger own-draw ceiling (Lillie's 8 early ≻ Judge 4). Scaled so a
                           # draw Supporter (base +10) tops out at ≤ +10.8 — never crossing the +15 chain
                           # opener or a +18 line piece. Breaks the flat-band tie, re-values nothing (the
                           # PLAY swing is priced later by `_refresh_swing_tactical`). ep86088989 f29.
# The discard equation's engine-supporter keep floor (ADR-0065 seam-D) — mirrors the ladder's
# `keep-engine-supporter-at-discard` (−8): a draw/search/dig SUPPORTER that is not hand_disruption
# is a draw engine kept over pure filler. Discard-CONTEXT (not general worth), tuned to the −8 band.
# NOTE: `heal`/`clutch_heal` are DELIBERATELY OUT (classification fix, 2026-07-21) — a heal Supporter
# (Wally's Compassion) is RECOVERY, not card advantage, and does not belong on the draw-engine slot.
# It was pricing Wally's at a saturated ~2.6 on the shared engine slot AND (as an `engine_cids`
# member) barring it from its rightful `general` worth (recovery role 20 → ~9). A heal that also
# genuinely draws still qualifies via its `draw`/`dig` tag; a pure heal now takes general worth.
_ENGINE_KEEP_TAGS = frozenset({"draw", "search", "dig"})
_ENGINE_SUPPORTER_KEEP = 8.0
# WP-N5 (keep-value v2): the LATENT-worth discount on a held card that fills no specific need — its
# role tier is real board value even without an open slot (the readiness leaf's `contribution` for
# the HAND), but a not-yet-deployed card is worth less than one filling a live need. Sized at the
# leaf's bench position weight (`_READINESS_BENCH_DISCOUNT` 0.45 — a hand card is ~one deploy away,
# like a benched body). De-duplicated by the assignment (one slot per distinct card).
_GENERAL_WORTH_W = 0.45
_GENERAL_ILLIQUID_FLOOR = 0.15  # piece 2b (the shed's Hole-2 fix): a general-worth card whose value
                           # needs board state it hasn't got — an Energy with NO body that can receive
                           # and attack with it (a doomed Active, an empty Bench, no benchable body in
                           # hand) — prices at this fraction of its latent tier, not the full catalog
                           # worth. Illiquid held value you cannot spend is not worth clinging to over a
                           # refresh (ep83038055 f40: Ignition 13.5 + a bare {W} propped the shed above
                           # the redraw with no attacker in sight). NOT 0 — a residual future worth once
                           # a body lands keeps it above outright-dead cards in pitch order. Derived from
                           # the board, never a card list; a live recipient restores full worth (f65: an
                           # Ignition kept for the BENCHED Mega Starmie stays fully priced).
# WP-N5b/N5d (armed OFF): the develop-rung LEAF's actionable-resource term — the value of my HELD
# hand at end-of-turn = the needs-assignment slot coverage (`needs.set_keep_v2`) of the held cards
# that COULD NOT have been deployed this turn (`_held_undeployable` — the N5d complement: a card I
# chose not to play is a fumble, not future value; crediting it rewarded HOARDING, the N5b/N5c
# regression). The SAME valuation the keep-value sites use (readiness CONSUMES needs — one
# vocabulary, not a rival). Sized/capped by the leaf-lab bench.
_HAND_READINESS_W = 0.5
_HAND_READINESS_CAP = 40.0
# The ε TIE-BREAK scale (the alternative sizing): shrink the whole term below the smallest genuine
# leaf gap (~0.025, the line account's smallest spend increment), so it can ONLY split exact-value
# ties (the 36→5 collapse) and can never overturn a real ranking gap. N5b's W-insensitivity proved
# the damage was tie-splits, not magnitude — so the ε only helps once the VALUATION is right (N5d).
_HAND_TIEBREAK_W = 0.0001
_HAND_TIEBREAK_CAP = 0.02
_DENIAL_BENCH = 0.25       # ADR-0062: discount on stripping a BENCHED body. Crushing Hammer targets ANY
                           # of their Pokémon (card text + engine), but a benched body must be PROMOTED
                           # before the denial bites AND they get a turn in between to simply re-attach —
                           # an Active strip is spent immediately, a bench strip is easily undone. The
                           # bound is DERIVED, not tuned to taste: ms f29 (bench, 70) must hold while
                           # ms f15 (Active, 30) must play, which forces bench weight < 30/70 = 0.43.
_DENIAL_PLAY_W = 1.0       # points per damage-point denied, at the PLAY. REPLACES `play-energy-denial`'s
                           # flat +20, which paid the same for turning off a 270 nuke as for shaving 70
                           # off a benched body. Same lesson as ADR-0060: price the quantity, don't
                           # threshold it.
_DENIAL_ITEM_COST = 10     # the value of KEEPING the Hammer. An Item is finite, and a free Item is tiered
                           # ahead of everything by `_finish_turn_last` — so a purely positive term could
                           # never decline one: any score above zero gets it played. The strip must beat
                           # the hold (ms f29: "wasted crushing hammer").
_DENIAL_TARGET_W = 1.0     # points per damage-point denied, at the DISCARD_ENERGY select. Ranks the
                           # Hammer's TARGET once its coin comes up heads; nothing scored that select
                           # before, so a won flip stripped option [0] — the OLDEST-attached Energy.
_DENIAL_UNFAVORED = 0.3    # Lever A (ADR-0026), as a MULTIPLIER on the priced denial rather than a flat
                           # rung beside it: when the Read says the race is lost, a strip that already
                           # denies something is worth MORE. It can never make a whiff worth playing —
                           # scaling 0 leaves 0, and scaling a negative play value leaves it negative.
                           # This is the whole point (ms 83968638 f17, CRITICAL): the old flat
                           # `disrupt-when-unfavored` (+18) rode `opp_denial_best > 0` (the raw PRESENCE
                           # of denial) and so OVERRODE the oracle's own hold — a free Item at score > 0
                           # is tiered ahead of everything. A booster must scale the oracle, never add to it.
_DENIAL_FORWARD = 0.5      # ADR-0062 amendment: credit for what the stripped Energy would pay for on the
                           # target's FORWARD form. "Evolving keeps attached cards" (rules.md:98), so
                           # Energy on a pre-evolution is BANKED, not spent: a Riolu's own Accelerating
                           # Stab ({F}, 30) is not what its Energy is for — Mega Lucario ex's Aura Jab
                           # ({F}, 130) is. Discounted because the payoff is a TURN AWAY (they must evolve
                           # first) and CONTINGENT (they must actually hold the evolution). The bound is
                           # DERIVED from two frames, not tuned: ms 82225643 f12 (Active Riolu, 1 Energy)
                           # must PLAY, and dragapult 85046350 f32 (Active Gabite, 1 Energy, forward 100)
                           # must stay BELOW the retreat-to-wall (30) it would otherwise bury — which
                           # forces 0.154 < _DENIAL_FORWARD < 0.8.
_ENERGY_RECOVER = 75       # per-Energy value of a recover rider (Aura Jab: "attach up to N Basic {X}
                           # from discard") on a NON-KO turn — chip-scale, so fueled Aura Jab beats bare Mega Brave
_RECOVER_KO = 0.25         # KO-branch sub-prize variant: "the cheaper KO that also develops" —
_RECOVER_KO_CAP = 0.75     # capped < 1, never overrides a real prize difference (like bench-snipe)
_FOLLOWUP_W = 0.5          # ADR-0061: weight on the FORCED follow-up a locking attack leaves behind.
                           # < 1 because damage THIS turn is certain and next turn's is not (they move in
                           # between) — so at equal two-turn totals the front-loaded nuke wins, which is
                           # the right default. Replaces the flat _LOCK_COST = 40, which was a phantom
                           # charge on a same-attack lock (270+130 == 130+270) and a 5x under-charge on a
                           # full lock (Blood Moon 240 + NOTHING loses to a lock-free 130/turn's 260).
_LOCK_KO = 0.3             # KO-branch sub-prize variant: among equal-prize KOs keep the nuke off cooldown
_RECOIL_DOOM = 100         # charge a NON-KO attack whose recoil FLIPS a safe Active doomed (Wild Press at
                           # 80 HP) — combat-scale; a KO/snipe-KO or already-doomed Active is never charged
_SELF_RETURN_ESCAPE = 50   # per-prize CREDIT for a self-return attack (Meowth ex Tuck Tail) that bounces a
                           # DOOMED multi-prize Active to hand, denying the opponent the prize(s); non-KO
                           # branch only, so a real KO always wins (mirror of _RECOIL_DOOM, a survival credit)
_ENERGIZED_SNIPE_TIER = 100000  # energized benched target is strictly higher snipe TIER than any
                           # bare one — attacks SOONER (imminence), sniped before a bigger latent
                           # threat (ADR-0020). Within a tier, threat magnitude orders the choice.
_SNIPE_THREAT_PRIZE_FLOOR = 5   # deny an ENERGIZED off-Prize-Path attacker (don't treat it as prize-
                           # redundant) while I still hold >= this many prizes — early game, the imminent
                           # threat will bleed my prizes before I close; below it I race my committed path
                           # (ms f39 snipe @6 vs 83667237-107 stand-down @4, symmetric boards). Calibrated
                           # on 2 corrections — a ladder-tuned floor.
_ITEM_LOCK_EARLY_TURN = 3  # promote/retreat shadow (Sweep #2 Finding A): an `item_lock` body's disruption
                           # (Itchy Pollen) is credited only while the opponent still depends on SETUP
                           # Items — turn <= this. dragapult f20/f13 (turn 2, retreat-into-Budew correct)
                           # keep it; f30/f35/f96 (turn 4/6/12) lose the flat +27 over-fire.
_HAND_SIZE_ATTACKER_BOOST = 500  # snipe-rank boost for a benched body whose evolution line CERTAINLY
                           # reaches a hand-size attacker (Kadabra→Alakazam "Powerful Hand") — latent
                           # win-condition hidden by low printed damage. `hand_size_attacker` Function Tag.
_PREVENT_EX_SNIPE_BOOST = 500  # snipe-rank boost for a benched body whose line reaches a Pokémon that
                           # PREVENTS my ex attacker's damage (`prevent_ex_damage`, e.g. Dwebble→Crustle) —
                           # hard counter once evolved, snipe the fragile pre-evo NOW (ep82225138 f46).
_MATCHUP_PRIORITY_SCALE = 5  # ADR-0051: scale from a MatchupPlan role priority (base ≤100, γ-pre-scaled)
                           # into the snipe/gust TACTICAL band — above the positional snipe rungs (Σ≲150)
                           # yet below KO_SCORE (1000), so it steers WHICH non-KO body to target but a
                           # real Knock Out always wins. A negative (`avoid`) priority pushes a draw engine
                           # below every real target.
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
    bench_full: bool = False       # my Bench holds the 5-slot maximum — a fetched Basic has nowhere
                                   # to go, so a bench-filler / Pokemon tutor buys nothing (ml f114)
    my_active_id: int | None = None
    my_active_energy: int = 0
    my_active_hp: int = 0
    opp_bench: tuple = ()          # ((cardId, hp), …) of the opponent's benched Pokémon
    turn: int = 0
    energy_attached: bool = False  # already attached Energy this turn?
    supporter_played: bool = False # the one-per-turn Supporter is already spent (`current.supporterPlayed`)
                                   # — so a Supporter grabbed now cannot be PLAYED until next turn,
                                   # while an Item still can (ml f71). Gates `grab-what-i-can-play-now`
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
    line_preevo_in_play: bool = False  # a non-payoff member of a Line's path (a pre-evolution) is in
                                       # play — so there's something a rush-evolve tutor can evolve
    line_preevo_in_hand: bool = False  # a non-payoff Line member (a base/mid-line pre-evolution) is in
                                       # my HAND — a piece to deploy, so a hand-shuffle refresh would bury
                                       # it (Riolu/Drakloak); gates `hold-line-piece-dont-shuffle` (ep83686860 f13)
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
                                       # redundancy test `dont-pre-bench-a-redundant-utility` needs (dragapult f4)
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
    evolving_wincon_on_bench: bool = False  # at a DAMAGE select, some benched opponent snipe target is a
                                        # developing WIN-CONDITION pre-evolution: forward damage reaches a
                                        # win-condition-class body (>= _EVOLVING_THREAT_DMG), its evolved form
                                        # is NOT yet in play, AND that form is a genuine higher-prize payoff
                                        # (>= 2 prizes). When present, the current-attacker snipe rungs
                                        # (top-threat / threat / forced-promotion) stand down on every body
                                        # that is NOT that pre-evo, so `snipe-the-evolving-threat` (+45) takes
                                        # the developing wincon instead of a bulky/energized current body whose
                                        # rungs SUM past it (ms 85164131 f22 — chip the Staryu that becomes
                                        # Mega Starmie ex, not the energized 1-prize Cinderace). Mirrors the
                                        # `snipe_ko_available` sum-burial stand-down. Kill-switch `evolving_wincon_priority`
    snipe_ko_available: bool = False    # at a DAMAGE select, SOME benched target is knocked out by the
                                        # snipe rider — so every POSITIONAL snipe rung must stand down and
                                        # let `snipe-for-the-ko` take the free prize. Three positional
                                        # bonuses used to SUM past it (ms 82754241 f45, 82753102 f63)
    snipe_damage: int = 0              # at a DAMAGE select, bench-snipe rider my Active's attack
                                       # deals (max over my Active's attacks) — closed-form KO test for a
                                       # snipe target (rider >= target HP; ignores W/R). 0 off a Damage select
    strongest_threat_rank: float = 0.0  # at a DAMAGE select, greatest snipe THREAT RANK among
                                        # benched targets (`_target_threat_rank`: max own/forward damage,
                                        # +boost for a hand-size-attacker line) — snipe pick when none KO'd. 0 off a Damage select
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
                                       # AND most-Energy. Backs `promote-the-powered-attacker`, not a bare copy/slot-0 (ep83007714 f92/f104)
    ko_promote_slot: tuple | None = None  # (AreaType, index) of the benched body whose affordable attack —
                                       # given this turn's attachable Energy + a playable {F} damage-boost —
                                       # KOs the opp Active (`promote_ko_aware`; None when off / no KO-body).
                                       # Backs `promote-the-ko-attacker`, role-independent (ml f26/f48/f24)
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
                                       # dont-promote-into-their-prize-reach so promote-the-ready-wincon wins
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
    opp_denial_best: float = 0.0       # ADR-0062: the most damage a single Energy discard could take away
                                       # from ANY of their Pokémon (Crushing Hammer targets Active OR Bench;
                                       # bench discounted by `_DENIAL_BENCH`). 0 = every energized body either
                                       # holds SURPLUS Energy (strip it and they still afford the same attack)
                                       # or cannot pay an attack at all — the Hammer is a whiff, HOLD it.
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
    opp_has_hand_size_attacker: bool = False  # opponent has a Pokémon in play (or in a committed
                                          # evolution line) that SCALES damage with hand size (a
                                          # `hand_size_attacker`, e.g. Alakazam) — `play-harlequin-vs-hand-size` gate. Card-fact, not meta guess
    opp_hand_size: int = 0                # opponent's current hand size (`handCount`) — the resource
                                          # STACK a hand-disruption Supporter strips on the engine's
                                          # swing turn (ADR-0051 Phase 3b `strip-the-stacked-engine-hand`). Sound off handCount.
    my_hand_size: int = 0                 # my current hand size — the don't-gift-a-refresh comparator
                                          # (only strip when theirs exceeds mine, so we net-strip rather than hand them a fresh hand)
    opp_draw_engine_in_play: bool = False  # opponent has a `draw`-tagged ENGINE (Dudunsparce/Budew
                                          # class) in play — the "engine swing turn" gate; a non-engine
                                          # deck has no swing turn to hold for (hand-size decks are `play-harlequin-vs-hand-size`). ADR-0051 Phase 3b
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
    active_attack_payable: bool = True    # my Active can PAY some attack this turn (attached Energy +
                                          # the best unspent hand attach ≥ its cheapest attack cost).
                                          # True when unknown (fail-open) — gates the starved stall-gust
    active_fully_powered: bool = False    # my Active already carries its HIGHEST-damage attack's cost
                                          # (attached ≥ maxDamageCost) — a burst Energy has no urgent
                                          # job; False when unknown (fail-closed keeps the keep rules)
    active_attack_payable_via_accel: bool = False  # a PLAYABLE hand energy-accelerator (`tutor_energy`,
                                          # e.g. Crispin) could fetch+attach ONE Energy and make my Active
                                          # attack-payable THIS turn — the false famine `active_attack_payable`
                                          # (attached + hand-attach only) misses; False when unknown, so a
                                          # PROVABLE famine still fires the stall-gust (dragapult f70)
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
                                       # dragapult f21). Gates `dont-fund-the-non-attacking-body`
    attach_target_under_max: bool = False  # receiving Pokémon carries fewer Energy than its
                                           # HIGHEST-damage attack costs — can't yet fire its big attack
                                           # (1 W can Jetting Blow but not Nebula Beam CCC). Fail-CLOSED (False when unknown).
    attach_completes_biggest_attack: bool = False  # this ATTACH onto the ACTIVE crosses it from short-of to
                                           # able-to-afford its HIGHEST-damage attack THIS turn (was < maxDamageCost,
                                           # attached + provided >= maxDamageCost). Gates the stand-down of
                                           # `dont-overbuild-the-doomed-wincon`: a DOOMED Active that this very
                                           # attach turns the big attack ON should still fire it — go down swinging
                                           # (ms 85163079 f51: 2W+1 = Nebula 210), unlike one merely overbuilt for a
                                           # turn that won't come (ep83037962 f48: 1W→2W still short of CCC=3).
                                           # Fail-CLOSED (False when target / CardStat / maxDamageCost unknown).
    attach_target_is_priority_wincon: bool = False  # this attach option puts Energy on the ONE
                                           # win-condition to concentrate on (== board.priority_wincon_slot)
                                           # — most-built buildable wincon. Gates `concentrate-energy-on-wincon` (load one, not spread).
    attach_type_wasted: bool = False       # this ATTACH provides an Energy TYPE the target already has
                                           # enough of for its attack, while a DIFFERENT specific type is
                                           # still short — a wasted off-type attach (Phantom Dive needs Fire+Psychic; 2nd Psychic wasted). Gates `dont-waste-off-type-energy`
    attach_fuels_dormant_ability: bool = False  # this ATTACH's typed Basic Energy is a colour the target's
                                           # ABILITY needs as fuel (CardStat.abilityEnergyTypes) and none is
                                           # attached — the attach switches a dormant Ability on (Adrena-Brain's
                                           # {D}). Attach-side sibling of `fetch-the-ability-fuel-color`
    attach_is_tool_deploy_target: bool = False  # this ATTACH option puts a +HP Tool on the body the
                                           # survival-turns picker chose (== board.tool_deploy_slot) —
                                           # proactive deploy endorsement (`deploy-hp-tool`, ADR-0028)
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
                                       # `attach_target_is_utility_body`. Backs `dont-open-with-the-engine`
    card_is_top_fetch_priority: bool = False  # this candidate IS deck's highest-priority fetch
                                       # target present (== board.top_fetch_priority_id) — Tier-3
                                       # explicit-list grab override (`fetch-deck-priority`)
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
                                       # stack could outvote. Also excluded from `target_kos` and `_forced_promotion_key`
    promote_target_kos: bool = False   # at a TO_ACTIVE promote, benched Pokémon this option brings
                                       # up can KNOCK OUT opp's Active this turn (cheapest attack reaches
                                       # HP) — promote it to take the prize from the front (esp. an accelerator that also loads the bench)
    is_best_promote_target: bool = False  # at a TO_ACTIVE promote OR a SWITCH (my retreat's new-Active
                                       # pick), this option brings up board.best_promote_slot — most-built
                                       # ready wincon. `promote-the-powered-attacker` fires so it's the built Mega, not a bare copy
    is_ko_promote_target: bool = False  # at a promote/switch, this option brings up board.ko_promote_slot —
                                       # the benched body whose (boost-inclusive) attack KOs the opp Active
                                       # (`promote_ko_aware`). Backs `promote-the-ko-attacker`
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
    target_on_path: bool = False        # Tier-3 (ADR-0040): this damage/snipe target sits on MY
                                        # cheapest Prize Path — its KO advances the MATCH win
                                        # (`snipe-on-the-path`); False when the path is unknown
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
    promote_target_on_their_path: bool = False  # Tier-3 Path Denial (ADR-0040): this promote/switch
                                        # candidate sits on THEIR cheapest path — bringing it up walks
                                        # it into the KO they want (`dont-promote-onto-their-path`)
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
    hand_size_relief: float = 0.0  # REPORTING-ONLY (hand-disruption grill ruling, 2026-07-19): the signed
                                 # incoming-damage delta of a `hand_disruption` refresh against a hand-size
                                 # attacker in the opponent's forward line — `forward_incoming_damage` now
                                 # vs at the card's redraw count (+ = damage DENIED off my Active, − = a
                                 # refill that ARMS them). NOT in `score` — inert telemetry that makes the
                                 # calc visible while the flat +25/+18 rungs still drive; promotion (ruling
                                 # 1a/2a: marginal vs my KO, retire the rungs) waits on corpus evidence.
    evolve_shadow: float = 0.0   # REPORTING-ONLY (evolve-valuation grill, 2026-07-15): the SHADOW
                                 # evolve-value oracle's output for an EVOLVE option (common/evolve_value.py)
                                 # — the marginal Δ need-coverage the evolve produces. NOT in `score`; the
                                 # baseline_evolution rungs still decide. Swap gated on the corpus family
                                 # (test_evolve_valuation_corpus.py). 0.0 off an EVOLVE option.
    promote_retreat_shadow: float = 0.0  # REPORTING-ONLY (promote/retreat grill, 2026-07-22): the SHADOW
                                 # promote/retreat value oracle's output for a TO_ACTIVE/SWITCH option
                                 # (common/promote_retreat_value.py) — the two-sided window-rollout diff. NOT
                                 # in `score`; the baseline_promote/baseline_retreat rungs still decide. 0.0
                                 # off a promote/retreat option.


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
    plan_candidates: list | None = None  # the develop-rollout rung's ranked end-boards (Phase 1): top-K
                                     # {step, value, why, committed?, greedy?} sorted by value desc, so a
                                     # correction reader sees WHAT the rung out-scored, not just its pick.
                                     # Sparse: None unless the develop rung fired — keeps a non-develop
                                     # record byte-identical to the pre-rung wire format
    discard_shadow: dict | None = None  # the DISCARD keep-cost SHADOW (shadow-equations ruling,
                                     # 2026-07-19): the card-worth oracle's per-candidate working
                                     # (worth/gates/keep) + its pick + the agreement bit vs the tuned
                                     # `_DISCARD` ladder, which stays the decider. Deciding NOTHING —
                                     # the evidence bridge for the discard convergence (seam D).
                                     # Sparse: None off a real discard choice
    refresh_shadow: dict | None = None  # the REFRESH-SHED keep-value v2 MAGNITUDE shadow (ADR-0065
                                     # WP-N4b): v1's Σ keep_cost (`_refresh_shed_keepcost`) beside
                                     # v2's whole-hand assignment marginal (`needs.set_keep_v2`) + the
                                     # resulting refresh swings and the SIGN-agreement bit (does
                                     # swapping the shed flip play/don't-play?). Deciding NOTHING — the
                                     # sets-not-sums evidence the refresh swap rides. Sparse: None off
                                     # a real refresh PLAY option / mid-sim
    attach_shadow: dict | None = None   # the ENERGY-ATTACH valuation shadow (attach-valuation-grill-
                                     # spec.md "Grill rulings — 2026-07-21"; the fourth shadow): every
                                     # energy-attach option priced in one currency — the marginal
                                     # readiness the attach buys, the value of the line it advances
                                     # (role-gated), the burst-waste of a discard-EOT Energy — plus the
                                     # pick (`eq_pick`) and the agreement bit vs the shipped rungs'
                                     # `chosen`. A Pokémon Tool ABSTAINS (Ruling 3: not Energy). Deciding
                                     # NOTHING — sparse: None off a real attach choice / mid-sim
    promote_retreat_shadow: dict | None = None  # the PROMOTE/RETREAT value shadow (promote-retreat-grill-
                                     # spec.md §Settled design; the fifth shadow): every promote/retreat
                                     # option's two-sided window-rollout total (common/promote_retreat_value.py)
                                     # + the pick (`eq_pick`) and the agreement bit vs the shipped rungs'
                                     # `chosen`. DECIDES NOTHING — sparse: None off a TO_ACTIVE/SWITCH select
                                     # (< 2 options) / mid-sim. The swap-ranking sweep reads its disagreement rows.
    threat_shadow: dict | None = None   # the DOOM keep-worst-case SHADOW (Threat-Clock unification
                                     # S1b, docs/plans/opponent-value-equation-unification.md): the
                                     # incumbent `active_doomed` (worst-case, the decider) beside its
                                     # `incoming(t=1)`-curve re-expression (`combat.doomed_incoming`,
                                     # ceiling policy) + the agreement bit. Surfaces the two known
                                     # divergences (current-form affordability gate; omitted
                                     # hand_size_attacker forward counter) for the survival-swap
                                     # adjudication. Deciding NOTHING — sparse: None mid-sim / no live
                                     # my-Active vs opp-Active


class Pilot(PlannerMixin, ObjectivesMixin, GustMixin, FetchMixin, ShuffleRefreshMixin, ToolMixin):
    """Composed from the Turn Planner — whose sound top rung IS the Lethal Solver (ADR-0030/0031/0037,
    one entry point) — the Tier-3 Match Objectives (ADR-0040: the KO Race), and four doctrine mixins
    (gust / fetch / shuffle-refresh / tool) — each contributes its closed-form Pilot-side methods;
    the shared Sense→Plan→Score→Act core is defined here. See common/strategy/."""

    def __init__(self, strategy, deck, *, general_strategy=None, overrides=None, stats=None,
                 functions=None, effects=None,
                 search_budget=0, scout=None, briefs=None, posture=True, lethal_verify=False,
                 planner_engine_rank=False, planner_key_threat=False, lethal_family=False,
                 lethal_veto=False, objectives_race=False,
                 objectives_path=False, objectives_phases=False, gamble_lines=False,
                 snipe_prize_redundant=False, snipe_prize_reach=False, forced_promotion=False,
                 value_model=None,
                 match_planner_steer=False, forgo_ko=False, prize_economy_fetch=True,
                 lethal_seed_exact=True, promote_ko_aware=False, boost_lethal=False,
                 retreat_enabler_lethal=False, disruptor_lock_maneuver=False,
                 evolving_wincon_priority=True, matchup_targeting=True,
                 ko_target_whiff=False, opp_resource_reads=False,
                 enabler_item_composer=False, play_accel_lethal=False,
                 develop_rollout=False, discard_keep_value=False, needs_keep_value=False,
                 leaf_hand_value=False):
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
        self.evolving_wincon_priority = evolving_wincon_priority  # kill-switch (default ON): at a DAMAGE snipe
                                                        # with a developing higher-prize wincon pre-evo on the
                                                        # opp bench, the current-attacker rungs stand down so
                                                        # their SUM can't bury `snipe-the-evolving-threat` (ms
                                                        # 85164131 f22). Backs `Board.evolving_wincon_on_bench`
        self.match_planner_steer = match_planner_steer  # ADR-0045 kill-switch (S3): the Match Planner's
                                                        # Game Plan directed goal biases the Turn Planner's
                                                        # candidate ranking (sub-prize, confidence-scaled).
                                                        # Default OFF — byte-identical; matured via ladder
        self.forgo_ko = forgo_ko                        # ADR-0045 kill-switch (S4): forgo a NON-winning KO
                                                        # under the tight sound gate ("don't wake the giant").
                                                        # Default OFF — the riskiest lever, ladder-gated
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
        self.play_accel_lethal = play_accel_lethal      # kill-switch (armed-ON): count a PLAY-based energy
                                                        # accelerator (a Trainer tagged energy_accel that
                                                        # attaches a Basic on play — Crispin) as +1 attach in
                                                        # the ko_for_prizes budget, ON TOP of the manual
                                                        # attach. Min-bound: only when the Trainer is playable
                                                        # NOW (Supporter needs a free slot) and a Basic Energy
                                                        # is still fetchable. An ATTACK-based accel (a Pokemon)
                                                        # is NEVER counted (using it IS the attack)
        self.discard_keep_value = discard_keep_value    # ADR-0065 seam-D kill-switch (default OFF): the
                                                        # card-worth equation DECIDES a forced discard in
                                                        # place of the `_DISCARD` ladder. OFF = the ladder
                                                        # decides and the equation only shadows (telemetry).
        self.leaf_hand_value = leaf_hand_value          # ADR-0065 WP-N5b kill-switch (default OFF): the
                                                        # develop-rung LEAF's actionable-resource term —
                                                        # readiness CONSUMES the needs module (the hand's
                                                        # slot coverage), the board-state-valuation fold.
                                                        # Needs the sim to plumb my end-of-turn hand into
                                                        # the (opponent-perspective) end obs. Gated on the
                                                        # leaf-lab bench (SOLE-top / distinct-values / Gate 0).
        self.needs_keep_value = needs_keep_value        # ADR-0065 WP-N4 kill-switch (default OFF): the
                                                        # keep-value v2 NEEDS-ASSIGNMENT (`_needs_v2`,
                                                        # `eq2_pick`) decides the forced discard in place of
                                                        # v1 — the per-family swap for the cleared discard
                                                        # family (agree_v2 12/12 + the duplicate-pair flip).
                                                        # Takes precedence over `discard_keep_value`; OFF =
                                                        # v1 decides (or the ladder) and v2 only shadows.
        self.develop_rollout = develop_rollout          # develop-rung Phase 1 kill-switch (default OFF):
                                                        # the within-turn rollout rung — on a develop turn
                                                        # (plan_turn else None) where greedy is weak/indifferent,
                                                        # sim each candidate first action to end-of-turn and
                                                        # commit the best leaf. OFF = byte-identical
        self._phase_prev = None                         # the hysteresis memory (Schmitt trigger) —
                                                        # the ONE stateful bit of the phase label
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
        from common.strategy.combat import CombatMath
        self.combat = CombatMath(stats, functions, transients=self._transients)   # the KO oracle
                                                        # (ADR-0052): the one closed-form combat home;
                                                        # the Pilot's damage/KO methods delegate to it
        self._turn_boosts = TurnBoostTracker(            # this-turn flat damage-boost plays (Power Pro
            lambda cid: self.stats.get(cid) if (self.stats and cid is not None) else None)
                                                        # class) — OHKO-line model's play half
        self._fetch_cache: dict = {}                    # memo: search card id -> deck ids it can fetch
        self._chain_target_cache: dict = {}             # memo: tutor card id -> FULL-scope deck fetch
                                                        # targets (the tutor-chain graph leg, seam C)
        self._derived_accel_cache = None                # memo: derived bench-accel body ids (deck-fixed)
        self._discard_fuel_cache = None                 # memo: energy types a discard-source accel attack
                                                        # wants IN the discard (deck-fixed; Aura Jab class)
        self._turn_plan = None                          # ADR-0031 turn-scoped committed plan:
                                                        # (fingerprint, TurnLine|None); re-planned on a reveal
        self._develop_candidates_pending = None         # develop-rung Phase 1: the last rung's ranked
                                                        # end-boards, lifted onto the Decision's plan_candidates
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
                            posture=self._posture_record(board),
                            objectives=self._objectives_trace(board), win_prob=self._win_prob(board),
                        game_plan=self._game_plan_record(board),
                            lethal_refuted=self._lethal_refutes)
        planned = self.plan_turn(obs, select, board, options, traces)  # ADR-0037: the ONE planning
        refuted = self._lethal_refutes                  # entry — win rung (take the win now) first, then
        if planned is not None:                         # the below-win Goal Ladder. Refutes kept on every
            return Decision(chosen=planned.next_step,   # Decision shape so a lethal_verify drop is countable
                            options=traces, read=board.read, planned=planned,
                            posture=self._posture_record(board),
                            objectives=self._objectives_trace(board), win_prob=self._win_prob(board),
                        game_plan=self._game_plan_record(board),
                            plan_candidates=(self._develop_candidates_pending   # develop-rung Phase 1: the
                                             if planned.goal == "develop" else None),  # rung's ranking (sparse)
                            gamble=getattr(self, "_gamble_trace", None),
                            attach_shadow=self._attach_shadow(obs, select, board, options, traces,
                                                              planned.next_step),  # attaches often route here
                            lethal_refuted=refuted, lethal_lost=self._lethal_lost)
        max_count = select.get("maxCount", 0)
        # Primary key = score; secondary key breaks an EXACT tie toward an attach feeding a needy Line
        # body (ep82867148 f87). decide()-only ordering nicety, W-route-invisible, never enters weight fit.
        by_score = sorted(range(len(options)),
                          key=lambda i: (traces[i].score, traces[i].attach_to_needy_line), reverse=True)
        order = self._finish_turn_last(obs, board, options, traces, by_score, max_count,
                                       select.get("context"))
        # Telemetry legibility (ADR-0019): flag when `chosen` did NOT come from argmax(score), so a
        # trace reader doesn't misread "top-score not chosen" as a scoring bug. `reordered` = attack-last
        # resequenced the menu; `grabbed` = the greedy multi-pick chose a set by dynamic gap-scoring.
        reordered = order != by_score
        grabbed = max_count > 1 and select.get("context") in _GRAB_CONTEXTS
        # ADR-0065 SWAP: at a forced discard the card-worth equation DECIDES — the `picks`
        # cheapest-to-lose cards — replacing the tuned `_DISCARD` ladder. Precedence (each a
        # kill-switch, OFF falls through): WP-N4 `needs_keep_value` (the v2 needs-assignment,
        # `_needs_v2`/`eq2_pick`) > seam-D `discard_keep_value` (v1, `_discard_equation_pick`) >
        # the ladder. Both OFF leaves the ladder deciding and both equations only shadow.
        eq_discard = None
        if select.get("context") == _DISCARD and max_count > 0:
            if getattr(self, "needs_keep_value", False):
                eq_discard = self._discard_needs_pick(obs, select, board, options, max_count)
            elif getattr(self, "discard_keep_value", False):
                eq_discard = self._discard_equation_pick(obs, select, board, options, max_count)
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
        return Decision(chosen=chosen, options=traces, read=board.read, lethal_refuted=refuted,
                        posture=self._posture_record(board),
                        objectives=self._objectives_trace(board), win_prob=self._win_prob(board),
                        game_plan=self._game_plan_record(board),
                        gamble=getattr(self, "_gamble_trace", None),
                        discard_shadow=self._discard_shadow(obs, select, board, options, chosen),
                        refresh_shadow=self._refresh_shed_shadow(obs, select, board, options, traces, chosen),
                        attach_shadow=self._attach_shadow(obs, select, board, options, traces, chosen),
                        promote_retreat_shadow=self._promote_retreat_record(obs, select, board, options, traces, chosen),
                        threat_shadow=self._threat_shadow(obs, board),
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
            """This ATTACK is a KO of the opponent's ACTIVE that takes my LAST prize — it wins the
            match, so it goes first (nothing to develop for). Conservative: gated on `active_can_ko`
            (my Active actually KOs the opp Active this turn), so a KO-class score coming ONLY from a
            bench SNIPE (which credits the opp Active's prize value for a lower-prize benched KO — the
            ep83661649 f54 bug: a 1-prize Staryu snipe read as a 3-prize Active KO) falls back to
            develop-first. The snipe-KO is still taken this turn, just AFTER the beneficial attach —
            no prize forfeited, and the attach toward Nebula Beam lands (attack-last)."""
            if options[i].get("type") != _ATTACK or traces[i].tactical < KO_SCORE:
                return False
            return (board.my_prizes_remaining > 0 and board.active_can_ko
                    and self._prize_value(self._opp_active(obs)) >= board.my_prizes_remaining)

        def _cost_discard(i: int) -> bool:
            cid = traces[i].card_id
            return bool(self.functions) and cid is not None and "cost_discard" in self.functions.tags(cid)

        def _is_gust_card(i: int) -> bool:
            cid = traces[i].card_id
            return bool(self.functions) and cid is not None and "gust" in self.functions.tags(cid)

        def _gust_enables_ko(i: int) -> bool:                        # a gust that fired a KO-converting rule
            return any(getattr(h, "id", None) in ("gust-for-the-ko", "gust-for-the-loaded-equal-ko")
                       for h, _w in traces[i].fired)

        def _retreat_walls_the_line(i: int) -> bool:                 # the sacrificial-wall maneuver step 1
            return any(getattr(h, "id", None) == "retreat-to-wall-the-line" for h, _w in traces[i].fired)

        def _is_supporter(i: int) -> bool:
            cid = traces[i].card_id
            st = self.stats.get(cid) if (self.stats and cid is not None) else None
            return bool(st and st.is_supporter)

        def _is_shuffle_refresh(i: int) -> bool:                     # a hand-nuke Supporter (shuffle_hand)
            cid = traces[i].card_id
            return bool(self.functions) and cid is not None and "shuffle_hand" in self.functions.tags(cid)

        def _tier(i: int) -> int:
            o = options[i]
            t = o.get("type")
            if t in (_ATTACH, _PLAY, _RETREAT) and traces[i].tactical >= KO_SCORE:  # a lethal play/attach
                return 0    # unlocks a KO, or a gust/retreat-to-lethal swap — take the win, don't dig first (REQ-GUST-0001)
            if t == _PLAY and _gust_enables_ko(i):                   # a KO-enabling gust: `gust-for-the-ko`
                return 0                                             # fires only when the gust-KO takes MORE
                                                                     # prizes than any menu attack (its own gate),
                                                                     # so take the gust-setup first, then KO the
                                                                     # dragged-up body — not tier-1 Supporter filler,
                                                                     # nor tier-4 behind the KO it out-values (f79/f81)
            if t == _RETREAT and _retreat_walls_the_line(i):         # retreat-to-promote the sacrificial
                return 0                                             # item-lock wall (dragapult f32/f20): the
                                                                     # retreat is STEP 1 of the maneuver, ahead
                                                                     # of a free evolve / Item strip; the
                                                                     # promote + item-lock + develop follow on
                                                                     # later frames via their own rungs
            if t == _ATTACK and _wins_now(i):                        # a game-winning KO: take the win now,
                return 0                                             # don't dig/develop first (ep83037962 f78)
            if t in (_ATTACK, _END, _RETREAT):                       # turn-ender / swaps the Active
                return 4
            if t == _EVOLVE and o.get("inPlayArea") == _ACTIVE and ko_available:
                return 4                                             # would forfeit an available KO
            if t == _PLAY and _is_gust_card(i) and board.active_can_ko:
                return 4                                             # a gust SWAPS the defender: never ahead of
                                                                     # a KO of the ACTIVE it would forfeit
                                                                     # (ep83456015 f38: 3-prize Nebula ≻ gust).
                                                                     # The old test was ANY menu KO — but a KO
                                                                     # coming from a bench SPREAD is not
                                                                     # forfeited by swapping the defender, and it
                                                                     # buried Boss's Orders (+50, the top-scored
                                                                     # option) below a setup Supporter that ate
                                                                     # the one-per-turn slot (dragapult f81)
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
        ctx = self._context(obs, select, board, option)   # built first: the matchup snipe steer
                                                           # respects its ADR-0044 redundancy flags
        tactical = (self._tactical(obs, board, option)
                    + self._snipe_tera_veto(ctx)      # card fact: a benched Tera takes NO damage
                    + self._refresh_swing_tactical(obs, board, ctx)
                    + self._grab_refresh_draw_tactical(board, ctx)
                    + self._denial_play_tactical(board, ctx)
                    + self._denial_target_tactical(obs, select, board, option)
                    + self._snipe_matchup_tactical(obs, select, board, option, ctx)
                    + self._gust_tactical(obs, select, board, option)
                    + self._gust_target_tactical(obs, select, board, option)
                    + self._gust_stall_target_tactical(obs, select, board, option)
                    + self._attach_lethal_tactical(obs, select, board, option)
                    + self._boost_lethal_tactical(obs, select, board, option)
                    + self._retreat_to_lethal_tactical(obs, board, option)
                    + self._grab_lethal_tactical(obs, select, board, option)
                    + self._grab_enabler_lethal_tactical(obs, select, board, option)
                    + self._grab_retreat_tool_lethal_tactical(obs, select, board, option)
                    + self._attach_retreat_tool_lethal_tactical(obs, select, board, option))
        hyps = (*self.general.hypotheses, *self.strategy.hypotheses)
        fired = [(h, self._weight(h)) for h in hyps if _fires(h, ctx)]
        score = sum(w for _, w in fired) + tactical
        return OptionTrace(index=index, score=score, plan=ctx.plan, card_id=ctx.card_id,
                           fired=fired, tactical=tactical,
                           attach_to_needy_line=ctx.attach_target_is_line_member and ctx.attach_target_needs,
                           hand_size_relief=self._hand_size_relief(obs, ctx),   # REPORTING-ONLY, not in `score`
                           evolve_shadow=self._evolve_shadow(obs, ctx, option),  # REPORTING-ONLY (shadow oracle)
                           promote_retreat_shadow=self._promote_retreat_shadow(obs, select, ctx, option))  # REPORTING-ONLY

    def _evolve_shadow(self, obs: dict, ctx, option: dict) -> float:
        """The SHADOW evolve-value oracle's output for an EVOLVE option (common/evolve_value.py) —
        the marginal Δ need-coverage the evolve produces. REPORTING-ONLY, not in `score`; 0.0 off an
        EVOLVE. Reads the board into `EvolveInputs`, so the equation stays a pure function."""
        if ctx.option_type != _EVOLVE or ctx.card_id is None or self.functions is None:
            return 0.0
        body = self._evolve_body(obs, option)
        body_cid = body.get("id") if body else None
        body_energies = (body.get("energies") or []) if body else []
        rtags = self.functions.tags(ctx.card_id)
        btags = self.functions.tags(body_cid) if body_cid is not None else []
        can_attack = (ctx.card_is_wincon
                      and self._typed_can_pay(self._valued_attack_types(ctx.card_id), body_energies))
        inp = EvolveInputs(
            result_has_draw=("draw" in rtags or "dig" in rtags),
            body_has_draw=("draw" in btags or "dig" in btags),
            result_is_wincon=ctx.card_is_wincon,
            result_is_line_preevo=ctx.card_is_line_preevo,
            result_can_attack_now=can_attack,
            body_has_energy=bool(body_energies),
            body_doomed_affordable=self._body_doomed_affordable(obs, ctx.board))
        return evolve_value(inp).total

    def _promote_retreat_shadow(self, obs: dict, select: dict, ctx, option: dict) -> float:
        """The SHADOW promote/retreat value oracle's output for a TO_ACTIVE/SWITCH option
        (common/promote_retreat_value.py) — the two-sided window-rollout diff (grill 2026-07-22).
        REPORTING-ONLY, not in `score`; 0.0 off a promote/retreat select. Reads the SAME Context flags
        the `baseline_promote` ladder consumes into `PromoteRetreatInputs`, so the equation stays a pure
        function. Readiness is sourced DIRECTLY off the option body (`_promote_can_attack`) rather than
        the TO_ACTIVE-scoped `ctx.promote_target_can_attack`, so the readiness leg is live on SWITCH
        retreats too. The retreat-side terms — the current Active's Energy cost and its forgone attack
        (`stay_yield`, ruling 1) — are wired for a voluntary SWITCH (`_retreat_side`). The closure
        probability (`fetch_enables_p`, spec §4's gamble-Outcome-Class assembly) remains the one 1-exchange
        hook at its default until that shared machinery is pointed at the promote target."""
        if ctx.select_context not in (_TO_ACTIVE, _SWITCH):
            return 0.0
        my_index = (obs.get("current") or {}).get("yourIndex", 0)
        if option.get("playerIndex") not in (None, my_index):
            return 0.0            # a Boss's-gust target (opponent body) — the gust-value equation's turf
        board = ctx.board
        tags, roles = (ctx.tags or []), (ctx.roles or [])
        is_switch = ctx.select_context == _SWITCH
        retreat_worth, stay_yield = self._retreat_side(obs) if is_switch else (0.0, 0.0)
        can_attack = self._promote_can_attack(obs, select, option)
        fetch_p = (self._promote_fetch_p(obs, select, board, option)
                   if (ctx.card_is_wincon and not can_attack) else 0.0)
        item_lock_live = self._item_lock_live(tags, board)   # Sweep #2 Finding A: early-game gate
        inp = PromoteRetreatInputs(
            is_switch=is_switch,
            can_attack_now=can_attack,
            is_wincon=ctx.card_is_wincon,
            is_best_target=ctx.is_best_promote_target,
            is_staller=("opener" in tags or item_lock_live),
            is_accelerator=("accel_source" in roles),
            bench_underpowered=(board.bench_wincon_underpowered and board.basic_energy_in_deck),
            provable_ko=(ctx.promote_target_kos or ctx.is_ko_promote_target),
            prize_value=ctx.card_prize_value,
            opp_can_punish=not board.opp_cannot_punish_wincon,
            opp_prizes_remaining=board.opp_prizes_remaining,
            on_their_path=ctx.promote_target_on_their_path,
            is_item_lock=item_lock_live,
            fetch_enables_p=fetch_p,
            retreat_energy_worth=retreat_worth,
            stay_yield=stay_yield)
        return promote_retreat_value(inp).total

    def _promote_retreat_record(self, obs: dict, select: dict, board: Board, options: list,
                                traces: list, chosen: list):
        """The promote/retreat value shadow (the fifth shadow), two emission SITES. DECIDES NOTHING;
        None mid-sim (`self._planning`) — the disagreement rows the swap-ranking sweep reads.

        - **pick** (TO_ACTIVE/SWITCH own-retreat select): every option's two-sided window-rollout total
          (per-option on `OptionTrace.promote_retreat_shadow`) + the top pick + the agreement bit vs the
          shipped rungs' `chosen`. None off a <2-option select or a Boss's-gust target (opponent bodies).
        - **whether** (MAIN select with a native RETREAT option): the value of retreating the Active into
          the BEST benched body (`_retreat_action_value`, ruling 1 — `stay_yield` live here) + the
          SIGN-agreement bit (retreat-worth-it vs did the ladder retreat). This is where the Group-A
          "whether to retreat" mass lives — invisible to the pick site."""
        if self._planning:
            return None
        ctx = select.get("context")
        my_index = (obs.get("current") or {}).get("yourIndex", 0)
        if ctx in (_TO_ACTIVE, _SWITCH):
            if len(options) < 2 or (options and options[0].get("playerIndex") not in (None, my_index)):
                return None                              # <2 options, or a gust-target (opponent) select
            rows = [{"i": i, "v": round(t.promote_retreat_shadow, 2)} for i, t in enumerate(traces)]
            eq_pick = max(range(len(traces)), key=lambda i: traces[i].promote_retreat_shadow)
            return {"site": "pick", "eq": rows, "eq_pick": eq_pick, "picks": sorted(chosen or []),
                    "agree": eq_pick in (chosen or [])}
        if ctx == _MAIN:
            retreat_idx = next((i for i, o in enumerate(options) if o.get("type") == _RETREAT), None)
            if retreat_idx is None:
                return None                              # no retreat action on the menu
            # Sweep #2 Finding B1: when the Active can KO the opp Active NOW, staying-and-KOing and
            # retreating-into-a-bigger-KO+snipe are BOTH on the table — a KO-vs-KO comparison the Turn
            # Planner owns (ruling 5), and the sub-lethal shadow cannot adjudicate (ep82717711-37's
            # correct retreat-to-finisher scores the SAME +30 as ep82750161-59's wrong pivot). The
            # shadow RECUSES itself rather than guess.
            if board.active_can_ko:
                return None
            value = self._retreat_action_value(obs, board)
            if value is None:
                return None                              # no benched body to retreat into
            worth_it = value > 0.0
            ladder_retreated = retreat_idx in (chosen or [])
            return {"site": "whether", "retreat_idx": retreat_idx, "value": round(value, 2),
                    "worth_it": worth_it, "ladder_retreated": ladder_retreated,
                    "agree": worth_it == ladder_retreated}
        return None

    def _retreat_action_value(self, obs: dict, board: Board) -> float | None:
        """Ruling 1's whether-to-retreat value at a MAIN menu: the BEST two-sided window-rollout total
        over every benched body the Active could retreat into, MINUS the retreat Energy and the Active's
        forgone attack (`_retreat_side` — constant across destinations). > 0 ⇒ retreating out-earns
        staying-and-attacking. None with no benched body. The destination readiness/exposure legs are
        computed off each body directly (valid without a per-option Context)."""
        me = self._my_player(obs)
        bench = (me.get("bench") or []) if me else []
        wincon = self._wincon_set()
        best_slot = board.best_promote_slot
        retreat_worth, stay_yield = self._retreat_side(obs)
        best = None
        for i, b in enumerate(bench):
            bid = b.get("id") if b else None
            if bid is None:
                continue
            stat = self.stats.get(bid) if self.stats else None
            tags = self.functions.tags(bid) if self.functions else []
            can_attack = bool(stat and stat.minAttackCost is not None
                              and len(b.get("energies") or []) >= stat.minAttackCost)
            item_lock_live = self._item_lock_live(tags, board)   # Sweep #2 Finding A: early-game gate
            inp = PromoteRetreatInputs(
                is_switch=True,
                can_attack_now=can_attack,
                is_wincon=(bid in wincon),
                is_best_target=(best_slot == (_BENCH, i)),
                is_staller=("opener" in tags or item_lock_live),
                is_accelerator=("accel_source" in self._roles_of(bid)),
                bench_underpowered=(board.bench_wincon_underpowered and board.basic_energy_in_deck),
                provable_ko=(board.ko_promote_slot == (_BENCH, i)),
                prize_value=self._prize_value(b),
                opp_can_punish=not board.opp_cannot_punish_wincon,
                opp_prizes_remaining=board.opp_prizes_remaining,
                on_their_path=False,
                is_item_lock=item_lock_live,
                retreat_energy_worth=retreat_worth,
                stay_yield=stay_yield)
            total = promote_retreat_value(inp).total
            if best is None or total > best:
                best = total
        return best

    def _promote_fetch_p(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """Ruling 3 (EV over closure): P that the closure READIES an unready wincon promote target THIS
        turn. Interim = the CERTAIN one-attach-short accel case, reusing the body-agnostic
        `_active_attack_payable_via_accel` (a playable `tutor_energy` in hand + a Basic Energy the deck
        holds → one accel-attach reaches the cheapest attack) pointed at the promote body — sound and
        fail-CLOSED (0.0 on unknowns / multi-attach-short). The probabilistic MIDDLE (drawing a
        not-yet-held enabler over the turn's remaining dig) is deferred to the shared self reachable-attach
        affordability oracle (the f70 finding in valuation-systems-coverage-review.md, symmetric to
        ADR-0064 `reachable_incoming`); until it lands this returns 1.0/0.0, never a partial."""
        poke = self._option_pokemon(obs, select, option)
        if not poke:
            return 0.0
        me = self._my_player(obs)
        state = obs.get("current") or {}
        payable = self._active_attack_payable_via_accel(
            me, poke, bool(state.get("supporterPlayed")), board.basic_energy_in_deck)
        return 1.0 if payable else 0.0

    def _item_lock_live(self, tags, board: Board) -> bool:
        """Whether an `item_lock` body's disruption is worth crediting NOW (Sweep #2 Finding A). Itchy
        Pollen denies the opponent's SETUP Items — valuable while they still depend on them (early game),
        near-worthless once they're built. Proxied by `board.turn <= _ITEM_LOCK_EARLY_TURN`; a candidate
        to replace with a real opponent-Item-reliance read. Without this the tempo/staller credit fired
        UNCONDITIONALLY (a flat +27 retreat-into-Budew on every dragapult frame — ep86091435 f30/35/96)."""
        return "item_lock" in tags and board.turn <= _ITEM_LOCK_EARLY_TURN

    def _promote_can_attack(self, obs: dict, select: dict, option: dict) -> bool:
        """Context-agnostic readiness for the shadow: the option's benched body can use an attack this
        turn (Energy >= its cheapest attack cost). Unlike `ctx.promote_target_can_attack` (which
        fail-closes off TO_ACTIVE), this is valid on a SWITCH retreat too — the readiness leg must live
        for the voluntary-retreat family. Same minAttackCost logic the ladder's TO_ACTIVE flag uses."""
        if select.get("context") not in (_TO_ACTIVE, _SWITCH):
            return False
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (poke and stat and stat.minAttackCost is not None):
            return False
        return len(poke.get("energies") or []) >= stat.minAttackCost

    def _retreat_side(self, obs: dict) -> tuple[float, float]:
        """The voluntary-retreat side terms for the shadow: (retreat_energy_worth, stay_yield). The
        Energy the current Active pays to retreat (its effective cost x ENERGY_TIER — lost on retreat),
        and the sub-lethal attack it FORGOES by leaving (ruling 1), priced by the SAME `my_yield` term
        the equation applies to a promote target so the currency is consistent. Both 0.0 on an unknown
        Active. A KO the Active could land by staying is the planner's (ruling 5); this reads only the
        readiness band, so it never carries a lethal magnitude."""
        from common.card_worth import ENERGY_TIER
        ma = self._my_active(obs)
        if not ma or not self.stats:
            return 0.0, 0.0
        retreat_worth = self._effective_retreat_cost(ma) * ENERGY_TIER
        aid = ma.get("id")
        can_attack = self._typed_can_pay(self._valued_attack_types(aid), ma.get("energies") or [])
        is_wincon = aid is not None and aid in self._wincon_set()
        stay = promote_retreat_value(PromoteRetreatInputs(
            can_attack_now=can_attack, is_wincon=is_wincon, is_best_target=is_wincon)).my_yield
        return retreat_worth, stay

    def _my_active(self, obs: dict) -> dict | None:
        """My Active Pokémon dict (mirror of `_opp_active`)."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        if not (0 <= yi < len(players)) or players[yi] is None:
            return None
        actives = players[yi].get("active") or []
        return actives[0] if actives and actives[0] else None

    def _effective_retreat_cost(self, ma: dict | None) -> int:
        """The Active's Retreat Cost in Energy, minus any ATTACHED retreat-reduction Tool (Air Balloon
        −2, `retreatReduction`) — the count of Energy a retreat discards. READ-ONLY (mirrors the cost
        arithmetic of `_can_retreat` without its affordability verdict); 0 on an unknown stat."""
        if not ma or not self.stats:
            return 0
        stat = self.stats.get(ma.get("id"))
        if stat is None:
            return 0
        cost = getattr(stat, "retreatCost", 0)
        for tool in (ma.get("tools") or []):
            tid = tool.get("id") if isinstance(tool, dict) else tool
            tstat = self.stats.get(tid) if tid is not None else None
            cost -= getattr(tstat, "retreatReduction", 0) if tstat is not None else 0
        return max(0, cost)

    def _valued_attack_types(self, cid) -> tuple:
        """The TYPED cost (per-slot EnergyType codes; 0 = colourless) of a card's biggest-damage attack
        — the payoff attack readiness is measured against. () when unknown."""
        stat = self.stats.get(cid) if self.stats else None
        if not stat or not getattr(stat, "attacks", None):
            return ()
        cands = [a for a in (self.stats.attack(aid) for aid in stat.attacks) if a is not None]
        if not cands:
            return ()
        pick = max(cands, key=lambda a: (getattr(a, "damage", 0) or 0, getattr(a, "cost", 0) or 0))
        return tuple(getattr(pick, "energyTypes", ()) or ())

    @staticmethod
    def _typed_can_pay(cost_types: tuple, have) -> bool:
        """Greedy typed affordability: a coloured cost slot needs a distinct matching-type Energy, a
        colourless slot any leftover. False for an unknown/empty cost."""
        if not cost_types:
            return False
        have = list(have)
        for t in cost_types:
            if t == 0:
                continue
            if t in have:
                have.remove(t)
            else:
                return False
        return len(have) >= sum(1 for t in cost_types if t == 0)

    def _body_doomed_affordable(self, obs: dict, board) -> bool:
        """SCOPED doom read (evolve carve-out only): the opponent's Active can ACTUALLY KO next turn —
        `active_doomed` AND their Active can afford its biggest attack NOW (count check). Deliberately
        NOT the global affordability-blind doom oracle (docs/todo/incoming-affordability.md)."""
        if not board.active_doomed:
            return False
        oa = self._opp_active(obs)
        st = self.stats.get(oa.get("id")) if (oa and self.stats) else None
        cost = getattr(st, "maxDamageCost", None) if st else None
        return cost is not None and len(oa.get("energies") or []) >= cost

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
        eff = _EFFICIENCY * self._attack_cost(attack_id, 0)   # cheaper of equal outcomes wins
        recover = self._recover_units(attack_id, dmg_ctx, board, obs)  # usable re-attachable fuel (Aura Jab)
        lock_cost = self._lock_sequence_cost(attack_id, board)    # damage the lock actually forfeits
        snipe_ko = self._snipe_ko_prizes(board.opp_bench, self._rider_snipe(attack_id))
        spread_ko = self._spread_ko_prizes(board.opp_bench, self._rider_spread(attack_id))
        bench_ko = snipe_ko + spread_ko              # direct opp-bench KO prizes (single-target rider +
                                                     # distributable spread; disjoint — no attack has both)
        if hp and dmg >= hp:
            if self._is_simultaneous_draw(board, attack_id, self._prize_value(opp)):
                return dmg - eff                            # a simultaneous double-KO is a DRAW, not a win
            bonus = bench_ko or (self._bench_snipe_bonus(board, attack_id)   # bench-KO is a full prize;
                                 + self._bench_spread_bonus(board, attack_id))  # else a sub-prize chip tiebreak
            bonus += min(_RECOVER_KO_CAP, _RECOVER_KO * recover)  # sub-prize: the KO that also develops
            bonus -= _LOCK_KO if lock_cost > 0 else 0             # sub-prize: keep the nuke off cooldown
            return KO_SCORE + self._prize_value(opp) - eff + bonus
        if bench_ko:                                        # Active survives, but a snipe rider / a
            return KO_SCORE + bench_ko - eff                # distributable spread KOs benched Pokémon — a PRIZE this turn
        race = self._race_attack_tactical(obs, board, attack_id, dmg_ctx)   # Tier-3 KO Race (ADR-0040):
        if race is not None:                                # vs a standing wall the single hit is fake
            return (race - eff + _ENERGY_RECOVER * recover  # value — price the SEQUENCE (chip included,
                    - lock_cost                             # so no separate spread bonus here)
                    - (_RECOIL_DOOM if self._recoil_flips_doom(attack_id, obs, board) else 0)
                    + self._self_return_escape_credit(attack_id, board))
        if self.objectives_race:                            # honest coin pricing for RANKING (ADR-0039):
            lo = self.predicted_damage(self._my_active_id(obs), attack_id, opp, bound="min",
                                       context=dmg_ctx)
            hi = self.predicted_damage(self._my_active_id(obs), attack_id, opp, bound="max",
                                       context=dmg_ctx)
            if hi > lo:                                     # a coin/conditional CHIP ranks by its mean;
                dmg = (lo + hi) / 2                         # the KO test above and every sound path
                                                            # (Lethal floor / Incoming ceiling) untouched
        return (dmg - eff + _ENERGY_RECOVER * recover - lock_cost
                - (_RECOIL_DOOM if self._recoil_flips_doom(attack_id, obs, board) else 0)
                + self._bench_spread_bonus(board, attack_id)     # a non-KO spread still chips the Bench (pre-load)
                + self._self_return_escape_credit(attack_id, board))

    # --- KO-oracle delegates (ADR-0052): combat judgment lives in CombatMath; these wrappers
    # keep the Pilot-side signatures the mixins/doctrines call via `self`.
    def _snipe_ko_prizes(self, opp_bench, rider: int) -> int:
        return self.combat.snipe_ko_prizes(opp_bench, rider)

    def _best_ko_subset(self, items, budget: int) -> frozenset:
        return self.combat.best_ko_subset(items, budget)

    def _spread_ko_prizes(self, opp_bench, spread: int) -> int:
        return self.combat.spread_ko_prizes(opp_bench, spread)

    def _is_tera(self, card_id) -> bool:
        return self.combat.is_tera(card_id)

    def _prize_value(self, poke: dict | None) -> int:
        """Prizes a knockout yields — Mega ex 3, ex 2, else 1 (the KO oracle's read)."""
        return self.combat.prize_value(poke)

    def _attached_type_counts(self, target: dict) -> dict:
        return self.combat.attached_type_counts(target)

    def _attack_type_payable(self, aid, target: dict | None, *, extra_type=None,
                             extra_units: int = 0, wild_units: int = 0) -> bool:
        return self.combat.attack_type_payable(aid, target, extra_type=extra_type,
                                               extra_units=extra_units, wild_units=wild_units)

    def _can_ko(self, my_stat, defender: dict | None) -> bool:
        """My Active's CHEAPEST attack KOs `defender` (the oracle's `can_ko_cheapest`; the
        card-level minCostDamage fallback is retired, ADR-0052)."""
        return self.combat.can_ko_cheapest(my_stat, defender)

    def _active_can_ko(self, ma: dict | None, oa: dict | None) -> bool:
        """My Active's best AFFORDABLE attack KOs the opp Active (backs `Board.active_can_ko`)."""
        return self.combat.can_ko_affordable(ma, oa)

    def _opp_active_can_damage_us(self, ma: dict | None, oa: dict | None) -> bool:
        """Their Active can hurt mine with what it holds NOW (the energy-strip worth read)."""
        return self.combat.can_damage(oa, ma)

    def _active_maxed_kos(self, ma: dict | None, oa: dict | None) -> bool:
        """My Active's biggest attack, fully powered, would KO theirs (the conserve-the-burst read)."""
        return self.combat.maxed_kos(ma, oa)

    def _bench_snipe_bonus(self, board: Board, attack_id) -> float:
        return self.combat.bench_snipe_bonus(board.opp_bench, attack_id)

    def _bench_spread_bonus(self, board: Board, attack_id) -> float:
        return self.combat.bench_spread_bonus(board.opp_bench, attack_id)

    def _best_counter_slot(self, obs: dict, select: dict) -> tuple | None:
        """At a DAMAGE_COUNTER_ANY (ctx 14) placement select — one counter (10 dmg) per select, budget
        ``remainDamageCounter`` — the OPPONENT Pokémon to place THIS counter on: (1) if the remaining
        counters can complete one or more KOs (`_best_ko_subset` over the opp targets within the budget),
        place on the KO-set member closest to dying (finish it first, so the sequential per-counter
        greedy maximizes same-turn prizes); (2) else pre-load the lowest-remaining-HP opp target
        (concentrate toward a future KO). Returns (area, index, playerIndex) or None (off ctx 14 / no
        opponent target). A benched Tera takes no damage, so it's excluded (a phantom placement).
        Serves BOTH the Phantom Dive spread (DAMAGE_COUNTER_ANY, budget = `remainDamageCounter`) and a
        counter-mover's ADD-to-opponent target (DAMAGE_COUNTER — Munkidori, which doesn't carry a
        per-select count, so the budget falls back to its 3-counter (30) maximum)."""
        if select.get("context") not in (_DAMAGE_COUNTER_ANY, _DAMAGE_COUNTER):
            return None
        yi = (obs.get("current") or {}).get("yourIndex", 0)
        rem = int(select.get("remainDamageCounter", 0))
        budget = rem * 10 if rem else 30      # ctx 14 carries the count; a counter-mover (ctx 13) -> up to 3
        cands = []                                                  # (option, hp, prize)
        for o in (select.get("option") or []):
            if o.get("type") != _CARD or o.get("playerIndex") == yi:   # opponent-owned targets only
                continue
            poke = self._option_pokemon(obs, select, o)
            hp = (poke or {}).get("hp")
            if not poke or not hp:
                continue
            if o.get("area") == _BENCH and self._is_tera(poke.get("id")):
                continue
            cands.append((o, hp, self._prize_value({"id": poke.get("id")})))
        if not cands:
            return None
        subset = self._best_ko_subset([(hp, pv) for _, hp, pv in cands], budget)
        if subset:
            o = min((cands[i] for i in subset), key=lambda c: c[1])[0]   # finish the closest-to-dying
        else:
            o = min(cands, key=lambda c: (c[1], -c[2]))[0]               # pre-load: lowest HP, tie higher prize
        return (o.get("area"), o.get("index"), o.get("playerIndex"))

    def _best_counter_source_slot(self, obs: dict, select: dict) -> tuple | None:
        """At a REMOVE_DAMAGE_COUNTER (ctx 16) source select — where a counter-mover (Munkidori
        Adrena-Brain) removes counters FROM one of OUR Pokémon — pick our MOST-DAMAGED body: removing
        its counters is the biggest heal (the deck's reverse-heal, offense + heal in one move). Returns
        (area, index, playerIndex) of that body, or None (off ctx 16 / nothing damaged)."""
        if select.get("context") != _REMOVE_DAMAGE_COUNTER:
            return None
        yi = (obs.get("current") or {}).get("yourIndex", 0)
        best, best_dmg = None, 0
        for o in (select.get("option") or []):
            if o.get("type") != _CARD or o.get("playerIndex") != yi:   # our own bodies only
                continue
            poke = self._option_pokemon(obs, select, o)
            if not poke:
                continue
            dmg = int(poke.get("maxHp") or 0) - int(poke.get("hp") or 0)   # damage counters on it
            if dmg > best_dmg:
                best, best_dmg = (o.get("area"), o.get("index"), o.get("playerIndex")), dmg
        return best

    def _max_counter_move_number(self, select: dict) -> int:
        """At a REMOVE_DAMAGE_COUNTER_COUNT (ctx 40) select, the LARGEST count offered (move as many
        counters as possible — max offense + max heal). 0 off ctx 40."""
        if select.get("context") != _REMOVE_DAMAGE_COUNTER_COUNT:
            return 0
        return max((int(o.get("number", 0)) for o in (select.get("option") or [])
                    if o.get("type") == _NUMBER), default=0)

    def _evolve_body(self, obs: dict, option: dict) -> dict | None:
        """The in-play Pokémon an EVOLVE option would evolve (its ``inPlayArea``/``inPlayIndex`` body).
        None off an EVOLVE option or when the slot can't be resolved."""
        if option.get("type") != _EVOLVE:
            return None
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        bodies = me.get(_ZONE.get(option.get("inPlayArea"), "")) or []
        idx = option.get("inPlayIndex")
        if idx is None or not (0 <= idx < len(bodies)) or not bodies[idx]:
            return None
        return bodies[idx]

    def _evolve_body_energy(self, obs: dict, option: dict) -> int | None:
        """Energy COUNT on the body an EVOLVE option would evolve — so a rule can HOLD a win-condition
        evolution until the payoff can attack. None off EVOLVE."""
        body = self._evolve_body(obs, option)
        return None if body is None else len(body.get("energies") or [])

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
    def _grab_lethal_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for a GRAB (a `_TO_HAND` search/recover CARD option) that supplies THIS
        turn's KO-enabling attach — the recover-the-energy-that-wins lethal (ADR-0030; ms f110, ml
        f26/f48). Fires when the grab yields a reusable Basic Energy (direct — you grabbed it) or a
        `tutor_energy` card the deck can CERTAINLY cash (`_tutor_energy_certain`, or a reusable Energy
        revealed in THIS search's pool), and attaching it — onto the Active, or retreating into a benched
        attacker — delivers a min-bound KO of the opponent's Active (`_best_affordable_ko_value`). Mirrors
        `_attach_lethal_tactical` (any KO, not just a win, scored KO_SCORE + prize), extended to the grab
        select because the win rung (plan_turn) is MAIN-only. Tactical-layer (never a weight), min-bound
        SOUND like the Lethal Solver's closed-form locks. The retreat-into-a-benched-attacker branch is
        not engine-verified (a grab select can't sim the later retreat), but its downside is small: an
        over-claim only grabs an Energy over a body, never throws a game (the real KO still gates the MAIN
        attack). 0 off a grab CARD, turn 1, once the manual attach is spent, or with no KO-enabling grab.

        The retreat branch carries three preconditions it once lacked (ml f39, CRITICAL — it priced a
        useless Energy grab at 1001 and buried the Solrock the deck needed):
          1. **the retreat must be legal** — retreating costs Energy equal to the printed cost
             (rules.md §Retreat), and the Active there was a 0-Energy Meowth ex with retreat 1;
          2. **the grab must be NECESSARY** — the benched Mega already carried two {F} and Aura Jab costs
             one, so the KO existed with or without the fetched Energy (`kos(current)` was never tested);
          3. **the grab must be the MARGINAL Energy** — two Basic {F} already sat in hand, so the grab was
             not the source of the attach at all.
        Any one of them refutes f39; a KO_SCORE-class claim carries all three. The counter-fixture is ml
        84890060 f48, where all three hold (1-Energy Lunatone Active, retreat 1; benched Mega at zero)."""
        if (select.get("context") != _TO_HAND or option.get("type") != _CARD
                or board.turn <= 1 or board.energy_attached or board.my_prizes_remaining <= 0):
            return 0.0
        opp = self._opp_active(obs)
        if opp is None or not (opp or {}).get("hp"):
            return 0.0
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        direct = bool(stat and getattr(stat, "hp", 0) == 0
                      and getattr(stat, "energyType", 0) and "discard_eot" not in tags)
        tutor = ("tutor_energy" in tags
                 and (self._tutor_energy_certain(board) or self._search_pool_has_reusable_energy(board)))
        if not (direct or tutor):
            return 0.0
        etype = getattr(stat, "energyType", None) if direct else None      # a tutor's type is WILD
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)

        def kos(attacker_id, energy, body, units=1):
            return self._best_affordable_ko_value(obs, board, opp, attacker_id, energy, bound="min",
                                                  body=body, extra_type=etype, extra_units=units) > 0

        ko = kos(board.my_active_id, board.my_active_energy + 1, ma)
        if not ko and self._can_retreat(ma):              # retreat into a benched attacker, then attach
            ko = any(kos(p.get("id"), len(p.get("energies") or []) + 1, p)
                     # NECESSARY: the body doesn't already take the KO on the Energy it carries
                     and not kos(p.get("id"), len(p.get("energies") or []), p, units=0)
                     for p in (me.get("bench") or []) if p)
        if ko and board.reusable_energy_in_hand and direct:
            ko = False                                    # MARGINAL: a reusable Energy is already in hand,
                                                          # so this grab is not the source of the attach
        return (KO_SCORE + self._prize_value(opp)) if ko else 0.0

    def _grab_enabler_lethal_tactical(self, obs: dict, select: dict, board: Board,
                                      option: dict) -> float:
        """KO_SCORE-class value for grabbing the BODY that turns my Active's conditional attack on —
        the bench-the-enabler lethal (ml f13, CRITICAL). Solrock's Cosmic Beam "does nothing if you
        don't have Lunatone on your Bench" (`AttackStat.requiresBench`); with one {F} already attached
        and the opponent down to a lone 70-HP Staryu, fetching a Lunatone, benching it and attacking
        empties their board and WINS. The Lethal Solver's generator family never puts a body on the
        Bench, so `live_trace.lethal` was null and the grab went to a Riolu.

        SOUND, same standard as the rest of the family: the candidate is a Basic revealed in this
        search's pool (certain), the Bench has room, the attack is already affordable on ATTACHED
        Energy alone (no attach assumed), and the KO must WIN — take my last prize or leave them
        nothing to promote. Any missing piece → 0.0.

        On the bound: `damageMin` is 0 for exactly these attacks, because the requiresBench clause IS
        the conditional the min-bound protects against. We are establishing that condition, so the
        floor would be vacuous. Instead we demand the attack be DETERMINISTIC once the enabler is down
        — no coin, no scaling, no hidden rider (`damageMax == damage`) — and then read the exact
        damage. Anything else conditional and this returns 0.0 rather than guess."""
        if (select.get("context") != _TO_HAND or option.get("type") != _CARD
                or board.turn <= 1 or board.bench_full or board.my_prizes_remaining <= 0):
            return 0.0
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp") or not self.stats:
            return 0.0        # attack records resolve per-aid below (_attack_stat -> None skips), so
                              # no table-level gate — the provider is a record source too (ADR-0056)
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if cid is not None else None
        if not stat or not stat.is_pokemon or stat.evolvesFrom:   # a benchable Basic Pokémon only
            return 0.0
        active = self.stats.get(board.my_active_id) if board.my_active_id is not None else None
        if not active:
            return 0.0
        ctx = self._damage_context(obs)
        have = set(ctx.get("atk_bench_names") or ())
        would_have = have | {stat.name}
        for aid in (getattr(active, "attacks", None) or ()):
            ast = self._attack_stat(aid)
            need = getattr(ast, "requiresBench", None)
            if not need or set(need) <= have:                 # unconditional, or already satisfied
                continue
            if not set(need) <= would_have:                   # this body isn't the missing piece
                continue
            if self._attack_cost(aid) > board.my_active_energy:
                continue                                      # affordable on ATTACHED Energy alone
            if not ast.is_deterministic:
                continue                                      # some OTHER clause is conditional — no lock
            dmg = self.predicted_damage(board.my_active_id, aid, opp, bound="exact",
                                        context={**ctx, "atk_bench_names": tuple(would_have)})
            if not (dmg and dmg >= (opp.get("hp") or 0)):
                continue
            wins = (self._prize_value(opp) >= board.my_prizes_remaining or not board.opp_bench)
            if wins and not self._is_simultaneous_draw(board, aid, self._prize_value(opp)):
                return KO_SCORE + self._prize_value(opp)
        return 0.0

    def _grab_retreat_tool_lethal_tactical(self, obs: dict, select: dict, board: Board,
                                           option: dict) -> float:
        """KO_SCORE-class value for grabbing a retreat-reduction Tool (Air Balloon) that FREES a retreat
        into an already-winning benched attacker — the retreat-enabler lethal (ml f15). My Active can't
        retreat now; a benched body, promoted, takes a min-bound WINNING KO
        (`_bench_body_wins_if_promoted`); the grabbed Tool's `retreatReduction` covers the Active's exact
        retreat shortfall. Extends the grab select because the enabler win rung (`_family_win_candidates`
        tier 6) is MAIN-only — the same shape as `_grab_enabler_lethal_tactical`, so the Petrel search
        picks Air Balloon over an off-line Trainer. Gated on `retreat_enabler_lethal`; SOUND (min-bound +
        win). Its downside mirrors the other grab tacticals: an over-claim only grabs the Tool over
        another card, never throws a game (the real retreat + KO still gate the later steps). 0 off a grab
        card, turn 1, or with no such win."""
        if (not getattr(self, "retreat_enabler_lethal", False) or select.get("context") != _TO_HAND
                or option.get("type") != _CARD or board.turn <= 1 or board.my_prizes_remaining <= 0):
            return 0.0
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp"):
            return 0.0
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)
        if ma is None or self._can_retreat(ma):            # only when a Tool is NEEDED to retreat
            return 0.0
        need = self._retreat_shortfall(ma)
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (need > 0 and stat is not None and getattr(stat, "retreatReduction", 0) >= need):
            return 0.0
        if not self._bench_body_wins_if_promoted(obs, board, opp, me, ma):
            return 0.0
        return KO_SCORE + self._prize_value(opp)

    def _attach_retreat_tool_lethal_tactical(self, obs: dict, select: dict, board: Board,
                                             option: dict) -> float:
        """KO_SCORE-class value for attaching a retreat-reduction Tool (Air Balloon) to the ACTIVE when it
        frees a retreat into an already-winning benched attacker (ml f15). Steers the Tool onto the body
        that must RETREAT (Makuhita), not the wincon the tool doctrine would otherwise prefer — the
        second half of the retreat-enabler lethal steering, after `_grab_retreat_tool_lethal_tactical`
        picks it in the Petrel search. Same gate/soundness; 0 off an ACTIVE Tool-attach, turn 1, or with
        no such win."""
        if (not getattr(self, "retreat_enabler_lethal", False) or board.turn <= 1
                or option.get("type") != _ATTACH or option.get("inPlayArea") != _ACTIVE
                or board.my_prizes_remaining <= 0):
            return 0.0
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp"):
            return 0.0
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)
        if ma is None or self._can_retreat(ma):            # a Tool is still NEEDED to retreat
            return 0.0
        need = self._retreat_shortfall(ma)
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (need > 0 and stat is not None and getattr(stat, "retreatReduction", 0) >= need):
            return 0.0
        if not self._bench_body_wins_if_promoted(obs, board, opp, me, ma):
            return 0.0
        return KO_SCORE + self._prize_value(opp)

    def _can_retreat(self, ma: dict | None) -> bool:
        """My Active can pay its Retreat Cost this turn — attached Energy >= its EFFECTIVE retreat cost
        (printed cost minus any ATTACHED retreat-reduction Tool: Air Balloon −2, `retreatReduction`;
        rules.md §Retreat: "pay the Retreat cost in Energy"). Fail-CLOSED on an unknown stat: a
        KO_SCORE-class claim must never assume a retreat it cannot prove (ml f39: a 0-Energy Meowth ex
        with retreat 1 "retreated" into a benched Mega and the grab scored 1001). An attached Tool is a
        PROVABLE board fact, so subtracting it stays sound (ml f15: Air Balloon on Makuhita -> retreat
        2−2=0 -> free retreat into the benched Mega Lucario ex)."""
        if not ma or not self.stats:
            return False
        stat = self.stats.get(ma.get("id"))
        if stat is None:
            return False
        cost = getattr(stat, "retreatCost", 0)
        for tool in (ma.get("tools") or []):              # attached retreat-reduction Tools lower it
            tid = tool.get("id") if isinstance(tool, dict) else tool
            tstat = self.stats.get(tid) if tid is not None else None
            cost -= getattr(tstat, "retreatReduction", 0) if tstat is not None else 0
        cost = max(0, cost)
        if cost == 0:
            return True                                   # free retreat
        return len(ma.get("energies") or []) >= cost

    def _search_pool_has_reusable_energy(self, board) -> bool:
        """True iff THIS search's revealed pool (`search_deck_ids`) contains a reusable Basic Energy a
        `tutor_energy` card could cash into this turn's attach — the single-frame complement to
        `_tutor_energy_certain` (which needs the match-scoped tracker anchor the retest lacks). A card is
        reusable Energy when hp 0 with a real `energyType` and not `discard_eot`. False off a search reveal."""
        sd = board.search_deck_ids
        if not sd or not self.stats:
            return False
        for eid in sd:
            est = self.stats.get(eid)
            etags = self.functions.tags(eid) if self.functions else []
            if (est and getattr(est, "hp", 0) == 0 and getattr(est, "energyType", 0)
                    and "discard_eot" not in etags):
                return True
        return False

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
        estat = self.stats.get(eid) if (self.stats and eid is not None) else None
        etype = getattr(estat, "energyType", None)          # 0/None = colourless/special — pays a {C}
                                                            # slot, NEVER a specific one (Ignition can't
                                                            # fund Jetting Blow's {W})
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)
        bench_names = tuple(                                     # requiresBench partner check: an attack
            (self.stats.get(b.get("id")).name if self.stats and self.stats.get(b.get("id")) else "")
            for b in (me.get("bench") or []) if b)               # that "does nothing" w/o a benched
        #                                                          partner (Cosmic Beam needs Lunatone) must
        # not phantom-KO here. The attach is to the ACTIVE, so the Bench is unchanged by it — the current
        # bench IS the partner set the unlocked attack fires under (ml 85709280 f17, CRITICAL: attach→Solrock
        # scored a 1001 phantom KO on an EMPTY bench because no context reached the requiresBench gate).

        def best_affordable(energy: int, extra_units: int = 0) -> float:
            # per-attack oracle (ADR-0032): adjust-then-max, so an ignore-flag attack is seen and a
            # prevented (ex-locked) defender correctly yields 0 — no lethal-attach onto a whiff.
            # Type-guarded (sound-or-silent): a specific-type slot the attach can't fund fails the
            # attack even when the COUNT suffices. Passes `atk_bench_names` (exact bound) so a
            # requiresBench attack with its partner absent is zeroed, not credited a phantom KO.
            return max((self.predicted_damage(board.my_active_id, aid, opp,
                                              context={"atk_bench_names": bench_names})
                        for aid in (active_stat.attacks or ())
                        if self._attack_cost(aid) <= energy
                        and self._attack_type_payable(aid, ma, extra_type=etype,
                                                      extra_units=extra_units)), default=0)

        cur = board.my_active_energy
        if best_affordable(cur) >= opp_hp:                  # already lethal — no attach needed
            return 0
        if best_affordable(cur + provided, extra_units=provided) >= opp_hp:
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
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        ma = next((p for p in (me.get("active") or []) if p), None)
        # Best KO the CURRENT Active can already take (0 if not, incl. ex-immune). Retreat is worth it
        # ONLY for a strictly better KO; same prize via a benched body wastes the Active's attack + turn.
        my_active_ko = self._best_affordable_ko_value(
            obs, board, opp, board.my_active_id, board.my_active_energy, body=ma)
        best = 0.0
        for p in (me.get("bench") or []):
            if not p:
                continue
            energy = len((p.get("energies") or []))
            best = max(best, self._best_affordable_ko_value(obs, board, opp, p.get("id"), energy, body=p))
        if best <= my_active_ko:                         # the Active already takes this KO (or better):
            return 0                                     # just attack — don't waste the retreat
        return best + _RETREAT_POSITION_EPS

    def _best_affordable_ko_value(self, obs: dict, board: Board, opp: dict, attacker_id: int | None,
                                  energy: int, *, bound: str = "exact", body: dict | None = None,
                                  extra_type=None, extra_units: int = 0,
                                  boost_amount: int = 0, boost_type=None,
                                  promote_bench_names=None) -> float:
        """The best KO value a hypothetical attacker reaches vs the opp Active — the KO oracle's
        ``best_affordable_ko_value`` (ADR-0052), handed the Board's ``opp_bench`` snapshot for the
        rider tiebreaks. Signature kept for the planner/tactical call sites (``obs`` vestigial)."""
        return self.combat.best_affordable_ko_value(
            opp, attacker_id, energy, opp_bench=board.opp_bench, bound=bound, body=body,
            extra_type=extra_type, extra_units=extra_units,
            boost_amount=boost_amount, boost_type=boost_type,
            promote_bench_names=promote_bench_names)

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
        if t == _PLAY and (st.is_item or st.is_supporter):  # Item stacks; a Supporter is one/turn
            copies = 1 if st.is_supporter else self._hand_count_of(obs, cid)
        elif (t == _ATTACH and st.is_tool
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
        if st.damageBoostVsEx and not (opp_stat and opp_stat.is_ex_body):
            return 0                                        # "{ex}" defender gate (incl. Mega ex)
        ctx = self._damage_context(obs)
        for aid in (active.attacks or ()):
            cost = self._attack_cost(aid)
            if cost > board.my_active_energy:
                continue
            dmg = self.predicted_damage(board.my_active_id, aid, opp, context=ctx)
            if dmg >= opp_hp:
                return 0                                    # an affordable KO already exists — just attack
        best = 0.0
        for aid in (active.attacks or ()):
            cost = self._attack_cost(aid)
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

    def _attack_stat(self, attack_id):
        """The attack's ``AttackStat`` (ADR-0032) — the KO oracle's provider read (ADR-0056/0052).
        None for an unknown attack or a stat-blind Pilot (no record, no damage)."""
        return self.combat.attack_stat(attack_id)

    def _attack_cost(self, attack_id, default=99):
        """The attack's Energy count off the ONE record; ``default`` carries the caller's
        epistemics (99 fail-closed / 0 tiebreak-neutral / None identity-compare)."""
        return self.combat.attack_cost(attack_id, default)

    def _attack_damage(self, attack_id) -> int:
        return self.combat.attack_damage(attack_id)

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

    def _rider_spread(self, attack_id) -> int:
        """The attack's distributable opp-bench spread total (Phantom Dive's ``benchSpread``, e.g. 60)
        — read off the ONE attack record; the legacy ``bench_spread`` dict feeds the synth fallback."""
        st = self._attack_stat(attack_id)
        return st.benchSpread if st else 0

    def _rider_recoil(self, attack_id) -> int:
        """The attack's unconditional self-damage — single-sourced like `_rider_snipe`."""
        st = self._attack_stat(attack_id)
        return st.recoil if st else 0

    def _refresh_swing_tactical(self, obs: dict, board: Board, ctx) -> float:
        """Closed-form value of a shuffle-refresh (ADR-0060, SHED graded by ADR-0065). Judge/Harlequin
        are symmetric REFILLS, not strips: each player shuffles their hand away and redraws to the
        card's printed count, so the play is fully described by how many cards move, in which direction
        (strategy/refresh.py):

            CYCLE                                  the draw side — flat, speculative, guard-cancellable
            - Σ keep_cost(held card)              the graded SHED — what shuffling my hand costs
            + STRIP * max(-opp_net, 0)  + FRESH*f  cards stripped from them        (certain)
            - GIFT  * max(opp_net, 0)              cards handed to them            (certain)

        The card's own printed draw count is the break-even. **The SHED side is now graded** (WP7): it
        was a flat ``_REFRESH_SHED × cards-lost``, propped up by the hand-QUALITY guards
        (`hold-wincon` / `hold-line-piece` / `hold-irreplaceable-tool`) — a wincon and a dreg cost the
        same to shuffle. It is now ``Σ keep_cost`` over the actual hand (`_refresh_shed_keepcost`): the
        SAME closure the gamble uses, so a live hand of wincons/engines is expensive to shuffle and a
        dead hand is nearly free — the guards fold in, one currency (the closure supplies the
        redundancy discount, so a wincon with its tutors live shuffles cheaper than a lone one-of).

        The DRAW side stays flat (`dont-refresh-into-a-probable-miss` owns redraw quality, a separate
        jurisdiction). Silent (0) on anything that is not the PLAY of a known refresh."""
        if ctx.option_type != _PLAY:
            return 0.0
        nets = net_change(ctx.card_id, my_hand=board.my_hand_size, opp_hand=board.opp_hand_size,
                          my_prizes_remaining=board.my_prizes_remaining,
                          opp_prizes_remaining=board.opp_prizes_remaining)
        if nets is None:
            return 0.0
        _my_net, opp_net = nets
        stripped = max(-opp_net, 0.0)
        fresh = fresh_cards(ctx.card_id, board.opp_hand_size, board.opp_hand_size_delta)
        return (_REFRESH_CYCLE
                - self._refresh_shed_keepcost(obs, board, ctx)
                + _REFRESH_STRIP * stripped
                + (_REFRESH_FRESH * fresh if stripped > 0 else 0.0)
                - _REFRESH_GIFT * max(opp_net, 0.0))

    def _hand_size_relief(self, obs: dict, ctx) -> float:
        """REPORTING-ONLY (hand-disruption grill, 2026-07-19): the signed Powerful-Hand damage swing a
        `hand_disruption` refresh works on a hand-size attacker in the opponent's ACTIVE forward line
        (Abra→Kadabra→Alakazam Powerful Hand = 20 dmg per card in THEIR hand, aimed at MY Active):

            relief = handSizeDamage × (their hand now − their redraw count)

        Positive = Powerful-Hand damage DENIED off my Active by shrinking their hand; negative = a
        refill that ARMS them (the ep85709280-shaped hole: Judge an EMPTY Alakazam hand and you hand
        them 20/card against your own board). Sign-correct by construction — the point of grill ruling
        1a/2a. Uses the same `handSizeDamage` the incoming oracle reads (`_forward_hand_size_damage`);
        the value is self-preservation (incoming), not opponent-worth.

        This reports the ISOLATED hand-size damage swing — deliberately NOT the change in worst-case
        `forward_incoming_damage`, which masks to 0 whenever a hand-INDEPENDENT forward threat (an
        energy-scaler on the same line) already out-damages Powerful Hand. That masking IS the correct
        MARGINAL decision value and belongs at promotion; the reported signal is the raw physical
        quantity that feeds it. Scoped to the ACTIVE forward line (only it can attack next turn) — a
        BENCHED hand-size attacker, which the flat +25 rung over-fires on, reads 0 here.

        INERT: surfaced on the OptionTrace for telemetry, NEVER added to `score`. The flat
        `play-harlequin-vs-hand-size` (+25) / `disrupt-when-unfavored` (+18) rungs still drive.
        Promotion (functional, marginal vs my own KO, retire the rungs) waits on corpus evidence —
        docs/plans/hand-disruption-grill-spec.md §Design B. 0 unless this is the PLAY of an
        opponent-shuffling refresh (Judge / Harlequin / Unfair Stamp) facing such a line."""
        if ctx.option_type != _PLAY or "hand_disruption" not in (ctx.tags or []) or not self.stats:
            return 0.0
        branches = refresh_branches(ctx.card_id, 0, 0)   # opp redraw count is board-independent for these
        if branches is None or not opponent_shuffles(ctx.card_id):
            return 0.0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        oa = next((p for p in (opp.get("active") or []) if p), None)
        oa_id = (oa or {}).get("id")
        if oa_id is None:
            return 0.0
        line = {oa_id} | self._forward_card_ids(oa_id)
        per_card = max((getattr(self.stats.get(i), "handSizeDamage", 0) or 0 for i in line), default=0)
        if per_card <= 0:
            return 0.0
        redraw = sum(opp_draw for _my, opp_draw in branches) / len(branches)
        return float(per_card * ((opp.get("handCount") or 0) - redraw))

    def _grab_refresh_draw_tactical(self, board: Board, ctx) -> float:
        """Sub-point tie-break at a TO_HAND draw-Supporter grab: rank a refresh by its own-draw
        ceiling (ADR-0060 facts), so among the `grab-a-draw-supporter-in-setup` band the bigger-ceiling
        refresh is grabbed (Lillie's redraws 8 early ≻ Judge's 4 — ep86088989 f29, CRITICAL). The +10
        band could not tell them apart, so the option INDEX decided.

        Mirrors the rung's gate exactly (setup TO_HAND, a `draw` Supporter CARD), plus `own_draw_count`
        knowing the card — so it only ever SEPARATES cards the rung already tied, never lifts one out of
        the band. Silent (0) otherwise; re-values nothing — the PLAY swing is priced by
        `_refresh_swing_tactical` when the card is actually played."""
        if (board.line_ready or ctx.select_context != _TO_HAND or "draw" not in ctx.tags
                or not (ctx.stat and getattr(ctx.stat, "is_supporter", False))):
            return 0.0
        draw = own_draw_count(ctx.card_id, board.my_prizes_remaining, board.opp_prizes_remaining)
        return _GRAB_REFRESH_DRAW * draw if draw is not None else 0.0

    def _refresh_shed_keepcost(self, obs: dict, board: Board, ctx) -> float:
        """The graded SHED (ADR-0065): the cost of shuffling my hand away on a refresh = the shared
        ``planner._hand_keep`` summation — ``Σ keep_cost`` over every held COPY except the played
        refresh itself (excluded once: it is discarded, not shuffled; a second held copy still
        charges), duplicates priced marginally (each copy's re-access odds count its shuffled
        siblings as outs). Each copy's cost = role value × (1 − re-access odds) over the
        shuffle-grown pool across the refresh's own draw window — the closure pointed backwards,
        the SAME summation as the gamble's `hand_keep` (`_best_gamble_line`) by construction.
        Anchored deck counts when the tracker has them, else the pre-anchor unseen composition
        (`decklist − visible − hidden prizes`, needs obs — the reason obs is threaded here) with the
        re-access odds PRIZE-SPLIT-WEIGHTED (`_prize_split_hit` via `_keep_cost` — the cost side
        prices the split exactly like the gain side; the shuffled hand copies stay ``certain``).
        0 when the deck bookkeeping is unresolved (no shed charged — the CYCLE credit alone stands,
        matching the old flat term's floor)."""
        from common.strategy.refresh import refresh_branches
        branches = refresh_branches(ctx.card_id, board.my_prizes_remaining, board.opp_prizes_remaining)
        if not branches:
            return 0.0
        draws = max(my_draw for my_draw, _opp in branches)
        me = self._my_player(obs)
        counts = board.deck_known_counts
        if counts:
            deck_count = sum(counts.values())
            prizes_hidden = 0                                    # anchored: the split is resolved
        else:
            from collections import Counter
            unseen = Counter(self.deck)
            unseen.subtract(self._visible_card_counts(me))
            counts = {cid: n for cid, n in unseen.items() if n > 0}
            prizes_hidden = sum(1 for p in (me.get("prize") or [])
                                if not (isinstance(p, dict) and p.get("id") is not None))
            deck_count = sum(counts.values()) - prizes_hidden
            if deck_count <= 0 or not counts:
                return 0.0
        hand = [c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None]
        pool = deck_count + max(0, len(hand) - 1)                # the shuffle-grown pool, per COPY
        return self._hand_keep(hand, ctx.card_id, counts, pool, draws, board,
                               prizes_hidden=prizes_hidden, deck_count=deck_count)

    def _discard_fuel_types(self) -> frozenset:
        """Energy types a DISCARD-SOURCE accel attack in this deck wants IN the discard — the
        Aura-Jab class (``AttackStat.recoverN`` > 0, ``recoverSource == "discard"``; ``None`` in the
        set = the attack takes any Basic). Pitching a matching Basic Energy is FUEL, not loss —
        the zone-signed worth the spec's Round 7 ruled (Kyogre-class; correction 84071010-45 held
        surplus Energy FOR the recycle). Memoised — deck-fixed. Empty without stats/deck."""
        if self._discard_fuel_cache is None:
            types = set()
            for cid in set(self.deck):
                st = self.stats.get(cid) if self.stats else None
                for aid in (getattr(st, "attacks", None) or ()):
                    ast = self._attack_stat(aid)
                    if (ast is not None and getattr(ast, "recoverN", 0)
                            and getattr(ast, "recoverSource", None) == "discard"):
                        types.add(getattr(ast, "recoverEnergyType", None))
            self._discard_fuel_cache = frozenset(types)
        return self._discard_fuel_cache

    def _discard_shadow(self, obs: dict, select: dict, board: Board, options: list, chosen: list):
        """The DISCARD keep-cost SHADOW (the shadow-equations ruling, 2026-07-19 — the first
        equation shipped under it): compute the card-worth oracle's answer at a real discard pick
        and EMIT it beside the decision, deciding NOTHING. The tuned `_DISCARD` ladder stays the
        decider; every disagreement row is either an oracle gap (a premise the gate library doesn't
        carry yet) or a latent ladder bug — the evidence bridge the discard convergence (seam D,
        `docs/plans/seam-discard-convergence.md`) swaps on.

        The v1 equation per candidate card — grilled legs only, simplifications EMITTED as terms so
        a reader can audit WHY (the ADR-0019 full-working standard):

            keep = Worth × Gates × (1 − pitch re-access)

        Worth = `_role_value` (roles / tags / ACE-SPEC / energy); Gates = `_deploy_odds` (the
        evolution + fetcher legs; the pressure bit rides as ``closing``). PITCH re-access — the
        DISCARD leg, deliberately distinct from the shuffle leg — is credited only when
        DETERMINISTIC: a duplicate still in hand (``dup_hand``), a same-card copy already in play
        (``in_play``), or a matching recycler HELD (``recycler`` — a ``zone: discard`` FETCH clause
        reaching this card). Probabilistic recycler draws are emitted (``recycler_deck``) but
        credited 0 — errs toward keep. ``fuel`` (`_discard_fuel_types`) floors the keep at 0 — the
        zone sign's v1 (a negative keep is deferred). Known naiveties, by design: per-card (sets
        not sums — a duplicate PAIR both price 0), and no probabilistic recycle window. None off a
        real choice (no options beyond the forced picks) and never mid-sim (`self._planning`).

        WP-N3 (keep-value v2): each row also carries ``keep_v2`` — the needs-assignment raw
        counterfactual marginal (`_needs_v2`) — and the record carries ``eq2_pick`` (the v2
        decider's cheapest removal, hedged at v1's post-gate keep) + ``agree_v2`` (v2 vs the
        DECIDED picks): the v1-vs-v2 evidence bridge the WP-N4 family swaps ride, deciding
        nothing."""
        if self._planning or select.get("context") != _DISCARD:
            return None
        picks = len(chosen)
        if picks <= 0 or len(options) <= picks:
            return None                                  # no real choice — nothing to shadow
        rows, order = self._discard_equation_rows(obs, select, board, options)
        if not rows:
            return None
        eq_pick = order[:picks]
        keeps_v2, eq2_pick = self._needs_v2(obs, board, rows, picks)
        for r, kv in zip(rows, keeps_v2):
            r["keep_v2"] = kv
        rec = {"picks": sorted(chosen), "eq": rows, "eq_pick": sorted(eq_pick),
               "agree": set(eq_pick) == set(chosen),
               "eq2_pick": eq2_pick, "agree_v2": set(eq2_pick) == set(chosen)}
        if getattr(self, "needs_keep_value", False):
            rec["decided_v2"] = True                     # v2 needs-assignment IS the decider (WP-N4)
        elif getattr(self, "discard_keep_value", False):
            rec["decided"] = True                        # v1 IS the decider (seam-D kill-switch ON)
        return rec

    def _discard_equation_pick(self, obs: dict, select: dict, board: Board, options: list, picks: int):
        """The DECIDER under the `discard_keep_value` kill-switch (ADR-0065 seam-D, the SWAP): the
        forced-discard pick IS the card-worth equation's ranking — the ``picks`` cheapest-to-lose
        cards (`_discard_equation_rows`), replacing the tuned `_DISCARD` ladder wholesale. None when
        the equation can't rank (no priceable rows), so the caller keeps the ladder order."""
        _rows, order = self._discard_equation_rows(obs, select, board, options)
        return order[:picks] if order else None

    def _discard_needs_pick(self, obs: dict, select: dict, board: Board, options: list, picks: int):
        """The DECIDER under the `needs_keep_value` kill-switch (ADR-0065 WP-N4, the per-family swap):
        the forced-discard pick IS the keep-value v2 needs-assignment's cheapest removal (`_needs_v2`
        → `eq2_pick`, `needs.cheapest_removal` over the resolved slots, hedged at v1's post-gate
        keep), replacing v1's per-card gate composition with the global assignment. Same rows as
        v1's ranking (`_discard_equation_rows` — the deploy gates + fuel/burst flags v2 consumes);
        None when nothing is priceable, so the caller falls through to v1 / the ladder."""
        rows, _order = self._discard_equation_rows(obs, select, board, options)
        if not rows:
            return None
        _keeps, eq2_pick = self._needs_v2(obs, board, rows, picks)
        return eq2_pick or None

    def _discard_equation_rows(self, obs: dict, select: dict, board: Board, options: list):
        """The card-worth discard equation's per-candidate rows AND the full ranked index order — the
        shared computation behind the SHADOW (`_discard_shadow`, telemetry) and the DECIDER
        (`_discard_equation_pick`, under the kill-switch). Pure and deterministic (safe mid-sim). The
        ranking is ``(keep asc, pitch desc, worth asc, index)``: cheapest-to-lose first, ties broken
        by DEADNESS then by lower underlying worth then hand index. Returns ``([], [])`` when nothing
        is priceable."""
        me = self._my_player(obs)
        from collections import Counter
        hand_ids = [c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None]
        held = Counter(hand_ids)
        counts = board.deck_known_counts
        if not counts:
            unseen = Counter(self.deck)
            unseen.subtract(self._visible_card_counts(me))
            counts = {cid: n for cid, n in unseen.items() if n > 0}
        from common import fetch_closure
        def _recyclers(stat):
            in_hand = in_deck = 0
            for rid, n in held.items():
                if any(cl.get("kind") == "fetch" and cl.get("zone") == "discard"
                       and fetch_closure.fetch_target_matches(cl, stat)
                       for cl in (self.effects.clauses(rid) if self.effects else ())):
                    in_hand += n
            for rid, n in counts.items():
                if n > 0 and any(cl.get("kind") == "fetch" and cl.get("zone") == "discard"
                                 and fetch_closure.fetch_target_matches(cl, stat)
                                 for cl in (self.effects.clauses(rid) if self.effects else ())):
                    in_deck += n
            return in_hand, in_deck
        fuel_types = self._discard_fuel_types()
        rows = []
        for i, o in enumerate(options):
            cid = self._option_card_id(obs, select, o)
            if cid is None:
                continue
            st = self.stats.get(cid) if self.stats else None
            tags = self.functions.tags(cid) if (self.functions and cid is not None) else ()
            worth = self._role_value(cid)
            # The engine-supporter WORTH floor (Finding 2's 5th premise gate, mirrored for the swap):
            # a draw/search/dig SUPPORTER that is NOT hand_disruption (Lillie's, not Harlequin) is
            # a draw engine worth keeping over pure filler, though it carries no ROLE/TAG worth.
            # (heal/clutch_heal excluded — a pure-heal Supporter is recovery, not a draw engine.)
            # Discard-CONTEXT (mirrors `keep-engine-supporter-at-discard` −8). A WORTH floor, not a keep
            # floor — it is still discounted by re-access (a duplicate engine supporter is covered) and
            # by the gates (a need-met tutor still zeros), unlike a hard override.
            engine_supporter = bool(st is not None and getattr(st, "is_supporter", False)
                                    and (_ENGINE_KEEP_TAGS & set(tags)) and "hand_disruption" not in tags)
            if engine_supporter and worth < _ENGINE_SUPPORTER_KEEP:
                worth = _ENGINE_SUPPORTER_KEEP
                row_engine = True
            else:
                row_engine = False
            row = {"i": i, "cid": cid, "worth": round(worth, 1)}
            if row_engine:
                row["engine_supporter"] = True
            dup = held.get(cid, 0) >= 2
            in_play = cid in board.in_play_ids
            rec_hand, rec_deck = _recyclers(st) if (st is not None and worth > 0) else (0, 0)
            fuel = bool(st is not None and getattr(st, "is_basic_energy", False)
                        and (None in fuel_types
                             or getattr(st, "energyType", None) in fuel_types))
            deploy = self._deploy_odds(cid, board, counts)
            if dup:
                row["dup_hand"] = True
            if in_play:
                row["in_play"] = True
            if rec_hand:
                row["recycler"] = rec_hand
            if rec_deck:
                row["recycler_deck"] = rec_deck
            if fuel:
                row["fuel"] = True
            if deploy != 1.0:
                row["deploy"] = deploy
            # The DEPLOY-NOW spike (closing edge, ep86091435 f68): an in-play same-card copy does NOT
            # cover THIS body's this-turn evolution, so re-access is not bankable — zero the credit
            # and the card charges FULL worth. Distinguishes the open Drakloak (keep) from the
            # just-benched-base one (ep83686860 f18, not in deploy_now_ids -> re-access still credited).
            closing = self._gate_closing(cid, board)
            if closing:
                row["closing"] = True
            reaccess = 0.0 if closing else (1.0 if (dup or in_play or rec_hand) else 0.0)
            # A SPENT burst (ladder-win 83454549-36): a `discard_eot` Energy is precious until the
            # Active is fully powered — then it self-discards at end of turn anyway, so it is fodder.
            # DISCARD-CONTEXT (at a refresh it is a next-turn attach), so it lives in the shadow's
            # pitch term, not a general Worth gate.
            spent_burst = "discard_eot" in tags and getattr(board, "active_fully_powered", False)
            row["keep"] = 0.0 if (fuel or spent_burst) else round(worth * deploy * (1.0 - reaccess), 1)
            # The PITCH-PREFERENCE term (seam-D grill Finding 3): keep-cost is a KEEP floor and
            # cannot RANK a discard — a dreg, a duplicate, and a DEAD card all price keep 0. The
            # pitch side is `P(met | pitch) − P(met | keep)` going positive: a card whose role is
            # EXPIRED/useless (or whose discard is progress) is actively best gone. Mirrors the
            # ladder's positive-pitch premises at SOURCE (not their weights — the equation ranks):
            # `discard-the-dead-opener` (opener role spent), `discard-the-redundant-tutor` (wincon in
            # hand → the tutor's target is had), a stranded evolution (payoff with no base), the
            # declared `discard_fodder`, `fuel` (zone sign), and the SPENT burst above. `pitch` = the
            # count; it breaks the zero-keep ties so dead weight sheds before a live spare. The
            # `redundant_tutor` case is now ALSO priced keep 0 by the need-met gate (`_deploy_odds`);
            # the flag stays for the pitch tie-break + display. SHADOW-only, deciding nothing.
            roles = self._roles_of(cid)
            dead_opener = "opener" in tags
            redundant_tutor = bool(getattr(board, "wincon_in_hand", False)
                                   and ({"rush_evolve", "tutor_mega"} & set(tags)))
            stranded = cid in self._stranded_evolution_set()
            fodder = "discard_fodder" in roles
            if dead_opener:
                row["dead_opener"] = True
            if redundant_tutor:
                row["redundant_tutor"] = True
            if stranded:
                row["stranded"] = True
            if fodder:
                row["fodder"] = True
            if spent_burst:
                row["spent_burst"] = True
            row["pitch"] = (int(fuel) + int(dead_opener) + int(redundant_tutor) + int(stranded)
                            + int(fodder) + int(spent_burst))
            rows.append(row)
        if not rows:
            return [], []
        # Rank: cheapest keep first; among equal keep, the DEADEST (highest pitch) sheds first; then
        # the LOWER underlying worth (sets-not-sums — a worth-10 duplicate's redundancy is worth
        # preserving over a worth-0 dreg's, ladder-win 83967840-54); index only as the last resort.
        order = [r["i"] for r in
                 sorted(rows, key=lambda r: (r["keep"], -r["pitch"], r["worth"], r["i"]))]
        return rows, order

    def _needs_v2(self, obs: dict, board: Board, rows: list, picks: int):
        """WP-N3 (keep-value v2, `keep-value-needs-assignment-grill-spec.md`): the Pilot-side needs
        RESOLVER — the live board resolved into `common.needs` slots / per-candidate eligibility /
        resupply, pricing the v2 shadow: per-row ``keep_v2`` (the raw counterfactual marginal,
        `needs.keep_v2`) and the v2 decider's pick (`needs.cheapest_removal`), hedged at v1's
        POST-GATE keep — the WP-N3 refinement: v2 never prices below the shipped decider (a
        raw-tier floor would undo the gate knowledge), and a firing floor telemeters a missing
        slot. SHADOW-ONLY (Round 6): nothing here decides. Returns ``(keep_v2 per row, eq2_pick
        as OPTION indices)``.

        v0 resolver scope (the discard bench's needs — the rest joins in WP-N4):
          * LINE slots per held card class at its line-role tier × the v1 deploy gate (dead
            evolution / dead-fetcher / need-met knowledge CONSUMED per the dissolution ledger); an
            in-play copy MEETS the primary slot; a wincon class adds the half-tier SUCCESSION slot
            (`needs.line_slots` — a spare wincon insures the line, never free).
          * DEPLOY-NOW slots off `Board.deploy_now_ids` (the spike, re-derived: the in-play copy
            does not cover THIS body's evolution).
          * FUND-ATTACK slots = the Active's biggest-attack cost remaining (the spent burst
            re-derived as slot ABSENCE; deadlines from the quota structure).
          * one saturating DRAW-ENGINE slot (engine Roles + the engine-supporter predicate).
          * SUPPLY-WINCON via `needs.supply_wincon_slot` (need-met = slot absence).
          * ANSWER-DOOM under the pressure read (successor / clutch_heal / switch).
          * FUEL slots ride the pitch side (`needs.pitch_gain` — pitching a matching Energy is
            progress).
          * opponent DENY slots (thread 2, the Round-3 ruled read): one per opponent in-play body
            a strip actually bites, valued by the SHIPPED ADR-0062 denial oracle and graded by the
            body's visible turns-to-ready (`_opp_turns_to_ready`) — the Hammer/gust classes' first
            v2 pricing (they still hedge-floor where the graded deny is small; note the oracle is
            DAMAGE-denominated, so a ready threat prices a deny slot above the worth tiers).
        Deferred, documented: probabilistic slot RESUPPLY at THIS site (0.0 here — a forced
        discard has no redraw window; errs toward keep. The REFRESH site's resupply is LIVE —
        `_refresh_slot_resupply` over the refresh draw window), non-Active fund bodies, and
        non-option hand cards as fixed coverage (a real forced discard offers the whole hand)."""
        from common import needs
        slots, elig = self._resolve_needs(obs, board, rows)
        resupply = [0.0] * len(slots)
        keeps = [round(needs.keep_v2(slots, elig, resupply, k), 1) for k in range(len(rows))]
        pick = needs.cheapest_removal(
            slots, elig, resupply, [r["keep"] for r in rows], picks,
            tiebreak=[r["worth"] * r.get("deploy", 1.0) for r in rows])
        return keeps, sorted(rows[k]["i"] for k in pick)

    def _resolve_needs(self, obs: dict, board: Board, rows: list, *, include_general: bool = True):
        """The shared keep-value v2 RESOLVER: the live board + the held-card ``rows`` resolved into
        `common.needs` slots and per-row eligibility (which slot indices each row can supply). The
        ONE slot derivation behind BOTH the discard decider (`_needs_v2`) and the refresh-SHED
        magnitude shadow (`_refresh_shed_shadow`) — rows need only ``cid``, ``deploy`` (the v1
        gate factor v2 consumes), and ``fuel``. Returns ``(slots, elig)``; the caller owns
        ``resupply`` — all-0.0 where no draw window backs a discount (the discard decider, the
        leaf), `_refresh_slot_resupply` at the refresh site. The slot vocabulary, the corpus-adjudicated
        derivations (the succession slot, Pokémon-only lines, the engine band, the fund/doom/fuel
        legs, the thread-2 opponent DENY leg) and the deferred legs are documented on `_needs_v2`.

        DENY slots and future per-slot resupply (the thread-1 closure discount, not yet landed
        here): the CLOSING-EDGE rule SHOULD apply — a deadline-0 deny slot (their body ready NOW)
        must take resupply 0.0 regardless of how many Hammers the deck could re-draw, because a
        deny needed THIS turn is not re-drawable in time (the same reasoning that makes the
        deploy_now spike and the deadline-0 answer_doom slot un-bankable). Deadline ≥ 1 deny slots
        may take their supplier classes' re-access odds over that window. Vacuous today (resupply
        is all-0.0), recorded here for the resupply thread.

        ``include_general=False`` (WP-N5c, the develop-rung LEAF's term) drops the GENERAL-worth
        slots — a card's latent tier where it fills no SPECIFIC need. Keep-value WANTS them (deciding
        what to shed prices a spare by its latent worth), but the LEAF must NOT: at end-of-turn a
        generically-good card still IN hand is a card I chose not to deploy, so crediting its latent
        worth rewards HOARDING over deploying (the WP-N5b regression — 676/677 held for +23 beat the
        line that played them). The grill's own term is "held cards with a LIVE use" = the SPECIFIC
        needs only (deploy-now / fund / answer-doom / supply-wincon / fuel / line), not latent worth."""
        from common import needs
        from common.card_worth import ROLE_TIER, ACE_SPEC_TIER, ENERGY_TIER, TAG_TIER
        me = self._my_player(obs)
        line_roles = {r for r, kinds in needs.SUPPLIES.items() if "line" in kinds and r in ROLE_TIER}
        slots: list = []
        elig: list = [set() for _ in rows]

        def _emit(slot, members) -> None:
            j = len(slots)
            slots.append(slot)
            for m in members:
                elig[m].add(j)

        def _tags(cid) -> set:
            return set(self.functions.tags(cid)) if (self.functions and cid is not None) else set()

        by_cid: dict = {}
        for k, r in enumerate(rows):
            by_cid.setdefault(r["cid"], []).append(k)
        for cid, members in by_cid.items():
            st = self.stats.get(cid) if self.stats else None
            roles = self._roles_of(cid)
            if cid in self._line_preevo_set():
                roles = [*roles, "win_condition_base"]   # the derived line-member worth (WORTH-ONLY)
            # A LINE slot is a BODY to assemble — Pokémon only (an ACE-SPEC Trainer keeps its
            # one-per-deck line claim). An Energy with a line-class derived role (Ignition as
            # `accel_source`) must NOT reopen a line: it resurrects the spent burst the fund-attack
            # absence just re-derived (corpus 83454549-36).
            worth = 0.0
            if st is not None and getattr(st, "is_pokemon", False):
                worth = max((ROLE_TIER[r] for r in roles if r in line_roles), default=0.0)
            if st is not None and getattr(st, "aceSpec", False):
                worth = max(worth, ACE_SPEC_TIER)
            deploy = rows[members[0]].get("deploy", 1.0)
            if worth * deploy > 0:
                # URGENT succession (the answer-doom ruling): MY Active is doomed and this class is
                # the successor with its base already in play — its replacement is needed imminently,
                # so its succession slot goes FULL tier at deadline 0 (the old answer-doom successor
                # spike, re-derived as the line's OWN worth; the successor no longer rides the flat
                # answer-doom slot). Same granularity as the retired answer-doom test.
                urgent = bool(board.active_doomed and cid in self._wincon_set()
                              and getattr(board, "line_preevo_in_play", False))
                # READINESS (piece 1): the primary comes online when its base is in play AND already
                # powered (evolve next turn, attack soon ⇒ deadline 1); a base in play but unpowered,
                # or not yet benched, is a turn further (2). The backup (succession) is one hop behind
                # the primary. Consumed ONLY by the refresh-SHED resupply window (`_refresh_slot_
                # resupply`) — inert for the live discard decider, which reads no deadline. Two live
                # Staryu that make both Mega Starmie imminent lines can no longer be shed for ~nothing.
                line_deadline = self._line_readiness_deadline(me, cid)
                for s in needs.line_slots(f"line:{cid}", value=worth * deploy,
                                          succession=bool(set(roles) & needs.SUCCESSION_ROLES),
                                          primary_met=cid in board.in_play_ids,
                                          succession_urgent=urgent,
                                          deadline=line_deadline,
                                          succ_deadline=line_deadline + 1):
                    _emit(s, members)
            if cid in getattr(board, "deploy_now_ids", frozenset()):
                _emit(needs.deploy_now_slot(f"deploy:{cid}", value=self._role_value(cid)), members)
        tutors = [k for k, r in enumerate(rows)
                  if r.get("deploy", 1.0) > 0
                  and ("tutor" in self._roles_of(r["cid"])
                       or ({"rush_evolve", "tutor_mega"} & _tags(r["cid"])))]
        supply = needs.supply_wincon_slot(
            wincon_in_hand=bool(getattr(board, "wincon_in_hand", False)), target_reachable=True)
        if supply is not None and tutors:
            _emit(supply, tutors)

        def _engine(cid) -> bool:
            st = self.stats.get(cid) if self.stats else None
            return ("engine" in self._roles_of(cid)
                    or bool(st is not None and getattr(st, "is_supporter", False)
                            and (_ENGINE_KEEP_TAGS & _tags(cid))
                            and "hand_disruption" not in _tags(cid)))

        engines = [k for k, r in enumerate(rows) if _engine(r["cid"])]
        if engines:
            online = sum(1 for pid in board.in_play_ids if "engine" in self._roles_of(pid))
            # The band reads off the eligible suppliers: an engine BODY need is the engine-role
            # tier; a supporter-only need is v1's tuned engine-supporter band (corpus 83686860-11
            # — a 12-point Lillie's out-priced the fund Energies the human keeps).
            band = (ROLE_TIER["engine"]
                    if any("engine" in self._roles_of(rows[k]["cid"]) for k in engines)
                    else _ENGINE_SUPPORTER_KEEP)
            _emit(needs.draw_engine_slot(engines_online=online, value=band), engines)
        active = next((p for p in (me.get("active") or []) if p), None)
        if active is not None:
            ast = self.stats.get(active.get("id")) if self.stats else None
            remaining = max(0, (getattr(ast, "maxDamageCost", 0) or 0)
                            - len(active.get("energies") or []))
            funders = [k for k, r in enumerate(rows)
                       if getattr(self.stats.get(r["cid"]) if self.stats else None,
                                  "is_basic_energy", False) or "discard_eot" in _tags(r["cid"])]
            if remaining and funders:
                for s in needs.fund_attack_slots("active", remaining,
                                                 quota_spent=bool(board.energy_attached)):
                    _emit(s, funders)
        if board.active_doomed:
            # The answer-doom slot is now the SWITCH/HEAL rescue only (the successor rides the URGENT
            # succession slot above), VALUED at the doomed body's OWN preserved worth (the grill
            # ruling): saving the Active is worth exactly what the Active is worth — a Switch that
            # rescues a 12-point engine Lunatone earns 12 (ep83661652 f40), a filler active earns ~0
            # and is not worth a card to save. NOT the flat clutch_heal tier, NOT the swap's catalog
            # worth. No slot when the active is worthless (`_role_value` 0 → `answer_doom_slot`
            # emits value 0, priced out by the assignment).
            answers = [k for k, r in enumerate(rows) if {"clutch_heal", "switch"} & _tags(r["cid"])]
            preserved = self._role_value(active.get("id")) if active is not None else 0.0
            if answers and preserved > 0:
                _emit(needs.answer_doom_slot(value=preserved), answers)
        # OPPONENT DENY SLOTS (thread 2; the grill's Round-3 ruling — VISIBLE state + basic
        # lookahead of their IN-PLAY bodies only): one slot per opponent body a strip actually
        # bites, VALUED at the DISRUPTION CARD-TIER (the grill's currency ruling, 2026-07-20 — the
        # deny slot is worth the card-worth of holding the strip, ~10 in the ONE currency, NOT the
        # ADR-0062 DAMAGE swing ~140; whether to FIRE the strip is a line evaluation the play-side
        # gust rungs own, not a keep price) and GRADED by the body's visible turns-to-ready
        # (`needs.deny_slot` — a ready threat's strip is worth its full card tier, a far-off one
        # discounts; the 86091435-68 ruling with timing). The ADR-0062 oracle (`_denial_at`) is now
        # a GATE only: `> 0` = the strip BITES this body (it has energy to strip / is worth reaching),
        # and a KO-able Active denies nothing (`active_can_ko` drop, consumed intact). Eligibility
        # routes through the SUPPLIES net: any held row carrying a deny-supplying tag
        # (gust / energy_denial). Fail-closed everywhere: no deny-capable row, no opponent read,
        # unknown stats (`_opp_turns_to_ready` → None) or a strip that bites nothing → NO slot —
        # those rows keep pricing at the shipped hedge. The disruption band is the ONE-currency
        # gust tier (`TAG_TIER["gust"]`, ~10) — NOT each denier's global worth (a role-less Hammer
        # stays worth 0 globally; only its live-strip DENY slot earns the band), so the leaf and
        # every other worth site are untouched.
        deny_tags = {src for src, kinds in needs.SUPPLIES.items() if "deny" in kinds}
        deniers = [k for k, r in enumerate(rows) if deny_tags & _tags(r["cid"])]
        deny_tier = TAG_TIER["gust"]
        if deniers:
            state = obs.get("current") or {}
            players = state.get("players") or []
            yi = state.get("yourIndex", 0)
            opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else None
            areas = [("bench", (opp or {}).get("bench") or [])]
            if not board.active_can_ko:
                areas.insert(0, ("active", (opp or {}).get("active") or []))
            for area, bodies in areas:
                for bi, p in enumerate(bodies):
                    if not p or self._denial_at(p) <= 0:   # the strip must BITE this body (oracle as
                        continue                            # a GATE, its damage magnitude discarded)
                    t = self._opp_turns_to_ready(p)
                    if t is None:
                        continue               # unknown stats — fail closed, no deny slot
                    _emit(needs.deny_slot(f"deny:{area}{bi}:{p.get('id')}",
                                          oracle_value=deny_tier, turns_to_ready=t), deniers)
        fuels = [k for k, r in enumerate(rows) if r.get("fuel")]
        if fuels:
            _emit(needs.fuel_slot("fuel", value=ENERGY_TIER), fuels)
        # GENERAL-WORTH slots (WP-N5): a held card with role worth that fills no SPECIFIC need still
        # carries LATENT board value — its tier, discounted (`_GENERAL_WORTH_W`, the leaf's bench
        # position weight) and DE-DUPLICATED (one slot per distinct cid, so spare copies price
        # marginally). Below every specific slot, so a need-filler assigns to its need first; the
        # floor the refresh-SHED sweep (WP-N4b) proved missing — a hand of playable pieces is no
        # longer shuffle-priced at ~0. The readiness leaf's `contribution × saturation` for the HAND.
        # The LEAF opts OUT (`include_general=False`, WP-N5c): at end-of-turn latent worth rewards
        # HOARDING over deploying (676/677 held for +23 beat the line that played them) — the leaf's
        # actionable-resource term is "held cards with a LIVE use" (the specific needs above) only.
        # A card class eligible for the SATURATING draw-engine need gets NO general slot (the
        # duplicate-Supporter ruling, 2026-07-20): one copy fills the one-per-turn need, the SPARE
        # covers nothing and prices 0 — "a second copy of a Supporter is 0; you'll lose it in a
        # shuffle for free" (ep82522698 f36, two Wally's). The residual-worth tiebreak still ranks
        # the spare above outright dead cards in pitch order; it just carries no keep value.
        engine_cids = {rows[k]["cid"] for k in engines}
        seen_general: set = set()
        for cid, members in (by_cid.items() if include_general else ()):
            if cid in seen_general or cid in engine_cids:
                continue
            seen_general.add(cid)
            # A row the PITCH term flags as dead-weight (spent_burst / fuel / dead_opener / stranded
            # / redundant_tutor / fodder) is fodder NOW — no LATENT worth, no general slot (else the
            # general worth RESURRECTS a spent burst v1 correctly zeroed — c4f5, the 83454549-36 trap
            # again). Context-correct: refresh rows carry no pitch flag (a SHUFFLED burst IS a future
            # attach), so they keep their general worth.
            live = [m for m in members if rows[m].get("pitch", 0) == 0]
            if not live:
                continue
            worth = self._role_value(cid)
            deploy = rows[live[0]].get("deploy", 1.0)
            if worth * deploy > 0:
                liq = self._general_liquidity(cid, board, me)   # piece 2b: illiquid latent worth discounts
                _emit(needs.general_worth_slot(f"general:{cid}",
                                               value=worth * deploy * _GENERAL_WORTH_W * liq), live)
        return slots, elig

    def _needs_hand_rows(self, obs: dict, board: Board, exclude_cid=None) -> list:
        """The whole-hand v2 rows for the refresh-SHED shadow: one row per held card (minus ONE copy
        of ``exclude_cid`` — the played refresh, discarded not shuffled, exactly as v1's
        `_hand_keep`), carrying the fields `_resolve_needs` reads (``cid``, ``deploy`` — the v1 gate
        factor v2 consumes — and ``fuel``) plus ``worth`` for display. The refresh analog of
        `_discard_equation_rows`' per-card facts, over the hand instead of the discard options."""
        from collections import Counter
        me = self._my_player(obs)
        hand_ids = [c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None]
        ids = list(hand_ids)
        if exclude_cid in ids:
            ids.remove(exclude_cid)
        counts = board.deck_known_counts
        if not counts:
            unseen = Counter(self.deck)
            unseen.subtract(self._visible_card_counts(me))
            counts = {cid: n for cid, n in unseen.items() if n > 0}
        fuel_types = self._discard_fuel_types()
        rows = []
        for k, cid in enumerate(ids):
            st = self.stats.get(cid) if self.stats else None
            fuel = bool(st is not None and getattr(st, "is_basic_energy", False)
                        and (None in fuel_types or getattr(st, "energyType", None) in fuel_types))
            rows.append({"i": k, "cid": cid, "worth": round(self._role_value(cid), 1),
                         "deploy": self._deploy_odds(cid, board, counts), "fuel": fuel})
        return rows

    def _held_undeployable(self, cid, ctx: dict) -> bool:
        """WP-N5d — the deployability COUNTERFACTUAL: could this held card NOT have been deployed
        during the turn that just ended? Only such cards are FUTURE VALUE the leaf may credit; a
        deployable card still in hand is a card I CHOSE not to play — a fumble or a deliberate hold,
        both already priced elsewhere (the spend account / the keep sites) — and crediting it
        rewards hoarding (the N5b/N5c regression: two held deployables at +23 beat the line that
        played them). ``ctx`` = the sim's `heldCtx` snapshot (the last my-perspective turn facts;
        `_simulate_line`). Per class, rules.md quotas at source: an Energy is undeployable iff the
        one manual attach was already spent (§3); a Supporter iff the Supporter slot was spent (§3);
        an evolution iff NO eligible base was in play (matching ``evolvesFrom`` name, in play since
        last turn — no evolving a just-arrived body, §4); a Basic iff the bench was full. Items /
        Tools / Stadiums are always deployable → never credited (a deliberate hold — e.g. a switch
        banked under doom — is the survival/keep sites' jurisdiction, not board readiness). Unknown
        stats → False (err toward NOT rewarding a hold)."""
        st = self.stats.get(cid) if self.stats else None
        if st is None:
            return False
        if getattr(st, "is_energy", False):
            return bool(ctx.get("energyAttached"))
        if getattr(st, "is_supporter", False):
            return bool(ctx.get("supporterPlayed"))
        base = getattr(st, "evolvesFrom", None)
        if base:
            eligible = any(b and not b.get("appearThisTurn")
                           and getattr(self.stats.get(b.get("id")), "name", None) == base
                           for b in (ctx.get("bodies") or ()))
            return not eligible
        if getattr(st, "is_pokemon", False):
            return bool(ctx.get("benchFull"))
        return False

    def _hand_readiness(self, end_obs: dict, my_index: int) -> float:
        """WP-N5b/N5d (armed OFF, `leaf_hand_value`): the develop-rung LEAF's actionable-resource
        term — readiness CONSUMES the needs module. The value of the held cards that COULD NOT have
        been deployed this turn (`_held_undeployable` — the N5d complement) = their JOINT slot
        coverage under the exact assignment (`needs.set_keep_v2` over the resolved hand, specific
        needs only — `include_general=False`, N5c), the SAME valuation the keep-value sites use —
        one vocabulary, not a rival (the grill's "do NOT build a rival" ruling). Deployable held
        cards still PARTICIPATE in the assignment (a deployable copy covering a slot correctly
        shrinks an undeployable sibling's marginal) — they just earn no credit themselves. Requires
        the sim's injected hand + `heldCtx` (fail-safe 0 without either — no plumbing → no term).
        Capped under the sub-prize budget; `_HAND_TIEBREAK_W/_CAP` is the ε sizing alternative
        (split only exact ties). Never raises."""
        cur = (end_obs or {}).get("current") or {}
        players = cur.get("players") or []
        me = players[my_index] if 0 <= my_index < len(players) and players[my_index] else {}
        ctx = me.get("heldCtx")
        if not me.get("hand") or not ctx:
            return 0.0
        # a MY-perspective view of the (opponent-perspective) end obs — the resolver reads
        # `_my_player`/board facts off `yourIndex`; the injected hand is already on players[my_index].
        mobs = {**end_obs, "current": {**cur, "yourIndex": my_index}}
        try:
            board = self._board_hypothetical(mobs)
            rows = self._needs_hand_rows(mobs, board)
            if not rows:
                return 0.0
            held = [k for k, r in enumerate(rows) if self._held_undeployable(r["cid"], ctx)]
            if not held:
                return 0.0
            slots, elig = self._resolve_needs(mobs, board, rows, include_general=False)
            resupply = [0.0] * len(slots)
            from common import needs
            val = needs.set_keep_v2(slots, elig, resupply, held)
        except Exception:
            return 0.0                                   # a featurize/resolve slip never crashes ranking
        return min(_HAND_READINESS_CAP, val * _HAND_READINESS_W)

    def _refresh_slot_resupply(self, slots, elig, rows, obs: dict, board: Board,
                               draws: int) -> list:
        """The slot-RESUPPLY leg for the REFRESH window (the WP-N5 residual's staged fix): per slot,
        P(the closure re-supplies it within the refresh's own ``draws``-card window) — the discount
        `needs.assignment_value` applies to a covered slot's marginal (×(1−r)) and credits an
        uncovered one (×r). The whole hand shuffles in with the played refresh, so the outs are the
        slot's supplier CLASSES pointed backwards over the shuffle-grown pool: deck copies + the
        tutors reaching any class (`fetch_closure.class_reaccess_outs` — each tutor once), with the
        slot's own eligible HELD copies joining as CERTAIN outs (a shuffled hand card is never
        prize-assignable) — v1's `_keep_cost` model per slot instead of per copy.

        Fail directions, all toward KEEP (a lower r → a higher shed price — the sweep's measured
        SAFE side): ``deploy_now`` / ``answer_doom`` slots stay 0.0 (the closing edge,
        `gate_library.closing_gate_reaccess` — re-access is not bankable against a this-turn
        deadline), and so does ANY ``deny`` or ``line`` slot at deadline ≤ 0 — a strip needed NOW
        (thread-2 ruling: not re-drawable in time) or the URGENT successor line slot (the
        answer-doom ruling: a doomed wincon's replacement is needed imminently); a slot with slack
        banks re-access like any other; the supplier classes are read off the HELD eligibility
        only (a deck-only filler
        class is not counted); the no-deadline (99) slots take the plain window, only
        ``fund_attack`` widens by its quota deadline (`gate_library.quota_window` re-derived:
        window = draws + deadline, one natural draw per intervening turn); unresolved deck
        bookkeeping → all-0.0 (no discount — v2 keeps over-pricing rather than under-pricing).
        Pre-anchor the outs are prize-split-weighted (`_prize_split_hit`), anchored the plain
        window draw — exactly the `_refresh_shed_keepcost` bookkeeping. Pitch-side (fuel) slots
        never enter the keep DP; theirs stay 0.0.

        ``general`` slots ALSO stay 0.0 — measured, not doctrinal (sweep 2026-07-20): their value
        already carries `_GENERAL_WORTH_W` (0.45), a latent-worth constant MEASURED with resupply
        at 0.0 (WP-N5: under-pricing 46→19 came from W alone), so W is empirically the site's
        whole re-access + latency discount. Stacking ×(1−r) on top priced a general slot at
        ~0.45 × v1's own re-access model and flipped the sweep to the UNSAFE side (under-pricing
        19→62, sign-flips 13→17). Re-open only as a JOINT re-measure of W and r, never r alone."""
        from common import fetch_closure
        from common.deck_odds import draw_hit_probability
        out = [0.0] * len(slots)
        me = self._my_player(obs)
        counts = board.deck_known_counts
        if counts:
            deck_count = sum(counts.values())
            prizes_hidden = 0                                    # anchored: the split is resolved
        else:
            from collections import Counter
            unseen = Counter(self.deck)
            unseen.subtract(self._visible_card_counts(me))
            counts = {cid: n for cid, n in unseen.items() if n > 0}
            prizes_hidden = sum(1 for p in (me.get("prize") or [])
                                if not (isinstance(p, dict) and p.get("id") is not None))
            deck_count = sum(counts.values()) - prizes_hidden
            if deck_count <= 0 or not counts:
                return out
        pool = deck_count + len(rows)                            # the shuffle-grown pool: rows ARE
        members: list = [[] for _ in slots]                      # the shuffled copies (refresh excluded)
        for k, js in enumerate(elig):
            for j in js:
                members[j].append(k)
        for j, s in enumerate(slots):
            if (s.supplied_by_pitch or s.kind in ("deploy_now", "answer_doom", "general")
                    or (s.kind in ("deny", "line") and s.deadline <= 0) or not members[j]):
                continue                       # closing edge: a THIS-TURN deadline (the urgent
                                               # successor, a ready-threat deny) can't bank re-access
            classes = {rows[k]["cid"] for k in members[j]}
            u = fetch_closure.class_reaccess_outs(classes, counts, self._closure_stat_of,
                                                  self._closure_clauses_of)
            certain = len(members[j])
            # fund_attack widens by its quota deadline; a LINE slot CLAMPS to its readiness deadline
            # (piece 1) — a wincon one attach from live gets only its ~1-2-draw re-access window, not
            # the whole refresh redraw, so its shed cost stays material; other slots take the window.
            if s.kind == "fund_attack":
                window = draws + s.deadline
            elif s.kind == "line":
                window = min(draws, s.deadline)
            else:
                window = draws
            if prizes_hidden > 0:
                r = self._prize_split_hit(u, deck_count, prizes_hidden, pool, window,
                                          certain=certain)
            else:
                r = draw_hit_probability(u + certain, pool, window)
            out[j] = max(0.0, min(1.0, r))
        return out

    def _refresh_shed_shadow(self, obs: dict, select: dict, board: Board, options: list,
                             traces: list, chosen: list):
        """WP-N4b: the refresh-SHED keep-value v2 MAGNITUDE shadow — the refresh analog of the
        discard shadow, deciding NOTHING (the SHED still uses v1's Σ keep_cost). At the refresh PLAY
        option the agent would actually play (top tactical among refreshes), emit v1's shed
        (`_refresh_shed_keepcost`) beside v2's whole-hand assignment marginal (`needs.set_keep_v2`
        over the held hand, slot resupply LIVE over the refresh draw window —
        `_refresh_slot_resupply`, the WP-N5 residual's fix) — the site where sets-not-sums bites: v1
        SUMS duplicate wincons and OVER-charges the shed (refresh looks too costly), v2 prices the
        pair as one line + the succession slot. Since the shed is the ONLY term that changes, the refresh
        swing follows by ``swing_v2 = swing_v1 + (v1_shed − v2_shed)``; the decision-relevant
        agreement is the SIGN bit (would swapping the shed flip play/don't-play?), the magnitude
        analog of the discard's pick agreement. None off a real refresh PLAY option or mid-sim
        (`self._planning`)."""
        if self._planning:
            return None
        from common import needs
        from common.strategy.refresh import refresh_branches
        refresh_opts = []
        for i, o in enumerate(options):
            if o.get("type") != _PLAY:
                continue
            cid = self._option_card_id(obs, select, o)
            if cid is not None and refresh_branches(cid, board.my_prizes_remaining,
                                                    board.opp_prizes_remaining):
                refresh_opts.append((i, cid))
        if not refresh_opts:
            return None
        i, cid = max(refresh_opts, key=lambda ic: traces[ic[0]].tactical)
        # A MINIMAL ctx — only the two fields `_refresh_shed_keepcost` / `_refresh_swing_tactical`
        # read (card_id, option_type) — so the shadow never re-runs the heavyweight `_context`
        # (already built per-option in the trace loop); both helpers are pure reads.
        from types import SimpleNamespace
        ctx = SimpleNamespace(card_id=cid, option_type=_PLAY)
        v1_shed = self._refresh_shed_keepcost(obs, board, ctx)
        swing_v1 = self._refresh_swing_tactical(obs, board, ctx)
        rows = self._needs_hand_rows(obs, board, exclude_cid=cid)
        slots, elig = self._resolve_needs(obs, board, rows)
        branches = refresh_branches(cid, board.my_prizes_remaining, board.opp_prizes_remaining)
        draws = max((my_draw for my_draw, _opp in branches or ()), default=0)
        resupply = self._refresh_slot_resupply(slots, elig, rows, obs, board, draws)
        v2_shed = needs.set_keep_v2(slots, elig, resupply, range(len(rows))) if rows else 0.0
        for k, r in enumerate(rows):
            r["keep_v2"] = round(needs.keep_v2(slots, elig, resupply, k), 1)
        swing_v2 = swing_v1 + (v1_shed - v2_shed)
        # PIECE 2 (report-only): the adaptive draw credit beside the flat CYCLE, and the swing that
        # applies BOTH the graded shed and the adaptive cycle. Decides nothing; measured before promotion.
        cycle_adaptive = self._refresh_cycle_adaptive(obs, board, cid)
        swing_v2_cyc = swing_v2 + (cycle_adaptive - _REFRESH_CYCLE)
        # DECISION CONTEXT for the ladder-time promotion analysis: the isolated swing is NOT the
        # decision — a positive shed swing on a frame the human ruled "don't shuffle" is benign when
        # another option out-scores the refresh (attach-first / lethal / deferred-fetch carry it). To
        # judge a v1->v2c promotion from ladder logs we must know whether the shed+cycle DELTA
        # (swing_v2_cyc − swing_v1) would move the refresh past its best rival:
        #   promoted_refresh_wins  ==  refresh_score + (swing_v2_cyc − swing_v1) > best_other_score
        # so emit both the refresh option's own score and the best NON-refresh option's score.
        refresh_idx = {j for j, _ in refresh_opts}
        refresh_score = traces[i].score
        other = [traces[j].score for j in range(len(options)) if j not in refresh_idx]
        best_other_score = max(other) if other else None
        return {"i": i, "cid": cid, "v1_shed": round(v1_shed, 1), "v2_shed": round(v2_shed, 1),
                "swing_v1": round(swing_v1, 1), "swing_v2": round(swing_v2, 1),
                "cycle_adaptive": round(cycle_adaptive, 1), "swing_v2_cyc": round(swing_v2_cyc, 1),
                "refresh_score": round(refresh_score, 1),
                "best_other_score": round(best_other_score, 1) if best_other_score is not None else None,
                "sign_agree": (swing_v1 >= 0) == (swing_v2 >= 0),
                "played": i in (chosen or []), "eq": rows}

    def _attach_readiness(self, cid, energy: int) -> float:
        """Best printed damage the body ``cid`` can afford with ``energy`` Energy — a 2-point
        threshold model off `CardStat` (cheapest attack / biggest attack). Opponent-independent, so
        it credits a BENCHED body's progress toward its OWN payoff (Nebula Beam 210 at 3, Jetting
        Blow 120 at 1) and reads 0 below the cheapest cost. The marginal of an attach is the delta of
        this across the extra Energy — over-attach on a maxed body is 0, a threshold-crossing attach
        is a big jump (the concentrate signal falls out)."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if st is None:
            return 0.0
        maxc, minc = getattr(st, "maxDamageCost", None), getattr(st, "minAttackCost", None)
        if maxc is not None and energy >= maxc:
            return float(getattr(st, "maxDamage", 0) or 0)
        if minc is not None and energy >= minc:
            return float(getattr(st, "minCostDamage", 0) or getattr(st, "maxDamage", 0) or 0)
        return 0.0

    def _opp_body_hps(self, obs: dict) -> list:
        """Current HP of every opponent Pokémon in play (Active + Bench) — the overkill-cap read: a
        bigger attack buys nothing once the current one already covers the biggest body on the board."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if len(players) > 1 else None
        if not opp:
            return []
        bodies = list(opp.get("active") or []) + list(opp.get("bench") or [])
        return [m.get("hp", 0) for m in bodies if m]

    def _attach_progress(self, cid, energy: int) -> float:
        """CONVEX forward-build value of body ``cid`` at ``energy`` Energy toward its biggest attack
        (attach grill Ruling 1). ``(min(e, M) / M)**2 * maxDamage`` — the SQUARE makes the marginal
        of the k-th Energy INCREASE with k, so completing a started carrier is worth more than
        starting a fresh body: concentrate on the most-built survivable carrier falls out (82523811-59,
        82749168-61), while the maxed body's marginal is 0 (over-attach). Falls back to the flat 2-point
        readiness when the biggest-attack cost is unknown."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        maxc = getattr(st, "maxDamageCost", None) if st is not None else None
        dmax = float(getattr(st, "maxDamage", 0) or 0) if st is not None else 0.0
        if not maxc or maxc <= 0 or dmax <= 0:
            return self._attach_readiness(cid, energy)
        frac = min(energy, maxc) / maxc
        return frac * frac * dmax

    def _partner_absent(self, cid, obs: dict) -> bool:
        """Ruling 6: `cid` is a co-dependent ENGINE body whose value requires a partner in play
        (Solrock needs a Lunatone, and vice-versa — `strategy.partners`), and NONE of its declared
        partners is on my board right now → a dead attach target, value it at 0. Partner-AGNOSTIC in
        the general oracle: the pairing itself is deck-declared data (ADR-0034). False for any body
        with no declared partner."""
        partners = getattr(self.strategy, "partners", None) or {}
        need = partners.get(cid)
        if not need:
            return False
        me = self._my_player(obs)
        in_play = {m.get("id") for m in ((me.get("active") or []) + (me.get("bench") or [])) if m}
        return not any(p in in_play for p in need)

    def _accel_attack_id(self, cid):
        """The body's attack that carries an energy-accel rider (recoverN > 0) — Turbo Flare / Aura
        Jab. None when the body has no accelerator attack."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        for aid in (getattr(st, "attacks", None) or ()):
            ast = self._attack_stat(aid)
            if ast and getattr(ast, "recoverN", 0):
                return aid
        return None

    def _accel_routed_value(self, obs: dict, board: Board, routed: int) -> float:
        """Value of the ``routed`` Energy an accelerator attack (Turbo Flare) attaches to the Bench —
        Ruling 4: an attach that FIRES an accelerator is worth the forward build the routed Energy
        buys on the survivable carrier, not the accelerator's own face damage. Concentrated onto the
        single Bench Line body that gains the most (the accel routes 'in any way you like'), priced in
        the same convex-build currency (`_attach_progress`)."""
        if routed <= 0:
            return 0.0
        me = self._my_player(obs)
        line_ids = self._line_preevo_set() | self._wincon_set()
        best = 0.0
        for b in (me.get("bench") or []):
            if not b:
                continue
            cid = b.get("id")
            if cid not in line_ids and self._is_utility_body(cid):
                continue                                       # don't credit routing onto a utility body
            have = len(b.get("energies") or [])
            best = max(best, self._attach_progress(cid, have + routed) - self._attach_progress(cid, have))
        return best

    def _attach_value(self, obs: dict, select: dict, board: Board, option: dict):
        """Phase-1 shadow of ONE energy-attach option (attach grill ruling, 2026-07-21). DECIDES
        NOTHING. Returns a per-option working row, or None to ABSTAIN — Ruling 3: a Pokémon Tool
        rides `OptionType.ATTACH` but is not Energy, so it is never priced here.

        The row's fields ARE the ruled terms (ranked lexicographically in `_attach_shadow`):
          * `marginal`      — max(`this_turn`, survival-weighted `build`, `accel_value`), gated to 0
                              for a non-attacking role (Ruling 5b/6-partial) and for a discard-EOT burst
                              that EVAPORATES on a body that can't attack this turn (the guard).
                              `this_turn` is the attack the Active unlocks tonight; `build` is the CONVEX
                              forward progress toward the biggest attack (Ruling 1), zeroed for a doomed
                              carrier; `accel_value` is the forward build the Energy an ACTIVE
                              accelerator ROUTES buys on the survivable carrier (Ruling 4).
          * `line_value`    — worth of the line the body advances (`_role_value`, line-aware); the
                              target-choice tie-break (wincon line over filler).
          * `resource_cost` — the spent Energy's own worth (`_role_value`); breaks the same-target,
                              same-marginal tie toward the reusable Basic over the burst.
        NOTE the remaining term (partner-conditional role, Ruling 6) is a LATER deck-layer increment —
        the frame that needs it is xfail in test_attach_shadow.py."""
        ctx = select.get("context")
        is_attach = option.get("type") == _ATTACH
        is_from = ctx == _ATTACH_FROM and option.get("type") == _CARD
        if not (is_attach or is_from):
            return None
        ecid = self._option_card_id(obs, select, option)
        estat = self.stats.get(ecid) if (self.stats and ecid is not None) else None
        if is_attach and not self._attach_is_energy(estat):
            return None                                        # Ruling 3: a Tool is not Energy
        target = self._attach_target(obs, option)
        if target is None and is_from:
            target = self._option_pokemon(obs, select, option)
        if target is None:
            return None
        tcid = target.get("id")
        have = len(target.get("energies") or [])
        area = option.get("inPlayArea") if is_attach else _BENCH   # accel recipients are benched
        etags = set(self.functions.tags(ecid)) if (self.functions and ecid is not None) else set()
        burst = "discard_eot" in etags
        # a burst that can't be cashed THIS turn evaporates at end of turn — no durable progress
        can_cash = area == _ACTIVE and board.turn > 1
        evaporates = burst and not can_cash
        # Ruling 5b/6-partial: a body whose job is non-attacking (wall / draw-engine, and not a
        # win-condition Line member) advances no valued attack — its marginal is 0.
        line_ids = self._line_preevo_set() | self._wincon_set()
        non_attacking = tcid not in line_ids and (
            self._is_utility_body(tcid) or self._is_draw_engine_body(tcid)
            or self._partner_absent(tcid, obs))         # Ruling 6: a partnerless co-dependent engine
        # Ruling 1 (carrier-survival forward P-term) + 2a (arm-the-doomed): the attach's marginal is the
        # BETTER of two readings — the immediate attack it unlocks THIS turn (only the Active fires this
        # turn), and the survival-weighted forward BUILD toward the body's biggest attack. A DOOMED
        # carrier earns no build credit (it won't live to fire the bigger attack — `dont-feed-the-
        # doomed`), so a doomed Active scores only if this Energy arms an attack tonight (arm-the-doomed);
        # a survivable carrier banks the build, so the most-built survivable body wins the concentrate.
        this_turn = (self._attach_readiness(tcid, have + 1)
                     - self._attach_readiness(tcid, have)) if area == _ACTIVE else 0.0
        survives = not (area == _ACTIVE and board.active_doomed)      # forward-survival of the carrier
        build = (self._attach_progress(tcid, have + 1)
                 - self._attach_progress(tcid, have)) if survives else 0.0
        # Ruling 2b (overkill cap): once the ACTIVE already KOs the opponent's Active AND its current
        # affordable attack already covers the biggest body on their board, a bigger attack buys
        # nothing more this game-state — stop over-building it and develop a second threat instead
        # (82750161-59: Jetting KOs the 80-HP Riolu, Nebula 210 overkills a 110-HP board). Opponent-
        # aware, so it does NOT fire when a bench threat still out-HPs the cheap attack (82523811-59:
        # Hariyama 150 needs Nebula), where Ruling 1's build stands.
        overkill = False
        if area == _ACTIVE and board.active_cheap_attack_kos:
            opp_hp = self._opp_body_hps(obs)
            if opp_hp and max(opp_hp) <= self._attach_readiness(tcid, have):
                overkill = True
        # Ruling 4 (accel-routing): an attach that lets an ACTIVE accelerator FIRE (Cinderace's Turbo
        # Flare) is worth the forward build the Energy it ROUTES buys on the survivable carrier, not the
        # accelerator's own face damage — holds even for a doomed accelerator (it powers the successor
        # before falling, 83037962-70). Prize-math delay stays OUT (planner-scope).
        accel_value = 0.0
        feeds_accel = (area == _ACTIVE and "accel_source" in self._roles_of(tcid)
                       and self._attach_target_needs(target)
                       and not board.accel_recipient_missing and not board.bench_wincon_ready)
        if feeds_accel:
            aid = self._accel_attack_id(tcid)
            ast = self._attack_stat(aid) if aid is not None else None
            if ast is not None:
                # EXPECTED routing for the value estimate: the printed ceiling capped by what the
                # recipients can actually use. (The live decider's `_recover_units` also floors this by
                # the prize-paranoid deck-fuel bound — a grader-safety concern for a COMMITMENT, not for
                # a shadow value read.)
                routed = min(getattr(ast, "recoverN", 0), self._recover_recipient_need(ast, board, obs))
                accel_value = self._accel_routed_value(obs, board, routed)
        marginal = 0.0 if (non_attacking or evaporates or overkill) else max(this_turn, build, accel_value, 0.0)
        type_wasted = bool(self._attach_type_wasted(estat, target))   # off-type: doesn't cover the need
        return {"i": None, "target": tcid, "energy": ecid,
                "marginal": round(marginal, 1), "this_turn": round(this_turn, 1),
                "build": round(build, 1), "accel_value": round(accel_value, 1), "doomed": not survives,
                "line_value": round(0.0 if non_attacking else self._role_value(tcid), 1),
                "resource_cost": round(self._role_value(ecid) if ecid is not None else 0.0, 1),
                "type_wasted": type_wasted, "burst": burst, "evaporates": evaporates}

    def _attach_shadow(self, obs: dict, select: dict, board: Board, options: list,
                       traces: list, chosen: list):
        """The energy-attach valuation shadow (the fourth shadow) — price every energy-attach option
        in `options` via `_attach_value`, emit the working rows + the top pick + the agreement bit vs
        the shipped rungs' `chosen`. DECIDES NOTHING. None off a real attach choice (fewer than two
        priced options) or mid-sim (`self._planning`).

        `eq_pick` ranks rows lexicographically by the ruled priority: (marginal, line_value,
        −resource_cost) — durable progress first, then the wincon line, then the reusable Energy."""
        if self._planning:
            return None
        ctx = select.get("context")
        attach_idx = [i for i, o in enumerate(options)
                      if o.get("type") == _ATTACH or (ctx == _ATTACH_FROM and o.get("type") == _CARD)]
        if len(attach_idx) < 2:
            return None
        rows, abstained = [], 0
        for i in attach_idx:
            row = self._attach_value(obs, select, board, options[i])
            if row is None:                                    # Ruling 3 abstain (Tool) — no row
                abstained += 1
                continue
            row["i"] = i
            rows.append(row)
        # Rank only options that buy DURABLE progress; if none does, the oracle attaches NOTHING
        # (`eq_pick = None`) — an all-Tool menu or a purely-wasteful attach. Priority (the ruled
        # order): marginal readiness, then the wincon line, then on-type over wasted, then reusable.
        positive = [r for r in rows if r["marginal"] > 0]
        if positive:
            best = max(positive, key=lambda r: (r["marginal"], r["line_value"],
                                                not r["type_wasted"], -r["resource_cost"]))
            eq_pick = best["i"]
            agree = eq_pick in (chosen or [])
        else:
            eq_pick = None                                     # attach nothing beats a valueless attach
            agree = not (set(chosen or []) & set(attach_idx))
        return {"eq": rows, "eq_pick": eq_pick, "abstained": abstained,
                "picks": sorted(chosen or []), "agree": agree}

    def _recover_units(self, attack_id, dmg_ctx: dict, board: Board, obs: dict) -> int:
        """Energy this attack's accel rider would actually attach AND that a recipient can
        actually USE — the development the Tactical layer credits (Aura Jab / Turbo Flare:
        attack + accelerate).

        Three independent bounds, all closed-form:
          1. `recoverN`   — the card's printed ceiling (Aura Jab: "attach up to 3").
          2. the matching Basic-Energy FUEL in the rider's SOURCE zone (`recoverSource`):
             "discard" → my open discard (`my_discard_basic_energy`, ADR-0061: re-sourced from the
             Board so it is the one truth for my discard fuel — `_damage_context` keeps its own
             attacker-relative copy because it must also serve the Incoming direction);
             "deck" → the whole-deck search's pool (`_deck_basic_energy_fuel`: tracker-exact once
             anchored, else the sound pigeonhole floor — an endorser never over-counts).
          3. the recipients' remaining NEED (ADR-0061). The old code checked only that the Bench was
             non-empty, so 3 {F} onto a Lunatone/Solrock support bench scored an identical +225 to 3
             {F} onto a Riolu that becomes the second Mega Lucario ex — and that +225 is exactly what
             tips Aura Jab (130) over Mega Brave (270). Energy nobody can pay an attack with is not
             development. Need is measured against each recipient's FORWARD form too, so a Riolu
             counts the {F}{F} its Mega Brave will cost, not the {F} its Quick Attack costs today.
             The same need gate makes Turbo Flare on an EMPTY bench credit 0 — the "firing blanks"
             signal the mega_starmie deck rules hand-encoded (hypergeometric-fetch-closure §Round 13).
        """
        st = self._attack_stat(attack_id)
        if not st or not getattr(st, "recoverN", 0):
            return 0
        if getattr(st, "recoverSource", None) == "deck":
            fuel = self._deck_basic_energy_fuel(board, obs, st.recoverEnergyType)
        else:
            by_type = (board.my_discard_basic_energy or {})
            fuel = (by_type.get(st.recoverEnergyType, 0) if st.recoverEnergyType is not None
                    else sum(by_type.values()))
        need = self._recover_recipient_need(st, board, obs)
        return max(0, min(st.recoverN, fuel, need))

    def _deck_basic_energy_fuel(self, board: Board, obs: dict, etype) -> int:
        """Matching Basic-Energy copies a whole-deck search rider (Turbo Flare) can PROVABLY still
        find in my deck. Tracker-anchored (`deck_known_counts`): the exact count. Pre-anchor: the
        sound pigeonhole FLOOR — of the ``unseen`` matching copies (decklist − visible), at most
        ``prizes_hidden`` can sit in the face-down prizes, so ≥ ``unseen − prizes_hidden`` are in
        deck. An endorser must never over-count (grader safety); the floor typically saturates the
        ``min(recoverN, …)`` anyway (9 Water unseen − 6 prizes ≥ 3). 0 without a decklist."""
        def _matches(cid) -> bool:
            st = self.stats.get(cid) if self.stats else None
            return bool(st and st.is_basic_energy
                        and (etype is None or getattr(st, "energyType", None) == etype))
        if board.deck_known_counts:
            return sum(n for cid, n in board.deck_known_counts.items() if n > 0 and _matches(cid))
        if not self.deck:
            return 0
        me = self._my_player(obs)
        visible = self._visible_card_counts(me)
        unseen = sum(n - visible.get(cid, 0) for cid, n in Counter(self.deck).items() if _matches(cid))
        prizes_hidden = sum(1 for p in (me.get("prize") or [])
                            if not (isinstance(p, dict) and p.get("id") is not None))
        return max(0, unseen - prizes_hidden)

    def _is_benchable_body(self, cid) -> bool:
        """A benchable body: a Basic Pokémon (`is_pokemon` and no `evolvesFrom` — it grounds out on
        the field itself, not as an evolution). Staryu/Riolu yes; Cinderace (evolves from Raboot) no."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        return bool(st and getattr(st, "is_pokemon", False) and not getattr(st, "evolvesFrom", None))

    def _hand_has_benchable_body(self, me: dict) -> bool:
        """True if a benchable Basic Pokémon is already IN HAND (deploy it directly)."""
        return any(self._is_benchable_body(c.get("id")) for c in (me.get("hand") or []) if c)

    def _hand_can_develop_body(self, me: dict) -> bool:
        """True if the HAND can put a body on the board this turn — a benchable Basic directly, OR a
        fetcher that produces one (`bench_fill` Poffin / `tutor_pokemon` Ball can grab a Basic). NOT a
        `tutor_mega` (Mega Signal fetches the payoff, which still needs its base). The line between a
        genuinely stranded hand (f40 — no body, no fetcher) and a developable one (ep83667237 f120 —
        a Poffin and an Ultra Ball on hand, so the Energy has a home coming and is NOT illiquid)."""
        if self._hand_has_benchable_body(me):
            return True
        body_fetch = {"bench_fill", "tutor_pokemon"}
        for c in (me.get("hand") or []):
            cid = c.get("id") if c else None
            if cid is not None and self.functions and (body_fetch & set(self.functions.tags(cid))):
                return True
        return False

    def _has_energy_recipient(self, board: Board, me: dict) -> bool:
        """True if an Energy card has a live home on my board: a benched body (bench bodies are not the
        doomed Active), a non-doomed Active, or a benchable body in hand to deploy onto. False is the
        f40 shape — a doomed Active, an empty Bench and no body in hand — where held Energy cannot be
        attached to anything that will attack, so its latent worth is illiquid."""
        if board.my_bench > 0:
            return True
        if not board.active_doomed and any(me.get("active") or []):
            return True
        return self._hand_can_develop_body(me)

    def _general_liquidity(self, cid, board: Board, me: dict) -> float:
        """PIECE 2b: the LIQUIDITY factor on a general-worth slot ∈ (`_GENERAL_ILLIQUID_FLOOR`, 1] —
        how realizable a card's LATENT worth is on the current board. An Energy with no recipient
        (`_has_energy_recipient` False) prices at the floor: catalog worth you cannot spend is not
        worth holding over a refresh (the shed mirror of piece 1's line-slot readiness — same idea, the
        keep side). 1.0 (unchanged) for everything with a live use, so only the genuinely stranded card
        is discounted; never a card list. Extends to other role-blocked worth (an evolver with no base)
        as the corpus demands — energy is the dominant f40 term and the first cut."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if st is not None and getattr(st, "is_energy", False) and not self._has_energy_recipient(board, me):
            return _GENERAL_ILLIQUID_FLOOR
        return 1.0

    def _refresh_cycle_adaptive(self, obs: dict, board: Board, cid) -> float:
        """PIECE 2 (SHADOW-reported, decides nothing yet — Ruling 3, 'CYCLE should scale to the
        situation'): the refresh DRAW credit, flat `_REFRESH_CYCLE` PLUS the open bench-deploy need a
        redraw can fill. A refresh into a starved board (`board.my_bench < _THIN_BENCH`) that the HAND
        cannot develop itself (`_hand_has_benchable_body` False — else deploy, don't shuffle) is worth
        more than card flow: the body deficit × the deploy tier × P(the redraw actually supplies a body
        from the deck over its own draw window).

        The supply probability is a VALUE estimate, not a grader-safety endorsement, so it is the
        prize-split-weighted expectation (`_prize_split_hit`, un-floored unseen) — the SAME model the
        shed's re-access uses — NOT the pigeonhole floor `_deck_basic_energy_fuel` needs (which zeroes
        a 3-of Staryu behind six hidden prizes, ep83038055 f40's exact hole). Bounded (deficit ≤
        `_THIN_BENCH`, prob ≤ 1). REPLACES nothing live — reported beside the flat CYCLE so the corpus
        can measure whether the lift fixes f40 without over-firing before it is promoted into
        `_refresh_swing_tactical`. Flat `_REFRESH_CYCLE` on a developed board or a hand that can bench."""
        from common.strategy.context import _THIN_BENCH
        from common.deck_odds import draw_hit_probability
        from common.strategy.refresh import refresh_branches
        branches = refresh_branches(cid, board.my_prizes_remaining, board.opp_prizes_remaining)
        deficit = max(0, _THIN_BENCH - board.my_bench)
        me = self._my_player(obs)
        if not branches or deficit <= 0 or self._hand_can_develop_body(me):
            return float(_REFRESH_CYCLE)
        draws = max(my_draw for my_draw, _o in branches)
        counts = board.deck_known_counts
        if counts:
            deck_count = sum(counts.values())
            prizes_hidden = 0
            outs = sum(n for c, n in counts.items() if n > 0 and self._is_benchable_body(c))
        else:
            unseen = Counter(self.deck)
            unseen.subtract(self._visible_card_counts(me))
            counts = {c: n for c, n in unseen.items() if n > 0}
            prizes_hidden = sum(1 for p in (me.get("prize") or [])
                                if not (isinstance(p, dict) and p.get("id") is not None))
            deck_count = sum(counts.values()) - prizes_hidden
            outs = sum(n for c, n in counts.items() if self._is_benchable_body(c))
        pool = deck_count + max(0, board.my_hand_size - 1)   # the shuffled hand joins the draw pool
        if outs <= 0 or deck_count <= 0 or pool <= 0:
            return float(_REFRESH_CYCLE)
        if prizes_hidden > 0:
            p = self._prize_split_hit(outs, deck_count, prizes_hidden, pool, draws)
        else:
            p = draw_hit_probability(outs, pool, draws)
        return float(_REFRESH_CYCLE) + _REFRESH_BENCH_BODY * deficit * p

    def _recover_recipient_need(self, st, board: Board, obs: dict) -> int:
        """Total Energy the rider's recipients still LACK to pay an attack — theirs or their forward
        evolution's (the dearest, since that is what the line is being built toward). 0 when the
        rider's target scope has no recipient at all (a bench-targeted recover with an empty Bench
        attaches nothing), which preserves the old empty-Bench guard as a special case."""
        me = self._my_player(obs)
        pool = []
        if st.recoverTarget in (None, "any", "bench"):
            pool += [p for p in (me.get("bench") or []) if p]
        if st.recoverTarget in (None, "any", "self"):
            pool += [p for p in (me.get("active") or []) if p]
        total = 0
        for p in pool:
            cid = p.get("id")
            forms = {cid} | set(self._forward_card_ids(cid) or ())
            costs = [self._attack_cost(aid)
                     for f in forms
                     for aid in (getattr(self.stats.get(f), "attacks", None) or ())
                     if self.stats and self.stats.get(f)]
            if not costs:
                continue
            total += max(0, max(costs) - len(p.get("energies") or []))
        return total

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
            if st is not None and st.is_typed_basic_energy:
                counts[st.energyType] = counts.get(st.energyType, 0) + 1
        return counts

    def _no_supporter_in_hand(self, me: dict) -> bool:
        """True if MY hand holds no Supporter card (cardType 3). Read by `bench-the-supporter-tutor`:
        bench a `supporter_tutor` Pokémon (Meowth ex) to fetch a Supporter only when we don't already
        hold one. Unknown stats -> False (don't assert the trigger — never bench the 2-prize ex blind)."""
        if not self.stats:
            return False
        for c in (me.get("hand") or []):
            st = self.stats.get((c or {}).get("id"))
            if st is not None and st.is_supporter:
                return False
        return True

    def _self_return_escape_credit(self, attack_id, board: Board) -> float:
        """Tactical CREDIT for a self-returning attack (Meowth ex Tuck Tail: "Put this Pokémon and all
        attached cards into your hand") when the Active is a DOOMED multi-prize body — bouncing it to
        hand denies the opponent the 2 (ex) / 3 (Mega ex) prizes it was about to bank, and re-arms a
        bench-drop Ability. Mirror of `_RECOIL_DOOM` but a survival CREDIT: it lives in the NON-KO
        branch only, so a real KO (scored KO_SCORE) always wins. 0 unless the attack self-returns, the
        Active is ex/megaEx, and it is doomed — so a healthy Meowth never scoops itself away for tempo."""
        st = self._attack_stat(attack_id)
        if not (st and getattr(st, "selfReturn", False)) or not board.active_doomed:
            return 0
        active = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        if not active or not active.is_ex_body:
            return 0
        return _SELF_RETURN_ESCAPE * active.prize_value

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
        best = max(aids, key=self._attack_damage)
        return same == best

    def _attacks_of(self, cid: int | None) -> dict:
        """``{attack_id: (cost, damage)}`` for a card id — the denial oracle's view of a body."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if st is None:
            return {}
        return {aid: (self._attack_cost(aid), self._attack_damage(aid))
                for aid in (getattr(st, "attacks", None) or ())}

    def _denial_at(self, p: dict | None) -> float:
        """Damage this Pokémon loses if ONE Energy is discarded from it (ADR-0062). 0 when the Energy
        is surplus (it still affords the same attack) or when it could not pay an attack anyway.

        Measured against the body's own attacks AND, discounted by `_DENIAL_FORWARD`, against what it
        EVOLVES INTO. "Evolving keeps attached cards" (rules.md:98), so Energy on a pre-evolution is
        being BANKED, not spent: a Riolu holds {F} for Mega Lucario ex's Aura Jab (130), not for its
        own Accelerating Stab (30). Pricing only the current form under-values every strip aimed at a
        line under construction — which is exactly where a Hammer earns its keep (ms 82225643 f12).

        The forward credit is DISCOUNTED, never taken at face value: the payoff is a turn away (they
        must evolve first) and contingent (they must actually hold the evolution). Un-discounted it
        resurrects a CRITICAL (dragapult 85046350 f32 — a Gabite's Garchomp prices the strip at 100)."""
        cid = (p or {}).get("id")
        if cid is None or self.stats is None:
            return 0.0
        energy = len((p or {}).get("energies") or [])
        now = denial_value(energy, self._attacks_of(cid))
        forward = 0
        for fwd in self._forward_card_ids(cid):
            forward = max(forward, denial_value(energy, self._attacks_of(fwd)))
        return float(max(now, _DENIAL_FORWARD * forward))

    def _opp_denial_best(self, opp: dict | None, active_doomed: bool = False) -> float:
        """The most damage a single Energy discard could take away from ANY of their Pokémon —
        Active OR Bench, because that is what the card says and what the engine offers (Crushing
        Hammer: "discard an Energy from 1 of your opponent's Pokémon"; `op_trash_energy_enemy` builds
        its options from ACTIVE + BENCH). A benched body must still be promoted before the denial
        bites, so it is discounted, not ignored — a bench-loading opponent used to make us stand down
        entirely, leaving 4 Hammers dead in hand all game.

        `active_doomed` (I can already KO their Active this turn) drops the ACTIVE from the max — it
        does NOT blank the board. Stripping Energy off a body that is about to die denies nothing; a
        benched body banking Energy is untouched by that fact. Hammer the bench, then take the KO
        (ms 82748422 f26: the old stand-down zeroed the whole board and left a benched Mega Starmie ex
        sitting on 3 Energy unmolested).

        0 means every energized body is either holding SURPLUS Energy, cannot pay an attack, or is
        already dead: there is nothing to deny and the Hammer should be HELD."""
        if not opp:
            return 0.0
        best = 0.0
        tiers = [(_DENIAL_BENCH, opp.get("bench") or [])]
        if not active_doomed:
            tiers.insert(0, (1.0, opp.get("active") or []))
        for weight, bodies in tiers:
            for p in bodies:
                if p:
                    best = max(best, weight * self._denial_at(p))
        return best

    def _opp_turns_to_ready(self, p: dict | None) -> int | None:
        """The Round-3 ruled basic lookahead of ONE opponent in-play body, from VISIBLE facts only
        (thread 2, the deny-slot deadline): `needs.turns_to_ready` over

          * the ENERGY DEFICIT — the line's biggest-attack cost (max ``maxDamageCost`` over the
            body's current + forward forms, "fully energized" measured against the threat it
            becomes) minus its attached Energy, at the 1-manual-attach/turn quota (rules.md §3).
            Their card-effect accel is NOT modelled: that can only OVER-state t and UNDER-price
            the deny slot — the fail-closed direction (the hedge keeps the card at v1's price).
          * the FORWARD EVOLUTION HOPS still owed — the ``evolvesFrom`` name-chain depth from this
            body to its line's deepest still-owed form (one evolve per turn, rules.md §4), walked
            over the forward index (`_forward_card_ids`), depth-guarded. A broken/unknown chain
            contributes 0 hops (the deficit leg still grades).

        None — the caller emits NO deny slot (fail-closed, erring toward the shipped hedge) —
        when the body/its stats are unknown or no form's biggest-attack cost is known.

        DELEGATES to `combat.turns_to_afford` (Threat-Clock unification S1c,
        docs/plans/opponent-value-equation-unification.md): the deny-clock's energy/evolve model now
        lives on the KO oracle beside `incoming` — the Threat Clock's two legs, one home — passing the
        Pilot's forward index so the read stays byte-identical. The slow deny policy is the default
        1-attach/turn (their card-effect accel is NOT modelled — the fail-closed direction)."""
        return self.combat.turns_to_afford(p, forward_ids=self._forward_card_ids)

    def _unfavored(self, board: Board) -> bool:
        """The Read says the straight race loses (Lever A, ADR-0026) — a compiled favorability at or
        below `_POSTURE_UNFAVORED`, backed by enough coverage to trust the prior."""
        return (board.matchup_coverage >= _POSTURE_MIN_COVERAGE
                and board.favorability <= _POSTURE_UNFAVORED)

    def _denial_play_tactical(self, board: Board, ctx) -> float:
        """Value of PLAYING an energy-denial Item (ADR-0062): what the strip actually takes away,
        priced by its odds, net of keeping the card.

            coin_odds(card) * _DENIAL_PLAY_W * (unfavored?) * opp_denial_best  -  _DENIAL_ITEM_COST

        Silent unless the card is `energy_denial`. A whiff (`opp_denial_best == 0` — surplus Energy,
        no affordable attack, or the only energized body is one I am about to KO) prices at 0 and is
        held; `_finish_turn_last` tiers a free Item ahead of everything, so declining one REQUIRES a
        non-positive score. Half of all Crushing Hammers do nothing whatever the board looks like, so
        the coin is priced here rather than absorbed into a tuned constant.

        The unfavored Read (Lever A) SCALES this value and is never added beside it — see
        `_DENIAL_UNFAVORED`. A multiplier cannot resurrect a hold; the flat rung it replaces did
        exactly that, and played a Hammer into a KO turn against a bare bench (ms 83968638 f17)."""
        if ctx.option_type != _PLAY or "energy_denial" not in ctx.tags:
            return 0.0
        if not board.opp_denial_best:
            return 0.0                                  # nothing to deny — hold it (whiff)
        weight = _DENIAL_PLAY_W * (1.0 + _DENIAL_UNFAVORED if self._unfavored(board) else 1.0)
        return coin_odds(ctx.card_id) * weight * board.opp_denial_best - _DENIAL_ITEM_COST

    def _denial_target_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """Rank the Crushing Hammer's TARGET once its coin comes up heads (ADR-0062).

        The engine poses a DISCARD_ENERGY select over every Energy on the opponent's board, ordered
        OLDEST-ATTACHED FIRST. Nothing scored it: every option came back 0.0, so the argmax fell
        through to index 0 and we stripped whatever Energy happened to land first — routinely a Basic
        on a benched support mon while their Active sat one Energy above its nuke. That is the literal
        waste. Score each option by what removing it actually denies.

        The DOOMED Active scores 0 here for the same reason it is dropped from `_opp_denial_best`:
        Energy on a body I am about to knock out is not worth taking. A won flip should land on the
        bench instead of shaving a corpse."""
        if (select or {}).get("context") != _DISCARD_ENERGY or option.get("type") != _ENERGY:
            return 0.0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        area = option.get("area")
        if area == _ACTIVE:
            if board.active_can_ko:
                return 0.0                     # it dies this turn — stripping it denies nothing
            target, weight = next((p for p in (opp.get("active") or []) if p), None), 1.0
        elif area == _BENCH:
            bench = opp.get("bench") or []
            idx = option.get("index", -1)
            target = bench[idx] if 0 <= idx < len(bench) else None
            weight = _DENIAL_BENCH
        else:
            return 0.0
        return _DENIAL_TARGET_W * weight * self._denial_at(target)

    def _lock_sequence_cost(self, attack_id, board: Board) -> float:
        """Horizon-2 lock cost (ADR-0061): the damage this attack's lock actually FORFEITS next turn,
        not a flat constant. Replaces `_LOCK_COST = 40`, which charged one number for two structurally
        different locks:

        - **same-attack lock** (Mega Brave 270 / Aura Jab 130): 270+130 == 130+270. You can never Mega
          Brave twice in a row WHICHEVER you open with, so the lock forfeits nothing the other ordering
          would have had — cost **0**. The flat 40 was a phantom charge biasing every pick toward Aura Jab.
        - **full lock** (Blood Moon 240, "can't use attacks"): 240 + 0 loses to a lock-free 130/turn's
          260 — cost **~240**, not 40.

        Cost = `_FOLLOWUP_W * (best follow-up a lock-free pick would leave − the follow-up THIS pick
        leaves)`, so a lock-free attack is always 0 and the term never inflates an attack's score (it is
        a cost, never a credit — attacks keep their scale against develops).

        Zero when the Active is `active_doomed`: there is no next turn for it, so every lock is free and
        we front-load. Zero when it is the only affordable attack — chipping must still beat passing
        (the invariant `_lock_cost_applies` held, preserved here)."""
        st = self._attack_stat(attack_id)
        if not st or board.active_doomed:
            return 0.0
        active = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        affordable = {aid: self._attack_damage(aid)
                      for aid in (getattr(active, "attacks", None) or ())
                      if self._attack_cost(aid) <= board.my_active_energy}
        if len(affordable) <= 1:
            return 0.0                                   # lone attack: never charged
        mine = followup_damage(attack_id, affordable=affordable,
                               full_lock=bool(getattr(st, "nextTurnSelfLock", False)),
                               same_attack_lock=bool(getattr(st, "nextTurnSameAttackLock", False)))
        return _FOLLOWUP_W * max(0.0, max(affordable.values()) - mine)

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
                    if st is not None and st.is_typed_basic_energy:
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
            if st is not None and st.is_energy:           # any Energy card
                total += 1
            if st is not None and st.is_typed_basic_energy:   # Basic Energy, by type
                by_type[st.energyType] = by_type.get(st.energyType, 0) + 1
        return total, by_type

    def predicted_damage(self, attacker_id: int | None, attack_id, defender: dict | None, *,
                         bound: str = "exact", context: dict | None = None) -> float:
        """The damage oracle (ADR-0032 E1) — delegates to the KO oracle (`CombatMath`, ADR-0052),
        the one closed-form combat home."""
        return self.combat.predicted_damage(attacker_id, attack_id, defender,
                                            bound=bound, context=context)

    def _predicted_max_damage(self, attacker_stat, defender: dict | None, *,
                              exclude_attack=None) -> float:
        """The worst damage `attacker_stat`'s attacks deal to `defender` (Incoming's magnitude) —
        the KO oracle's `predicted_max_damage`, handed the per-decision opponent context this
        Pilot stashes (`_opp_attack_context`, set by `_board`)."""
        return self.combat.predicted_max_damage(
            attacker_stat, defender, exclude_attack=exclude_attack,
            context=getattr(self, "_opp_attack_context", None))

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

    def _context(self, obs: dict, select: dict, board: Board, option: dict) -> Context:
        state = obs.get("current") or {}
        plan = board.phase                # the DERIVED advisory phase (ADR-0040) — one compute point
                                          # (`_board`), shared by every option; rules no longer gate
                                          # on it (the gate-ban migration), traces still record it
        cid = self._option_card_id(obs, select, option)
        roles = self._roles_of(cid)
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        card_is_line_preevo = cid is not None and cid in self._line_preevo_set()
        card_is_recognized_line_preevo = cid is not None and cid in self._recognized_line_preevo_set()
        card_is_wincon = cid is not None and cid in self._wincon_set()
        card_is_starter = bool(stat and stat.hp > 0 and not stat.evolvesFrom)
        card_is_support = bool(stat and stat.hp > 0 and (_ENGINE_TAGS & set(tags)))
        card_is_utility_body = bool(stat and stat.hp > 0 and self._is_utility_body(cid))
        card_is_top_fetch_priority = cid is not None and cid == board.top_fetch_priority_id
        card_is_redundant = cid is not None and cid in board.in_play_ids
        card_is_hand_duplicate = cid is not None and cid in board.hand_duplicate_ids
        # a Basic/Special Energy is fungible — a second copy is always a future attach, never redundant
        fungible = bool(stat and stat.is_energy)
        card_already_in_hand = bool(select.get("context") == _TO_HAND and cid is not None
                                    and not fungible and cid in board.hand_ids)
        card_unplayable_this_turn = bool(
            select.get("context") == _TO_HAND and board.supporter_played
            and bool(stat and stat.is_supporter))
        card_chain_value = (self._chain_grab_value(board, cid, plan)
                            if select.get("context") == _TO_HAND and cid is not None else 0.0)
        card_spends_last_evolution_route = (
            card_chain_value > 0 and self._spends_last_evolution_route(select, board, cid))
        fetch_fills_a_need = (option.get("type") == _PLAY
                              and self._fetch_fills_a_need(board, cid, plan))
        fetch_target_deferred = (fetch_fills_a_need
                                 and self._fetch_target_deferred(obs, cid, board, plan))
        refresh_shuffles_deferred = (option.get("type") == _PLAY and "shuffle_hand" in tags
                                     and self._held_fetch_deferred(obs, cid, board, plan))
        target_energy = self._target_energy(obs, select, option)
        target_hp = self._target_hp(obs, select, option)
        target_is_weakest = (target_hp is not None and board.weakest_bench_hp is not None
                             and target_hp == board.weakest_bench_hp)
        target_forward_damage = self._target_forward_damage(obs, select, option)
        target_is_strongest_forward = (
            target_forward_damage is not None and board.strongest_forward_bench is not None
            and target_forward_damage == board.strongest_forward_bench
            and target_forward_damage >= _EVOLVING_THREAT_DMG)
        target_is_bench_tera = bool(select.get("context") == _DAMAGE and option.get("area") == _BENCH
                                    and stat is not None and getattr(stat, "tera", False))
        target_kos = bool(board.snipe_damage and target_hp and board.snipe_damage >= target_hp
                          and not target_is_bench_tera)   # Tera: no damage while Benched
        target_on_path = self._target_on_path(obs, select, option, board)   # Tier-3 (ADR-0040)
        bench_shortens = self._bench_shortens_their_path(obs, select, option, stat, board)
        promote_on_their_path = (select.get("context") in (_TO_ACTIVE, _SWITCH)
                                 and self._promote_target_on_their_path(obs, select, option, board))
        target_rank = self._target_threat_rank(
            obs, select, option, board.read, board.posture_confidence)
        target_is_top_threat = (target_rank is not None and target_rank > 0
                                and board.strongest_threat_rank > 0
                                and target_rank == board.strongest_threat_rank)
        promote_target_kos = (select.get("context") == _TO_ACTIVE
                              and self._promote_target_kos(obs, select, option))
        is_best_promote_target = (
            select.get("context") in (_TO_ACTIVE, _SWITCH) and board.best_promote_slot is not None
            and option.get("playerIndex", state.get("yourIndex", 0)) == state.get("yourIndex", 0)
            and (option.get("area"), option.get("index")) == board.best_promote_slot)
        is_ko_promote_target = (
            select.get("context") in (_TO_ACTIVE, _SWITCH) and board.ko_promote_slot is not None
            and option.get("playerIndex", state.get("yourIndex", 0)) == state.get("yourIndex", 0)
            and (option.get("area"), option.get("index")) == board.ko_promote_slot)
        card_prize_value = self._prize_value({"id": cid}) if cid is not None else 1
        promote_target_can_attack = self._promote_target_can_attack(obs, select, option)
        promote_target_hits_weakness = self._promote_target_hits_weakness(obs, select, option)
        at_target = self._attach_target(obs, option)   # Pokémon an attach option puts Energy on
        at_roles = self._roles_of(at_target.get("id")) if at_target else []
        # the body an attach FUNDS, at either seam: the manual ATTACH (inPlayArea/inPlayIndex) or the
        # accel ATTACH_FROM recipient pick (area/index — cf `_option_pokemon`).
        fund_target = at_target
        if fund_target is None and select.get("context") == _ATTACH_FROM:
            fund_target = self._option_pokemon(obs, select, option)
        attach_target_is_utility_body = bool(
            fund_target and self._is_utility_body(fund_target.get("id")))
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
        attach_completes_biggest_attack = (
            option.get("type") == _ATTACH and option.get("inPlayArea") == _ACTIVE
            and self._attach_completes_biggest_attack(at_target, tags))
        search_exhausted, redundant_wincon, baseless_wincon = self._search_signals(option, cid, board)
        search_unlikely = self._search_probable_whiff(option, cid, board)
        search_confirmed = self._search_confirmed_hit(option, cid, board, plan)
        sheds_junk, sheds_live, sheds_key = self._shed_signals(obs, option, tags, board, plan)
        refresh_miss = self._refresh_probable_miss(option, cid, tags, board, obs, plan)
        attach_from_needs = self._attach_from_target_needs(obs, select, option)
        attach_from_concentrate = (select.get("context") == _ATTACH_FROM
                                   and board.attach_from_concentrate_slot is not None
                                   and (option.get("area"), option.get("index"))
                                   == board.attach_from_concentrate_slot)   # ATTACH_FROM encodes
                                   # recipient in area/index (not inPlayArea/inPlayIndex — cf _option_pokemon)
        # ADR-0044 opponent-choice snipe reads (kill-switched; DAMAGE bench-target only)
        snipe_ctx = (select.get("context") == _DAMAGE and option.get("type") == _CARD
                     and option.get("area") == _BENCH)
        snipe_poke = self._option_pokemon(obs, select, option) if snipe_ctx else None
        target_is_forced_promotion = bool(
            snipe_ctx and getattr(self, "forced_promotion", False) and board.opp_active_doomed
            and board.forced_promotion_key is not None
            and snipe_poke is not None and id(snipe_poke) == board.forced_promotion_key)
        target_prize_redundant = bool(                 # off my committed path — chip here doesn't advance it
            snipe_ctx and getattr(self, "snipe_prize_redundant", False)
            and board.my_path_turns is not None and not target_on_path
            and not target_is_forced_promotion
            # PRIZE-POSITION gate (ms f39 vs 83667237-107, symmetric board shapes — the ONLY difference is
            # remaining prizes): an ENERGIZED (imminent) bench attacker is worth DENYING while I still have
            # MANY prizes to protect — it will take a chunk of them before I close, so I can't just race an
            # off-path body away (f39: snipe the energized ex @ 6 prizes). Only in the RACING back-half
            # (`my_prizes_remaining < _SNIPE_THREAT_PRIZE_FLOOR`) do I stick to my committed path and let it
            # be (107: stand down @ 4 prizes). A NON-energized off-path body stays redundant regardless.
            and not (target_energy and board.my_prizes_remaining >= _SNIPE_THREAT_PRIZE_FLOOR)
            # a high-prize body I never need is avoided ALWAYS; a low-prize off-path body only when I'm
            # not under pressure (else deny the threat) — the "not an imminent threat to me" guard
            and (card_prize_value >= 2 or not board.active_doomed))
        target_promotion_mirage = bool(                # their Active dead, but NOT who they promote
            snipe_ctx and getattr(self, "forced_promotion", False) and board.opp_active_doomed
            and board.forced_promotion_key is not None and not target_is_forced_promotion)
        return Context(plan=plan, select_context=select.get("context"),
                       option_type=option.get("type"), card_id=cid, option_area=option.get("area"),
                       attach_target_area=option.get("inPlayArea"), attach_target_roles=at_roles,
                       attach_target_needs=self._attach_target_needs(at_target),
                       attach_is_energy=self._attach_is_energy(stat),
                       attach_target_is_utility_body=attach_target_is_utility_body,
                       attach_target_under_max=self._attach_target_under_max(at_target),
                       attach_completes_biggest_attack=attach_completes_biggest_attack,
                       attach_target_is_priority_wincon=attach_target_is_priority_wincon,
                       attach_type_wasted=self._attach_type_wasted(stat, at_target),
                       attach_fuels_dormant_ability=self._attach_fuels_dormant_ability(stat, at_target),
                       attach_is_tool_deploy_target=attach_is_tool_deploy_target,
                       attach_feeds_firing_accel=attach_feeds_firing_accel,
                       attach_target_is_line_member=at_is_line_member,
                       attach_target_is_draw_engine=self._is_draw_engine_body((at_target or {}).get("id")),
                       attach_from_target_needs=attach_from_needs,
                       attach_from_target_is_concentrate=attach_from_concentrate,
                       card_is_line_preevo=card_is_line_preevo, card_is_wincon=card_is_wincon,
                       card_is_recognized_line_preevo=card_is_recognized_line_preevo,
                       card_forward_payoff_prize=self._forward_payoff_prize_value(cid),
                       card_evolution_baseless=self._evolution_baseless(obs, cid),
                       card_base_unreachable=self._card_base_unreachable(obs, cid, board),
                       card_is_starter=card_is_starter, card_is_support=card_is_support,
                       card_is_utility_body=card_is_utility_body,
                       card_is_top_fetch_priority=card_is_top_fetch_priority,
                       card_is_redundant=card_is_redundant,
                       card_is_hand_duplicate=card_is_hand_duplicate,
                       card_already_in_hand=card_already_in_hand,
                       card_unplayable_this_turn=card_unplayable_this_turn,
                       card_chain_value=card_chain_value,
                       card_spends_last_evolution_route=card_spends_last_evolution_route,
                       fetch_fills_a_need=fetch_fills_a_need,
                       fetch_target_deferred=fetch_target_deferred,
                       refresh_shuffles_deferred_fetch=refresh_shuffles_deferred,
                       target_energy=target_energy, target_is_threat=bool(target_energy),
                       target_hp=target_hp, target_is_weakest=target_is_weakest,
                       target_is_strongest_forward=target_is_strongest_forward,
                       target_forward_form_in_play=self._target_forward_form_in_play(obs, select, option),
                       target_forward_damage=target_forward_damage,
                       target_kos=target_kos, target_is_top_threat=target_is_top_threat,
                       target_is_bench_tera=target_is_bench_tera,
                       target_on_path=target_on_path, target_prize_redundant=target_prize_redundant,
                       target_is_forced_promotion=target_is_forced_promotion,
                       target_promotion_mirage=target_promotion_mirage,
                       bench_shortens_their_path=bench_shortens,
                       promote_target_on_their_path=promote_on_their_path,
                       counter_is_best_placement=(
                           board.best_counter_slot is not None
                           and (option.get("area"), option.get("index"),
                                option.get("playerIndex")) == board.best_counter_slot),
                       counter_is_source_pick=(
                           board.best_counter_source_slot is not None
                           and (option.get("area"), option.get("index"),
                                option.get("playerIndex")) == board.best_counter_source_slot),
                       is_max_counter_move=(
                           option.get("type") == _NUMBER and board.max_counter_move_number > 0
                           and int(option.get("number", 0)) == board.max_counter_move_number),
                       evolve_body_energy=self._evolve_body_energy(obs, option),
                       promote_target_kos=promote_target_kos,
                       is_best_promote_target=is_best_promote_target,
                       is_ko_promote_target=is_ko_promote_target,
                       card_prize_value=card_prize_value,
                       promote_target_can_attack=promote_target_can_attack,
                       promote_target_hits_weakness=promote_target_hits_weakness,
                       card_stranded_evolution=(cid is not None
                                                and cid in self._stranded_evolution_set()),
                       roles=roles, tags=tags, stat=stat, board=board, params=self.strategy.params,
                       context_card_id=((select.get("contextCard") or {}).get("id")),
                       search_targets_exhausted=search_exhausted,
                       search_redundant_wincon=redundant_wincon,
                       search_baseless_wincon=baseless_wincon,
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

    def _is_utility_body(self, card_id: int | None) -> bool:
        """This body exists to DRAW / TUTOR / STALL, not to attack — Energy on it is wasted while any
        real attacker can take it (ml f121/f84, dragapult f21). Read universally, never by card id:

        - the deck's own Roles win: any `_ATTACKER_ROLES` member, or a win-condition Line body, is
          never a utility body (Solrock is `secondary_attacker` + `engine`; Riolu is the Line base);
        - an `engine`-ONLY Role says it outright (Lunatone: Lunar Cycle draws, Power Gem never fires);
        - otherwise a `_UTILITY_TAGS` Function Tag on the body OR on its forward evolution
          (Meowth ex's `supporter_tutor`; Dunsparce, untagged, evolving into a `draw` Dudunsparce).

        Fail-CLOSED: an unknown card is not a utility body, so a missing tag never suppresses an attach.
        Note `attach_target_needs` is an ANTI-signal on these bodies — a Meowth ex needing 3 Energy for
        Tuck Tail reads "needier" than a Riolu that is already online."""
        if card_id is None:
            return False
        roles = set(self.strategy.roles.get(card_id, []))
        if roles & _ATTACKER_ROLES:
            return False
        if card_id in (self._line_preevo_set() | self._wincon_set()):
            return False
        if "engine" in roles:
            return True
        if not self.functions:
            return False
        tags = set(self.functions.tags(card_id))
        for fwd in self._forward_card_ids(card_id):
            tags |= set(self.functions.tags(fwd))
        return bool(_UTILITY_TAGS & tags)

    def _attach_is_energy(self, stat) -> bool:
        """This ATTACH option's CARD is an Energy, not a Pokémon Tool. The engine reports both through
        `OptionType.ATTACH`, so without this every Energy hypothesis (`power-up-attacker`,
        `attach-energy-last`, `dont-waste-off-type-energy`) also priced Air Balloon — a retreat-cost
        Tool that provides no Energy at all (ml f87/f4). Fail-OPEN (True when the stat is unknown), so
        an unresolvable attach keeps the default attach-every-turn behavior."""
        if stat is None:
            return True
        return not (stat is not None and stat.is_tool)

    def _attach_fuels_dormant_ability(self, energy_stat, target: dict | None) -> bool:
        """True iff this ATTACH's typed Basic Energy is a colour the TARGET's Ability needs as fuel
        (`CardStat.abilityEnergyTypes`) and the target carries NONE of it — the attach switches a
        dormant Ability on (the {D} for a bare Munkidori's Adrena-Brain). The attach-target-level
        mirror of `_in_play_unfueled_ability_colors` (which backs the fetch side); backs
        `fuel-the-dormant-ability` and exempts the fuel from `_attach_type_wasted`, whose attack-cost
        read called Adrena-Brain's {D} 'wasted' (86091728 f19, measured −12). Sound-or-silent:
        False for an untyped/colourless Energy, a targetless option, or missing stats."""
        etype = getattr(energy_stat, "energyType", None) if energy_stat else None
        if etype in (None, 0) or getattr(energy_stat, "hp", 1) != 0:   # a typed Basic Energy only
            return False
        if not target:
            return False
        tst = self.stats.get(target.get("id")) if self.stats else None
        fuels = [t for t in (getattr(tst, "abilityEnergyTypes", ()) or ()) if t not in (0, None)]
        if etype not in fuels:
            return False
        return self._attached_type_counts(target).get(etype, 0) == 0

    def _attach_type_wasted(self, energy_stat, target: dict | None) -> bool:
        """True iff this ATTACH puts an Energy of a TYPE the target already has ENOUGH of for its
        most type-demanding attack, while that attack still LACKS a DIFFERENT specific type — a wasted
        attach when the needed type is on offer (ep83686860 f45: a 2nd Psychic onto a Drakloak that
        holds its Psychic but needs the Fire for Phantom Dive [Fire, Psychic]). Sound-or-silent: False
        for an untyped/colourless Energy, a targetless option, or a target whose attack type-costs can't
        be resolved. Colourless (type-0) cost slots never make an attach wasted — only an unmet SPECIFIC
        type on another slot does. A colour that switches the target's DORMANT Ability on is FUEL, not
        waste (`_attach_fuels_dormant_ability`): the attack-cost read alone called Adrena-Brain's {D}
        wasted while it is the whole point of the body (86091728 f19)."""
        etype = getattr(energy_stat, "energyType", None) if energy_stat else None
        if etype in (None, 0) or getattr(energy_stat, "hp", 1) != 0:   # a typed Basic Energy only
            return False
        if not target:
            return False
        if self._attach_fuels_dormant_ability(energy_stat, target):
            return False                       # the "off-type" colour switches an Ability on — fuel
        tst = self.stats.get(target.get("id")) if self.stats else None
        aids = getattr(tst, "attacks", ()) if tst else ()
        if not aids:
            return False
        best_types, best_specific = (), -1                 # the attack demanding the most typed Energy
        for aid in aids:
            ast = self._attack_stat(aid)
            types = getattr(ast, "energyTypes", ()) if ast else ()
            n_specific = sum(1 for t in types if t not in (0, None))
            if n_specific > best_specific:
                best_types, best_specific = types, n_specific
        if best_specific <= 0:
            return False
        from collections import Counter
        cost = Counter(t for t in best_types if t not in (0, None))
        attached = self._attached_type_counts(target)
        if cost.get(etype, 0) - attached.get(etype, 0) > 0:   # this type fills its own unmet need
            return False
        return any(cost.get(t, 0) - attached.get(t, 0) > 0 for t in cost if t != etype)

    def _in_play_attack_colors(self, me: dict) -> frozenset:
        """The specific Energy-type colors my IN-PLAY attackers' attacks require — every non-colourless
        `AttackStat.energyTypes` slot across my Active + Bench bodies' attacks. The set a fetched Basic
        Energy can actually be USED for now, so an off-color Energy no in-play body needs (dragapult's
        {D} while Munkidori is still in the deck) is absent. Backs `fetch-the-attack-color`. Empty
        without stats/attack_stats (silent — never a false steer)."""
        if not self.stats:
            return frozenset()
        out = set()
        for p in ((me.get("active") or []) + (me.get("bench") or [])):
            st = self.stats.get(p.get("id")) if p else None
            for aid in (getattr(st, "attacks", ()) or ()):
                ast = self._attack_stat(aid)
                for t in (getattr(ast, "energyTypes", ()) or ()):
                    if t not in (0, None):
                        out.add(t)
        return frozenset(out)

    def _in_play_ability_fuel_colors(self, me: dict) -> frozenset:
        """Ability-FUEL colors of my in-play bodies — the union of each Active/Bench body's
        `CardStat.abilityEnergyTypes` (Munkidori's Adrena-Brain needs {D}). A colour a body needs
        SOLELY to switch its Ability on, invisible to the attack-cost signal. Unioned with
        `_in_play_attack_colors` into `in_play_required_colors`. Empty without stats."""
        if not self.stats:
            return frozenset()
        out = set()
        for p in ((me.get("active") or []) + (me.get("bench") or [])):
            st = self.stats.get(p.get("id")) if p else None
            out.update(t for t in (getattr(st, "abilityEnergyTypes", ()) or ()) if t not in (0, None))
        return frozenset(out)

    def _in_play_unfueled_ability_colors(self, me: dict) -> frozenset:
        """Ability-fuel colors of in-play bodies that currently LACK that colour attached — the
        Energy a fetch would use to switch a DORMANT Ability on (grab {D} for a bare Munkidori, not a
        2nd {D} for one already fuelled). Backs `fetch-the-ability-fuel-color`. Empty without stats."""
        if not self.stats:
            return frozenset()
        out = set()
        for p in ((me.get("active") or []) + (me.get("bench") or [])):
            st = self.stats.get(p.get("id")) if p else None
            fuels = [t for t in (getattr(st, "abilityEnergyTypes", ()) or ()) if t not in (0, None)]
            if not fuels:
                continue
            attached = self._attached_type_counts(p)
            out.update(t for t in fuels if attached.get(t, 0) == 0)
        return frozenset(out)

    def _setup_placed_ids(self, obs: dict) -> frozenset:
        """Card ids I placed on my Active/Bench during the PREGAME setup, recovered from the MOVE_CARD
        logs. The just-placed Active shows only in the logs (obs still reads `active=[None]`), so the
        obs-zone `in_play_ids` misses it — the redundancy test at `_SETUP_BENCH` (bench a 2nd copy of
        something already placed) needs this to see the placement. Scoped to turn 0 so mid-game
        promote/retreat MOVE_CARD logs never leak in; empty off setup."""
        state = obs.get("current") or {}
        if state.get("turn"):                              # 0/None only — pregame setup window
            return frozenset()
        yi = state.get("yourIndex", 0)
        out = set()
        for lg in (obs.get("logs") or []):
            if (lg.get("type") == _MOVE_CARD and lg.get("playerIndex") == yi
                    and lg.get("toArea") in (_ACTIVE, _BENCH) and lg.get("cardId") is not None):
                out.add(lg["cardId"])
        return frozenset(out)

    def _is_draw_engine_body(self, cid) -> bool:
        """True iff card `cid` is a DRAW-ENGINE body — it carries a `draw`/`stall` Function Tag, OR it
        evolves INTO one (Dunsparce → Dudunsparce: the base is untagged but its payoff IS the engine).
        Marks a body whose role is card advantage, not attacking, so the turn's Energy shouldn't be sunk
        into it (dragapult f21). The consuming rung ALSO excludes a win-condition-Line member, so a wincon
        pre-evolution whose Stage-1 happens to draw (Drakloak's Recon) is never mislabelled. Fail-open
        (False) with no functions / id."""
        if not (self.functions and cid is not None):
            return False
        draw = {"draw", "stall"}
        if draw & set(self.functions.tags(cid)):
            return True
        return any(draw & set(self.functions.tags(f)) for f in self._forward_card_ids(cid))

    def _evolution_baseless(self, obs: dict, cid: int | None) -> bool:
        """True iff grab candidate `cid` is an EVOLUTION (has an `evolvesFrom` base) but I hold NO copy
        of that base in play or hand to evolve it onto — a speculative/dead grab (a 3rd Drakloak when
        every Dreepy is already evolved or gone, ep83686860 f33: take the playable Munkidori instead).
        Board-derivable and SOUND (no deck-content claim): checks only the visible own zones (an evolved
        base shows as its evolution's top card, so a name match means a still-bare base). False for a
        Basic (no base needed) or when a base body is present."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        base_name = getattr(st, "evolvesFrom", None) if st else None
        if not base_name:
            return False
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        bodies = (me.get("active") or []) + (me.get("bench") or []) + (me.get("hand") or [])
        for b in bodies:
            bst = self.stats.get(b.get("id")) if (b and self.stats) else None
            if bst and getattr(bst, "name", None) == base_name:
                return False
        return True

    def _card_base_unreachable(self, obs: dict, cid: int | None, board) -> bool:
        """True iff grab candidate `cid` is an EVOLUTION whose pre-evolution base is provably UNGETTABLE
        this game — baseless in play/hand (`_evolution_baseless`) AND unreachable in the deck: absent
        from the current search's revealed pool (`search_deck_ids`, an EXACT within-frame test) or, off
        a search reveal, provably empty from the sound deck oracle. So the fetched evolution is a dead
        card — a Mega ex only enters play by evolving its Basic (ml f53: grabbed Mega Lucario ex with
        every Riolu gone). False for a Basic, when a base is in play/hand, or when the base is still
        reachable. FAIL-CLOSED (False) when the base name can't be resolved to ids."""
        if not self._evolution_baseless(obs, cid):
            return False                                  # base in play/hand (or a Basic) -> reachable
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        base_name = getattr(st, "evolvesFrom", None) if st else None
        ids_for_name = getattr(self.stats, "ids_for_name", None)
        base_ids = set(ids_for_name(base_name)) if (ids_for_name and base_name) else set()
        if not base_ids:
            return False                                  # unresolvable base -> fail open (don't suppress)
        sd = board.search_deck_ids
        if sd is not None:
            return not bool(base_ids & sd)                # base absent from the search pool -> unreachable
        return all(board.deck_definitely_empty_of(bid) for bid in base_ids)   # sound oracle fallback

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

    def _attach_completes_biggest_attack(self, target: dict | None, tags: list) -> bool:
        """True if attaching this Energy onto the ACTIVE crosses it from short-of to able-to-afford its
        HIGHEST-damage attack THIS turn — the attach COMPLETES the big attack. Guards the stand-down of
        `dont-overbuild-the-doomed-wincon`: a doomed Active this very attach turns the payoff attack ON
        should fire it (go down swinging, ms 85163079 f51: 2 W + 1 = Nebula CCC), unlike one merely
        overbuilt for a turn that won't come (ep83037962 f48: 1 W → 2 W, still short of CCC=3, dies first).
        `provided` mirrors the planner's `_attach_provided` (3 for a `discard_eot` burst onto an Evolution,
        else 1). Fail-CLOSED (False when target / CardStat / maxDamageCost unknown), like `_attach_target_under_max`."""
        if not target:
            return False
        stat = self.stats.get(target.get("id")) if self.stats else None
        cost = getattr(stat, "maxDamageCost", None) if stat else None
        if cost is None:
            return False
        have = len((target.get("energies") or []))
        provided = 3 if ("discard_eot" in (tags or []) and getattr(stat, "evolvesFrom", None)) else 1
        return have < cost and (have + provided) >= cost

    def _active_attack_payable_via_accel(self, me: dict, ma: dict | None,
                                         supporter_played: bool, basic_energy_in_deck: bool) -> bool:
        """My Active could be made attack-payable THIS turn by a PLAYABLE hand energy-accelerator (a
        `tutor_energy` card, e.g. Crispin: fetch a Basic Energy from the deck and attach it). The famine
        stall-gust family reads only `active_attack_payable` (attached + best hand-attach) and misses the
        deck-fetch accel, so it declares a FALSE famine (dragapult f70: Active Dragapult ex 0e, Crispin in
        hand → Jet Headbutt {C} payable). Kept SEPARATE from `active_attack_payable` (attached-now truth
        other consumers need). Fail-CLOSED (False on unknown stats / nothing to fetch / accel one short),
        so a PROVABLE famine still fires the stall."""
        if ma is None or not (self.stats and self.functions):
            return False
        stat = self.stats.get(ma.get("id"))
        if stat is None or (stat.minAttackCost or 0) <= 0 or not basic_energy_in_deck:
            return False
        if (len(ma.get("energies") or []) + 1) < (stat.minAttackCost or 0):
            return False                                   # even one accel-attach is short of the cheapest attack
        for c in (me.get("hand") or []):
            cid = c.get("id") if c else None
            if cid is None or "tutor_energy" not in self.functions.tags(cid):
                continue
            cstat = self.stats.get(cid)
            if getattr(cstat, "cardType", None) == 3 and supporter_played:  # 3 = Supporter: only one/turn
                continue
            return True
        return False

    def _active_arm_available(self, ma: dict | None, bench_wincon_ready: bool) -> bool:
        """Go-down-swinging is available on the Active: it is a real ATTACKER (NOT a utility draw/tutor/stall
        body) whose HIGHEST-damage attack ONE more Energy would COMPLETE this turn, and there is no ready
        benched win-condition to retreat into instead. Distinguishes ml f21 (doomed Solrock — Cosmic Beam
        {F} completed by one {F} → arm + swing for 70) from f42 Makuhita (biggest attack costs 2, one {F}
        short) / f54 Lunatone (utility engine) and from the retreat-into-a-ready-wincon case (accel f70).
        Fail-CLOSED. Backs `arm-the-doomed-active`, `dont-feed-the-doomed`'s go-down-swinging stand-down,
        and the Lunar-Cycle famine's yield-to-arming."""
        if ma is None or not self.stats or bench_wincon_ready or self._is_utility_body(ma.get("id")):
            return False
        return self._attach_completes_biggest_attack(ma, [])

    def _immediate_preevo_in_play(self, me: dict) -> bool:
        """The payoff's IMMEDIATE pre-evolution (e.g. Drakloak for the Dragapult line) is ALREADY on my
        board (active/bench). A hand copy of it is then redundant — the shuffle-refresh hold on a line
        piece should stand down and let the refuel dig for the buried payoff (dragapult f38)."""
        preevos = self._payoff_immediate_preevo_set()
        if not preevos:
            return False
        return any(p and p.get("id") in preevos
                   for p in ((me.get("active") or []) + (me.get("bench") or [])))

    def _deploy_now_ids(self, me: dict, turn: int) -> frozenset:
        """Hand card ids that are evolutions able to be played onto an ELIGIBLE in-play base THIS turn
        — a body matching the card's ``evolvesFrom`` name in play since last turn (``appearThisTurn``
        False; rules.md §4: no evolving a body the turn it arrives, and no evolution at all on turn 1).
        Pitching or shuffling such a card forfeits a live tempo play its re-access cannot restore (the
        base is here and eligible NOW) — the DEPLOY-NOW closing edge (ep86091435 f68: a hand Drakloak
        over the active Dreepy). A just-benched base does NOT qualify (ep83686860 f18: two Dreepy
        placed this turn — no eligible base, so the hand Drakloak stays sheddable). Pure; empty on
        turn ≤ 1 or without stats."""
        if not self.stats or turn <= 1:
            return frozenset()
        eligible = {getattr(self.stats.get(b.get("id")), "name", None)
                    for b in ((me.get("active") or []) + (me.get("bench") or []))
                    if b and not b.get("appearThisTurn")}
        eligible.discard(None)
        out = set()
        for c in (me.get("hand") or []):
            cid = c.get("id") if c else None
            st = self.stats.get(cid) if cid is not None else None
            if st is not None and getattr(st, "evolvesFrom", None) in eligible:
                out.add(cid)
        return frozenset(out)

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

    def _attach_from_concentrate_slot(self, me: dict, select: dict | None = None) -> tuple | None:
        """(AreaType, index) of the win-condition-Line body to CONCENTRATE accelerated Energy on at an
        ATTACH_FROM (Turbo Flare recipient) select — among my in-play Line members (`_line_member_set`:
        Staryu AND Mega Starmie ex) still short of the payoff's biggest-attack cost, the one ALREADY
        carrying the most Energy, so the deck loads ONE body toward the Mega payoff (Nebula Beam, 3
        Energy) instead of dribbling one Energy onto each bare Staryu (`spread-attach-to-the-needy`
        reads a 1-Energy Staryu as 'done' because it clears Staryu's OWN 1-cost attack — the wrong
        frame for a Line whose real payoff is the evolved Mega). A body at/over the payoff cost is
        skipped (don't over-stack a ready attacker). None when no buildable Line body exists (ep83116081
        f21). Deterministic: most-Energy wins, index breaks a tie.

        RESTRICTED to the bodies THIS select actually offers. Aura Jab loads the BENCH only, so the
        whole-board scan picked my Active Mega (1 Energy from the attack it just used) over the benched
        one it could really load; no option matched the slot, the rule went silent, and all five bench
        bodies tied at `spread-attach-to-the-needy` +15 → the option index loaded Lunatone (ml f121,
        CRITICAL). Falls back to the whole board when the select is absent (unit tests / no options)."""
        offered = None
        if select is not None:
            offered = {(o.get("area"), o.get("index")) for o in (select.get("option") or [])}
            if not offered:
                offered = None
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
                if offered is not None and (area, i) not in offered:
                    continue                              # this effect can't load that body (Aura Jab: Bench only)
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

        Accounts for a HAND-SIZE-scaling attacker in the line (Alakazam Powerful Hand: 2 counters =
        20 per card in the opponent's hand): its printed damage (10) hides the real threat, so it is
        CALCULATED as `handSizeDamage x the opponent's current hand size` and max'd with the printed
        forward (f85: opp holding 10 cards → Kadabra→Alakazam threatens 200, the strongest forward).

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
        if cid is None:
            return None
        printed = fwd(cid) or 0
        dmg = max(printed, self._forward_hand_size_damage(obs, cid))
        return dmg or None

    def _forward_hand_size_damage(self, obs: dict, cid: int | None) -> int:
        """Damage a HAND-SIZE-scaling attacker in `cid`'s forward evolution line does against me —
        `handSizeDamage` (per-card, e.g. Alakazam Powerful Hand = 20) x the OPPONENT player's current
        hand size (the attacker's own hand, `for each card in YOUR hand`). The user-directed f85 fix:
        Alakazam's threat is dynamic, so its printed forward damage undercounts it — calculate it. 0
        when no hand-size attacker in the line / no provider."""
        if not self.stats or cid is None:
            return 0
        line = {cid} | self._forward_card_ids(cid)
        per_card = max((getattr(self.stats.get(i), "handSizeDamage", 0) or 0 for i in line), default=0)
        if per_card <= 0:
            return 0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        hand = opp.get("handCount")
        if hand is None:
            hand = len(opp.get("hand") or [])
        return per_card * (hand or 0)

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
        read = self.opponent.observe(obs)            # ADR-0047 fan-out: Identity (Scout) + Resources
        if self.scout is None:                       # preserve Posture-off semantics (facade returns Read())
            read = None                              # the Read (M2.0); γ/favorability derive from it
        gamma = _posture_gamma(read) if self.posture else 0.0    # γ threads into snipe rank; kill-switch zeroes it
        my_arch = self.strategy.params.get("my_archetype")
        fav, cov = (matchup_favorability(self.scout.artifact, my_arch, read.candidates)
                    if (self.posture and self.scout and read and my_arch) else (0.5, 0.0))
        # covers-routed (ADR-0027), γ-gated to a RECOGNIZED opponent: on an empty early board the Read's
        # top candidate is just the prior favourite -> gate on γ>0 to keep board.brief off until recognized.
        brief = match_brief(self.briefs, read) if (self.posture and read and gamma > 0) else None
        self.opponent.note_brief(brief)              # feed the γ-gated Brief to Dispositions (ADR-0047)
        # ADR-0064 Decision 1: the reachable-Incoming energy policy. Charged (per-attack typed-cost
        # affordability) ONLY behind a γ-matched Brief — the calibrated "we know what they run" signal;
        # an unrecognized opponent stays None → worst-case ceiling (never relax pessimism on a guess).
        # burst_on_evo credits an Ignition-class colourless burst ({C}{C}{C} on an Evolution): it only
        # ever makes a COLOURLESS-costed attack more reachable (the pessimism-safe direction — it can
        # never fund a typed {F}{F}), so a flat matched-archetype allowance keeps a burst nuke doomed
        # while the typed/colourless split sharpens genuine typed-cost reach (the variant-2 read).
        self._incoming_budget = {"base_attach": 1, "burst_on_evo": 2} if brief is not None else None
        _opp_res = getattr(self.opponent, "resources", None)   # match-scoped Resources tracker (flattened below)
        # Resolve the matched Brief's name-keyed threats/targets to card ids (ADR-0027 consumer). Guarded
        # like forward_max_damage: an old/None provider -> empty, never crashes. Behavior-neutral surface.
        _ids_for_name = getattr(self.stats, "ids_for_name", None)
        brief_threat_ids, brief_target_roles = (
            resolve_brief_cards(brief, _ids_for_name)
            if (brief is not None and _ids_for_name is not None) else (frozenset(), {}))
        matchup_plan = self._matchup_plan(opp, brief_target_roles, read, gamma)   # ADR-0051 spine
        active_doomed = self._active_doomed(ma, oa, opp)
        active_lethal = self._active_cheap_attack_kos(ma, oa)   # its turn is done — build the successor
        # the Energy my Active can actually PAY an attack with this turn: attached + the best unspent
        # hand attach (Ignition = 3 on an Evolution) — the gust/offense affordability gate (f31)
        hand_ids_now = frozenset(c.get("id") for c in (me.get("hand") or [])
                                 if c and c.get("id") is not None)
        payable = (len((ma or {}).get("energies") or [])
                   + (0 if state.get("energyAttached")
                      else self._best_hand_attach_units(
                          hand_ids_now, self.stats.get((ma or {}).get("id")) if self.stats else None)))
        base_plan = (choose_plan(state, self.strategy, self.stats) if state.get("players")
                     else Plan.SETUP)                   # the readiness core (SETUP→RACE)
        path_sig = self._path_signals(obs, me, opp, ma, oa,   # Tier-3 two-sided Prize Path (ADR-0040):
                                      len(me.get("prize") or []),   # re-derived every decision,
                                      len(opp.get("prize") or []),  # ranking data only; their-side
                                      read, gamma)                  # sees the γ-gated Read overlay (T4)
        phase = self._derive_phase(base_plan, path_sig["race_ahead"], active_doomed,
                                   len(me.get("prize") or []),   # derived ADVISORY phase (hysteretic)
                                   favorability=fav, coverage=cov)   # + Tier-4 favorability (Lever A)
        opp_doomed = oa is None or (oa or {}).get("hp", 1) <= 0    # ADR-0044: forced promote next turn
        board = Board(
            opp_active_doomed=opp_doomed,
            forced_promotion_key=self._forced_promotion_key(opp, opp_doomed),
            my_bench=sum(1 for b in (me.get("bench") or []) if b),
            bench_full=sum(1 for b in (me.get("bench") or []) if b) >= _BENCH_MAX,
            my_active_id=(ma or {}).get("id"),
            my_active_energy=len((ma or {}).get("energies") or []),
            my_active_hp=(ma or {}).get("hp", 0),
            opp_bench=tuple((b.get("id"), b.get("hp", 0)) for b in (opp.get("bench") or []) if b),
            turn=state.get("turn", 0),
            energy_attached=bool(state.get("energyAttached")),
            supporter_played=bool(state.get("supporterPlayed")),
            hand_startable=self._hand_startable(me.get("hand") or []),
            active_doomed=active_doomed,
            incoming_active_damage=self._incoming_active_damage(ma, oa),
            active_cheap_attack_kos=active_lethal,
            active_can_ko=self._active_can_ko(ma, oa),
            active_maxed_kos=self._active_maxed_kos(ma, oa),
            gust_best_ko_prizes=self._gust_best_ko_prizes(ma, opp, payable),
            active_ko_prizes=self._active_ko_prizes(ma, oa, payable),
            gust_best_total_prizes=self._gust_best_total_prizes(ma, opp, payable),
            menu_attack_total_prizes=self._menu_attack_total_prizes(ma, oa, opp, payable),
            gust_ko_energy_swing=self._gust_ko_energy_swing_calc(ma, oa, opp, payable),
            stall_swap_pointless=self._stall_swap_pointless(opp),
            my_prizes_remaining=len(me.get("prize") or []),
            opp_prizes_remaining=len(opp.get("prize") or []),
            reusable_energy_in_hand=self._has_reusable_energy(me.get("hand") or []),
            recycle_dead_only=self._recycle_dead_only(me),
            active_attack_payable=(self._active_attack_payable(ma, payable)
                                   and not self._attack_impossible_on_menu(
                                       select, me, bool(state.get("energyAttached")))),
            active_attack_payable_via_accel=self._active_attack_payable_via_accel(
                me, ma, bool(state.get("supporterPlayed")), self._basic_energy_in_deck(deck_empty)),
            immediate_preevo_in_play=self._immediate_preevo_in_play(me),
            deploy_now_ids=self._deploy_now_ids(me, state.get("turn", 0)),
            active_arm_available=self._active_arm_available(ma, self._bench_wincon_ready(me)),
            active_fully_powered=self._active_fully_powered(ma),
            energy_placeable=self._energy_placeable(me),
            wincon_in_play=self._wincon_in_play(me),
            wincon_prize_value=self._wincon_prize_value(),
            wincon_in_hand=self._wincon_in_hand(me),
            line_preevo_in_play=self._line_preevo_in_play(me),
            line_preevo_in_hand=self._line_preevo_in_hand(me),
            bench_line_member_needs=self._bench_line_member_needs(me),
            wincon_base_deployable=self._payoff_immediate_preevo_available(me),
            wincon_in_hand_undeployable=self._wincon_in_hand_undeployable(me),
            accel_recipient_missing=self._accel_recipient_missing(me),
            support_in_play=self._support_in_play(me),
            in_play_ids=frozenset(p.get("id") for p in ((me.get("active") or []) + (me.get("bench") or []))
                                  if p and p.get("id") is not None),
            in_play_attack_colors=self._in_play_attack_colors(me),
            in_play_required_colors=(self._in_play_attack_colors(me) | self._in_play_ability_fuel_colors(me)),
            in_play_unfueled_ability_colors=self._in_play_unfueled_ability_colors(me),
            setup_placed_ids=self._setup_placed_ids(obs),
            hand_duplicate_ids=self._hand_duplicate_ids(me),
            top_fetch_priority_id=self._top_fetch_priority_id(select),
            weakest_bench_hp=self._weakest_snipe_hp(obs, select),
            strongest_forward_bench=self._strongest_forward_snipe(obs, select),
            evolving_wincon_on_bench=self._evolving_wincon_on_bench(obs, select),
            snipe_damage=self._snipe_damage(obs, (ma or {}).get("id"), select),
            snipe_ko_available=self._snipe_ko_available(
                opp, self._snipe_damage(obs, (ma or {}).get("id"), select)),
            strongest_threat_rank=self._strongest_threat_rank(obs, select, read, gamma),
            best_counter_slot=self._best_counter_slot(obs, select) if select else None,
            best_counter_source_slot=self._best_counter_source_slot(obs, select) if select else None,
            max_counter_move_number=self._max_counter_move_number(select) if select else 0,
            stadium_in_play=((state.get("stadium") or [{}])[0] or {}).get("id"),
            opp_stadium_in_play=bool((state.get("stadium") or [{}])[0]
                                     and (state.get("stadium") or [{}])[0].get("playerIndex", yi) != yi),
            bench_wincon_ready=self._bench_wincon_ready(me),
            best_promote_slot=self._best_promote_slot(me),
            evolve_to_ready_wincon_available=self._evolve_to_ready_wincon_available(me),
            bench_wincon_prize_value=self._bench_wincon_prize_value(me),
            bench_wincon_underpowered=self._bench_wincon_underpowered(me),
            opp_cannot_punish_wincon=self._opp_cannot_punish_wincon(me, opp),
            basic_energy_in_deck=self._basic_energy_in_deck(deck_empty),
            my_discard_basic_energy=self._discard_energy_counts(me.get("discard") or [])[1],
            opp_discard_energy=self._discard_energy_counts(opp.get("discard") or [])[1],
            active_best_attack_locked=self._active_best_attack_locked(ma),
            opp_has_stage2=self._board_has_stage2(opp),
            opp_has_colorless_ability=self._board_has_colorless_ability(opp),
            hand_ids=frozenset(c.get("id") for c in (me.get("hand") or [])
                               if c and c.get("id") is not None),
            search_deck_ids=(frozenset(c.get("id") for c in (select.get("deck") or [])
                                       if c and c.get("id") is not None)
                             if select and select.get("deck") else None),
            hand_basic_energy=self._hand_basic_energy(me.get("hand") or []),
            no_supporter_in_hand=self._no_supporter_in_hand(me),
            opp_has_played_gust=self._opp_has_played_gust(opp),
            active_is_wincon=bool(ma) and ma.get("id") in self._wincon_set(),
            active_is_weak_preevo=self._active_is_weak_preevo(ma),
            can_wall_line_with_disruptor=self._can_wall_line_with_disruptor(me, ma, oa),
            can_lock_line_with_disruptor=self._can_lock_line_with_disruptor(
                me, ma, oa, state.get("turn", 0)),
            priority_wincon_slot=self._priority_wincon_slot(
                me, active_lethal, active_doomed),
            attach_from_concentrate_slot=self._attach_from_concentrate_slot(me, select),
            stall_target_exists=self._stall_target_exists(opp),
            stall_target_is_keystone=self._stall_target_is_keystone(opp),
            opp_denial_best=self._opp_denial_best(opp, self._active_can_ko(ma, oa)),
            opp_has_energy_in_play=self._opp_has_energy_in_play(opp),
            opp_active_has_energy=bool(oa and (oa.get("energies") or [])),
            opp_active_can_damage_us=self._opp_active_can_damage_us(ma, oa),
            opp_has_hand_size_attacker=self._opp_has_hand_size_attacker(opp),
            opp_hand_size=int((opp or {}).get("handCount") or 0),
            my_hand_size=len(me.get("hand") or []),
            opp_draw_engine_in_play=bool(self._draw_engine_ids(opp)),
            # Opponent RESOURCES (ADR-0047) flattened for `when()` triggers — sourced from the tracker
            # observed at self.opponent.observe(obs) above; each read fails OPEN (unknown -> no-fire default).
            opp_took_ko_this_turn=bool(getattr(_opp_res, "took_ko_this_turn", False)),
            my_pokemon_koed_last_turn=bool(getattr(_opp_res, "my_pokemon_koed_last_turn", False)),
            opp_hand_size_delta=getattr(_opp_res, "hand_size_delta", None),
            opp_last_turn_dumped=bool(getattr(_opp_res, "last_turn_dumped", False)),
            opp_deckout_in_turns=getattr(_opp_res, "deckout_in_turns", None),
            opp_comeback_disruptor=bool(brief is not None
                                        and self.opponent.disposition("opp_comeback_disruptor", False)),
            opp_hand_strip_odds=self._opp_hand_strip_odds(),
            deck_empty_ids=deck_empty,
            deck_known_counts=deck_known,
            deck_contains_odds=deck_odds_map,
            opp_active_condition_gift=self._opp_active_condition_gift(opp),
            active_condition_ko_prizes=self._active_condition_ko_prizes(opp, oa),
            read=read,                                              # Posture Read (ADR-0026); None = off
            opponent=self.opponent,                                 # Opponent Model facade (ADR-0047)
            posture_confidence=gamma,                               # γ ∈ [0,1] the levers scale by
            favorability=fav, matchup_coverage=cov,                 # lever-A signal + its reliability
            brief=brief,                                            # matched Matchup Brief (ADR-0027); None = off
            brief_threat_ids=brief_threat_ids,                      # its threats/targets resolved to card ids
            brief_target_roles=brief_target_roles,                  # (behavior-neutral consumer surface)
            matchup_plan=matchup_plan,                              # ADR-0051 unified target-priority spine
            **path_sig,                                             # Tier-3 two-sided Prize Path
            line_ready=(base_plan == Plan.RACE),                    # the readiness signal old plan
                                                                    # gates migrated to (ADR-0040)
            phase=phase,                                            # derived ADVISORY phase — bands +
                                                                    # trace only, never a gate
        )
        if self.promote_ko_aware and select is not None and select.get("context") in (_TO_ACTIVE, _SWITCH):
            board.ko_promote_slot = self._ko_aware_promote_slot(obs, board, me, oa)   # KO-aware,
            #                                             boost-inclusive promote target (KO-gated; None
            #                                             when no benched body reaches a KO -> inert)
        if self._tool_in_hand(me):                      # Tool doctrine signals (ADR-0028) — only when a
            board = replace(board,                      # Tool is in hand (common case pays nothing)
                            tool_deploy_slot=self._tool_deploy_slot(obs, me, board),
                            irreplaceable_tool_in_hand=self._irreplaceable_tool_in_hand(me))
        board.game_plan = self.plan_match(obs, board)   # the Match Planner (ADR-0045) runs first each turn;
        board.turn_goal_satisfied = self._turn_goal_satisfied(board, select)  # BUILD 4 predicate
        return board                                    # COMPUTE-ONLY here — nothing scores off it yet (S2)

    def _opp_hand_strip_odds(self) -> float:
        """`Board.opp_hand_strip_odds` — the held-card-risk exposure leg (hypergeometric-fetch-closure
        §Round 8 §5): P(the opponent's deck still holds ≥1 card that shuffles MY hand away), read as
        the max `copies_left_odds` over the matched Read's representative build restricted to
        `hand_disruption`-tagged cards (Judge / Harlequin / Unfair Stamp — verified tags,
        card_functions.json). `copies_left_odds` already nets out their tracker-observed plays (a
        Judge in their discard is a Judge they no longer hold). Fails OPEN to 0.0 — no facade, no
        functions table, no confident Read, or any error claims NO exposure, so the deferral veto
        reading this never fires on a guess (the declared suppressor fail direction)."""
        if self.opponent is None or not self.functions:
            return 0.0
        try:
            odds = self.opponent.copies_left_odds()
            return max((p for cid, p in odds.items()
                        if "hand_disruption" in self.functions.tags(cid)), default=0.0)
        except Exception:
            return 0.0

    def _turn_goal_satisfied(self, board: Board, select: dict | None) -> bool:
        """BUILD 4 predicate — is THIS turn's directed goal already met, so a draw/gust/evolution Supporter
        could be HELD for a later decisive turn (`dont-spend-unneeded-supporter`)?

        DELIBERATELY FAILS SAFE TO FALSE. A sound "the directed goal is *met*" oracle is not derivable from
        the current Board signals: the Game Plan exposes the directed goal-KIND (survive / ko_on_path /
        trade) and its confidence, but NOT a per-mode completion state, and a plausible proxy ("I can attack,
        so I'm done") over-claims — drawing could still find the piece that turns a chip into a lethal, so
        holding on that proxy would lose tempo. Rather than assert an unsound True, the predicate returns
        False until a sound completion oracle exists. The field is WIRED and telemetry-visible; its only
        consumer ships at weight 0 (inert), and its intended-True board is exercised directly in tests.
        `select` is threaded so a future sound derivation can require "not mid-search/tutor" (nothing still
        being resolved) without another signature change."""
        return False

    # Shuffle-Refresh doctrine's signals live in doctrine_shuffle_refresh (ShuffleRefreshMixin); `_board` calls them.

    def _wincon_lines(self) -> list:
        """The declared Lines whose payoff IS the win-condition (Line role 'win_condition') — never a
        secondary-attacker Line (ADR-0048). The win-condition machinery (`_wincon_set`, `_line_preevo_set`,
        `_line_member_set`, the immediate-pre-evo / concentrate helpers) is scoped to these, so declaring a
        cheap secondary-attacker Line (role 'secondary_attacker') never mislabels its payoff a win-condition
        or its base a wincon pre-evo. A no-op for every existing deck — all declare only 'win_condition'."""
        return [l for l in self.strategy.lines if getattr(l, "role", "win_condition") == "win_condition"]

    def _wincon_set(self) -> set:
        """Card ids that ARE the win-condition — a WIN-CONDITION Line payoff (role-gated, `_wincon_lines`)
        or a card carrying the `win_condition` / `primary_attacker` Role. Match-invariant (pure over the
        fixed `Strategy`), so memoised like `_stranded_evolution_set` — `_context` reads it per option."""
        cached = getattr(self, "_wincon_set_cache", None)
        if cached is not None:
            return cached
        wincon = {line.payoff for line in self._wincon_lines()}
        wincon |= {cid for cid, r in self.strategy.roles.items()
                   if {"win_condition", "primary_attacker"} & set(r)}
        self._wincon_set_cache = wincon
        return wincon

    def _wincon_prize_value(self) -> int:
        """The greatest prize value among my declared win-condition bodies (Mega ex 3 / ex 2 / else 1) —
        the multi-prize payoff a cheap secondary line makes the opponent take MORE, smaller KOs than
        (ADR-0048). 0 if none. Backs `Board.wincon_prize_value`."""
        wincon = self._wincon_set()
        return max((self._prize_value({"id": c}) for c in wincon), default=0) if wincon else 0

    def _wincon_in_hand(self, me: dict) -> bool:
        """True if the win-condition card is already in my hand — a tutor needn't dig for another."""
        wincon = self._wincon_set()
        return bool(wincon) and any(c and c.get("id") in wincon for c in (me.get("hand") or []))

    def _wincon_in_hand_undeployable(self, me: dict) -> bool:
        """True iff an EVOLUTION win-condition is in my hand but has NO base to deploy it: not already
        in play, its Line HAS a pre-evolution (so it isn't a directly-benchable Basic wincon), and no
        pre-evolution sits in play OR hand. Such a card is dead this turn — `hold-wincon-dont-shuffle`
        must let it be shuffled away to dig for a base (ep83966336 f44: Mega Lucario ex held with no
        Riolu anywhere)."""
        if not (self._wincon_in_hand(me) and not self._wincon_in_play(me)):
            return False
        if not self._line_preevo_set():                    # Basic-payoff wincon — benchable, keep it
            return False
        return not (self._line_preevo_in_play(me) or self._line_preevo_in_hand(me))

    def _line_preevo_set(self) -> set:
        """Card ids that are a non-payoff member of a WIN-CONDITION Line's path (role-gated,
        `_wincon_lines`) — a pre-evolution that builds toward the win-condition payoff (Staryu on the
        Staryu → Mega Starmie line). NARROW by design: feeds `wincon_base_deployable` /
        `_evolve_to_ready_wincon_available` / the hold/undeployable machinery, so a secondary-attacker
        Line's base is NOT in it (ADR-0048 — the broadened, line-piece-crediting set is
        `_recognized_line_preevo_set`). Match-invariant, memoised (read per option in `_context`)."""
        cached = getattr(self, "_line_preevo_cache", None)
        if cached is not None:
            return cached
        self._line_preevo_cache = {cid for line in self._wincon_lines()
                                   for cid in line.path if cid != line.payoff}
        return self._line_preevo_cache

    def _recognized_line_preevo_set(self) -> set:
        """Pre-evolutions of EVERY declared attacker Line — win-condition AND secondary-attacker
        (ADR-0048). Read ONLY by the preference rungs (`prefer-wincon-line-piece` at a fetch,
        `develop-the-cheap-prize-wall-line`), so a secondary attacker's base (Makuhita) earns the same
        line-piece credit as the wincon base (Riolu) without touching the narrow `_line_preevo_set` the
        deploy/hold machinery rides. Falls back to the narrow win-condition set when the ADR-0048
        kill-switch is OFF — so a declared secondary Line is fully inert then. Match-invariant
        (the kill-switch is fixed too), memoised — read per option in `_context`."""
        cached = getattr(self, "_recognized_preevo_cache", None)
        if cached is not None:
            return cached
        if not self.prize_economy_fetch:
            result = self._line_preevo_set()
        else:
            result = {cid for line in self.strategy.lines for cid in line.path if cid != line.payoff}
        self._recognized_preevo_cache = result
        return result

    def _forward_payoff_prize_value(self, cid) -> int:
        """The greatest prize value the card `cid` BECOMES — max `_prize_value` over `cid` and its forward
        evolution descendants (`_forward_card_ids`): Riolu → Mega Lucario ex = 3, Makuhita → Hariyama = 1.
        The prize a body's LINE ultimately presents, which the card's own prize value (Riolu and Makuhita
        are both 1-prize Basics) cannot distinguish (ADR-0048). 0 with no stats / id."""
        if cid is None or not self.stats:
            return 0
        ids = {cid} | self._forward_card_ids(cid)
        return max((self._prize_value({"id": i}) for i in ids), default=0)

    def _active_is_weak_preevo(self, ma: dict | None) -> bool:
        """True iff my Active is a WIN-CONDITION line pre-evolution (`_line_preevo_set`) whose OWN printed
        output is a minor chip far below the body it evolves into — attaching an Energy to it buys little
        tempo (Riolu's 30 vs Mega Lucario ex 130/270). Read by mega_lucario's Lunar-Cycle stand-down: with
        the engine online, discard the last {F} to draw 3 rather than sink it into a weak pre-evo whose 30
        chip doesn't change the game's tempo (ml 85058574 f16). 'Weak' = own maxDamage is under half the
        forward form's max, so a real-attacker pre-evo (Makuhita→Hariyama 210) still keeps the {F}. FAIL-CLOSED
        on missing stats / non-preevo active."""
        cid = (ma or {}).get("id")
        if cid is None or cid not in self._line_preevo_set():
            return False
        stat = self.stats.get(cid) if self.stats else None
        own = getattr(stat, "maxDamage", None) if stat else None
        fwd_fn = getattr(self.stats, "forward_max_damage", None) if self.stats else None
        fwd = fwd_fn(cid) if fwd_fn else None
        if not own or not fwd:
            return False
        return own * 2 <= fwd

    def _line_preevo_in_play(self, me: dict) -> bool:
        """True if a non-payoff member of any Line's path (a pre-evolution) is on my Active/Bench —
        so a rush-evolve tutor has something to evolve toward the payoff."""
        preevos = self._line_preevo_set()
        if not preevos:
            return False
        board = (me.get("active") or []) + (me.get("bench") or [])
        return any(p and p.get("id") in preevos for p in board)

    def _line_readiness_deadline(self, me: dict, cid) -> int:
        """READINESS (piece 1): how soon a held wincon ``cid`` comes online, as the re-access deadline
        the refresh-SHED window clamps to (`_refresh_slot_resupply`). Keyed on the payoff's BASE being
        in play — the human's own line ("no riolu in play, thus it's worthless at this moment",
        ml ep83966336 f44):

          * a base in play AND already powered ⇒ **1** (evolve next turn, attack soon — hold it);
          * a base in play but unpowered ⇒ **2** (a turn further, still an imminent line — hold it);
          * NO base in play ⇒ **99** (latent — the payoff cannot be assembled soon, it is freely
            re-fetchable once a base lands, so it stays cheap to shuffle away — restores f44).

        Two live Staryu keep both Mega Starmie expensive to shed (deadline 2, ep82752604 f16); a lone
        Mega Lucario with no Riolu down stays sheddable (99). Fail-open: unknown forward-line facts ⇒
        no base found ⇒ 99 (the re-fetchable side, never over-protects)."""
        if cid is None:
            return 99
        board = [p for p in ((me.get("active") or []) + (me.get("bench") or [])) if p]
        bases = [p for p in board if cid in self._forward_card_ids(p.get("id"))]
        if not bases:
            return 99
        return 1 if any(p.get("energies") for p in bases) else 2

    def _bench_line_member_needs(self, me: dict) -> bool:
        """True if a BENCHED body on a declared win-condition Line's path (pre-evolution or payoff,
        `_line_member_set`) still needs Energy for its cheapest attack (`_attach_target_needs`) — an
        un-powered line is waiting on the bench. The board-side gate of `prefer-active-attach-in-
        setup`'s stand-down (86091728 f19: two bare benched Dreepy while the {P} went to Munkidori);
        role-gated via `_wincon_lines`, so decks without a declared Line never trip it."""
        members = self._line_member_set()
        if not members:
            return False
        return any(p and p.get("id") in members and self._attach_target_needs(p)
                   for p in (me.get("bench") or []))

    def _line_preevo_in_hand(self, me: dict) -> bool:
        """True if a Line pre-evolution (a base to evolve the payoff from) is in my hand — so I can
        bench it and deploy the payoff. The hand-side companion of `_line_preevo_in_play`."""
        preevos = self._line_preevo_set()
        if not preevos:
            return False
        return any(c and c.get("id") in preevos for c in (me.get("hand") or []))

    def _payoff_immediate_preevo_set(self) -> set:
        """Card ids that are a Line payoff's IMMEDIATE pre-evolution — the path member one hop below
        the payoff (`path[index(payoff) - 1]`). For a SINGLE-HOP Line (Staryu -> Mega Starmie ex) this
        is the Basic base and equals `_line_preevo_set`; for a MULTI-STAGE Line (Dreepy -> Drakloak ->
        Dragapult ex) it is ONLY the Stage-1 (Drakloak), not the Stage-0 base (Dreepy). Lets the
        win-condition readiness signals tell 'the payoff is ONE evolution from deployable/ready' apart
        from 'some Line pre-evo is around somewhere' — the distinction the distance-blind signals
        missed on the corpus's first 2-stage line (dragapult f14/f31; ml f31). Pure + total."""
        out = set()
        for line in self._wincon_lines():
            path = line.path or []
            if line.payoff in path:
                i = path.index(line.payoff)
                if i > 0:
                    out.add(path[i - 1])
        return out

    def _payoff_immediate_preevo_available(self, me: dict) -> bool:
        """True if a payoff's IMMEDIATE pre-evolution is in play OR hand — the payoff is exactly one
        evolution from being deployable. Identical to `_line_preevo_in_play or _line_preevo_in_hand`
        for single-hop Lines (the immediate pre-evo IS the only pre-evo); on a multi-stage Line it is
        False while only a deeper base is around (a lone Dreepy no longer reads the two-hop Dragapult
        ex as base-deployable). Backs `wincon_base_deployable`."""
        imm = self._payoff_immediate_preevo_set()
        if not imm:
            return False
        zones = (me.get("active") or []) + (me.get("bench") or []) + (me.get("hand") or [])
        return any(p and p.get("id") in imm for p in zones)

    def _line_member_set(self) -> set:
        """Every card id on a WIN-CONDITION Line's path (role-gated, `_wincon_lines`) — pre-evolutions AND
        the payoff. The Pokémon a bench accelerator (e.g. Cinderace's Turbo Flare) can usefully load Energy
        onto; scoped to the win-condition line so a secondary-attacker Line never silently redirects the
        accelerator's recipient hunt (ADR-0048)."""
        return {cid for line in self._wincon_lines() for cid in line.path}

    def _roles_of(self, cid) -> list:
        """The Context's per-card Roles: the deck-DECLARED list (`strategy.roles`) plus the DERIVED
        `accel_source` for a body whose attack carries a bench-target accel rider
        (`_derived_accel_body_ids` — Turbo Flare / Aura Jab class). Derivation-first, declaration as
        the confirm/override (Round 9): a new deck fielding Cinderace gets the whole accel rung
        family (open-the-accelerator, develop-the-accel-recipient, feed-the-accelerator, promote)
        with NO Role declaration; for the existing agents the union is a no-op (both declare it)."""
        if cid is None:
            return []
        roles = self.strategy.roles.get(cid, [])
        if cid in self._derived_accel_body_ids() and "accel_source" not in roles:
            roles = [*roles, "accel_source"]
        return roles

    def _derived_accel_body_ids(self) -> frozenset:
        """Deck Pokémon whose ATTACK carries a bench-target energy-accel rider (`recoverTarget ==
        "bench"`, either zone: Turbo Flare deck-search, Aura Jab discard-recover) — the DERIVED
        bench-accelerator set (hypergeometric-fetch-closure §Round 9: derive from the card
        representation; the deck's `accel_source` Role declaration stays the override/confirm, never
        a parallel system). Self-target chargers (Regi Charge) are NOT bench accelerators. Memoised
        (deck-fixed). Empty without stats/deck."""
        if self._derived_accel_cache is None:
            ids = set()
            for cid in set(self.deck):
                st = self.stats.get(cid) if self.stats else None
                for aid in (getattr(st, "attacks", None) or ()):
                    ast = self._attack_stat(aid)
                    if (ast is not None and getattr(ast, "recoverN", 0)
                            and getattr(ast, "recoverTarget", None) == "bench"):
                        ids.add(cid)
                        break
            self._derived_accel_cache = frozenset(ids)
        return self._derived_accel_cache

    def _accel_recipient_missing(self, me: dict) -> bool:
        """True if my Active is a bench-accelerator (declared `accel_source` Role ∪ the DERIVED
        bench-accel-attack set, e.g. Cinderace's Turbo Flare) but NO Line member sits on my Bench to
        receive the accelerated Energy — so the accel attack would fire blanks. The trigger for
        developing a recipient first. False with no accel body Active or any Line member benched."""
        accel = ({cid for cid, r in self.strategy.roles.items() if "accel_source" in r}
                 | self._derived_accel_body_ids())
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
        Staryu but a Water in hand -> evolve, the Mega comes online).

        The benched body must be the payoff's IMMEDIATE pre-evolution (one hop) — a Stage-0 Dreepy
        cannot become a Dragapult ex this turn no matter how much Energy it carries, yet the old
        any-pre-evo test said it could, so `promote-the-staller` stood down and the agent promoted a
        fragile bare Dreepy into the Active Spot (dragapult f31, CRITICAL)."""
        if not self._wincon_in_hand(me):
            return False
        preevos = self._payoff_immediate_preevo_set()   # IMMEDIATE pre-evo only — a deeper Stage-0 base is
        wincon = self._wincon_set()                      # >1 evolution from a ready attacker (dragapult f31)
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
        `concentrate-energy-on-wincon` (load one attacker, don't spread; ep83116501 f89).

        EVOLUTION-DISTANCE AWARE (2026-07-10). The evolved payoff is preferred, but the slot also
        considers a Line PRE-EVOLUTION that has ALREADY BEEN STARTED (carries Energy) and is still short
        of the PAYOFF's cost — Energy carries through evolution (rules.md), so finishing a started pre-evo
        IS building the wincon. Without this, a board of pre-evos found nothing and
        `concentrate-energy-on-wincon` stood down, letting `power-up-attacker` spread: a 2nd {P} onto a
        bare Dreepy instead of finishing the started one (dragapult f85), and a whole hand of {F} onto a
        Meowth ex while the 1-Energy Riolu — already 'online' for its own 1-cost attack, so invisible to
        `attach_target_needs` — stayed one Energy short of Mega Brave (ml f84).

        A BARE pre-evo is deliberately NOT a slot: with nothing started there is nothing to concentrate,
        and claiming one would hijack the attach from a genuinely better target (ml f24, where the
        winning line attaches to Solrock and retreats into it)."""
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
        if best is not None:
            return (best[1], best[2])
        # Pass 2 (multi-stage lines): no win-condition BODY is buildable, so concentrate on the LINE
        # PRE-EVO closest to firing the payoff — the one carrying the MOST Energy while still short of
        # its payoff's biggest attack cost (Energy carries through evolution). Lets
        # `concentrate-energy-on-wincon` finish a started pre-evo instead of `power-up-attacker`
        # dribbling one Energy onto a bare body (dragapult f85). Inert where a win-condition body is in
        # play (Pass 1 wins) — so single-hop decks are unaffected in the common case. A BARE pre-evo
        # (e == 0) is deliberately excluded, so with nothing started the slot stands down and the attach
        # stays free for a genuinely better target (ml f24).
        zones = ((_ACTIVE, active if not (active_lethal or active_doomed) else []),
                 (_BENCH, me.get("bench") or []))
        best_pre = None                                    # (energy, area, index)
        for line in self._wincon_lines():
            payoff_stat = self.stats.get(line.payoff) if self.stats else None
            thresh = getattr(payoff_stat, "maxDamageCost", None) if payoff_stat else None
            if not thresh:
                continue
            preevos = {cid for cid in line.path if cid != line.payoff}
            for area, zone in zones:
                for i, p in enumerate(zone):
                    if p and p.get("id") in preevos:
                        e = len(p.get("energies") or [])
                        if 0 < e < thresh and (best_pre is None or e > best_pre[0]):
                            best_pre = (e, area, i)
        return (best_pre[1], best_pre[2]) if best_pre else None

    def _bench_wincon_ready(self, me: dict) -> bool:
        """True if a benched win-condition / primary attacker already carries enough Energy to attack
        (>= its cheapest attack cost) — a powered finisher worth retreating into."""
        wincon = self._wincon_set()
        if not wincon:
            return False
        return any(p and p.get("id") in wincon
                   and len(p.get("energies") or []) >= _min_attack_cost(self.stats, p.get("id"))
                   for p in (me.get("bench") or []))

    def _opp_cannot_punish_wincon(self, me: dict, opp: dict | None) -> bool:
        """ADR-0064 Decision 4: True when the opponent's reachable Incoming cannot KO my best benched
        win-condition next turn — the return-KO reachability veto behind the interpose / dont-promote
        stand-down (scenario 3: they literally can't afford to punish the exposed wincon, so
        `promote-the-ready-wincon` should win). **Matched-Read only** (Decision 4's safety direction):
        the veto fires solely behind a γ-matched Brief (`_incoming_budget` populated) — we expose a
        3-prize wincon only when we KNOW the archetype and its charged typed-affordability read says no
        lethal is reachable. Unmatched → False (fail CLOSED: keep interpose — under-counting their reach
        would feed them the wincon). Deliberately PESSIMISTIC even when matched (pool-forward evolution
        existence, `evo_min_energy` default 0), so a wincon is never exposed on a phantom-safety read."""
        if getattr(self, "_incoming_budget", None) is None:
            return False                                  # no matched Read → never expose on a guess
        slot = self._best_promote_slot(me)
        if slot is None or opp is None:
            return False
        idx = slot[1]
        bench = me.get("bench") or []
        wincon = bench[idx] if 0 <= idx < len(bench) else None
        if not (wincon and wincon.get("hp")):
            return False
        opp_bodies = (opp.get("active") or []) + (opp.get("bench") or [])
        incoming = self.combat.reachable_incoming(
            {"id": wincon.get("id"), "hp": wincon.get("hp")}, opp_bodies,
            charged=getattr(self, "_incoming_budget", None),
            context=getattr(self, "_opp_attack_context", None))
        return incoming < wincon.get("hp")

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

    def _ko_aware_promote_slot(self, obs: dict, board: Board, me: dict,
                               opp: dict | None) -> tuple | None:
        """(_BENCH, index) of the benched body to promote whose best affordable attack — given the
        Energy attachable THIS turn (the manual attach, when unspent) plus any playable {F}
        damage-boost — Knocks Out the opponent's Active. The KO-aware, boost-inclusive promote pick
        (`promote_ko_aware`): among the benched bodies that reach such a KO it prefers the one already
        carrying the most Energy (deterministic index tiebreak). None when no benched body reaches a
        KO — the picker then stands down (`is_ko_promote_target` false everywhere).

        This is a promote *steering* signal (a Hypothesis then weights it), not a Lethal lock, so it
        may model one planned attach; the KO valuation itself is min-bound sound. It KO-gates (fires
        only on a real KO of the CURRENT opp Active), so it never perturbs a board with no KO and its
        Hypothesis sits below the ADR-0044 interpose promote (deny-prizes still wins its cases). ROLE-
        INDEPENDENT so it works before any deck Strategy is loaded — ml f26/f48: promote Mega Lucario
        ex (Aura Jab 130 >= Tangela 80) over Solrock (70); ml f24: promote the boosted Solrock."""
        if not (opp and opp.get("hp")):
            return None
        ma = next((p for p in (me.get("active") or []) if p), None)
        bench = me.get("bench") or []
        hand_ids = frozenset(c.get("id") for c in (me.get("hand") or [])
                             if c and c.get("id") is not None)
        hand_basic = self._hand_basic_energy(me.get("hand") or [])       # {EnergyType: count}
        best = None                                                      # (energy, index)
        for i, p in enumerate(bench):
            if not p:
                continue
            e = len(p.get("energies") or [])
            pstat = self.stats.get(p.get("id")) if self.stats else None
            # this turn's manual attach, when unspent — typed to the body's own Energy when the hand
            # holds that Basic, else counted WILD (fail-open)
            if not board.energy_attached and self._best_hand_attach_units(hand_ids, pstat) >= 1:
                planned = 1
                ptype = (pstat.energyType if (pstat and pstat.energyType in hand_basic) else None)
            else:
                planned, ptype = 0, None
            boost = self._typed_boost_total(obs, pstat, opp)
            # bodies that WILL sit on my Bench after this promote: the current Active retreats down,
            # every other benched body stays (a requiresBench partner is satisfiable from these)
            bench_names = self._promote_bench_names(me, i, ma)
            ko = self._best_affordable_ko_value(
                obs, board, opp, p.get("id"), e + planned, bound="min", body=p,
                extra_type=ptype, extra_units=planned, boost_amount=boost,
                boost_type=(pstat.energyType if pstat else None), promote_bench_names=bench_names)
            if ko > 0 and (best is None or e > best[0]):
                best = (e, i)
        return (_BENCH, best[1]) if best else None

    def _promote_bench_names(self, me: dict, promoted_index: int, ma: dict | None) -> set:
        """Names on my Bench AFTER promoting bench slot ``promoted_index`` — every other benched body
        plus the current Active (which retreats to the Bench). The `requiresBench` partner set a
        promoted attacker can count on (Cosmic Beam's benched Lunatone is the retreated Active)."""
        names = set()
        for j, b in enumerate(me.get("bench") or []):
            if j == promoted_index or not b:
                continue
            st = self.stats.get(b.get("id")) if self.stats else None
            if st is not None and st.name:
                names.add(st.name)
        ma_stat = self.stats.get((ma or {}).get("id")) if (self.stats and ma) else None
        if ma_stat is not None and ma_stat.name:
            names.add(ma_stat.name)
        return names

    def _typed_boost_total(self, obs: dict, body_stat, defender: dict | None) -> int:
        """Total flat this-turn damage-boost applicable to ``body_stat`` attacking the opponent's
        Active — the boosts already PLAYED this turn (`TurnBoostTracker`) plus the playable boost-Item
        copies still in MY hand (Items stack; a Supporter is one/turn, dropped once `supporterPlayed`).
        Each boost carries its own gates — the attacker-type ("your {F} Pokémon") and the defender-{ex}
        scope — applied here so a boost the line can't legally cash is never counted. 0 with no body."""
        if body_stat is None:
            return 0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        dstat = self.stats.get((defender or {}).get("id")) if (self.stats and defender) else None
        def_is_ex = bool(dstat and dstat.is_ex_body)

        def applies(atype, vs_ex) -> bool:
            if atype is not None and getattr(body_stat, "energyType", None) != atype:
                return False
            return not (vs_ex and not def_is_ex)

        total = 0
        for amount, atype, vs_ex in self._turn_boosts.boosts_for(yi):
            if applies(atype, vs_ex):
                total += amount
        supporter_spent = bool(state.get("supporterPlayed"))
        for c in (me.get("hand") or []):
            st = self.stats.get((c or {}).get("id")) if (self.stats and c) else None
            if st is None or not getattr(st, "damageBoost", 0) or getattr(st, "hp", 0):
                continue
            if st.is_tool:                                     # a Tool boost lives while ATTACHED
                continue                                       # (visible board state, priced elsewhere)
            if st.is_supporter and supporter_spent:
                continue
            if applies(st.damageBoostType, st.damageBoostVsEx):
                total += st.damageBoost
        return total

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
            if stat and stat.is_basic_energy and cid not in empty:
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

    def _evolving_wincon_on_bench(self, obs: dict, select: dict | None) -> bool:
        """True iff some benched opponent snipe target is a DEVELOPING WIN-CONDITION pre-evolution: its
        forward-evolution damage reaches a win-condition-class body (>= _EVOLVING_THREAT_DMG), its evolved
        form is NOT yet in play, AND that form is a genuine higher-prize payoff (>= 2 prizes). When present,
        the current-attacker snipe rungs stand down on every body that is NOT that pre-evo, so the +45
        `snipe-the-evolving-threat` takes the developing wincon instead of a bulky/energized current body
        whose rungs SUM past it (ms 85164131 f22: chip the Staryu that becomes Mega Starmie ex = 3 prizes,
        not the energized 1-prize Cinderace). Mirrors the `snipe_ko_available` sum-burial stand-down. Off
        (False) when the `evolving_wincon_priority` kill-switch is disabled or off a DAMAGE select. FAIL-CLOSED."""
        if not getattr(self, "evolving_wincon_priority", True):
            return False
        if not select or select.get("context") != _DAMAGE:
            return False
        for o in (select.get("option") or []):
            if o.get("type") != _CARD or o.get("area") != _BENCH:
                continue
            fwd = self._target_forward_damage(obs, select, o)
            if fwd is None or fwd < _EVOLVING_THREAT_DMG:
                continue
            if self._target_forward_form_in_play(obs, select, o):
                continue
            cid = (self._option_pokemon(obs, select, o) or {}).get("id")
            if cid is not None and self._forward_payoff_prize_value(cid) >= 2:
                return True
        return False

    def _target_forward_form_in_play(self, obs: dict, select: dict, option: dict) -> bool:
        """True iff this bench DAMAGE snipe target is a PRE-EVOLUTION whose evolved form is ALREADY on
        the opponent's board (any of the target's `_forward_card_ids` is an opponent in-play id) — the
        ADR-0044 discriminator that keeps `snipe-the-evolving-threat` from pre-chipping a redundant
        pre-evo when the ready wincon it becomes is already present (chip the ready form directly). False
        off a bench Damage option, for a non-evolving target, or when the forward form is not yet in play
        (the developing-wincon case f75/f47). FAIL-CLOSED (returns False) on any missing fact."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return False
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        fwd_ids = self._forward_card_ids(cid) if cid is not None else frozenset()
        if not fwd_ids:
            return False
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        opp_ids = {p.get("id") for p in ((opp.get("active") or []) + (opp.get("bench") or [])) if p}
        return bool(fwd_ids & opp_ids)

    def _snipe_ko_available(self, opp: dict, snipe_damage: int) -> bool:
        """Some benched opponent body is KNOCKED OUT by my Active's snipe rider — so a free prize is on
        offer and every POSITIONAL snipe rung stands down (`snipe-for-the-ko` +60 is the only score a KO
        target should need). Gating each rung on its OWN `target_kos` was not enough: the bonuses fire on
        a DIFFERENT, non-KO body and their SUM (top-threat 30 + forced-promotion 40 + evolving-threat 45
        = 115) out-voted the prize (ms 82754241 f45, 82753102 f63). A benched Tera body is never a KO
        target — it takes no damage from attacks while Benched. 0 off a DAMAGE select, so this is False."""
        if not snipe_damage:
            return False
        for b in (opp.get("bench") or []):
            if not b:
                continue
            stat = self.stats.get(b.get("id")) if self.stats else None
            if stat is not None and getattr(stat, "tera", False):
                continue
            hp = b.get("hp") or 0
            if hp and snipe_damage >= hp:
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
        damage). This is the single generic threat order behind `snipe-the-top-threat`; it never
        rewards a low-HP SUPPORT body. The Brief's target-role boosts now live in the MatchupPlan
        (ADR-0051), not here."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None
        poke = self._option_pokemon(obs, select, option)
        if (poke or {}).get("id") is None:
            return None
        return self._body_threat_rank(obs, poke, read, gamma)

    def _matchup_plan(self, opp: dict, brief_roles: dict, read, gamma: float):
        """Compose the ADR-0051 MatchupPlan for this decision — the unified opponent target-
        priority spine read by the snipe/gust consumers. Empty (inert) when the kill-switch is
        off. Curated ``brief_roles`` (already resolved to ids) is the top tier; ``read.targets``
        Intel is the γ-gated speculative tier; the general ``draw``-engine card fact is the
        always-on floor. Pure over the resolved inputs — the composition lives in
        ``matchup_plan.build_matchup_plan``."""
        if not self.matchup_targeting:
            return MatchupPlan()
        read_roles = {t.cardId: t.role for t in (read.targets if read else [])}
        return build_matchup_plan(brief_roles=brief_roles, read_roles=read_roles,
                                  draw_engine_ids=self._draw_engine_ids(opp), gamma=gamma)

    def _snipe_matchup_tactical(self, obs: dict, select: dict, board: Board, option: dict,
                                ctx) -> float:
        """ADR-0051: steer a bench SNIPE by the MatchupPlan — toward the highest-priority target,
        away from a negative-priority draw engine. Scored in the tactical band (above the
        positional snipe rungs, below KO_SCORE), so it decides WHICH body to chip while a real KO
        still wins. Stands down when a snipe-KO is on offer (defer to the KO logic, exactly as the
        positional rungs do) and off any non bench-DAMAGE option. 0 when the plan is inert.

        A POSITIVE boost stands down on an ADR-0044 redundant / promotion-mirage body: chip is best
        spent advancing my Prize Path, not on a body off it that I mean to gust around (test_107 —
        the redundant 2nd wincon copy AND the off-path Hariyama pre-evo both defer to the on-path
        small). The `snipe-the-evolving-threat` positional rung still fires on a genuine on-path /
        imminent pre-evo, so the wincon line is not abandoned — only the extra boost stands down. A
        negative (`avoid`) priority always applies — de-prioritizing a draw engine is safe regardless."""
        if (select.get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH or board.snipe_ko_available):
            return 0.0
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        if cid is None:
            return 0.0
        pri = board.matchup_plan.priority(cid) * _MATCHUP_PRIORITY_SCALE
        if pri > 0 and (ctx.target_prize_redundant or ctx.target_promotion_mirage
                        or ctx.target_is_bench_tera):
            return 0.0                                     # don't chip a body ADR-0044 says I don't need
            #                                              ...nor a benched TERA, which takes NO damage from
            #                                              attacks at all (CardStat.tera). `_snipe_tera_veto`
            #                                              already orders it last structurally; this keeps the
            #                                              boost itself from ever crediting an immune body, so
            #                                              a Brief may safely role a Tera-ex WINCON
            #                                              `prize_liability` (the natural call — it IS the
            #                                              wincon). The GUST is deliberately untouched:
            #                                              dragging a Tera Active REMOVES the immunity
            #                                              (bench-only), so `_can_ko` still takes it there —
            #                                              which is what makes roling one safe at all.
        return pri

    def _snipe_tera_veto(self, ctx) -> float:
        """STRUCTURAL veto: a benched Tera Pokémon takes NO damage from attacks at all ("prevent all
        damage done to this Pokémon by attacks", `CardStat.tera`; rules.md §185) — so aiming a snipe
        rider or a damage counter there is ALWAYS strictly wasted, on every board, forever. That is a
        CARD FACT, not a preference, so it lives in the Tactical layer (like every other KO/damage
        fact) rather than as a tunable positional weight.

        Supersedes the retired `dont-snipe-a-benched-tera` (−60 positional, `status="assumed"` — i.e.
        TUNER-MUTABLE). That weight only ever held by a 10-point margin: the reachable positional stack
        is `snipe-the-top-threat` (30) + `snipe-the-threat` (20) = 50, and adding `snipe-on-the-path`
        (12) reaches 62 and DEFEATS it. The bigger rungs are excluded elsewhere — `snipe-for-the-ko` via
        `target_kos`, `snipe-the-forced-promotion` via `_forced_promotion_key`, and
        `snipe-the-evolving-threat` only because no Tera card currently has `forward_max_damage > 0`, a
        DATA accident rather than a guarantee. One weight-tune or one new snipe rung would silently
        reintroduce the misplay (ms 81785223 f45: Wellspring Mask Ogerpon ex). A KO_SCORE-class veto
        dominates any positional stack, so nothing can outvote it.

        Orders the Tera LAST; it does NOT remove the option — when a benched Tera is the ONLY target the
        select is forced and the rider is wasted either way, so the agent must still answer. `ctx`'s
        `target_is_bench_tera` is already scoped to a bench target at a DAMAGE select."""
        return -KO_SCORE if ctx.target_is_bench_tera else 0.0

    def _draw_engine_ids(self, opp: dict) -> frozenset:
        """Opponent in-play body ids whose card carries the general ``draw`` Function Tag — a draw
        ENGINE (Dudunsparce / Budew class) that is a poor target in EVERY deck (matchup-agnostic).
        The general tier of the MatchupPlan; empty when no provider / no opponent."""
        if not self.functions or not opp:
            return frozenset()
        ids = {(p or {}).get("id")
               for p in (opp.get("active") or []) + (opp.get("bench") or [])
               if p and p.get("id") is not None and "draw" in self.functions.tags(p["id"])}
        return frozenset(ids)

    def _body_threat_rank(self, obs: dict, poke: dict, read=None, gamma: float = 0.0) -> float:
        """The select-independent threat-rank core behind `_target_threat_rank` — rank ANY benched
        opponent body (a raw player-dict Pokémon), so the Planner's KO-the-key-threat rung can rank
        the bench at the MAIN menu with exactly the same order the DAMAGE-select snipe uses. 0 when
        the id/provider is missing (an unknowable body never outranks a known threat). The Brief's
        target-role boosts have moved to the MatchupPlan spine (ADR-0051 `_snipe_matchup_tactical`);
        this stays the generic (card-fact + Read-modulated) threat order."""
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
            if (my_active and my_active.is_ex_body                    # I attack with an ex/Mega ex …
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

    def _forced_promotion_key(self, opp: dict, doomed: bool) -> int | None:
        """ADR-0044 Forced-Promotion Read: when the opponent's Active is doomed (a promotion is
        forced next turn), the body they bring up = their highest OWN-damage READY attacker on the
        Bench (printed max damage, energy-INDEPENDENT — they promote the win-condition and accelerate
        it, not the energized bench-sitter that merely happens to be affordable now). Returns
        ``id(body)`` for exact, duplicate-safe matching against the snipe option; None when not doomed
        / no benched attacker / no provider. NOTE: blind to hand-size-scaling attackers (Alakazam's
        printed 10 hides the real threat) — the ms f85 gap, deferred to a `forward_max_damage`/provider
        fix so `_body_threat_rank`'s hand-size boost is reflected here without over-counting pre-evos.

        READY means it can actually ATTACK next turn — attached Energy plus the one manual attach they
        will make reaches some attack's cost. "Energy-INDEPENDENT" was only ever meant to say 'they
        promote the win-condition, not whoever happens to carry Energy now'; read literally it picked a
        0-Energy Latias ex whose only attack costs three, over the 1-Energy Lillie's Clefairy ex that
        would be attacking immediately (ms 81785223 f45). A body that cannot attack next turn is not the
        promotion they will make. Among genuinely ready bodies, printed damage still decides."""
        if not doomed or not self.stats:
            return None
        best = None                                          # (own_damage, hp, id(body))
        for b in (opp.get("bench") or []):
            if not b:
                continue
            stat = self.stats.get(b.get("id"))
            own = stat.maxDamage if stat else 0
            if own <= 0:
                continue
            if getattr(stat, "tera", False):
                continue                                     # Tera on the Bench takes no damage —
                                                             # a pre-chip key I can never chip
            reach = len(b.get("energies") or []) + 1         # + the manual attach on their promote turn
            min_cost = getattr(stat, "minAttackCost", None) if stat else None
            if min_cost is not None and reach < min_cost:
                continue                                     # can't attack next turn — not their promote
            cand = (own, b.get("hp", 0), id(b))
            if best is None or cand[:2] > best[:2]:
                best = cand
        return best[2] if best else None

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
            if stat and stat.is_energy:
                continue                                  # fungible Energy: spare is never a redundant pitch
            out.add(cid)
        return frozenset(out)

    def _incoming_active_damage(self, ma: dict | None, oa: dict | None) -> int:
        """Worst next-turn damage their Active deals mine (the KO oracle's read, ADR-0052) —
        exposed on the Board so a +HP tool can test a survival breakpoint."""
        return self.combat.incoming_active_damage(
            ma, oa, context=getattr(self, "_opp_attack_context", None))

    def _active_doomed(self, ma: dict | None, oa: dict | None, opp: dict | None = None) -> bool:
        """The opponent can KO my Active next turn (current OR forward-evolved attack) — the KO
        oracle's WORST-CASE read; see its docstring for the deliberate no-affordability stance
        (docs/todo/incoming-affordability.md). The Threat Clock (ADR-0045) is the multi-turn
        complement, never a replacement."""
        return self.combat.active_doomed(
            ma, oa, opp, context=getattr(self, "_opp_attack_context", None))

    def _threat_shadow(self, obs: dict, board) -> dict | None:
        """S1b threat-clock doom SHADOW (docs/plans/opponent-value-equation-unification.md): emit the
        incumbent worst-case doom read (`active_doomed`, the decider) beside its `incoming(t=1)`-curve
        re-expression (`combat.doomed_incoming`, ceiling policy) + the agreement bit — the evidence
        bridge for routing survival through the ONE Threat-Clock curve. Deciding NOTHING.

        Sparse: None mid-sim (`self._planning`, no shadow work in rollouts) or with no live my-Active
        vs opp-Active to read. The two divergences the sweep of this bit adjudicates before any swap:
        the current-form affordability gate (`can_pay_cheapest`) and the omitted `hand_size_attacker`
        forward counter — ADR-0064 §2 kept `active_doomed` unconditionally worst-case."""
        if getattr(self, "_planning", False):
            return None
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) else None
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else None
        ma = next((p for p in ((me or {}).get("active") or []) if p), None)
        oa = next((p for p in ((opp or {}).get("active") or []) if p), None)
        if not (ma and oa):
            return None
        my_hp = ma.get("hp", 0) or 0
        dmg = self.combat.doomed_incoming(ma, oa, context=getattr(self, "_opp_attack_context", None))
        old = bool(getattr(board, "active_doomed", False))
        new = bool(my_hp and dmg >= my_hp)
        return {"doom_old": old, "doom_curve": new, "doom_incoming": int(dmg),
                "my_hp": int(my_hp), "agree": old == new}

    def _forward_incoming_damage(self, ma: dict | None, oa: dict | None, opp: dict | None) -> int:
        """Worst-case incoming if their Active EVOLVES next turn (the Posture forward read;
        ep82754875 f52 / ep83457493 f20) — the KO oracle's read."""
        return self.combat.forward_incoming_damage(
            ma, oa, opp, context=getattr(self, "_opp_attack_context", None))

    def _active_cheap_attack_kos(self, ma: dict | None, oa: dict | None) -> bool:
        """True if my Active's cheapest attack KOs the opponent's CURRENT Active this turn — so a costly
        burst Energy (e.g. Ignition -> Nebula Beam) is unnecessary. The mirror of `_active_doomed`
        (me attacking them, cheapest attack), via the shared `_can_ko` oracle."""
        if not (self.stats and ma and oa):
            return False
        return self._can_ko(self.stats.get(ma.get("id")), oa)

    def _can_wall_line_with_disruptor(self, me: dict, ma: dict | None, oa: dict | None) -> bool:
        """The retreat-to-promote-the-sacrificial-wall maneuver premise (dragapult f32/f20): my Active is
        a fragile developing win-condition LINE pre-evo (a Line pre-evolution, NOT the payoff), a benched
        `item_lock` disruptor (Budew's Itchy Pollen) can be promoted as a sacrificial wall, and the
        opponent's Active can damage that fragile line NOW (`_opp_active_can_damage_us`) — so retreat it to
        safety, promote the wall, item-lock, and evolve the line on the Bench behind cover. Board-SOUND
        (visible zones); silent for decks with no benched item-lock opener (no-op on mega_starmie /
        mega_lucario) and once the Active is the payoff (not a pre-evo). Backs `retreat-to-wall-the-line`
        and stands `hold-position-in-setup` down; `_finish_turn_last` rides the retreat step tier-0."""
        if not (self.functions and ma and ma.get("id") in self._line_preevo_set()):
            return False
        has_lock = any(b and "item_lock" in self.functions.tags(b.get("id"))
                       for b in (me.get("bench") or []))
        return has_lock and self._opp_active_can_damage_us(ma, oa)

    def _can_lock_line_with_disruptor(self, me: dict, ma: dict | None, oa: dict | None,
                                      turn: int) -> bool:
        """The OFFENSIVE variant of the disruptor maneuver (dragapult f20/t2, `disruptor_lock_maneuver`):
        early game, my Active is a fragile win-condition LINE pre-evo (f20) OR a retreatable support-ex
        PIVOT (f20's t2 sibling — Fezandipiti ex) with nothing better to do, and a benched `item_lock`
        disruptor (Budew) can be promoted to deny the opponent their Item turn — attach -> retreat the
        pivot/line-preevo into Budew -> promote -> Itchy Pollen. Unlike
        `_can_wall_line_with_disruptor` this does NOT require the opponent to threaten damage NOW (their
        Item-reliant SETUP turn is the target). Gated instead on: `turn` <= 2 (the lock bites their
        setup), NO win-condition Line body already carries Energy (nothing is being DEVELOPED — else
        that energy should advance the wincon, not fund the maneuver; the f21 boundary), the retreat is
        reachable this turn on ONE more Energy (a line-preevo Basic's cheap retreat), and the Active
        can't already KO (not a wincon attacker being wasted). Kill-switched; board-SOUND (visible
        zones); silent for decks with no benched item-lock opener. SHIP-AND-REFINE: its ladder value is
        matchup-dependent (a fragile promoted disruptor may concede a prize) — the kill-switch is the
        lever if it underperforms."""
        if not (getattr(self, "disruptor_lock_maneuver", False) and self.functions
                and turn <= 2 and ma and self.stats):
            return False
        ma_id = ma.get("id")
        # Eligible Active: a fragile win-condition LINE pre-evo (the original trigger, e.g. Dreepy), OR a
        # retreatable NON-attacking support-ex PIVOT (e.g. Fezandipiti ex, 85786096-t2) — an ex we would
        # cycle out anyway, NOT a wincon-line body. Both sac into the benched item_lock; the shared guards
        # below (nothing developed / cheap retreat / can't-KO) keep either variant a sound recovery line.
        ma_stat = self.stats.get(ma_id)
        is_support_ex_pivot = (ma_stat is not None and ma_stat.is_ex_body
                               and ma_id not in self._wincon_set())
        if not (ma_id in self._line_preevo_set() or is_support_ex_pivot):
            return False
        has_lock = any(b and "item_lock" in self.functions.tags(b.get("id"))
                       for b in (me.get("bench") or []))
        if not has_lock:
            return False
        line_ids = self._line_preevo_set() | self._wincon_set()
        in_play = [p for p in (me.get("active") or []) if p] + [b for b in (me.get("bench") or []) if b]
        if any((p.get("energies") or []) for p in in_play if p.get("id") in line_ids):
            return False                                  # a wincon Line body is already being energized
                                                          # -> develop it, don't retreat for the lock (f21)
        if ma_stat is None or getattr(ma_stat, "retreatCost", 0) > len(ma.get("energies") or []) + 1:
            return False                                  # the retreat must be reachable this turn
        return not self._active_maxed_kos(ma, oa)         # don't waste a body that could KO instead

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

    def _active_attack_payable(self, ma: dict | None, payable: int) -> bool:
        """My Active can PAY **and legally use** some attack this turn: ``payable`` (attached Energy +
        the best unspent hand attach) covers an attack's cost AND that attack is not transient-locked.
        True on unknown stats (fail-open — the starved stall-gust must only fire on a PROVABLE famine,
        ep83457493 f20).

        The lock half (ADR-0033) matters: a Riolu holding one {F} 'pays' Accelerating Stab, but it used
        Accelerating Stab last turn and the card says it can't again — the engine offered no ATTACK
        option at all. Energy math alone said payable, so `dont-play-damage-boost-when-cant-attack`
        stood down and the agent burned a Premium Power Pro that expired having buffed nothing
        (ml f69, CRITICAL)."""
        stat = self.stats.get((ma or {}).get("id")) if (self.stats and ma) else None
        if stat is None:
            return True
        if payable < (stat.minAttackCost or 0):
            return False
        grant = self._transients.grant_for_serial((ma or {}).get("serial"))
        if not grant:
            return True
        if grant.get("self_lock"):                     # every attack locked (blanket)
            return False
        same = grant.get("same_lock")                  # exactly one attack id locked
        if same is None:
            return True
        affordable = [aid for aid in (getattr(stat, "attacks", None) or ())
                      if self._attack_cost(aid) <= payable]
        return any(aid != same for aid in affordable) if affordable else True

    def _attack_impossible_on_menu(self, select, me: dict, energy_attached: bool) -> bool:
        """The ENGINE says my Active cannot attack this turn: I am at the open turn menu and it lists no
        ATTACK option. Authoritative where the closed-form energy math is not — it already accounts for
        a transient attack-lock, a Special Condition, and turn-1-going-first, and unlike the ADR-0033
        tracker it survives a single-frame retest (a Correction carries one `obs`, so the tracker never
        saw last turn's attack).

        NOT decisive while an attach could still turn an attack on: with the manual attach unspent and a
        reusable Energy in hand, the ATTACK option simply hasn't appeared yet. Only once the attach is
        gone (or there is nothing to attach) does an empty attack menu mean 'no attack this turn'."""
        if not select or select.get("context") != _MAIN:
            return False
        opts = select.get("option") or []
        if not opts or any(o.get("type") == _ATTACK for o in opts):
            return False
        if not energy_attached and self._has_reusable_energy(me.get("hand") or []):
            return False
        return True

    def _active_fully_powered(self, ma: dict | None) -> bool:
        """My Active already carries the Energy for its HIGHEST-damage attack (attached ≥
        `maxDamageCost`) — a burst Energy (Ignition) has no urgent job on it. False when the stat /
        cost is unknown (fail-closed: the keep-at-discard rules stay protective, ep83454549 f36)."""
        stat = self.stats.get((ma or {}).get("id")) if (self.stats and ma) else None
        cost = getattr(stat, "maxDamageCost", 0) or 0
        if not cost:
            return False
        return len((ma or {}).get("energies") or []) >= cost

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
        if area == _LOOKING:                               # a face-up reveal (Pokégear/search top-N):
            looking = state.get("looking") or []           # candidates live in current.looking, not a
            return looking[index] if 0 <= index < len(looking) else None   # player zone (None = facedown)
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
