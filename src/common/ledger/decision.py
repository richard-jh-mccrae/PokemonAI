from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from common.decision import (
    EvaluationStatus,
    StateValuation,
    ValueComponent,
    ValueScale,
)

from .features import FEATURE_CATALOG
from .evaluate import (FeatureActivation, FeatureContribution, Valuation, evaluate)


LEDGER_VALUE_SCALE = ValueScale("ledger-worth", 1)
EVALUATOR_ID_DIGEST_BYTES = 16


def evaluator_semantics_identity(paths=None) -> str:
    paths = tuple(paths or (
        Path(__file__).with_name("activation.py"),
        Path(__file__).with_name("evaluate.py"),
        Path(__file__).with_name("features.py"),
        Path(__file__).with_name("prizes.py"),
        Path(__file__).with_name("worth.py"),
    ))
    digest = hashlib.blake2b(digest_size=EVALUATOR_ID_DIGEST_BYTES)
    for path in paths:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                node.body = body[1:]
        digest.update(Path(path).name.encode("utf-8"))
        digest.update(ast.dump(tree, include_attributes=False).encode("utf-8"))
    return digest.hexdigest()


class LedgerValueEvaluator:
    identity = f"ledger-linear-v2:{FEATURE_CATALOG.identity}:{evaluator_semantics_identity()}"

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
