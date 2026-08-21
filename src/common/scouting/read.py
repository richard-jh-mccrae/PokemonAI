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
    role: str            # e.g. primary_attacker / backup_attacker / engine / fragile_preevo
    seen: bool           # True = on the board now; False = predicted/expected


@dataclass
class EvoPath:
    """Predicted evolution of an in-play opponent Pokémon toward its line top."""
    seen_cardId: int
    line: list[int]      # [basic, …, top] card ids
    top_cardId: int


@dataclass
class Read:
    candidates: list[tuple[str, float]] = field(default_factory=list)
    unknown_mass: float = 1.0
    confidence: tuple[float, float] = (0.0, 0.0)                       # (top posterior, margin)
    evolution_paths: list[EvoPath] = field(default_factory=list)
    expected_cards: list[tuple[int, float]] = field(default_factory=list)
    threats: list[Intel] = field(default_factory=list)
    targets: list[Intel] = field(default_factory=list)


__all__ = ["EvoPath", "Intel", "Read"]
