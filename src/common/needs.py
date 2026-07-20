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
               primary_met: bool = False) -> list:
    """The line slots for ONE card class: the primary assembly slot at the full tier (absent when a
    copy is already IN PLAY — ``primary_met``, the in_play gate re-derived as slot absence), plus —
    for a wincon class (``succession=True``, `SUCCESSION_ROLES`) — a half-tier SUCCESSION slot: the
    plan needs the line to survive attrition (KOs and prizing take bodies), so a spare copy's solo
    marginal is the half tier, never 0 — "copy 2's marginal = its next-best slot" (the grill spec's
    own sets-not-sums answer). Halving mirrors `draw_engine_slot` saturation; no this-turn deadline
    (a deploy-now slot supersedes for the same hop)."""
    out = []
    if not primary_met:
        out.append(Slot("line", float(value), 99, key))
    if succession:
        out.append(Slot("line", float(value) / 2.0, 99, f"{key}:succ"))
    return out


def answer_doom_slot(*, value: float, deadline: int = 0) -> Slot:
    """The pressure gate re-derived: the threat read (`active_doomed` / incoming) opens an answer
    slot — heal / switch / the successor — at the threat's deadline."""
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
    """The graded Hammer (the user's 86091435-68 ruling, with TIMING): strip THEIR resource. The
    VALUE comes from the shipped denial oracle (ADR-0062 `_opp_denial_best` — consumed, never
    re-derived) and grades toward full as their body nears ready: at deadline 0 the full oracle
    value; each turn of slack halves it (a closing edge inverted — urgency, not decay of worth)."""
    t = max(0, int(turns_to_ready))
    return Slot("deny", float(oracle_value) / (2 ** t), t, key)


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
    "gust":               ("deny",),
    "recycle":            ("supply_wincon", "fund_attack"),
    # fallback classes
    "typed_basic_energy": ("fund_attack", "fuel"),
    "ace_spec":           ("line", "answer_doom"),
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
