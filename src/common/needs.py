"""Needs — WHAT the position requires: deadline-tagged SLOTS derived from board state, valued in the
ONE currency (ADR-0065, `ADR-0065`).

A held card's keep-value is its marginal slot coverage, so multi-copies, doom, quotas, fuel and
deploy-now are slot PROPERTIES resolved globally in the assignment, not pairwise gates. Opponent-side
reads VISIBLE state only. Pure and lib-free; the Pilot resolves board facts and passes them.
Horizon discipline: consumers cap Σ slot values < KO_SCORE (the readiness invariant).
"""
from __future__ import annotations

from dataclasses import dataclass

from common.card_worth import ROLE_TIER, ENERGY_TIER
from common.grading import halve      # the ONE hop/turn discount convention (ADR-0070 §6)
from common.strategy.context import (MAX_PRIZE_VALUE,   # the rules' own constants, one home
                                     PRIZE_CARDS)

#: Every slot kind the vocabulary knows. The coverage lint rejects a SUPPLIES entry naming
#: anything outside this set.
SLOT_KINDS = frozenset({
    "fund_attack",    # a missing Energy unit on a body (deadline = its quota rank)
    "deploy_now",     # an eligible evolution play THIS turn
    "line",           # a Line member still to be assembled (no this-turn deadline)
    "answer_doom",    # heal/switch/successor against the threat read
    "draw_engine",    # the recurring draw need (saturating)
    "supply_wincon",  # the tutor's fetch target (absent when the wincon is in hand)
    "fuel",           # discard-source accel fuel — SUPPLIED BY PITCHING (the zone sign)
    "deny",           # strip THEIR resource; deadline from their turns-to-ready
    "gust_target",    # a held gust-effect Trainer, by the opponent-target marginal (ADR-0076)
    "general",        # a held card's LATENT board worth where it fills no specific need
})


@dataclass(frozen=True)
class Slot:
    """One need: ``value`` in the one currency, ``deadline`` in turns (0 = this turn).
    ``supplied_by_pitch`` marks the fuel class — the slot a DISCARD fills."""
    kind: str
    value: float
    deadline: int
    key: str
    supplied_by_pitch: bool = False


# ─────────────────────────────────────────────────────────── my-side derivations
def fund_attack_slots(body_key: str, cost_remaining: int, *, quota_spent: bool = False) -> list:
    """One slot per missing Energy unit; deadline = attach turns out (1 manual attach/turn,
    rules.md §3), +1 across the board when this turn's attach is already spent."""
    base = 1 if quota_spent else 0
    return [Slot("fund_attack", ENERGY_TIER, base + j, f"{body_key}:unit{j}")
            for j in range(max(0, int(cost_remaining)))]


def deploy_now_slot(key: str, *, value: float) -> Slot:
    """Deadline 0: a card assigned to a deadline-0 slot cannot bank re-access, so its marginal is
    full."""
    return Slot("deploy_now", float(value), 0, key)


#: Roles whose line carries a SUCCESSION need: the plan must survive attrition, so a spare copy's
#: marginal is real, never 0.
SUCCESSION_ROLES = frozenset({"win_condition", "primary_attacker"})


def line_slots(key: str, *, value: float, succession: bool = False,
               primary_met: bool = False, succession_urgent: bool = False,
               deadline: int = 99, succ_deadline: int = 99) -> list:
    """``deadline`` / ``succ_deadline`` default 99 = LATENT; only `pilot._refresh_slot_resupply`
    consumes them (clamping the re-access window), so every other caller is unaffected."""
    out = []
    if not primary_met:
        out.append(Slot("line", float(value), deadline, key))
    if succession:
        succ_val = float(value) if succession_urgent else float(value) / 2.0
        sd = 0 if succession_urgent else succ_deadline
        out.append(Slot("line", succ_val, sd, f"{key}:succ"))
    return out


def answer_doom_slot(*, value: float, deadline: int = 0) -> Slot:
    """``value`` is the DOOMED BODY'S OWN preserved worth — what saving the Active preserves — NOT a
    flat tier and NOT the swap card's own catalog worth."""
    return Slot("answer_doom", float(value), int(deadline), "answer_doom")


def insure_wincon_slot(key: str, *, value: float, deadline: int = 1) -> Slot:
    """Opens on the win-condition LINE being exhausted, not on `active_doomed` (ADR-0101). Kind
    ``answer_doom`` so `_refresh_slot_resupply` zeroes its re-access — the closing edge is the point."""
    return Slot("answer_doom", float(value), int(deadline), key)


def draw_engine_slot(*, engines_online: int, value: float | None = None) -> Slot:
    """``value`` overrides the engine-ROLE tier with the band the resolver reads off the eligible
    suppliers (a supporter-only engine need is the engine-supporter band, not the engine-body tier)."""
    base = ROLE_TIER["engine"] if value is None else float(value)
    return Slot("draw_engine", base if engines_online <= 0 else base / 2.0, 0, "draw_engine")


def supply_wincon_slot(*, wincon_in_hand: bool, target_reachable: bool):
    """The need-met and fetcher gates re-derived as slot ABSENCE: no slot → the tutor's marginal is
    0, no gate required."""
    if wincon_in_hand or not target_reachable:
        return None
    return Slot("supply_wincon", ROLE_TIER["tutor"], 99, "supply_wincon")


def fuel_slot(key: str, *, value: float) -> Slot:
    """Discard-source accel fuel (Aura Jab class, `_discard_fuel_types`): a card assigned here
    contributes by being DISCARDED, so its keep-side marginal is ≤ 0."""
    return Slot("fuel", float(value), 99, key, supplied_by_pitch=True)


def general_worth_slot(key: str, *, value: float) -> Slot:
    """A held card's LATENT worth where it fills no SPECIFIC need. The resolver emits ONE per
    distinct held card and pre-discounts ``value``; it must sit BELOW every specific slot."""
    return Slot("general", float(value), 99, key)


# ─────────────────────────────────────────────────── opponent-side (Round-3 ruling)
def turns_to_ready(*, energy_deficit: int, evolve_hops: int, attaches_per_turn: int = 1) -> int:
    """Attaching and evolving run in PARALLEL, so the read is the MAX of the two legs, never the
    sum. Clamped at 0 (surplus/ready)."""
    e = max(0, int(energy_deficit))
    per = max(1, int(attaches_per_turn))
    attach_turns = (e + per - 1) // per
    return max(attach_turns, max(0, int(evolve_hops)))


def deny_slot(key: str, *, oracle_value: float, turns_to_ready: int) -> Slot:
    """``oracle_value`` is a MISNOMER kept for call-compatibility (ADR-0078/0080): the caller passes
    `TAG_TIER["gust"] x relevance`, NOT the ADR-0062 oracle. The `/2**t` grade prices WHEN it lands."""
    t = max(0, int(turns_to_ready))
    return Slot("deny", float(oracle_value) / (2 ** t), t, key)


# ─────────────────────────── the two-term opponent-target marginal (Opponent Value Equation, S3)
_PRIZES_START = PRIZE_CARDS # the rules' own constant, homed once in `strategy.context` (Issue #279)
_PHASE_BASE = 0.3           # neutral phase weight (no race read)
_PHASE_RACE_W = 0.15        # per turn-of-race-margin: BEHIND sharpens each survival turn, ahead flattens
_PHASE_PRIZE_W = 0.5        # prize-proximity weight. Seed.
_SURVIVAL_PER_TURN = 0.5    # prize-equivalents per turn-of-survival bought, before the phase scale
_SURVIVAL_CAP = 0.9         # keeps the survival term SUB-prize: breaks ties, never overrides a prize

#: The CEILING of :func:`opponent_target_value` as every shipped caller supplies it: `MAX_PRIZE_VALUE`
#: + `_SURVIVAL_CAP` = 3.9. NOT enforced here — `currency.target_value_to_worth` clamps and divides.
TARGET_VALUE_CEILING = float(MAX_PRIZE_VALUE) + _SURVIVAL_CAP


def phase_scale(*, race_ahead: float | None, opp_prizes_remaining: int) -> float:
    """Converts one turn of survival bought into prize-equivalents ∈ [0, 1]; ``race_ahead`` = their
    path turns − mine (behind = negative). The [0, 1] bound guards the ADR-0065 +76 runaway."""
    s = _PHASE_BASE
    if race_ahead is not None:
        s -= _PHASE_RACE_W * float(race_ahead)              # behind (negative) raises the scale
    opp_close = max(0, min(_PRIZES_START, _PRIZES_START - int(opp_prizes_remaining))) / _PRIZES_START
    s += _PHASE_PRIZE_W * opp_close
    return max(0.0, min(1.0, s))


def survival_value(*, survival_shift: float, phase: float) -> float:
    """``survival_shift`` is a Δ on `turns_to_ko_me`, in prize-equivalents after ``phase``. SIGNED
    and symmetrically capped: a one-directional caller floors the shift ITSELF, at the call site."""
    return max(-_SURVIVAL_CAP,
               min(_SURVIVAL_CAP, float(survival_shift) * float(phase) * _SURVIVAL_PER_TURN))


def line_prize_advance(*, own_prize: float, max_line_prize: float, hops: float) -> float:
    """The LINE's prize, not the body's own (ADR-0119). Bounded by `MAX_PRIZE_VALUE` by construction
    — an ADDITIVE leg would move :data:`TARGET_VALUE_CEILING` and both rates derived from it."""
    gap = max(0.0, float(max_line_prize) - float(own_prize))
    return float(own_prize) + gap * halve(hops)


def opponent_target_value(*, prize_advance: float, survival_shift: float, phase: float) -> float:
    """What removing/damaging an opponent body is worth, in prize-equivalents; redundancy is the
    caller's gate, not priced here. The shift is FLOORED at 0 HERE, as this caller's own policy."""
    return float(prize_advance) + survival_value(survival_shift=max(0.0, float(survival_shift)),
                                                 phase=phase)


def gust_target_slot(key: str, *, value: float) -> Slot:
    """⚠️ ``value`` is WORTH-denominated and the CALLER converts (`currency.target_value_to_worth`);
    handing this a raw prize-equivalent is the ADR-0076 Amendment E defect. Deadline 0, no grade."""
    return Slot("gust_target", float(value), 0, key)


# ─────────────────────────────────────────────────────────── the soundness nets
#: Card→slot SUPPLIES. The COVERAGE LINT asserts every worth source names ≥1 REAL kind here.
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
    # BOTH kinds gust could fill; the `gust_target_slots` switch picks which is live per decision —
    # never both (`_resolve_needs` drops gust from `deny_tags` once armed). ADR-0076.
    "gust":               ("deny", "gust_target"),
    "recycle":            ("supply_wincon", "fund_attack"),
    # a bench-drop tutor fetches a SUPPORTER, so it supplies that Supporter's needs (ADR-0086)
    "supporter_tutor":    ("draw_engine", "supply_wincon"),
    # fallback classes
    "typed_basic_energy": ("fund_attack", "fuel"),
    "ace_spec":           ("line", "answer_doom"),
    # a Hammer carries no ROLE/TAG tier, so without this route the resolver prices it 0
    "energy_denial":      ("deny",),
}

# ───────────────────────────────────────── WP-N2: exact assignment + marginals (Round-2 ruling)
_MAX_KEEP_SLOTS = 16    # bitmask-DP bound; beyond it lowest-weight slots drop (under-count, no crash)


def _keep_slot_dp(slots, eligibility, resupply, exclude, capacity=None):
    """``(base, best)``: closure re-supply Σ_j v_j·r_j plus optimal held coverage; V = base + best.
    Cost is super-linear in per-card BREADTH, not slot count (ADR-0122); ``capacity`` caps popcount."""
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
    """V(held \\ exclude): a covered slot counts full, an uncovered one counts value × its closure
    RESUPPLY odds; fuel slots never enter the keep side. Exact — no greedy order-dependence."""
    base, best = _keep_slot_dp(slots, eligibility, resupply, frozenset(exclude), capacity)
    return base + best


def keep_v2(slots, eligibility, resupply, index: int, *, intrinsic: float = 0.0) -> float:
    """``V(all) − V(all − index)`` with re-assignment. ``intrinsic`` is a transitional v1-tier floor;
    a FIRING floor is missing-slot telemetry."""
    marginal = (assignment_value(slots, eligibility, resupply)
                - assignment_value(slots, eligibility, resupply, exclude={index}))
    return max(marginal, float(intrinsic))


def deploy_marginal(slots, eligibility, resupply, index: int, *, capacity) -> float:
    """WORTH-denominated, signed (ADR-0086): ``V(X deployed, cap=K) − V(C \\ X, cap=K)`` — gain nets
    displacement in ONE difference. The caller divides by `currency.DEPLOY_WORTH_SCALE`."""
    k = max(0, int(capacity))
    if k <= 0:
        # No free slot: the deploy cannot HAPPEN, so the marginal is exactly 0. Without this the loop
        # below credits X its slot's value for an impossible play (reachable from `_TO_BENCH`).
        return 0.0
    without = frozenset({index})
    tight = max(0, k - 1)
    v_without = assignment_value(slots, eligibility, resupply, exclude=without, capacity=k)
    # Deploying X eats one slot whether or not it covers anything, and may cover one of its own.
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
    """:func:`assignment_value`'s two halves as ``(re_access, coverage)``. NOT recoverable by
    differencing: zeroing resupply changes WHICH assignment wins, not just its price."""
    base, best = _keep_slot_dp(slots, eligibility, resupply, frozenset(exclude), capacity)
    return base, best


@dataclass(frozen=True)
class Resolution:
    """A position's Needs, RESOLVED — the shape :attr:`common.state_model.MySide.needs` carries. The
    Pilot owns the board→slots derivation (`_resolve_needs`); this module owns the assignment maths."""

    slots: tuple = ()
    #: Per held card, the slot indices it can supply. Index-aligned with :attr:`hand_ids`.
    eligibility: tuple = ()
    #: Per slot, P(the closure re-supplies it inside its deadline). Index-aligned with `slots`.
    resupply: tuple = ()
    #: The held cards, in hand order.
    hand_ids: tuple = ()
    #: Worth of held cards that fill NO specific slot, already discounted by the resolver.
    latent_worth: float = 0.0
    #: Per-card contribution to ``latent_worth``. Optional for existing callers; discard projection
    #: uses it to keep the root demand ledger fixed while cards leave the hand.
    latent_by_hand: tuple = ()

    def split(self) -> tuple:
        """``(re_access, coverage)`` over the whole held hand."""
        return assignment_split(list(self.slots), list(self.eligibility), list(self.resupply))

    def set_keep(self, indices) -> float:
        return set_keep_v2(list(self.slots), list(self.eligibility), list(self.resupply), indices)


def set_keep_v2(slots, eligibility, resupply, indices) -> float:
    """``V(all) − V(all − indices)``: two duplicate wincons solo-price 0 each (the sibling covers)
    but the PAIR prices full."""
    return (assignment_value(slots, eligibility, resupply)
            - assignment_value(slots, eligibility, resupply, exclude=frozenset(indices)))


def pitch_gain(slots, eligibility, index: int) -> float:
    """The best fuel slot ``index`` fills by BEING discarded — it subtracts from removal cost."""
    best = 0.0
    for j in eligibility[index] if index < len(eligibility) else ():
        if j < len(slots) and slots[j].supplied_by_pitch:
            best = max(best, slots[j].value)
    return best


def cheapest_removal(slots, eligibility, resupply, intrinsics, picks: int,
                     deadness=None, tiebreak=None) -> list:
    """The ``picks``-subset minimising :func:`removal_score`, ranked ``(score, −Σ deadness, Σ tiebreak,
    indices)``; ``deadness`` (0/1, ADR-0106) outranks ``tiebreak``, else a corpse's catalog tier wins."""
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
    """Public because the discard decider and the fetch shed PREDICTOR must use the SAME formula, not
    just the same argmin (ADR-0103). ``<= 0`` = the shed is free or actively progress."""
    floor = max((float(intrinsics[i]) if i < len(intrinsics) else 0.0 for i in indices),
                default=0.0)
    return (max(set_keep_v2(slots, eligibility, resupply, indices), floor)
            - sum(pitch_gain(slots, eligibility, i) for i in indices))


#: Every v1 keep_value gate → the slot kind that re-derives it. Retiring a gate not listed here (or
#: listed against a kind that doesn't exist) is a red test.
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
