from __future__ import annotations

from dataclasses import replace
import pytest

from common.cards import card_clauses, card_store
from common.cards.card_facts import Clause
from common.ledger.activation import ActivationCompiler, ActivationEnvironment
from common.ledger import EvaluationModel
from common.ledger.coverage import (
    CLAUSE_PARAMETER_CONTRACTS, CLAUSE_VALUATION_CONTRACTS, ClauseValuationMode,
    clause_parameter_mode, placed_clauses,
)
from common.ledger.capabilities import (
    body_capability, card_option_units, clause_cost_units, clause_value_units,
)
from common.ledger.features import FEATURE_CATALOG
from common.ledger.sensitivity import (
    OBSERVATION_SENSITIVITY_WITNESSES, PARAMETER_SENSITIVITY_WITNESSES,
    SENSITIVITY_WITNESSES,
    _body_for_facts, _rich_board, card_clause_contribution, card_probe_contribution,
    run_clause_sensitivity,
    run_observation_sensitivity, run_parameter_sensitivity,
    run_sensitivity_witness,
)
from common.observation.nodes import Card
from common.observation.state import AttackEvent


def test_every_active_feature_has_a_generated_sensitivity_witness():
    assert set(SENSITIVITY_WITNESSES) == {
        f"feature:{key}" for key in FEATURE_CATALOG.priced_keys
    }


def test_every_clause_names_a_generated_sensitivity_witness():
    assert {contract.witness for contract in CLAUSE_VALUATION_CONTRACTS.values()} == {
        f"clause:{kind}" for kind in CLAUSE_VALUATION_CONTRACTS}


def test_every_direct_parameter_has_an_executable_sensitivity_witness():
    assert {witness.parameter for witness in PARAMETER_SENSITIVITY_WITNESSES.values()} == {
        parameter for parameter, mode in CLAUSE_PARAMETER_CONTRACTS.items()
        if mode is ClauseValuationMode.DIRECT_EQUATION
    }
    expected = sum(
        clause_parameter_mode(parameter, value, placement, clause.kind)
        is ClauseValuationMode.DIRECT_EQUATION
        for facts in card_store().values()
        for placement, clause in placed_clauses(facts)
        for parameter, value in clause.params.items())
    assert len(PARAMETER_SENSITIVITY_WITNESSES) == expected
    assert all(witness.expected_feature in FEATURE_CATALOG
               and witness.expected_direction in {-1, 1}
               for witness in PARAMETER_SENSITIVITY_WITNESSES.values())


@pytest.mark.parametrize("witness", PARAMETER_SENSITIVITY_WITNESSES.values(),
                         ids=PARAMETER_SENSITIVITY_WITNESSES)
def test_direct_parameter_witness_changes_valuation(witness):
    result = run_parameter_sensitivity(witness, EvaluationModel.build())

    assert result.passed, result.reason
    if witness.expected_feature is not None:
        assert result.feature_delta * witness.expected_direction > 0


def test_parameter_sensitivity_rejects_a_reversed_direction_contract():
    witness = next(
        row for row in PARAMETER_SENSITIVITY_WITNESSES.values()
        if row.parameter == "distinct_types")

    result = run_parameter_sensitivity(
        replace(witness, expected_direction=-witness.expected_direction),
        EvaluationModel.build())

    assert not result.passed
    assert result.reason == (
        "clause.parameter.distinct_types moved positive; expected negative")


@pytest.mark.parametrize("contract", CLAUSE_VALUATION_CONTRACTS.values(),
                         ids=CLAUSE_VALUATION_CONTRACTS)
def test_each_clause_has_an_executable_nonzero_direct_or_successor_witness(contract):
    result = run_clause_sensitivity(contract, EvaluationModel.build())

    assert result.passed, result.reason


@pytest.mark.parametrize("witness", SENSITIVITY_WITNESSES.values(),
                         ids=SENSITIVITY_WITNESSES)
def test_each_seeded_feature_has_a_nonzero_causal_activation(witness):
    result = run_sensitivity_witness(witness, EvaluationModel.build())

    assert result.passed, result.reason


def test_sensitivity_positive_control_detects_a_zeroed_coefficient():
    witness = SENSITIVITY_WITNESSES["feature:kind.pokemon"]
    general = EvaluationModel.build().configuration
    context = EvaluationModel.build(
        configuration=general.with_values({"kind.pokemon": 0.0}))

    result = run_sensitivity_witness(witness, context)

    assert not result.passed
    assert result.reason == "zero contribution"


@pytest.mark.parametrize("identity,witness", OBSERVATION_SENSITIVITY_WITNESSES.items(),
                         ids=OBSERVATION_SENSITIVITY_WITNESSES)
def test_each_observation_field_has_an_explicit_zero_or_nonzero_expectation(
        identity, witness):
    result = run_observation_sensitivity(
        identity, witness.features, EvaluationModel.build(),
        expected_nonzero=witness.expected_nonzero)

    assert result.passed, (identity, witness)


def test_every_known_card_has_a_nonzero_reachable_zone_probe():
    context = EvaluationModel.build()

    missing = [card_id for card_id in card_store()
               if card_probe_contribution(card_id, context) == 0.0]

    assert missing == []


def test_every_card_clause_has_its_own_nonzero_reachable_probe():
    context = EvaluationModel.build()
    missing = [
        f"{card_id}:{kind}"
        for card_id, facts in card_store().items()
        for kind in sorted({clause.kind for clause in card_clauses(facts)})
        if card_clause_contribution(card_id, kind, context) == 0.0
    ]

    assert missing == []


def test_clause_amount_changes_the_runtime_activation_magnitude():
    context = EvaluationModel.build()

    ten_damage = card_clause_contribution(317, "recoil", context)
    seventy_damage = card_clause_contribution(674, "recoil", context)

    assert seventy_damage == pytest.approx(7 * ten_damage)


def test_clause_condition_uses_the_observed_body_position():
    context = EvaluationModel.build()
    board = _rich_board()
    facts = context.facts(56)
    clause = next(clause for clause in card_clauses(facts)
                  if clause.kind == "ability_suppression")
    flutter = _body_for_facts(board.me.active, facts)
    active_side = replace(board.me, active=flutter)
    bench_side = replace(board.me, bench=(flutter, *board.me.bench[1:]))

    active = clause_value_units(
        clause, facts, active_side, board.them,
        replace(board, me=active_side), context, body=flutter)
    benched = clause_value_units(
        clause, facts, bench_side, board.them,
        replace(board, me=bench_side), context, body=flutter)

    assert active == 1.0
    assert benched == 0.0


def test_own_bench_damage_has_negative_target_activation():
    context = EvaluationModel.build()
    board = _rich_board()
    clause = Clause("bench_spread", amount=20, target="own_bench")
    units = clause_value_units(
        clause, context.facts(934), board.me, board.them, board, context,
        body=board.me.active)
    activations = ActivationCompiler().compile(
        "function", (clause.kind,), ActivationEnvironment(
            scale=units, board=board, evaluation_model=context, side=board.me,
            opponent=board.them, facts=context.facts(934), clause=clause,
            body=board.me.active))

    target = next(row for row in activations
                  if row.feature == "function.bench_pressure.target_count")
    assert target.value < 0


def test_ultra_ball_clause_prices_two_discard_costs():
    context = EvaluationModel.build()
    board = _rich_board()

    clause = next(clause for clause in context.facts(1121).clauses
                  if clause.kind == "fetch")

    assert clause_cost_units(clause, board.me) == 2.0


def test_ultra_ball_discard_cost_reduces_its_card_option_value():
    context = EvaluationModel.build()
    board = _rich_board()
    facts = context.facts(1121)
    costless = replace(
        facts, clauses=tuple(Clause(
            clause.kind, **{key: value for key, value in clause.params.items()
                            if key != "cost"}) for clause in facts.clauses))

    costed_units = card_option_units(
        facts, board.me, board.them, board, context)
    costless_units = card_option_units(
        costless, board.me, board.them, board, context)

    assert costed_units.cost == costless_units.cost + 2.0
    assert costed_units.total == costless_units.total - 2.0


def test_own_bench_damage_is_not_counted_as_opponent_attack_reach():
    context = EvaluationModel.build()
    board = _rich_board()
    facts = context.facts(934)
    active = _body_for_facts(board.me.active, facts)
    side = replace(board.me, active=active)

    capability = body_capability(
        active, side, board.them, replace(board, me=side), context)

    assert capability.bench_reach == 0.0


def test_opp_any_damage_counters_value_an_active_only_target():
    context = EvaluationModel.build()
    board = _rich_board()
    opponent = replace(board.them, bench=())
    facts = context.facts(133)
    clause = next(clause for clause in card_clauses(facts)
                  if clause.kind == "damage_counters")
    units = clause_value_units(
        clause, facts, board.me, opponent, replace(board, them=opponent), context,
        body=board.me.active)
    activations = ActivationCompiler().compile(
        "function", (clause.kind,), ActivationEnvironment(
            scale=units, board=replace(board, them=opponent),
            evaluation_model=context, side=board.me, opponent=opponent,
            facts=facts, clause=clause, body=board.me.active))

    target = next(row for row in activations
                  if row.feature == "function.bench_pressure.target_count")
    assert target.value > 0.0


def test_attack_to_hand_size_uses_the_unchanged_hand_count():
    context = EvaluationModel.build()
    board = _rich_board()
    side = replace(board.me, hand_count=3)
    facts = context.facts(381)
    clause = next(clause for attack in facts.attacks for clause in attack.clauses
                  if clause.kind == "draw")

    units = clause_value_units(
        clause, facts, side, board.them, replace(board, me=side), context,
        body=side.active)

    assert units == 3.0


def test_optional_attack_cost_changes_the_selected_attack_equation():
    context = EvaluationModel.build()
    board = _rich_board()
    facts = context.facts(108)
    active = _body_for_facts(board.me.active, facts)
    side = replace(board.me, active=active)
    costless = replace(facts, attacks=tuple(replace(
        attack, clauses=tuple(Clause(
            clause.kind, **{key: value for key, value in clause.params.items()
                            if key != "cost"}) for clause in attack.clauses))
        for attack in facts.attacks))
    costless_context = replace(context, store={**context.store, 108: costless})

    costed = body_capability(active, side, board.them, replace(board, me=side), context)
    free = body_capability(
        active, side, board.them, replace(board, me=side), costless_context)

    assert costed != free


def test_multi_target_attack_count_changes_total_attack_impact():
    context = EvaluationModel.build()
    board = _rich_board()
    facts = context.facts(144)
    active = _body_for_facts(board.me.active, facts)
    side = replace(
        board.me, active=active, asleep=False, paralyzed=False, confused=False)
    single = replace(facts, attacks=tuple(replace(
        attack, clauses=tuple(Clause(
            clause.kind, **({**clause.params, "count": 1}
                            if clause.kind == "bench_snipe" else clause.params))
                              for clause in attack.clauses))
        for attack in facts.attacks))
    single_context = replace(context, store={**context.store, 144: single})

    triple_value = body_capability(
        active, side, board.them, replace(board, me=side), context)
    single_value = body_capability(
        active, side, board.them, replace(board, me=side), single_context)

    assert triple_value.attack_now > single_value.attack_now


def test_opponent_draw_amount_is_an_independent_option_cost():
    context = EvaluationModel.build()
    board = _rich_board()
    facts = context.facts(1213)
    one_sided = replace(facts, clauses=tuple(Clause(
        clause.kind, **{key: value for key, value in clause.params.items()
                        if key not in {"opponent_amount", "opponent_amount_if"}})
        for clause in facts.clauses))

    symmetric = card_option_units(facts, board.me, board.them, board, context)
    own_only = card_option_units(one_sided, board.me, board.them, board, context)

    assert symmetric.cost == own_only.cost + 4.0
    assert symmetric.total == own_only.total - 4.0


def test_moved_to_active_requires_a_move_or_retreat_not_appearance():
    context = EvaluationModel.build()
    board = _rich_board()
    active = replace(board.me.active, appeared_this_turn=True)
    side = replace(board.me, active=active)
    clause = Clause("damage_boost", amount=20, condition="moved_to_active_this_turn")

    appeared = clause_value_units(
        clause, context.facts(active.card.card_id), side, board.them,
        replace(board, me=side), context, body=active)
    retreated_board = replace(board, me=side, turn=replace(board.turn, retreated=True))
    moved = clause_value_units(
        clause, context.facts(active.card.card_id), side, board.them,
        retreated_board, context, body=active)

    assert appeared == 0.0
    assert moved > 0.0


def test_ancient_attack_condition_checks_card_family_and_player():
    context = EvaluationModel.build()
    board = _rich_board()
    body = _body_for_facts(board.me.active, context.facts(226))
    side = replace(board.me, active=body)
    clause = Clause(
        "damage_boost", amount=150, condition="other_ancient_attacked_last_turn")

    wrong = replace(board, me=side, events=(AttackEvent(
        15, (("cardId", 119), ("playerIndex", board.seat)), True),))
    correct = replace(board, me=side, events=(AttackEvent(
        15, (("cardId", 62), ("playerIndex", board.seat)), True),))

    assert clause_value_units(
        clause, context.facts(226), side, board.them, wrong, context, body=body) == 0.0
    assert clause_value_units(
        clause, context.facts(226), side, board.them, correct, context, body=body) > 0.0


def test_team_rocket_energy_condition_does_not_accept_arbitrary_special_energy():
    context = EvaluationModel.build()
    board = _rich_board()
    clause = Clause(
        "damage_boost", amount=20, condition="team_rocket_energy_attached")
    ordinary = replace(
        board.me.active, energy_cards=(Card(17, 8800, board.seat),))
    rocket = replace(
        board.me.active, energy_cards=(Card(15, 8801, board.seat),))

    assert clause_value_units(
        clause, context.facts(ordinary.card.card_id),
        replace(board.me, active=ordinary), board.them, board, context,
        body=ordinary) == 0.0
    assert clause_value_units(
        clause, context.facts(rocket.card.card_id),
        replace(board.me, active=rocket), board.them, board, context,
        body=rocket) > 0.0
