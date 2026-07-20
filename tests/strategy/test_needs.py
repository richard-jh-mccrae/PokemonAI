"""Needs — the fifth Ubiquitous Language seam (keep-value v2 grill, ruled 2026-07-19).

WHAT the position requires: deadline-tagged slots derived from board state, valued in the ONE
currency. A card's keep-value (WP-N2) will be its MARGINAL slot coverage under exact assignment;
this module (WP-N1) owns the slot vocabulary, the derivation primitives, the card→slot SUPPLIES
mapping, and the two soundness nets the grill ruled: the COVERAGE LINT (every worth source maps to
≥1 slot kind — a missed slot sheds a good card, the wrong fail direction) and the DISSOLUTION
LEDGER (every gate names the slot that re-derives it).
"""
import pytest

from common import needs
from common.card_worth import ROLE_TIER, TAG_TIER, ENERGY_TIER


# ============================================================ slot primitives
@pytest.mark.req("REQ-NEEDS-0001")
def test_fund_attack_slots_carry_quota_deadlines():
    """A body missing k Energy opens k fund-attack slots; unit j's deadline is j−1 turns out
    (1 manual attach/turn, rules.md §3), +1 across the board when this turn's attach is spent —
    the quota gate re-derived as slot structure."""
    slots = needs.fund_attack_slots("active:112", cost_remaining=3, quota_spent=False)
    assert [s.deadline for s in slots] == [0, 1, 2]
    assert all(s.kind == "fund_attack" and s.value == ENERGY_TIER for s in slots)
    spent = needs.fund_attack_slots("active:112", cost_remaining=2, quota_spent=True)
    assert [s.deadline for s in spent] == [1, 2]
    assert needs.fund_attack_slots("active:112", cost_remaining=0, quota_spent=False) == []


@pytest.mark.req("REQ-NEEDS-0001")
def test_deploy_now_slot_is_a_this_turn_deadline():
    """The deploy-now spike re-derived: an eligible evolution play is a slot with deadline 0 at the
    evolution's own tier."""
    s = needs.deploy_now_slot("evolve:120", value=ROLE_TIER["win_condition_base"])
    assert s.kind == "deploy_now" and s.deadline == 0 and s.value == 20.0


@pytest.mark.req("REQ-NEEDS-0001")
def test_answer_doom_slot_from_the_threat_read():
    """The pressure gate re-derived: a doomed Active opens an answer slot (heal/switch/successor)
    with the threat's deadline."""
    s = needs.answer_doom_slot(value=TAG_TIER["clutch_heal"], deadline=0)
    assert s.kind == "answer_doom" and s.deadline == 0 and s.value == 20.0


@pytest.mark.req("REQ-NEEDS-0001")
def test_supply_wincon_slot_absent_when_the_wincon_is_in_hand():
    """The need-met gate re-derived: the tutor's slot exists only while the wincon is NOT in hand
    (and something remains to fetch). Absent slot = zero marginal for the tutor, no gate needed."""
    s = needs.supply_wincon_slot(wincon_in_hand=False, target_reachable=True)
    assert s is not None and s.kind == "supply_wincon" and s.value == ROLE_TIER["tutor"]
    assert needs.supply_wincon_slot(wincon_in_hand=True, target_reachable=True) is None
    assert needs.supply_wincon_slot(wincon_in_hand=False, target_reachable=False) is None


@pytest.mark.req("REQ-NEEDS-0001")
def test_fuel_slot_is_supplied_by_pitching():
    """The zone sign re-derived: a discard-source accel's fuel need is a slot FILLED BY PITCHING —
    the pitch side of the marginal, not a keep."""
    s = needs.fuel_slot("fuel:F", value=ENERGY_TIER)
    assert s.kind == "fuel" and s.supplied_by_pitch is True


@pytest.mark.req("REQ-NEEDS-0001")
def test_draw_engine_slot_saturates():
    """The engine-supporter premise re-derived: one recurring draw-engine slot; with an engine
    already in play/hand the slot's value drops (saturation — the readiness leaf's term)."""
    fresh = needs.draw_engine_slot(engines_online=0)
    sat = needs.draw_engine_slot(engines_online=1)
    assert fresh.kind == "draw_engine" and sat.value < fresh.value


# ============================================================ the opponent-side read (Round 3)
@pytest.mark.req("REQ-NEEDS-0002")
def test_turns_to_ready_is_the_basic_visible_lookahead():
    """The ruled opponent read: turns until an in-play body is fully energized (deficit at the
    attach quota) AND evolved (forward hops, one per turn) — attach and evolve run in PARALLEL, so
    the read is the max, never the sum. Visible facts only."""
    assert needs.turns_to_ready(energy_deficit=2, evolve_hops=1) == 2
    assert needs.turns_to_ready(energy_deficit=1, evolve_hops=2) == 2
    assert needs.turns_to_ready(energy_deficit=0, evolve_hops=0) == 0
    assert needs.turns_to_ready(energy_deficit=-1, evolve_hops=0) == 0    # surplus clamps


@pytest.mark.req("REQ-NEEDS-0002")
def test_deny_slot_value_grades_by_their_closeness():
    """The Hammer ruling (86091435-68) with TIMING: a denial slot consumes the shipped oracle's
    value (ADR-0062 — never re-derived) and grades UP as their body nears ready — deadline = their
    turns-to-ready, value scaled toward full as the deadline closes."""
    near = needs.deny_slot("deny:opp-active", oracle_value=30.0, turns_to_ready=0)
    far = needs.deny_slot("deny:opp-active", oracle_value=30.0, turns_to_ready=3)
    assert near.kind == "deny" and near.deadline == 0 and far.deadline == 3
    assert near.value == 30.0 and 0 < far.value < near.value


# ============================================================ the soundness nets (Round 1 ruling)
@pytest.mark.req("REQ-NEEDS-0003")
def test_coverage_lint_every_worth_source_maps_to_a_slot_kind():
    """The COVERAGE LINT: every ROLE_TIER role and TAG_TIER tag names ≥1 slot kind it can supply
    (`needs.SUPPLIES`), and every named kind is a real slot kind — so no card class can be silently
    priced 0 by a missed slot (the wrong fail direction). The `test_role_coverage` pattern, one
    level up."""
    for role in ROLE_TIER:
        assert needs.SUPPLIES.get(role), f"ROLE_TIER role {role!r} maps to no slot kind"
    for tag in TAG_TIER:
        assert needs.SUPPLIES.get(tag), f"TAG_TIER tag {tag!r} maps to no slot kind"
    for src, kinds in needs.SUPPLIES.items():
        unknown = set(kinds) - needs.SLOT_KINDS
        assert not unknown, f"{src!r} names unknown slot kinds {sorted(unknown)}"


@pytest.mark.req("REQ-NEEDS-0003")
def test_dissolution_ledger_every_gate_names_its_deriving_slot():
    """The DISSOLUTION LEDGER: every shipped gate/flag of the v1 equation names the slot kind that
    re-derives it — so no gate's corpus-anchored knowledge can silently evaporate in the migration.
    Retiring a gate without a deriving slot is a red test, by design."""
    expected_gates = {
        "evolution_gate", "fetcher_gate", "need_met_gate", "pressure_gate", "quota_gate",
        "deploy_now_spike", "spent_burst", "engine_supporter_floor", "fuel_sign",
    }
    assert set(needs.DISSOLUTION_LEDGER) == expected_gates
    for gate, kind in needs.DISSOLUTION_LEDGER.items():
        assert kind in needs.SLOT_KINDS, f"gate {gate!r} names unknown slot kind {kind!r}"
