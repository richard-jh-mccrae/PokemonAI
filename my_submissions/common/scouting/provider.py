"""Card-stat providers (see docs/scouting.md).

The Scout resolves opponent card ids to stats through a provider, so recognition stays
decoupled from the engine: runtime uses ``EngineCardStatProvider``; tests inject
``DictCardStatProvider`` (lib-free). ``.get(card_id)`` returns a ``CardStat`` or None.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CardStat:
    cardId: int
    name: str = ""
    hp: int = 0
    ex: bool = False
    megaEx: bool = False
    maxDamage: int = 0
    weakness: int | None = None
    resistance: int | None = None
    energyType: int | None = None
    stage: str | None = None
    evolvesFrom: str | None = None


class DictCardStatProvider:
    """In-memory provider for tests and precomputed caches."""

    def __init__(self, stats: dict[int, CardStat]):
        self._stats = stats

    def get(self, card_id: int) -> CardStat | None:
        return self._stats.get(card_id)


def _build_cache(card_data, attacks) -> dict[int, CardStat]:
    """Pure transform: engine card/attack records -> ``{cardId: CardStat}``.

    Kept separate from the engine import so it is testable lib-free.
    """
    dmg: dict[int, int] = {}
    for a in attacks:
        dmg.setdefault(a.attackId, a.damage)
    cache: dict[int, CardStat] = {}
    for c in card_data:
        max_dmg = max((dmg.get(aid, 0) for aid in c.attacks), default=0)
        cache[c.cardId] = CardStat(
            cardId=c.cardId, name=c.name, hp=int(c.hp),
            ex=bool(c.ex), megaEx=bool(c.megaEx), maxDamage=int(max_dmg),
            weakness=(int(c.weakness) if c.weakness is not None else None),
            resistance=(int(c.resistance) if c.resistance is not None else None),
            energyType=(int(c.energyType) if c.energyType is not None else None),
            evolvesFrom=c.evolvesFrom,
        )
    return cache


class EngineCardStatProvider:
    """Lazily build a ``{cardId: CardStat}`` cache from the native engine (runtime only)."""

    def __init__(self):
        self._cache: dict[int, CardStat] | None = None

    def get(self, card_id: int) -> CardStat | None:
        if self._cache is None:
            from cg.api import all_attack, all_card_data  # runtime only
            self._cache = _build_cache(all_card_data(), all_attack())
        return self._cache.get(card_id)
