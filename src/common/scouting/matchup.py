"""Matchup favorability — turns the artifact's compiled matchup win-rates into an expected
favorability against the Read's candidate opponents (docs/scouting.md). Pure and lib-free; the
agent supplies its own archetype. It reads the artifact and never acts."""
from __future__ import annotations

from .artifact import Artifact


def matchup_favorability(artifact: Artifact, my_archetype: str,
                         candidates: list[tuple[str, float]]) -> tuple[float, float]:
    """``(favorability, coverage)`` — posterior-weighted win-rate of ``my_archetype`` vs the Read's
    candidates (0.5 for an uncompiled cell), and the posterior mass that had a real cell."""
    vs = ((artifact.dossiers or {}).get(my_archetype) or {}).get("matchups") or {}
    num = covered = total = 0.0
    for arch, posterior in candidates:
        total += posterior
        cell = vs.get(arch)
        num += posterior * (cell["win_rate"] if cell else 0.5)
        if cell:
            covered += posterior
    if total <= 0:
        return (0.5, 0.0)
    return (round(num / total, 4), round(covered / total, 4))
