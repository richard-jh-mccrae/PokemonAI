from __future__ import annotations

import math

import ast
import hashlib
import os
from pathlib import Path

from common.decision import (
    EvaluationStatus,
    StateValuation,
    ValueComponent,
    ValueScale,
)

from .features import FEATURE_CATALOG
from .evaluate import (EvaluationSnapshot, FeatureActivation, FeatureContribution, Valuation,
                       evaluate, evaluate_snapshot)


LEDGER_VALUE_SCALE = ValueScale("ledger-worth", 1)
EVALUATOR_ID_DIGEST_BYTES = 16


def evaluator_semantics_identity(paths=None) -> str:
    paths = tuple(paths or (
        Path(__file__).with_name("activation.py"),
        Path(__file__).with_name("capabilities.py"),
        Path(__file__).with_name("evaluate.py"),
        Path(__file__).with_name("features.py"),
        Path(__file__).with_name("portfolio.py"),
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

    def evaluate_with_state(
            self, request, parent_state=None) -> tuple[StateValuation, EvaluationSnapshot]:
        board = getattr(request.state, "observation", request.state)
        model = request.evaluation_model
        parent = parent_state if isinstance(parent_state, EvaluationSnapshot) else None
        snapshot = evaluate_snapshot(
            board, model, parent=parent, delta=request.observation_delta)
        if parent is not None and os.environ.get("LEDGER_INCREMENTAL_PARITY") == "1":
            full = evaluate(board, model)
            if snapshot.valuation != full:
                raise AssertionError("incremental Ledger valuation differs from full valuation")
        return state_valuation_from_ledger(
            board, snapshot.valuation, self.identity), snapshot

    def evaluate(self, request) -> StateValuation:
        return self.evaluate_with_state(request)[0]


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
        status, valuation.gaps, valuation.prize_map, board.valuation_key)


def ledger_valuation_from_state(valuation: StateValuation) -> Valuation:
    totals = {}
    provenance = {}
    for item in valuation.components:
        totals.setdefault(item.key, []).append(item.activation)
        provenance.setdefault(item.key, set()).update(item.provenance)
    activations = tuple(FeatureActivation(
        key, math.fsum(values), tuple(sorted(provenance[key])))
        for key, values in sorted(totals.items()) if math.fsum(values))
    contributions = tuple(FeatureContribution(
        item.key, item.activation, item.coefficient, item.value, item.provenance)
        for item in valuation.components)
    return Valuation(
        valuation.total, (), valuation.gaps, activations, contributions, valuation.evidence)


__all__ = ("LEDGER_VALUE_SCALE", "LedgerValueEvaluator", "ledger_valuation_from_state",
           "state_valuation_from_ledger", "value_components")
