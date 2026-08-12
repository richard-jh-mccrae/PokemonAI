from __future__ import annotations

import pytest

from common.bellman import ValueRegistry
from common.strategy import Line, PrizePlan, Roles, Strategy


BASE, MIDDLE, PAYOFF, WALL, SECONDARY_BASE, SECONDARY = 10, 11, 12, 20, 30, 31


def test_roles_normalize_evolution_relationships_into_the_legacy_line_view():
    roles = Roles(
        {PAYOFF: ["win_condition", "primary_attacker"], WALL: ["accel_source"]},
        evolves={BASE: MIDDLE, MIDDLE: PAYOFF}, ready={PAYOFF: 2})
    strategy = Strategy(roles=roles)

    assert roles[BASE] == ["win_condition_base"]
    assert len(strategy.lines) == 1
    line = strategy.lines[0]
    assert line.path == [BASE, MIDDLE, PAYOFF]
    assert line.payoff == PAYOFF
    assert line.role == "win_condition"
    assert line.ready.energy == 2


def test_roles_reject_ambiguous_duplicate_line_declarations():
    roles = Roles({PAYOFF: ["win_condition"]}, evolves={BASE: PAYOFF})
    with pytest.raises(ValueError, match="not both"):
        Strategy(roles=roles, lines=[Line([BASE, PAYOFF], PAYOFF)])


def test_roles_derive_secondary_lines_without_mislabeling_their_base_as_a_win_condition():
    roles = Roles({SECONDARY: ["secondary_attacker"]},
                  evolves={SECONDARY_BASE: SECONDARY})
    strategy = Strategy(roles=roles)

    assert roles[SECONDARY_BASE] == ["evolution_base"]
    assert strategy.lines[0].role == "secondary_attacker"
    registry = ValueRegistry.from_strategy(
        strategy=strategy, stats=None, functions=None, deck=(SECONDARY_BASE, SECONDARY))
    assert "win_condition_base" not in registry.roles[SECONDARY_BASE]


def test_prize_plan_normalizes_routes_and_rejects_empty_declarations():
    plan = PrizePlan(routes=[[WALL, PAYOFF, PAYOFF]])
    assert plan.routes == ((WALL, PAYOFF, PAYOFF),)
    assert plan.prizes_to_win == 6
    with pytest.raises(ValueError, match="non-empty"):
        PrizePlan(routes=[])
