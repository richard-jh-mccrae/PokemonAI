"""Matchup favorability — consumer-side bridge from the Read to play (docs/scouting.md).

Pure and lib-free. Turns the offline matchup win-rates compiled into the artifact
(``dossier[my_archetype]["matchups"]``) into an expected favorability against the Read's
candidate opponents. The agent supplies its *own* archetype (known at build time); how it
learns that is the caller's concern, not this module's.

This reads the artifact; it never acts — choosing a Posture from the favorability is the
consumer's job, exactly as with threats/targets.
"""
from __future__ import annotations

from .artifact import Artifact


def matchup_favorability(artifact: Artifact, my_archetype: str,
                         candidates: list[tuple[str, float]]) -> tuple[float, float]:
    """Posterior-weighted expected win-rate of ``my_archetype`` vs the Read candidates.

    Args:
        artifact: the loaded Scouting artifact.
        my_archetype: the agent's own archetype name (the matchup table is keyed by it).
        candidates: the Read's ``(opponent_archetype, posterior)`` list.

    Returns:
        ``(favorability, coverage)``. ``favorability`` is the candidates' matchup
        win-rates weighted by posterior (0.5 for any candidate with no compiled cell);
        ``coverage`` is the share of posterior mass that had a real cell — low coverage
        means the favorability is mostly the 0.5 default, so trust it less. Degrades to
        ``(0.5, 0.0)`` for an unknown/empty archetype or empty candidates; never raises.
    """
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
