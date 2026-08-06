"""Needs — WHAT the position requires (the fifth Ubiquitous Language term, ratified 2026-07-19;
`docs/plans/keep-value-needs-assignment-grill-spec.md`, `docs/adr/0065-glossary.md`).

Deadline-tagged SLOTS derived from board state, valued in the ONE currency. A held card's
keep-value (WP-N2, the exact-assignment marginal) is its marginal slot coverage — so multi-copies,
energy-attached, doom, quotas, fuel and deploy-now become slot PROPERTIES instead of gates, and
interactions resolve globally in the assignment instead of pairwise in bespoke composition rules.

This module (WP-N1) owns:
  * the slot vocabulary (`SLOT_KINDS`) and the pure derivation primitives — deadlines from the
    quota structure / the threat read / the ruled opponent lookahead, never authored (Round 9);
  * the card→slot ``SUPPLIES`` mapping the COVERAGE LINT checks (every worth source names ≥1 slot
    kind — a MISSED slot sheds a good card, the wrong fail direction; Round-1 ruling);
  * the ``DISSOLUTION_LEDGER`` (every v1 gate names the slot kind that re-derives it — retiring a
    gate without its deriving slot is a red test, so no corpus-anchored knowledge evaporates).

Opponent-side (Round-3 ruling): VISIBLE state + basic lookahead of their in-play bodies only —
`turns_to_ready` = max(energy deficit at the attach quota, forward evolution hops). Slot VALUES that
a shipped oracle already prices (ADR-0062 denial, the gust oracle, the threat read) are CONSUMED,
never re-derived. ADR-0064's pessimism still owns the threat ceiling.

Pure and lib-free; the Pilot resolves board facts and passes them (the `gate_library` pattern).
Horizon discipline: consumers cap Σ slot values < KO_SCORE (the readiness invariant).
"""
from __future__ import annotations

from dataclasses import dataclass

from common.card_worth import ROLE_TIER, ENERGY_TIER
from common.grading import halve      # the ONE hop/turn discount convention (ADR-0070 §6)
from common.strategy.context import (MAX_PRIZE_VALUE,   # the rules' own constants, one home (leaf
                                     PRIZE_CARDS)       # module)

#: Every slot kind the vocabulary knows. The coverage lint rejects a SUPPLIES entry naming
#: anything outside this set; adding a kind here without a supplier or a deriving gate is inert.
SLOT_KINDS = frozenset({
    "fund_attack",    # a missing Energy unit on a body (deadline = its quota rank)
    "deploy_now",     # an eligible evolution play THIS turn (the deploy-now spike, re-derived)
    "line",           # a Line member still to be assembled (no this-turn deadline)
    "answer_doom",    # heal/switch/successor against the threat read (the pressure gate, re-derived)
    "draw_engine",    # the recurring draw need (saturating — the engine-supporter premise)
    "supply_wincon",  # the tutor's fetch target (absent when the wincon is in hand — need-met)
    "fuel",           # discard-source accel fuel — SUPPLIED BY PITCHING (the zone sign)
    "deny",           # strip THEIR resource (value from the ADR-0062 oracle, deadline from their
                      # turns-to-ready — the graded Hammer, 86091435-68)
    "gust_target",    # a held gust-effect Trainer card (Guzma/Boss's-Orders-class), valued by the
                      # two-term opponent-target marginal (ADR-0076) — NOT the flat disruption tier
                      # `deny` still uses for true energy-denial cards
    "general",        # a held card's LATENT board worth where it fills no specific need — its role
                      # tier discounted (the readiness leaf's `contribution` for the HAND; WP-N5)
})


@dataclass(frozen=True)
class Slot:
    """One need: what filling it is worth (the one currency), by when (turns; 0 = this turn), and
    a stable ``key`` for telemetry/dedup. ``supplied_by_pitch`` marks the fuel class — the slot a
    DISCARD fills (the pitch side of the marginal)."""
    kind: str
    value: float
    deadline: int
    key: str
    supplied_by_pitch: bool = False


# ─────────────────────────────────────────────────────────── my-side derivations
def fund_attack_slots(body_key: str, cost_remaining: int, *, quota_spent: bool = False) -> list:
    """One slot per missing Energy unit on ``body_key``; unit j's deadline is j−1 turns out
    (1 manual attach/turn — rules.md §3), +1 across the board when this turn's attach is already
    spent. The quota gate re-derived as slot structure: the 3rd needed unit is two turns away, so
    the copy assigned to it re-accesses over a wider window — derived, not asserted."""
    base = 1 if quota_spent else 0
    return [Slot("fund_attack", ENERGY_TIER, base + j, f"{body_key}:unit{j}")
            for j in range(max(0, int(cost_remaining)))]


def deploy_now_slot(key: str, *, value: float) -> Slot:
    """An eligible evolution play THIS turn (`Board.deploy_now_ids`): deadline 0 at the evolution's
    own tier. The deploy-now spike re-derived — a card assigned to a deadline-0 slot cannot bank
    re-access, so its marginal is full (WP-N2)."""
    return Slot("deploy_now", float(value), 0, key)


#: Roles whose line carries a SUCCESSION need (see `line_slots`): the plan's payoff class, whose
#: attrition (KOs, prizing) the plan must survive — a spare copy's marginal is real, never 0.
SUCCESSION_ROLES = frozenset({"win_condition", "primary_attacker"})


def line_slots(key: str, *, value: float, succession: bool = False,
               primary_met: bool = False, succession_urgent: bool = False,
               deadline: int = 99, succ_deadline: int = 99) -> list:
    """The line slots for ONE card class: the primary assembly slot at the full tier (absent when a
    copy is already IN PLAY — ``primary_met``, the in_play gate re-derived as slot absence), plus —
    for a wincon class (``succession=True``, `SUCCESSION_ROLES`) — a SUCCESSION slot: the plan needs
    the line to survive attrition (KOs and prizing take bodies), so a spare copy's solo marginal is
    real, never 0 — "copy 2's marginal = its next-best slot" (the grill spec's own sets-not-sums
    answer).

    Two grades of succession (the answer-doom grill ruling, 2026-07-20):
      * NORMAL (``succession_urgent=False``) — a HALF-tier slot at no this-turn deadline: attrition
        is a future concern, so the insurance is discounted (mirrors `draw_engine_slot` saturation),
        and a deploy-now slot supersedes for the same hop.
      * URGENT (``succession_urgent=True``) — the doomed-payoff spike: when MY Active is doomed and
        this class is the successor with its base already in play, the replacement is needed
        IMMINENTLY, so the slot goes FULL tier at deadline 0 (a closing edge — re-access can't bank
        against a this-turn need). This re-derives the old flat answer-doom successor value
        (`TAG_TIER["clutch_heal"]`) AS the line's own worth: a doomed wincon's successor is not
        shuffle fodder (ep83037962 f49 — don't Harlequin away the second Mega Starmie the turn its
        Staryu hit the bench).

    READINESS (piece 1, the shuffle-value grill): ``deadline`` / ``succ_deadline`` carry the line's
    board-derived power-up timing — the primary at the turn the payoff comes online (its base already
    in play and powered ⇒ ~1), the succession one turn further (the backup). They default to 99
    (latent) so every non-refresh caller is unchanged; only the refresh-SHED resupply consumes
    ``deadline`` (`pilot._refresh_slot_resupply` clamps the re-access window to it), so a wincon one
    attach from live is no longer priced as freely re-fetchable and shed for nearly nothing
    (ep82752604 f16). The URGENT succession override still wins (deadline 0)."""
    out = []
    if not primary_met:
        out.append(Slot("line", float(value), deadline, key))
    if succession:
        succ_val = float(value) if succession_urgent else float(value) / 2.0
        sd = 0 if succession_urgent else succ_deadline
        out.append(Slot("line", succ_val, sd, f"{key}:succ"))
    return out


def answer_doom_slot(*, value: float, deadline: int = 0) -> Slot:
    """The pressure gate re-derived: the threat read (`active_doomed` / incoming) opens an answer
    slot — heal / switch — at the threat's deadline. ``value`` is the DOOMED BODY'S OWN PRESERVED
    worth (the grill's answer-doom ruling, 2026-07-20): a switch/heal is worth exactly what saving
    the Active preserves — a worth-0 Switch that rescues a 12-point engine Lunatone is worth 12
    (ep83661652 f40), a filler active worth ~0 is not worth a card to save. NOT a flat tier, and
    NOT the swap card's own catalog worth. The SUCCESSOR is no longer priced here — a doomed
    wincon's replacement rides the URGENT succession slot (`line_slots`, full tier at deadline 0)."""
    return Slot("answer_doom", float(value), int(deadline), "answer_doom")


def insure_wincon_slot(key: str, *, value: float, deadline: int = 1) -> Slot:
    """The heal that INSURES an irreplaceable win condition (ADR-0101 amendment, Issue #261 wave-2
    ruling on ep83969481 f55: *"preserve our healer when we only have a single wincon remaining"*).

    Distinct from `answer_doom_slot` in WHEN it opens and identical to it in KIND, and both halves
    are deliberate:

    * it opens on the win-condition LINE being exhausted, not on `active_doomed` — the threat is a
      turn out, which is exactly why the answer-doom read correctly stays shut (`reviewed.json` rules
      that on the frame in as many words), hence the deadline-1 default;
    * it carries kind ``answer_doom`` so it inherits that kind's CLOSING EDGE — `_refresh_slot_
      resupply` zeroes re-access for it. That is the point rather than a side effect: the ruling is
      about **certainty**, and a heal you are relying on to survive is not one you may price at "I'll
      probably redraw it." The deadline is documentary here; the kind is what carries the semantics.

    Its own ``key`` (rather than `answer_doom_slot`'s fixed one) so it can coexist with a real
    answer-doom slot on a board that opens both."""
    return Slot("answer_doom", float(value), int(deadline), key)


def draw_engine_slot(*, engines_online: int, value: float | None = None) -> Slot:
    """The recurring draw need, SATURATING (the readiness leaf's term, and the engine-supporter
    premise re-derived): with an engine already online the marginal engine's value halves — kept
    over filler, but never stacking linearly. ``value`` overrides the engine-ROLE tier for the band
    the resolver reads off the eligible suppliers (a supporter-only engine need is the v1 tuned
    engine-supporter band, not the engine-body tier — corpus 83686860-11)."""
    base = ROLE_TIER["engine"] if value is None else float(value)
    return Slot("draw_engine", base if engines_online <= 0 else base / 2.0, 0, "draw_engine")


def supply_wincon_slot(*, wincon_in_hand: bool, target_reachable: bool):
    """The tutor's slot — present only while the wincon is NOT in hand and a target remains
    reachable. The need-met and fetcher gates re-derived as slot ABSENCE: no slot → the tutor's
    marginal is 0, no gate required. None when absent."""
    if wincon_in_hand or not target_reachable:
        return None
    return Slot("supply_wincon", ROLE_TIER["tutor"], 99, "supply_wincon")


def fuel_slot(key: str, *, value: float) -> Slot:
    """Discard-source accel fuel (Aura Jab class, `_discard_fuel_types`): a slot SUPPLIED BY
    PITCHING — the zone sign as structure. A matching Energy assigned here contributes by being
    discarded, so its keep-side marginal is ≤ 0."""
    return Slot("fuel", float(value), 99, key, supplied_by_pitch=True)


def general_worth_slot(key: str, *, value: float) -> Slot:
    """A held card's LATENT board worth where it fills no SPECIFIC need (WP-N5): its role tier,
    DISCOUNTED (a not-yet-deployed card is worth less than one filling a live need — the readiness
    leaf's bench position weight, `_READINESS_BENCH_DISCOUNT`). The resolver emits ONE per distinct
    held card, so spare COPIES price marginally (the assignment de-duplicates — sets-not-sums), and
    it sits BELOW every specific slot so a need-filler still assigns to its need first. The floor the
    refresh-SHED sweep proved missing: a hand of playable pieces is no longer shuffle-priced at ~0.
    No deadline (latent, not this-turn)."""
    return Slot("general", float(value), 99, key)


# ─────────────────────────────────────────────────── opponent-side (Round-3 ruling)
def turns_to_ready(*, energy_deficit: int, evolve_hops: int, attaches_per_turn: int = 1) -> int:
    """The ruled basic lookahead of an IN-PLAY opponent body, from VISIBLE facts only: turns until
    it is fully energized (deficit at their attach quota) and fully evolved (forward-index hops,
    one per turn). Attaching and evolving run in PARALLEL, so the read is the MAX of the two legs,
    never the sum. Clamped at 0 (surplus/ready)."""
    e = max(0, int(energy_deficit))
    per = max(1, int(attaches_per_turn))
    attach_turns = (e + per - 1) // per
    return max(attach_turns, max(0, int(evolve_hops)))


def deny_slot(key: str, *, oracle_value: float, turns_to_ready: int) -> Slot:
    """The graded Hammer (the user's 86091435-68 ruling, with TIMING): strip THEIR resource. ``value``
    grades toward full as their body nears ready: at deadline 0 the full passed-in value; each turn of
    slack halves it (a closing edge inverted — urgency, not decay of worth).

    **``oracle_value`` is a misnomer, kept for call-compatibility (corrected 2026-07-28, ADR-0078).**
    This docstring used to claim the value came from the ADR-0062 denial oracle (`_opp_denial_best`).
    It does not, and has not since the WP-N8 currency ruling: the caller passes the flat disruption
    card-tier `TAG_TIER["gust"]` (~10) — `pilot._resolve_needs` — graded per body by relevance. The
    ADR-0062 oracle used to survive on this path as a `> 0` BITE GATE (`_denial_at`); Issue #228
    deleted it, and `relevance > 0` SUBSUMES that gate (already 0 for a body with no Energy, for
    surplus Energy, and for one dying to my Knock Out this turn). With `deny_relevance` OFF the
    emission now stands down entirely — DEGRADED MODE, never a rollback.

    ADR-0078 (#187 grill) overturned that WP-N8 ruling in turn — deny was to read the shared per-body
    `opponent_target_value` marginal converted at a DERIVED Worth Damage Rate. **That plan is
    withdrawn** (ADR-0080, Issue #199): the rate is not derivable (the corpus holds exactly one
    keep-side anchor and it prices 0 under both instruments, so the rate divides out) and deny turned
    out not to need one, being a CATEGORICAL RELEVANCE instrument rather than a magnitude one.

    So what the caller passes depends on the instrument, and this function stays agnostic:
      * `deny_relevance` OFF — the flat disruption card-tier `TAG_TIER["gust"]` (~10), as shipped;
      * ARMED (Issue #187) — `TAG_TIER["gust"] x relevance(this body)`, relevance being the [0,1]
        Deny Relevance read. The `/2**t` grade below is retained under either (user ruling
        2026-07-30): relevance is deliberately not imminence-gated, so the grade is the only term
        pricing WHEN the threat lands.

    Resupply ruling (recorded for the closure-discount thread; vacuous while resupply is 0.0):
    a DEADLINE-0 deny slot must take resupply 0.0 — a deny needed NOW is not re-drawable in time,
    the same closing edge that makes `deploy_now` un-bankable; slack (deadline ≥ 1) deny slots may
    take their supplier classes' re-access odds over that window."""
    t = max(0, int(turns_to_ready))
    return Slot("deny", float(oracle_value) / (2 ** t), t, key)


# ─────────────────────────── the two-term opponent-target marginal (Opponent Value Equation, S3)
_PRIZES_START = PRIZE_CARDS # the Prize-count both players race down from — the rules' own constant,
                            # homed once in `strategy.context` (POC-T3.5, Issue #279) because the
                            # Damage Formula's prizes-taken scalers read the same 6. Value unchanged.
_PHASE_BASE = 0.3           # neutral phase weight (no race read)
_PHASE_RACE_W = 0.15        # per turn-of-race-margin: being BEHIND (race_ahead < 0) sharpens every
                            # survival turn toward a full prize; being ahead flattens it. Seed —
                            # ladder-/grill-matured, same discipline as `objectives.plan_confidence`.
_PHASE_PRIZE_W = 0.5        # prize-proximity weight: as the opponent nears their last Prize, one
                            # survival turn is worth more. Seed.
_SURVIVAL_PER_TURN = 0.5    # prize-equivalents per turn-of-survival bought, before the phase scale —
                            # a SUB-prize seed (the gust-marginal band), matured by the corpus grill.
_SURVIVAL_CAP = 0.9         # the survival term stays < 1 Prize: it breaks ties among prize outcomes,
                            # never overrides a real prize difference (the sub-prize-tie-break rule).

#: The CEILING of :func:`opponent_target_value` **as every shipped caller supplies it** — the largest
#: prize-equivalent any one body's removal can price at. **Derived, not chosen**: the marginal is
#: `prize_advance + survival_value(...)`, whose second term `_SURVIVAL_CAP` bounds at 0.9 for ANY
#: caller, and whose first is a *parameter* — bounded at the card set's largest prize value
#: (`MAX_PRIZE_VALUE` = 3, a Mega ex) because `pilot._opponent_target_rows`, the only site that builds
#: these rows, passes `CardStat.prize_value`. So the sum is **3.9** — exactly the number ADR-0076
#: Amendment E quotes when it names the denomination debt (*"max ~3.9 for a 3-prize body with 8
#: survival turns bought"*).
#:
#: The distinction is not pedantry: this function does not enforce the bound (a caller may hand it any
#: `prize_advance`), so the consumer clamps rather than trusting — see
#: `currency.target_value_to_worth`.
#:
#: Public because it is the YARDSTICK that lets a prize-denominated marginal be read as a
#: dimensionless [0, 1] fraction and so meet a Worth-denominated consumer without a general
#: prize↔worth rate: `currency.target_value_to_worth` (Issue #313 item 2g) is that consumer, and it
#: divides by this. It lives HERE rather than in `currency` because it is a fact about this module's
#: own equation — move the equation's bounds and the yardstick must move with them, in one place.
TARGET_VALUE_CEILING = float(MAX_PRIZE_VALUE) + _SURVIVAL_CAP


def phase_scale(*, race_ahead: float | None, opp_prizes_remaining: int) -> float:
    """The KO-race-margin PHASE SCALER (ruling 5, docs/plans/opponent-value-equation-unification.md):
    converts a *turn of survival bought* into prize-equivalents ∈ [0, 1]. A survival turn is worth ≈0
    when I am stable and ahead, and ≈1 Prize when I am about to be KO'd with the race on the line —
    "how close either player is to their last Prize."

    Grounded in the same VISIBLE primitives as `objectives.plan_confidence` (ADR-0045): the two-sided
    race margin (`race_ahead` = their path turns − mine; behind = negative) and the opponent's Prize
    proximity (fewer of their Prizes left = higher stakes). **Bounded [0, 1] — the deliberate guard
    against the ADR-0065 +76 runaway (R1): NOT a free match-importance multiplier, a DERIVED, capped
    race scalar.** Seeds; ladder-matured."""
    s = _PHASE_BASE
    if race_ahead is not None:
        s -= _PHASE_RACE_W * float(race_ahead)              # behind (negative) raises the scale
    opp_close = max(0, min(_PRIZES_START, _PRIZES_START - int(opp_prizes_remaining))) / _PRIZES_START
    s += _PHASE_PRIZE_W * opp_close
    return max(0.0, min(1.0, s))


def survival_value(*, survival_shift: float, phase: float) -> float:
    """Turns of survival bought or LOST, in prize-equivalents — the survival leg on its own.

    ``survival_shift`` is a Δ on `turns_to_ko_me` against MY Active, from whatever counterfactual the
    caller is pricing: removing an opponent body (`opponent_target_value`), or shrinking the hand a
    hand-size attacker scales off (`pilot._hand_size_relief_tactical`, ADR-0102). ``phase`` is
    :func:`phase_scale`'s [0, 1] race scaler — how much one turn of survival is worth on this board.

    **SIGNED and SYMMETRICALLY capped** at ``±_SURVIVAL_CAP``. The sign matters because not every
    counterfactual can only help: a symmetric refresh played into a SMALL hand REFILLS the opponent
    and shortens my own clock, which is the ml f111 CRITICAL ("Judging a 1-card opponent hand is an
    enormous blunder") and the whole reason ADR-0102's term is priced rather than thresholded. Callers
    whose counterfactual is one-directional floor the shift THEMSELVES, at the call site, where the
    reason for the floor is legible — see :func:`opponent_target_value`.

    Sub-prize by construction (``_SURVIVAL_CAP`` < 1): it breaks ties among prize outcomes and never
    overrides a real prize difference (the gust-marginal discipline)."""
    return max(-_SURVIVAL_CAP,
               min(_SURVIVAL_CAP, float(survival_shift) * float(phase) * _SURVIVAL_PER_TURN))


def line_prize_advance(*, own_prize: float, max_line_prize: float, hops: float) -> float:
    """``prize_advance`` read as the LINE's prize rather than the body's own — **Denial Value**'s one
    new leg (ADR-0119 decision 2).

        own + (max_line_prize − own) × halve(hops)

    A 1-prize Staryu one hop from a 3-prize Mega Starmie ex prices at 2, where its own `prize_value`
    says 1 and cannot say otherwise. What removing it DENIES is the form that never arrives, and
    that quantity was priced nowhere before this — three authored constants in two modules were
    standing in for it at three different magnitudes.

    ``halve`` is `EvolveBody.p_arrive`'s shipped hop-discount (ADR-0070 §6), reused rather than a
    fourth decay rate invented here.

    **Bounded by `MAX_PRIZE_VALUE` by construction, and that is load-bearing rather than tidy.**
    `max_line_prize` is itself a `prize_value`, and the discount only ever shrinks the gap toward it,
    so the result stays in ``[own, MAX_PRIZE_VALUE]`` — which leaves :data:`TARGET_VALUE_CEILING`
    still, and with it BOTH rates derived from that ceiling in other modules
    (`state_value._THREAT_W`, `currency.GUST_TARGET_WORTH_RATE`). An ADDITIVE denial leg would have
    moved all three before the new reading did anything on the board.

    FLOORED at ``own_prize``: a forward form worth fewer prizes owes nothing (the direction
    `CombatMath.forward_payoff_terms` already floors owed damage), and an ABSENT supplier reads 0,
    which must not drag a body below the prize it is plainly worth."""
    gap = max(0.0, float(max_line_prize) - float(own_prize))
    return float(own_prize) + gap * halve(hops)


def opponent_target_value(*, prize_advance: float, survival_shift: float, phase: float) -> float:
    """The two-term OPPONENT-TARGET marginal (ruling 1): what removing/damaging an opponent body is
    worth to MY match = ``prize_advance`` (prize-race progress) + the ``survival_shift`` (turns of
    survival bought — Δ `turns_to_ko_me` from removing the body) converted to prize-equivalents by the
    ``phase`` scale (ruling 5). The survival term is SUB-prize (``_SURVIVAL_CAP`` < 1), so it breaks
    ties among prize outcomes but never overrides a real prize difference — the gust-marginal
    discipline. Redundancy (the ADR-0044 guards) is applied by the caller/gate, not priced here. The
    ONE currency snipe / gust / deny / promo-chip all read (Option B); seeds, grill-matured.

    The shift is FLOORED at 0 here rather than inside :func:`survival_value`, because the floor is
    this caller's policy and not the currency's: removing an opponent body can only RAISE my clock, so
    a negative reading is a bench-harvest redirect artefact rather than a cost of the removal. The
    hand-size counterfactual has no such guarantee and consumes the signed value."""
    return float(prize_advance) + survival_value(survival_shift=max(0.0, float(survival_shift)),
                                                 phase=phase)


def gust_target_slot(key: str, *, value: float) -> Slot:
    """The held gust-effect Trainer card (Guzma/Boss's-Orders-class) as a KEEP-priced slot (ADR-0076,
    generalizing `deny_slot` to a second instrument): unlike deny, this instrument is GRADED by the
    real per-body ``opponent_target_value`` (prize_advance + phase-scaled survival_shift) rather than
    firing at a flat disruption card-tier — a gust card doesn't strip Energy, so pricing it through
    the `deny` kind's oracle-value/timing-grade shape never matched what it actually does. No timing
    grade of its own (unlike `deny_slot`'s turns-to-ready halving): the two-term marginal is already
    the per-body "if used now" value, and no ruling has named a distinct gust deadline-discount —
    adding one here would be an un-derived guess. Deadline 0 (this-turn, un-bankable, mirroring
    `deploy_now_slot`'s closing-edge convention for a value with no re-access window of its own).

    ⚠️ **``value`` is WORTH-denominated, and the caller does the conversion**
    (`currency.target_value_to_worth`, Issue #313 item 2g) — exactly as `deploy_marginal`'s
    Worth-denominated result is divided by `currency.DEPLOY_WORTH_SCALE` at ITS call site, and for the
    same reason: this module is `card_worth`'s and `strategy.context`'s dependant, never `currency`'s,
    so the crossing cannot live here without inverting that arrow. Handing this function a raw
    prize-equivalent is the defect ADR-0076 Amendment E recorded and ADR-0080 decision 4 re-inherited
    — the slot then sums against wincon 30 / `deny` 10 / Energy 8 at a value that tops out at 3.9, and
    measured over the corpus the assignment covered one on a single frame in 80, usually losing even
    to the SAME card's own `general` slot."""
    return Slot("gust_target", float(value), 0, key)


# ─────────────────────────────────────────────────────────── the soundness nets
#: Card→slot SUPPLIES: which slot kinds each worth source (ROLE_TIER role / TAG_TIER tag / the
#: fallback classes) can fill. The COVERAGE LINT asserts every worth source appears here with ≥1
#: REAL kind — so no card class is silently priced 0 by a missed slot (Round-1 ruling).
SUPPLIES: dict = {
    # ROLE_TIER roles
    "win_condition":      ("line", "deploy_now", "answer_doom"),
    "primary_attacker":   ("line", "deploy_now", "answer_doom"),
    "secondary_attacker": ("line", "deploy_now"),
    "win_condition_base": ("line", "deploy_now"),
    "evolution_base":     ("line", "deploy_now"),
    "engine":             ("draw_engine",),
    "accel_source":       ("line",),
    "counter_mover":      ("line", "answer_doom"),
    "tutor":              ("supply_wincon",),
    # TAG_TIER tags
    "discard_eot":        ("fund_attack",),
    "clutch_heal":        ("answer_doom",),
    # ADR-0076: gust supplies BOTH kinds it could ever fill (the coverage lint just needs ≥1 real
    # kind named). WHICH kind is actually live for a given decision is the Pilot's call, gated by the
    # `gust_target_slots` kill-switch: OFF = today's `deny`-only routing (byte-identical); ON = gust
    # rows route to `gust_target` INSTEAD of `deny` (never both — `_resolve_needs` excludes gust from
    # `deny_tags` once armed, so one card is never priced through two instruments at once).
    "gust":               ("deny", "gust_target"),
    "recycle":            ("supply_wincon", "fund_attack"),
    # ADR-0086 (Issue #197): a bench-drop tutor (Meowth ex's Last-Ditch Catch) fetches a SUPPORTER,
    # so what it supplies is the DRAW/ENGINE need that Supporter serves — plus the wincon dig, when
    # the Supporter the deck holds is a tutor. It was absent from this table entirely, so the
    # coverage lint's promise ("no card class is silently priced 0 by a missed slot") did not hold
    # for it: the tag carried a `_READINESS_ABILITY_VALUE` but no slot kind, so the Needs assignment
    # priced a Meowth drop at nothing.
    "supporter_tutor":    ("draw_engine", "supply_wincon"),
    # fallback classes
    "typed_basic_energy": ("fund_attack", "fuel"),
    "ace_spec":           ("line", "answer_doom"),
    # behavioral tags outside TAG_TIER that are worth SOURCES in v2 (the deny leg is their only
    # pricing — a Crushing/Enhanced Hammer carries no ROLE/TAG tier, so without this route the
    # resolver would price it 0 and the hedge would carry it forever)
    "energy_denial":      ("deny",),
}

# ───────────────────────────────────────── WP-N2: exact assignment + marginals (Round-2 ruling)
_MAX_KEEP_SLOTS = 16    # bitmask-DP bound; beyond it the lowest-weight slots are dropped (an
                        # under-count of V on BOTH sides of a marginal — never a crash)


def _keep_slot_dp(slots, eligibility, resupply, exclude, capacity=None):
    """The exact-coverage core: over the KEEP slots (``supplied_by_pitch`` excluded), maximise
    Σ_covered v_j·(1−r_j) by assigning each non-excluded card to ≤1 eligible slot — lib-free
    bitmask DP over slot subsets. Returns (base, best): ``base`` = Σ_j v_j·r_j (what the closure
    re-supplies even with no held card) and ``best`` = the optimal held coverage on top.
    V = base + best.

    **COST: trivial at the eligibility real hands produce, super-linear in BREADTH — and this
    docstring used to claim the wrong one** (ADR-0122, Issue #406). It read *"(≤
    `_MAX_KEEP_SLOTS` × ≤ ~10 cards ⇒ trivial)"*, which reads as a claim about the BOUND. At the
    bound it names — 16 slots, 12 cards, every card eligible for every slot — it measures **748 ms
    per call**, three orders of magnitude off. Cost is driven by how many slots ONE card can supply
    (the mask space each row opens), not by the slot count `_MAX_KEEP_SLOTS` caps:

        eligible slots per card    1      2      3      4      5     16 (the declared bound)
        ms per call             1.63   4.49  10.06  23.64  61.37    748

    What makes it trivial in practice is that real hands are SPARSE. Censused over the ctx-7
    correction corpus (`tools/train/grab_sweep.py --breadth`, n = 1177 resolves): breadth **max 7,
    mean 1.57**, slot count **max 15**. Two things follow for anyone changing this file. The slot
    count is ONE below `_MAX_KEEP_SLOTS`, so the truncation below is adjacent rather than
    hypothetical; and a change that widens eligibility — a new slot kind many rows can supply, or a
    row made eligible for a class it merely reaches — buys cost on the curve above, not on the
    bound. `pilot._needs_v2` runs one `keep_v2` per hand row at every forced discard and that path
    DECIDES, so the exposure is already live and not confined to any new caller.

    ``capacity`` (ADR-0086, Issue #197) bounds how many cards may be assigned AT ONCE — the Bench
    holds 5, and that cap is the only reason a deploy displaces anything. Because each card takes at
    most one slot, the number of cards assigned is exactly the number of slots covered, so the bound
    is a **popcount bound on the mask** — an exact restriction of the same DP, not a heuristic.
    ``None`` means unbounded, which is every pre-existing caller (the keep/discard family has no
    capacity: holding a card costs no board slot). ``base`` is deliberately untouched by it: the
    closure re-supplies a slot whether or not a body is deployed."""
    cap = None if capacity is None else max(0, int(capacity))
    keep = [(j, s) for j, s in enumerate(slots) if not s.supplied_by_pitch]
    weighted = []
    for j, s in keep:
        r = min(1.0, max(0.0, float(resupply[j]) if j < len(resupply) else 0.0))
        weighted.append((j, s.value * (1.0 - r), s.value * r))
    weighted.sort(key=lambda t: -t[1])
    weighted = weighted[:_MAX_KEEP_SLOTS]
    base = sum(b for _j, _w, b in weighted)
    bit_of = {j: i for i, (j, _w, _b) in enumerate(weighted)}
    weights = [w for _j, w, _b in weighted]
    dp = {0: 0.0}
    for i, elig in enumerate(eligibility):
        if i in exclude:
            continue
        mask_i = 0
        for j in elig:
            if j in bit_of:
                mask_i |= 1 << bit_of[j]
        if not mask_i:
            continue
        ndp = dict(dp)
        for mask, val in dp.items():
            if cap is not None and mask.bit_count() >= cap:
                continue                     # capacity spent — this card cannot also be deployed
            free = mask_i & ~mask
            while free:
                low = free & -free
                nm = mask | low
                v = val + weights[low.bit_length() - 1]
                if v > ndp.get(nm, -1.0):
                    ndp[nm] = v
                free ^= low
        dp = ndp
    return base, max(dp.values())


def assignment_value(slots, eligibility, resupply, *, exclude=frozenset(),
                     capacity=None) -> float:
    """V(held \\ exclude) — expected slot coverage: a slot covered by a held card counts full; an
    uncovered slot counts value × its closure RESUPPLY odds (the re-access discount, derived); fuel
    slots (``supplied_by_pitch``) never enter the keep side. Exact (no greedy order-dependence —
    the Round-2 counterexample is the pinned proof).

    ``capacity`` caps how many cards may be assigned simultaneously (see :func:`_keep_slot_dp`);
    ``None``, the default, is the unbounded keep-side reading every pre-existing caller wants."""
    base, best = _keep_slot_dp(slots, eligibility, resupply, frozenset(exclude), capacity)
    return base + best


def keep_v2(slots, eligibility, resupply, index: int, *, intrinsic: float = 0.0) -> float:
    """The v2 keep-cost of held card ``index`` = ``V(all) − V(all − index)`` with re-assignment —
    the counterfactual marginal, exactly. ``intrinsic`` is the Round-1 transitional hedge: the
    card's v1 tier as a floor (`max(marginal, intrinsic)`) while the migration runs; a firing floor
    is missing-slot telemetry. Deadline-0 slots with 0 resupply lose full value (the deploy-now
    spike, derived); duplicate copies price marginally (the sibling covers — sets-not-sums)."""
    marginal = (assignment_value(slots, eligibility, resupply)
                - assignment_value(slots, eligibility, resupply, exclude={index}))
    return max(marginal, float(intrinsic))


def deploy_marginal(slots, eligibility, resupply, index: int, *, capacity) -> float:
    """What DEPLOYING card ``index`` into one of ``capacity`` free Bench slots is worth, in Worth
    points — the Deploy Marginal's assignment leg (ADR-0086, Issue #197, amendment E).

        net(X) = V(X deployed now, cap=K) − V(C \\ X, cap=K)

    — "the board's coverage if I spend a slot on X now" minus "its coverage if I don't, and the other
    candidates have all K slots." Deploying X consumes one capacity unit and covers at most one of
    X's eligible slots, so the left side is
    ``max_j∈elig(X) [ w_j + V(C \\ X, slots≠j, cap=K−1) ]``, floored by ``V(C \\ X, cap=K−1)`` for the
    case where X covers nothing at all but still eats the slot.

    Gain and displacement are NOT two subtractable terms — at tight capacity the gain already nets
    the displacement, and subtracting it again double-counts. They are two readings of this one
    difference, which is the Amendment-B correction restated at the arithmetic level.

    **Why not the ADR's written form.** Decision 2 spells the marginal `V(C) − V(C, X pinned)`, which
    is ≤ 0 for every candidate — forcing a card into an already-optimal assignment can only lower it,
    and the best candidate prices exactly 0. That ranks bodies against each other but can never clear
    `_finish_turn_last`'s floor, which is precisely `ms_free_bench_evolve_f17`'s failure mode (a good
    develop netting 0.0 and being starved by the `score <= 0` gate). The form above is the one under
    which decision 2's OWN sentence — "the cost of the 5th slot is emergent: exactly the contribution
    of the supplier it displaces" — is literally true of a computed quantity.

    Both properties the ADR asks for fall out rather than being asserted:

    * **emergent, never a constant** — displacement is whatever the displaced supplier was worth, so
      a last slot contested by a 25 is dearer than the same slot contested by a 5;
    * **zero on an empty Bench** — with slack capacity, dropping one unit costs the others nothing,
      so `displacement == 0` and a deploy nets its full gain.

    A REDUNDANT body prices 0 gain however free the Bench, because redundancy is a property of the
    board (a sibling already covers the slot) rather than of scarcity — the f51 shape. Deliberately
    signed: a body worth less than what it displaces nets NEGATIVE, which is how the take-fewer
    decline and the turn-ender floor come to refuse it.

    Worth-denominated, like everything else in this module. The caller divides by
    `currency.DEPLOY_WORTH_SCALE` to get the dimensionless relevance that crosses into the damage
    scale (ADR-0086 amendment B) — this function must never be handed to a damage-scale consumer raw.
    """
    k = max(0, int(capacity))
    if k <= 0:
        # No free slot: the deploy cannot HAPPEN, so there is no counterfactual and the marginal is
        # exactly 0. Without this the branch below still credited X its slot's value — it enumerates
        # X's eligible slots without asking whether X can take one — and priced a full positive
        # marginal for an impossible play. Latent while only `_PLAY` was wired (the engine never
        # offers an illegal placement), reachable from `_TO_BENCH`'s greedy multi-pick, where the
        # capacity is OUR hypothetical after an earlier pick rather than the engine's menu.
        return 0.0
    without = frozenset({index})
    tight = max(0, k - 1)
    # Not deploying X: the other candidates have every free slot.
    v_without = assignment_value(slots, eligibility, resupply, exclude=without, capacity=k)
    # Deploying X: it eats one slot whether or not it covers anything (the floor), and may cover one
    # of its own — in which case that slot is no longer available to the rest.
    best = assignment_value(slots, eligibility, resupply, exclude=without, capacity=tight)
    for j in (eligibility[index] if 0 <= index < len(eligibility) else ()):
        if not (0 <= j < len(slots)) or slots[j].supplied_by_pitch:
            continue
        r = min(1.0, max(0.0, float(resupply[j]) if j < len(resupply) else 0.0))
        taken = [set(e) - {j} for e in eligibility]      # X took slot j; nobody else may cover it
        best = max(best, slots[j].value * (1.0 - r)
                   + assignment_value(slots, taken, resupply, exclude=without, capacity=tight))
    return best - v_without


def assignment_split(slots, eligibility, resupply, *, exclude=frozenset(),
                     capacity=None) -> tuple:
    """:func:`assignment_value`'s TWO halves, separately: ``(re_access, coverage)``.

    ``re_access`` is ``Σ_j v_j·r_j`` — what the closure re-supplies with no held card at all — and
    ``coverage`` is the optimal held coverage on top; ``assignment_value`` is their sum, so this
    cannot disagree with it (one DP, two readings).

    Exposed for `state_value`'s ``hand`` family (POC-T3, Issue #262), whose frozen composition is
    *"assignment coverage of LIVE slots PLUS re-access"* — two named sub-values that a single
    ``V`` has already added together. Recovering them by differencing (``V`` minus ``V`` at zero
    resupply) would re-run the DP and, worse, would not agree with it at the margin: the coverage
    half is chosen against the DISCOUNTED weights, so zeroing resupply changes which assignment
    wins rather than just its price."""
    base, best = _keep_slot_dp(slots, eligibility, resupply, frozenset(exclude), capacity)
    return base, best


@dataclass(frozen=True)
class Resolution:
    """A position's Needs, RESOLVED — the shape :attr:`common.state_model.MySide.needs` carries.

    The model's docstring already promised this: *"the model does not own the Needs engine; it holds
    the resolution so several equations read one assignment instead of each re-running the DP."*
    Until POC-T3 nothing supplied one, so `MySide.needs` was `None` in production and every consumer
    re-resolved. This is the value type that closes that, and it is a plain record on purpose — the
    Pilot owns the board→slots derivation (`_resolve_needs`), this module owns the assignment maths,
    and neither reaches into the other.

    ``latent_worth`` is supplied by the RESOLVER rather than derived here because its discount is a
    Pilot-side constant (`_GENERAL_WORTH_W`); a value equation that reached for it would be reaching
    into the Pilot, which `state_value` is asserted at import not to do."""

    #: The position's Needs slots.
    slots: tuple = ()
    #: Per held card, the slot indices it can supply. Index-aligned with :attr:`hand_ids`.
    eligibility: tuple = ()
    #: Per slot, P(the closure re-supplies it inside its deadline). Index-aligned with `slots`.
    resupply: tuple = ()
    #: The held cards, in hand order — so a consumer can name which card a marginal belongs to.
    hand_ids: tuple = ()
    #: Worth of held cards that fill NO specific slot, already discounted by the resolver.
    latent_worth: float = 0.0

    def split(self) -> tuple:
        """``(re_access, coverage)`` over the whole held hand — :func:`assignment_split` applied."""
        return assignment_split(list(self.slots), list(self.eligibility), list(self.resupply))

    def set_keep(self, indices) -> float:
        """:func:`set_keep_v2` over this resolution — what losing ``indices`` jointly costs."""
        return set_keep_v2(list(self.slots), list(self.eligibility), list(self.resupply), indices)


def set_keep_v2(slots, eligibility, resupply, indices) -> float:
    """The SET marginal — ``V(all) − V(all − indices)``: what a multi-pick discard jointly costs.
    Two duplicate wincons solo-price 0 each (the sibling covers) but the PAIR prices full — the
    duplicate-wincon naivety is structurally impossible here."""
    return (assignment_value(slots, eligibility, resupply)
            - assignment_value(slots, eligibility, resupply, exclude=frozenset(indices)))


def pitch_gain(slots, eligibility, index: int) -> float:
    """The pitch side: the best ``supplied_by_pitch`` (fuel) slot card ``index`` can fill by BEING
    discarded — pitching it is progress, so it subtracts from its removal cost. One slot per card
    (v1 — a second matching fuel card re-prices next decision)."""
    best = 0.0
    for j in eligibility[index] if index < len(eligibility) else ():
        if j < len(slots) and slots[j].supplied_by_pitch:
            best = max(best, slots[j].value)
    return best


def cheapest_removal(slots, eligibility, resupply, intrinsics, picks: int,
                     deadness=None, tiebreak=None) -> list:
    """The discard decider's objective (WP-N3/N4 consume this): the ``picks``-subset with the
    lowest removal score, where

        score(P) = max( set_keep_v2(P), max_{i∈P} intrinsic_i ) − Σ_{i∈P} pitch_gain(i)

    — the joint keep loss (exact set marginal), floored by the most-protected member's hedge (a
    MAX, not a sum: summing intrinsics would re-introduce the double-count sets-not-sums kills),
    minus what pitching actively gains (fuel). Brute-force over C(n, picks) (n ≤ ~10 ⇒ ≤ ~250
    subsets — trivial).

    The ranking key is ``(score, −Σ deadness, Σ tiebreak, indices)`` — the score first, then two
    per-card legs that discriminate only where it TIES, then the index. Both legs are optional and
    both are ordering-only: neither can make a removal look cheaper than one that genuinely costs
    less, which is the property that lets a CATEGORICAL fact rank without being handed a magnitude.

    ``deadness`` (per-card, ADR-0106): a CATEGORICAL 0/1 — a card whose role has EXPIRED (a
    spent `opener`, a burst whose Active is already powered, a tutor whose target is in hand, a
    stranded evolution, declared fodder) is actively best gone. Keep-cost cannot express that:
    `keep_cost = Worth × Odds × Gates` is a product of non-negative factors, and for a dead card
    `P(met | keep) = P(met | pitch) = 0` — so the equation's honest answer is exactly the 0 a
    worthless live spare also prices. "Shed the dead one" is therefore a preference ORDER over cards
    the equation prices EQUAL, and it rides the key rather than inventing a term, which is the same
    shape as ADR-0103 one layer up (an exact tie stopped being resolved by menu position). Summing
    it across the SET is a different and sound claim: shedding two dead cards beats shedding one.

    ``tiebreak`` (per-card, below deadness): among still-equal removals the set with the lower
    Σ tiebreak sheds first — the resolver passes residual worth (worth × deploy), so a worth-10
    redundancy is preserved over a worth-8 one (the 83967840-54 corpus ruling, v1's worth tie-break
    re-derived). It sits BELOW deadness because residual worth reads a card's CATALOG tier, which a
    dead card still carries: a spent Ignition prices worth 30 against a role-less spare's 0, so
    worth-first sheds the live spare and keeps the corpse (`83454549-36`, the shipped defect).

    Final tie → lower indices; returns a sorted list."""
    from itertools import combinations
    n = len(eligibility)
    k = max(0, min(int(picks), n))
    tb = list(tiebreak) if tiebreak is not None else [0.0] * n
    dead = list(deadness) if deadness is not None else [0.0] * n
    best_set, best_key = None, None
    for combo in combinations(range(n), k):
        score = removal_score(slots, eligibility, resupply, intrinsics, combo)
        key = (score,
               -sum(dead[i] for i in combo if i < len(dead)),
               sum(tb[i] for i in combo if i < len(tb)))
        if best_key is None or key < best_key:
            best_set, best_key = combo, key
    return sorted(best_set or ())


def removal_score(slots, eligibility, resupply, intrinsics, indices) -> float:
    """What shedding ``indices`` COSTS, net — the objective `cheapest_removal` minimises:

        ``max( set_keep_v2(P), max_{i∈P} intrinsic_i ) − Σ_{i∈P} pitch_gain(i)``

    Named and public because two callers need the same number, not just the same argmin: the discard
    decider picks the set that minimises it, and the fetch doctrine's shed PREDICTOR asks what the
    set the decider *would* pick costs, to decide whether a `cost_discard` search is being paid for
    in junk or in live cards (ADR-0103 amendment, Issue #261 item 2h). Predicting with a different
    formula than the one that decides is the drift `_discard_equation_rows` was just narrowed to
    prevent.

    ``<= 0`` means the shed is free or actively progress (a fuel pitch gains more than the cards
    cost); positive is a real price paid."""
    floor = max((float(intrinsics[i]) if i < len(intrinsics) else 0.0 for i in indices),
                default=0.0)
    return (max(set_keep_v2(slots, eligibility, resupply, indices), floor)
            - sum(pitch_gain(slots, eligibility, i) for i in indices))


#: The DISSOLUTION LEDGER: every gate/flag of the v1 keep_value equation → the slot kind that
#: re-derives it. Retiring a gate not listed here (or listed against a kind that doesn't exist) is
#: a red test — the migration cannot silently drop corpus-anchored knowledge.
DISSOLUTION_LEDGER: dict = {
    "evolution_gate":         "line",           # dead evolution = no line slot its base can open
    "fetcher_gate":           "supply_wincon",  # every target dead = the supply slot is absent
    "need_met_gate":          "supply_wincon",  # wincon in hand = the supply slot is absent
    "pressure_gate":          "answer_doom",
    "quota_gate":             "fund_attack",    # unit deadlines ARE the quota ranks
    "deploy_now_spike":       "deploy_now",
    "spent_burst":            "fund_attack",    # zero cost_remaining = no slot for the burst
    "engine_supporter_floor": "draw_engine",
    "fuel_sign":              "fuel",
}
