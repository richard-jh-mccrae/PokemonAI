"""AIVAT variance-reduction seam (ADR-0053 WP2 design D5) — frozen now, fills after WP1.

AIVAT (Burch et al.) is provably-unbiased variance reduction: given a rough per-decision
state-value estimate and one side's known strategy, it subtracts out the variance from chance
(shuffles/draws) and known-strategy randomization, so a paired eval reaches significance on
~10× fewer games (DeepStack's human match: 95% CI ±220→±40 mbb/g). The value net WP1 trains is
exactly that estimate — and the counterfactual values a decision-time search already computes
come free — so the eval harness gets low-variance measurement as a byproduct once G1 lands.

v1 ships the NULL implementation: it returns None, so the C3 report carries ``aivat: null`` and
the paired win-delta stands on its own. WP1 fills this one function — the signature is frozen so
the plug-in needs no harness rework.
"""
from __future__ import annotations


def aivat(films, value_fn):
    """AIVAT-correct the paired eval over ``films`` using per-decision values from ``value_fn``.

    ``films`` is the run's captured replay films; ``value_fn`` maps a decision obs to a P(win)
    estimate (WP1's value net). Returns ``{"variance_reduction": float, "corrected_delta": float}``
    once implemented, or **None** (the v1 null seam) → the report emits ``aivat: null``. The
    frozen contract: a null return is always valid and never raises, so an eval run is complete
    with or without the correction.
    """
    return None
