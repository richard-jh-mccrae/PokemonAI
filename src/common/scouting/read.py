"""The Read and its parts — the public output of Scouting (see docs/scouting.md).

Pure data describing the matchup; it never acts. Cards are referenced by id; stats
are resolved by the consumer via the card-stat cache.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Intel:
    """An objective threat or target on the opponent's side."""
    cardId: int
    role: str            # e.g. attacker / engine / fragile_preevo / prize_liability
    seen: bool           # True = on the board now; False = predicted/expected


@dataclass
class EvoPath:
    """Predicted evolution of an in-play opponent Pokémon toward its line top."""
    seen_cardId: int
    line: list[int]      # [basic, …, top] card ids
    top_cardId: int


@dataclass
class Read:
    candidates: list[tuple[str, float]] = field(default_factory=list)  # top-k (archetype, posterior)
    unknown_mass: float = 1.0
    confidence: tuple[float, float] = (0.0, 0.0)                       # (top posterior, margin)
    evolution_paths: list[EvoPath] = field(default_factory=list)
    expected_cards: list[tuple[int, float]] = field(default_factory=list)
    threats: list[Intel] = field(default_factory=list)
    targets: list[Intel] = field(default_factory=list)


POSTURE_CONFIDENCE_LOW = 0.5
POSTURE_CONFIDENCE_HIGH = 0.85


def posture_gamma(read: Read | None) -> float:
    """Map a Scout posterior to the Bellman belief-strength interval ``[0, 1]``."""

    if read is None or not read.candidates:
        return 0.0
    top = read.confidence[0] if read.confidence else 0.0
    span = POSTURE_CONFIDENCE_HIGH - POSTURE_CONFIDENCE_LOW
    ramp = max(0.0, min(1.0, (top - POSTURE_CONFIDENCE_LOW) / span))
    return ramp * (1.0 - read.unknown_mass)


__all__ = ["EvoPath", "Intel", "Read", "posture_gamma"]
