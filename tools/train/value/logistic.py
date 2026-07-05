"""A pure-Python, dependency-free logistic-regression trainer (ADR-0042).

No numpy / sklearn — the grader never runs this (only ``common.value.model`` runs there), but the
project must build offline on Windows + Linux with the stdlib alone, so the trainer is stdlib too.
Standardizes each feature, fits with full-batch gradient descent + L2, and reports train/holdout
log-loss so a caller can see whether the fit generalizes. Small by design: ~17 features, thousands
of rows, converges in a second.
"""
from __future__ import annotations

import math


def standardize(rows: list[list[float]]) -> tuple[list[float], list[float]]:
    """Per-column ``(mean, std)`` of ``rows`` (std floored to 1.0 so a constant column — e.g. the
    bias, or a feature unseen in this corpus — divides cleanly and contributes nothing)."""
    n = len(rows)
    d = len(rows[0]) if rows else 0
    mean = [0.0] * d
    for r in rows:
        for j in range(d):
            mean[j] += r[j]
    mean = [m / n for m in mean]
    var = [0.0] * d
    for r in rows:
        for j in range(d):
            var[j] += (r[j] - mean[j]) ** 2
    std = [math.sqrt(v / n) or 1.0 for v in var]
    return mean, std


def _sigmoid(z: float) -> float:
    if z < -60.0:
        return 0.0
    if z > 60.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def log_loss(weights, rows, labels, mean, std) -> float:
    """Mean binary cross-entropy of ``weights`` over standardized ``rows`` (a clamped-probability
    log-loss; the honest generalization read a caller prints for the holdout split)."""
    total = 0.0
    for r, y in zip(rows, labels):
        p = _sigmoid(sum(weights[j] * ((r[j] - mean[j]) / std[j]) for j in range(len(r))))
        p = min(max(p, 1e-12), 1 - 1e-12)
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(rows) if rows else 0.0


def fit(rows, labels, *, mean, std, lr: float = 0.3, epochs: int = 400, l2: float = 1e-3):
    """Full-batch gradient descent on standardized ``rows`` → weight vector (bias column NOT
    L2-penalized, the standard convention). Deterministic (no shuffling / no RNG — reproducible and
    grader-safe), so the same corpus always yields the same model."""
    n = len(rows)
    d = len(rows[0]) if rows else 0
    w = [0.0] * d
    std_rows = [[(r[j] - mean[j]) / std[j] for j in range(d)] for r in rows]
    for _ in range(epochs):
        grad = [0.0] * d
        for r, y in zip(std_rows, labels):
            err = _sigmoid(sum(w[j] * r[j] for j in range(d))) - y
            for j in range(d):
                grad[j] += err * r[j]
        for j in range(d):
            g = grad[j] / n + (0.0 if j == 0 else l2 * w[j])   # column 0 is the bias — never penalized
            w[j] -= lr * g
    return w
