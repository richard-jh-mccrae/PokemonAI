"""Presence-only Naive Bayes recognition scorer (see docs/scouting.md).

`posterior` ranks Archetypes given the set of opponent cards revealed so far. It is a
pure function — no I/O, no engine — so it is trivially testable and fast to call each
decision.
"""
from __future__ import annotations


def posterior(
    priors: dict[str, float],
    card_inclusion: dict[str, dict[int, float]],
    background: dict[int, float],
    evidence,
    *,
    unknown_prior: float = 0.05,
    floor: float = 0.01,
) -> tuple[list[tuple[str, float]], float]:
    """Rank archetypes by posterior given revealed cards.

    Args:
        priors: ``{archetype: prior_probability}``.
        card_inclusion: ``{archetype: {card_id: P(card in deck | archetype)}}``.
        background: ``{card_id: P(card present overall)}`` — the unknown hypothesis.
        evidence: iterable of revealed opponent card ids.
        unknown_prior: prior mass for the off-meta "unknown" hypothesis.
        floor: smoothing floor for a card absent from an archetype's inclusion.

    Returns:
        ``(candidates, unknown_mass)`` where candidates is ``[(archetype, posterior)]``
        sorted descending.
    """
    ev = list(evidence)

    scores: dict[str, float] = {}
    for arch, prior in priors.items():
        incl = card_inclusion.get(arch, {})
        s = prior
        for c in ev:
            s *= incl.get(c, floor)
        scores[arch] = s

    s_unknown = unknown_prior
    for c in ev:
        s_unknown *= background.get(c, floor)

    total = sum(scores.values()) + s_unknown
    if total <= 0:
        return [(a, 0.0) for a in priors], 1.0

    candidates = sorted(
        ((a, s / total) for a, s in scores.items()), key=lambda x: x[1], reverse=True
    )
    return candidates, s_unknown / total
