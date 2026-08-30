from dataclasses import replace

import pytest

from common.decision import (
    BudgetController,
    ComputeConfiguration,
    DecisionDeadlineExceeded,
    DecisionExecutionGuard,
    PolicyConfiguration,
    SearchConfiguration,
    correction_compute_profile,
)


def test_compute_configuration_is_a_versioned_search_and_policy_envelope():
    compute = ComputeConfiguration()
    fewer_nodes = replace(
        compute,
        search=replace(compute.search, node_budget=64),
    )
    another_tie_seed = replace(
        compute,
        policy=replace(compute.policy, tie_seed=7),
    )

    assert compute.search == SearchConfiguration()
    assert compute.policy == PolicyConfiguration()
    assert fewer_nodes.identity != compute.identity
    assert another_tie_seed.identity != compute.identity
    assert not hasattr(compute, "chain_node_cap")


def test_search_budget_supports_deterministic_node_and_wall_time_stops():
    configured = SearchConfiguration(node_budget=128, time_budget_ms=50)

    assert SearchConfiguration().time_budget_ms == 1_000
    assert configured.node_budget == 128
    assert configured.time_budget_ms == 50


def test_budget_stops_only_at_recorded_node_boundaries():
    times = iter((0.0, 0.001, 0.002, 0.003))
    budget = BudgetController(
        SearchConfiguration(node_budget=2, time_budget_ms=50),
        clock=lambda: next(times),
    )

    assert budget.visit("first")
    assert budget.visit("second")
    assert not budget.visit("third")
    assert budget.nodes == 2
    assert budget.stop_reason == "node_budget"
    assert budget.frontier == ["third"]


def test_budget_checks_elapsed_time_without_spending_a_node():
    times = iter((0.0, 0.051))
    budget = BudgetController(
        SearchConfiguration(node_budget=2, time_budget_ms=50),
        clock=lambda: next(times),
    )

    assert budget.check()
    assert budget.nodes == 0
    assert budget.stop_reason == "time_budget"


def test_correction_profile_uses_structural_bounds_without_an_inner_deadline():
    compute = correction_compute_profile()
    times = iter((0.0, 60.0, 120.0))
    budget = BudgetController(compute.search, clock=lambda: next(times))

    assert compute.profile == "correction"
    assert compute.search.time_budget_ms is None
    assert compute.search.path_node_budget == 512
    assert compute.search.node_budget == 8_192
    assert compute.search.chance_sample_budget == 12
    assert budget.visit("first")
    assert budget.visit("second")
    assert budget.stop_reason == "complete"


def test_failure_containment_raises_instead_of_returning_partial_search():
    times = iter((0.0, 114.9, 115.0))
    guard = DecisionExecutionGuard(115.0, clock=lambda: next(times))

    guard.check()
    with pytest.raises(DecisionDeadlineExceeded, match="115"):
        guard.check()


@pytest.mark.parametrize("limit", (0.0, float("nan"), float("inf")))
def test_failure_containment_requires_a_real_deadline(limit):
    with pytest.raises(ValueError, match="positive and finite"):
        DecisionExecutionGuard(limit)


def test_policy_configuration_rejects_unknown_status_names():
    with pytest.raises(ValueError, match="unknown evaluation status"):
        PolicyConfiguration(accepted_statuses=("complete", "invented"))


def test_configuration_constructors_reject_unknown_schema_versions():
    with pytest.raises(ValueError, match="search configuration schema"):
        SearchConfiguration(schema_version=99)
    with pytest.raises(ValueError, match="policy configuration schema"):
        PolicyConfiguration(schema_version=99)
    with pytest.raises(ValueError, match="compute configuration schema"):
        ComputeConfiguration(schema_version=99)
