from __future__ import annotations

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

    def __init__(self):
        self._snapshots: dict[tuple[str, str], EvaluationSnapshot] = {}
        self.last_snapshot: EvaluationSnapshot | None = None

    def clear(self) -> None:
        self._snapshots = {}
        self.last_snapshot = None

    def snapshot(self, model_identity: str, position_key: str):
        return getattr(self, "_snapshots", {}).get((str(model_identity), str(position_key)))

    def evaluate(self, request) -> StateValuation:
        board = getattr(request.state, "observation", request.state)
        model = request.evaluation_model
        snapshots = getattr(self, "_snapshots", None)
        if snapshots is None:
            self._snapshots = snapshots = {}
        parent_key = (None if request.parent_valuation is None else
                      (model.identity, request.parent_valuation.state_key))
        parent = None if parent_key is None else snapshots.get(parent_key)
        snapshot = evaluate_snapshot(
            board, model, parent=parent, delta=request.observation_delta)
        if parent is not None and os.environ.get("LEDGER_INCREMENTAL_PARITY") == "1":
            full = evaluate(board, model)
            if (snapshot.valuation.total != full.total
                    or snapshot.valuation.activations != full.activations
                    or snapshot.valuation.gaps != full.gaps
                    or snapshot.valuation.prize_map != full.prize_map):
                raise AssertionError("incremental Ledger valuation differs from full valuation")
        snapshots[(model.identity, board.position_key)] = snapshot
        self.last_snapshot = snapshot
        return state_valuation_from_ledger(board, snapshot.valuation)


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
