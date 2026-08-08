"""Derive a Correction's attribution by diffing the Hypotheses that fired for each option.

Pure routing logic (ADR-0017, tools/train/CONTEXT.md "Attribution"): inputs are the
fired-Hypothesis-id sets for `chosen` and `correct` plus the combat-term delta; output is the
attribution string that routes W (weight fix) vs H (new rule).
"""
from __future__ import annotations

from collections.abc import Iterable


def derive_attribution(chosen_ids: Iterable[str], correct_ids: Iterable[str],
                       tactical_delta: float = 0.0) -> str:
    """Differing fired sets are reorderable by a weight; IDENTICAL ones are not, so the gap is either
    the combat term (``tactical``) or a missing rule."""
    discriminating = set(chosen_ids) ^ set(correct_ids)
    if discriminating:
        return "hypothesis:" + ",".join(sorted(discriminating))
    return "tactical" if tactical_delta else "missing_hypothesis"
