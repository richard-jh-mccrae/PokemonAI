"""Name-keyed indexes over the CardStat cache: forward evolution (ADR-0020) and name -> ids
(ADR-0027). Pure, lib-free transforms over an already-built ``{cardId: CardStat}`` cache."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .provider import CardStat


class _ForwardIndex:
    """Deck-agnostic forward-evolution map: inverts ``CardStat.evolvesFrom`` (a *name*). Keyed by
    name, folding MAX over every printing. Distinct from the Read's opponent-specific ``EvoPath``."""

    def __init__(self, cache: dict[int, CardStat]):
        self._maxdmg: dict[str, int] = {}
        self._children: dict[str, set[str]] = {}
        self._name_ids: dict[str, set[int]] = {}
        for st in cache.values():
            if not st.name:
                continue
            self._name_ids.setdefault(st.name, set()).add(st.cardId)
            if st.maxDamage > self._maxdmg.get(st.name, 0):
                self._maxdmg[st.name] = st.maxDamage
            if st.evolvesFrom:
                self._children.setdefault(st.evolvesFrom, set()).add(st.name)

    def _descendant_names(self, name: str | None) -> set[str]:
        """The forms ``name`` can evolve INTO (descendants only, multi-hop). Cycle-guarded."""
        seen, stack = set(), list(self._children.get(name or "", ()))
        while stack:
            child = stack.pop()
            if child in seen:
                continue
            seen.add(child)
            stack.extend(self._children.get(child, ()))
        return seen

    def max_forward_damage(self, name: str | None) -> int:
        """Max printed damage over the forms ``name`` can evolve INTO; 0 for a dead end."""
        if not name:
            return 0
        return max((self._maxdmg.get(d, 0) for d in self._descendant_names(name)), default=0)

    def forward_card_ids(self, name: str | None) -> frozenset[int]:
        """Every card id of every form ``name`` can evolve INTO, all printings; empty for a dead end."""
        ids: set[int] = set()
        for d in self._descendant_names(name):
            ids |= self._name_ids.get(d, set())
        return frozenset(ids)


def _build_forward_index(cache: dict[int, CardStat]) -> _ForwardIndex:
    return _ForwardIndex(cache)


def _name_index(cache: dict[int, CardStat]) -> dict[str, frozenset[int]]:
    """``card name -> frozenset of ids printed under it`` — names aren't unique, so it folds every
    printing. The Matchup Brief consumer's name->id bridge (ADR-0027)."""
    idx: dict[str, set[int]] = {}
    for cid, st in cache.items():
        if st.name:
            idx.setdefault(st.name, set()).add(cid)
    return {name: frozenset(ids) for name, ids in idx.items()}
