from common.decision import EvaluationRequest, EvaluationStatus
from common.ledger import EvaluationModel
from common.ledger.decision import LEDGER_VALUE_SCALE, LedgerValueEvaluator
from common.observation import ObservationStateBuilder
from ledger_helpers import DARK_E, DRAGAPULT, body, player, printout


def test_ledger_evaluator_exposes_total_and_every_linear_component():
    board = ObservationStateBuilder((DRAGAPULT, DARK_E) * 30).root(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[DARK_E])))
    model = EvaluationModel.build()

    valuation = LedgerValueEvaluator().evaluate(EvaluationRequest(board, model))

    assert valuation.state_key == board.position_key
    assert valuation.cache_key == board.valuation_key
    assert valuation.scale == LEDGER_VALUE_SCALE
    assert valuation.status is EvaluationStatus.ESTIMATED
    assert valuation.gaps
    assert valuation.total == sum(component.value for component in valuation.components)
    assert all(component.value == component.activation * component.coefficient
               for component in valuation.components)


def test_delta_hint_never_changes_exact_ledger_valuation():
    builder = ObservationStateBuilder((DRAGAPULT, DARK_E) * 30)
    parent = builder.root(printout(me=player(active=body(DRAGAPULT, 1), hand=[DARK_E])))
    child, delta = builder.advance(parent, printout(
        me=player(active=body(DRAGAPULT, 1, energies=(8,)), hand=[])))
    evaluator = LedgerValueEvaluator()
    model = EvaluationModel.build()
    parent_value, parent_state = evaluator.evaluate_with_state(
        EvaluationRequest(parent, model))

    hinted, hinted_state = evaluator.evaluate_with_state(
        EvaluationRequest(child, model, parent_value, delta), parent_state)
    assert hinted_state.reused_groups == ("context",)
    full = evaluator.evaluate(EvaluationRequest(child, model))

    assert hinted == full
