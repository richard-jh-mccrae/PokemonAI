"""Needs — the fifth Ubiquitous Language seam: deadline-tagged slots valued in the ONE currency.

A card's keep-value is its MARGINAL slot coverage under exact assignment. Two soundness nets: the
COVERAGE LINT (every worth source maps to ≥1 slot kind — a missed slot sheds a good card, the wrong
fail direction) and the DISSOLUTION LEDGER (every gate names the slot that re-derives it).
"""
import pytest

from common import needs
from common.card_worth import ROLE_TIER, TAG_TIER, ENERGY_TIER


# ============================================================ slot primitives
@pytest.mark.req("REQ-NEEDS-0001")
def test_fund_attack_slots_carry_quota_deadlines():
    """A body missing k Energy opens k slots; unit j's deadline is j−1 turns out (1 manual attach
    per turn, rules.md §3), +1 across the board once this turn's attach is spent."""
    slots = needs.fund_attack_slots("active:112", cost_remaining=3, quota_spent=False)
    assert [s.deadline for s in slots] == [0, 1, 2]
    assert all(s.kind == "fund_attack" and s.value == ENERGY_TIER for s in slots)
    spent = needs.fund_attack_slots("active:112", cost_remaining=2, quota_spent=True)
    assert [s.deadline for s in spent] == [1, 2]
    assert needs.fund_attack_slots("active:112", cost_remaining=0, quota_spent=False) == []


@pytest.mark.req("REQ-NEEDS-0001")
def test_deploy_now_slot_is_a_this_turn_deadline():
    s = needs.deploy_now_slot("evolve:120", value=ROLE_TIER["win_condition_base"])
    assert s.kind == "deploy_now" and s.deadline == 0 and s.value == 20.0


@pytest.mark.req("REQ-NEEDS-0001")
def test_line_slots_carry_succession_for_the_wincon_class():
    """A wincon-class line opens the primary assembly slot at full tier PLUS a half-tier SUCCESSION
    slot: the plan must survive attrition, so a spare copy is never free."""
    both = needs.line_slots("line:1031", value=30.0, succession=True)
    assert [s.value for s in both] == [30.0, 15.0] and all(s.kind == "line" for s in both)
    met = needs.line_slots("line:1031", value=30.0, succession=True, primary_met=True)
    assert [s.value for s in met] == [15.0] and met[0].key.endswith(":succ")
    plain = needs.line_slots("line:1159", value=25.0)
    assert [s.value for s in plain] == [25.0]


@pytest.mark.req("REQ-NEEDS-0001")
def test_urgent_succession_is_full_tier_at_a_this_turn_deadline():
    """When MY Active is doomed and this class is its successor, the succession slot goes FULL tier
    at deadline 0: the replacement is needed imminently, not banked as half-tier insurance."""
    urgent = needs.line_slots("line:1031", value=30.0, succession=True,
                              primary_met=True, succession_urgent=True)
    assert len(urgent) == 1 and urgent[0].value == 30.0 and urgent[0].deadline == 0
    normal = needs.line_slots("line:1031", value=30.0, succession=True, primary_met=True)
    assert normal[0].value == 15.0 and normal[0].deadline == 99


@pytest.mark.req("REQ-NEEDS-0001")
def test_answer_doom_slot_from_the_threat_read():
    s = needs.answer_doom_slot(value=TAG_TIER["clutch_heal"], deadline=0)
    assert s.kind == "answer_doom" and s.deadline == 0 and s.value == 20.0


@pytest.mark.req("REQ-NEEDS-0001")
def test_supply_wincon_slot_absent_when_the_wincon_is_in_hand():
    """An ABSENT slot is zero marginal for the tutor, so no gate is needed."""
    s = needs.supply_wincon_slot(wincon_in_hand=False, target_reachable=True)
    assert s is not None and s.kind == "supply_wincon" and s.value == ROLE_TIER["tutor"]
    assert needs.supply_wincon_slot(wincon_in_hand=True, target_reachable=True) is None
    assert needs.supply_wincon_slot(wincon_in_hand=False, target_reachable=False) is None


@pytest.mark.req("REQ-NEEDS-0001")
def test_fuel_slot_is_supplied_by_pitching():
    """A discard-source accel's fuel need is FILLED BY PITCHING — the pitch side of the marginal."""
    s = needs.fuel_slot("fuel:F", value=ENERGY_TIER)
    assert s.kind == "fuel" and s.supplied_by_pitch is True


@pytest.mark.req("REQ-NEEDS-0001")
def test_general_worth_slot_floors_a_spare_role_card():
    """Role worth with no SPECIFIC need is still latent board value: a discounted general slot that
    sits BELOW a specific need and is de-duplicated per distinct card, so spare COPIES price low."""
    line = needs.Slot("line", 30.0, 99, "s")
    gen = needs.general_worth_slot("general:X", value=6.0)
    assert gen.kind == "general" and gen.value == 6.0 and "general" in needs.SLOT_KINDS
    slots, elig, resupply = [line, gen], [{0, 1}, {1}], [0.0, 0.0]   # A: line+general; B: spare
    assert needs.assignment_value(slots, elig, resupply) == 36.0     # A→line(30), B→general(6)
    assert needs.keep_v2(slots, elig, resupply, 0) == 30.0           # A's need-fill dominates
    assert needs.keep_v2(slots, elig, resupply, 1) == 6.0            # the spare's latent general worth


@pytest.mark.req("REQ-NEEDS-0001")
def test_draw_engine_slot_saturates():
    fresh = needs.draw_engine_slot(engines_online=0)
    sat = needs.draw_engine_slot(engines_online=1)
    assert fresh.kind == "draw_engine" and sat.value < fresh.value


# ============================================================ the opponent-side read (Round 3)
@pytest.mark.req("REQ-NEEDS-0002")
def test_turns_to_ready_is_the_basic_visible_lookahead():
    """Attach and evolve run in PARALLEL, so the read is the MAX of the two and never the sum.
    Visible facts only."""
    assert needs.turns_to_ready(energy_deficit=2, evolve_hops=1) == 2
    assert needs.turns_to_ready(energy_deficit=1, evolve_hops=2) == 2
    assert needs.turns_to_ready(energy_deficit=0, evolve_hops=0) == 0
    assert needs.turns_to_ready(energy_deficit=-1, evolve_hops=0) == 0    # surplus clamps


@pytest.mark.req("REQ-NEEDS-0002")
def test_deny_slot_value_grades_by_their_closeness():
    """A denial slot CONSUMES the shipped oracle's value (ADR-0062, never re-derived) and grades up
    as their body nears ready."""
    near = needs.deny_slot("deny:opp-active", oracle_value=30.0, turns_to_ready=0)
    far = needs.deny_slot("deny:opp-active", oracle_value=30.0, turns_to_ready=3)
    assert near.kind == "deny" and near.deadline == 0 and far.deadline == 3
    assert near.value == 30.0 and 0 < far.value < near.value


@pytest.mark.req("REQ-NEEDS-0010")
def test_gust_target_slot_carries_the_real_per_body_value_at_a_this_turn_deadline():
    """ADR-0076: `gust_target` is a SEPARATE instrument from `deny` — the caller's computed value
    passes through UNGRADED, always at deadline 0, with no turns-to-ready discount."""
    s = needs.gust_target_slot("gust_target:opp-bench0", value=1.9)
    assert s.kind == "gust_target" and s.deadline == 0 and s.value == 1.9
    zero = needs.gust_target_slot("gust_target:opp-bench1", value=0.0)
    assert zero.value == 0.0


@pytest.mark.req("REQ-NEEDS-0010")
def test_gust_tag_supplies_both_deny_and_gust_target_kinds():
    """`gust` names BOTH kinds it could ever fill; which one is LIVE for a decision is the Pilot's
    kill-switched call, not this module's (ADR-0076 Amendment)."""
    assert needs.SUPPLIES["gust"] == ("deny", "gust_target")
    assert set(needs.SUPPLIES["gust"]) <= needs.SLOT_KINDS


# ============================================================ the soundness nets (Round 1 ruling)
@pytest.mark.req("REQ-NEEDS-0003")
def test_coverage_lint_every_worth_source_maps_to_a_slot_kind():
    """No card class may be silently priced 0 by a missed slot — the wrong fail direction."""
    for role in ROLE_TIER:
        assert needs.SUPPLIES.get(role), f"ROLE_TIER role {role!r} maps to no slot kind"
    for tag in TAG_TIER:
        assert needs.SUPPLIES.get(tag), f"TAG_TIER tag {tag!r} maps to no slot kind"
    for src, kinds in needs.SUPPLIES.items():
        unknown = set(kinds) - needs.SLOT_KINDS
        assert not unknown, f"{src!r} names unknown slot kinds {sorted(unknown)}"


@pytest.mark.req("REQ-NEEDS-0003")
def test_dissolution_ledger_every_gate_names_its_deriving_slot():
    """Retiring a v1 gate without naming the slot kind that re-derives it is a red test by design —
    otherwise its corpus-anchored knowledge evaporates silently."""
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
    """The counterexample that refuted greedy: losing B costs 15 because A slides to S1 and S2 goes
    bare, NOT 0."""
    slots = [needs.Slot("line", 20.0, 99, "s1"), needs.Slot("line", 15.0, 99, "s2")]
    elig = [{0, 1}, {0}]                                # A: S1+S2; B: S1 only
    resupply = [0.0, 0.0]
    assert needs.assignment_value(slots, elig, resupply) == 35.0
    assert needs.keep_v2(slots, elig, resupply, 1) == 15.0      # B's marginal: re-assignment happens
    assert needs.keep_v2(slots, elig, resupply, 0) == 15.0      # A's: B covers S1, S2's 15 is lost


@pytest.mark.req("REQ-NEEDS-0004")
def test_duplicate_copies_price_marginally_and_as_a_set():
    """Sets-not-sums: each copy's SOLO marginal is 0 because the sibling covers, while the PAIR's set
    marginal is the full slot — so a forced discard-2 never reads both as free."""
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
    """A slot the deck can re-fill by its deadline at odds r loses only ×(1−r) when its held card
    leaves; a deadline-0 slot with no resupply loses full value."""
    slots = [needs.Slot("line", 20.0, 2, "s")]
    assert needs.keep_v2(slots, [{0}], [0.7], 0) == pytest.approx(20.0 * 0.3)
    spike = [needs.Slot("deploy_now", 20.0, 0, "d")]
    assert needs.keep_v2(spike, [{0}], [0.0], 0) == 20.0


@pytest.mark.req("REQ-NEEDS-0004")
def test_hedge_floors_the_marginal_at_the_intrinsic_tier():
    """A card the slot model prices at 0 keeps its intrinsic tier as a floor while migrating, and the
    floor firing is missing-slot telemetry."""
    slots = [needs.Slot("line", 20.0, 99, "s")]
    elig = [{0}, set()]
    assert needs.keep_v2(slots, elig, [0.0], 1) == 0.0
    assert needs.keep_v2(slots, elig, [0.0], 1, intrinsic=12.0) == 12.0
    assert needs.keep_v2(slots, elig, [0.0], 0, intrinsic=5.0) == 20.0   # marginal already higher


@pytest.mark.req("REQ-NEEDS-0004")
def test_option_floor_residual_prices_redundant_supply_without_double_charging_live_coverage():
    """Issue #507: two cards covering one need retain option value; a unique supplier's existing
    assignment marginal already satisfies the floor."""
    slots = [needs.Slot("line", 10.0, 0, "line")]
    assert needs.option_floor_residual(slots, [{0}], [0.0], 0, floor=4.5) == 0.0
    duplicate = [{0}, {0}]
    assert needs.option_floor_residual(slots, duplicate, [0.0], 0, floor=4.5) == 4.5
    assert needs.option_floor_residual(slots, duplicate, [0.0], 1, floor=4.5) == 4.5


@pytest.mark.req("REQ-NEEDS-0004")
def test_cheapest_removal_ties_break_by_residual_worth():
    """Among EQUAL-marginal removals the lower residual worth sheds first; raw index order never
    decides while a tiebreak discriminates."""
    slots = [needs.Slot("line", 10.0, 99, "s1"), needs.Slot("line", 8.0, 99, "s2")]
    elig = [{0}, {0}, {1}, {1}]                         # dup pair A (10), dup pair B (8)
    resupply = [0.0, 0.0]
    intrinsics = [0.0] * 4
    assert needs.cheapest_removal(slots, elig, resupply, intrinsics, 1) == [0]   # index fallback
    picks = needs.cheapest_removal(slots, elig, resupply, intrinsics, 1,
                                   tiebreak=[10.0, 10.0, 8.0, 8.0])
    assert picks == [2]                                 # the lower-worth redundancy sheds first


@pytest.mark.req("REQ-NEEDS-0004")
def test_deadness_ranks_an_exact_tie_the_index_used_to_decide():
    """A role-less spare and an EXPIRED-role card both price 0 at residual worth 0, and the equation
    is right to call them equal — so "shed the dead one" rides the ranking key (ADR-0106)."""
    slots = [needs.Slot("line", 20.0, 99, "s")]
    elig = [set(), set(), {0}]                          # spare, dead card, the line's own supplier
    resupply = [0.0]
    intrinsics = [0.0] * 3
    assert needs.cheapest_removal(slots, elig, resupply, intrinsics, 1) == [0]   # index fallback
    picks = needs.cheapest_removal(slots, elig, resupply, intrinsics, 1, deadness=[0, 1, 0])
    assert picks == [1]


@pytest.mark.req("REQ-NEEDS-0004")
def test_deadness_outranks_residual_worth_which_reads_a_corpse_as_valuable():
    """Residual worth is a CATALOG tier a dead card still carries, so worth-first sheds the live
    spare and keeps the corpse; deadness therefore sits ABOVE worth in the key."""
    elig = [set(), set()]                               # spare, spent burst — neither covers a slot
    args = ([], elig, [], [0.0, 0.0], 1)
    assert needs.cheapest_removal(*args, tiebreak=[0.0, 30.0]) == [0]            # worth alone: WRONG
    assert needs.cheapest_removal(*args, deadness=[0, 1], tiebreak=[0.0, 30.0]) == [1]


@pytest.mark.req("REQ-NEEDS-0004")
def test_deadness_is_ordering_only_and_never_beats_a_real_cost():
    """The deadness leg is consulted only where `removal_score` TIES, so no amount of it can make a
    removal look cheaper than one that genuinely costs less."""
    slots = [needs.Slot("line", 20.0, 99, "s")]
    elig = [{0}, set()]                                 # the dead card is the line's ONLY supplier
    picks = needs.cheapest_removal(slots, elig, [0.0], [0.0, 0.0], 1, deadness=[9, 0])
    assert picks == [1]                                 # the 20-point loss still outranks deadness


@pytest.mark.req("REQ-NEEDS-0004")
def test_a_fuel_card_that_also_funds_the_attack_is_not_dead_weight():
    """A fuel Energy that ALSO covers the only `fund_attack` slot nets to a TIE, so passing the whole
    pitch count into the deadness leg prices fuel twice and sheds the attack's only funder."""
    slots = [needs.fuel_slot("fuel", value=8.0), needs.Slot("fund_attack", 8.0, 0, "unit0")]
    elig = [{0, 1}, set()]                              # the Energy (fuel AND funder), a role-less spare
    resupply, intrinsics = [0.0, 0.0], [0.0, 0.0]
    worth = [8.0, 0.0]                                  # ENERGY_TIER vs a role-less spare
    assert needs.removal_score(slots, elig, resupply, intrinsics, [0]) == 0.0
    assert needs.removal_score(slots, elig, resupply, intrinsics, [1]) == 0.0    # a genuine tie
    assert needs.cheapest_removal(slots, elig, resupply, intrinsics, 1,
                                  deadness=[0, 0], tiebreak=worth) == [1]
    assert needs.cheapest_removal(slots, elig, resupply, intrinsics, 1,          # the bug: fuel in
                                  deadness=[1, 0], tiebreak=worth) == [0]        # the deadness leg


@pytest.mark.req("REQ-NEEDS-0004")
def test_fuel_slots_ride_the_pitch_side_not_the_keep_side():
    """A `supplied_by_pitch` slot never enters keep coverage: it feeds `pitch_gain`, and
    `cheapest_removal` prefers pitching it among otherwise-equal removals."""
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


# ── the DEPLOY assignment: capacity, and gain minus the marginal slot (ADR-0086, Issue #197) ──────


@pytest.mark.req("REQ-NEEDS-0010")
def test_capacity_bounds_how_many_cards_can_be_assigned_at_once():
    """The DP assigns each card to at most ONE slot, so a capacity bound is a popcount bound — an
    exact extension rather than a heuristic (Issue #197)."""
    slots = [needs.Slot("line", 20.0, 99, "s1"), needs.Slot("line", 15.0, 99, "s2")]
    elig = [{0}, {1}]                                   # A covers S1 only, B covers S2 only
    resupply = [0.0, 0.0]
    assert needs.assignment_value(slots, elig, resupply) == 35.0                    # uncapped
    assert needs.assignment_value(slots, elig, resupply, capacity=None) == 35.0     # explicit
    assert needs.assignment_value(slots, elig, resupply, capacity=2) == 35.0        # cap not binding
    assert needs.assignment_value(slots, elig, resupply, capacity=1) == 20.0        # best one only
    assert needs.assignment_value(slots, elig, resupply, capacity=0) == 0.0         # base only


@pytest.mark.req("REQ-NEEDS-0010")
def test_capacity_keeps_the_resupply_base_which_no_bench_slot_can_change():
    """`base` is what the CLOSURE re-supplies whether or not a body is deployed, so it is independent
    of Bench capacity — capping the deploys must not delete the deck's own coverage."""
    slots = [needs.Slot("line", 20.0, 99, "s1")]
    assert needs.assignment_value(slots, [{0}], [0.25], capacity=0) == pytest.approx(5.0)
    assert needs.assignment_value(slots, [{0}], [0.25], capacity=1) == pytest.approx(20.0)


@pytest.mark.req("REQ-NEEDS-0011")
def test_deploy_marginal_is_gain_minus_the_marginal_slot_cost():
    """ADR-0086 amendment E: `net(X) = gain(X) − displacement(X)`. The written form
    `V(C) − V(C, X pinned)` is ≤ 0 for every candidate, so it ranks bodies but never clears a floor."""
    slots = [needs.Slot("line", 20.0, 99, "s1"), needs.Slot("line", 15.0, 99, "s2")]
    elig = [{0}, {1}]
    resupply = [0.0, 0.0]
    assert needs.deploy_marginal(slots, elig, resupply, 0, capacity=2) == 20.0
    assert needs.deploy_marginal(slots, elig, resupply, 0, capacity=1) == pytest.approx(5.0)
    assert needs.deploy_marginal(slots, elig, resupply, 1, capacity=1) == pytest.approx(-5.0)


@pytest.mark.req("REQ-NEEDS-0011")
def test_deploy_marginal_prices_a_redundant_body_at_zero_however_free_the_bench():
    """Redundancy is a property of the board, not of scarcity: with one free slot and two
    interchangeable bodies the slot is filled either way, so this copy costs nothing at ANY capacity."""
    slots = [needs.Slot("line", 20.0, 99, "engine")]
    elig = [{0}, {0}]                                   # two interchangeable engine bodies
    resupply = [0.0]
    assert needs.deploy_marginal(slots, elig, resupply, 1, capacity=5) == 0.0
    assert needs.deploy_marginal(slots, elig, resupply, 1, capacity=1) == 0.0

    # ...and the penalty shape: the redundant body supplies nothing while the last Bench slot is
    # exactly what another line wants, so deploying it nets the full displacement.
    f51 = [needs.Slot("line", 20.0, 99, "second_line")]
    elig_f51 = [set(), {0}]                             # 2nd Solrock (supplies nothing), Makuhita
    assert needs.deploy_marginal(f51, elig_f51, [0.0], 0, capacity=1) == pytest.approx(-20.0)
    assert needs.deploy_marginal(f51, elig_f51, [0.0], 0, capacity=2) == 0.0   # room for both: free


@pytest.mark.req("REQ-NEEDS-0011")
def test_deploy_marginal_is_zero_with_no_free_slot_because_the_deploy_cannot_happen():
    """A full Bench has no counterfactual — `V(X deployed)` is unreachable — so the marginal is 0.
    Reachable from `_TO_BENCH`'s greedy multi-pick, where capacity is OUR hypothetical, not the menu's."""
    slots = [needs.Slot("line", 20.0, 99, "s1")]
    assert needs.deploy_marginal(slots, [{0}], [0.0], 0, capacity=0) == 0.0
    assert needs.deploy_marginal(slots, [{0}], [0.0], 0, capacity=1) == 20.0   # ...and one slot pays


@pytest.mark.req("REQ-NEEDS-0011")
def test_deploy_marginal_displacement_reads_the_BEST_rival_not_a_constant():
    """"Emergent, never a constant": the slot cost is whatever the displaced supplier was worth, so a
    last slot contested by a 25 is dearer than the same slot contested by a 5."""
    def net(rival_value):
        slots = [needs.Slot("line", 20.0, 99, "mine"), needs.Slot("line", rival_value, 99, "theirs")]
        return needs.deploy_marginal(slots, [{0}, {1}], [0.0, 0.0], 0, capacity=1)
    assert net(25.0) == pytest.approx(-5.0)
    assert net(5.0) == pytest.approx(15.0)


@pytest.mark.req("REQ-NEEDS-0011")
def test_supporter_tutor_supplies_a_slot_kind_so_a_bench_drop_tutor_is_not_priced_zero():
    """A Supporter tutor supplies the draw/engine need the fetched Supporter serves; absent from
    SUPPLIES, the coverage lint's promise did not hold for it."""
    assert "supporter_tutor" in needs.SUPPLIES
    assert set(needs.SUPPLIES["supporter_tutor"]) <= needs.SLOT_KINDS
    assert needs.SUPPLIES["supporter_tutor"]
