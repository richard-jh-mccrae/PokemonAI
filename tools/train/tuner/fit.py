"""Turn featurized Corrections into ranking constraints and fit Hypothesis weights.

`Score = Σ wᵢ·firedᵢ + tactical` is linear in the weights, so `correct ≻ chosen` is the
linear constraint `Σ wᵢ·Δᵢ + Δtactical > 0` where `Δᵢ ∈ {-1,0,+1}` over the discriminating
Hypotheses. Fitting is a convex linear-ranking problem (ADR-0009); we use a lib-free
**soft-margin** structured perceptron — L2-regularised toward the authored seeds, band-clamped to
docs/weights.md, and pocketed (return the best iterate, not the oscillating last one) — so a
contradictory corpus can't run a weight away or collapse a doctrine for a couple of extra ranks.
"""
from __future__ import annotations

from dataclasses import dataclass

from .featurize import Featurization


@dataclass
class Constraint:
    deltas: dict          # hyp_id -> +1 (favors correct) | -1 (favors chosen)
    tactical_delta: float  # combat-term advantage for correct (fixed bias, not tunable)


def ranking_constraint(feat: Featurization) -> Constraint:
    """The signed sparse delta encoding `correct ≻ chosen`; shared Hypotheses cancel."""
    chosen, correct = set(feat.chosen_fired), set(feat.correct_fired)
    deltas = {h: 1 for h in correct - chosen}
    deltas.update({h: -1 for h in chosen - correct})
    return Constraint(deltas=deltas, tactical_delta=feat.tactical_delta)


# `docs/weights.md`. DEFAULT_REG is the CONSERVATISM knob: high enough that a contradictory corpus
# cannot buy a few satisfied ranks by gutting a doctrine weight; lower it (`--reg`) for a clean one.
DEFAULT_REG = 0.25
_CLAMP = 100.0          # >100 is reserved combat-scale
_MARGIN_TARGET = 1.0    # keeps a satisfied rank off the knife-edge


def _total_hinge(constraints: list[Constraint], weights: dict, target: float) -> float:
    """Ranking loss: Σ max(0, target − margin). 0 ⇔ every rank holds with room."""
    return sum(max(0.0, target - margin_of(c, weights)) for c in constraints)


def _objective(constraints, weights, seed0, target, reg) -> float:
    """J = Σ hinge + (reg/2)·Σ(w−seed)². The QUADRATIC drift term is what tells a fit from an
    overfit: spreading a move over several weights is cheap, collapsing one doctrine weight is not."""
    drift_sq = sum((weights[h] - seed0[h]) ** 2 for h in weights)
    return _total_hinge(constraints, weights, target) + 0.5 * reg * drift_sq


def fit_weights(constraints: list[Constraint], seeds: dict, *, lr: float = 1.0, epochs: int = 200,
                reg: float = DEFAULT_REG, clamp: float = _CLAMP, target: float = _MARGIN_TARGET) -> dict:
    """Regularised structured perceptron with a POCKET. A constant step oscillates around the margin
    boundary, so the last iterate is often worse than one already seen — keep the lowest-``J``."""
    weights = dict(seeds)
    for constraint in constraints:
        for hid in constraint.deltas:
            weights.setdefault(hid, 0.0)
    seed0 = {hid: float(seeds.get(hid, 0.0)) for hid in weights}

    best = dict(weights)                              # seeds are the first candidate
    best_j = _objective(constraints, weights, seed0, target, reg)
    for _ in range(epochs):
        violated = False
        for constraint in constraints:
            if margin_of(constraint, weights) < target:
                violated = True
                for h, d in constraint.deltas.items():
                    weights[h] += lr * d
        for hid, w in weights.items():               # L2 pull to seed + band clamp
            w -= lr * reg * (w - seed0[hid])
            weights[hid] = clamp if w > clamp else -clamp if w < -clamp else w
        j = _objective(constraints, weights, seed0, target, reg)
        if j < best_j:
            best_j, best = j, dict(weights)
        if not violated:
            break
    return best


def margin_of(constraint: Constraint, weights: dict) -> float:
    """Signed rank margin under ``weights``; ``> 0`` ⇔ ``correct ≻ chosen`` for this constraint."""
    return sum(weights.get(h, 0.0) * d for h, d in constraint.deltas.items()) + constraint.tactical_delta


_margin = margin_of  # back-compat alias


def satisfied_after_fit(constraints: list[Constraint], seeds: dict) -> list[bool]:
    """Fit weights over ``constraints`` then report, per constraint, whether ``correct ≻ chosen``
    holds (margin > 0). Contradictory constraints leave at least one unsatisfied."""
    weights = fit_weights(constraints, seeds)
    return [margin_of(c, weights) > 0 for c in constraints]
