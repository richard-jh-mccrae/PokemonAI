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
    card-tier `TAG_TIER["gust"]` (~10) — `pilot._resolve_needs` — and the ADR-0062 oracle survives on
    that path only as a `> 0` BITE GATE (`_denial_at`), its damage magnitude discarded.

    ADR-0078 (#187 grill) overturns that WP-N8 ruling in turn: deny is to read the shared per-body
    `opponent_target_value` marginal on all three of its surfaces (this keep slot, the play rung, the
    target pick), converted at a DERIVED rate rather than consumed raw — the Worth Damage Rate, which
    is specified but **not yet derived** (it needs a keep-side corpus anchor that does not exist).
    Until the S3c prerequisite lands, this stays the flat tier.

    Resupply ruling (recorded for the closure-discount thread; vacuous while resupply is 0.0):
    a DEADLINE-0 deny slot must take resupply 0.0 — a deny needed NOW is not re-drawable in time,
    the same closing edge that makes `deploy_now` un-bankable; slack (deadline ≥ 1) deny slots may
    take their supplier classes' re-access odds over that window."""
    t = max(0, int(turns_to_ready))
    return Slot("deny", float(oracle_value) / (2 ** t), t, key)


# ─────────────────────────── the two-term opponent-target marginal (Opponent Value Equation, S3)
_PRIZES_START = 6           # the Prize-count both players race down from
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


def opponent_target_value(*, prize_advance: float, survival_shift: int, phase: float) -> float:
    """The two-term OPPONENT-TARGET marginal (ruling 1): what removing/damaging an opponent body is
    worth to MY match = ``prize_advance`` (prize-race progress) + the ``survival_shift`` (turns of
    survival bought — Δ `turns_to_ko_me` from removing the body) converted to prize-equivalents by the
    ``phase`` scale (ruling 5). The survival term is SUB-prize (``_SURVIVAL_CAP`` < 1), so it breaks
    ties among prize outcomes but never overrides a real prize difference — the gust-marginal
    discipline. Redundancy (the ADR-0044 guards) is applied by the caller/gate, not priced here. The
    ONE currency snipe / gust / deny / promo-chip all read (Option B); seeds, grill-matured."""
    survival = min(_SURVIVAL_CAP, max(0.0, float(survival_shift)) * float(phase) * _SURVIVAL_PER_TURN)
    return float(prize_advance) + survival


def gust_target_slot(key: str, *, value: float) -> Slot:
    """The held gust-effect Trainer card (Guzma/Boss's-Orders-class) as a KEEP-priced slot (ADR-0076,
    generalizing `deny_slot` to a second instrument): unlike deny, this instrument's value is the
    real per-body ``opponent_target_value`` (prize_advance + phase-scaled survival_shift), not the
    flat disruption card-tier — a gust card doesn't strip Energy, so pricing it through the `deny`
    kind's oracle-value/timing-grade shape never matched what it actually does. No timing grade of
    its own (unlike `deny_slot`'s turns-to-ready halving): the two-term marginal is already the
    per-body "if used now" value, and no ruling has named a distinct gust deadline-discount — adding
    one here would be an un-derived guess. Deadline 0 (this-turn, un-bankable, mirroring
    `deploy_now_slot`'s closing-edge convention for a value with no re-access window of its own)."""
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


def _keep_slot_dp(slots, eligibility, resupply, exclude):
    """The exact-coverage core: over the KEEP slots (``supplied_by_pitch`` excluded), maximise
    Σ_covered v_j·(1−r_j) by assigning each non-excluded card to ≤1 eligible slot — lib-free
    bitmask DP over slot subsets (≤ `_MAX_KEEP_SLOTS` × ≤ ~10 cards ⇒ trivial). Returns
    (base, best): ``base`` = Σ_j v_j·r_j (what the closure re-supplies even with no held card) and
    ``best`` = the optimal held coverage on top. V = base + best."""
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


def assignment_value(slots, eligibility, resupply, *, exclude=frozenset()) -> float:
    """V(held \\ exclude) — expected slot coverage: a slot covered by a held card counts full; an
    uncovered slot counts value × its closure RESUPPLY odds (the re-access discount, derived); fuel
    slots (``supplied_by_pitch``) never enter the keep side. Exact (no greedy order-dependence —
    the Round-2 counterexample is the pinned proof)."""
    base, best = _keep_slot_dp(slots, eligibility, resupply, frozenset(exclude))
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
                     tiebreak=None) -> list:
    """The discard decider's objective (WP-N3/N4 consume this): the ``picks``-subset with the
    lowest removal score, where

        score(P) = max( set_keep_v2(P), max_{i∈P} intrinsic_i ) − Σ_{i∈P} pitch_gain(i)

    — the joint keep loss (exact set marginal), floored by the most-protected member's hedge (a
    MAX, not a sum: summing intrinsics would re-introduce the double-count sets-not-sums kills),
    minus what pitching actively gains (fuel). Brute-force over C(n, picks) (n ≤ ~10 ⇒ ≤ ~250
    subsets — trivial).

    ``tiebreak`` (optional, per-card): among EQUAL-score removals the set with the lower Σ tiebreak
    sheds first — the resolver passes residual worth (worth × deploy), so a worth-10 redundancy is
    preserved over a worth-8 one and a deploy-dead card sheds before either (the 83967840-54 corpus
    ruling, v1's worth tie-break re-derived). Final tie → lower indices; returns a sorted list."""
    from itertools import combinations
    n = len(eligibility)
    k = max(0, min(int(picks), n))
    tb = list(tiebreak) if tiebreak is not None else [0.0] * n
    best_set, best_key = None, None
    for combo in combinations(range(n), k):
        floor = max((float(intrinsics[i]) if i < len(intrinsics) else 0.0 for i in combo),
                    default=0.0)
        score = (max(set_keep_v2(slots, eligibility, resupply, combo), floor)
                 - sum(pitch_gain(slots, eligibility, i) for i in combo))
        key = (score, sum(tb[i] for i in combo if i < len(tb)))
        if best_key is None or key < best_key:
            best_set, best_key = combo, key
    return sorted(best_set or ())


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
