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
def test_line_slots_carry_succession_for_the_wincon_class():
    """"Copy 2's marginal = its next-best slot" (the grill spec): a wincon-class line opens the
    primary assembly slot at full tier PLUS a half-tier SUCCESSION slot — the plan must survive
    attrition, so a spare copy is never free. An in-play copy MEETS the primary (the in_play gate
    as slot absence) but the succession need stands; a non-wincon class gets the primary only."""
    both = needs.line_slots("line:1031", value=30.0, succession=True)
    assert [s.value for s in both] == [30.0, 15.0] and all(s.kind == "line" for s in both)
    met = needs.line_slots("line:1031", value=30.0, succession=True, primary_met=True)
    assert [s.value for s in met] == [15.0] and met[0].key.endswith(":succ")
    plain = needs.line_slots("line:1159", value=25.0)
    assert [s.value for s in plain] == [25.0]


@pytest.mark.req("REQ-NEEDS-0001")
def test_urgent_succession_is_full_tier_at_a_this_turn_deadline():
    """The answer-doom ruling (2026-07-20): when MY Active is doomed and this class is the
    successor with its base in play, the succession slot goes FULL tier at deadline 0 (the old
    answer-doom successor spike, re-derived as the line's own worth) instead of the half-tier
    no-deadline insurance — a doomed wincon's replacement is needed imminently, not banked."""
    urgent = needs.line_slots("line:1031", value=30.0, succession=True,
                              primary_met=True, succession_urgent=True)
    assert len(urgent) == 1 and urgent[0].value == 30.0 and urgent[0].deadline == 0
    normal = needs.line_slots("line:1031", value=30.0, succession=True, primary_met=True)
    assert normal[0].value == 15.0 and normal[0].deadline == 99


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
def test_general_worth_slot_floors_a_spare_role_card():
    """WP-N5 (the general-worth floor the refresh-SHED sweep proved missing): a held card with role
    worth but no SPECIFIC need still carries LATENT board value — a discounted general slot that
    sits BELOW a specific need (a need-filler assigns to its need first) and is de-duplicated (one
    per distinct card, so spare COPIES price marginally — sets-not-sums)."""
    line = needs.Slot("line", 30.0, 99, "s")
    gen = needs.general_worth_slot("general:X", value=6.0)
    assert gen.kind == "general" and gen.value == 6.0 and "general" in needs.SLOT_KINDS
    slots, elig, resupply = [line, gen], [{0, 1}, {1}], [0.0, 0.0]   # A: line+general; B: spare
    assert needs.assignment_value(slots, elig, resupply) == 36.0     # A→line(30), B→general(6)
    assert needs.keep_v2(slots, elig, resupply, 0) == 30.0           # A's need-fill dominates
    assert needs.keep_v2(slots, elig, resupply, 1) == 6.0            # the spare's latent general worth


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


@pytest.mark.req("REQ-NEEDS-0010")
def test_gust_target_slot_carries_the_real_per_body_value_at_a_this_turn_deadline():
    """ADR-0074: `gust_target` is a SEPARATE instrument from `deny` — its value is whatever the
    caller computed via the two-term `opponent_target_value` marginal (not a flat disruption tier),
    and it always carries deadline 0 (no ruled timing discount for this instrument, unlike deny's
    turns-to-ready halving) — an un-graded value passes through unchanged."""
    s = needs.gust_target_slot("gust_target:opp-bench0", value=1.9)
    assert s.kind == "gust_target" and s.deadline == 0 and s.value == 1.9
    zero = needs.gust_target_slot("gust_target:opp-bench1", value=0.0)
    assert zero.value == 0.0


@pytest.mark.req("REQ-NEEDS-0010")
def test_gust_tag_supplies_both_deny_and_gust_target_kinds():
    """The SUPPLIES schema change (ADR-0074 Amendment): `gust` names BOTH kinds it could ever fill —
    which one is actually LIVE for a decision is the Pilot's kill-switched call, not this module's;
    the coverage lint only needs ≥1 real kind, and this asserts both are present and real."""
    assert needs.SUPPLIES["gust"] == ("deny", "gust_target")
    assert set(needs.SUPPLIES["gust"]) <= needs.SLOT_KINDS


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


# ============================================================ WP-N2: exact assignment + marginals
@pytest.mark.req("REQ-NEEDS-0004")
def test_marginal_is_counterfactual_with_reassignment():
    """The Round-2 counterexample that refuted greedy: card A supplies S1(20) and S2(15), card B
    supplies only S1. Exact assignment covers both (V=35); the marginals re-assign — losing B costs
    15 (A slides to S1, S2 goes bare), NOT 0."""
    slots = [needs.Slot("line", 20.0, 99, "s1"), needs.Slot("line", 15.0, 99, "s2")]
    elig = [{0, 1}, {0}]                                # A: S1+S2; B: S1 only
    resupply = [0.0, 0.0]
    assert needs.assignment_value(slots, elig, resupply) == 35.0
    assert needs.keep_v2(slots, elig, resupply, 1) == 15.0      # B's marginal: re-assignment happens
    assert needs.keep_v2(slots, elig, resupply, 0) == 15.0      # A's: B covers S1, S2's 15 is lost


@pytest.mark.req("REQ-NEEDS-0004")
def test_duplicate_copies_price_marginally_and_as_a_set():
    """Sets-not-sums, natively: two identical wincons, one line slot (20). Each copy's SOLO marginal
    is 0 (the sibling covers); the PAIR's set marginal is the full 20 — so a forced discard-2 never
    reads both as free. The duplicate-wincon naivety dies here."""
    slots = [needs.Slot("line", 20.0, 99, "s1")]
    elig = [{0}, {0}, set()]                            # wincon, wincon, dreg
    resupply = [0.0]
    assert needs.keep_v2(slots, elig, resupply, 0) == 0.0
    assert needs.keep_v2(slots, elig, resupply, 1) == 0.0
    assert needs.set_keep_v2(slots, elig, resupply, {0, 1}) == 20.0
    assert needs.set_keep_v2(slots, elig, resupply, {0, 2}) == 0.0
    # the discard decider's objective: the cheapest 2-removal pitches ONE wincon + the dreg
    picks = needs.cheapest_removal(slots, elig, resupply, [0.0, 0.0, 0.0], 2)
    assert 2 in picks and len(picks) == 2 and picks != [0, 1]


@pytest.mark.req("REQ-NEEDS-0004")
def test_resupply_discounts_the_uncovered_loss():
    """The Closure re-enters as slot RESUPPLY: a slot the deck can re-fill by its deadline at odds r
    only loses value ×(1−r) when its held card leaves — the old re-access discount, derived. A
    deadline-0 slot with no resupply (deploy-now) loses full value — the spike, derived."""
    slots = [needs.Slot("line", 20.0, 2, "s")]
    assert needs.keep_v2(slots, [{0}], [0.7], 0) == pytest.approx(20.0 * 0.3)
    spike = [needs.Slot("deploy_now", 20.0, 0, "d")]
    assert needs.keep_v2(spike, [{0}], [0.0], 0) == 20.0


@pytest.mark.req("REQ-NEEDS-0004")
def test_hedge_floors_the_marginal_at_the_intrinsic_tier():
    """The Round-1 transitional hedge (discretionary per the dev-window ruling): a card the slot
    model prices at 0 keeps its intrinsic tier as a floor while migrating; the floor's firing is
    missing-slot telemetry."""
    slots = [needs.Slot("line", 20.0, 99, "s")]
    elig = [{0}, set()]
    assert needs.keep_v2(slots, elig, [0.0], 1) == 0.0
    assert needs.keep_v2(slots, elig, [0.0], 1, intrinsic=12.0) == 12.0
    assert needs.keep_v2(slots, elig, [0.0], 0, intrinsic=5.0) == 20.0   # marginal already higher


@pytest.mark.req("REQ-NEEDS-0004")
def test_cheapest_removal_ties_break_by_residual_worth():
    """The 83967840-54 corpus ruling, re-derived (v1's worth tie-break): among EQUAL-marginal
    removals the lower Σ tiebreak (residual worth) sheds first — a worth-10 redundancy is worth
    preserving over a worth-8 one; raw index order never decides while a tiebreak discriminates."""
    slots = [needs.Slot("line", 10.0, 99, "s1"), needs.Slot("line", 8.0, 99, "s2")]
    elig = [{0}, {0}, {1}, {1}]                         # dup pair A (10), dup pair B (8)
    resupply = [0.0, 0.0]
    intrinsics = [0.0] * 4
    assert needs.cheapest_removal(slots, elig, resupply, intrinsics, 1) == [0]   # index fallback
    picks = needs.cheapest_removal(slots, elig, resupply, intrinsics, 1,
                                   tiebreak=[10.0, 10.0, 8.0, 8.0])
    assert picks == [2]                                 # the lower-worth redundancy sheds first


@pytest.mark.req("REQ-NEEDS-0004")
def test_fuel_slots_ride_the_pitch_side_not_the_keep_side():
    """A supplied_by_pitch slot never enters keep coverage; it feeds `pitch_gain` (pitching the
    matching card is progress) and `cheapest_removal` prefers pitching the fuel card among
    otherwise-equal removals."""
    fuel = needs.fuel_slot("fuel:F", value=8.0)
    line = needs.Slot("line", 20.0, 99, "s")
    slots = [line, fuel]
    elig = [{0}, {1}, set()]                            # wincon->line, energy->fuel, dreg
    resupply = [0.0, 0.0]
    assert needs.assignment_value(slots, elig, resupply) == 20.0         # fuel excluded from keep V
    assert needs.pitch_gain(slots, elig, 1) == 8.0
    assert needs.pitch_gain(slots, elig, 0) == 0.0
    picks = needs.cheapest_removal(slots, elig, resupply, [0.0, 0.0, 0.0], 1)
    assert picks == [1]                                 # the fuel energy out-pitches even the dreg
