from __future__ import annotations

from common import RootDecision
from common.board_cards import body_card_ids
from common.card_worth import ACE_SPEC_TIER, ENERGY_TIER, ROLE_TIER, role_value
from common.option_equivalence import class_representatives, fan_out
from common.strategy import PrizePlan, Roles, Strategy
from common.telemetry import to_record


def test_declarative_roles_derive_a_complete_evolution_line():
    roles = Roles({12: ["win_condition", "primary_attacker"]},
                  evolves={10: 11, 11: 12}, ready={12: 2})
    strategy = Strategy(name="test", roles=roles, prize_plan=PrizePlan([[12, 12]]))
    assert roles[10] == ["win_condition_base"]
    assert strategy.lines[0].path == (10, 11, 12)
    assert strategy.lines[0].ready.energy == 2
    assert strategy.prize_plan.prizes_to_win == 6


def test_portable_worth_is_independent_of_a_legacy_value_stack():
    assert role_value(["win_condition", "engine"]) == ROLE_TIER["win_condition"]
    assert role_value([], is_typed_basic_energy=True) == ENERGY_TIER
    assert role_value(["engine"], is_ace_spec=True) == ACE_SPEC_TIER
    assert role_value([]) == 0.0


def test_board_card_walk_uses_attached_cards_not_energy_units():
    body = {"id": 10, "energies": [0, 0, 6],
            "energyCards": [{"id": 17}, {"id": 20}],
            "tools": [{"id": 1250}], "preEvolution": [{"id": 9}]}
    assert list(body_card_ids(body)) == [10, 17, 20, 1250, 9]


def test_option_equivalence_helpers_preserve_the_best_member():
    classes = {1: frozenset({1, 3}), 3: frozenset({1, 3})}
    assert class_representatives(classes, 5) == [0, 1, 2, 4]
    assert fan_out([5.0, 10.0, None, 7.0], classes) == [5.0, 10.0, None, 10.0]


def test_telemetry_exposes_only_the_bellman_decision_contract():
    decision = RootDecision((2,), None, 3.5, True, {"backend": "test"})
    record = to_record(decision)
    assert record == {
        "bellman": True, "chosen": [2], "action": None, "value": 3.5,
        "complete": True, "diagnostics": {"backend": "test"}, "belief": None,
    }
