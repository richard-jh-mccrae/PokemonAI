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
    minAttackCost: int | None = None   # energy count of the card's cheapest attack (None if unknown)
    weakness: int | None = None
    resistance: int | None = None
    energyType: int | None = None
    stage: str | None = None
    evolvesFrom: str | None = None


class DictCardStatProvider:
    """In-memory provider for tests and precomputed caches."""

    def __init__(self, stats: dict[int, CardStat]):
        self._stats = stats
        self._forward: _ForwardIndex | None = None

    def get(self, card_id: int) -> CardStat | None:
        return self._stats.get(card_id)

    def forward_max_damage(self, card_id: int) -> int:
        """Max damage the card's evolution line eventually reaches (see ``_ForwardIndex``)."""
        if self._forward is None:
            self._forward = _build_forward_index(self._stats)
        st = self._stats.get(card_id)
        return self._forward.max_forward_damage(st.name) if st else 0


def _build_cache(card_data, attacks) -> dict[int, CardStat]:
    """Pure transform: engine card/attack records -> ``{cardId: CardStat}``.

    Kept separate from the engine import so it is testable lib-free.
    """
    dmg: dict[int, int] = {}
    cost: dict[int, int] = {}
    for a in attacks:
        dmg.setdefault(a.attackId, a.damage)
        cost.setdefault(a.attackId, len(getattr(a, "energies", None) or []))
    cache: dict[int, CardStat] = {}
    for c in card_data:
        max_dmg = max((dmg.get(aid, 0) for aid in c.attacks), default=0)
        costs = [cost[aid] for aid in c.attacks if aid in cost]   # energy-count of each known attack
        cache[c.cardId] = CardStat(
            cardId=c.cardId, name=c.name, hp=int(c.hp),
            ex=bool(c.ex), megaEx=bool(c.megaEx), maxDamage=int(max_dmg),
            minAttackCost=(min(costs) if costs else None),
            weakness=(int(c.weakness) if c.weakness is not None else None),
            resistance=(int(c.resistance) if c.resistance is not None else None),
            energyType=(int(c.energyType) if c.energyType is not None else None),
            evolvesFrom=c.evolvesFrom,
        )
    return cache


class _ForwardIndex:
    """Generic, deck-agnostic forward-evolution map (ADR-0020).

    Inverts ``CardStat.evolvesFrom`` (a *name*) over the stat cache so we can read, off any benched
    pre-evolution, the damage its line eventually reaches — the **Evolving Threat** signal (e.g.
    Riolu -> Mega Lucario ex = 270). Keyed by name; folds MAX over every printing of a name (names
    are not unique). Distinct from the Read's opponent-specific ``EvoPath``.
    """

    def __init__(self, cache: dict[int, CardStat]):
        self._maxdmg: dict[str, int] = {}        # name -> max printed damage over all its printings
        self._children: dict[str, set[str]] = {}  # parent name -> child names (evolvesFrom == parent)
        for st in cache.values():
            if not st.name:
                continue
            if st.maxDamage > self._maxdmg.get(st.name, 0):
                self._maxdmg[st.name] = st.maxDamage
            if st.evolvesFrom:
                self._children.setdefault(st.evolvesFrom, set()).add(st.name)

    def max_forward_damage(self, name: str | None) -> int:
        """Max printed damage over the forms ``name`` can evolve INTO (descendants only, multi-hop);
        0 if it is a dead end. Cycle-guarded, so a malformed line can't loop."""
        if not name:
            return 0
        best, seen, stack = 0, set(), list(self._children.get(name, ()))
        while stack:
            child = stack.pop()
            if child in seen:
                continue
            seen.add(child)
            best = max(best, self._maxdmg.get(child, 0))
            stack.extend(self._children.get(child, ()))
        return best


def _build_forward_index(cache: dict[int, CardStat]) -> _ForwardIndex:
    """Pure transform: ``{cardId: CardStat}`` -> forward-evolution index. Kept lib-free for tests."""
    return _ForwardIndex(cache)


class EngineCardStatProvider:
    """Lazily build a ``{cardId: CardStat}`` cache from the native engine (runtime only)."""

    def __init__(self):
        self._cache: dict[int, CardStat] | None = None
        self._forward: _ForwardIndex | None = None

    def _ensure_cache(self) -> None:
        """Build the stat cache + forward index together, once. The single build site so the two
        never diverge — ``get`` and ``forward_max_damage`` both go through here."""
        if self._cache is None:
            from cg.api import all_attack, all_card_data  # runtime only
            self._cache = _build_cache(all_card_data(), all_attack())
            self._forward = _build_forward_index(self._cache)

    def get(self, card_id: int) -> CardStat | None:
        self._ensure_cache()
        return self._cache.get(card_id)

    def forward_max_damage(self, card_id: int) -> int:
        """Max damage the card's evolution line eventually reaches (see ``_ForwardIndex``)."""
        self._ensure_cache()
        st = self._cache.get(card_id)
        return self._forward.max_forward_damage(st.name) if st else 0
