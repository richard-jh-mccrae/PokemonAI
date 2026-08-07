"""Presence-only Naive Bayes recognition scorer (docs/scouting.md): ranks Archetypes given the
opponent cards revealed so far. Pure — no I/O, no engine."""
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
    """``(candidates, unknown_mass)``, candidates ``[(archetype, posterior)]`` sorted descending.
    ``background`` is the off-meta hypothesis; ``floor`` smooths a card absent from an inclusion."""
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
