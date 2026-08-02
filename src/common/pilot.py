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

from common import deck_odds
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
from common.scouting.matchup_plan import MatchupPlan, build_matchup_plan

# Engine vocab (enum mirrors, KO_SCORE, _ENGINE_TAGS) shared w/ doctrines -> common.strategy.context.
# Doctrines own their Hypotheses + Pilot-side `*Mixin` code — see those modules.
from common.grading import HORIZON as _HORIZON
from common.strategy.context import *  # noqa: F401,F403  (the engine-vocabulary constants + _fires/Board live there or below)
from common.strategy.doctrines import FetchMixin, GustMixin, ShuffleRefreshMixin, ToolMixin
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
                                     own_draw_count, refresh_branches)  # (ADR-0060 swing oracle)
from common.strategy.sequence import followup_damage  # noqa: E402  (ADR-0061 horizon-2 lock oracle)
from common.strategy.denial import coin_odds          # noqa: E402  (ADR-0062 energy denial)

#: "derive this from the observation" — the DEFAULT sentinel for a `_snapshot` argument whose own
#: vocabulary already spends None on a meaning. `deck_known=None` is the deck tracker's answer for
#: *"the prizes are not resolved, so I claim nothing"*, a real value a caller may legitimately pass,
#: so "unset" needs a distinct marker or the two collapse and an honest no-claim silently re-derives
#: (POC-T3.5, Issue #279). Deliberately NOT in the scoring-weight table below — it is not a weight.
_DERIVE = object()

# A shuffle-refresh moves cards in four directions and they are NOT worth the same per card. Pricing
# them symmetrically is what broke the guard family on the first cut: a per-card credit for cards I
# DRAW reached +76 and went straight through `hold-wincon-dont-shuffle` (−25),
# `hold-irreplaceable-tool-dont-shuffle` (−30) and `dont-refresh-into-a-probable-miss` (−25), which
# were all calibrated against `dig-before-commit`'s flat +20.
#
# The four legs split by WHOSE HAND they price, and the two sides are priced by different means for a
# structural reason: my hand is FACE-UP to me, so its leg can ask each held card what my board loses
# without it (the graded SHED); theirs is a `handCount` and nothing else, so their legs can only ever
# be `card count × a per-card rate`. The constants below carry `OPPONENT_HAND` in their names because
# reading `_REFRESH_STRIP` as "cards stripped from ME" is the natural misreading, and it inverts the
# sign of the whole term (Issue #261 review, 2026-08-01).
#
#   MY hand:     _REFRESH_CYCLE (+, flat)          · the SHED (−, GRADED — `_refresh_shed_keepcost`)
#   THEIR hand:  _REFRESH_OPPONENT_HAND_STRIP (+)  · _OPPONENT_HAND_FRESH (+)  · _OPPONENT_HAND_GIFT (−)
#
# STRIP and GIFT are one leg split by SIGN, never two live terms: both read the single signed
# `opp_net`, so `max(-opp_net, 0)` and `max(opp_net, 0)` cannot both be non-zero. A one-sided refresh
# (Lillie's, Lacey — they shuffle only MY hand) zeroes `opp_net` outright, leaving `CYCLE − SHED`.
_REFRESH_CYCLE = 20        # the DRAW side, flat: cards I have not seen are speculative and only as
                           # good as what the deck can still supply — which is precisely what the
                           # `hold-*-dont-shuffle` / probable-miss guards adjudicate. Bounded and flat
                           # so those guards can still cancel it, exactly as they could cancel the +20
                           # `dig-before-commit` used to supply blindly.
# _REFRESH_SHED (the flat −8/card-lost shed) RETIRED 2026-07-18 (ADR-0065), and its Σ-over-copies
# successor RETIRED 2026-08-01 (ADR-0101): the shed side is now the v2 assignment SET marginal over
# the whole hand (`_refresh_shed_keepcost`). ENERGY_TIER (8, `common.card_worth`) is the old flat anchor.
#
# The three OPPONENT-HAND rates below stay FLAT deliberately, and the reason is measured rather than
# doctrinal (ADR-0101; hand-disruption-grill-spec.md design A, PARKED). Grading them needs a worth for
# cards we cannot see, i.e. an expectation over their representative build — and 59.4% of that build
# prices `_role_value` 0 today, because role declarations come from OUR deck. The missing 59% is
# exactly their attackers and wincons, so a "derived" GIFT would be biased DOWNWARD precisely where it
# matters, making "Judge into their small hand" look cheap — ml f111's CRITICAL blunder. They retire
# when `gusting-keepcost-design.md` §2's shared opponent role sheet exists, not before.
_REFRESH_OPPONENT_HAND_STRIP = 4   # per card stripped from THEIR hand — certain denial (ms f43/f45/f100/f64).
_REFRESH_OPPONENT_HAND_GIFT = 8    # per card HANDED to them: Judge into a 1-card opponent hand REFILLS
                           # them to 4. Priced like a shed — a card in their hand is as real as one in
                           # mine. The 4-vs-8 ratio is the denial haircut: denying them a card is worth
                           # about half handing them one, because they redraw into a fresh one.
_REFRESH_OPPONENT_HAND_FRESH = 2   # per stripped card THEY DREW LAST TURN (`opp_hand_size_delta` > 0):
                           # live resources denied, versus cards they have demonstrably been unable to play.
# _REFRESH_BENCH_BODY / `_refresh_cycle_adaptive` (the ADAPTIVE draw credit — "CYCLE should scale to
# the open bench-deploy need", ep83038055 f40) DELETED 2026-08-01 with the shadow that was its only
# reader (ADR-0101). It reported beside the flat CYCLE and decided nothing, so it fell with
# `_refresh_shed_shadow`; the promotion question it was measuring is now T3's, where a starved bench
# is priced by the `development` term family rather than by a second credit inside this equation.
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
_DENIAL_PLAY_W = 1.0       # points per damage-point denied, at the PLAY. REPLACES `play-energy-denial`'s
                           # flat +20, which paid the same for turning off a 270 nuke as for shaving 70
                           # off a benched body. Same lesson as ADR-0060: price the quantity, don't
                           # threshold it.
_DENIAL_ITEM_COST = 10     # the value of KEEPING the Hammer. An Item is finite, and a free Item is tiered
                           # ahead of everything by `_finish_turn_last` — so a purely positive term could
                           # never decline one: any score above zero gets it played. The strip must beat
                           # the hold (ms f29: "wasted crushing hammer").
_BRIEF_THREAT_BOOST = 1.25 # Deny Relevance's Brief SHARPENER (ADR-0080 decision 2, Issue #199): a body
                           # the matched Matchup Brief names among its `threats` is scored up, then
                           # clipped back into [0,1]. A MULTIPLIER, never a source — authored scouting
                           # sharpens a read that already works without it, which is what keeps the
                           # instrument correct against the unbriefed decks the Kaggle grader is made
                           # of (only 8 Briefs exist). It cannot promote a whiff: 0 x anything is 0,
                           # so a Brief can never make an irrelevant Energy worth taking — the same
                           # discipline `_DENIAL_UNFAVORED` follows below ("a booster must scale the
                           # oracle, never add to it", ADR-0063).
_DENIAL_TARGET_W = 1.0     # points per damage-point denied, at the DISCARD_ENERGY select. Ranks the
                           # Hammer's TARGET once its coin comes up heads; nothing scored that select
                           # before, so a won flip stripped option [0] — the OLDEST-attached Energy.
#: ADR-0080 / Issue #187: the factor standing where `opp_denial_best` supplied a damage MAGNITUDE, now
#: that relevance is a [0,1] scalar. **DERIVED, not chosen** — it is exactly the normalizer relevance
#: was divided by, so `K x relevance == the setback damage` and the armed fire rung is a strict
#: GENERALISATION of the incumbent's own arithmetic rather than a re-scaling of it. There is no free
#: parameter here: pin it to anything else and `K x relevance` stops being a damage figure at all.
#:
#: Measured on the ADR-0062 anchors AT ISSUE #187, the identity reproduced the incumbent to the cent
#: where the readings coincided, and diverged only upward where relevance saw a setback `_denial_at`
#: could not — **f12 +55.0 vs +22.50, f26 +16.25 vs +1.25**, same sign, same decision, strictly
#: better informed.
#: ⚠️ That comparison is the DERIVATION RECORD, not a live cross-check, and **both armed figures have
#: since moved** — do not read them as current. f12 now prices +22.50 (ADR-0084 Amendment A applied
#: the mandated `_DENIAL_FORWARD` discount to the armed read, which had been crediting the forward
#: form at double) and f26 now prices +95.00 (decision 5 dropped the bench weight in favour of the
#: promotion gate). Issue #228 then armed the flag and DELETED the ADR-0062 magnitude rung
#: (`opp_denial_best` / `_denial_at`), so there is no second instrument left to compare against at
#: all. K stays pinned to the normalizer for the reason it was derived — it cancels the division
#: relevance performs — and that is now the only thing holding it. The live pin is
#: `test_deny_relevance_consumer.py::test_the_fire_factor_is_the_normalizer_so_it_prices_in_damage_units`.
#:
#: ⚠️ **The witness moved (ADR-0084 decision 8).** This note used to cite f21/f29's benched Dragapult
#: ex pricing **-1.25 on both**. That figure was `70 x _DENIAL_BENCH`, and decision 5 retired the
#: constant from this rung in favour of ADR-0071's promotion GATE (Issue #228 then deleted the
#: constant outright with the rest of the OFF path). On that board the gate SHUTS (their Terapagos ex
#: holds 0 Energy against retreat cost 2, and no switch survives the read), so the bench carries no
#: weight, `deny_relevance_best` is 0, and the rung takes its whiff branch at **0.00** — same
#: decision, different number. f12 and f26 are the surviving witnesses; f21/f29 now witness the
#: GATE instead. K itself is untouched: decision 5 changed an area WEIGHT, which multiplies outside
#: this normalizer, so there was never a free parameter here to re-derive.
#:
#: It is **NOT an exchange rate** and must never be reused as one: that is the Worth Damage Rate, which
#: ADR-0080 decision 1 rules MOOT for deny and `common/currency.py`'s guard test keeps absent by design.
#: The distinction is that this factor cancels a normalizer inside ONE instrument's own units; a rate
#: would carry a value ACROSS two currencies.
_DENY_RELEVANCE_K = _DENY_RELEVANCE_NORM
_DENIAL_UNFAVORED = 0.3    # Lever A (ADR-0026), as a MULTIPLIER on the priced denial rather than a flat
                           # rung beside it: when the Read says the race is lost, a strip that already
                           # denies something is worth MORE. It can never make a whiff worth playing —
                           # scaling 0 leaves 0, and scaling a negative play value leaves it negative.
                           # This is the whole point (ms 83968638 f17, CRITICAL): the old flat
                           # `disrupt-when-unfavored` (+18) rode `opp_denial_best > 0` (the raw PRESENCE
                           # of denial) and so OVERRODE the oracle's own hold — a free Item at score > 0
                           # is tiered ahead of everything. A booster must scale the oracle, never add to it.
                           # RE-EXPRESSED ON RELEVANCE (user ruling 2026-07-30, ADR-0080 Amendment B): its
                           # SUBJECT is now "deny's value, whichever instrument supplies it" rather than
                           # "the priced denial magnitude". It multiplies the whole product, so it is
                           # scale-invariant — a 30% amplification is 30% whether the term it scales is a
                           # damage figure or `K x relevance`, and the f17 discipline survives verbatim
                           # (relevance 0 -> 0, so it still cannot resurrect a whiff). Since Issue #228
                           # deleted the ADR-0062 magnitude rung, `K x relevance` is the ONLY term it
                           # scales; the scale-invariance argument is what made that deletion safe.
                           # ADR-0078 decision 6 had retired this outright, on the grounds that it and
                           # `needs.phase_scale` "say the same thing multiplicatively". That retirement is
                           # **WITHDRAWN**: under ADR-0080 deny reads `phase_scale` on NO surface, so the
                           # substitution justifying it no longer exists, and retiring it unreplaced would
                           # have deleted Lever A from the live codebase (this is its last consumer).
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
# `_HAND_SIZE_ATTACKER_BOOST` (a flat +500 for a line reaching a hand-size attacker) was DELETED by
# Issue #213. It was a proxy for a fact `_threat_damage_pair` now computes exactly, so keeping both
# would double-count one card fact; and as a flat constant keyed off a Function Tag covering exactly
# one card in the pool, it could never generalise to any other scaling attacker.
_PREVENT_EX_SNIPE_BOOST = 500  # snipe-rank boost for a benched body whose line reaches a Pokémon that
                           # PREVENTS my ex attacker's damage (`prevent_ex_damage`, e.g. Dwebble→Crustle) —
                           # hard counter once evolved, snipe the fragile pre-evo NOW (ep82225138 f46).
# `_MATCHUP_PRIORITY_SCALE = 5` (ADR-0051) was DELETED with `_snipe_matchup_tactical` by ADR-0085
# decision 5 — its sole consumer. It existed to map a MatchupPlan role priority into a TACTICAL band
# defined relative to "the positional snipe rungs (Σ≲150)", and once those rungs are gone the band it
# named has no lower edge to sit above. The Brief's steer now travels as a MULTIPLIER on a [0,1]
# scalar instead of an addend in a damage-scale band, which is why no replacement rate is needed.
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
                                       # AND most-Energy. Backs `promote-the-powered-attacker`, not a bare copy/slot-0 (ep83007714 f92/f104)
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
    # reader. `_draw_engine_ids` survives — the Read's deck-recognition still consumes it.
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
                                       # dragapult f21). Gates `dont-fund-the-non-attacking-body`
    attach_target_under_max: bool = False  # receiving Pokémon carries fewer Energy than its
                                           # HIGHEST-damage attack costs — can't yet fire its big attack
                                           # (1 W can Jetting Blow but not Nebula Beam CCC). Fail-CLOSED (False when unknown).
    attach_target_is_priority_wincon: bool = False  # this attach option puts Energy on the ONE
                                           # win-condition to concentrate on (== board.priority_wincon_slot)
                                           # — most-built buildable wincon. Gates `concentrate-energy-on-wincon` (load one, not spread).
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
                                       # ready wincon. `promote-the-powered-attacker` fires so it's the built Mega, not a bare copy
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
    fetch_sheds_junk: bool = False  # this option PLAYS a cost_discard fetch whose 2 predicted sheds
                                   # (top-2 pitch over hand minus the fetch, same discard rungs) BOTH score > 0 — junk cost, dig at the free band (`costly-fetch-sheds-junk`)
    fetch_sheds_live: bool = False  # ...a predicted shed scores < 0 — a live card pays the cost
                                   # (`dont-shed-a-live-card`)
    fetch_sheds_key: bool = False   # ...`keep-key-cards-at-discard` fires on a predicted shed — an
                                   # irreplaceable card is forced into the pitch (`dont-shed-a-key-card`)
    refresh_probable_miss: bool = False  # this option PLAYS a shuffle_hand refresh whose N-card draw
                                   # PROBABLY misses every needed card (post-anchor hypergeometric over the
                                   # shuffle-grown pool, ADR-0024 amendment). Drives `dont-refresh-into-a-probable-miss`.

# ── the ATTACH DECIDER's constants (ADR-0069; kill-switch `attach_value`, shipped ON) ─────────
# Every one is DERIVED, not folklore: each is pinned by an inequality in
# tests/strategy/test_attach_bands.py, solved against the SHIPPED decks' real build steps. Change a
# constant and the band tests re-check the whole set — that is the retune protocol, not a comment.
#
# Damage->weight calibration (ADR-0060 calibration-anchor). Retuned CONSTRAINT-FIRST for the swap:
# the written inequalities give a feasible region, `tools/train/probes/attach_decider_sweep.py`
# picks inside it on corpus score-diff (agreement with the retired pile peaks flat over [1.0, 1.5];
# 0.3 — the shadow-era seed, sized so a flat +15 rung floor still carried small attaches — costs 3
# extra corpus regressions because a real early build step then scores below a +8 Tool equip).
# 1.0 is the region's lower edge AND makes the marginal a DIRECT damage currency: one point of
# marginal is one rung point, the same units the ADR-0062 damage tacticals already speak.
_ATTACH_VALUE_SCALE = 1.0
# The two orthogonal CHANNELS, in DAMAGE units so they sum with the attack axis before scaling.
# Both are LOW-BAND by ruling: a mobility/fuel signal breaks ties among build-equal options and must
# never outrank one real build step (the thinnest shipped step is Staryu's first slot toward Nebula
# Beam, 210/9 x 0.25 = 5.83). "~half the smallest live build credit" -> 3.0.
# NB the channels are in damage units BEFORE the scale, so raising the scale never lets a channel
# overtake a build step — the constraint is scale-invariant by construction.
_ATTACH_RETREAT_EQUITY = 3.0   # FULL coverage of the printed Retreat cost (colourless -> type-agnostic)
_ATTACH_ABILITY_FUEL = 3.0     # a dormant in-play Ability switched on (the {D} a bare Munkidori wants)
# The resource TIE-BREAK (ADR-0069 §5c): among equal marginals, spend the RENEWABLE card. Charged on
# the worth a card carries ABOVE a reusable Basic (`card_worth.ENERGY_TIER`), so a plain Basic pays
# nothing and only a one-shot (Ignition's `discard_eot` band, 30) is nudged. Sub-band by
# construction: 0.05 x (30 - 8) = 1.1 < one scaled build step (1.0 x 5.83 = 5.83), so it can order
# equals and never overturn a real build difference.
_ATTACH_RESOURCE_TIEBREAK = 0.05
# A pre-evolution's Energy carries through evolution, but the body must still EVOLVE before the
# payoff fires — so its forward build is discounted below an already-evolved body's (83007714-22)
# and below a this-turn arm of the doomed Active (82522726-7, 85785606-19/21).
_ATTACH_PREEVO_DISCOUNT = 0.25


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
    attach_working: dict | None = None  # the ENERGY-ATTACH DECIDER's legible working (ADR-0069 §9):
                                     # the per-option AXES rows — attack_axis (this_turn / build /
                                     # accel_value), retreat_equity, ability_fuel, evaporation_loss,
                                     # which gate fired, and the `tactical` each option actually
                                     # scored. This DECIDES (the rows are the decider's own arithmetic,
                                     # not a shadow's), so there is no agreement bit: one emission path,
                                     # one truth. A Pokémon Tool ABSTAINS (not Energy) and is counted.
                                     # Sparse: None off an attach menu / mid-sim
    threat_shadow: dict | None = None   # the DOOM keep-worst-case SHADOW (Threat-Clock unification
                                     # S1b, docs/plans/opponent-value-equation-unification.md): the
                                     # incumbent `active_doomed` (worst-case, the decider) beside its
                                     # `incoming(t=1)`-curve re-expression (`combat.doomed_incoming`,
                                     # ceiling policy) + the agreement bit. Surfaces the ONE known
                                     # divergence (the current-form affordability gate) for the
                                     # survival-swap adjudication; a second was claimed and RETRACTED
                                     # (ADR-0064 Amendment A, Issue #213 — the hand-size scaler was
                                     # always priced by the Damage Formula, on both sides of the
                                     # comparison). Deciding NOTHING — sparse: None mid-sim / no live
                                     # my-Active vs opp-Active
    recur_shadow: dict | None = None    # the DISCARD-RECUR fuel SHADOW (Threat-Clock unification S2):
                                     # per opponent in-play body whose line refuels from its discard
                                     # (`discard_energy_recur`), the Threat-Clock reads with-vs-without
                                     # the discard fuel (incoming(t=1) to my Active + turns_to_afford)
                                     # — how much the discard reservoir accelerates/sharpens the threat.
                                     # Deciding NOTHING (live reads pass no fuel) — sparse: None mid-sim
                                     # / no opponent discard fuel
    opp_target_shadow: dict | None = None  # the OPPONENT-TARGET value SHADOW (Opponent Value Equation
                                     # S3, O1 = Option B): per opponent in-play body the two-term removal
                                     # value in the one currency — prize_advance + phase × survival_shift
                                     # (needs.opponent_target_value; survival via the S1 turns_to_ko_me
                                     # curve). Deciding NOTHING — the evidence for the snipe/gust/deny
                                     # slot-assignment fold. Sparse: None mid-sim / no opp bodies


def _slot_cid(slot):
    """The card id a `line:<cid>` slot belongs to, or None for any other slot kind."""
    key = getattr(slot, "key", "") or ""
    if getattr(slot, "kind", "") != "line" or not key.startswith("line:"):
        return None
    head = key.split(":")[1]
    return int(head) if head.isdigit() else None


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
                 matchup_targeting=True,
                 ko_target_whiff=False, opp_resource_reads=False,
                 enabler_item_composer=False,
                 develop_rollout=False, discard_keep_value=False, needs_keep_value=False,
                 leaf_hand_value=False, attach_value=True, evolve_value=True, deploy_value=False,
                 promote_retreat_value=True, doom_matched_relax=False,
                 recur_fuel_relax=False, gust_target_slots=False,
                 deny_strip_delta=False, deny_relevance=False, scaled_threat_rank=False,
                 snipe_relevance=False, leaf_option_equivalence=False):
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
        self.promote_retreat_value = promote_retreat_value   # the PROMOTE/RETREAT DECIDER's emergency
                                                        # lever (ADR-0100, shipped ON): the Sub-lethal
                                                        # Residual, one evaluator across the body pick, the
                                                        # whether-to-retreat question and the forced
                                                        # promote. OFF is DEGRADED MODE, not a rollback —
                                                        # eleven of the twelve rungs it replaced are
                                                        # deleted, so OFF silences promote/retreat and
                                                        # leaves only `retreat-to-wall-the-line` speaking.
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
        self.leaf_option_equivalence = leaf_option_equivalence   # ADR-0091 (Issue #247) kill-switch:
                                                        # options a board cannot tell apart are ONE
                                                        # decision, so the develop rung sims one
                                                        # representative per class and gives every member
                                                        # the class MAXIMUM. Fixes a measured 1167.0-vs-95.4
                                                        # split on three byte-identical Riolu, caused by an
                                                        # index-order-dependent greedy rollout (Issue #254).
                                                        # OFF = byte-identical to the pre-#247 rung.
        self.develop_rollout = develop_rollout          # develop-rung Phase 1 kill-switch (default OFF):
                                                        # the within-turn rollout rung — on a develop turn
                                                        # (plan_turn else None) where greedy is weak/indifferent,
                                                        # sim each candidate first action to end-of-turn and
                                                        # commit the best leaf. OFF = byte-identical
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

    def _evaluate(self, obs: dict, *, carried=None) -> Decision:
        """Rank this decision's options. ``carried`` forwards a Carried State snapshot to the board
        build, making the whole evaluation non-mutating in the two memories (ADR-0068 decision 2) —
        what a re-score of the root inside a simulated line needs."""
        select = obs.get("select")
        if select is None:                       # initial deck-submission step
            return Decision(chosen=list(self.deck))
        if not self._planning:                   # ADR-0033: consume the REAL log stream only —
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
                            # The doom shadow is a per-decision DIAGNOSTIC, so it must not depend on
                            # which branch decided. #177 made more KO lines reachable, which sent
                            # frames like 82749168-29 down this branch for the first time and
                            # silently blanked their shadow (`ms_doom_relax_bare_terapagos_f29`).
                            threat_shadow=self._threat_shadow(obs, board),
                            posture=self._posture_record(board),
                            objectives=self._objectives_trace(board), win_prob=self._win_prob(board),
                        game_plan=self._game_plan_record(board),
                            plan_candidates=(self._develop_candidates_pending   # develop-rung Phase 1: the
                                             if planned.goal == "develop" else None),  # rung's ranking (sparse)
                            gamble=getattr(self, "_gamble_trace", None),
                            attach_working=self._attach_working(obs, select, board, options),
                            lethal_refuted=refuted, lethal_lost=self._lethal_lost)
        max_count = select.get("maxCount", 0)
        # Primary key = score; secondary key breaks an EXACT tie toward an attach feeding a needy Line
        # body (ep82867148 f87). decide()-only ordering nicety, W-route-invisible, never enters weight fit.
        by_score = sorted(range(len(options)),
                          key=lambda i: (traces[i].score, traces[i].attach_to_needy_line), reverse=True)
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
        chosen = self._never_pre_bench(select, chosen)
        return Decision(chosen=chosen, options=traces, read=board.read, lethal_refuted=refuted,
                        posture=self._posture_record(board),
                        objectives=self._objectives_trace(board), win_prob=self._win_prob(board),
                        game_plan=self._game_plan_record(board),
                        gamble=getattr(self, "_gamble_trace", None),
                        discard_shadow=self._discard_shadow(obs, select, board, options, chosen),
                        attach_working=self._attach_working(obs, select, board, options),
                        threat_shadow=self._threat_shadow(obs, board),
                        recur_shadow=self._recur_shadow(obs, board),
                        opp_target_shadow=self._opponent_target_shadow(obs, board),
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

    def _prefer_soonest_arming_evolve(self, order: list, options: list, traces: list) -> list:
        """Break an EXACT tie between EVOLVE options toward the body that arms soonest — i.e. put the
        evolution where the Energy already is (ADR-0070 amendment M, #167).

        `evolve-the-energized-body-first` was one of the five rungs the 1b swap retired, on the
        premise that `evolve_value` subsumes it. It does not, and the reason is structural rather
        than a missing read: `deploy = result.deploy() - body.deploy()` cancels **per slot**, because
        the body and its result share that slot's Energy, arm and ko. So an energised Staryu cancels
        2-against-2 and a bare one cancels 3-against-3 — both exactly 0.0 — and the tie then broke by
        raw option INDEX. Measured on 81905522|0|decision|64: the equation reads the post-attach board
        correctly (bench0's arm drops 3 -> 2), and the delta erases what it read. The consequence was
        the Energy and the evolution landing on DIFFERENT bodies, stranding an Energy on a Staryu that
        must still evolve before it can attack.

        So consult the one term that does not cancel — the RESULT's arm clock — and only where it can
        change nothing else: a run must be **all EVOLVE options at an identical score** before it is
        reordered, so an evolve can never be promoted past a tied non-evolve. Ordering only; no score
        moves, so f35's hold, the attach-anyway floor and the free-development exemption are all
        untouched. The arm clock is already in `evolve_working["result"]`, so a trace reader can see
        why one body won.

        Tied evolves need NOT be adjacent: on 81905522|0|decision|64 the equal-score run is
        ``[2, 0, 1, 6]`` with a non-evolve sitting BETWEEN the two evolves, so a consecutive-run
        implementation never forms a run and never fires. This permutes the evolves *within the
        positions they already occupy*, leaving every non-evolve exactly where it was — which is what
        keeps "an evolve is never promoted past a tied non-evolve" true while still ordering the
        evolves against each other."""
        def arm(i):
            w = getattr(traces[i], "evolve_working", None)
            return (w or {}).get("result", {}).get("arm") if w else None

        def is_evolve(i):
            return options[i].get("type") == _EVOLVE and arm(i) is not None

        out, n = list(order), len(order)
        i = 0
        while i < n:
            j = i                           # the maximal run of options sharing one score
            while j + 1 < n and traces[out[j + 1]].score == traces[out[i]].score:
                j += 1
            slots = [k for k in range(i, j + 1) if is_evolve(out[k])]
            if len(slots) > 1:              # permute ONLY the evolves, into their own slots
                for slot, opt in zip(slots, sorted((out[k] for k in slots), key=arm)):
                    out[slot] = opt
            i = j + 1
        return out

    def _never_pre_bench(self, select: dict, chosen: list) -> list:
        """NEVER place a Pokémon on the Bench during Set Up (ADR-0086 decision 9). A sound rule read
        off the rulebook, not a price — so it filters the pick rather than scoring it, like decision
        7's empty-Bench guard.

        Deferring to my own first turn is WEAKLY DOMINANT: never worse, sometimes better. Three facts
        make it safe, each checked at source rather than recalled:

        1. **The placement is optional.** "Put **up to** 5 more Basic Pokémon face down on your Bench"
           (`docs/rulebook.txt` L97) — which is why the select carries `minCount 0` and this can be a
           filter at all.
        2. **No ATTACK reaches me first, in either seat.** Going first, my turn 1 precedes any
           opponent action at all; going second, their turn 1 cannot attack (`docs/rules.md` §2,
           rulebook L152), so their turn 2 is the first legal attack — after my turn 1 either way.
        3. **No ABILITY damage reaches me either**, which is the leg that makes 2 sufficient rather
           than merely suggestive. Only Basics can be in play on turn 1, because neither player may
           evolve on their own first turn (`docs/rules.md` §4, rulebook L123-128) — and of the 21
           damage-counter Abilities in `data/EN_Card_Data.csv`, ZERO are on a Basic. Dusknoir's 130,
           Froslass's checkup counters and Tyranitar's Sand Stream are all evolutions.

        And the Basics I keep in hand cannot be stripped in the meantime: the player going first
        cannot play a Supporter (rulebook L133), so no Judge or Iono shuffles them away.

        What deferring BUYS: the pregame placement wastes every bench-drop Ability, since "once during
        your turn" is unsatisfiable before the game starts — Meowth ex's Last-Ditch Catch is the case
        that opened Issue #197. Benching the same body on turn 1 fires it. Going second it also buys
        information: I draw a card and see their committed board before spending any of my own.

        This SUBSUMES three Set-Up special cases that were separately bolted onto the equation — the
        exposure fallback's pregame branch, the redundancy charge keyed on `setup_placed_ids`, and
        the `_SETUP_BENCH` half of the since-deleted `bench-fill-a-basic`. Three approximations of
        one rule.

        Scoped to `_SETUP_BENCH` only. The Set-Up ACTIVE choice is untouched (a Basic there is
        mandatory), and every in-game bench play is still the Deploy Marginal's to price."""
        if select.get("context") != _SETUP_BENCH:
            return chosen
        return []

    def _empty_bench_forced(self, obs: dict, select: dict, board: Board, options: list,
                            order: list) -> list:
        """The post-setup EMPTY-BENCH guard (ADR-0086 decision 7): with nothing to promote, a single
        Knock-Out ends the match on the spot (`docs/rules.md` §7 case 2), so a legal Pokémon deploy is
        TAKEN rather than ranked.

        A FILTER on the option order, never a score, and since Issue #261 item 2d the ONLY mechanism
        scoring or ordering this fact besides `_predicted_loss` — `keep-a-bench` (+60) scored the same
        play "so the two agree", and ADR-0096 decision 2 deleted it as the redundant third guard.
        `_LINE_CAP`'s band invariant is why this cannot be a weight at all: max positional (readiness
        300 + survival 50 + threat 100 + value 40 + line 100) = 590 < 1000 = KO_SCORE, deliberately,
        so no positional term can outrank a real prize — and a loss-avoidance value cannot be
        simultaneously bounded under that band AND un-outbiddable. A filter is the only shape that is
        both.

        It ranks WHICH body, never WHETHER: the surviving order is the Deploy Marginal's, restricted
        to the deploys.

        **Post-setup only.** Verified at source (`docs/rules.md` §2): the player going first cannot
        attack on turn 1 and the player going second acts only after that turn, so in either seat my
        first turn precedes the first legal attack — declining a pregame placement cannot lose the
        game before I can bench. Scoping it here keeps the guard a statement about a REACHABLE loss:
        at Set Up no Knock Out is legal yet, so there is nothing to be forced by.

        The converse is what makes the scoping mandatory: an unscoped guard fires at `_SETUP_BENCH`
        on `setup_bench_decline_f3` (bench empty, Meowth ex the sole option) and forces exactly the
        placement decision 3 derives us out of, burning Last-Ditch Catch — which can be had one turn
        later, from hand, WITH the fetch.

        OPEN (2026-07-30): the same reasoning is being asked of this filter's own trigger — whether an
        empty Bench should force a body unconditionally, or only when the Active is DOOMED. Not
        changed here, and deliberately: the filter guards a LOSS, and gating a loss-guard on a
        prediction trades a bounded cost for an unbounded one. See
        `docs/plans/deploy-decider-swap-review.md`.

        Silent unless it has something to force, so an empty Bench with no legal body on the menu
        leaves the order untouched."""
        if select.get("context") != _MAIN or int(board.my_bench or 0) > 0 or not self.stats:
            return order
        deploys = [i for i in order
                   if options[i].get("type") == _PLAY
                   and getattr(self.stats.get(self._option_card_id(obs, select, options[i])),
                               "is_pokemon", False)]
        if not deploys:
            return order
        seen = set(deploys)
        return deploys + [i for i in order if i not in seen]

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
            if (t == _EVOLVE and o.get("inPlayArea") != _ACTIVE      # FREE DEVELOPMENT, tier 0 already
                    and traces[i].score >= 0):                       # names it: "evolve a benched
                return 0                                             # Pokémon". A same-line bench evolve
                                                                     # nets to exactly 0.0 — the pre-evo is
                                                                     # pre-credited with the LINE's payoff
                                                                     # (`_line_payoff_stat`), so the deploy
                                                                     # delta CANCELS — and the `score <= 0`
                                                                     # gate below then starved it, ending
                                                                     # turns with bare 70 HP Staryu instead
                                                                     # of 330 HP Mega Starmie ex (#167's
                                                                     # six-frame sitting).
                                                                     # Scoped deliberately: `>= 0` only, so
                                                                     # an evolve the equation prices as a
                                                                     # WEAKENING (f35's -30.36 forfeited
                                                                     # Recon dig) still falls to tier 4; and
                                                                     # BENCHED only, leaving the Active's
                                                                     # KO-forfeit guard above untouched.
                                                                     # This is NOT the `>= 0` loosening
                                                                     # ADR-0070 rejected — that was the whole
                                                                     # sequencer; a zero-priced ATTACH still
                                                                     # drops to 4 below (the attach-anyway
                                                                     # blunder class, 82749168-21/82867148-34).
            if traces[i].score <= 0:                                 # only an endorsed action sequences early
                return 4                                             # — incl. an attach the decider prices at
                                                                     # ZERO: sequencing that ahead of End is
                                                                     # attach-anyway, the blunder class
                                                                     # ADR-0069 rejected an epsilon floor for
                                                                     # (measured: 82749168-21, 82867148-34)
            if t == _PLAY and _is_shuffle_refresh(i):                # hand-nuke: AFTER the Energy attach, so
                return 3                                             # held Energy placed before the shuffle
            if t == _PLAY and _is_supporter(i):                      # one-per-turn Supporter: after the
                return 1                                             # free Item digs, before the blind attach
            if t == _ATTACH or (t == _PLAY and _cost_discard(i)):    # blind/costly commitment: after free dev
                return 2                                             # THIS is `attach-energy-last` (ADR-0069
                                                                     # §7): the deleted −5 rung became this
                                                                     # deferral, so attach-late costs an attach
                                                                     # no SCORE — an irreversible commitment is
                                                                     # simply ORDERED after the draw/search that
                                                                     # would reveal a better target. Tier-aware
                                                                     # by construction: it stands DOWN against a
                                                                     # hand-shuffle finisher (tier 3 above), so
                                                                     # development → attach → hand-shuffle →
                                                                     # attack is structural, not a coincidence
                                                                     # of −5 vs −60. Score-invisible, which is
                                                                     # what let the desperation floor stop
                                                                     # depending on out-scoring that −5.
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
        attach_row = self._attach_decision(obs, select, board, option)   # priced ONCE: the score term
                                                           # and the planner's spend account read it
        evolve_row = self._evolve_decision(obs, board, ctx, option)      # the EVOLVE decider (ADR-0070)
        promote_row = self._promote_retreat_decision(obs, select, board, ctx, option)  # ADR-0100
        deploy_row = self._deploy_decision(obs, select, board, option)   # ADR-0086 (#197)
        tactical = (self._tactical(obs, board, option)
                    + self._snipe_tera_veto(ctx)      # card fact: a benched Tera takes NO damage
                    + self._refresh_swing_tactical(obs, board, ctx)
                    + self._hand_size_relief_tactical(obs, board, ctx)   # ADR-0102: the SURVIVAL leg
                    + self._grab_refresh_draw_tactical(board, ctx)       # of the same refresh, summed
                                                                         # ACROSS axes (cards vs damage)
                    + self._denial_play_tactical(obs, board, ctx)
                    + self._denial_target_tactical(obs, select, board, option)
                    + self._snipe_relevance_tactical(obs, select, board, option, ctx)
                    + self._snipe_brief_tiebreak(obs, select, board, option, ctx)
                    + self._snipe_ko_dominator(ctx)   # armed: the KO rung, as structure not a weight
                    + self._gust_tactical(obs, select, board, option)
                    + self._gust_target_tactical(obs, select, board, option)
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

    def _evolve_side(self, obs: dict, board: Board, raw: dict | None, card_id, *,
                     is_active: bool, bench=None) -> EvolveBody:
        """Read ONE body — the pre-evolution as it stands, or the hypothetical form it becomes —
        into the decider's damage-currency view (ADR-0070 §2).

        The hypothetical result carries the pre-evolution's attached Energy, because evolving keeps
        attached cards (rules.md §4). Only the ACTIVE can swing tonight, and the player going first
        cannot attack on turn 1 (rules.md §2), so `this_turn` is 0 elsewhere rather than optimistic."""
        from common.state_model import BodyView
        raw = raw or {}
        st = self._line_payoff_stat(card_id)
        payoff = float(getattr(st, "maxDamage", 0) or 0) if st is not None else 0.0
        this_turn = 0.0
        mine = self._state_model.mine if self._state_model is not None else None
        if mine is not None and is_active and board.turn > 1:
            this_turn = mine.best_reachable_damage(
                BodyView(raw, combat=self.combat, is_active=True))
        opp = self._opp_player(obs) or {}
        model = self._state_model
        # The SNAPSHOT owns both sides' body lists (ADR-0068 / ADR-0071 decision 7) — read them from
        # it so the harvest and the promotion gate cannot drift from the rest of the turn's reads.
        # `bench` is caller-supplied because the RESULT side reads a substituted bench, not the
        # board's; falling back to the real bench keeps a direct caller sound.
        my_bench = list(bench) if bench is not None else self._my_bench_raws(obs)
        opp_active = (model.theirs.active_raw if model is not None
                      else next((p for p in (opp.get("active") or []) if p), None))
        if model is None:
            # No snapshot — a board that never went through `_board()`. Both clocks then make NO
            # CLAIM, which is what `EvolveBody`'s own declared defaults mean (`arm=None` fail-closed,
            # `ko=_HORIZON` safe); reaching past the model to the oracle here is exactly the bypass
            # POC-T1 exists to close, and the alternative — a second, model-free clock path — is the
            # "answered three ways at three fidelities" disease ADR-0068 was written for.
            return EvolveBody(this_turn=float(this_turn), payoff_damage=payoff)
        return EvolveBody(
            this_turn=float(this_turn), payoff_damage=payoff,
            # MY armed clock, off the snapshot (POC-T1): `mine.turns_to_afford` IS this read with
            # `typed=True` baked in — the typed leg is not optional for my own bodies, because
            # over-crediting an off-colour Energy prices an unpayable line as armed (ADR-0070 §2).
            arm=model.mine.turns_to_afford(raw),
            # AREA-AT-DAMAGE-TIME (ADR-0070 §9): an evolve does not move the body, so the area it
            # occupies now IS the area the reply lands on — the one place the board read is sound.
            #
            # HARVEST READING (ADR-0071 decision 3): this is a RESCUE read — it asks what evolving
            # BUYS — so it declares UNAVOIDABLE. A benched knockout the opponent can simply redirect
            # onto another body in range denies nothing; crediting it inflates every bench rescue.
            # The bench snapshot is passed because a shared rider budget is unrepresentable from one
            # body alone, and `key_ids` is deck-DECLARED (CombatMath is deck-agnostic).
            #
            # The energy policy is the snapshot's THREADED one (the Read's `_incoming_budget`) — no
            # `charged=` here, because this consumer wants exactly the default the Read supplies.
            ko=model.theirs.turns_to_ko_me(raw,
                                           context=self._opp_attack_context,
                                           my_benched=not is_active,
                                           my_bench=my_bench, key_ids=self._harvest_key_ids(),
                                           reading=HARVEST_UNAVOIDABLE,
                                           opp_active=opp_active,
                                           switch_enabler=self._opp_switch_enabler()))

    def _my_bench_raws(self, obs: dict) -> list:
        """MY benched bodies' raw dicts — the Bench Harvest's input, from the SNAPSHOT when one is
        built (ADR-0068 keeps it lazy and pure, so the bench cannot shift under a memoized clock) and
        off the observation otherwise."""
        if self._state_model is not None:
            return list(self._state_model.mine.bench_raws)
        return [p for p in ((self._my_player(obs) or {}).get("bench") or []) if p]

    def _opp_switch_enabler(self) -> bool:
        """Can the opponent promote a benched attacker WITHOUT paying retreat — the enabler leg of
        the promotion gate (ADR-0071 decision 6).

        True unless a switch-class out is PROVABLY gone: `copies_left_odds` returns 0 for a card only
        when every copy in the matched Read's representative build is already accounted for on the
        board or in the discard, so `p > 0` is exactly ADR-0067's *not-provably-absent* test — and a
        copy sitting in their hidden HAND counts as unseen, which is the case that matters here.
        Only the `switch` tag: a `gust` card drags one of MY bodies up, it does not promote theirs.

        Same shape as `_opp_hand_strip_odds`, **opposite fail direction**. That one claims no
        exposure on a guess because a veto must not fire on one; this one claims FULL exposure,
        because it OPENS a threat gate — and the gate can only ever make a survival read less
        pessimistic. CONTEXT.md's Threat Clock: *"A survival read must never under-prepare; a prep
        read off by a turn is recoverable."* So no facade, no functions table, no confident Read, or
        any error all mean "assume they can switch"."""
        if self.opponent is None or not self.functions:
            return True
        try:
            odds = self.opponent.copies_left_odds()
            if not odds:                              # unrecognized opponent — cannot rule one out
                return True
            return any(p > 0 for cid, p in odds.items() if "switch" in self.functions.tags(cid))
        except Exception:
            return True

    def _harvest_key_ids(self) -> frozenset:
        """Card ids the OPPONENT prefers to knock out among equal-prize targets — my deck-declared
        attacker/line Roles (ADR-0071 decision 8). A sub-prize tie-break, never a magnitude: it
        cannot represent an opponent who forfeits a prize to kill an engine piece.

        `_ATTACKER_ROLES` rather than `_WINCON_ROLES` because the narrow pair is verified INERT on
        the Bench — the wincon itself is usually Active or in hand, and what sits benched is its
        base (dragapult_ex declares Dreepy `win_condition_base`, Munkidori `counter_mover`, and
        Dunsparce no Role at all). A deck declaring no Roles degrades to pure prize-max."""
        cached = getattr(self, "_harvest_key_id_cache", None)
        if cached is None:                            # deck Roles are static for the Pilot's life
            roles = getattr(self.strategy, "roles", None) or {}
            cached = frozenset(cid for cid, r in roles.items() if _ATTACKER_ROLES & set(r or ()))
            self._harvest_key_id_cache = cached
        return cached

    def _evolve_income_delta(self, raw: dict | None, card_id, *, is_active: bool) -> float:
        """Δ`readiness_p` an Ability's dig buys on this body — what the engine is actually worth
        (ADR-0070 §3), as odds rather than a tier.

        Zero on a body that ALREADY reaches, which is what makes a redundant engine worth exactly
        nothing with no saturation rule, and what collapses the hold the moment the body is armed.
        Otherwise the exact hypergeometric that the dig finds an enabler that WOULD pay — checked
        per candidate Energy type against a Budget built as though that card were in hand. Fail-
        CLOSED at 0.0 (ADR-0067): an untagged dig depth, or an enabler that still would not pay, is
        worth nothing rather than its bare draw odds."""
        from common.deck_odds import draw_hit_probability
        from common.state_model import BodyView
        depth = self.functions.dig_depth(card_id) if self.functions is not None else 0
        mine = self._state_model.mine if self._state_model is not None else None
        if depth <= 0 or mine is None or not raw:
            return 0.0
        if mine.reachable_attach(BodyView(raw, combat=self.combat, is_active=is_active), None):
            return 0.0
        pool = mine.deck_count
        best = 0.0
        for etype, count in (mine.deck_energy_counts or {}).items():
            # NAME the epistemic. `deck_energy_counts` holds `CountTriple`s, which refuse to be a
            # bare number precisely so a consumer cannot smuggle an estimate into sound math
            # (ADR-0068). A dig's odds ARE an estimate — ADR-0070 §3 calls income "an ODDS read,
            # never a tier" — so `expected` is the leg. `floor` is the leg for comparisons against a
            # COST, and while prizes are hidden it is 0 for almost every energy type: passing the
            # triple itself used to raise TypeError into `draw_hit_probability`'s "bad input -> 0.0"
            # guard, which silently zeroed §3, §7 and amendment B on EVERY board (#167).
            # Truncated, not rounded — the conservative direction for an endorser.
            copies = int(getattr(count, "expected", count) or 0)
            # DELIBERATE CombatMath bypass (POC-T1's documented list; `test_combat_bypass_census`):
            # a HYPOTHETICAL enabler Budget. Every argument is a model read, but the TARGET is a form
            # the board does not carry in this configuration, and the model's route builds a Budget
            # for a body it holds. Inventing a `MySide` method per hypothetical would move the
            # assembly, not remove it.
            enabler = self.combat.attach_budget(
                raw, mine.hand_ids, energy_attached=mine.energy_attached,
                supporter_played=mine.supporter_played,
                deck_energy_types=mine.deck_energy_types,
                hand_energy_types=frozenset(mine.hand_energy_types) | {etype},
                discard_energy_counts=mine.discard_energy_counts,
                target_benched=not is_active,
                more_prizes_than_opp=mine.more_prizes_than_opp)
            # ADR-0074 decision 6 (#175): this priced the DRAW honestly while leaving the enabler
            # Budget's deck-fetch leg a fail-open boolean, so a line resting on the last copy of a
            # colour read identically to one resting on three. Both are priced now; with an
            # anchored deck `pay_p` is exactly 1.0 and the reading is unchanged.
            pay_p = self.combat.reachable_attach_p(raw, None, budget=enabler,
                                                   p_by_type=mine.deck_energy_p)
            if pay_p > 0.0:
                best = max(best, pay_p * draw_hit_probability(copies, pool, depth))
        return best

    def _evolve_decision(self, obs: dict, board: Board, ctx, option: dict):
        """The EVOLVE DECIDER: price ONE evolve option (ADR-0070). Returns the per-option TERM row —
        the decider's legible working — or None to abstain: the kill-switch is OFF, or this is not
        an EVOLVE option.

        While the switch is OFF the `baseline_evolution` rungs decide alone, which is the swap
        protocol (ADR-0069 §8): both deciders stay alive until the corpus flips are user-ruled."""
        if not getattr(self, "evolve_value", False):
            return None
        if ctx.option_type != _EVOLVE or ctx.card_id is None:
            return None
        raw = self._evolve_body(obs, option) or {}
        body_cid = raw.get("id")
        me = self._my_player(obs)
        is_active = any(raw is p for p in (me.get("active") or []))
        bench = self._my_bench_raws(obs)
        body = self._evolve_side(obs, board, raw, body_cid, is_active=is_active, bench=bench)
        # The result inherits the pre-evolution's attached Energy (rules.md §4) and its slot, so the
        # hypothetical body differs from the real one ONLY in which card it is — exactly the
        # substitution the deploy delta is asking about.
        result_raw = dict(raw, id=ctx.card_id)
        rstat = self.stats.get(ctx.card_id) if self.stats else None
        if rstat is not None and getattr(rstat, "hp", None):
            result_raw["hp"] = rstat.hp
        # SUBSTITUTE the hypothetical into the bench rather than reading it alone. `result_raw` is a
        # COPY, so without this the Harvest would read B among its bench-mates and R in isolation —
        # and R would look fragile purely for being alone, which is not a fact about evolving. Both
        # sides must see the same bench with exactly one body swapped (ADR-0070's body-substituted
        # delta; ADR-0071 makes the bench read sensitive to the company a body keeps).
        result_bench = [result_raw if b is raw else b for b in bench]
        result = self._evolve_side(obs, board, result_raw, ctx.card_id, is_active=is_active,
                                   bench=result_bench)
        btags = self.functions.tags(body_cid) if (self.functions and body_cid is not None) else []
        inp = EvolveInputs(
            body=body, result=result,
            ready_gain=self._evolve_income_delta(result_raw, ctx.card_id, is_active=is_active),
            ready_loss=self._evolve_income_delta(raw, body_cid, is_active=is_active),
            # An Ability the engine still offers has NOT been used this turn — the menu is the fact,
            # never an assumption about whether the tier-0 sequencer already fired it (ADR-0070 §7).
            result_ability_now=self._ability_on_menu(obs, ctx.card_id),
            body_ability_on_menu=self._ability_on_menu(obs, body_cid),
            body_ability_oneshot=("self_shuffle" in btags),
            hold_turns=(body.arm or 0))
        val = evolve_value(inp)
        return {"deploy": val.deploy, "income_gain": val.income_gain,
                "income_loss": val.income_loss, "tactical": val.total,
                "body": {"this_turn": body.this_turn, "arm": body.arm, "ko": body.ko},
                "result": {"this_turn": result.this_turn, "arm": result.arm, "ko": result.ko}}

    def _ability_on_menu(self, obs: dict, card_id) -> bool:
        """Is this card's Ability still offered on the current menu — i.e. not yet used this turn?
        Abilities fire "per the ability's own text" (rules.md:91), and the engine simply stops
        offering a once-per-turn one after use, so the MENU is the fact. False without a menu.

        An ABILITY option names its body by **slot** (``area``/``index``) and carries no ``cardId``
        at all, so matching on one was False on every board ever built — silently killing
        ``body_ability_on_menu`` (§7's "this turn's use is forfeit" half of the split-horizon loss)
        and ``result_ability_now`` (which un-halves a gain that fires THIS turn). Resolve the slot
        and compare the card sitting in it (#167)."""
        if card_id is None:
            return False
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        for o in ((obs.get("select") or {}).get("option") or ()):
            if o.get("type") != _ABILITY:
                continue
            bodies = me.get(_ZONE.get(o.get("area"), "")) or []
            idx = o.get("index")
            if idx is None or not (0 <= idx < len(bodies)) or not bodies[idx]:
                continue
            if bodies[idx].get("id") == card_id:
                return True
        return False

    # ── the PROMOTE/RETREAT DECIDER (ADR-0100, #141) ───────────────────────────────────────────
    # ONE evaluator, three call sites (§9). Every read routes through the StateModel snapshot
    # (ADR-0068), so a memoized clock cannot shift under a hypothetical build, and the equation
    # itself stays pure over MEASUREMENTS — the Pilot fills `PromoteBody`/`RetreatSide`, exactly
    # ADR-0070's `EvolveBody` pattern.

    def _promote_body(self, obs: dict, board: Board, raw: dict | None, *, draws: int = 0,
                      bench_after=None) -> PromoteBody:
        """Read ONE body into the promote/retreat decider's damage-currency view (ADR-0100 §3-§7).

        The body is measured AS THE ACTIVE — that is where a promote candidate arrives and where the
        retreating Active currently stands — so its Attach Budget is built at ``target_benched=False``
        (#137 contract hazard 1: a Budget is PER-TARGET-BODY, and the same body budgeted as benched
        vs Active can differ).

        ``bench_after`` is the Bench this body would sit on if it went there — supplied only for the
        RETREATING Active, whose `preservation` needs the bench leg. Without it the bench clock is
        pinned to the Active one, so `preservation` reads a safe ZERO rather than a phantom credit on
        a body nobody is asking about."""
        from common.state_model import BodyView
        raw = raw or {}
        model = self._state_model
        mine = model.mine if model is not None else None
        view = BodyView(raw, combat=self.combat, is_active=True)
        # CARD RULE, not a heuristic: the player going FIRST cannot attack on turn 1
        # (`docs/rules.md` §2 L71-72, rulebook L152), so a body promoted then earns NO attack yield
        # and readying it buys nothing THIS turn. `_evolve_side` gates its own `this_turn` leg on the
        # same fact; without it the equation promises damage the rules forbid and endorses a turn-1
        # pivot on the strength of it (corpus 83007714-8).
        can_swing = board.turn > 1
        reach = float(mine.best_reachable_damage(view)) if (mine is not None and can_swing) else 0.0
        opp = self._opp_player(obs) or {}
        opp_active = (model.theirs.active_raw if model is not None
                      else next((p for p in (opp.get("active") or []) if p), None))
        # Both clocks go through the SNAPSHOT (POC-T1) — no `charged=`, so each takes the Read's
        # threaded `_incoming_budget`, which is exactly the policy the bypass used to pass by hand.
        clock = dict(context=self._opp_attack_context,
                     key_ids=self._harvest_key_ids(), opp_active=opp_active,
                     switch_enabler=self._opp_switch_enabler())
        if model is None:
            # No snapshot — a board that never went through `_board()`. Both clocks then make NO
            # CLAIM, which is what `PromoteBody`'s own declared default (`HORIZON` = safe) means; a
            # model-free second clock path here is the bypass POC-T1 exists to close.
            ko_active = ko_bench = _HORIZON
        else:
            ko_active = model.theirs.turns_to_ko_me(raw, my_benched=False,
                                                    my_bench=self._my_bench_raws(obs), **clock)
            if bench_after is None:
                ko_bench = ko_active                  # not asked — `preservation` reads 0, never a
            else:                                     # phantom rescue credit
                # HARVEST READING (ADR-0071 decision 3): this is a RESCUE read — it asks what
                # retreating BUYS — so it declares UNAVOIDABLE. A benched knockout the opponent can
                # simply redirect onto another body in range denies nothing; crediting it inflates
                # every bench rescue. The 35 bench-immune Tera bodies drop out of the harvest
                # entirely (`combat._harvest_items`, verified), so their bench leg reads the full
                # horizon.
                ko_bench = model.theirs.turns_to_ko_me(raw, my_benched=True,
                                                       my_bench=list(bench_after),
                                                       reading=HARVEST_UNAVOIDABLE, **clock)
        cid = raw.get("id")
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        return PromoteBody(
            reach=reach,
            # Gated on the same card rule: the race leg is still an ATTACK claim, and it REPLACES
            # `reach` rather than adding to it, so leaving it live would re-introduce the turn-1
            # damage the line above just refused.
            wall_progress=self._promote_wall_progress(obs, board, raw) if can_swing else None,
            accel_units=self._promote_accel_units(obs, board, raw) if can_swing else 0.0,
            closure=self._promote_closure(obs, raw, draws=draws if can_swing else 0),
            prizes=self._prize_value(raw),
            ko_active=ko_active, ko_bench=ko_bench,
            tempo_step=self._promote_tempo_step(raw),
            denies_items=("item_lock" in tags and self._opp_items_live()),
            opp_prizes_remaining=board.opp_prizes_remaining,
            takes_ko=self._promote_body_kos(obs, board, raw))

    def _promote_wall_progress(self, obs: dict, board: Board, raw: dict) -> float | None:
        """ADR-0040's per-turn wall progress (``hp / t_star``) for a body promoted into a STANDING
        WALL, or None when the wall does not stand and the body's reachable damage speaks for itself
        (ADR-0100 §3a: "vs a standing wall the single hit is fake value — price the SEQUENCE").

        Scoped to THIS body rather than `board.active_can_ko`, because the question is what B faces
        after arriving. Returns None the moment B can Knock the defender Out: the KO is then the
        tactical layer's (`_promote_ko_tactical`), and the residual must not re-price it.

        Deliberately `hp / t_star` ALONE, without `_race_attack_tactical`'s incidental-chip terms:
        that chip is a tie-break between the attacks of ONE body, and importing it here would let an
        attack-choice tie-break reorder a BODY comparison."""
        from common.strategy.objectives import race_values
        if not getattr(self, "objectives_race", False):
            return None
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        cid = (raw or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (hp and stat and stat.attacks):
            return None
        energy = len(raw.get("energies") or [])
        table = {}
        for aid in (stat.attacks or ()):
            if self.combat.attack_cost(aid) > energy:
                continue                              # not affordable on the Energy it carries
            dmg = self.predicted_damage(cid, aid, opp)
            if dmg <= 0:
                continue
            if dmg >= hp:
                return None                           # no wall — B takes the KO, the KO layer's turf
            table[aid] = (dmg, 0)                     # chip omitted deliberately (see docstring)
        vals = race_values(table, hp)
        if not vals:
            return None
        return hp / min(t_star for t_star, _chip in vals.values())

    def _promote_accel_units(self, obs: dict, board: Board, raw: dict) -> float:
        """Energy this body's accel rider would actually attach AND a recipient can actually USE —
        the `_recover_units` count (ADR-0100 §3b).

        `max` over the body's AFFORDABLE attacks, because it commits to one attack and picks the
        best: `max` WITHIN the axis, per ADR-0069 §1. Retreating INTO Cinderace must credit what
        attacking WITH Cinderace credits, which the shipped `_DIVIDEND = 5` under-paid ~45x."""
        cid = (raw or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (stat and stat.attacks):
            return 0.0
        energy = len(raw.get("energies") or [])
        best = 0.0
        for aid in (stat.attacks or ()):
            if self.combat.attack_cost(aid) <= energy:
                best = max(best, self._recover_units(aid, {}, board, obs))
        return best

    def _promote_closure(self, obs: dict, raw: dict, *, draws: int) -> float:
        """``max`` over attacks of ``damage(a) x [readiness_p(a | enabler) - readiness_p(a)]`` — the
        odds that THIS turn's dig readies an unready body, priced as probability x the damage it
        unlocks (ADR-0100 §5).

        `_evolve_income_delta` is the wiring this copies, so it inherits that path's fixes rather
        than re-earning them — notably `CountTriple.expected` rather than the raw triple, whose
        absence silently zeroed three of ADR-0070's terms on every board (#167).

        Three sub-rulings hold here. PER ATTACK, never ``attack_id=None`` (which asks the famine
        question across ALL attacks — right for a boolean, wrong for a magnitude, since the reachable
        attack may be the cheap one while the biggest damage belongs to the dear one). ONE Budget per
        target body, at this site's ``target_benched``. And the draw window is SITE-DEPENDENT: the
        caller passes ``draws=0`` at a forced promote, where no play window remains at all.

        Fail-CLOSED at 0.0 throughout (ADR-0067): no dig, no enabler that would still pay, or an
        already-ready body all earn nothing rather than bare draw odds. A body that ALREADY reaches
        has ``Δ = 0``, which is what stops closure double-crediting readiness."""
        from common.state_model import BodyView
        model = self._state_model
        mine = model.mine if model is not None else None
        cid = (raw or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if draws <= 0 or mine is None or not (raw and stat and stat.attacks):
            return 0.0
        view = BodyView(raw, combat=self.combat, is_active=True)
        pool = mine.deck_count
        best = 0.0
        for aid in (stat.attacks or ()):
            dmg = float(self.combat.attack_damage(aid) or 0)
            if dmg <= 0:
                continue
            base = mine.readiness_p(view, aid)
            if base >= 1.0:
                continue                              # already ready — no double credit
            for etype, count in (mine.deck_energy_counts or {}).items():
                # `expected` is the leg: a dig's odds ARE an estimate, and passing the CountTriple
                # itself raises into `draw_hit_probability`'s "bad input -> 0.0" guard (#167).
                copies = int(getattr(count, "expected", count) or 0)
                # DELIBERATE CombatMath bypass (POC-T1's documented list;
                # `test_combat_bypass_census`): a HYPOTHETICAL enabler Budget. Every argument is a
                # model read, but the TARGET is a form the board does not carry in this
                # configuration, and the model's route builds a Budget for a body it holds.
                # Inventing a `MySide` method per hypothetical would move the assembly, not remove it.
                enabler = self.combat.attach_budget(
                    raw, mine.hand_ids, energy_attached=mine.energy_attached,
                    supporter_played=mine.supporter_played,
                    deck_energy_types=mine.deck_energy_types,
                    hand_energy_types=frozenset(mine.hand_energy_types) | {etype},
                    discard_energy_counts=mine.discard_energy_counts,
                    target_benched=False,             # it is being promoted INTO the Active Spot
                    more_prizes_than_opp=mine.more_prizes_than_opp)
                p = mine.readiness_p(view, aid, enabler_budget=enabler, copies=copies,
                                     pool=pool, draws=draws)
                best = max(best, dmg * max(0.0, p - base))
        return best

    def _promote_tempo_step(self, raw: dict) -> float:
        """``incoming(t=2) - incoming(t=1)`` against the body that would be my Active — ONE
        development step's threat growth off the live Threat-Clock curve (ADR-0100 §6).

        The curve's own docstring notes that `t` moves only the ENERGY budget, evolution reach being
        maximal at `t=1`, so the delta IS one step. 0.0 without a snapshot (fail-closed)."""
        model = self._state_model
        if model is None or not raw:
            return 0.0
        ctx = self._opp_attack_context
        return float(max(0, model.theirs.incoming(raw, 2, context=ctx)
                         - model.theirs.incoming(raw, 1, context=ctx)))

    def _opp_items_live(self) -> bool:
        """Does the opponent PROVABLY still hold live Item copies — the gate on `tempo_denied`
        (ADR-0100 §6).

        The shape of `_opp_switch_enabler`, but failing **CLOSED**: no facade, no functions table, no
        matched Read or any error all mean NO CREDIT. That is the opposite fail direction from a
        survival read, and it is the right one here because this term ENDORSES a play, and ADR-0067's
        rule is fail-closed on yield. An item lock that denies nothing must not pay."""
        if self.opponent is None or not self.stats:
            return False
        try:
            odds = self.opponent.copies_left_odds()
            if not odds:                              # unrecognised opponent — claim nothing
                return False
            return any(p > 0 for cid, p in odds.items()
                       if (st := self.stats.get(cid)) is not None and st.is_item)
        except Exception:
            return False

    def _promote_body_kos(self, obs: dict, board: Board, raw: dict) -> bool:
        """Does this body take a Knock Out on arrival — ruling 5's provable-KO stand-down for the
        fatal step (trading while ahead on the exchange is fine). The KO's own MAGNITUDE is not
        priced here; that is `_promote_ko_tactical`'s, summed on the same option (§1, §11)."""
        opp = self._opp_active(obs)
        if not (opp and opp.get("hp") and raw):
            return False
        return self._best_affordable_ko_value(
            obs, board, opp, raw.get("id"), len(raw.get("energies") or []), body=raw) > 0

    def _turn_dig_depth(self, obs: dict) -> int:
        """The cards this turn's REMAINING dig still puts within reach — the closure term's draw
        window (ADR-0100 §5).

        Summed over my in-play bodies whose draw/dig Ability is STILL ON THE MENU, because the menu
        is the fact about whether a use is left (the same argument ADR-0070 §7 makes for
        `body_ability_on_menu`). 0 when nothing is tagged or nothing is offered — fail-closed, and
        automatically 0 at a forced promote, where the menu is a TO_ACTIVE select and no play window
        remains at all (`docs/rulebook.txt` L173-176/L183)."""
        if self.functions is None:
            return 0
        me = self._my_player(obs) or {}
        bodies = [p for p in ((me.get("active") or []) + (me.get("bench") or [])) if p]
        return sum(self.functions.dig_depth(b.get("id")) for b in bodies
                   if b.get("id") is not None and self._ability_on_menu(obs, b.get("id")))

    def _retreat_discard_choice(self, ma: dict, n: int) -> dict:
        """``ma`` as it stands after a retreat discards ``n`` Energy — the GREEDY cheapest-to-lose
        typed choice (ADR-0100 §8).

        A Retreat Cost slot is COLOURLESS (`docs/rules.md` §89, rulebook.txt L142: "discard 1 Energy
        for each ⟨C⟩"), so which Energy goes is genuinely ours to pick — and the engine poses a
        `DISCARD_ENERGY` select over EVERY attached Energy to ask (verified in
        `cgpy/turn.py:_pose_retreat_energy`). Competent play, not optimism: it sheds the unit whose
        removal costs the least Build Standing first, which is off-type waste before matched slots."""
        energies = list(ma.get("energies") or [])
        for _ in range(min(max(0, int(n)), len(energies))):
            keep = max(range(len(energies)),
                       key=lambda i: self._build_standing(
                           dict(ma, energies=energies[:i] + energies[i + 1:])))
            energies.pop(keep)
        return dict(ma, energies=energies)

    def _retreat_cost_legs(self, obs: dict, card_worth: float = 0.0) -> dict:
        """What LEAVING the Active Spot costs (ADR-0100 §8) — the build the discard destroys, plus
        ADR-0069 §5c's resource premium.

        Computed ONCE per menu rather than per destination, because §9's claim is precisely that
        this is CONSTANT across destinations: "`preservation(A)` and `retreat_cost(A)` are CONSTANT
        across destinations, so they belong only on the whether-site's retreat option." Expressing
        that in the code's shape (rather than recomputing an identical answer per bench body) is what
        makes the claim checkable, and it keeps the greedy discard search off the inner loop.

        ``card_worth`` prices a switch-class ITEM instead of an Energy discard (§11's rider): a
        Switch costs a CARD and no Energy, so it destroys no build at all."""
        ma = self._my_active(obs)
        if not ma:
            return {}
        if card_worth > 0.0:                          # a Switch Item pays a card, never a build
            return {"card_worth": float(card_worth)}
        after = self._retreat_discard_choice(ma, self._effective_retreat_cost(obs, ma))
        discarded = list(ma.get("energies") or [])
        for eid in (after.get("energies") or []):     # the multiset difference — what actually goes
            if eid in discarded:
                discarded.remove(eid)
        # ADR-0069 §5c's resource premium: charged on worth ABOVE a reusable Basic, so a plain Basic
        # pays nothing and only a one-shot is nudged. Sub-band — it orders equals.
        premium = _ATTACH_RESOURCE_TIEBREAK * sum(
            max(0.0, self._role_value(eid) - ENERGY_TIER) for eid in discarded)
        return {"build_before": self._build_standing(ma),
                "build_after": self._build_standing(after), "resource_premium": premium}

    def _retreat_side(self, obs: dict, board: Board, *, promoted_raw, cost: dict) -> RetreatSide:
        """The A-side of a voluntary swap, for ONE destination (ADR-0100 §4 preservation, §8 cost).

        Only the PRESERVATION leg is per-destination, and only because the Bench that A lands on
        depends on which body left it — reading A among its CURRENT bench-mates would mis-price the
        Harvest exactly as ADR-0070 warned for the evolve result. The cost legs arrive precomputed
        from :meth:`_retreat_cost_legs`."""
        ma = self._my_active(obs)
        bench_after = [b for b in self._my_bench_raws(obs) if b is not promoted_raw] + [ma]
        return RetreatSide(body=self._promote_body(obs, board, ma, draws=0,
                                                   bench_after=bench_after), **cost)

    def _promote_retreat_decision(self, obs: dict, select: dict, board: Board, ctx, option: dict):
        """The PROMOTE/RETREAT DECIDER: price ONE option (ADR-0100). Returns the per-option TERM row
        — the decider's legible working — or None to abstain: the kill-switch is OFF, or this option
        is neither a body PICK nor a whether-to-retreat action.

        The three sites §9 names, all through ONE evaluator:

        * **pick** (a TO_ACTIVE forced promote or a SWITCH retreat destination) — `promote_value(B)`
          with NO A-side terms, because `preservation`/`retreat_cost` are constant across
          destinations and could change no ordering there.
        * **whether** (a native RETREAT at MAIN, or a switch-class Item PLAY) — the best destination's
          `promote_value(B)` PLUS `preservation(A) - retreat_cost(A)`.
        * **forced promote** — the pick site with the draw window at zero (§5).

        That both sites run this one evaluator is what makes the shipped divergence — retreat BECAUSE
        Cinderace is worth promoting, then promote Budew — structurally impossible rather than
        merely fixed."""
        if not getattr(self, "promote_retreat_value", False):
            return None
        sctx, otype = ctx.select_context, ctx.option_type
        my_index = (obs.get("current") or {}).get("yourIndex", 0)
        if sctx in (_TO_ACTIVE, _SWITCH):
            if option.get("playerIndex") not in (None, my_index):
                return None                           # a Boss's-gust target — the gust equation's turf
            raw = self._option_pokemon(obs, select, option)
            if not raw:
                return None
            # §5: the replacement Active is chosen right after the KO'ing attack resolves or at
            # Checkup, and attacking ends the turn — so at a FORCED promote no play window remains.
            draws = 0 if sctx == _TO_ACTIVE else self._turn_dig_depth(obs)
            body = self._promote_body(obs, board, raw, draws=draws)
            return self._promote_row(promote_value(PromoteRetreatInputs(body=body)), site="pick")
        if sctx != _MAIN:
            return None
        is_switch_item = (otype == _PLAY and "switch" in (ctx.tags or []))
        if otype != _RETREAT and not is_switch_item:
            return None
        # §11's rider: a switch-class ITEM is priced by the SAME equation as a manual retreat, with
        # the card's Worth as the cost — the charter names "SWITCH-class retreats", and two of the
        # deleted rungs fired on a `_PLAY` + `switch` option that the whether-site never saw.
        worth = self._role_value(ctx.card_id) if is_switch_item else 0.0
        if self._my_active(obs) is None:
            return None                               # no readable Active — make no claim
        cost = self._retreat_cost_legs(obs, worth)    # CONSTANT across destinations (§9)
        draws = self._turn_dig_depth(obs)
        best = None
        for raw in self._my_bench_raws(obs):
            if not raw or raw.get("id") is None:
                continue
            val = promote_value(PromoteRetreatInputs(
                body=self._promote_body(obs, board, raw, draws=draws),
                retreat=self._retreat_side(obs, board, promoted_raw=raw, cost=cost)))
            if best is None or val.total > best.total:
                best = val
        return None if best is None else self._promote_row(best, site="whether")

    @staticmethod
    def _promote_row(val, *, site: str) -> dict:
        """The decider's per-option working (ADR-0008/0019 full working), rounded for the wire. This
        DECIDES, so — like the attach and evolve rows — there is no agreement bit: one emission path,
        one truth, and the substrate #146/#148 consume."""
        return {"site": site, "tactical": val.total,
                "my_yield": round(val.my_yield, 2), "closure": round(val.closure, 2),
                "exposure": round(val.exposure, 2), "tempo_denied": round(val.tempo_denied, 2),
                "fatal": round(val.fatal, 2), "preservation": round(val.preservation, 2),
                "retreat_cost": round(val.retreat_cost, 2), "total": round(val.total, 2)}

    def _promote_ko_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for the body PICK that takes the prize — the pick site's own Knock-Out
        layer (ADR-0100 §11), mirroring `_retreat_to_lethal_tactical`.

        Rulings 4/5 defer wins to the Lethal Solver and provable KOs to the Turn Planner, but BOTH are
        MAIN-only (`planner.py:283`; `_retreat_to_lethal_tactical` fires only on a `_RETREAT` option).
        At a TO_ACTIVE/SWITCH body pick those owners DO NOT EXIST, so a strictly sub-lethal equation
        would promote the body that hits hardest over the body that takes the prize.

        Load-bearing at the two selects for DIFFERENT reasons:

        * **SWITCH — REALISATION, not a new decision.** The KO comparison already happened at MAIN,
          but `_retreat_to_lethal_tactical` takes a `max` over the bench and returns only a NUMBER —
          it never says WHICH body won. A sub-lethal pick could therefore retreat *because* Mega
          Lucario ex takes the Knock Out and then promote Cinderace. Both sites calling
          `best_affordable_ko_value` makes the pick land on the body that justified the retreat:
          consistency by construction, §9's argument applied to the KO layer.
        * **TO_ACTIVE — a fresh claim.** Their attack Knocked our Active out and attacking ends the
          turn (`docs/rules.md` §5), so per `docs/rulebook.txt` L176 we promote, their turn ends, and
          OUR turn starts with only the Checkup between — the promoted body swings against
          essentially the same board.

        Decision 1's split is preserved exactly: the KO DELTA is tactical, the sub-lethal residual is
        the equation's, and they SUM on the option. No new constant.

        Rides the SAME `promote_retreat_value` kill-switch as the equation, because it is half of one
        replacement: it takes over from `promote-the-ko-attacker` (+45) and
        `promote-the-accelerator-for-the-ko` (+50), both DELETED. Gating it separately would make OFF
        an incoherent state — a body pick with a KO layer but no residual, which is neither the old
        agent nor the new one. (This supersedes the `promote_ko_aware` kill-switch for SCORING; that
        flag now only feeds `board.ko_promote_slot`'s Context reads.)"""
        if not getattr(self, "promote_retreat_value", False):
            return 0.0
        if select.get("context") not in (_TO_ACTIVE, _SWITCH):
            return 0.0
        my_index = (obs.get("current") or {}).get("yourIndex", 0)
        if option.get("playerIndex") not in (None, my_index):
            return 0.0                                # a gust target (opponent body), not my pick
        opp = self._opp_active(obs)
        if not (opp and opp.get("hp")):
            return 0.0
        raw = self._option_pokemon(obs, select, option)
        if not raw:
            return 0.0
        return self._best_affordable_ko_value(
            obs, board, opp, raw.get("id"), len(raw.get("energies") or []), body=raw)

    def _my_active(self, obs: dict) -> dict | None:
        """My Active Pokémon dict (mirror of `_opp_active`)."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        if not (0 <= yi < len(players)) or players[yi] is None:
            return None
        actives = players[yi].get("active") or []
        return actives[0] if actives and actives[0] else None

    def _effective_retreat_cost(self, obs: dict, ma: dict | None) -> int:
        """The Active's Retreat Cost in Energy — the count of Energy a retreat actually discards, and
        so (ADR-0100 §8) the size of the build a retreat destroys. READ-ONLY (mirrors the cost
        arithmetic of `_can_retreat` without its affordability verdict); 0 on an unknown stat.

        Three grant shapes, all fail-CLOSED — an unreadable or unmodelled grant charges the PRINTED
        cost, erring toward not retreating and never toward the retreat-happy pathology:

        1. a flat attached-Tool reduction (Air Balloon −2, `retreatReduction`);
        2. a CONDITIONAL attached Tool (`retreatFreeAtHp` — Rescue Board zeroes the cost outright once
           the holder is down to 30 HP or less);
        3. a BOARD-LEVEL Ability on ANOTHER of my bodies (`retreatFreeGrant` — Latias ex's Skyliner
           gives every Basic of mine no Retreat Cost, and `slowking` runs it).

        Shape 3 is why this now takes ``obs``: the granting body is not the body retreating, so no
        per-card read could ever see it. Under the old flat `x ENERGY_TIER` pricing a missed
        reduction cost 8 points; under the convex build delta, over-charging one Energy on a 3-slot
        attacker is `(3/3)^2 - (2/3)^2 = 5/9 x maxDamage` ~ **117 damage of phantom cost**, and it
        would be systematic on an archetype built around free-retreat pivoting."""
        if not ma or not self.stats:
            return 0
        stat = self.stats.get(ma.get("id"))
        if stat is None:
            return 0
        cost = getattr(stat, "retreatCost", 0)
        hp = ma.get("hp") or 0
        for tool in (ma.get("tools") or []):
            tid = tool.get("id") if isinstance(tool, dict) else tool
            tstat = self.stats.get(tid) if tid is not None else None
            if tstat is None:
                continue
            free_at = getattr(tstat, "retreatFreeAtHp", 0)
            if free_at and hp and hp <= free_at:
                return 0                                  # Rescue Board on a damaged holder
            cost -= getattr(tstat, "retreatReduction", 0)
        if cost > 0 and self._retreat_free_granted(obs, ma, stat):
            return 0
        return max(0, cost)

    def _retreat_free_granted(self, obs: dict, ma: dict, stat) -> bool:
        """Does a BOARD-LEVEL Ability of mine give ``ma`` no Retreat Cost (ADR-0100 §8)?

        The predicate travels WITH the grant (`CardStat.retreatFreeGrant`), so adding a card adds a
        parse and a predicate rather than a call-site special case. Unknown predicate → False, which
        is the fail-closed direction: we charge the printed cost."""
        me = self._my_player(obs) or {}
        bodies = [p for p in ((me.get("active") or []) + (me.get("bench") or [])) if p]
        for body in bodies:
            gstat = self.stats.get(body.get("id")) if body.get("id") is not None else None
            grant = getattr(gstat, "retreatFreeGrant", None) if gstat is not None else None
            if grant == "basic" and (getattr(stat, "stage", None) or "").lower() == "basic":
                return True
            if grant == "metal_attached" and self._attached_type_counts(ma).get(_METAL):
                return True
        return False

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
        dmg_ctx = self._my_damage_context(obs)
        dmg = self.predicted_damage(self._my_active_id(obs), attack_id, opp, context=dmg_ctx)
        eff = _EFFICIENCY * self._attack_cost(attack_id, 0)   # cheaper of equal outcomes wins
        recover = self._recover_units(attack_id, dmg_ctx, board, obs)  # usable re-attachable fuel (Aura Jab)
        lock_cost = self._lock_sequence_cost(attack_id, board)    # damage the lock actually forfeits
        snipe_ko = self._snipe_ko_prizes(board.opp_bench, self.combat.rider_snipe(attack_id))
        spread_ko = self._spread_ko_prizes(board.opp_bench, self.combat.rider_spread(attack_id))
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
            return (race - eff + ENERGY_RECOVER * recover  # value — price the SEQUENCE (chip included,
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
        return (dmg - eff + ENERGY_RECOVER * recover - lock_cost
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
        # DELIBERATE CombatMath bypass (POC-T1's documented list): card knowledge, constant all
        # game. `PrizeRace`'s own docstring keeps per-body prize YIELD on the oracle and only the
        # RACE on the model (ADR-0052) — and every caller of this adapter passes a SYNTHETIC
        # `{"id": cid}`, which is a card question, not a board one.
        return self.combat.prize_value(poke)

    def _attached_type_counts(self, target: dict) -> dict:
        # DELIBERATE CombatMath bypass (POC-T1's documented list): pure typed arithmetic over a
        # body's own `energies`, with no other board input — so two readers cannot disagree, which
        # is the drift this track's census exists to prevent. Called with synthetic bodies.
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
        recoil = self.combat.rider_recoil(attack_id)
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
        ctx = self._my_damage_context(obs)
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
                                  promote_bench_names=None, attack_p=None, budget=None) -> float:
        """The best KO value a hypothetical attacker reaches vs the opp Active — the KO oracle's
        ``best_affordable_ko_value`` (ADR-0052), handed the Board's ``opp_bench`` snapshot for the
        rider tiebreaks. Signature kept for the planner/tactical call sites (``obs`` vestigial).

        ``budget`` (ADR-0079, #177) hands the oracle the typed **Attach Budget** instead of a wild
        count; ``energy`` is then ignored. ``attack_p`` (ADR-0074, #175) weights a ranked
        consumer's claim. Refuse-then-weight: they are separate concerns on separate parameters."""
        return self.combat.best_affordable_ko_value(
            opp, attacker_id, energy, opp_bench=board.opp_bench, bound=bound, body=body,
            extra_type=extra_type, extra_units=extra_units,
            boost_amount=boost_amount, boost_type=boost_type,
            promote_bench_names=promote_bench_names, attack_p=attack_p, budget=budget)

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
        ctx = self._my_damage_context(obs)
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

    # `_rider_snipe` / `_rider_spread` / `_rider_recoil` were DELETED by POC-T1 (Issue #260) and
    # every caller re-pointed at `self.combat.rider_*`. They were byte-identical copies of the
    # oracle's own accessors — an ADR-0052 consolidation leftover, and the shape
    # `docs/plans/TODO-dead-accessor-cleanup.md` §2 rules on: snipe and spread got away with the
    # duplication because both copies had callers, and recoil is where it became visible, because
    # the Pilot's copy won and `CombatMath.rider_recoil` got nothing. Deleting the oracle's method
    # (the literal reading of the T1 scope line) would have removed the EVIDENCE of the duplication
    # while leaving the duplication; card knowledge belongs on the oracle, so the copies went instead.

    def _refresh_swing_tactical(self, obs: dict, board: Board, ctx) -> float:
        """Closed-form value of a shuffle-refresh (ADR-0060, SHED graded by ADR-0065). Judge/Harlequin
        are symmetric REFILLS, not strips: each player shuffles their hand away and redraws to the
        card's printed count, so the play is fully described by how many cards move, in which direction
        (strategy/refresh.py):

          MY hand      CYCLE                                 flat, speculative, guard-cancellable
                     - set_keep_v2(whole hand)               the graded SHED — what I lose
          THEIR hand + OPPONENT_HAND_STRIP * max(-opp_net,0) cards their shuffle takes  (certain)
                     + OPPONENT_HAND_FRESH * f               …of which they drew last turn
                     - OPPONENT_HAND_GIFT  * max(opp_net,0)  cards their redraw hands them (certain)

        Both opponent-side rates read the ONE signed `opp_net`, so STRIP and GIFT are a single leg
        split by sign and can never both fire; a one-sided refresh (Lillie's/Lacey shuffle only MY
        hand) zeroes `opp_net` and leaves `CYCLE − SHED` alone.

        The card's own printed draw count is the break-even. **The SHED side is graded** (WP7): it was
        a flat ``_REFRESH_SHED × cards-lost``, propped up by the hand-QUALITY guards (`hold-wincon` /
        `hold-line-piece` / `hold-irreplaceable-tool`) — a wincon and a dreg cost the same to shuffle.
        It became ``Σ keep_cost`` over the actual hand, and is now (ADR-0101) the **v2 assignment set
        marginal** `_refresh_shed_keepcost` — one price for the JOINT shed, so duplicate plan pieces
        cost what the pair is worth rather than twice what one is. A live hand of wincons/engines is
        expensive to shuffle, a dead hand nearly free, and the guards fold in as one currency.

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
                + _REFRESH_OPPONENT_HAND_STRIP * stripped
                + (_REFRESH_OPPONENT_HAND_FRESH * fresh if stripped > 0 else 0.0)
                - _REFRESH_OPPONENT_HAND_GIFT * max(opp_net, 0.0))

    def _hand_size_relief_tactical(self, obs: dict, board: Board, ctx) -> float:
        """Value of playing a hand REFRESH against an attacker whose damage scales off a hand — the
        survival it buys me, or hands them (**ADR-0102**, promoting the hand-disruption grill's
        design B).

            relief = prize_to_damage( survival_value( turns_to_ko_me(the hands the card leaves)
                                                      − turns_to_ko_me(the hands as they stand) ) )

        Alakazam's Powerful Hand (MEG 743, *"2 damage counters … for each card in your hand"* = 20 per
        card in THEIR hand, aimed at MY Active) is INCOMING damage, so shrinking their hand is
        self-preservation, not opponent-worth. The whole term is therefore the same clock every other
        survival read speaks: ask `turns_to_ko_me` twice, once at the hands as they stand and once at
        the hands the card leaves both players on, and price the DIFFERENCE in the shared sub-prize
        survival currency (`needs.survival_value`), crossing to the damage scale on the derived
        `PRIZE_DAMAGE_RATE`. Nothing new is invented — the counterfactual is two keys of the Damage
        Formula's own opponent-as-attacker context, which is where every hand scaler already reads
        its count, and the two redraw numbers are `strategy/refresh.py`'s own branch facts.

        **BOTH hands, because the card moves both and the pool scales off both.** `atk_hand` is THEIR
        hand (Powerful Hand) and moves only for a symmetric refresh — the `opponent_shuffles`
        discriminator, exactly as `net_change` applies it. `def_hand` is MY hand, and it moves for
        every refresh in the table including the self-only ones: **Mega Froslass ex** (861, Resentful
        Refrain, *"50 damage for each card in your opponent's hand"*) and **Chandelure** (98, Mind
        Ruler, 30/card) are in the set, so holding ten cards in front of a Froslass is 500 incoming
        and a Lillie's down to six is the survival play. Pricing only their hand would have left the
        bigger of the two scalers unmodelled while claiming to price "the hand-size damage swing".

        **Marginal vs my own KO** (grill ruling 1a), which is why it replaces the flat rungs rather
        than joining them: 80 damage denied is worth ~0 when my Active survives either way (both
        clocks read the same, the difference is 0) and a great deal when it moves the clock. The flat
        +25 could not tell those apart, and its three failures all close here:

        * **Undervaluation** — `_REFRESH_OPPONENT_HAND_STRIP` x 4/card is a fifth of Powerful Hand's
          real 20/card; the clock reads the damage itself.
        * **The sign hole** — at their hand 1 the old terms netted ≈ +1, so the Pilot Judged an EMPTY
          Alakazam hand and refilled it from 20 to 80 damage against its own Active (ml 85709280 f111,
          *"an enormous blunder"*). Here the refill SHORTENS my clock, the shift is negative, and the
          term declines. Sign-correct by construction, not by a gate.
        * **The benched over-fire** — the retired rung fired on `opp_has_hand_size_attacker` anywhere
          in play, paying the same +25 for an Alakazam line that cannot attack for three turns. The
          accumulating clock prices a benched threat at its real distance, through the same promotion
          gate (`opp_active` + `switch_enabler`) every other threat read uses.

        There is deliberately **no card-fact gate** in front of the two clock reads. A guard asking
        "does any line here scale off a hand" would be a second enumeration of the Damage Formula's
        scaler families, free to disagree with the oracle it guards — the drift `card_level_damage`
        was extracted to end. The clock is the authority: on a board where nothing scales off a hand
        the two reads are equal and the term is 0, which is the same answer a guard would give and
        cannot fall out of step with the scaler table.

        **No Lever-A multiplier rides on top, and none is smuggled in either.** Stated precisely,
        because the loose version of this sentence is wrong: the Read-gated half of the deleted
        `disrupt-when-unfavored` (+18) is **not** re-expressed here — this term reads neither
        `favorability` nor `matchup_coverage`, so nothing "returns". It is SUBSTITUTED. ADR-0078
        decision 6 ruled that `_DENIAL_UNFAVORED` and `needs.phase_scale` say the same thing from
        different inputs, so a path carrying both multiplies one race read by itself, and named
        `phase_scale` the derived successor. Deny kept the Read-gated scaler only because it reads
        `phase_scale` on no surface (ADR-0080 decision 3, which says so in as many words); this term
        reads it directly, as its survival currency's own scaler — so the discipline the +18's
        posture half was owed ("posture SCALES the oracle, it is never re-added as a flat") is
        honoured by a scaler that was going to be here anyway, and is strictly the better instrument:
        board-derived, [0,1]-bounded, live without matchup coverage.

        **Fail direction.** Neither hand's size beyond the redraw count is knowable, so both clocks
        read hands that are CONSTANT over the horizon: the honest deterministic quantity, never a
        speculative refill projection.

        The energy policy is `UNCHARGED` — the DOOM policy, named rather than inherited, because this
        term is the graded generalisation of `_active_doomed` and must fail the way doom fails. The
        difference from the CEILING (`charged=None`) that the opponent-target rows take is not
        cosmetic: the ceiling reads an unresolvable attack cost through `can_pay_cheapest`, which is
        fail-CLOSED, and `_affords` says outright that pointed at the opponent this means *"I cannot
        tell what this costs, so assume it cannot reach me"* — the one thing a survival read must
        never say. Under `UNCHARGED` an unresolvable cost counts as payable and the current form is
        charged no affordability at all (the hidden-Ignition lesson). Threading the Read's own budget
        instead would let a matched Brief quietly relax a survival read (ADR-0064 keeps that
        conservatism per-consumer; the `doom-ceiling-fail-direction` whitelist entry is the policy).

        0 unless this is the PLAY of a refresh `strategy/refresh.py` knows, with a live Active to
        survive on and a counterfactual that actually moves a hand."""
        from common import needs
        from common.currency import prize_to_damage
        if ctx.option_type != _PLAY or not self.stats:
            return 0.0
        branches = refresh_branches(ctx.card_id, board.my_prizes_remaining,
                                    board.opp_prizes_remaining)
        model, now_ctx = self._state_model, self._opp_attack_context
        if branches is None or model is None or not now_ctx:
            return 0.0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        ma = next((p for p in ((me or {}).get("active") or []) if p), None)
        if not (ma and opp):
            return 0.0
        # The two redraw counts, averaged over the card's coin branches exactly as the swing oracle
        # averages its own (Harlequin's 3/5 split is EV 4, the same number `net_change` prices). Their
        # hand moves only if the card shuffles it — the `opponent_shuffles` discriminator, applied
        # here for the same reason `net_change` applies it: a self-only refresh leaves them untouched.
        after = dict(now_ctx, def_hand=sum(m for m, _o in branches) / len(branches))
        if opponent_shuffles(ctx.card_id):
            after["atk_hand"] = sum(o for _m, o in branches) / len(branches)
        if after == now_ctx:
            return 0.0                      # the card moves no hand on this board: nothing to price
        clock = dict(charged=UNCHARGED,
                     opp_active=next((p for p in (opp.get("active") or []) if p), None),
                     switch_enabler=self._opp_switch_enabler())
        shift = (model.theirs.turns_to_ko_me(ma, context=after, **clock)
                 - model.theirs.turns_to_ko_me(ma, context=now_ctx, **clock))
        if not shift:
            return 0.0
        phase = needs.phase_scale(race_ahead=getattr(board, "race_ahead", None),
                                  opp_prizes_remaining=board.opp_prizes_remaining)
        return prize_to_damage(needs.survival_value(survival_shift=shift, phase=phase))

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
        """The graded SHED — the **v2 whole-hand assignment marginal** (ADR-0101, Issue #261 item 2b):
        what shuffling my hand away on a refresh costs = ``needs.set_keep_v2`` over EVERY held row,
        i.e. ``V(hand) − V(∅)`` under the exact bitmask-DP assignment of held cards to the board's
        resolved NEEDS (`_resolve_needs`), with each slot discounted by the closure's odds of
        re-supplying it inside the refresh's own draw window (`_refresh_slot_resupply`). One row per
        held copy except the played refresh itself (excluded once: it is discarded, not shuffled; a
        second held copy still charges — `_needs_hand_rows`).

        **Sets, not sums — the swap's whole point.** v1 was ``Σ keep_cost`` over the copies
        (`planner._hand_keep`, still the gamble keep-floor's own summation): it charged each duplicate
        wincon separately and OVER-priced the shed, so a refresh looked too costly on exactly the
        hands that most want refreshing. The assignment prices the pair as ONE covered line plus its
        succession slot, and a card covering nothing the board needs costs 0 however dear its catalog
        worth. The set marginal is the honest quantity here because a refresh sheds the hand
        JOINTLY — v1's per-copy sum was never the price of the move it was pricing.

        0 when the hand resolves to no rows or the card is not a known refresh — the CYCLE credit
        alone stands, matching the retired flat term's floor.

        **One floor moved, and in the safe direction.** v1 returned 0 when the deck bookkeeping was
        unresolved (no anchor and no usable unseen composition); v2 still prices the hand, because
        `_refresh_slot_resupply` returns all-zero resupply in that case and the assignment then
        charges the UNDISCOUNTED set marginal. So an unresolved tracker now makes the shed dearer
        rather than free — it over-prices the shuffle instead of under-pricing it, which is the
        fail direction this site has taken throughout (the WP-N6 sweep's "safe side")."""
        from common import needs
        from common.strategy.refresh import refresh_branches
        branches = refresh_branches(ctx.card_id, board.my_prizes_remaining, board.opp_prizes_remaining)
        if not branches:
            return 0.0
        draws = max(my_draw for my_draw, _opp in branches)
        rows = self._needs_hand_rows(obs, board, exclude_cid=ctx.card_id)
        if not rows:
            return 0.0
        slots, elig = self._resolve_needs(obs, board, rows)
        resupply = self._refresh_slot_resupply(slots, elig, rows, obs, board, draws)
        return needs.set_keep_v2(slots, elig, resupply, range(len(rows)))

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
        slot. Returns ``(keep_v2 per row, eq2_pick as OPTION indices)``.

        **This DECIDES** (`needs_keep_value`, armed ON 2026-07-20 by ADR-0065 WP-N4): the forced
        discard's pick IS `eq2_pick` — see `_discard_needs_pick`, the consumer. The line here read
        "SHADOW-ONLY (Round 6): nothing here decides" for eleven days after the swap; corrected by
        POC-T1 (Issue #260). A stale "decides nothing" is worse than no note at all — it is the
        sentence a reader trusts when judging whether a change here is safe.

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
        ONE slot derivation behind BOTH the discard decider (`_needs_v2`) and the refresh SHED
        (`_refresh_shed_keepcost`) — rows need only ``cid``, ``deploy`` (the v1
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
                # NOTE (Issue #261 wave-2, ep83117367 f34): narrowing this to a base that is
                # EVOLVABLE THIS TURN (`_successor_evolvable_now`) was built and REVERTED — it
                # contradicts the ruling this spike exists for. `line_slots`' own docstring rules the
                # turn-fresh case explicitly: "don't Harlequin away the second Mega Starmie **the
                # turn its Staryu hit the bench**" (ep83037962 f49). The need is created by the Active
                # DYING, not by the evolve being legal today, so a successor whose base arrived this
                # turn is still needed imminently. f34's residual regression is a live ruling conflict
                # between those two frames, recorded in ADR-0101, NOT a defect to patch here.
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
        # discounts; the 86091435-68 ruling with timing). The ADR-0062 oracle (`_denial_at`) was a
        # GATE only here — `> 0` = the strip BITES this body — and Issue #228 deleted it: relevance
        # > 0 SUBSUMES that gate (it is already 0 for a bare body, for surplus Energy and for one
        # dying to my KO this turn, the `active_can_ko` drop consumed intact). Eligibility
        # routes through the SUPPLIES net: any held row carrying a deny-supplying tag
        # (gust / energy_denial). Fail-closed everywhere: no deny-capable row, no opponent read,
        # unknown stats (`_opp_turns_to_ready` → None) or a strip that bites nothing → NO slot —
        # those rows keep pricing at the shipped hedge. The disruption band is the ONE-currency
        # gust tier (`TAG_TIER["gust"]`, ~10) — NOT each denier's global worth (a role-less Hammer
        # stays worth 0 globally; only its live-strip DENY slot earns the band), so the leaf and
        # every other worth site are untouched.
        # ADR-0076: gust ALWAYS supplies both "deny" and "gust_target" kinds (`needs.SUPPLIES`), but
        # only ONE is ever LIVE for a given decision — armed, gust rows route to their own instrument
        # instead of riding the flat deny tier (a Boss's Orders doesn't strip Energy; pricing it
        # through `deny`'s oracle-value/timing-grade shape never matched what it actually does). OFF
        # (default) leaves `deny_tags` exactly as shipped — byte-identical.
        deny_tags = {src for src, kinds in needs.SUPPLIES.items() if "deny" in kinds}
        gust_tags = {src for src, kinds in needs.SUPPLIES.items() if "gust_target" in kinds}
        if self.gust_target_slots:
            deny_tags = deny_tags - gust_tags
        deniers = [k for k, r in enumerate(rows) if deny_tags & _tags(r["cid"])]
        deny_tier = TAG_TIER["gust"]
        # ARMED (ADR-0080, Issue #187): the keep price stops being the FLAT disruption tier and becomes
        # `tier x relevance(this body)` — a Hammer is worth keeping in proportion to how much the
        # Energy it would take is actually doing. The `/2^t` turns-to-ready GRADE is retained (user
        # ruling, 2026-07-30): relevance is deliberately not imminence-gated — it scans the whole line
        # including forward forms, which is what lets a Riolu's banked {F} score at all — so the grade
        # is the only term pricing WHEN the threat lands. Per-body rather than a board-level max, so
        # each body keeps its own deadline; the DP then picks the best assignment, which is the max.
        deny_rel = self._deny_relevance_map(obs, board) if self.deny_relevance else {}
        if deniers and self.deny_relevance:
            state = obs.get("current") or {}
            players = state.get("players") or []
            yi = state.get("yourIndex", 0)
            opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else None
            areas = [("bench", (opp or {}).get("bench") or [])]
            if not board.active_can_ko:
                areas.insert(0, ("active", (opp or {}).get("active") or []))
            for area, bodies in areas:
                for bi, p in enumerate(bodies):
                    # relevance > 0 SUBSUMES the ADR-0062 bite gate: it is already 0 for a body
                    # with no Energy, for surplus Energy, and for one dying to my KO this turn. The
                    # OFF branch here read `_denial_at` as that gate; both are DELETED (Issue #228,
                    # directive 1) and OFF now emits no deny slot at all — degraded, not a rollback.
                    value = deny_tier * max((deny_rel.get((area, bi)) or {}).values(), default=0.0)
                    if not p or value <= 0:
                        continue
                    t = self._opp_turns_to_ready(p)
                    if t is None:
                        continue               # unknown stats — fail closed, no deny slot
                    _emit(needs.deny_slot(f"deny:{area}{bi}:{p.get('id')}",
                                          oracle_value=value, turns_to_ready=t), deniers)
        # GUST-TARGET SLOTS (ADR-0076, kill-switched): held gust-effect Trainer cards keep-priced
        # against the REAL per-body removal value (`_opponent_target_rows`) — reads the per-decision
        # cache `_board()` stashes when one exists (shared with the S3a shadow, never recomputed
        # twice per decision), falling back to a fresh compute for a hand-built `board` that never
        # went through `_board()` (test fixtures). Not a flat card tier. Bench ONLY — a gust effect
        # forces a switch of a BENCHED Pokémon (verified at source, `doctrine_gust.py`); the
        # opponent's Active is never a legal gust target, so it never opens a slot here (unlike deny,
        # which strips Energy off either area).
        if self.gust_target_slots:
            gusters = [k for k, r in enumerate(rows) if gust_tags & _tags(r["cid"])]
            if gusters:
                # ONE ladder, `_deny_rows` — this used to open-code the cache-or-compute walk, a
                # second spelling of the same three lines. Issue #228 extracted
                # `_best_area_weighted_relevance` for
                # exactly that reason and would have left this copy behind.
                target_rows = self._deny_rows(obs, board)
                if target_rows:
                    for r in target_rows:
                        if r["area"] != "bench" or r["value"] <= 0:
                            continue           # off-area, or a removal that isn't worth anything
                        _emit(needs.gust_target_slot(
                            f"gust_target:{r['area']}{r['bi']}:{r['id']}", value=r["value"]),
                            gusters)
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
                # INSURANCE, not latent worth (ADR-0101 amendment, Issue #261 wave-2 ruling on
                # ep83969481 f55): `_GENERAL_WORTH_W` prices a card that is ~one deploy away from
                # mattering. A `clutch_heal` covering an IRREPLACEABLE Active is not one deploy away —
                # it is the survival plan, and the latency haircut is simply the wrong model of it.
                # Full tier at deadline 1 (the threat is NEXT turn, which is why `answer_doom` — a
                # this-turn read — correctly stays shut here; reviewed.json rules exactly that), and
                # the slot takes the answer-doom KIND so it also takes that kind's closing edge:
                # `_refresh_slot_resupply` gives it no re-access credit. Deliberate — the ruling is
                # about CERTAINTY, and a heal you are relying on to survive may not be priced at
                # "I'll probably redraw it". `needs.insure_wincon_slot` carries the reasoning.
                if self._heal_insures_the_last_wincon(cid, me):
                    _emit(needs.insure_wincon_slot(f"insure:{cid}", value=worth * deploy), live)
                    continue
                _emit(needs.general_worth_slot(f"general:{cid}",
                                               value=worth * deploy * _GENERAL_WORTH_W * liq), live)
        return slots, elig

    def _heal_insures_the_last_wincon(self, cid, me: dict) -> bool:
        """Is held card ``cid`` the heal keeping my LAST win-condition alive? — the user's wave-2
        ruling on ep83969481 f55, stated as a board fact: *"preserve our healer when we only have a
        single wincon remaining."*

        All four clauses are load-bearing, and each removes a way this could over-fire:

        1. ``cid`` carries ``clutch_heal`` — the emergency-heal tag, not any heal (a routine heal is
           latent worth and keeps the general slot);
        2. my Active IS a win-condition (`_wincon_set`) — healing a filler body insures nothing;
        3. no OTHER win-condition body is in play — a second copy on the Bench means the line
           survives the KO, which is exactly ep83661649 f30 (two Mega Starmie ex in play), and that
           frame must NOT take this slot;
        4. the line CANNOT BE REBUILT — no pre-evolution of it survives anywhere reachable: not on
           the Bench, not in hand, and **not in the unseen pool** (deck + face-down prizes).

        Clause 4 reads the unseen pool deliberately, and an earlier draft that stopped at the board
        was measurably wrong: with only the board clauses it fired on *any* empty Bench under a
        wincon Active and cost the Discrimination Gate `82525101|1|decision|87` (rank 1 -> 2), a
        board whose deck still holds Staryu. "Our last wincon" is a claim about COPIES REMAINING, not
        about board shape — on ep83969481 f55 the real fact is that both Staryu are in the discard,
        which strands the spare Mega Starmie ex still sitting in the deck.

        That distinction is also what keeps this off §6's double-counting list. An empty Bench under
        a knock-outable Active already carries two guards (`empty-bench-filter`, `_predicted_loss`),
        and the POC plan names putting it there a third time as the error to avoid. This is a
        different fact — the win-condition LINE being exhausted — and it prices a held card rather
        than gating a move."""
        if not (self.functions and "clutch_heal" in set(self.functions.tags(cid))):
            return False
        active = next((b for b in (me.get("active") or []) if b), None)
        wincons = self._wincon_set()
        if not active or active.get("id") not in wincons:
            return False
        bench = [b for b in (me.get("bench") or []) if b]
        if any(b.get("id") in wincons for b in bench):
            return False                       # the line survives the KO — ep83661649 f30
        hand = [c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None]
        if any(h in wincons and self._successor_evolvable_now(me, h) for h in hand):
            return False                       # a successor lands this turn
        preevos = self._line_preevo_set()
        if not preevos:
            return False                       # a Basic wincon has no line to exhaust
        if any(b.get("id") in preevos for b in bench) or any(h in preevos for h in hand):
            return False
        from collections import Counter
        unseen = Counter(self.deck)
        unseen.subtract(self._visible_card_counts(me))
        return not any(unseen.get(pid, 0) > 0 for pid in preevos)

    def _needs_hand_rows(self, obs: dict, board: Board, exclude_cid=None) -> list:
        """The whole-hand v2 rows for the refresh SHED: one row per held card (minus ONE copy
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

    def _line_payoff_stat(self, cid):
        """The CardStat whose attack a body's Energy ultimately FUELS — evolution-lookahead (attach
        grill Ruling 5a). A win-condition-Line PRE-evolution's Energy carries through evolution and
        builds toward the LINE's PAYOFF attack (a Staryu's Energy builds toward Mega Starmie's Nebula
        Beam CCC=210, NOT Staryu's own Water Gun, maxed at 1), so its progress must be priced by the
        payoff, not the pre-evo's cheap own attack. Returns the payoff's stat for a wincon-Line
        pre-evolution, else the body's own stat (a terminal/own-attacker body is priced by itself)."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if cid is None or not self.stats:
            return st
        for line in self._wincon_lines():
            if cid in (line.path or []) and cid != line.payoff:
                return self.stats.get(line.payoff) or st
        return st

    def _attach_progress(self, cid, energy: int) -> float:
        """The COUNT reading of convex forward-build value — body ``cid`` at ``energy`` Energy toward
        the biggest attack it FUELS. ``(min(e, M) / M)**2 * maxDamage`` — the SQUARE makes the
        marginal of the k-th Energy INCREASE with k, so completing a started carrier is worth more
        than starting a fresh body: concentrate on the most-built survivable carrier falls out
        (82523811-59, 82749168-61), while the maxed body's marginal is 0 (over-attach). `M`/`maxDamage`
        come from the LINE PAYOFF (`_line_payoff_stat`), so a wincon pre-evo builds toward its evolution's
        attack, not its own cheap one (82752604-61, 83116081-21, 85059103-84).

        The DECIDER prefers the TYPED slot-fraction reading (`_attach_build_delta`, ADR-0069 §3) and
        only falls back here when the payoff attack's per-slot cost does not resolve — where a typed
        claim would be a guess and the count reading makes none."""
        st = self._line_payoff_stat(cid)
        maxc = getattr(st, "maxDamageCost", None) if st is not None else None
        dmax = float(getattr(st, "maxDamage", 0) or 0) if st is not None else 0.0
        if not maxc or maxc <= 0 or dmax <= 0:
            return self._attach_readiness(cid, energy)
        frac = min(energy, maxc) / maxc
        value = frac * frac * dmax
        if cid in self._line_preevo_set():
            value *= _ATTACH_PREEVO_DISCOUNT
        return value

    def _payoff_attack_id(self, payoff_stat):
        """The attack a body's Energy is ultimately BUILDING toward — the biggest-damage attack of
        the line payoff. None when no attack record resolves (the caller then makes no typed claim)."""
        aids = tuple(getattr(payoff_stat, "attacks", None) or ())
        return max(aids, key=self.combat.attack_damage) if aids else None

    def _build_standing(self, target: dict | None, extra_units=()) -> float:
        """**Build Standing** — the LEVEL of ``target``'s convex typed build credit, optionally over a
        hypothetical body also carrying ``extra_units`` (ADR-0070 §2).

        ``(matched/slots)**2 * maxDamage``, where ``matched`` is the greedy typed assignment of the
        body's attached Energy against the LINE PAYOFF attack's cost shape — by the SAME matcher
        `reachable_attach` uses, so "fits" and "reaches" can never disagree. Two consequences that
        used to need their own rungs: an Energy filling no slot earns ZERO build (off-type waste is
        emergent, never a separate colourless-blind boolean), and a colourless slot absorbs any type
        (so Munkidori's {D} in Mind Bend's ● is real progress, not "wasted"). A pre-evolution keeps
        the `_ATTACH_PREEVO_DISCOUNT`; the evolution-lookahead payoff pricing carries over unchanged
        from the count reading, which is the fallback when the payoff attack's per-slot cost does not
        resolve (where a typed claim would be a guess).

        The LEVEL is the shared form: #139 needs only its DIFFERENCE under an option's provision
        (`_attach_build_delta`, below), while #140 needs the level itself — an evolve moves no Energy,
        so its deploy value is `standing(evolved) − standing(pre-evolution)` on the SAME attached
        Energy, and **evolving is precisely the removal of the pre-evolution discount**. One function
        owns build credit so the two readings cannot drift."""
        if not target:
            return 0.0
        tcid = target.get("id")
        st = self._line_payoff_stat(tcid)
        dmax = float(getattr(st, "maxDamage", 0) or 0) if st is not None else 0.0
        aid = self._payoff_attack_id(st)
        if aid is not None and dmax > 0:
            matched, slots = self.combat.matched_slots(target, aid, extra_units=extra_units)
            if slots:
                value = ((matched / slots) ** 2) * dmax
                return value * (_ATTACH_PREEVO_DISCOUNT if tcid in self._line_preevo_set() else 1.0)
        have = len(target.get("energies") or [])          # no typed cost record -> the count reading
        return self._attach_progress(tcid, have + len(extra_units))

    def _attach_build_delta(self, target: dict | None, extra_units) -> float:
        """The CONVEX, TYPED build progress ``extra_units`` buys on ``target`` (ADR-0069 §3) — the
        DIFFERENCE of :meth:`_build_standing` with and without the option's provision.

        The branch (typed vs the count fallback) is chosen by the payoff attack's cost record, which
        no attach changes, so both legs always read the same way and the difference is exact."""
        return self._build_standing(target, extra_units) - self._build_standing(target)

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
        wild = self.combat.wild_units(routed)   # the routed colours aren't fixed by this pick — fail-open
        best = 0.0
        for b in (me.get("bench") or []):
            if not b:
                continue
            cid = b.get("id")
            if cid not in line_ids and self._is_utility_body(cid):
                continue                                       # don't credit routing onto a utility body
            best = max(best, self._attach_build_delta(b, wild))
        return best

    def _attach_provision(self, target_stat, burst: bool) -> int:
        """Energy UNITS this attach delivers, at PRINTED provision (ADR-0069 §5).

        Ignition Energy provides {C} on a Basic and {C}{C}{C} on an Evolution Pokémon (card text,
        verified at source) — a CARD FACT, never bent by a valuation heuristic. The old unit gate
        falsified it to 1 unless the 3 happened to unlock a KO; the spend discipline that gate was
        smuggling now lives in the equation (the evaporation loss and the no-KO cap below), where it
        can be read. Colourless provision pays colourless slots only — that typing is carried by the
        units themselves, not by this count."""
        if burst and bool(getattr(target_stat, "evolvesFrom", None)):
            return 3
        return 1

    def _attach_body_view(self, target: dict | None):
        """The StateModel :class:`BodyView` wrapping this raw board dict — the handle the
        affordability family (Budget / reachability) is keyed on. None off-board or when no model has
        been built (the decider then makes no this-turn claim)."""
        model = self._state_model
        if model is None or not target:
            return None
        return next((b for b in model.mine.bodies if b.body is target), None)

    def _reusable_hand_energy_id(self, obs: dict):
        """A REUSABLE (non-`discard_eot`) Energy card id in my hand — the conservation alternative a
        burst's tonight-credit is capped against (ADR-0069 §5b). ONE predicate, at two arities:
        `_has_reusable_energy` is this lookup's boolean projection, so "does one exist" and "which
        one" cannot disagree — which the cap depends on, since it would otherwise fire with no
        alternative to fall back to. None when the hand holds none."""
        return self._reusable_energy_id(self._my_player(obs).get("hand") or [])

    def _attacker_alternative_in_play(self, obs: dict, target: dict | None) -> bool:
        """Is a REAL attacker alternative on my board right now — some OTHER body of mine that is a
        win-condition Line member or carries an attacker Role (not itself dead through a missing
        partner) AND that would gain actual build from THIS Energy?

        This is what makes the role gate BOARD-EVALUATED (ADR-0069 §4, the Ruling-6 pattern
        generalized). "This body's job is not attacking" is only a reason to withhold Energy while
        somebody else can take it; on a lone or attacker-less board the utility body IS the attacker,
        and pricing it at zero would score the only legal home BELOW ending the turn.

        Deliberately IN PLAY, not "could use THIS colour". Making the test per-provision is tempting
        once build is typed — a dead colour is withheld on behalf of a body that cannot take it — but
        it was MEASURED and rejected: it inverts 86091728-19, where the human ruled that the line eats
        the {P} first even though the {D} in the same hand is useless to the line. That frame says the
        priority is a resource-sequencing doctrine (which Energy to spend this turn), not a gating
        one, and ADR-0069 §4 states the gate as written here. See
        docs/plans/attach-decider-swap-review.md for the ruling the two follow-up doctrine pins owe."""
        line_ids = self._recognized_line_preevo_set() | self._wincon_set()
        me = self._my_player(obs)
        for p in ((me.get("active") or []) + (me.get("bench") or [])):
            if not p or p is target:
                continue
            cid = p.get("id")
            if (cid in line_ids
                    or ((_ATTACKER_ROLES & set(self._roles_of(cid)))
                        and not self._partner_absent(cid, obs))):
                return True
        return False

    def _attach_retreat_equity(self, target: dict | None, units: int, burst: bool) -> float:
        """**Retreat Equity** — the mobility an attach buys by paying toward the body's printed
        Retreat cost (ADR-0069 §1; glossary in `common/CONTEXT.md`).

        The attack terms structurally cannot see this: the turn-1 Energy onto a lone Lunatone buys no
        damage tonight and no build the deck cares about, but it pays the pivot that later lets
        Solrock attack. TYPE-AGNOSTIC, because Retreat slots are colourless (rules.md §3) — which is
        exactly the value an off-type desperation attach buys. Zero on a body already funded for its
        retreat, on a free-retreat body (TEF Dunsparce has NO Retreat cost, so the "don't feed
        Dunsparce the only {D}" lesson survives any mobility credit), and on a burst (it leaves play
        at end of turn, so it funds no future pivot)."""
        if burst or not target:
            return 0.0
        st = self.stats.get(target.get("id")) if self.stats else None
        cost = int(getattr(st, "retreatCost", 0) or 0)
        if cost <= 0:
            return 0.0
        have = len(target.get("energies") or [])
        if have >= cost:
            return 0.0                                     # already funded — the pivot is already paid
        covered = min(have + units, cost) - min(have, cost)
        return _ATTACH_RETREAT_EQUITY * covered / cost

    def _attach_value(self, obs: dict, select: dict, board: Board, option: dict):
        """The ATTACH DECIDER: price ONE energy-attach option as an AXES-SUM (ADR-0069).

            marginal = attack_axis + retreat_equity + ability_fuel − evaporation_loss
            attack_axis = max(this_turn, build, accel_value)

        MAX within the attack axis because its three terms re-read ONE progress (a single Energy is
        never double-paid for the same attack); SUM across the channels because Retreat Equity and
        Ability Fuel are INDEPENDENT card features — a {D} that both fills Mind Bend's colourless slot
        and wakes Adrena-Brain beats the same-build {P} outright, with no tie-break coincidence.

        Returns a per-option working row (the decider's legible working, ADR-0008/0019 — the
        substrate #146/#148 consume), or None to ABSTAIN: a Pokémon Tool rides `OptionType.ATTACH`
        but is not Energy, so it is never priced here.

        The terms, and the rung each one retired:
          * `this_turn`      — a TRUE COUNTERFACTUAL under the full Attach Budget: best reachable
                               damage with this Energy committed minus best reachable damage without
                               it, both legs typed and sound (ADR-0067), both at the same residual
                               capacity. So an attach that needs a budget partner is credited instead
                               of read as futile (the f70 under-read), a type-unpayable attack stops
                               reading as reachable, ANY attack a doomed Active unlocks counts (not
                               only its biggest — the Mega-Starmie tempo arm), and an option on a body
                               the accel already reaches is credited only for what it UNIQUELY adds.
          * `build`          — typed slot-fraction progress toward the line payoff (`_attach_build_delta`).
          * `accel_value`    — the forward build the Energy an ACTIVE accelerator ROUTES buys.
          * `retreat_equity` / `ability_fuel` — the two orthogonal channels.
          * `evaporation_loss` — a `discard_eot` Energy that leaves play UNCASHED costs its own worth,
                               so ending the turn genuinely beats torching an Ignition on turn 1.
        Gates land PER-AXIS: the board-evaluated role gate and the overkill cap zero the ATTACK AXIS
        only (a role-gated body still banks mobility and fuel); the survival gate zeroes `build` for a
        doomed Active EXCEPT a wincon-Line pre-evolution (the evolution-escape: Energy carries through
        evolution, and a Mega evolving does not end the turn); evaporation is GLOBAL.

        `tactical` is what the option actually scores: the marginal scaled into the rung band, less
        the sub-band resource tie-break that spends the renewable card among equals. It MAY be
        NEGATIVE — the decider is allowed to say "attach nothing" and mean it.
        """
        ctx = select.get("context")
        is_attach = option.get("type") == _ATTACH
        is_from = ctx == _ATTACH_FROM and option.get("type") == _CARD
        if not (is_attach or is_from):
            return None
        ecid = self._option_card_id(obs, select, option)
        estat = self.stats.get(ecid) if (self.stats and ecid is not None) else None
        if is_attach and not self._attach_is_energy(estat):
            return None                                        # a Pokémon Tool is not Energy
        target = self._attach_target(obs, option)
        if target is None and is_from:
            target = self._option_pokemon(obs, select, option)
        if target is None:
            return None
        tcid = target.get("id")
        target_stat = self.stats.get(tcid) if (self.stats and tcid is not None) else None
        # The recipient's real board AREA. An ATTACH_FROM option carries it as `area` (an accel usually
        # routes to the Bench, but the engine does offer the Active — and the survival gate has to see
        # a DOOMED Active recipient, or the accelerated Energy sinks into a body that dies holding it).
        area = option.get("inPlayArea") if is_attach else option.get("area", _BENCH)
        etags = set(self.functions.tags(ecid)) if (self.functions and is_attach and ecid is not None) else set()
        burst = "discard_eot" in etags
        units = self._attach_provision(target_stat, burst) if is_attach else 1
        # The PROVISION as Budget units: an ATTACH commits a known card (a typed Basic keeps its
        # colour; Ignition's {C}{C}{C} pays colourless slots only), while an ATTACH_FROM recipient
        # pick receives an Energy whose colour this decision does not fix — wild, fail-open.
        provision = (self.combat.attach_units(ecid, units) if is_attach
                     else self.combat.wild_units(units))
        # -- the attack axis, term 1: tonight's counterfactual ------------------------------------
        # The survival gate's THIS-TURN half: going down swinging is only worth buying when it is
        # actually the line. A READY benched win-condition that I can pivot into strictly dominates
        # whatever the doomed Active could swing for, so tonight's damage is not this attach's to buy
        # (83007714-65: the Ignition onto doomed Cinderace before the retreat into a ready Mega
        # Starmie ex was pure waste — the charter frame of the deleted `dont-feed-the-doomed`).
        # The pivot must be LEGAL NOW, which only the engine's own menu can say: at 82525101-69 the
        # bench Mega is "ready" for Jetting Blow but carries too little Energy to pay the 2-cost
        # retreat, so no RETREAT option is offered and arming the doomed Active for 120 IS the play.
        # Reading `bench_wincon_ready` alone would call both frames the same and break that one.
        arm_dominated = (area == _ACTIVE and board.active_doomed and board.bench_wincon_ready
                         and any(o.get("type") == _RETREAT for o in (select.get("option") or ())))
        # Only the ACTIVE fires this turn, and the player going FIRST cannot attack on its turn 1
        # (rules.md §2 / rulebook L152), so on either of those there is no tonight to buy.
        view = self._attach_body_view(target)
        can_attack_tonight = (area == _ACTIVE and board.turn > 1 and view is not None
                              and not arm_dominated)
        this_turn = base_dmg = committed_dmg = 0.0
        if can_attack_tonight and is_attach:
            mine = self._state_model.mine
            base_dmg = mine.best_reachable_damage(view, manual_spent=True)
            committed_dmg = mine.best_reachable_damage(view, extra_energy_ids=(ecid,) * units,
                                                       manual_spent=True)
            this_turn = max(0.0, committed_dmg - base_dmg)
            if burst and this_turn > 0:
                this_turn = self._burst_capped_tonight(obs, view, this_turn, base_dmg, committed_dmg)
        # -- the attack axis, terms 2 and 3 -------------------------------------------------------
        # The survival gate: a doomed carrier banks no forward build — EXCEPT a wincon-Line
        # pre-evolution, whose Energy carries through evolution (the evolution-escape).
        survives = not (area == _ACTIVE and board.active_doomed)
        # A `discard_eot` burst earns NO build, ever: build is FORWARD value and the card is discarded
        # at end of turn, so there is nothing forward about it. Only `this_turn` — what it cashes
        # before it goes — can credit a burst. (Without this the Ignition's honest 3 units read as a
        # full Nebula Beam build and beat the reusable Basic even where its attack cannot KO, which is
        # exactly the 83116501-70 blunder the no-KO cap exists to prevent; the cap alone does not
        # reach it, because it caps `this_turn` and the build axis was quietly out-bidding it.)
        build = (self._attach_build_delta(target, provision)
                 if (not burst and (survives or tcid in self._line_preevo_set())) else 0.0)
        accel_value = 0.0
        feeds_accel = (area == _ACTIVE and "accel_source" in self._roles_of(tcid)
                       and self._attach_target_needs(target)
                       and not board.accel_recipient_missing and not board.bench_wincon_ready)
        if feeds_accel:
            aid = self._accel_attack_id(tcid)
            ast = self._attack_stat(aid) if aid is not None else None
            if ast is not None:
                # EXPECTED routing for the value estimate: the printed ceiling capped by what the
                # recipients can actually use. (The live accel commitment's `_recover_units` also
                # floors this by the prize-paranoid deck-fuel bound — a grader-safety concern for a
                # COMMITMENT, not for a valuation.)
                routed = min(getattr(ast, "recoverN", 0), self._recover_recipient_need(ast, board, obs))
                accel_value = self._accel_routed_value(obs, board, routed)
        # -- the per-axis gates -------------------------------------------------------------------
        # The ROLE gate, board-evaluated: a body whose job is non-attacking (wall / draw-engine /
        # partnerless co-dependent engine, and not a win-condition Line member) advances no valued
        # attack — but only while somebody else can take the Energy.
        # The bodies the deck's PLAN attacks with: every declared attacker Line's members (ADR-0048's
        # broadened set, so a secondary attacker's base is a plan piece too — Makuhita on the
        # Makuhita -> Hariyama prize-wall line is `evolution_base`, a Role that names a Line stage
        # rather than an attack) plus the win-condition payoffs. NARROWER sets stay narrow elsewhere in
        # this equation on purpose: the pre-evolution discount and the evolution-escape read
        # `_line_preevo_set`, which is win-condition-only by design.
        line_ids = self._recognized_line_preevo_set() | self._wincon_set()
        # A body the deck gave ROLES, none of which is an attacker Role, has been DECLARED a
        # non-attacking plan piece — the general form of the `engine`-only read `_is_utility_body`
        # already makes. It is what catches a `counter_mover` (dragapult's Munkidori: "the attach seam
        # reads the Role — a stuck-Active Munkidori may take its {P} … once the benched line is fed")
        # and a sacrificial `starter`, neither of which carries a `_UTILITY_TAGS` tag. Reading it here
        # rather than widening `_is_utility_body` keeps the change inside the attack axis, which is the
        # only place a declared role means "do not fund this to attack".
        declared = set(self._roles_of(tcid))
        non_attacking = tcid not in line_ids and (
            self._is_utility_body(tcid) or self._is_draw_engine_body(tcid)
            or self._partner_absent(tcid, obs)
            or (bool(declared) and not (_ATTACKER_ROLES & declared)))
        role_gated = non_attacking and self._attacker_alternative_in_play(obs, target)
        # The OVERKILL cap: once the ACTIVE already KOs the opponent's Active AND what it can afford
        # RIGHT NOW already covers the biggest body on their board, a bigger attack buys nothing more
        # this game-state — develop a second threat instead (82750161-59). Opponent-aware, so it
        # stands down while a bench threat still out-HPs the affordable attack (82523811-59).
        overkill = False
        if area == _ACTIVE and board.active_cheap_attack_kos:
            opp_hp = self._opp_body_hps(obs)
            # DELIBERATE CombatMath bypass (POC-T1's documented list): the #142 EMPTY-Budget leg —
            # "what can this body do with what is attached RIGHT NOW", the baseline of the
            # counterfactual. The model's route always carries the FULL Budget, so the empty leg has
            # no model expression by construction.
            if opp_hp and max(opp_hp) <= self.combat.best_reachable_damage(target, budget=Budget()):
                overkill = True
        # The EVAPORATION gate, global: a `discard_eot` Energy that buys nothing before it is
        # discarded at end of turn banks nothing durable — and costs what it was worth.
        cashed = this_turn > 0 and not role_gated and not overkill
        evaporates = burst and not cashed
        resource_cost = self._role_value(ecid) if (is_attach and ecid is not None) else 0.0
        evaporation_loss = resource_cost if evaporates else 0.0
        # -- the axes-sum -------------------------------------------------------------------------
        attack_axis = 0.0 if (role_gated or overkill or evaporates) else max(
            this_turn, build, accel_value, 0.0)
        retreat_equity = self._attach_retreat_equity(target, units, burst)
        ability_fuel = (_ATTACH_ABILITY_FUEL if (not burst and is_attach
                                                and self._attach_fuels_dormant_ability(estat, target))
                        else 0.0)
        marginal = attack_axis + retreat_equity + ability_fuel - evaporation_loss
        # The resource TIE-BREAK: charged on worth ABOVE a reusable Basic, so a plain Basic pays
        # nothing and only the one-shot is nudged. Sub-band — it orders equals, never overturns build.
        tactical = (marginal * _ATTACH_VALUE_SCALE
                    - _ATTACH_RESOURCE_TIEBREAK * max(0.0, resource_cost - ENERGY_TIER))
        # The resolved target SLOT (board area, position) — the comparison key for the corpus sweep,
        # NOT the raw option index: duplicate energy-source options and identical-effect target copies
        # otherwise read as false disagreements (82523811-59, 82750161-59). type-8 ATTACH carries
        # inPlayArea/inPlayIndex; the type-3 ATTACH_FROM recipient carries area/index.
        slot = [area, option.get("inPlayIndex") if is_attach else option.get("index")]
        return {"i": None, "target": tcid, "energy": ecid, "slot": slot,
                "marginal": round(marginal, 2), "tactical": round(tactical, 2),
                "attack_axis": round(attack_axis, 2), "this_turn": round(this_turn, 2),
                "build": round(build, 2), "accel_value": round(accel_value, 2),
                "retreat_equity": round(retreat_equity, 2), "ability_fuel": round(ability_fuel, 2),
                "evaporation_loss": round(evaporation_loss, 2), "units": units,
                "role_gated": role_gated, "overkill": overkill, "doomed": not survives,
                "burst": burst, "evaporates": evaporates,
                "line_value": round(0.0 if role_gated else self._role_value(tcid), 1),
                "resource_cost": round(resource_cost, 1)}

    def _burst_capped_tonight(self, obs: dict, view, this_turn: float,
                              base_dmg: float, committed_dmg: float) -> float:
        """The burst's no-KO CAP (ADR-0069 §5b): a cashable one-shot earns at most what the best
        REUSABLE Basic in hand would have earned tonight — UNLESS its attack converts a KO the Basic
        cannot reach.

        This is the whole of `conserve-burst-when-no-ko` / `conserve-discard-energy-prefer-basic` as
        arithmetic: when Ignition's {C}{C}{C} unlocks Nebula Beam 210 against a 200-HP Active the cap
        lifts and the burst is spent (82523811-105); when even the big attack cannot KO (Nebula 210
        vs a 300-HP wall) the Basic does tonight's job just as well, so the burst keeps only the
        Basic's credit and loses the resource tie-break (83664340-45). No reusable Basic in hand ->
        no alternative -> no cap."""
        reusable = self._reusable_hand_energy_id(obs)
        if reusable is None:
            return this_turn
        opp_hp = (self._opp_active(obs) or {}).get("hp", 0) or 0
        reusable_dmg = self._state_model.mine.best_reachable_damage(
            view, extra_energy_ids=(reusable,), manual_spent=True)
        if committed_dmg >= opp_hp > reusable_dmg:
            return this_turn                                   # the burst converts a KO the Basic misses
        return min(this_turn, max(0.0, reusable_dmg - base_dmg))

    def _attach_decision(self, obs: dict, select: dict, board: Board, option: dict):
        """The decider's working ROW for this option, or None when the decider does not speak here:
        the kill-switch is OFF, the option is not an energy attach, or it is a Pokémon Tool. The ONE
        pricing call per option — the score term and the planner's spend account both read it, so
        neither can price a different attach than the other."""
        if not getattr(self, "attach_value", False):
            return None
        return self._attach_value(obs, select, board, option)

    # ── the DEPLOY decider (ADR-0086, Issue #197) ────────────────────────────────────────────────

    def _deploy_offered_ids(self, obs: dict, select: dict) -> list:
        """The card ids a `_TO_BENCH` select actually OFFERS, one per option — the Poffin-class
        fetch's revealed candidates (ADR-0086 decision 6's third entry point).

        These are deck cards, but they are **not** deck RESUPPLY: the search has already found them
        and the only remaining question is which go onto the Bench. So they are certain suppliers,
        exactly like a body in hand, and `_deploy_supplier_rows` takes them as such. One row per
        OPTION rather than per distinct id, because two copies of the same species are two physical
        bodies that can both be placed.

        Read off the MENU, which during `_greedy_grab`'s re-score still lists candidates already
        taken this multi-pick. That is deliberate rather than overlooked: the greedy re-scores
        against a virtual board where those bodies are already in play, so the needs they covered are
        closed and their rows are eligible for nothing — while `my_bench` has risen, which is what
        actually tightens the capacity. Filtering them out would need the acquired set threaded
        through the trace path for no change in the answer."""
        out = []
        for opt in (select.get("option") or []):
            cid = self._option_card_id(obs, select, opt)
            st = self.stats.get(cid) if (self.stats and cid is not None) else None
            if st is not None and getattr(st, "is_pokemon", False):
                out.append(cid)
        return out

    def _deploy_supplier_rows(self, obs: dict, board: Board, *, offered=()):
        """``(ready_rows, deck_rows)`` — the bodies competing for my free Bench slots, split by
        CERTAINTY because the two are not interchangeable (ADR-0086 decision 2).

        Only POKÉMON: capacity here is BENCH capacity, and a Trainer covering a draw need costs no
        Bench slot.

        **The split is the whole point, and the first build got it wrong.** Deck-reachable bodies
        were handed to the assignment as full rival SUPPLIERS, so every hand copy had a deck twin
        covering the same slot — and a body whose slot a sibling already covers prices 0 (the
        sets-not-sums rule, working exactly as designed). With the deck always holding a twin, that
        zeroed nearly every deploy in the corpus and the sweep read `(no-deploy)` on frames the agent
        obviously should bench.

        A deck copy is NOT a substitute for one in hand: you have to draw it. So the deck leg enters
        as slot **RESUPPLY** — the odds the closure re-fills that slot anyway, which discounts the
        held copy to ``v × (1 − r)`` — which is what `resupply` exists for and what decision 2's
        "weighted by Deck-Content Odds" describes.

        ``offered`` is what makes the split about CERTAINTY rather than about the zone. A
        `_TO_BENCH` candidate is a deck card the search has ALREADY found, so no draw stands between
        it and the Bench — it belongs on the ready side with the hand, and its copy is removed from
        the deck counts so the same physical card cannot also re-supply the slot it is about to
        fill (which would discount it against itself)."""
        from collections import Counter
        me = self._my_player(obs)
        counts = board.deck_known_counts
        if not counts:
            unseen = Counter(self.deck)
            unseen.subtract(self._visible_card_counts(me))
            counts = {cid: n for cid, n in unseen.items() if n > 0}

        def _is_body(cid) -> bool:
            st = self.stats.get(cid) if (self.stats and cid is not None) else None
            return bool(st is not None and getattr(st, "is_pokemon", False))

        offered = [cid for cid in offered if cid is not None and _is_body(cid)]
        if offered:
            counts = dict(counts)
            for cid in offered:
                if counts.get(cid, 0) > 0:
                    counts[cid] -= 1
            counts = {cid: n for cid, n in counts.items() if n > 0}

        ready_rows = []
        for c in (me.get("hand") or []):
            cid = (c or {}).get("id")
            if cid is not None and _is_body(cid):
                ready_rows.append({"i": len(ready_rows), "cid": cid, "zone": "hand",
                                   "worth": round(self._role_value(cid), 1),
                                   "deploy": self._deploy_odds(cid, board, counts), "fuel": False})
        for cid in offered:
            ready_rows.append({"i": len(ready_rows), "cid": cid, "zone": "offered",
                               "worth": round(self._role_value(cid), 1),
                               "deploy": self._deploy_odds(cid, board, counts), "fuel": False})
        deck_rows = []
        for cid in sorted(c for c in counts if _is_body(c)):
            deck_rows.append({"i": len(ready_rows) + len(deck_rows), "cid": cid, "zone": "deck",
                              "worth": round(self._role_value(cid), 1),
                              "deploy": self._deploy_odds(cid, board, counts), "fuel": False})
        return ready_rows, deck_rows

    def _deploy_line_deadline(self, me: dict, cid) -> int:
        """When the line THIS held body belongs to comes online, in turns — the deploy path's
        readiness read.

        `_line_readiness_deadline` answers the held-PAYOFF direction ("is my Riolu in play, so this
        Mega is live?"). For a held BASE it is structurally 99: nothing in play forward-evolves INTO
        a Basic, so no base is ever found. Correct for the shed question it was built for, and
        useless for this one — deploying a base is precisely what STARTS its clock.

        So a held body that is itself a line pre-evolution reads its own hop instead: benching it now
        means evolving next turn, so a single-hop base (Riolu -> Mega Lucario ex) is deadline 1.
        Anything else defers to the payoff-direction helper unchanged."""
        if cid is None:
            return 99
        if cid in self._line_preevo_set():
            forward = self._forward_card_ids(cid) or ()
            if any(f in self._wincon_set() or f in self._line_member_set() for f in forward):
                return 1                       # bench now, evolve next turn
        return self._line_readiness_deadline(me, cid)

    def _deploy_resupply(self, board: Board, slots: list, elig_all: list, hand_n: int,
                         deck_rows: list) -> list:
        """Per-slot RESUPPLY from the deck leg: how likely the closure re-fills each slot without
        spending a Bench slot on a held body now.

        The odds a deck body actually arrives, not merely that it exists: its Deck-Content Odds
        (`deck_contains_probability` — could it be prized?) times the `deploy` gate the resolver
        already applies per row (a dead evolution re-supplies nothing). A RANKED read, so it weights
        the marginal and never gates it (ADR-0074)."""
        resupply = [0.0] * len(slots)
        for k, row in enumerate(deck_rows):
            j_set = elig_all[hand_n + k] if hand_n + k < len(elig_all) else ()
            if not j_set:
                continue
            p = 1.0
            if hasattr(board, "deck_contains_probability"):
                try:
                    p = float(board.deck_contains_probability(row["cid"]))
                except Exception:
                    p = 1.0
            odds = max(0.0, min(1.0, p * float(row.get("deploy", 1.0))))
            for j in j_set:
                if 0 <= j < len(resupply):
                    resupply[j] = max(resupply[j], odds)
        # The CLOSING EDGE — whether the deck delivers IN TIME, not merely whether it delivers.
        # `_resolve_needs`' own docstring specifies this rule and records it as not yet landed: "a
        # deadline-0 slot must take resupply 0.0 regardless of how many the deck could re-draw,
        # because one needed THIS turn is not re-drawable in time" — the same reasoning behind the
        # deploy-now spike and the deadline-0 answer-doom slot.
        #
        # It is what stops SCARCITY standing in for URGENCY. Without it two equal-tier lines are
        # separated by re-drawability alone, so a win-condition base the deck holds more of sinks
        # beneath a scarcer secondary line — 83661652-44, where Makuhita priced 16.67 against Riolu's
        # 2.19 because the deck held no more Makuhita and 87% odds of another Riolu. Both facts are
        # true; they are answers to different questions.
        #
        # Graded against the shared HORIZON rather than a constant invented here: a latent slot
        # (deadline 99) keeps its full re-access credit, a deadline-1 slot keeps ~1/9 of it.
        for j, s in enumerate(slots):
            dl = max(0, int(getattr(s, "deadline", 99) or 0))
            resupply[j] *= min(1.0, dl / float(_HORIZON))
        return resupply

    def _last_ditch_spent(self, me: dict) -> bool:
        """Has a "Last-Ditch" Ability already fired this turn?

        Read SOUNDLY off the board rather than tracked: the card's own text caps it at one per turn
        ("You can't use more than 1 Ability that has 'Last-Ditch' in its name each turn"), and the
        Ability fires on the bench-drop — so a `supporter_tutor` body that ``appearThisTurn`` IS the
        spent use. Same field `_deploy_now_ids` reads for evolution eligibility."""
        for b in (me.get("bench") or []):
            if not b or not b.get("appearThisTurn"):
                continue
            tags = set(self.functions.tags(b.get("id"))) if self.functions else set()
            if "supporter_tutor" in tags:
                return True
        return False

    def _deploy_decision(self, obs: dict, select: dict, board: Board, option: dict):
        """Price ONE candidate Bench deployment — the Pilot half of ADR-0086: resolve board facts
        into `DeployInputs` and delegate. None when the switch is off or the option is not a body
        reaching my Bench.

        **All three entry points** decision 6 names are live: `_PLAY` (7) at `_MAIN`, `_SETUP_BENCH`
        (2, refused by decision 9 before it ever reaches a price) and `_TO_BENCH` (5, the
        Poffin-class fetch). The third abstained silently until Issue #261 item 2d, because the
        candidate is a DECK card and the supplier lookup read hand rows only — so every option on
        that select tied and the pick fell to menu position."""
        if not getattr(self, "deploy_value", False):
            return None
        ctx = select.get("context")
        if ctx not in (_MAIN, _SETUP_BENCH, _TO_BENCH):
            return None
        if ctx == _MAIN and option.get("type") != _PLAY:
            return None
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if stat is None or not getattr(stat, "is_pokemon", False):
            return None

        from common import needs
        from common.deploy_value import DeployInputs, deploy_value

        me = self._my_player(obs)
        offered = self._deploy_offered_ids(obs, select) if ctx == _TO_BENCH else ()
        ready_rows, deck_rows = self._deploy_supplier_rows(obs, board, offered=offered)
        index = next((r["i"] for r in ready_rows if r["cid"] == cid), None)
        if index is None:
            return None
        # One resolve over BOTH sides so the slot indices line up, then the READY rows are the
        # SUPPLIERS and the deck rows become per-slot RESUPPLY (they are not substitutes — you have
        # to draw a deck copy).
        slots, elig_all = self._resolve_needs(obs, board, ready_rows + deck_rows,
                                              include_general=False)
        elig = elig_all[:len(ready_rows)]
        # Re-stamp each LINE slot with the deploy-path deadline before the resupply clamp reads
        # it: `_resolve_needs` supplies the held-PAYOFF direction, which is structurally 99 for
        # a held base. Scoped here so the discard and refresh sites are untouched.
        slots = [dataclasses.replace(s, deadline=self._deploy_line_deadline(me, _slot_cid(s)))
                 if _slot_cid(s) is not None else s for s in slots]
        resupply = self._deploy_resupply(board, slots, elig_all, len(ready_rows), deck_rows)
        capacity = max(0, _BENCH_MAX - int(board.my_bench or 0))
        assignment = needs.deploy_marginal(slots, elig, resupply, index, capacity=capacity)

        tags = set(self.functions.tags(cid)) if self.functions else set()
        # WHERE THE BODY COMES FROM decides whether the trigger exists at all, and it is a card fact
        # rather than a policy: every bench-drop Ability in the pool reads "when you play this
        # Pokémon FROM YOUR HAND onto your Bench" (`data/EN_Card_Data.csv` — Meowth ex 1071's
        # Last-Ditch Catch, Iron Leaves ex 75, Drilbur 81, Farfetch'd 123, Bloodmoon Ursaluna 135,
        # Durant ex 198, Chien-Pao 209; the two "to evolve" siblings are a different trigger again).
        # A Poffin-class fetch puts the body there from the DECK, so the clause is unsatisfiable —
        # the same DERIVED zero decision 3 gives `_SETUP_BENCH`, for the same kind of reason.
        can_fire = ("supporter_tutor" in tags and ctx == _MAIN
                    and not self._last_ditch_spent(me))
        ability_marginal, ability_odds = 0.0, 0.0
        if can_fire:
            ability_marginal, ability_odds = self._supporter_fetch_need(obs, board)

        inp = DeployInputs(
            assignment_marginal=assignment,
            ability_marginal=ability_marginal,
            ability_odds=ability_odds,
            ability_can_fire=can_fire,
            supporter_quota_spent=bool((obs.get("current") or {}).get("supporterPlayed")),
            accel_unlock=self._deploy_accel_unlock(obs, board, cid),
            exposure_prizes=self._deploy_exposure_prizes(obs, select, board, option, stat),
            phase=self._needs_phase_scale(board),
        )
        value = deploy_value(inp)
        return {"cid": cid, "capacity": capacity, **value.working()}

    def _supporter_fetch_need(self, obs: dict, board: Board):
        """``(worth marginal, odds)`` for a bench-drop Supporter tutor — decision 3's Ability leg.

        WHAT the fetch is worth is the best need a Supporter can fill that nothing held already
        covers (`draw_engine` / `supply_wincon`, the kinds `supporter_tutor` supplies). WHETHER it
        lands is the Deck-Content Odds that such a Supporter is still in deck. Both are RANKED
        reads, so they weight the leg and never gate it (ADR-0074).

        This is what makes "bench it only when we need a SPECIFIC Supporter" arithmetic: a position
        whose draw need is met scores 0 however certainly the deck holds one.

        The two slots are built HERE rather than looked up in `_resolve_needs`' output, and that is
        the whole point. That resolver derives slots FROM THE HELD ROWS — `draw_engine` is emitted
        only `if engines:` (I hold an engine) and `supply_wincon` only `if tutors:` (I hold a tutor).
        Correct for keep-value, where a slot exists to price a card you have; exactly inverted for
        this question, where the need exists BECAUSE I hold nothing that meets it. Asking the
        resolver for an UNCOVERED slot of those kinds is therefore near-unsatisfiable, and the leg
        measured 0 on every board — the real mega_lucario deck holding six Supporters included.
        Slot VALUES still come from `needs`, so the two derivations cannot drift.

        Odds range over the DECKLIST, not `board.deck_known_counts`: the counts are empty until the
        tracker anchors, and iterating them zeroed the leg whenever tracking was unavailable —
        gating on a missing signal, which is the fail direction ADR-0074 forbids. A provably-gone
        Supporter is dropped (`deck_empty_ids`, the SOUND read); otherwise
        `deck_contains_probability` already returns 1.0 when the odds are uncomputable."""
        from common import needs
        me = self._my_player(obs)
        hand_ids = list(board.hand_ids or ())

        def _held_engine_supporter() -> bool:
            for cid in hand_ids:
                st = self.stats.get(cid) if self.stats else None
                tags = set(self.functions.tags(cid)) if self.functions else set()
                if "engine" in self._roles_of(cid):
                    return True
                if (st is not None and getattr(st, "is_supporter", False)
                        and (_ENGINE_KEEP_TAGS & tags) and "hand_disruption" not in tags):
                    return True
            return False

        def _held_tutor() -> bool:
            return any("tutor" in self._roles_of(cid)
                       or ({"rush_evolve", "tutor_mega"}
                           & (set(self.functions.tags(cid)) if self.functions else set()))
                       for cid in hand_ids)

        draw_need = 0.0
        if not _held_engine_supporter():
            online = sum(1 for pid in board.in_play_ids if "engine" in self._roles_of(pid))
            draw_need = needs.draw_engine_slot(engines_online=online,
                                               value=_ENGINE_SUPPORTER_KEEP).value
        supply_need = 0.0
        if not _held_tutor():
            supply = needs.supply_wincon_slot(
                wincon_in_hand=bool(getattr(board, "wincon_in_hand", False)), target_reachable=True)
            supply_need = supply.value if supply is not None else 0.0
        if draw_need <= 0 and supply_need <= 0:
            return 0.0, 0.0

        # Match the need against the Supporters the deck ACTUALLY holds, one at a time, instead of
        # asserting the slot's tier and then asking separately whether "a Supporter" survives. A need
        # no reachable Supporter can fill is not a need this Ability answers: neither deck's Supporter
        # line reaches the win-condition (mega_lucario's Petrel is `tutor_trainer` — Trainers, not the
        # Mega), so an unconditioned `supply_wincon` claim paid +10 on every board and made Meowth ex
        # always worth benching, which is the opposite of "bench it only when we need a SPECIFIC
        # Supporter". The wincon leg now requires a Supporter whose own fetch closure reaches it.
        wincon = self._wincon_set()
        empty = getattr(board, "deck_empty_ids", frozenset()) or frozenset()
        best_value = best_odds = 0.0
        for cid in set(self.deck or ()):
            st = self.stats.get(cid) if self.stats else None
            if st is None or not getattr(st, "is_supporter", False) or cid in empty:
                continue
            tags = set(self.functions.tags(cid)) if self.functions else set()
            value = 0.0
            if draw_need > 0 and (_ENGINE_KEEP_TAGS & tags) and "hand_disruption" not in tags:
                value = draw_need
            if supply_need > 0 and wincon and (self._chain_fetch_targets(cid) & wincon):
                value = max(value, supply_need)
            if value <= 0:
                continue
            odds = (board.deck_contains_probability(cid)
                    if hasattr(board, "deck_contains_probability") else 1.0)
            odds = max(0.0, min(1.0, float(odds)))
            # Rank by the WEIGHTED yield: a slightly smaller need that is far likelier to be there is
            # the better reason to bench. The leg then reports that candidate's own pair, so the odds
            # never travel attached to a need some other Supporter would have filled.
            if value * odds > best_value * best_odds:
                best_value, best_odds = value, odds
        return float(best_value), float(best_odds)

    def _needs_phase_scale(self, board: Board) -> float:
        """`needs.phase_scale` off the live board — the prize-proximity sharpener the exposure leg
        rides. Neutral (1.0) when the race read is unavailable, so a missing signal never inflates
        or deletes the term."""
        from common import needs
        try:
            return float(needs.phase_scale(
                race_ahead=getattr(board, "race_ahead", None),
                opp_prizes_remaining=int(getattr(board, "opp_prizes_remaining", 0) or 0)))
        except Exception:
            return 1.0

    def _deploy_accel_unlock(self, obs: dict, board: Board, cid) -> float:
        """Decision 8's accel-unlock leg: the DAMAGE the Attach Budget realises because a legal
        landing spot now exists.

        The value belongs to the ACCELERATOR's stranded Energy, not to the recipient's own role —
        which is why this is not a tier bump on the body's line slot. `_recover_units` already prices
        a rider's real yield under three bounds (printed ceiling, matching fuel in the source zone,
        and the recipients' remaining NEED), and its need bound is exactly what makes a bench-targeted
        rider credit 0 on an empty Bench. So the counterfactual is that same function evaluated on the
        board WITH the candidate benched, which is ADR-0069's `this_turn` shape applied to a deploy.

        Three behaviours fall out instead of being asserted, and they are the flat +20 rung's
        hand-written stand-down conditions:

        * 0 when the accelerator is not Active (`accel_recipient_missing` is False — nothing stranded);
        * 0 when a recipient is already benched (same signal — the Energy already lands);
        * PROPORTIONAL to the rider's real yield, so a 3-Energy Aura Jab pays more than a 1-Energy
          trickle, which the flat rung could not express at all.

        Priced per Energy at `ENERGY_RECOVER` — the shipped, DERIVED median damage-per-Energy over
        every attack costing >= 2 (`160/3`, ADR-0078 via Issue #172) — rather than a constant invented
        for this leg. Damage-denominated already, so it does NOT ride the deploy band."""
        if not board.accel_recipient_missing or not self.stats or cid is None:
            return 0.0
        stat = self.stats.get(cid)
        if stat is None or not getattr(stat, "is_pokemon", False):
            return 0.0
        if cid not in self._line_member_set():        # only a Line member receives (the glossary term)
            return 0.0
        active = self._my_active(obs)
        aid, best = None, 0.0
        for candidate in (getattr(self.stats.get((active or {}).get("id")), "attacks", None) or ()):
            st = self._attack_stat(candidate)
            if st is not None and getattr(st, "recoverN", 0) > 0:
                aid = candidate
                break
        if aid is None:
            return 0.0
        # The hypothetical board: the candidate is on the Bench, so the rider has somewhere to land.
        hypo = copy.deepcopy(obs)
        me = hypo["current"]["players"][hypo["current"].get("yourIndex", 0)]
        me["bench"] = list(me.get("bench") or []) + [{"id": cid, "hp": getattr(stat, "hp", 0),
                                                      "energies": [], "appearThisTurn": True}]
        units = self._recover_units(aid, {}, board, hypo)   # dmg_ctx unused by the fuel/need bounds
        best = max(0.0, float(units)) * ENERGY_RECOVER
        return best

    def _deploy_exposure_prizes(self, obs: dict, select: dict, board: Board, option: dict,
                                stat) -> float:
        """The exposure leg's prize-equivalents (decision 5): the Prize-Path DELTA, and nothing else.

        How much does benching this body shorten the opponent's cheapest route (`_bench_path_delta`)?
        Sharp, board-aware, and zero against a body they cannot reach.

        **Where the Path cannot be read, this contributes ZERO** — decision 6, verbatim: *"a term that
        cannot be computed contributes ZERO, never a guess."* That matters in practice rather than in
        principle: the Path is unreadable on 189 of the corpus's non-Set-Up frames (both pregame
        Actives face down is the obvious case, but far from the only one).

        A FALLBACK stood here and is now DELETED, and the history is worth keeping because it is a
        lesson about scope. It guessed the body's own prize liability — the excess over a 1-prize
        body — and was added for ONE reason: at `_SETUP_BENCH` a derived-zero Ability leg plus a zero
        exposure lands at exactly 0.0, and the optional-select take-fewer drops only `score < 0`, so
        Meowth ex survived the pregame on `setup_bench_decline_f3`. Decision 9 now refuses every
        pregame placement by RULE, so that reason is gone — and with it went two more pregame patches
        that had accreted on the same spot (a `setup_placed_ids` redundancy charge, and before it a
        flat full-prize Set-Up charge measured and rejected for also declining the win-condition Line
        base). Amendment F was a fourth, proposed and withdrawn the same day.

        Removing it was checked, not assumed: both ADR-0072 gates still PASS and the suite stays
        green, so the guess was carrying none of the rulings. Four patches on one context, none of
        them load-bearing, is what a missing rule looks like from the inside.
        """
        delta = self._bench_path_delta(obs, select, option, stat, board)
        if delta > 0.0:
            return delta
        return 0.0                         # unreadable Path: decision 6 says ZERO, never a guess

    def _attach_value_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """The ATTACH decider's contribution to an option's score (kill-switch `attach_value`,
        shipped ON). 0 when the switch is OFF — DEGRADED MODE, not a rollback: the rungs this
        replaced are deleted, so OFF means attach endorsements go SILENT and the surviving structure
        rungs decide alone. Also 0 off an energy-attach option and on a Tool (`_attach_value`
        abstains). Prize math stays OUT (ADR-0069 §6) — the race belongs to one scalar, in Phase 2.

        Signed like the ADR-0062 tacticals and — unlike every shadow-era fold — allowed to go
        NEGATIVE, which is what lets the decider score an attach below ending the turn."""
        row = self._attach_decision(obs, select, board, option)
        return 0.0 if row is None else row["tactical"]

    def _attach_working(self, obs: dict, select: dict, board: Board, options: list):
        """The attach decider's LEGIBLE WORKING (ADR-0069 §9): the per-option axes rows for every
        energy-attach option on the menu, attached to the decision record.

        This replaces the fourth shadow and its self-referential agreement bit — one emission path
        carrying one truth. The rows are the substrate the value-working emitter (#146) and the
        term-level blunder loop (#148) consume: a reader sees WHICH axis carried a pick, not just
        that it won. A Pokémon Tool ABSTAINS (not Energy) and is counted, never priced. None off an
        attach menu or mid-sim (`self._planning`), so the wire key stays sparse."""
        if self._planning:
            return None
        ctx = select.get("context")
        attach_idx = [i for i, o in enumerate(options)
                      if o.get("type") == _ATTACH or (ctx == _ATTACH_FROM and o.get("type") == _CARD)]
        if not attach_idx:
            return None
        rows, abstained = [], 0
        for i in attach_idx:
            row = self._attach_value(obs, select, board, options[i])
            if row is None:                                    # a Tool abstains — no row
                abstained += 1
                continue
            row["i"] = i
            rows.append(row)
        return {"eq": rows, "abstained": abstained} if rows else None

    def _recover_units(self, attack_id, dmg_ctx: dict, board: Board, obs: dict) -> float:
        """Energy this attack's accel rider would actually attach AND that a recipient can
        actually USE — the development the Tactical layer credits (Aura Jab / Turbo Flare:
        attack + accelerate).

        Three independent bounds, all closed-form:
          1. `recoverN`   — the card's printed ceiling (Aura Jab: "attach up to 3").
          2. the matching Basic-Energy FUEL in the rider's SOURCE zone (`recoverSource`):
             "discard" → my open discard (`my_discard_basic_energy`, ADR-0061: re-sourced from the
             Board so it is the one truth for my discard fuel — `_damage_context` keeps its own
             attacker-relative copy because it must also serve the Incoming direction);
             "deck" → the whole-deck search's pool (`_deck_basic_energy_fuel`: the EXPECTED count
             off the one Count Triple derivation, ADR-0077 — a ranked count consumer reads
             `expected`, and anchored the leg collapses to the exact integer).
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
            return 0.0
        if getattr(st, "recoverSource", None) == "deck":
            fuel = self._deck_basic_energy_fuel(st.recoverEnergyType)   # EXPECTED — fractional
        else:
            by_type = (board.my_discard_basic_energy or {})             # the discard is PUBLIC: exact
            fuel = (by_type.get(st.recoverEnergyType, 0) if st.recoverEnergyType is not None
                    else sum(by_type.values()))
        need = self._recover_recipient_need(st, board, obs)
        return max(0.0, min(float(st.recoverN), float(fuel), float(need)))

    def _deck_basic_energy_fuel(self, etype) -> float:
        """Matching Basic Energy a whole-deck search rider (Turbo Flare) can EXPECT to still find in
        my deck — `CountTriple.expected` off the ONE `MySide.deck_energy_counts` derivation
        (ADR-0077 decision 3).

        A COUNT question, so it reads the count leg. `p_any` answers *is there at least one?* and
        weighting a full `recoverN` by it would claim "P(≥1) odds of finding ALL of them"; the
        provable `floor` this replaces answered a question nobody asked — it reads 0 for every
        realistic suite still behind hidden prizes (3 unseen Water behind 5 prizes on
        `82756664|1|decision|97`, a deck 99.75 % certain to hold Water), which zeroed
        `min(recoverN, fuel, need)` and killed the accel dividend outright (Issue #172).

        `etype` None is an UNTYPED rider (Turbo Flare, Whimsicott ex's Energy Gift — "search your
        deck for up to 3 Basic Energy cards"), which takes the cross-type union. That union is EXACT
        rather than a second instrument: every type's leg divides the same
        `(deck_count, prizes_hidden)`, so `Σₜ expectedₜ == expected(Σₜ unseenₜ)` — the identity that
        licenses on `expected` what ADR-0074 decision 6 forbids on `p_any`.

        No regime branch: anchored, the legs collapse to the exact integer on their own, so the old
        `deck_known_counts` short-circuit is subsumed rather than replaced. 0.0 with no StateModel."""
        model = self._state_model
        if model is None:
            return 0.0
        counts = model.mine.deck_energy_counts
        if etype is None:
            return float(sum(c.expected for c in counts.values()))
        triple = counts.get(etype)
        return float(triple.expected) if triple else 0.0

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
        recoil = self.combat.rider_recoil(attack_id)
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
        benched copy restores the attack (the rung is DELETED, ADR-0100 §11 — the swap is
        now emergent from destination value minus retreat cost)."""
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

        DELEGATES to `model.theirs.turns_to_afford` (Threat-Clock unification S1c,
        docs/plans/opponent-value-equation-unification.md; re-pointed off the raw oracle onto the
        SNAPSHOT by POC-T1, Issue #260): the deny-clock's energy/evolve model lives on the KO oracle
        beside `incoming` — the Threat Clock's two legs, one home — and the snapshot supplies the
        forward index and the discard the read needs, so no caller assembles them by hand. The slow
        deny policy is the default 1-attach/turn.

        **Their DISCARD RECURSION is now modelled** (Issue #204, landed with this migration): the two
        `discard_energy_recur` lines reload outside the attach quota, so the bare quota under-states
        their clock rather than over-stating it. Their deck-search accel (Punk Up class) is still not
        on THIS leg — it enters the `charged` budget instead (Issue #257), which is the read that can
        express a Supporter quota; leaving it off here is the fail-closed direction for a deny slot.

        None — the caller emits NO deny slot — when there is no snapshot: a board that never went
        through `_board()` has no opponent side to read, and the fail-closed answer is the same one an
        unknown stat gives."""
        model = self._state_model
        if model is None:
            return None
        return model.theirs.turns_to_afford(p)

    def _unfavored(self, board: Board) -> bool:
        """The Read says the straight race loses (Lever A, ADR-0026) — a compiled favorability at or
        below `_POSTURE_UNFAVORED`, backed by enough coverage to trust the prior."""
        return (board.matchup_coverage >= _POSTURE_MIN_COVERAGE
                and board.favorability <= _POSTURE_UNFAVORED)

    def _denial_play_tactical(self, obs: dict, board: Board, ctx) -> float:
        """Value of PLAYING an energy-denial Item (ADR-0062): what the strip actually takes away,
        priced by its odds, net of keeping the card.

            coin_odds(card) * _DENIAL_PLAY_W * (unfavored?) * value  -  _DENIAL_ITEM_COST

        where ``value`` is `K x relevance` (ADR-0080, Issue #187). It was the ADR-0062 damage
        magnitude `opp_denial_best` until Issue #228 armed the flag and deleted that oracle; OFF now
        stands the rung down entirely — DEGRADED MODE, never a rollback.

        Silent unless the card is `energy_denial`. A whiff (value 0 — surplus Energy, no affordable
        attack, or the only energized body is one I am about to KO) still pays the keep price and so
        prices at **-`_DENIAL_ITEM_COST`**, which DECLINES. It used to short-circuit to a bare 0.0,
        and this docstring used to claim that "prices at 0 and is held" — it did not: `_finish_turn_last`
        promotes only on `score > 0`, so a 0.0 free Item landed in the last tier TIED with End and
        stable score order played it by option index (Issue #228; the asymmetry ADR-0084 decision 8
        knowingly handed forward). Declining REQUIRES a STRICTLY negative score, not merely a
        non-positive one. Half of all Crushing Hammers do nothing whatever the board looks like, so
        the coin is priced here rather than absorbed into a tuned constant.

        The unfavored Read (Lever A) SCALES this value and is never added beside it — see
        `_DENIAL_UNFAVORED`. A multiplier cannot resurrect a hold; the flat rung it replaces did
        exactly that, and played a Hammer into a KO turn against a bare bench (ms 83968638 f17)."""
        if ctx.option_type != _PLAY or "energy_denial" not in ctx.tags:
            return 0.0
        # ARMED (ADR-0080, Issue #187): `K x relevance` replaces the damage magnitude. Same SHAPE —
        # odds x weight x value - keep price — so the whiff hold, the Lever A scaling and the
        # `_finish_turn_last` interaction all survive unchanged; only what supplies "value" moves.
        if not self.deny_relevance:
            return 0.0          # DEGRADED MODE, never a rollback — see the flag's note in runtime.py
        # `None` on the Board is ABSENT, not zero (ADR-0093 decision 2), so it is RECOMPUTED
        # rather than read as a whiff. A genuine 0.0 survives the ladder and is a real hold.
        value = _DENY_RELEVANCE_K * self._deny_relevance_best(obs, board)
        weight = _DENIAL_PLAY_W * (1.0 + _DENIAL_UNFAVORED if self._unfavored(board) else 1.0)
        # NO whiff short-circuit. A `value` of 0 is a real read saying "nothing here", and it must
        # still pay the keep price: `odds x weight x 0 - _DENIAL_ITEM_COST` = -10.0, which DECLINES.
        # Returning a bare 0.0 here did not — `_finish_turn_last` promotes only on `score > 0`, so a
        # 0.0 free Item landed in the last tier TIED with End and stable score order played it by
        # option index. The OFF path escaped that by arithmetic accident (its magnitude is rarely
        # exactly 0 while the card is playable); a categorical [0,1] scalar is 0 routinely and by
        # design, which is what turned a latent contract violation into a live defect at arming time.
        return coin_odds(ctx.card_id) * weight * value - _DENIAL_ITEM_COST

    def _denial_target_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """Rank the Crushing Hammer's TARGET once its coin comes up heads (ADR-0062).

        The engine poses a DISCARD_ENERGY select over every Energy on the opponent's board, ordered
        OLDEST-ATTACHED FIRST. Nothing scored it: every option came back 0.0, so the argmax fell
        through to index 0 and we stripped whatever Energy happened to land first — routinely a Basic
        on a benched support mon while their Active sat one Energy above its nuke. That is the literal
        waste. Score each option by what removing it actually denies.

        The DOOMED Active scores 0 here for the same reason Deny Relevance's redundancy gate zeroes
        its row: Energy on a body I am about to knock out is not worth taking. A won flip should land
        on the bench instead of shaving a corpse.

        ARMED (ADR-0080, Issue #187) this is a **pure `argmax relevance`**, scored per OPTION rather
        than per body — which is what makes the within-body rulings expressible at all: on a Munkidori
        holding `{D}` + `{P}`, both options point at the same body, and only the Energy's own TYPE
        separates muting Adrena-Brain from shaving Mind Bend's cost. The lookup is therefore keyed on
        the option's Provider-resolved type (`_option_energy_type`), never on its position."""
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
            target, weight, key = next((p for p in (opp.get("active") or []) if p), None), 1.0, \
                ("active", 0)
        elif area == _BENCH:
            bench = opp.get("bench") or []
            idx = option.get("index", -1)
            target = bench[idx] if 0 <= idx < len(bench) else None
            # No area weight at all — a PURE `argmax relevance` (user ruling, 2026-07-30). Relevance
            # already prices a benched body's slower clock through its own line scan, so discounting
            # it again double-counts. `_DENIAL_BENCH` was the OFF-path weight here and is DELETED
            # (Issue #228, directive 1); the promotion GATE carries its question on the fire rung.
            weight = 1.0
            key = ("bench", idx)
        else:
            return 0.0
        if not self.deny_relevance:
            return 0.0          # DEGRADED MODE, never a rollback — see the flag's note in runtime.py
        etype = self._option_energy_type(target, option)
        rel_map = self._deny_relevance_map(obs, board)
        rel = (rel_map.get(key) or {}).get(etype, 0.0)
        base = _DENIAL_TARGET_W * weight * _DENY_RELEVANCE_K * rel
        return base + self._deny_strip_delta_tiebreak(obs, board, select, key, rel, rel_map)

    def _deny_strip_delta_tiebreak(self, obs: dict, board: Board, select: dict, key,
                                   rel: float, rel_map: dict) -> float:
        """The ADR-0084 decision 2 tiebreak: among candidates tied on relevance EXACTLY, prefer the
        one whose strip actually buys turns of survival. Returns 0.0 whenever there is nothing to
        break.

        **Lexicographic, and provably so — the bound is DERIVED, not hand-set.** The adjustment is
        half the FINEST distinction relevance actually draws: the smallest positive gap between two
        distinct relevance values on this menu, falling back to ``1 / K`` — one unit of damage — when
        the menu draws no distinction at all. Since ``K x relevance`` IS the setback damage
        (ADR-0080 Amendment B) and damage is integral, two relevance values that differ at all differ
        by at least ``1 / K``, so half of that can never overtake a difference relevance settled.

        Deriving the bound rather than fixing it is the whole point: a hardcoded epsilon would be a
        constant sized against relevance's current arithmetic, and this repo has a recorded case of a
        new positive term silently voiding every guard calibrated against the previous arithmetic
        (ADR-0063). A rotted bound would begin overriding real differences with nothing failing
        loudly. Any fraction in (0, 1) is equally sound; a half is the midpoint of that proven-safe
        interval, NOT a value fitted to data.

        It is also deliberately TINY — a fraction of one damage unit. An earlier draft bounded the top
        tier by its own relevance, which is order-safe (nothing sits above it) but yields a bonus of
        ~125 score units on a real board. That would order the tie correctly and then swamp the other
        twenty-odd tacticals summed into the same option score, converting a tiebreak into a rung.

        **Why this may not GATE.** The clock reads *"does this strip delay MY defeat by a whole turn
        or more"*, which is strictly narrower than *"does this strip do anything"* — it is blind to
        Ability mutes, to sub-turn setbacks, and to any strip that wrecks their plan without touching
        their clock against me. Measured, a `strip_shift > 0` gate on the keep price would suppress
        128 of 218 relevance-positive corpus rows (ADR-0084 decision 7, the reversal). Ordering a tie
        asserts no worth; gating one asserts a great deal.

        Silent, by construction, on the cases the clock cannot speak to: a body tied with itself
        across two Energy TYPES reads ONE delta (`strip_shift` is per body, and which Energy you
        remove never changes it — 109 bodies, 0 cases), so no strict maximum exists and no preference
        is manufactured."""
        shifts = self._deny_strip_shift_map(obs, board)
        mine = shifts.get(key)
        if mine is None or not rel:
            return 0.0                            # absent reading, or nothing relevant — not a zero
        # Every candidate this menu actually offers, as (relevance, key). Peers are read off the
        # SELECT rather than off the board: an Energy no option targets is not a candidate, and
        # ranking against it would invent a tie the engine never posed.
        peers = []
        for opt in (select.get("option") or ()):
            if opt.get("type") != _ENERGY:
                continue
            area = opt.get("area")
            k = ("active", 0) if area == _ACTIVE else (
                ("bench", opt.get("index", -1)) if area == _BENCH else None)
            if k is None or k not in rel_map:
                continue
            if k[0] == "active" and board.active_can_ko:
                continue                          # the caller already scored this option 0.0 — a body
                #                                   dying to my KO is not a candidate, and letting it
                #                                   hold the largest shift would make `best`
                #                                   unreachable and silently re-mute the tiebreak on
                #                                   the live bench candidate
            r = (rel_map.get(k) or {}).get(
                self._option_energy_type(self._deny_body_at(obs, k), opt), 0.0)
            peers.append((r, k))
        tied = {k for r, k in peers if r == rel}
        if len(tied) < 2:
            return 0.0                            # nothing tied with me — relevance already decided
        best = max((shifts.get(k) for k in tied), key=lambda s: (s is not None, s))
        if best is None or best <= 0 or mine != best:
            return 0.0                            # no strict winner, or I am not it
        if sum(1 for k in tied if shifts.get(k) == best) > 1:
            return 0.0                            # tied on the clock too — no preference expressible
        # The finest distinction relevance actually draws on THIS menu; `1 / K` (one damage unit) when
        # it draws none. Never this candidate's own relevance — see the docstring. The arithmetic is
        # shared with snipe's tiebreak (`currency.tiebreak_bonus`, extracted 2026-07-30 by ADR-0085
        # Amendment H) because it is the piece most likely to drift; the GUARDS above stay separate,
        # which is the whole point of the divergence recorded there.
        from common.currency import tiebreak_bonus
        return _DENIAL_TARGET_W * tiebreak_bonus([r for r, _k in peers], _DENY_RELEVANCE_K)

    def _deny_body_at(self, obs: dict, key) -> dict | None:
        """The opponent body a ``(area, bi)`` deny key names, read off the live obs."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        area, bi = key
        bodies = [b for b in (opp.get("active") if area == "active" else opp.get("bench")) or [] if b]
        return bodies[bi] if 0 <= bi < len(bodies) else None

    def _option_energy_type(self, target: dict | None, option: dict):
        """The `EnergyType` a ``DISCARD_ENERGY`` option's own Energy contributes, or ``None``.

        Resolved through the Stat Provider from the option's ``energyIndex``, which indexes the
        body's attached **cards** (`energyCards`) — NOT its ``energies``, which lists the units those
        cards PROVIDE and so runs longer on any multi-unit Energy (Ignition provides `{C}{C}{C}`).
        Falls back to ``energies`` for a hand-built obs that carries no `energyCards`, where the two
        coincide because such fixtures hold single-unit Basic Energy.

        Never infers the type from the card id: they coincide for Basic Energy (Basic `{F}` is card 6
        and FIGHTING is 6) but that is a coincidence in the data — Ignition Energy is card id 17."""
        k = option.get("energyIndex")
        if target is None or k is None:
            return None
        cards = target.get("energyCards") or []
        if 0 <= k < len(cards):
            cid = (cards[k] or {}).get("id")
        else:
            units = target.get("energies") or []
            cid = units[k] if 0 <= k < len(units) else None
        if cid is None:
            return None
        est = self.stats.get(cid) if self.stats else None
        return getattr(est, "energyType", None) if est else None

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
        attacker's discard Energy histograms (Riptide-class scalers).

        **The assembly is no longer here** (POC-T3.5, Issue #279). This method used to BE the
        builder — the only full construction of the context anywhere — and POC-T3.5 needed a second
        one on the StateModel, because ``state_value(model)`` may read nothing but the model
        (the sole-supplier ruling — `docs/plans/value-system-poc-plan.md` §4-T0, restated on
        `state_value`) and so cannot be handed a context threaded down from here. Two
        hand-rolled builders of one fact is the exact defect ``CombatMath.card_level_damage`` was
        extracted to end (*"One fact, two hand-rolled call sites, free to drift — and they did"*),
        so the shape moved out rather than being copied: the per-side countables are gathered by
        ``_SideBase.damage_facts`` and assembled by ``common.strategy.damage_context``, and
        ``test_damage_context`` pins this method and :meth:`StateModel.damage_context` key-for-key on
        corpus frames.

        What remains here is the ADAPTER: which raw player dict is whose, which side plays the
        attacker's role, and the two per-decision facts a board snapshot cannot recover on its own —
        the tracked this-turn damage-boost PLAYS (a log fact; the played card is in the discard by
        the time anyone reads the board) and the deck tracker's anchored resolution of my deck.

        The two side views are built here rather than read off ``self._state_model``, and that is a
        SEQUENCING fact rather than a preference: ``_board`` resolves the opponent-as-attacker
        context before the snapshot exists, because the snapshot's own ``TheirSide`` takes the Read's
        clock policy as a constructor argument and the Read is resolved further down. Constructing a
        side is free (every field is lazy, ADR-0068), so the adapter pays for the fields it reads and
        nothing else.
        """
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        prizes = obs.get("own_prizes")             # exact prize multiset from deck-tracker, or None
        if prizes:                                 # keys are card ids: coerce str->int so a
            prizes = {int(k): v for k, v in prizes.items()}    # JSON-captured obs matches the deck
        mine = MySide(me, combat=self.combat, deck=self.deck, own_prizes=prizes,
                      turn_boosts=self._turn_boosts.boosts_for(yi),
                      # exact deck facts for hidden deck-discard scalers (only MY deck can be
                      # exact — tracker-anchored): the oracle turns them into a pigeonhole floor /
                      # hypergeometric EV. Resolved only when I am the attacker, because the pair is
                      # read for the attacker alone and the walk is not free.
                      deck_known=self._deck_known_counts(me, prizes) if attacker_is_me else None)
        theirs = TheirSide(opp, combat=self.combat,
                           turn_boosts=self._turn_boosts.boosts_for(1 - yi))
        atk, dfn = (mine, theirs) if attacker_is_me else (theirs, mine)
        return _assemble_damage_context(atk.damage_facts, dfn.damage_facts)

    def _my_damage_context(self, obs: dict) -> dict:
        """MY-attacker Damage Formula context for THIS decision, built at most once.

        The missing mirror of `_opp_attack_context`, which `_board` has cached per decision since
        ADR-0032 P1 for exactly this reason. My own direction had no such home, so the three
        per-OPTION consumers rebuilt it — once per ATTACK option on the menu, plus once per
        boost-card option — each getting a fresh, identical dict. That was already waste; POC-T3.5
        (Issue #279) made it worth removing by routing the gather through the model's lazy typed
        side views, which pay descriptor overhead the old raw-dict walk did not.

        **Measured** over mega_starmie's 140 committed correction frames, this tree vs `main`: the
        builder itself **0.019 → 0.084 ms/call**, one `Board` build (which calls it once, for the
        OPPONENT direction) **2.07 → 2.22 ms/decision (+7%)**, and the whole `explain()` decision
        path **5.31 → 5.33 ms** — inside run-to-run noise (the unchanged tree spread 5.05–5.71 ms
        over three passes). Without this cache the same `explain()` measured ~5.65 ms, so collapsing
        the per-option rebuilds is what keeps the extraction free where it is actually paid for.

        A **freshly-allocated dict per call is also the wrong thing to hand downstream**, which is
        the substrate's own argument one layer down: every clock read that prices a scaler carries
        the context in its memo key, and a new object cannot hit the memo the previous one filled.

        Keyed by the observation's IDENTITY and sound *because the entry holds the obs*: a cached
        object cannot be collected, so its address cannot be reused under a live entry — the same
        argument `_Lazily._key` makes for its own projection cache. A hypothetical board (a planner
        leaf, a re-scored root) is a different obs and rebuilds; the model's purity contract
        (ADR-0068) is what says the observation does not change under a snapshot.

        **The obs is not the whole key**, and the second half is a sequencing fact rather than a
        proof: the context also reads `_turn_boosts`, which is match-scoped mutable state. It is
        safe because `_evaluate` consumes the log stream ONCE, before `_board`, so the tracker
        cannot move between two reads within a decision — and because a planner leaf runs with
        `_planning` set, which suppresses `observe` outright (the engine-sim future must never
        mutate match state). Anything that later observes mid-decision must invalidate here too.
        """
        if self._my_attack_context_obs is not obs:
            self._my_attack_context_obs, self._my_attack_context = obs, self._damage_context(obs)
        return self._my_attack_context

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
            context=self._opp_attack_context)

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
        card_is_top_starter = cid is not None and cid == board.top_starter_id
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
        bench_path_delta = self._bench_path_delta(obs, select, option, stat, board)
        bench_shortens = bench_path_delta > 0.0     # the sign; one source, no drift
        promote_on_their_path = (select.get("context") in (_TO_ACTIVE, _SWITCH)
                                 and self._promote_target_on_their_path(obs, select, option, board))
        target_rank = self._target_threat_rank(
            obs, select, option, board.read, board.posture_confidence)
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
            # ADR-0085 decision 13: the `_SNIPE_THREAT_PRIZE_FLOOR = 5` PRIZE-POSITION rescue that used
            # to sit here is DELETED. It thresholded `my_prizes_remaining` to keep an ENERGIZED
            # off-path attacker out of the redundant set while I still held many prizes (f39: snipe
            # the energized ex @ 6; 83667237-107: stand down @ 4 — symmetric boards differing only in
            # prize count). The scalar now prices that same quantity CONTINUOUSLY through
            # `share = min(1, prize_value / my_prizes_remaining)`, so keeping the threshold beside the
            # graded term was two readings of one fact, one of them a magic number — the ADR-0060/0062
            # "price the quantity, don't threshold it" move, and the standing "a graded term REPLACES
            # its guard family" rule. Measured INERT before removal: floor-5 and an inert clause both
            # score 17/19 on the corpus and both pass `ms_snipe_energized_bench_f39`, the fixture
            # written to cover it.
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
                       attach_target_is_priority_wincon=attach_target_is_priority_wincon,
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
                       card_is_top_starter=card_is_top_starter,
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
                       target_kos=target_kos,                        target_is_bench_tera=target_is_bench_tera,
                       target_on_path=target_on_path, target_prize_redundant=target_prize_redundant,
                       target_is_forced_promotion=target_is_forced_promotion,
                       target_promotion_mirage=target_promotion_mirage,
                       bench_shortens_their_path=bench_shortens,
                       bench_path_delta=bench_path_delta,
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
        mirror of `_in_play_unfueled_ability_colors` (which backs the fetch side); it is the
        predicate behind the decider's **Ability Fuel** channel (ADR-0069 §1) — the value an attack
        cost structurally cannot see, and the reason the old colourless-blind waste boolean called
        Adrena-Brain's {D} 'wasted' (86091728 f19, measured −12). Sound-or-silent: False for an
        untyped/colourless Energy, a targetless option, or missing stats."""
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

    def _active_arm_available(self, ma: dict | None, bench_wincon_ready: bool) -> bool:
        """Go-down-swinging is available on the Active: it is a real ATTACKER (NOT a utility draw/tutor/stall
        body) whose HIGHEST-damage attack this turn's Attach Budget would COMPLETE, and there is no ready
        benched win-condition to retreat into instead. Distinguishes ml f21 (doomed Solrock — Cosmic Beam
        {F} completed by one {F} → arm + swing for 70) from f42 Makuhita (biggest attack costs 2, one {F}
        short) / f54 Lunatone (utility engine) and from the retreat-into-a-ready-wincon case (accel f70).
        Fail-CLOSED. Backs `arm-the-doomed-active`, `dont-feed-the-doomed`'s go-down-swinging stand-down,
        and the Lunar-Cycle famine's yield-to-arming.

        Both legs are the ONE oracle at different budgets (#142), which is what retired the last untyped
        count-vs-`maxDamageCost` matcher in the tree: the biggest attack is NOT payable on the EMPTY
        budget — the honest "with what is attached right now" reading — but IS reachable under the full
        one. So it reads typed slots rather than a bare count, honours ADR-0033 attack locks, and sees an
        accelerator's yield instead of assuming a flat one more Energy."""
        if ma is None or not self.stats or bench_wincon_ready or self._is_utility_body(ma.get("id")):
            return False
        model = self._state_model
        body = model.mine.active if model is not None else None
        stat = self.stats.get(ma.get("id"))
        aids = (getattr(stat, "attacks", None) or ()) if stat is not None else ()
        if body is None or not aids:
            return False
        biggest = max(aids, key=self._attack_damage)
        # DELIBERATE CombatMath bypass (POC-T1's documented list): the #142 EMPTY-Budget leg again —
        # the biggest attack must NOT be payable on the empty budget but MUST be under the full one,
        # and the line below takes the full one off the model.
        if self.combat.reachable_attach(ma, biggest, budget=Budget()):
            return False                    # already armed — there is nothing left for an attach to complete
        return bool(model.mine.reachable_attach(body, biggest))

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
                               my_path_prev=getattr(self, "_my_path_prev", None))

    def _snapshot(self, obs: dict, *, my_index=None, deck_empty=None, deck_known=_DERIVE,
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

        `deck_known` is the deck tracker's anchored `{card id: copies left in my deck}` and defaults
        to :data:`_DERIVE`, meaning *"work it out from this obs"* — a real sentinel rather than None,
        because None is the tracker's own answer for *"the prizes are not resolved, claim nothing"*
        and the two must stay distinguishable. `_board` passes the resolution it already computed;
        every other caller gets the same one derived here. Threaded because the model's Damage
        Formula context reads it (POC-T3.5, Issue #279) and the model cannot derive it — see
        `MySide._deck_known`.
        """
        state = obs.get("current") or {}
        mi = state.get("yourIndex", 0) if my_index is None else my_index
        if deck_empty is None or deck_known is _DERIVE:
            players = state.get("players") or []
            me = players[mi] if 0 <= mi < len(players) and players[mi] else {}
            raw_prizes = obs.get("own_prizes")
            prizes = {int(k): v for k, v in raw_prizes.items()} if raw_prizes else raw_prizes
            if deck_empty is None:
                # `or None` collapses an EMPTY multiset, which is what this fallback has always
                # done for `deck_empty` — preserved verbatim rather than unified with the line
                # below, because changing it would move the sound emptiness oracle and this issue
                # may not move scoring. `_board` and `_damage_context` both keep `{}` as itself.
                deck_empty = self._deck_empty_ids(me, prizes or None)
            if deck_known is _DERIVE:
                deck_known = self._deck_known_counts(me, prizes)
        self._state_model = model = StateModel.build(
            obs, combat=self.combat, my_index=mi, deck=self.deck, deck_empty=deck_empty,
            deck_known=deck_known,
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

    def _board(self, obs: dict, select: dict | None = None, *, carried=None) -> Board:
        """Summarise the shared board once per decision (see Board).

        ``carried`` (a :class:`~common.state_model.CarriedState` snapshot) makes the build PURE
        (ADR-0068 decision 2): the two hysteresis memories — the phase Schmitt trigger and the
        Prize-Path stickiness — are then read from the snapshot instead of ``self``, and the new
        values are not written back. Callers building a HYPOTHETICAL board pass it, which is what
        retires the hand-written snapshot/restore guards that each such site previously had to
        remember. A live decision passes nothing and keeps the in-order write, byte-identically."""
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
        # The StateModel for this decision (ADR-0068) — the ONE two-sided snapshot the migrated Board
        # fields below read instead of each calling its own hand-rolled helper. Construction computes
        # NOTHING (every field is lazy), so building it here costs only the fields actually read; new
        # consumers from Phase 1a on take it directly rather than going through Board at all.
        #
        # **Built HERE rather than at the top of `_board()`** (POC-T1, Issue #260). `TheirSide`'s clock
        # family takes the Read's `charged` energy policy and the forward-availability gate as
        # CONSTRUCTOR arguments (the T0 API, Issue #259), and both are resolved by the Read/Brief
        # fan-out above — so a model built before them is strictly WORSE than the CombatMath bypasses
        # it is meant to replace, which is exactly why every live consumer bypassed it. Nothing between
        # the old build site and here reads `self._state_model`, so the move is behaviour-neutral; the
        # threading below is what closes the gap.
        model = self._snapshot(obs, my_index=yi, deck_empty=deck_empty, deck_known=deck_known,
                               read=read, brief=brief,
                               matchup_plan=matchup_plan, gamma=gamma, favorability=fav,
                               matchup_coverage=cov, carried=carried)
        active_doomed = self._active_doomed(ma, oa, opp)
        active_lethal = self._active_cheap_attack_kos(ma, oa)   # its turn is done — build the successor
        # the Energy my Active can actually PAY an attack with this turn: attached + the best unspent
        # hand attach (Ignition = 3 on an Evolution) — the gust/offense affordability gate (f31)
        payable = ((model.mine.active.energy_count if model.mine.active is not None else 0)
                   + (0 if model.energy_attached
                      else self._best_hand_attach_units(          # ← StateModel (POC-T1): my hand
                          frozenset(model.mine.hand_ids),         #   and my Active's Energy both
                          self.stats.get((ma or {}).get("id")) if self.stats else None)))
        # **Famine** (#142) — "my Active cannot attack this turn", read ONCE off the model: no attack
        # reachable under the full Attach Budget, or the rules forbid one at all (`attack_blocked`).
        famine = model.mine.active_famine
        # 0 attached, yet an attack is still reachable this turn — the fact behind "go down swinging
        # rather than stall-gust". Derived here because two stall-gust rules need the identical clause.
        unarmed_but_able = (model.mine.active is not None
                            and model.mine.active.energy_count == 0 and not famine)
        base_plan = (choose_plan(state, self.strategy, self.stats) if state.get("players")
                     else Plan.SETUP)                   # the readiness core (SETUP→RACE)
        path_sig = self._path_signals(obs, me, opp, ma, oa,   # Tier-3 two-sided Prize Path (ADR-0040):
                                      len(me.get("prize") or []),   # re-derived every decision,
                                      len(opp.get("prize") or []),  # ranking data only; their-side
                                      read, gamma,                  # sees the γ-gated Read overlay (T4)
                                      carried=carried)              # snapshot ⇒ pure (ADR-0068)
        phase = self._derive_phase(base_plan, path_sig["race_ahead"], active_doomed,
                                   len(me.get("prize") or []),   # derived ADVISORY phase (hysteretic)
                                   favorability=fav, coverage=cov,  # + Tier-4 favorability (Lever A)
                                   carried=carried)                 # snapshot ⇒ pure (ADR-0068)
        opp_doomed = oa is None or (oa or {}).get("hp", 1) <= 0    # ADR-0044: forced promote next turn
        board = Board(
            opp_active_doomed=opp_doomed,
            forced_promotion_key=self._forced_promotion_key(opp, opp_doomed),
            my_bench=model.mine.bench_count,                    # ← StateModel (POC-T1): bench
            bench_full=model.mine.bench_full,                   #   occupancy has ONE derivation,
            #                                                     and `bench_full` reads the
            #                                                     engine's own `benchMax`
            my_active_id=(ma or {}).get("id"),
            my_active_energy=(model.mine.active.energy_count            # ← StateModel (POC-T1):
                              if model.mine.active is not None else 0),  #   UNITS, not typed count
            my_active_hp=(ma or {}).get("hp", 0),
            opp_bench=tuple((b.card_id, b.body.get("hp", 0)) for b in model.theirs.bench),
            turn=model.mine.turn,                               # ← StateModel: the turn/allowance
            energy_attached=model.energy_attached,              #   facts, off their one home
            supporter_played=model.supporter_played,
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
            my_prizes_remaining=model.prize_race.my_prizes_remaining,   # ← StateModel (ADR-0068):
            opp_prizes_remaining=model.prize_race.opp_prizes_remaining,  # the ONE prize-race read
            reusable_energy_in_hand=self._has_reusable_energy(me.get("hand") or []),
            recycle_dead_only=self._recycle_dead_only(me),
            active_famine=famine,                                        # ← StateModel (#142): the ONE
            active_unarmed_but_able=unarmed_but_able,
            active_attack_provable=(not model.mine.attack_blocked        # the rules first: a boost on
                                    and model.mine.reachable_attach(model.mine.active, provable=True)
                                    and not self._attack_impossible_on_menu(
                                        select, model.mine.attach_budget(model.mine.active,
                                                                         provable=True))),
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
            top_starter_id=self._top_starter_id(obs, select),
            weakest_bench_hp=self._weakest_snipe_hp(obs, select),
            strongest_forward_bench=self._strongest_forward_snipe(obs, select),
            snipe_damage=self._snipe_damage(obs, (ma or {}).get("id"), select),
            snipe_ko_available=self._snipe_ko_available(
                opp, self._snipe_damage(obs, (ma or {}).get("id"), select)),
            best_counter_slot=self._best_counter_slot(obs, select) if select else None,
            best_counter_source_slot=self._best_counter_source_slot(obs, select) if select else None,
            max_counter_move_number=self._max_counter_move_number(select) if select else 0,
            stadium_in_play=model.stadium_id,                   # ← StateModel (POC-T1): the
            opp_stadium_in_play=model.stadium_is_theirs,         #   Stadium and who owns it
            bench_wincon_ready=self._bench_wincon_ready(me),
            best_promote_slot=self._best_promote_slot(me),
            evolve_to_ready_wincon_available=self._evolve_to_ready_wincon_available(me),
            bench_wincon_prize_value=self._bench_wincon_prize_value(me),
            bench_wincon_underpowered=self._bench_wincon_underpowered(me),
            opp_cannot_punish_wincon=self._opp_cannot_punish_wincon(me, opp),
            basic_energy_in_deck=self._basic_energy_in_deck(deck_empty),
            my_discard_basic_energy=model.mine.discard_energy_counts,    # ← StateModel: both discards
            opp_discard_energy=model.theirs.discard_energy_counts,        # are PUBLIC, so sound counts
            active_best_attack_locked=self._active_best_attack_locked(ma),
            opp_has_stage2=self._board_has_stage2(opp),
            opp_has_colorless_ability=self._board_has_colorless_ability(opp),
            hand_ids=frozenset(model.mine.hand_ids),                      # ← StateModel
            search_deck_ids=(frozenset(c.get("id") for c in (select.get("deck") or [])
                                       if c and c.get("id") is not None)
                             if select and select.get("deck") else None),
            hand_basic_energy=model.mine.hand_energy_counts,               # ← StateModel
            no_supporter_in_hand=self._no_supporter_in_hand(me),
            opp_has_played_gust=self._opp_has_played_gust(),
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
            opp_has_energy_in_play=self._opp_has_energy_in_play(opp),
            opp_active_has_energy=bool(oa and (oa.get("energies") or [])),
            opp_active_can_damage_us=self._opp_active_can_damage_us(ma, oa),
            opp_hand_size=model.theirs.hand_size,               # ← StateModel (POC-T1): THE
            my_hand_size=model.mine.hand_size,                   #   supplier of BOTH hand counts
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
        # ADR-0076: the shared per-body opponent-target value, resolved ONCE per `_board()` call and
        # cached (the `_opp_attack_context` stash precedent) — both the S3a diagnostic shadow and the
        # live `gust_target` slot emission read this SAME cache rather than each re-running the
        # per-body `turns_to_ko_me` simulation from scratch.
        self._snipe_relevance_cache = {}            # per-decision, keyed by id(body) — the curve
                                                    # reads are per BODY while `_context` runs per
                                                    # OPTION, and a DAMAGE select offers the same
                                                    # bench repeatedly (ADR-0076 Amendment C's
                                                    # resolve-once-per-decision promise).
        self._snipe_peer_cache = None               # per-decision `[(relevance, priority)]` over the
                                                    # WHOLE menu, for the Brief tiebreak (ADR-0085
                                                    # Amendment H). Built once: the tiebreak is
                                                    # inherently peer-relative, so computing it per
                                                    # option would rebuild every rival's Context on
                                                    # every option — O(n^2) `_context` per decision.
        self._opponent_target_cache = self._opponent_target_rows(obs, board)
        if self.deny_relevance and self._opponent_target_cache is not None:
            # Deny Relevance, resolved ONCE per decision off that same cache (ADR-0080, Issue #187).
            # The three deny surfaces read these fields; none re-scores a body, so the ADR-0076
            # Amendment C "resolved once per decision" promise covers deny too.
            _rel_rows = self._opponent_target_cache[1]
            # The AREA weighting and its ADR-0084 decision-5 derivation now live on
            # `_best_area_weighted_relevance`,
            # so the ladder `_denial_play_tactical` reads and this per-decision build cannot drift.
            # The reading is the AFFORDABLE one, not the full one: spending the card prices only what
            # they can do NOW (ADR-0080 Amendment B). Measured on the four ADR-0062 anchors, this is
            # what keeps all four signs: f21/f29 hold (-6.50), f12 plays (+16.00), f26 plays (+0.50).
            # Full relevance here fires on f21/f29 (+2.50) off an unaffordable Phantom Dive.
            board.deny_relevance_best = self._best_area_weighted_relevance(_rel_rows, opp, oa)
            board.deny_relevance_rows = tuple(
                (r["area"], r["bi"], dict(r.get("relevance_by_type") or {}), r.get("strip_shift"))
                for r in _rel_rows)
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

    def _successor_evolvable_now(self, me: dict, cid) -> bool:
        """Can ``cid`` — a payoff sitting in my HAND — legally evolve a body I have in play **this
        turn**? A pre-evolution matching its ``evolvesFrom`` name must be on my Active/Bench AND must
        not have arrived this turn: `docs/rules.md` §4 `[RULE: rulebook L123-128]` `[ENGINE-LEGAL]`
        — *"cannot evolve a Pokémon the turn it was played/put into play."*

        Consumed by `_heal_insures_the_last_wincon` (clause 3: a successor that LANDS this turn
        means the line is not exhausted, so the heal insures nothing irreplaceable). Deliberately NOT
        `board.line_preevo_in_play`, which asks the looser *"is there anything a rush-evolve tutor
        could aim at"* and is read by other consumers. Both clauses matter: name-matching alone says
        yes on a board where the engine offers no evolve option at all (ep83117367 f34 — two Staryu,
        both benched this turn, so the held Mega Starmie ex has no playable option on the menu).

        It was also built as the URGENT succession spike's gate and REVERTED — see `line_slots`'
        docstring and ADR-0101: that narrowing contradicts the ep83037962 f49 ruling."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        base = getattr(st, "evolvesFrom", None) if st is not None else None
        if not base:
            return False
        bodies = (me.get("active") or []) + (me.get("bench") or [])
        return any(b and not b.get("appearThisTurn")
                   and getattr(self.stats.get(b.get("id")), "name", None) == base
                   for b in bodies)

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
        family (develop-the-accel-recipient, feed-the-accelerator, promote — `open-the-accelerator`
        was deleted by ADR-0079; the pregame Active pick is `Strategy.starter_priority` now)
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
        model = self._state_model
        if model is None:
            return False                                  # no snapshot → never expose on no read
        # AREA-AT-DAMAGE-TIME (ADR-0070 §9): the wincon is benched NOW, but every consumer of this
        # veto decides whether to EXPOSE it in the Active Spot (`interpose-...` stands down so
        # `promote-the-ready-wincon` wins; `dont-promote-into-their-prize-reach` stands down so the
        # promote goes through). So the opponent replies against it as the ACTIVE — the full printed
        # damage, not the bench riders. Declared explicitly: reading it as benched here would grant
        # phantom safety and expose a 3-prize wincon on a false read.
        #
        # Off the SNAPSHOT (POC-T1) with no `charged=`: the guard above already established that the
        # threaded policy IS `_incoming_budget`, so naming it again here would be a second copy of the
        # same decision — and the guard and the read could then drift apart.
        incoming = model.theirs.reachable_incoming(
            {"id": wincon.get("id"), "hp": wincon.get("hp")},
            context=self._opp_attack_context, my_benched=False)
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

    def _basic_energy_types_in_deck(self, deck_empty) -> frozenset:
        """The Basic-Energy TYPES my deck can still yield — the typed extension of
        ``_basic_energy_in_deck`` the Attach Budget's deck-fetch leg needs (issue #137).

        Same epistemic as its untyped sibling, per type: a type counts unless EVERY Basic Energy
        card id of that type is known-exhausted by the sound emptiness oracle (``deck_empty``) —
        *not-provably-empty*, never provably-present. ADR-0067 rules that split deliberately: with
        a thin 3-copy Energy suite nothing is provable before a search anchors the prizes, so a
        strict gate would zero every deck-fetch pre-anchor and re-fire the f70 false famine. The
        honest probability for a still-uncertain fetch lives in ``CombatMath.readiness_p``.
        Empty with no stats (fail-CLOSED — a stat-blind Pilot claims no fuel)."""
        if not self.stats:
            return frozenset()
        empty = deck_empty or frozenset()
        return frozenset(
            stat.energyType for cid in set(self.deck or ())
            if cid not in empty and (stat := self.stats.get(cid)) is not None
            and stat.is_typed_basic_energy)

    def _opp_has_played_gust(self) -> bool:
        """True if the opponent has played a gust (a Boss's Orders-style forced-switch) this game — a
        `gust`-tagged card sits in their discard. It means they CAN drag my benched win-condition into the
        Active and Knock it Out, so hiding the finisher on the Bench is less safe: interposing a cheap attacker
        at a promote taxes their next gust and denies the free front-line prize. False with no functions.

        Reads :attr:`TheirSide.discard_ids` (POC-T1, Issue #260). Their discard is a PUBLIC zone in
        both directions (`docs/rules.md`), so scanning it is sound knowledge rather than an estimate —
        which is exactly why it belongs on the snapshot and not in an ad-hoc walk here. The zone was
        homed at T0 and INERT; this is its first consumer."""
        model = self._state_model
        if model is None or not self.functions:
            return False
        return any("gust" in self.functions.tags(cid) for cid in model.theirs.discard_ids)

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

    # `_evolving_wincon_on_bench` was DELETED by ADR-0085 Amendment G along with the
    # `evolving_wincon_priority` kill-switch it gated. See the Board field note above.

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
        return max((self.combat.rider_snipe(aid) for aid in (stat.attacks or ())), default=0)

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

    # `_snipe_matchup_tactical` (ADR-0051's MatchupPlan snipe steer) was DELETED by ADR-0085
    # decision 5, which put it in the fold's scope alongside the six target rungs. Armed it was
    # already inert, because the steer now travels as the Brief MULTIPLIER inside
    # `snipe_relevance.target_relevance` — only the SIGN crosses the seam, with `_BRIEF_THREAT_BOOST`
    # supplying the magnitude, so no rate is invented to map a damage-scale MatchupPlan priority into
    # the [0,1] band (ADR-0065's no-fudge rule). Its positive/negative asymmetry (a positive boost
    # stands down on an ADR-0044 redundant / mirage / Tera body; a negative `avoid` always applies)
    # lives in the pure scorer now, where it is unit-testable without a board.

    def _snipe_ko_dominator(self, ctx) -> float:
        """STRUCTURAL dominator: a bench snipe that KNOCKS OUT its target is a free PRIZE.

        The armed replacement for `snipe-for-the-ko`'s +60 weight, and the same move the Tera veto
        already made — from a tuner-mutable positional weight to a KO_SCORE-class Tactical term
        (ADR-0085 decision 1). The weight form is the documented blunder class: its own rationale
        records `top-threat 30 + forced-promotion 40 + evolving-threat 45 = 115` on an un-KO-able
        Grookey out-voting `60` on the KO-able Applin (`82754241-45`, and `97-vs-72` on
        `82753102-63`). Gating each rung on its own `target_kos` was not enough, because the bonuses
        fire on a DIFFERENT body and their SUM out-voted the prize.

        As a dominator that is unrepresentable: `K x relevance` is bounded by `MAX_ATTACK_DAMAGE`
        (350), so no relevance score can approach `KO_SCORE` (1000), and no future leg or Brief
        multiplier can reintroduce the misplay. `ctx.target_kos` is already false for a benched Tera
        (it takes no damage at all), so the two dominators cannot both fire on one body."""
        return KO_SCORE if (self.snipe_relevance and ctx.target_kos) else 0.0

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
        the id/provider is missing (an unknowable body never outranks a known threat). This stays the
        generic (card-fact + Read-modulated) threat order.

        SURVIVES ADR-0085's deletion pass despite its snipe-flavoured constants, because the snipe
        target pick is no longer its only consumer — `planner.py:_ko_key_threat_lines` ranks the
        opponent bench with it for the ADR-0031 `ko_key_threat` Goal-Ladder rung (`planner_key_threat`,
        shipped ON), and `test_posture_read.py` covers its ADR-0026 lever-C read modulation. So
        `_ENERGIZED_SNIPE_TIER` and `_PREVENT_EX_SNIPE_BOOST` stay live here: they are snipe-NAMED but
        Planner-SHARED, and retiring them is a Planner behaviour change owing its own gate, not part
        of decision 5's scope."""
        cid = (poke or {}).get("id")
        if cid is None:
            return 0.0
        stat = self.stats.get(cid) if self.stats else None
        own, fwd = self._threat_damage_pair(cid, stat)
        fwd = self._read_modulated_forward(cid, fwd, read, gamma)   # lever C (ADR-0026): Read-accurate forward
        rank = float(max(own, fwd))
        rank += 0.001 * own                                   # more-evolved tie-break (Drakloak>Dreepy)
        if self.functions:
            line = {cid} | self._forward_card_ids(cid)
            my_active = self.stats.get(self._my_active_id(obs)) if self.stats else None
            if (my_active and my_active.is_ex_body                    # I attack with an ex/Mega ex …
                    and any("prevent_ex_damage" in self.functions.tags(i) for i in line)):  # … can't touch
                rank += _PREVENT_EX_SNIPE_BOOST                        # this line once evolved — kill now
        if poke.get("energies"):                              # energized = imminent: a higher snipe tier
            rank += _ENERGIZED_SNIPE_TIER
        return rank

    def _threat_own_damage(self, cid, stat) -> float:
        """A body's OWN biggest hit — see :meth:`_threat_damage_pair` for the two policies.

        Split out because ``_forced_promotion_key`` wants only this half, per benched body: asking
        for the pair there would walk each line's forward forms and throw the answer away.
        """
        if not self.scaled_threat_rank:
            return float(stat.maxDamage if stat else 0)
        return float(self.combat.threat_ceiling(
            cid, context=self._opp_attack_context))

    def _threat_damage_pair(self, cid, stat) -> tuple[float, float]:
        """``(own, forward)`` damage for the threat rank — the body's own biggest hit and the
        biggest its line evolves into.

        ``scaled_threat_rank`` ON (Issue #213) prices both through the Damage Formula against the
        live board (``CombatMath.threat_ceiling`` / ``forward_threat_ceiling``), so a scaling
        attacker is ranked by what it would actually hit for. OFF reproduces the historical
        PRINTED-only read (``CardStat.maxDamage`` + the provider's forward index) byte-for-byte,
        as the flag's incident lever.

        The printed read is why this needed fixing: it drops the Damage Formula's whole
        ``per_unit x count(variable)`` term, so Alakazam ranks at its forward index's 10 and
        Lillie's Clefairy ex at 20 — and the flat `_HAND_SIZE_ATTACKER_BOOST` that used to paper
        over the first of those covered exactly one card in the pool and nothing else.
        """
        own = self._threat_own_damage(cid, stat)
        if not self.scaled_threat_rank:
            fwd_fn = getattr(self.stats, "forward_max_damage", None)
            return own, float((fwd_fn(cid) or 0) if fwd_fn is not None else 0)
        return own, float(self.combat.forward_threat_ceiling(
            cid, context=self._opp_attack_context))

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

    # `_strongest_threat_rank` was DELETED by ADR-0085's deletion pass. It walked every benched
    # DAMAGE option to find the greatest `_target_threat_rank`, solely so `target_is_top_threat` could
    # be computed as an equality against it — a full extra pass over the bench per decision to answer
    # a question the graded scalar answers by ordering. `_target_threat_rank` / `_body_threat_rank`
    # SURVIVE: the Planner's `ko_key_threat` rung consumes them (see `_body_threat_rank`).

    def _forced_promotion_key(self, opp: dict, doomed: bool) -> int | None:
        """ADR-0044 Forced-Promotion Read: when the opponent's Active is doomed (a promotion is
        forced next turn), the body they bring up = their highest OWN-damage READY attacker on the
        Bench (printed max damage, energy-INDEPENDENT — they promote the win-condition and accelerate
        it, not the energized bench-sitter that merely happens to be affordable now). Returns
        ``id(body)`` for exact, duplicate-safe matching against the snipe option; None when not doomed
        / no benched attacker / no provider. Damage is priced by the same scaled read the snipe rank
        uses (``_threat_damage_pair``), which closes the ms f85 gap this used to defer: printed damage
        hid a hand-size attacker's whole threat, so Alakazam's line read 10.

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
            own = self._threat_own_damage(b.get("id"), stat)
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

    def _reusable_energy_id(self, hand: list):
        """The first **reusable** (non-discard) Energy card id in ``hand`` — a *typed* Energy card
        (hp 0 with a real `energyType`) that is not tagged `discard_eot`. NB the engine reports
        `energyType == 0` for Trainers *and* colourless special energies (e.g. Ignition), so a typed
        basic Energy is `energyType not in (None, 0)` — that excludes Trainers and Ignition. None when
        the hand holds none."""
        for c in hand:
            cid = c.get("id") if c else None
            if cid is None:
                continue
            stat = self.stats.get(cid) if self.stats else None
            tags = self.functions.tags(cid) if self.functions else []
            if stat and stat.hp == 0 and stat.energyType not in (None, 0) and "discard_eot" not in tags:
                return cid
        return None

    def _has_reusable_energy(self, hand: list) -> bool:
        """Is a reusable Energy in hand? The boolean projection of `_reusable_energy_id` — used to
        prefer a Basic over a discard-at-end-of-turn Energy when both are available (deck-agnostic)."""
        return self._reusable_energy_id(hand) is not None

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
        model = self._state_model
        if model is None:
            return 0
        # Off the SNAPSHOT (POC-T1). `CURRENT_FORMS_ONLY` empties the forward-availability gate,
        # which is what makes this the CURRENT-form read: the Board exposes it so a +HP Tool can test
        # a survival breakpoint against what the body in front of me hits for today, and the line it
        # becomes is `active_doomed`'s question, not this one.
        return int(model.theirs.incoming(ma, 1, bodies=[oa], charged=UNCHARGED,
                                         forward_ids=CURRENT_FORMS_ONLY,
                                         context=self._opp_attack_context))

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

    def _doom_recur_fueled(self, oa: dict | None, opp: dict | None) -> bool:
        """The opponent's Active LINE (current + forward forms) refuels from their discard
        (`discard_energy_recur` — Assemble Alloy re-attaches Basic {M} on evolving) AND that discard
        visibly holds Basic Energy — fuel the charged attach budget cannot see, so the matched relax
        must stand down to worst-case (the S2 recur read models the fuel; the doom swap only refuses
        to relax across it). False when tags/discard are unknown (no extra pessimism on no evidence)."""
        if not (oa and opp and self.functions):
            return False
        ids = {oa.get("id")} | set(self.combat.forward_card_ids(oa.get("id")))
        if not any("discard_energy_recur" in self.functions.tags(i) for i in ids if i is not None):
            return False
        return bool(self._discard_energy_counts(opp.get("discard") or [])[1])

    def _recur_fueled_oa(self, oa: dict | None, opp: dict | None) -> dict | None:
        """ADR-0076 S2 live (survival-only): augments `oa`'s energies with its discard-recur reload
        for the CHARGED relax read — the same current-form-energyType proxy the S2 shadow
        (`_recur_shadow`) already uses; precise per-form reload TARGETING (Aura Jab feeds the
        BENCH, not itself; Archaludon any {M}) stays a further refinement, not required to make the
        relax gate fuel-aware. Returns `oa` unchanged when there's no fuel, no tag, or the discard/
        stats are unknown — fail-open to the unaugmented read.

        Reads the opponent discard through `_discard_energy_counts(opp)` — the SAME source
        `_doom_recur_fueled` gates on, deliberately (the `_build_standing` / `_affords` lesson: one
        function owns the fact, so two readings cannot drift). An earlier cut read it off
        `_state_model.theirs` instead, which left a live hazard: had the two sources ever
        disagreed, `fueled` could report True while this returned `oa` unaugmented, and the relax
        would then fire on a read that never counted the fuel it stood down for."""
        if not (oa and opp and self.stats):
            return oa
        disc = self._discard_energy_counts(opp.get("discard") or [])[1]
        if not disc:
            return oa
        # DELIBERATE CombatMath bypass (POC-T1's documented list): the ONE-FACT-SOURCE rule stated in
        # this method's own docstring — the relax's `fueled` gate and this augmentation must read the
        # SAME discard, and `_doom_recur_fueled` reads it through `_discard_energy_counts(opp)`.
        fuel = self.combat.discard_recur_fuel(oa, disc, forward_ids=self._forward_card_ids)
        if fuel <= 0:
            return oa
        st = self.stats.get(oa.get("id"))
        etype = getattr(st, "energyType", None)
        return dict(oa, energies=list(oa.get("energies") or []) + [etype] * fuel)

    def _doom_relax_inputs(self, oa: dict | None, opp: dict | None) -> tuple:
        """Shared inputs for the matched-Read doom relax, read by both the live decider
        (`_active_doomed`) and its diagnostic (`_threat_shadow`) so they cannot drift: whether a
        γ-matched Brief exists (`matched`), whether the opponent's Active is a POSSIBLE
        discard-recur refueler (`fueled`, `_doom_recur_fueled`'s existing gate), and the oa dict the
        CHARGED read should actually consume (`read_oa`) — augmented with its real fuel reload only
        when `recur_fuel_relax` is armed AND fuel is possible; unaugmented otherwise (today's
        behavior, byte-identical when the kill-switch is OFF)."""
        matched = getattr(self, "_incoming_budget", None) is not None
        fueled = self._doom_recur_fueled(oa, opp)
        read_oa = self._recur_fueled_oa(oa, opp) if (fueled and self.recur_fuel_relax) else oa
        return matched, fueled, read_oa

    def _active_doomed(self, ma: dict | None, oa: dict | None, opp: dict | None = None) -> bool:
        """The opponent can KO my Active next turn (current OR forward-evolved attack).

        Two policies, γ-gated (the doom-shadow grill ruling, 2026-07-23 — the ADR-0064 §4 asymmetry,
        mirroring `_incoming_budget`):

        - **Matched Read** (`doom_matched_relax` ON + `_incoming_budget` populated + no discard-recur
          fuel, OR fuel present but quantified via `recur_fuel_relax`, ADR-0076 S2): RELAX-ONLY
          conjunction — a doom the worst-case oracle cries stands only if the CHARGED Threat-Clock
          curve confirms it (`doomed_incoming` under `_DOOM_CHARGED`: per-attack typed affordability
          at manual + one supporter-accel attach, Ignition burst on Evolutions, PLUS the recur reload
          when `recur_fuel_relax` is armed). The charged read can CLEAR a worst-case doom, never
          manufacture one — its own extra reach (the +1 supporter wild can credit a forward form the
          incumbent's `attached + 1` forward gate does not, e.g. a 1-Energy Makuhita → Wild Press
          210) must not re-open the phantom play-scared class (ADR-0064 §3; the 82525101-14
          Ultra-Ball-discard pin). On the 15-frame disagreement corpus this relaxes exactly the
          ruled-B frames (bare Terapagos ex / 0-Energy Archaludon ex) while every ruled-C frame stays
          doomed (Hammer-lanche density 600, weakness-doubled Mind Bend 120, 1-Energy Metal Defender
          220).
        - **Unmatched / fueled-with-`recur_fuel_relax`-OFF / switch OFF**: the WORST-CASE oracle,
          byte-identical (`combat.active_doomed` — no affordability charge, the hidden-Ignition
          planner_6858 lesson; docs/todo/incoming-affordability.md). Never relax on a guess."""
        ctx = self._opp_attack_context
        my_hp = (ma or {}).get("hp", 0) or 0
        model = self._state_model
        if model is None or not my_hp:
            return False                    # no snapshot / no live Active: no claim
        # BOTH legs are the SAME curve at DIFFERENT policies (POC-T1, Issue #260) — that is the
        # whole content of the fold. `UNCHARGED` is the worst-case doom ceiling the incumbent
        # `active_doomed` spelled as its own implementation; `_DOOM_CHARGED` is the matched-Read
        # relax. Reading them off one method at two policies is what makes "these two disagree on
        # 15 frames" a statement about POLICY rather than about two pieces of code.
        worst = model.theirs.doomed(ma, bodies=[oa], context=ctx)
        if not (worst and self.doom_matched_relax):
            return worst
        matched, fueled, read_oa = self._doom_relax_inputs(oa, opp)
        if not matched or (fueled and not self.recur_fuel_relax):
            return worst
        return model.theirs.doomed(ma, bodies=[read_oa], charged=self._DOOM_CHARGED, context=ctx)

    def _threat_shadow(self, obs: dict, board) -> dict | None:
        """S1b threat-clock doom SHADOW (docs/plans/opponent-value-equation-unification.md): emit the
        incumbent worst-case doom read (`active_doomed`, the decider) beside its `incoming(t=1)`-curve
        re-expression (`combat.doomed_incoming`, ceiling policy) + the agreement bit — the evidence
        bridge for routing survival through the ONE Threat-Clock curve. Deciding NOTHING.

        Sparse: None mid-sim (`self._planning`, no shadow work in rollouts) or with no live my-Active
        vs opp-Active to read. ONE divergence remains for the sweep to adjudicate before any swap:
        the current-form affordability gate (`can_pay_cheapest`) — ADR-0064 §2 kept `active_doomed`
        unconditionally worst-case. The hand-size counter was listed as a second divergence and was
        not one; see `CombatMath.doomed_incoming` (Issue #213).

        Post-swap fields (the doom-shadow grill, 2026-07-23 — `doom_matched_relax`): `doom_old` is
        the worst-case oracle COMPUTED FRESH (the Board bit is now the decided value, not the
        incumbent), `doom_charged` the `_DOOM_CHARGED` curve damage where a Read matched (None
        unmatched), `matched`/`decided` whether the γ-gate held / the charged curve decided this
        frame, and `doom_final` the live `Board.active_doomed` that consumers saw."""
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
        ctx = self._opp_attack_context
        model = self._state_model
        if model is None:
            return None
        my_hp = ma.get("hp", 0) or 0
        # Three readings of ONE curve, off the snapshot (POC-T1): the CEILING (`charged=None`, the
        # `doomed_incoming` re-expression), the DOOM policy (`UNCHARGED`, what the incumbent
        # `active_doomed` was), and the matched-Read relax budget. The pair this shadow was built to
        # compare is now one implementation, so what it still measures — and the only thing it ever
        # really measured — is the gap between two POLICIES.
        dmg = model.theirs.incoming(ma, 1, bodies=[oa], charged=None, context=ctx)
        old = model.theirs.doomed(ma, bodies=[oa], context=ctx)
        new = bool(my_hp and dmg >= my_hp)
        matched, fueled, read_oa = self._doom_relax_inputs(oa, opp)
        decided = bool(old and self.doom_matched_relax and matched
                       and (not fueled or self.recur_fuel_relax))  # relax-only: consulted iff worst cries
        charged = (int(model.theirs.incoming(ma, 1, bodies=[read_oa],
                                             charged=self._DOOM_CHARGED, context=ctx))
                   if matched else None)
        return {"doom_old": old, "doom_curve": new, "doom_incoming": int(dmg),
                "my_hp": int(my_hp), "agree": old == new, "doom_charged": charged,
                "matched": matched, "decided": decided,
                "doom_final": bool(getattr(board, "active_doomed", False))}

    def _recur_shadow(self, obs: dict, board) -> dict | None:
        """S2 discard-recur fuel SHADOW (docs/plans/opponent-value-equation-unification.md): for each
        opponent in-play body whose line refuels from its own discard (`discard_energy_recur` — Mega
        Lucario ex 678 reloads {F}, Archaludon ex 190 reloads {M}), emit the Threat-Clock reads
        WITH-vs-WITHOUT the discard fuel — `incoming(t=1)` to my Active and `turns_to_afford` — so the
        sweep can see how much the discard reservoir accelerates (lower t) and sharpens (higher
        incoming) the threat. Deciding NOTHING: the live reads pass no fuel; the shadow models it by
        augmenting a copy of the body's `energies`. Sparse: None mid-sim (`self._planning`), with no
        opponent discard Energy, or no live opponent board."""
        if getattr(self, "_planning", False):
            return None
        model = self._state_model
        if model is None or not model.theirs.discard_energy_counts:
            # ONE source for the discard (POC-T1): the shadow used to take the sparse guard off
            # `board.opp_discard_energy` and the fuel off a hand-assembled read, which is the drift
            # hazard `_recur_fueled_oa`'s own docstring warns about — the guard could pass on one
            # reading while the fuel came back 0 on the other.
            return None
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) else None
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else None
        if not opp:
            return None
        ma = next((p for p in ((me or {}).get("active") or []) if p), None)
        bodies = [p for p in ((opp.get("active") or []) + (opp.get("bench") or [])) if p]
        rows = []
        for p in bodies:
            # The CAUTION reading — "could this line refuel at all" — which is what the shadow has
            # always reported and what the doom relax gates on. The CLOCK's own reading is narrower
            # (Issue #204), and the `ttr_*` pair below is exactly that difference measured.
            fuel = model.theirs.discard_recur_fuel(p)
            if fuel <= 0:
                continue
            st = self.stats.get(p.get("id")) if self.stats else None
            etype = getattr(st, "energyType", None)
            fueled = dict(p, energies=list(p.get("energies") or []) + [etype] * fuel)
            row = {"id": p.get("id"), "fuel": fuel,
                   "ttr_plain": model.theirs.turns_to_afford(p, fuelled=False),
                   "ttr_fuel": model.theirs.turns_to_afford(fueled, fuelled=False)}
            if ma:
                row["inc_plain"] = model.theirs.incoming(ma, 1, bodies=[p], charged=None)
                row["inc_fuel"] = model.theirs.incoming(ma, 1, bodies=[fueled], charged=None)
            rows.append(row)
        return {"bodies": rows} if rows else None

    def _opponent_target_rows(self, obs: dict, board) -> tuple | None:
        """S3 opponent-target value, the SHARED per-body computation (ADR-0076): `prize_advance +
        phase × survival_shift` (`needs.opponent_target_value`) for every opponent in-play body —
        the ONE place both the S3a diagnostic (`_opponent_target_shadow`) and the live
        `gust_target` slot emission (`_resolve_needs`) read it, so they cannot drift apart.
        `survival_shift` is the turns of survival bought by removing the body (Δ
        `combat.turns_to_ko_me` via the S1 curve); `prize_advance` is its prize value (the if-KO'd
        term); `phase` is the KO-race scale (`needs.phase_scale`). A THREAT read, so it keeps the
        conservative default reading; `opp_active` is passed for the promotion gate, which opens
        correctly when the loop removes it (the replacement Active is chosen from the Bench for
        free, rulebook.txt:176). Redundancy (the ADR-0044 guards) and instrument-specifics (chip vs
        KO, reachability) are each consumer's own job, not priced here.

        Returns ``(phase, rows)``; each row carries the raw ``body`` dict, its ``area``
        (``"active"``/``"bench"``) and within-area index ``bi`` (the deny-slot key convention), plus
        ``id``/``prize``/``survival_shift``/``value``. None when sparse: no live my Active, or no
        opponent in-play bodies.

        **Runs MID-SIM** (ADR-0093 decision 3). It used to early-return `None` under the
        planner's `_planning` reentrancy flag, alongside the three SHADOWS — but this is the LIVE
        computation both the deny fire rung and the `gust_target` slot emission read, not a
        diagnostic, and withholding it mid-sim made the agent evaluate a different policy inside its
        own rollout than outside it. That is the third confirmed source of continuation collateral
        in this repo (ADR-0072 finding 2, ADR-0070 amendment H, Issue #228). The guard was a COST
        decision, not a correctness one — nothing below starts a nested engine search; `turns_to_ko_me`
        is the closed-form S1 curve. It now lives on `_opponent_target_shadow`, which is the caller
        that genuinely wants no shadow work in rollouts."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) else None
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else None
        ma = next((p for p in ((me or {}).get("active") or []) if p), None)
        active_list = [p for p in ((opp or {}).get("active") or []) if p]
        bench_list = [p for p in ((opp or {}).get("bench") or []) if p]
        bodies = active_list + bench_list
        if not (ma and bodies):
            return None
        from common import needs
        phase = needs.phase_scale(race_ahead=getattr(board, "race_ahead", None),
                                  opp_prizes_remaining=getattr(board, "opp_prizes_remaining", 0))
        model = self._state_model
        if model is None:
            return None                          # no snapshot: no target rows, no gust/deny slots
        opp_active = active_list[0] if active_list else None
        enabler = self._opp_switch_enabler()
        # Off the SNAPSHOT (POC-T1), with the counterfactual board named explicitly: the removal Δ
        # below asks the clock about a board with one of their bodies gone, which is precisely the
        # question the old model route could not express and the reason this read bypassed it.
        #
        # `charged=None` is the CEILING, stated rather than inherited. This is a THREAT read, so it
        # keeps the worst-case energy policy whatever the Read says (ADR-0064 Decision 1 keeps the
        # conservatism per-consumer); taking the snapshot's threaded budget here would silently relax
        # every gust/deny target value behind a matched Brief.
        clock = dict(bodies=bodies, charged=None, opp_active=opp_active, switch_enabler=enabler)
        base_t = model.theirs.turns_to_ko_me(ma, **clock)
        # Deny Relevance's REDUNDANCY gate (ADR-0080 step 2), resolved once for the whole decision
        # rather than per body: which opponent bodies die to our Knock Out this turn, and so deny
        # nothing. Keyed by the row's own (area, bi) convention. Only built when the read is armed.
        doomed_ids = frozenset()
        if self.deny_relevance:
            doomed_ids = (frozenset({("active", 0)} if getattr(board, "active_can_ko", False)
                                    else ())
                          | frozenset(("bench", j)
                                      for j in self._bench_doomed_by_me(ma, bench_list)))
        rows = []
        for i, b in enumerate(bodies):
            shift = model.theirs.turns_to_ko_me(
                ma, **dict(clock, bodies=bodies[:i] + bodies[i + 1:])) - base_t
            prize = model.theirs.view_of(b).prize_value
            val = needs.opponent_target_value(prize_advance=prize, survival_shift=shift, phase=phase)
            area, bi = ("active", i) if i < len(active_list) else ("bench", i - len(active_list))
            row = {"body": b, "area": area, "bi": bi, "id": b.get("id"), "prize": prize,
                   "survival_shift": shift, "value": val}
            if self.deny_strip_delta:
                row.update(self._strip_delta_terms(ma, bodies, i, phase,
                                                   opp_active=opp_active, enabler=enabler))
            if self.deny_relevance:
                row.update(self._relevance_terms(
                    b, doomed=doomed_ids, area=area, bi=bi,
                    brief_ids=getattr(board, "brief_threat_ids", ()) or ()))
            rows.append(row)
        return phase, rows

    def _best_area_weighted_relevance(self, rel_rows, opp: dict | None,
                                      oa: dict | None) -> float:
        """The best relevance achievable anywhere on their board — `Board.deny_relevance_best`.

        AREA-WEIGHTED, and deliberately so. The 2026-07-30 ruling dropped `_DENIAL_BENCH` from the
        TARGET pick (surface c), where relevance already prices a benched body's own line scan; it
        did NOT drop the question this rung asks, which is whether that benched body can REACH the
        Active position at all. ADR-0084 decision 5 answered it with ADR-0071's promotion GATE rather
        than a flat discount: a bench row counts in full when the gate is open and not at all when it
        is shut. Measured over all 21 Hammer-ruled corpus frames: ZERO sign changes vs the constant.

        Extracted from `_board()` by Issue #228 so the ladder below and the per-decision build share
        ONE definition — a second spelling of "which rows count, and how much" is exactly the drift
        that put a whiff and an absent read at the same value in the first place."""
        bodies = [b for b in ([oa] if oa else []) + list((opp or {}).get("bench") or []) if b]
        promotion_open = bool(bodies) and self.combat._promotion_open(
            bodies, oa, switch_enabler=self._opp_switch_enabler())
        return max((r.get("relevance_fire", 0.0) * (1.0 if r["area"] == "active"
                                                    else (1.0 if promotion_open else 0.0))
                    for r in rel_rows), default=0.0)

    def _deny_relevance_best(self, obs: dict, board: Board) -> float:
        """`Board.deny_relevance_best`, cached-or-computed — the fire rung's value.

        The SAME cache-or-compute ladder `_deny_relevance_map` and `_deny_strip_shift_map` carry, and
        for the same stated reason: *without the fallback an armed hand-built board would emit no
        deny read and score as a whiff, which is a silent behaviour change rather than a fail-closed
        one.* This surface was the one of the three that lacked it (Issue #228), and it is the one
        that moved three Discrimination Gate frames.

        A `None` on the Board means ABSENT, never a measured zero, so it must never be read as one —
        it is recomputed here instead. A genuine 0.0 (no Energy doing work, surplus Energy, or the
        only live body dies to my KO this turn) survives the ladder unchanged and is a real HOLD."""
        if board.deny_relevance_best is not None:
            return board.deny_relevance_best
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else None
        oa = next((p for p in ((opp or {}).get("active") or []) if p), None)
        return self._best_area_weighted_relevance(self._deny_rows(obs, board), opp, oa)

    def _deny_relevance_map(self, obs: dict, board: Board) -> dict:
        """``{(area, bi): {EnergyType: relevance}}`` — the resolved Deny Relevance read, per body.

        Prefers what `_board()` already stashed on the Board; falls back to the per-decision
        `_opponent_target_cache`, then to a fresh compute for a hand-built `board` that never went
        through `_board()` (test fixtures). Exactly the cache-or-compute ladder the `gust_target`
        slot uses — without the fallback an armed hand-built board would emit NO deny slots and read
        as a whiff, which is a silent behaviour change rather than a fail-closed one."""
        if board.deny_relevance_rows:
            return {(a, i): rel for a, i, rel, _shift in board.deny_relevance_rows}
        result = self._deny_rows(obs, board)
        return {(r["area"], r["bi"]): dict(r.get("relevance_by_type") or {}) for r in result}

    def _deny_strip_shift_map(self, obs: dict, board: Board) -> dict:
        """``{(area, bi): strip_shift}`` — the ADR-0084 **strip Δ** per body, the target pick's
        lexicographic tiebreak key. Named for the delta, never "clock": `strip_shift` is a
        delta OF `turns_to_ko_me`, not a reading of it (CONTEXT.md, The Two Clocks). Same cache-or-compute ladder as `_deny_relevance_map`, off the
        SAME rows, so the rank and its tiebreak cannot drift apart.

        A value of ``None`` means **absent, not zero** — `deny_strip_delta` is off, or the row never
        carried a reading. The distinction is load-bearing: a delta may break a tie but must never
        GATE one (ADR-0084 decision 7), and an absent reading must leave the ranking exactly as
        relevance alone ordered it."""
        if board.deny_relevance_rows:
            return {(a, i): shift for a, i, _rel, shift in board.deny_relevance_rows}
        return {(r["area"], r["bi"]): r.get("strip_shift") for r in self._deny_rows(obs, board)}

    def _deny_rows(self, obs: dict, board: Board) -> list:
        """The per-decision opponent-target rows, cached-or-computed — the one ladder both deny maps
        read. Falls back to a fresh compute for a hand-built `board` that never went through
        `_board()` (test fixtures); without it an armed hand-built board would emit NO deny slots and
        read as a whiff, which is a silent behaviour change rather than a fail-closed one."""
        result = getattr(self, "_opponent_target_cache", None)
        if result is None:
            result = self._opponent_target_rows(obs, board)
        return list(result[1]) if result else []

    def _bench_doomed_by_me(self, ma: dict | None, bench_list) -> frozenset:
        """Indices into ``bench_list`` of benched opponent bodies MY Active can Knock Out this turn.

        The bench half of the Deny Relevance redundancy gate (ADR-0080 decision 1, step 2): *"or
        maybe its a benched pokemon that we can snipe and KO. same thing, no hammer on that specific
        pokemon."* The Active half is `board.active_can_ko` (ADR-0063's drop, which ADR-0078's
        re-audit ruled NOT subsumed and required to survive any swap).

        Reads the biggest bench REACH among the attacks my Active can currently AFFORD — the same
        `attack_cost(aid) <= attached` affordability test `can_ko_affordable` uses, and the same
        instantaneous framing as the rest of deny (the user's ruling of 2026-07-28): what we can do
        with the board as it stands, crediting no attach of our own.

        Reach is the max of the single-target snipe rider and the DISTRIBUTABLE spread total, because
        a spread reads *"in any way you like"* and so may land entirely on one body. Covering only
        the snipe rider would have left the gate blind on Dragapult ex — whose Phantom Dive is a
        6-counter spread, not a snipe — i.e. blind on one of our own three decks.

        Fail-open to the empty set without stats: an unknown attacker is not evidence that a body is
        dying, and this gate SUPPRESSES relevance, so failing open keeps the Hammer's value rather
        than inventing a corpse."""
        st = self.stats.get(ma.get("id")) if (ma and self.stats) else None
        if not st:
            return frozenset()
        attached = len((ma.get("energies") or []))
        reach = max((max(self.combat.rider_snipe(aid), self.combat.rider_spread(aid))
                     for aid in (getattr(st, "attacks", ()) or ())
                     if self.combat.attack_cost(aid) <= attached), default=0)
        bench = [(b.get("id"), b.get("hp", 0)) for b in bench_list]
        return self.combat.bench_ko_indices(bench, reach)

    def _snipe_relevance_terms(self, obs: dict, select: dict, board: Board, option: dict,
                               ctx) -> dict | None:
        """The SNIPE instrument's value — **Snipe Relevance** (ADR-0085, Issue #188;
        `common/snipe_relevance.py` owns the scoring, this owns the board plumbing).

        Mirrors `_relevance_terms` for the sibling instrument. Returns None off a bench-DAMAGE option
        or without the stats provider, so the caller contributes nothing rather than guessing.

        Everything `their_plan` needs comes off the **Threat Clock** rather than
        `_body_threat_rank` (ADR-0045's own thesis, and ADR-0085 decision 3), which is what wins the
        self-lock and damage-scaler reads for free instead of re-deriving them. The two policies are
        SPLIT on purpose (decision 8) and must not be collapsed by a later refactor:

          * `incoming(..., charged=None)` — the CEILING, for how HARD they can hit. Under-counting
            their reach feeds them the wincon (ADR-0064's hidden-burst lesson).
          * `turns_to_afford(..., attaches_per_turn=1)` — the SLOW rules-floor clock (`rules.md` §3)
            for how SOON. It credits no ATTACH acceleration, but it does credit the line's own
            discard recursion (Issue #204), because that reload is a printed card effect outside the
            attach quota rather than a guess about their hand. Over-counting their speed only wastes
            a rider, so this leg's fail direction tolerates the extra credit.

        The route side reads `combat.turns_to_ko`, which prices the body **as an Active** against my
        real attack — the *"once it moves into active"* the user's ruling asks for — rather than
        counting rider hits, and over a TWO-chip window because a one-chip read scores `82756021-57`'s
        correct answer at zero."""
        if not (self.snipe_relevance and self.stats):
            return None
        if ((select or {}).get("context") != _DAMAGE or option.get("type") != _CARD
                or option.get("area") != _BENCH):
            return None      # the incumbent rungs' exact scope — a non-CARD bench option at a DAMAGE
                             # select was scored by nothing before and must stay that way
        body = self._option_pokemon(obs, select, option)
        if not body:
            return None
        cache = getattr(self, "_snipe_relevance_cache", None)
        if cache is None:
            cache = self._snipe_relevance_cache = {}
        key = id(body)
        if key in cache:
            return cache[key]

        from common import snipe_relevance as srel
        ma, oa = self._my_active(obs), self._opp_active(obs)
        if not ma:
            return None

        cid = body.get("id")
        # `context=` is what makes the Damage Formula's `per_unit x count(variable)` term visible
        # (Issue #213). WITHOUT it a bench-count scaler prices at its PRINTED base — Lillie's
        # Clefairy ex reads 20 instead of the up-to-200 it actually hits for — so `imminence` and
        # `forced`, which both take this number, under-read a whole card class by 10x. Every other
        # decider-facing `incoming` call in this file passes the `_board` stash; this one must too.
        # ADR-0085 decision 7 bar 4 named exactly this case and could only be met once Issue #213's
        # combined-bench scaler family landed, which it now has.
        #
        # Off the SNAPSHOT (POC-T1). `bodies=[body]` is the point: this instrument asks what THIS ONE
        # body threatens, not what their whole board does, and `charged=None` states the CEILING
        # policy the docstring above rules for it rather than inheriting the Read's budget.
        model = self._state_model
        if model is None:
            return None                      # no snapshot: the instrument contributes nothing
        incoming = model.theirs.incoming(ma, 1, bodies=[body], charged=None, opp_active=oa,
                                         context=self._opp_attack_context,
                                         switch_enabler=self._opp_switch_enabler())
        tta = model.theirs.turns_to_afford(body)
        # The forward leg reads through Issue #213's pair accessor for the same reason and behind the
        # same `scaled_threat_rank` lever, rather than the provider's PRINTED forward index (which
        # drops the scaling term outright — it returns 0 for card 272).
        forward_damage = 0.0
        if cid is not None:
            _own, forward_damage = self._threat_damage_pair(cid, self.stats.get(cid))

        # The route side. `rider` is my repeatable bench reach; `my_energy` is what my Active carries
        # NOW, so `turns_to_ko` reads the attack I can actually afford (on `82756021-57` that is
        # Jetting Blow 120, not Nebula Beam 210 — which is why that body reads 3 turns, not 2).
        rider = board.snipe_damage or 0
        hp = body.get("hp") or 0
        my_energy = len((ma.get("energies") or []))
        t_before = self.combat.turns_to_ko(ma.get("id"), my_energy, body)
        chipped = dict(body)
        chipped["hp"] = max(1, hp - 2 * rider)
        t_after = self.combat.turns_to_ko(ma.get("id"), my_energy, chipped) if (hp and rider) else None

        # `_PREVENT_EX_SNIPE_BOOST` re-homed to the ROUTE side (decision 9): a line reaching
        # `prevent_ex_damage` does not hit me harder once evolved, it becomes IMMUNE to my ex
        # attacker — so my route through it closes permanently and this turn is the last one it exists.
        my_stat = self.stats.get(ma.get("id")) if ma.get("id") is not None else None
        prevents_my_ex = bool(
            self.functions and my_stat and getattr(my_stat, "is_ex_body", False) and cid is not None
            and any("prevent_ex_damage" in self.functions.tags(i)
                    for i in ({cid} | self._forward_card_ids(cid))))

        # The ADR-0051 MatchupPlan steer, folded in as the Brief MULTIPLIER (decision 5). Its
        # positive/negative asymmetry lives in the pure scorer, where it is testable.
        # Only the SIGN travels: `_BRIEF_THREAT_BOOST` supplies the magnitude, so no rate is invented
        # to map a damage-scale MatchupPlan priority into the [0,1] band (ADR-0065's no-fudge rule).
        priority = 0.0
        plan = getattr(board, "matchup_plan", None)
        if plan is not None and cid is not None:
            priority = plan.priority(cid) or 0.0

        got = srel.target_relevance(
            plan=srel.TheirPlanInputs(
                incoming_damage=incoming, turns_to_afford=tta,
                forward_damage=forward_damage,
                is_strongest_forward=bool(getattr(ctx, "target_is_strongest_forward", False)),
                forward_form_in_play=bool(getattr(ctx, "target_forward_form_in_play", False)),
                is_forced_promotion=bool(getattr(ctx, "target_is_forced_promotion", False)),
                prize_redundant=bool(getattr(ctx, "target_prize_redundant", False)),
                promotion_mirage=bool(getattr(ctx, "target_promotion_mirage", False)),
                is_tera=bool(getattr(ctx, "target_is_bench_tera", False)),
                brief_priority=priority),
            route=srel.MyRouteInputs(
                turns_to_ko_before=t_before, turns_to_ko_after=t_after,
                hp_remaining=hp, rider_damage=rider,
                prize_value=model.theirs.view_of(body).prize_value,
                prizes_needed=max(1, int(getattr(board, "my_prizes_remaining", 6) or 6)),
                prevents_my_ex=prevents_my_ex),
            brief_boost=_BRIEF_THREAT_BOOST)
        cache[key] = got
        return got

    def _snipe_relevance_tactical(self, obs: dict, select: dict, board: Board, option: dict,
                                  ctx) -> float:
        """`K x relevance`, the armed snipe target score (ADR-0085 decisions 1-13).

        `K = MAX_ATTACK_DAMAGE`, which is the normalizer itself, so `K x relevance` lands back in
        DAMAGE units and the armed term is a strict generalisation of the band the deleted rungs
        competed in rather than a re-scaling — the identity ADR-0080 Amendment B derived for deny and
        ADR-0085 Amendment A1 adopted here. It deliberately does NOT go through
        `currency.PRIZE_DAMAGE_RATE`: relevance is a `[0,1]` scalar, not a prize-denominated value, so
        a prizes-to-damage rate would convert nothing.

        Stands down on a KO target exactly as every positional rung did — `snipe-for-the-ko` and the
        Tera veto remain STRUCTURAL dominators outside the scalar (decision 1)."""
        if board.snipe_ko_available:
            return 0.0
        got = self._snipe_relevance_terms(obs, select, board, option, ctx)
        if not got:
            return 0.0
        return _SNIPE_RELEVANCE_K * got["relevance"]

    def _snipe_brief_priority(self, obs: dict, select: dict, option: dict, plan) -> float:
        """This option's signed MatchupPlan/Brief priority, or 0.0 when nothing is briefed.

        One owner, because the tiebreak reads it twice — once for the candidate and once per peer —
        and the two readings MUST agree exactly: the comparison is `!=` against a strict maximum, so
        any drift between them silently turns a winner into a non-winner."""
        cid = (self._option_pokemon(obs, select, option) or {}).get("id")
        if plan is None or cid is None:
            return 0.0
        return float(plan.priority(cid) or 0.0)

    def _snipe_brief_peers(self, obs: dict, select: dict, board: Board) -> list[tuple[float, float]]:
        """``[(relevance, brief_priority)]`` over every bench target this menu offers, once per
        decision. Peers are read off the SELECT, not off the board: a body no option targets is not a
        candidate, and ranking against it would invent a tie the engine never posed."""
        cached = getattr(self, "_snipe_peer_cache", None)
        if cached is not None:
            return cached
        plan = getattr(board, "matchup_plan", None)
        peers, seen = [], set()
        for o in (select.get("option") or ()):
            if o.get("type") != _CARD or o.get("area") != _BENCH:
                continue
            # DEDUPED by bench slot, as the deny sibling dedupes by its `(area, index)` key. Two
            # options naming the SAME body would otherwise enter twice, and the strict-maximum test
            # (`sum(p == best) > 1`) would read that duplicate as a rival and silently mute the
            # tiebreak on a board where the Brief does express a preference. No corpus DAMAGE frame
            # offers a body twice today, so this is a guard against a shape the engine may pose
            # rather than a fix for one it does.
            slot = o.get("index")
            if slot in seen:
                continue
            got = self._snipe_relevance_terms(obs, select, board, o,
                                              self._context(obs, select, board, o))
            if got is None:
                continue
            seen.add(slot)
            peers.append((got["relevance"], self._snipe_brief_priority(obs, select, o, plan)))
        self._snipe_peer_cache = peers
        return peers

    def _snipe_brief_tiebreak(self, obs: dict, select: dict, board: Board, option: dict,
                              ctx) -> float:
        """The **Brief Tiebreak** — ordering BENEATH relevance, never a term in it (ADR-0085
        Amendment H).

        Relevance stays the sole ranker. Among options it scores EXACTLY equal, the signed
        MatchupPlan/Brief priority orders them instead of the engine's option index. Because this is a
        comparison key rather than a value, decision 2's conjunctive product is untouched and *"either
        alone is worthless"* stays literally true.

        **Why it exists.** The deletion pass (Amendment E) turned the Brief steer from a signed ADDEND
        into a MULTIPLIER, and a multiplier cannot express a preference over a zero: where `their_plan`
        is 0 for every target the product is 0 for all of them however the Brief reads them, and the
        pick fell to option index (Amendment E3).

        ⚠️ **Diverges from `_deny_strip_delta_tiebreak` on exactly one line, deliberately.** That sibling
        guards ``not rel -> 0.0`` (*"nothing relevant — not a zero"*); this one fires at zero. The
        difference is the SOURCE of the ordering signal, not taste: `strip_shift` is DERIVED from the
        same board, so ordering by it at zero relevance would re-assert a fact relevance already priced
        at nothing, whereas the Brief priority is INDEPENDENT AUTHORED scouting — a zero `their_plan`
        says the threat clock is silent about this body, not that the Brief is wrong about it.
        Decision 2's *"authored scouting can never promote a whiff"* is preserved exactly as written:
        it protects a whiff from outranking a NON-whiff, and on an all-zero menu there is nothing of
        value to promote it above.

        **No sign guard, unlike the sibling's ``best > 0``.** A strict maximum is the whole test. That
        admits the neutral-over-``avoid`` case — two bodies tied on relevance where the Brief only
        says *don't poke the draw engine* — which a positive-only guard would drop, and which is the
        half of the ADR-0051 steer that survives on a board where nothing is imminent. It also cannot
        manufacture a preference: when every tied candidate carries the same priority (the two
        IDENTICAL Riolu on `81905522-75` both read `fragile_preevo`) there is no strict maximum and
        this returns 0.0, so decision 7's recorded miss stays missing.

        The bonus is DERIVED, never hardcoded: half the finest distinction relevance actually draws on
        THIS menu, falling back to ``1 / K`` — one damage unit — when it draws none, which is exactly
        the all-zero case. A fixed epsilon would be sized against relevance's current arithmetic and
        would rot silently the moment a term changed it (the ADR-0063 failure mode). Half of the
        smallest real gap can never overtake a difference relevance itself settled, and the result is
        a fraction of one damage unit — small enough to order a tie without swamping the other
        tacticals summed into the same option score.
        """
        if not self.snipe_relevance or board.snipe_ko_available:
            return 0.0
        got = self._snipe_relevance_terms(obs, select, board, option, ctx)
        if got is None:
            return 0.0
        from common import snipe_relevance as srel
        mine = self._snipe_brief_priority(obs, select, option, getattr(board, "matchup_plan", None))
        return srel.brief_tiebreak(self._snipe_brief_peers(obs, select, board),
                                   got["relevance"], mine)

    def _relevance_terms(self, b, *, doomed: frozenset, area: str, bi: int, brief_ids=()) -> dict:
        """The DENY instrument's value — **Deny Relevance**, the read that replaced the magnitude
        (ADR-0080, Issue #199 grill; `common/deny_relevance.py` owns the scoring, this owns the plumbing).

        Emits, per opponent body: the best relevance achievable against it, WHICH attached Energy
        achieves it, ``relevance_by_type`` for a consumer that must score a SPECIFIC Energy, and the
        per-leg components for diagnosis. Consumed by the three deny surfaces since Issue #187
        (ADR-0080 decision 4); still gated on `deny_relevance`.

        ⚠️ **``relevance_energy`` is an index into ``energies`` and is DIAGNOSTIC ONLY — never match
        an engine option against it.** A ``DISCARD_ENERGY`` option identifies its Energy by
        ``energyIndex``, which indexes the body's attached *cards* (``energyCards`` / ``p.energy``),
        while ``energies`` is what those cards PROVIDE (`cgpy.options.provided_energy`) — one entry
        per unit, so an Ignition Energy contributes three. The two only coincide on a body holding
        nothing but single-unit Basic Energy. ``relevance_by_type`` exists so surface (c) can key off
        the option's Provider-resolved TYPE instead, which is what relevance is actually a function
        of; Issue #187's spec originally assumed a positional match and was corrected here.

        The two gates come first and force 0 before any leg is scored:
          * **liveness** — no attached Energy, which also delivers ADR-0062's whiff structurally;
          * **redundancy** — this body dies to our Knock Out this turn (`active_can_ko` for the
            Active, `_bench_doomed_by_me` for the bench), so we never spend a Hammer on a corpse.

        The Energy's TYPE is resolved through the Stat Provider, never inferred from its card id:
        the two coincide for Basic Energy (Basic ``{F}`` is card 6 and FIGHTING is 6) but that is a
        coincidence in the data, and Ignition Energy is card id 17 with a colourless contribution.
        A colourless/special Energy therefore scores 0 on the typed leg, which is correct — it pays
        no specific-type slot and so is never on a plan's critical path.

        A matched Brief's ``threats`` MULTIPLY the derived rank, never source it (ADR-0080
        decision 2): authored scouting sharpens a read that already works without it. The Brief-free
        path deliberately does NOT fall back to `Scout._target_role`, which orders `prize_liability`
        (any *ex* body) above `attacker` and so would top an unbriefed board with exactly the
        Meowth ex the doctrine says to ignore."""
        from common import deny_relevance as dr
        blank = {"relevance": 0.0, "relevance_energy": None, "relevance_attack_leg": 0.0,
                 "relevance_ability_leg": 0.0, "relevance_setback": 0, "relevance_forward": 0,
                 "relevance_by_type": {}, "relevance_fire": 0.0}
        energies = list((b or {}).get("energies") or [])
        if not energies or (area, bi) in doomed:
            return blank
        line_attacks, ability_types = self._line_attack_costs(b.get("id"))
        model = self._state_model
        if model is None:
            return blank                       # no snapshot: the instrument claims nothing
        counts = model.theirs.view_of(b).attached_types      # ← StateModel (POC-T1)
        best = dict(blank)
        by_type: dict = {}
        fire = 0.0
        for j, eid in enumerate(energies):
            est = self.stats.get(eid) if self.stats else None
            etype = getattr(est, "energyType", None) if est else None
            got = dr.strip_relevance(energy_type=etype, type_count=counts.get(etype, 0),
                                     line_attacks=line_attacks, ability_types=ability_types,
                                     total_attached=len(energies), attached_counts=counts,
                                     # ADR-0084 Amendment A: the ADR-0080-mandated forward discount,
                                     # the SAME constant `_denial_at` applies on the OFF path. Without
                                     # it the armed read credited a forward form in full.
                                     forward_discount=_DENIAL_FORWARD)
            by_type[etype] = got["relevance"]
            fire = max(fire, got["affordable_relevance"])
            if best["relevance_energy"] is None or got["relevance"] > best["relevance"]:
                best = {"relevance": got["relevance"], "relevance_energy": j,
                        "relevance_attack_leg": got["attack_leg"],
                        "relevance_ability_leg": got["ability_leg"],
                        "relevance_setback": got["setback_damage"],
                        "relevance_forward": got["forward_setback"],
                        "relevance_by_type": {}, "relevance_fire": 0.0}
        if b.get("id") in (brief_ids or ()):
            # The Brief sharpens the RANK (ADR-0080 decision 2's own word) — the keep price and the
            # target pick. It deliberately does NOT touch the fire reading: that one is compared
            # against `_DENIAL_ITEM_COST`, so a multiplier there can lift a hold above zero, and "a
            # booster must scale the oracle, never override it" is the f17 ruling (ADR-0062). Measured:
            # boosting the fire leg turns f21's -1.25 into +0.94 and plays the Hammer the human ruled
            # against, on a board where the ONLY thing that changed is that the body is Brief-named.
            best = dict(best, relevance=min(1.0, best["relevance"] * _BRIEF_THREAT_BOOST))
            by_type = {t: min(1.0, v * _BRIEF_THREAT_BOOST) for t, v in by_type.items()}
        return dict(best, relevance_by_type=by_type, relevance_fire=fire)

    def _line_attack_costs(self, card_id) -> tuple:
        """Every attack of every form in an opponent body's LINE, as
        ``([(damage, {EnergyType: slots}, total_cost, is_forward), …], ability_fuel_types)``.

        The line is the body plus all its forward forms (`combat.forward_card_ids`, all-descendants
        since S1a) because attached Energy carries THROUGH an evolution — which is what lets an
        Energy on a Riolu be priced by Mega Lucario ex's Mega Brave rather than by Riolu's own
        30-damage poke. Colourless slots are dropped: they are payable by anything, so no specific
        Energy is ever on their critical path (this is why an Energy on a Meowth ex, whose Tuck Tail
        costs ``●●●``, scores 0 — the doctrine's *"ignore it"*).

        ``ability_fuel_types`` unions `CardStat.abilityEnergyTypes` over the line — the shipped
        ADR-0032 parse (Munkidori's Adrena-Brain *"if this Pokémon has any {D} Energy attached"*),
        read here rather than re-derived so deny and the attach marginal (Issue #139) cannot drift."""
        from collections import Counter
        if not self.stats:
            return (), frozenset()
        forward = set(self.combat.forward_card_ids(card_id))
        attacks, fuels = [], set()
        for cid in {card_id} | forward:
            st = self.stats.get(cid) if cid is not None else None
            if not st:
                continue
            fuels.update(t for t in (getattr(st, "abilityEnergyTypes", ()) or ()) if t not in (0, None))
            for aid in (getattr(st, "attacks", ()) or ()):
                ast = self.combat.attack_stat(aid)
                need = Counter(t for t in (getattr(ast, "energyTypes", ()) or ()) if t not in (0, None))
                attacks.append((self.combat.attack_damage(aid), dict(need),
                                self.combat.attack_cost(aid, default=0), cid in forward))
        return tuple(attacks), frozenset(fuels)

    def _strip_delta_terms(self, ma, bodies, i, phase, *, opp_active, enabler) -> dict:
        """The DENY instrument's slice of the shared marginal (ADR-0078 decision 1; built by #199).

        The removal Δ beside it asks "what do I buy by taking this body OFF the board" — the gust /
        snipe question. A Hammer cannot ask that: it discards ONE Energy and the body stays. So deny
        plugs its own Δ into the shared currency (the design doc's *"each plugs its own `Δ` into the
        two terms"*), in the shape the user's ruling fixes — see SHAPE below.

        Mechanism mirrors the S2 recur shadow in the opposite direction — it augments a COPY of the
        body's ``energies`` upward to model discard fuel; this drops one, so no live primitive is
        touched and no caller's body dict is mutated.

        **SHAPE (user ruling, ADR-0078 Amendments B + C).** Deny's Δ is the SAME two-term marginal the
        removal Δ uses — ``needs.opponent_target_value`` over a ``turns_to_ko_me`` difference — so the
        one-backend claim of decision 1 holds for real. Only the POLICY differs (below).

        A fully-stripped body reads as not attacking within the horizon, so its Δ runs to the horizon.
        That is **correct, not a runaway**, for two reasons the user's ruling names: a bare body
        genuinely cannot attack on the board as it stands, and a Hammer cannot take it below zero, so
        the value SATURATES rather than compounding — `_strip_delta_terms` returns 0 for a bare body,
        which is that floor. `needs._SURVIVAL_CAP` (0.9) then bounds the term regardless, so deny stays
        sub-prize and can never out-price a real prize outcome. An earlier draft of this method priced
        a one-step damage swing instead, on the mistaken worry that the horizon Δ "overstates"; the cap
        already contained it, and the corpus preferred this shape (see Amendment C's table).

        ``prize_advance`` is **0**, and that is a ruling, not an omission (ADR-0078 decision 1 /
        design doc line 50, "deny (pure tempo)"): a strip takes no Prizes. The forward-form case that
        might look like a prize term is already inside the curve — S1a established ``forward_card_ids``
        is all-descendants, so the read already sees what a body evolves into off the Energy it is
        banking (ADR-0063's `_DENIAL_FORWARD` instinct, derived).

        A body holding no Energy yields 0: there is nothing to strip, which is the ADR-0062 whiff
        arriving structurally instead of as a separate gate.

        **POLICY (design doc ruling 2, the load-bearing per-consumer conservatism).** This Δ is read
        under `_DENY_CHARGED`, NOT the ceiling the removal Δ beside it uses, and the difference is not
        a refinement — under the ceiling the Δ is identically 0 by construction. The ceiling checks a
        form's affordability against its CHEAPEST attack and then credits its BIGGEST regardless
        (`incoming`'s own contract: *"a form contributes its biggest attack once it can pay its
        cheapest under `attached + t`; the bigger attack's affordability is NOT charged"*), so
        removing one Energy cannot change what it deals. Only a charged policy prices the per-attack
        typed affordability a strip actually attacks.

        `_DENY_CHARGED` carries the **user's ruling of 2026-07-28** (ADR-0078 Amendment B): the Δ is
        INSTANTANEOUS — `base_attach: 0`, no credit for the Energy they re-attach next turn — and it
        is only ever taken over opponent bodies carrying Energy right now. See that constant for why
        the design doc's "slow" (`base_attach: 1`) reading was the thing gate 1 measured as broken.

        **`energies[:-1]` is arbitrary and measured HARMLESS, not assumed harmless (ADR-0084 decision
        3).** Removing "the last-attached Energy" looks like it should matter under a typed
        affordability policy, and it does not: across **109 corpus bodies holding two or more
        Energies, which Energy is removed changes `turns_to_ko_me` in ZERO cases**, with zero false
        negatives for this policy. So the per-removed-TYPE generalisation the charged framing implies
        is measurably inert, while raising cost from 2 simulations per body per decision to
        `1 + Ntypes`. That is an EMPIRICAL rather than a provable guarantee: if a board ever appears
        where a body holds one critical and one surplus Energy AND sets the clock, re-run that
        measurement rather than re-deriving the question. The harness was
        `tools/train/probes/deny_gate217.py`, deleted by Issue #243 once ADR-0084 recorded its
        answer; rebuild it from that ADR's description rather than editing a stale one — a harness
        whose six hardcoded anchors have gone quietly out of date is a trap, not a head start.

        **Consumer (ADR-0084 decision 7).** Exactly ONE: the target pick's lexicographic tiebreak
        (`_deny_strip_delta_tiebreak`). This Δ may order a tie; it may never GATE one. It reads *"does this
        strip delay MY defeat by a whole turn or more"*, which is strictly narrower than *"does this
        strip do anything"* — blind to Ability mutes, to sub-turn setbacks, and to any strip that
        wrecks their plan without touching their clock against me. Measured, a `strip_shift > 0` gate
        on the keep price would have suppressed **128 of 218** relevance-positive rows."""
        from common import needs
        b = bodies[i]
        energies = list((b or {}).get("energies") or [])
        if not energies:
            return {"strip_shift": 0, "deny_value": 0.0}       # nothing to strip — the whiff, derived
        stripped = dict(b)
        stripped["energies"] = energies[:-1]                   # one Energy gone; the body remains
        model = self._state_model
        if model is None:
            return {"strip_shift": 0, "deny_value": 0.0}       # no snapshot: the Δ claims nothing
        # Off the SNAPSHOT (POC-T1). Both legs name `bodies` — the second is a COUNTERFACTUAL board
        # with the stripped copy spliced in — and both name `_DENY_CHARGED` explicitly, because this
        # Δ is measured under the zero-attach budget and must NOT drift onto the Read's threaded one
        # (see `_DENY_CHARGED` for why the "slow" reading was what gate 1 measured as broken).
        base = model.theirs.turns_to_ko_me(ma, bodies=bodies, opp_active=opp_active,
                                           switch_enabler=enabler, charged=self._DENY_CHARGED)
        after = model.theirs.turns_to_ko_me(ma, bodies=bodies[:i] + [stripped] + bodies[i + 1:],
                                            opp_active=stripped if b is opp_active else opp_active,
                                            switch_enabler=enabler, charged=self._DENY_CHARGED)
        return {"strip_shift": after - base,                   # BOTH legs under `_DENY_CHARGED` — the
                                                               # caller's `base_t` is the CEILING
                                                               # baseline, and differencing across two
                                                               # policies would be meaningless
                "deny_value": needs.opponent_target_value(prize_advance=0.0,
                                                          survival_shift=after - base, phase=phase)}

    def _opponent_target_shadow(self, obs: dict, board) -> dict | None:
        """S3 opponent-target value SHADOW (docs/plans/opponent-value-equation-unification.md; O1 =
        Option B): the sweep compares `_opponent_target_rows`' per-body ranking to the shipped snipe
        / gust / deny picks — the evidence for the Option-B assignment. Deciding NOTHING.

        Reads the per-decision cache `_board()` stashes (ADR-0076) when one exists, so a real
        decision computes the per-body simulation once and shares it with the live `gust_target`
        slot emission; falls back to a fresh compute when called directly (off a hand-built `board`
        that never went through `_board()`, as the existing shadow tests do) — `_board()` always
        runs first in a real decision, so the cache is never stale by the time this reads it.

        Sparse: None mid-sim (`self._planning`, no shadow work in rollouts) — the guard
        `_opponent_target_rows` used to carry for everyone. It belongs HERE, on the diagnostic, and
        not on the live row computation two live instruments read (ADR-0093 decision 3). Same
        placement as `_threat_shadow` and `_recur_shadow`."""
        if getattr(self, "_planning", False):
            return None
        result = getattr(self, "_opponent_target_cache", None)
        if result is None:
            result = self._opponent_target_rows(obs, board)
        if result is None:
            return None
        phase, rows = result
        return {"phase": round(phase, 3),
                "bodies": [{"id": r["id"], "prize": r["prize"], "survival_shift": r["survival_shift"],
                           "value": round(r["value"], 3)} for r in rows]}

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
        ; `_finish_turn_last` rides the retreat step tier-0. (`hold-position-in-setup` is
        DELETED, ADR-0100 §11, so there is no longer a setup brake to stand down.)"""
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
        # ^ RETAINED DELIBERATELY, and known to be doctrinally wrong (user rulings 2026-07-28/29).
        # It was deleted on this branch and the deletion was REVERTED here, on evidence:
        #
        #   * The doctrine says it is too strict. On 86091435-13 the correct play is to retreat the
        #     Dreepy into Budew while severely behind, and this guard forbids it purely because the
        #     line carries one partial Energy. A boolean cannot say "behind, so protection plus
        #     disruption beats one more development step". That ruling stands.
        #   * But deleting it LOSES GAMES. The ADR-0072 mid-build paired A/B over 2400 games
        #     (`gauntlet_swap_ab.py --stage mid-build`, build-vs-build because there is no flag to
        #     overlay) returned delta -4.75%, 95% CI [-8.22%, -1.28%], 0 crashes — CI-lo through the
        #     -5% floor, and all SIX directed matchups negative at +-3.5% precision, so not noise.
        #     The per-frame gates were clean (1 corpus flip, that fix; Discrimination Gate PASS), so
        #     this is exactly the effect only the A/B can see.
        #   * WHY it costs more than the one frame it fixes: this gate feeds TWO rungs, and the
        #     heavier one is not the retreat. `retreat-to-wall-the-line` (w30) is the retreat;
        #     `feed-the-line-for-disruptor-lock` (w55, baseline_energy) is the ATTACH that funds it.
        #     Ungated, the attach rung diverts the turn's Energy into paying a retreat on boards
        #     where the line was already being built — which is the diversion `f21` actually ruled
        #     on, so the guard's own citation is apt for the attach even though it over-reaches on
        #     the retreat.
        #
        # The real fix is NOT a better boolean here: it is the value question (what a
        # protection/disruption turn is worth against the race) composed across a multi-step turn.
        # Owned by #165 (Turn Planner) with #145's currency work; both frames are recorded there.
        # Until one of those lands, this crude guard is measurably earning its keep, so it stays.
        # An untested middle option is on the record if anyone wants it: keep the guard on the w55
        # attach rung and drop it only for the w30 retreat rung, then re-run the same A/B.
        if ma_stat is None or getattr(ma_stat, "retreatCost", 0) > len(ma.get("energies") or []) + 1:
            return False                                  # the retreat must be reachable this turn
        return not self._active_maxed_kos(ma, oa)         # don't waste a body that could KO instead

    # (Gust Board-signal builders — _active_ko_prizes, _opp_active_condition_gift, etc. — are in
    # doctrine_gust.GustMixin; `_board` calls them as `self.…`.)
    # `_opp_has_hand_size_attacker` DELETED (ADR-0102, Issue #261 item 2c) with the `Board` field and
    # the two rungs it gated. It asked the `hand_size_attacker` Function Tag whether a line scales off
    # the hand, and NOTHING replaces it: a card-fact reader in front of the survival clock would be a
    # second enumeration of the Damage Formula's scaler families, free to drift from the oracle it
    # guards. `_hand_size_relief_tactical` asks the clock instead (ADR-0102 decision 5).
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

    def _attack_impossible_on_menu(self, select, budget) -> bool:
        """The ENGINE says my Active cannot attack this turn: I am at the open turn menu and it lists no
        ATTACK option. Authoritative where the closed-form energy math is not — it already accounts for
        a transient attack-lock, a Special Condition, and turn-1-going-first, and unlike the ADR-0033
        tracker it survives a single-frame retest (a Correction carries one `obs`, so the tracker never
        saw last turn's attack).

        NOT decisive while THIS TURN'S ATTACH BUDGET could still turn an attack on — only once the
        budget is empty does an empty attack menu mean 'no attack this turn'. The guard is the Budget
        and not "a reusable Energy card sits in hand" (#142): the narrower reading is the SAME
        under-read as the retired `+1`, and it fired at dragapult f70, where the hand was three
        Supporters and Crispin's fetch-and-attach was invisible to it."""
        if not select or select.get("context") != _MAIN:
            return False
        opts = select.get("option") or []
        if not opts or any(o.get("type") == _ATTACK for o in opts):
            return False
        return not (budget is not None and budget.size > 0)

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

    def _opens_from_hand(self, cid: int | None) -> bool:
        """This card's own Ability puts it into the Active Spot straight from hand — the `opener`
        Function Tag (Cinderace's Explosiveness: "if this Pokémon is in your hand when you are setting
        up to play, you may put it face down in the Active Spot"). The ONE definition of the
        Ability route into the Active Spot; both readers below derive from it so they cannot drift."""
        return bool(self.functions) and cid is not None and _OPENER_TAG in self.functions.tags(cid)

    def _hand_startable(self, hand: list) -> bool:
        """True if a card in hand can take the Active Spot WITHOUT being a Basic — i.e. by the Ability
        route. Scoped to the mulligan keep, where that is the only interesting case: a hand holding
        any Basic never reaches the prompt (rulebook L224 — "if either player has no Basic Pokémon in
        their opening hand, that player must take a mulligan"). Deliberately NARROWER than
        `_is_startable_body`, which is why it reads `_opens_from_hand` rather than calling it — the
        Basic half would make this trivially true on a hand that cannot mulligan anyway.

        The deck `starter` Role was a second accepted signal here until ADR-0079 retired it: every
        declaration in the repo was either a Basic (moot per the rule above) or Cinderace, which
        carries the `opener` Tag anyway — so it never changed this answer. Naming a deck's openers is
        now `Strategy.starter_priority`'s job, at the Set-Up ACTIVE pick rather than the mulligan."""
        return any(self._opens_from_hand(c.get("id")) for c in hand if c)

    def _is_startable_body(self, cid: int | None) -> bool:
        """True iff this card can legally take the Active Spot at the pregame Set-Up pick — a Basic
        Pokémon, or one that `_opens_from_hand`. This is the universe `Strategy.starter_priority` must
        rank COMPLETELY (ADR-0079 decision 5).

        Lives here, on the runtime, rather than in the test that consumes it: the completeness
        invariant is only worth anything if it measures the declaration against what the ENGINE can
        actually offer, and a re-implementation in the test would be free to drift from it — which is
        the failure the invariant exists to prevent. Returns False on unknown stats, so a caller that
        needs the answer to be MEANINGFUL must first establish that stats loaded (the test asserts a
        non-empty startable set for exactly this reason)."""
        if cid is None or not self.stats:
            return False
        st = self.stats.get(cid)
        if not st or not st.is_pokemon:
            return False
        return not st.evolvesFrom or self._opens_from_hand(cid)

    def _wincon_payoff_ids(self) -> frozenset:
        """The deck's declared WIN-CONDITION Line payoffs. The gate on the Opener Marginal (ADR-0081
        amendment A) — an evolution in hand only reorders the opener when it is what the deck is
        actually trying to build.

        Routed through `_wincon_lines`, so a `secondary_attacker` Line is excluded exactly as it is
        everywhere else in the win-condition machinery (ADR-0048). That role gate is load-bearing
        here, not incidental: mega_lucario declares `Line(MAKUHITA -> HARIYAMA,
        role='secondary_attacker')` for a 210-damage prize wall, and reading it as a payoff would
        promote Makuhita over a declared rank-1 Solrock on the strength of raw damage — the very
        "big number wins" reasoning amendment A rejected.

        **Deliberately NOT `_wincon_set`**, whose first clause is identical. That set additionally
        unions in every card carrying a `win_condition` / `primary_attacker` ROLE, which is a strictly
        broader concept: it would let a role-tagged body that is on no declared Line act as an opener
        payoff, widening the gate past what ADR-0081 decision 4 specifies (*"the `payoff` of one of the
        deck's declared win-condition Lines"*). The two sets coincide for all three authored decks
        today, so the divergence is LATENT — swapping them reddens nothing by accident. The binding
        record is therefore ADR-0081 decision 4 plus its guard test
        (`test_a_ROLE_tagged_body_that_is_no_line_payoff_does_not_promote_its_base`), not this
        docstring, which would be deleted along with the very function a reviewer proposes collapsing.

        Deck-fixed and match-invariant, so memoised in the same shape as `_wincon_set`."""
        cached = getattr(self, "_wincon_payoff_cache", None)
        if cached is not None:
            return cached
        payoffs = frozenset(p for p in (getattr(ln, "payoff", None) for ln in self._wincon_lines())
                            if p is not None)
        self._wincon_payoff_cache = payoffs
        return payoffs

    def _deck_body_names(self) -> frozenset:
        """Every card NAME in this deck's list. NAMES rather than ids because an evolution identifies
        its previous stage by name (`CardStat.evolvesFrom`) and reprints share a name across ids —
        Raboot is both 152 and 665 — so an id-keyed test would miss the reprint.

        Deck-fixed and match-invariant, so memoised like `_wincon_set` / `_derived_accel_body_ids`
        rather than rebuilt per call: `_route_only_at_setup` is consulted once per declared starter,
        and rebuilding a 60-card set inside that loop is the kind of quiet quadratic the neighbouring
        derived sets already avoid."""
        cached = getattr(self, "_deck_body_names_cache", None)
        if cached is not None:
            return cached
        names = frozenset(s.name for s in (self.stats.get(c) for c in set(self.deck or ()))
                          if s and s.name) if self.stats else frozenset()
        self._deck_body_names_cache = names
        return names

    def _opener_marginal(self, cid: int | None, hand_ids) -> float:
        """**Opener Marginal** (ADR-0081 decision 4): ADR-0070's body-substituted evolve delta, in
        DAMAGE, read at turn 0. Non-zero only when a card in hand evolves from `cid` AND that card is
        a declared Line payoff; then `maxDamage(payoff) - maxDamage(cid)`. Zero otherwise.

        Silent by default BY CONSTRUCTION, which is what lets the declaration keep every frame it
        already gets right without a threshold constant to tune (ADR-0065). The Line gate is
        load-bearing rather than a refinement: without it this fires on five promotable bodies across
        the three authored decks and only one firing is wanted — a mid-line stepping stone (Drakloak)
        or a draw engine (Dudunsparce) would otherwise promote its own base, rebuilding the guard
        pile ADR-0079 deleted.

        Matches on the evolution's `evolvesFrom` NAME, not an id, so reprints of the same body (Raboot
        is both 152 and 665) resolve identically. Reads the HAND only — at turn 0 the deck carries no
        frame-specific information, so deck odds would be a per-deck constant the ranking already
        encodes (ADR-0081 decision 3)."""
        if cid is None or not self.stats or not hand_ids:
            return 0.0
        st = self.stats.get(cid)
        if not st or not st.name:
            return 0.0
        payoffs = self._wincon_payoff_ids()
        if not payoffs:
            return 0.0
        best = 0.0
        for hid in hand_ids:
            if hid not in payoffs:
                continue
            hst = self.stats.get(hid)
            if hst and hst.evolvesFrom == st.name:
                best = max(best, float(hst.maxDamage - st.maxDamage))
        return best

    def _route_only_at_setup(self, cid: int | None) -> bool:
        """Is the pregame Set-Up pick this body's ONLY route into play? The DERIVED pin (ADR-0081
        decision 1) — true for an `opener`-tagged Evolution whose previous stage is absent from this
        deck, i.e. Cinderace in a deck running no Raboot. Skipping such a body forfeits it
        permanently, so the Opener Marginal may not move it.

        Computed from the DECKLIST rather than declared, which is what keeps it correct for free: add
        the previous stage to the deck and the pin lifts by itself, where a declared marker would go
        stale. Derivation-first with declaration as the confirm/override is the established pattern
        (ADR-0079 amendment F, `_derived_accel_body_ids`).

        **Fails CLOSED** — pins when it cannot tell — deliberately the opposite of
        `_is_startable_body`. The asymmetry is justified by consequence, not symmetry: a MISSING pin
        permanently forfeits a card, while a spurious one merely opens suboptimally. Pinning
        everything degrades exactly to the pre-ADR-0081 behaviour (the declared order, verbatim)."""
        if cid is None:
            return False
        if not (self.stats and self.deck and self.functions):
            return True                                  # cannot tell -> freeze the declaration
        if not self._opens_from_hand(cid):
            return False                                 # not route-restricted: an ordinary body
        st = self.stats.get(cid)
        if st is None:
            return True                                  # opener-tagged but unknown -> pin
        if not st.evolvesFrom:
            return False                                 # a Basic can always be benched instead
        return st.evolvesFrom not in self._deck_body_names()

    def _effective_starter_order(self, obs: dict, sp: list) -> list:
        """**Effective Starter Order** (ADR-0081 decision 5): the declaration as resolved against THIS
        opening hand. Pinned entries hold their declared slot; unpinned entries re-sort among the
        slots left over, by (Opener Marginal desc, declared rank asc).

        The override is STRUCTURAL — it changes what the declaration SAYS, not what anything SCORES —
        so the seam keeps one rule and one boolean (ADR-0079 decision 5 survives intact) and the
        reorder cannot be disarmed by a learned weight. Scoring it additively would have made
        correctness depend on `open-the-declared-starter`'s tuned magnitude staying small.

        Returns the declaration untouched when no body has a marginal, which is the overwhelmingly
        common case — so the pin predicate is not even consulted on an ordinary hand."""
        marginals = {}
        hand_ids = [c.get("id") for c in ((self._my_player(obs) or {}).get("hand") or [])
                    if c and c.get("id") is not None]
        if hand_ids:
            marginals = {cid: self._opener_marginal(cid, hand_ids) for cid in sp}
        if not any(marginals.values()):
            return list(sp)
        rank = {cid: i for i, cid in enumerate(sp)}
        pinned = {i for i, cid in enumerate(sp) if self._route_only_at_setup(cid)}
        movable = sorted((cid for i, cid in enumerate(sp) if i not in pinned),
                         key=lambda c: (-marginals.get(c, 0.0), rank[c]))
        out, it = list(sp), iter(movable)
        for i in range(len(out)):
            if i not in pinned:
                out[i] = next(it)
        return out

    def _top_starter_id(self, obs: dict, select: dict | None) -> int | None:
        """The body the deck most wants Active among the ones actually on offer — the first id in the
        **Effective Starter Order** present in this SETUP_ACTIVE select's options. None off that
        select, on an empty declaration, or when nothing offered is ranked.

        One id, not a rank, because SETUP_ACTIVE is a forced single pick (minCount/maxCount 1): argmax
        reads only the winner, so under a COMPLETE list this collapses the whole ordering losslessly
        (ADR-0079 decision 5). Twin of `_top_fetch_priority_id`, except that the order it scans is
        hand-conditional (ADR-0081) rather than the declaration verbatim."""
        sp = getattr(self.strategy, "starter_priority", None)
        if not sp or not select or select.get("context") != _SETUP_ACTIVE:
            return None
        present = set()
        for opt in (select.get("option") or []):
            card = self._option_pokemon(obs, select, opt)
            if card and card.get("id") is not None:
                present.add(card["id"])
        return next((cid for cid in self._effective_starter_order(obs, sp) if cid in present), None)

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
