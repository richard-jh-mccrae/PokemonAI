"""Turn featurized Corrections into ranking constraints and fit Hypothesis weights.

`Score = Σ wᵢ·firedᵢ + tactical` is linear in the weights, so `correct ≻ chosen` is the
linear constraint `Σ wᵢ·Δᵢ + Δtactical > 0` where `Δᵢ ∈ {-1,0,+1}` over the discriminating
Hypotheses. Fitting is a convex linear-ranking problem (ADR-0009); we use a lib-free
structured perceptron, band-anchored to docs/weights.md for legibility.
"""
from __future__ import annotations

from dataclasses import dataclass

from .featurize import Featurization


@dataclass
class Constraint:
    deltas: dict          # hyp_id -> +1 (favors correct) | -1 (favors chosen)
    tactical_delta: float  # combat-term advantage for correct (a fixed bias, not tunable)


def ranking_constraint(feat: Featurization) -> Constraint:
    """The signed sparse delta encoding `correct ≻ chosen`; shared Hypotheses cancel."""
    chosen, correct = set(feat.chosen_fired), set(feat.correct_fired)
    deltas = {h: 1 for h in correct - chosen}
    deltas.update({h: -1 for h in chosen - correct})
    return Constraint(deltas=deltas, tactical_delta=feat.tactical_delta)


def fit_weights(constraints: list[Constraint], seeds: dict, *, lr: float = 1.0,
                epochs: int = 100) -> dict:
    """Structured perceptron: start from the authored ``seeds`` and, for each violated
    ranking constraint, nudge its discriminating weights toward satisfying it. Converges when
    no constraint is violated (or after ``epochs``). Returns the effective ``{hyp_id: weight}``
    overrides. (Band-anchoring to docs/weights.md is a planned refinement.)"""
    weights = dict(seeds)
    for constraint in constraints:
        for hid in constraint.deltas:
            weights.setdefault(hid, 0.0)
    for _ in range(epochs):
        violated = False
        for constraint in constraints:
            margin = sum(weights[h] * d for h, d in constraint.deltas.items()) + constraint.tactical_delta
            if margin <= 0:
                violated = True
                for h, d in constraint.deltas.items():
                    weights[h] += lr * d
        if not violated:
            break
    return weights


def _margin(constraint: Constraint, weights: dict) -> float:
    return sum(weights.get(h, 0.0) * d for h, d in constraint.deltas.items()) + constraint.tactical_delta


def satisfied_after_fit(constraints: list[Constraint], seeds: dict) -> list[bool]:
    """Fit weights over ``constraints`` then report, per constraint, whether ``correct ≻ chosen``
    holds (margin > 0). Contradictory constraints leave at least one unsatisfied."""
    weights = fit_weights(constraints, seeds)
    return [_margin(c, weights) > 0 for c in constraints]
