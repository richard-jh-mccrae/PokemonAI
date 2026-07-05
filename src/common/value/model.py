"""The Base Value Model runtime (ADR-0042): load a trained logistic once, predict ``P(win)`` from a
feature vector — pure Python, dependency-free, **absent-safe**.

The shipped artifact (``value_model.json``, written by ``tools/train/value/train.py``) carries the
standardization stats and weights for :data:`~common.value.features.FEATURE_NAMES`. With no artifact
the model is *null*: ``present`` is False and every prediction is 0.5 (zero influence), so the
closed-form heuristic is the clean fallback (ADR-0007). Inference is one standardize-then-dot-product
over ~17 features — microseconds, never a budget concern.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from common.value.features import FEATURE_NAMES

# The shipped artifact lives beside this module (packaged into the Bundle like tuned.json).
_ARTIFACT = Path(__file__).with_name("value_model.json")


class ValueModel:
    """A loaded logistic value model, or the null model. Construct via :meth:`load`. ``predict``
    takes a feature vector in :data:`FEATURE_NAMES` order and returns ``P(win) ∈ [0, 1]``."""

    __slots__ = ("present", "_w", "_mean", "_std", "meta")

    def __init__(self, weights=None, mean=None, std=None, meta=None):
        self.present = weights is not None
        self._w = list(weights or ())
        self._mean = list(mean or ())
        self._std = list(std or ())
        self.meta = meta or {}

    @classmethod
    def load(cls, path=None) -> "ValueModel":
        """Load the model from ``path`` (default: the packaged artifact). Returns the **null model**
        when the file is absent or malformed, or when its feature list doesn't match this build's
        :data:`FEATURE_NAMES` (a stale artifact must never mis-map columns) — never raises."""
        p = Path(path) if path is not None else _ARTIFACT
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return cls()
        if list(d.get("features", ())) != list(FEATURE_NAMES):
            return cls()                               # shape drift → refuse (fall back to heuristic)
        w, mean, std = d.get("weights"), d.get("mean"), d.get("std")
        n = len(FEATURE_NAMES)
        if not (isinstance(w, list) and len(w) == n == len(mean or ()) == len(std or ())):
            return cls()
        return cls(weights=w, mean=mean, std=std, meta=d.get("meta", {}))

    def predict(self, features) -> float:
        """``P(win)`` for a feature vector (standardize each column by the trained mean/std, then
        the logistic of the dot product). The null model returns 0.5; a zero-variance column
        contributes only through its weight×0 (std floored to 1.0 at train time)."""
        if not self.present:
            return 0.5
        z = 0.0
        for i, x in enumerate(features):
            s = self._std[i] or 1.0
            z += self._w[i] * ((x - self._mean[i]) / s)
        if z < -60.0:                                  # guard the exp overflow at the tails
            return 0.0
        if z > 60.0:
            return 1.0
        return 1.0 / (1.0 + math.exp(-z))
