from __future__ import annotations

from common.decision import (
    EvaluationStatus,
    StateValuation,
    ValueComponent,
    ValueScale,
)

from .evaluate import (FeatureActivation, FeatureContribution, Valuation, evaluate)


LEDGER_VALUE_SCALE = ValueScale("ledger-worth", 1)


class LedgerValueEvaluator:
    identity = "ledger-linear-v1"

    def evaluate(self, request) -> StateValuation:
        board = getattr(request.state, "observation", request.state)
        valuation = evaluate(board, request.evaluation_model)
        return state_valuation_from_ledger(board, valuation)


def value_components(contributions) -> tuple[ValueComponent, ...]:
    return tuple(ValueComponent(
        item.feature, item.activation, item.coefficient, item.value,
        item.provenance) for item in contributions)


def state_valuation_from_ledger(board, valuation: Valuation,
                                evaluator_identity=LedgerValueEvaluator.identity) -> StateValuation:
    status = (EvaluationStatus.ESTIMATED if valuation.gaps
              else EvaluationStatus.COMPLETE)
    return StateValuation(
        board.position_key, valuation.total, LEDGER_VALUE_SCALE,
        board.seat, evaluator_identity, value_components(valuation.contributions),
        status, valuation.gaps, valuation.prize_map)


def ledger_valuation_from_state(valuation: StateValuation) -> Valuation:
    activations = tuple(FeatureActivation(
        item.key, item.activation, item.provenance) for item in valuation.components)
    contributions = tuple(FeatureContribution(
        item.key, item.activation, item.coefficient, item.value, item.provenance)
        for item in valuation.components)
    return Valuation(
        valuation.total, (), valuation.gaps, activations, contributions, valuation.evidence)


__all__ = ("LEDGER_VALUE_SCALE", "LedgerValueEvaluator", "ledger_valuation_from_state",
           "state_valuation_from_ledger", "value_components")
