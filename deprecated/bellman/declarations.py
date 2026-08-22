"""Deck declarations consumed only by the quarantined Bellman teacher."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class BellmanDeclarations:
    partners: Mapping[int, tuple[int, ...]] = field(default_factory=dict)
    worth_overrides: Mapping[int, float] = field(default_factory=dict)
    pilot_overrides: Mapping[str, float] = field(default_factory=dict)
    prize_routes: tuple[tuple[int, ...], ...] = ()
    prizes_to_win: int | None = None


_BY_DECK = {
    "dragapult_ex": BellmanDeclarations(
        partners={112: (1260,)}, worth_overrides={1260: 10.0}),
    "mega_lucario": BellmanDeclarations(
        partners={676: (675,), 675: (676,)}),
    "mega_starmie": BellmanDeclarations(
        prize_routes=((666, 1031, 1031), (1031, 666, 1031)),
        prizes_to_win=6),
}


def bellman_declarations(deck_name: str) -> BellmanDeclarations:
    return _BY_DECK.get(str(deck_name), BellmanDeclarations())


__all__ = ("BellmanDeclarations", "bellman_declarations")
