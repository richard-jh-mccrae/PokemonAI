"""Name-keyed indexes over the CardStat cache: forward evolution + name -> ids.

``_ForwardIndex`` inverts ``CardStat.evolvesFrom`` so a consumer can read, off any benched
pre-evolution, what its line eventually becomes (the Evolving Threat signal, ADR-0020);
``_name_index`` is the Matchup Brief's name -> card-ids bridge (ADR-0027). Both are pure,
lib-free transforms over an already-built ``{cardId: CardStat}`` cache. Split out of
``provider.py`` (ADR-0054); the providers build and consume them lazily.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .provider import CardStat


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
        self._name_ids: dict[str, set[int]] = {}  # name -> every card id printed under it
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
        """Max printed damage over the forms ``name`` can evolve INTO (descendants only, multi-hop);
        0 if it is a dead end. Cycle-guarded, so a malformed line can't loop."""
        if not name:
            return 0
        return max((self._maxdmg.get(d, 0) for d in self._descendant_names(name)), default=0)

    def forward_card_ids(self, name: str | None) -> frozenset[int]:
        """Every card id of every form ``name`` can evolve INTO (descendants only, multi-hop, all
        printings) — so a consumer can ask whether a benched pre-evolution's line eventually reaches
        an ``ex`` / a card carrying a given Function Tag (e.g. a hand-size attacker). Empty for a dead
        end. Cycle-guarded (delegates to ``_descendant_names``)."""
        ids: set[int] = set()
        for d in self._descendant_names(name):
            ids |= self._name_ids.get(d, set())
        return frozenset(ids)


def _build_forward_index(cache: dict[int, CardStat]) -> _ForwardIndex:
    """Pure transform: ``{cardId: CardStat}`` -> forward-evolution index. Kept lib-free for tests."""
    return _ForwardIndex(cache)


def _name_index(cache: dict[int, CardStat]) -> dict[str, frozenset[int]]:
    """Reverse index ``card name -> frozenset of ids printed under it`` (names aren't unique — folds
    every printing). The Matchup Brief consumer's name->id bridge (ADR-0027). Pure/lib-free."""
    idx: dict[str, set[int]] = {}
    for cid, st in cache.items():
        if st.name:
            idx.setdefault(st.name, set()).add(cid)
    return {name: frozenset(ids) for name, ids in idx.items()}
