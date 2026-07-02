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


# Fit defaults (docs/weights.md). DEFAULT_REG = L2 pull back to authored seed each epoch - keeps fit
# legible, makes a *non-separable* corpus converge to a finite minimiser instead of pumping a weight
# to infinity (old raw perceptron drove `power-up-attacker` to 156; a perpetually-violated push now
# settles at ~push/reg). Also the **conservatism knob**: default is deliberately high so a
# contradictory corpus can't buy a couple extra satisfied ranks by gutting a doctrine weight (e.g.
# `accel-into-main` 30->2) - that overfit gets rejected, seeds kept. Lower it (CLI `--reg`) to let
# clean, consistent corrections move weights more freely; ladder (ADR-0009) is the ultimate arbiter
# of magnitude. CLAMP = hard band backstop (>100 is reserved combat-scale, docs/weights.md).
# MARGIN_TARGET keeps a satisfied rank off the knife-edge.
DEFAULT_REG = 0.25
_CLAMP = 100.0
_MARGIN_TARGET = 1.0


def _total_hinge(constraints: list[Constraint], weights: dict, target: float) -> float:
    """Ranking loss: Σ max(0, target − margin). 0 ⇔ every rank holds with room."""
    return sum(max(0.0, target - margin_of(c, weights)) for c in constraints)


def _objective(constraints, weights, seed0, target, reg) -> float:
    """The soft-margin objective J = Σ hinge + (reg/2)·Σ(w−seed)². The *quadratic* drift term is
    what tells a good fit from an overfit: spreading a small move across several weights is cheap,
    but collapsing one doctrine weight far from its seed is expensive — so the fit only does the
    latter when the ranking payoff genuinely outweighs it."""
    drift_sq = sum((weights[h] - seed0[h]) ** 2 for h in weights)
    return _total_hinge(constraints, weights, target) + 0.5 * reg * drift_sq


def fit_weights(constraints: list[Constraint], seeds: dict, *, lr: float = 1.0, epochs: int = 200,
                reg: float = DEFAULT_REG, clamp: float = _CLAMP, target: float = _MARGIN_TARGET) -> dict:
    """Regularised structured perceptron with a pocket (soft-margin ranking fit).

    Starts from the authored ``seeds``; for each violated ranking constraint (``margin < target``)
    nudges its discriminating weights toward satisfying it, then applies an L2 pull back toward the
    seed (``reg``) and clamps to the legible band (``±clamp``, docs/weights.md). Two properties make
    the result trustworthy:

    - **``reg`` bounds it.** A contradictory / non-separable corpus settles at ``≈ seed + push/reg``
      instead of running away — the raw perceptron pumped ``power-up-attacker`` to 156.
    - **The pocket picks the best iterate by ``_objective``.** A constant step oscillates around the
      margin boundary, so the *last* iterate is often worse than one already seen (this silently
      broke the W route: satisfiable corrections looked unsatisfiable). We keep the lowest-``J``
      weights seen — and because ``J`` includes the quadratic drift, the pocket won't grab an
      iterate that satisfies a couple more ranks by collapsing a weight far from its seed.

    Converges when no constraint is violated, else stops at ``epochs``. Returns ``{hyp_id: weight}``.
    """
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
