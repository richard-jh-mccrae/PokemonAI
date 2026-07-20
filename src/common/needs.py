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


def line_slot(key: str, *, value: float, deadline: int = 99) -> Slot:
    """A Line member still to be assembled — no this-turn deadline unless a deploy-now slot
    supersedes it for the same hop."""
    return Slot("line", float(value), int(deadline), key)


def answer_doom_slot(*, value: float, deadline: int = 0) -> Slot:
    """The pressure gate re-derived: the threat read (`active_doomed` / incoming) opens an answer
    slot — heal / switch / the successor — at the threat's deadline."""
    return Slot("answer_doom", float(value), int(deadline), "answer_doom")


def draw_engine_slot(*, engines_online: int) -> Slot:
    """The recurring draw need, SATURATING (the readiness leaf's term, and the engine-supporter
    premise re-derived): with an engine already online the marginal engine's value halves — kept
    over filler, but never stacking linearly."""
    value = ROLE_TIER["engine"] if engines_online <= 0 else ROLE_TIER["engine"] / 2.0
    return Slot("draw_engine", value, 0, "draw_engine")


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
