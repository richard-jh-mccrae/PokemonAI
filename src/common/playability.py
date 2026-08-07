"""Playability — BACKWARD line topology: can a card held in hand ever reach the board at all?
(ADR-0104, Issue #288.) `development.line_topology` asks the FORWARD question; this is its mirror.
Pure over the card pool and three ZONE reads — the caller resolves the zones, this owns the walk:

* **the chain, not one hop** — each step grounds out on a body already IN PLAY, or on a Basic.
* **the Rare Candy escape** — a missing Stage 1 does NOT prove a Stage 2 dead (card text, id 1079).
  No shipped deck runs Rare Candy since PR #436, so its tests feed the Candy in by fixture.
* **fail OPEN — *unreadable is not unplayable*.** Only a base PROVABLY absent from all three zones
  takes anything away. A missed slot sheds a good card, which is the wrong way to be wrong.
* the `opener` route is deliberately NOT an escape: it reaches only the ACTIVE spot during Set Up,
  before any consumer of this module runs (ADR-0081's `_route_only_at_setup` models that route).

The deck zone must be the SOUND *"not provably gone"* read, never *"seen"*. Names, not ids,
throughout: reprints share a name across ids (Beldum is both 85 and 274).
"""
from __future__ import annotations

from dataclasses import dataclass

#: The Function Tag for a card putting a Stage 2 from hand straight onto its root Basic (Rare Candy,
#: id 1079). A tag rather than a hard-coded id so the behavioural claim lives where the others do.
RARE_CANDY_TAG = "rare_candy"


@dataclass(frozen=True)
class Zones:
    """Card NAMES, by zone. ``in_play`` ends the walk; ``reachable`` still owes its own playability.
    ``rare_candy`` is TRI-STATE — ``None`` (no tag table) keeps the escape OPEN, never "no Candy"."""
    in_play: frozenset
    reachable: frozenset            # in hand, or still "not provably gone" from the deck
    rare_candy: bool | None = None


def zones(stats, *, in_play_ids=(), hand_ids=(), deck_ids=(), rare_candy_reachable=None) -> Zones:
    """``rare_candy_reachable`` needs the Function Tag table, which this module deliberately does not
    take. Pass ``None`` when there is no table to read."""
    def _names(ids) -> frozenset:
        found = set()
        for i in (ids or ()) if stats is not None else ():
            st = stats.get(i) if i is not None else None
            if st is not None and getattr(st, "name", None):
                found.add(st.name)
        return frozenset(found)

    return Zones(in_play=_names(in_play_ids),
                 reachable=_names(hand_ids) | _names(deck_ids),
                 rare_candy=None if rare_candy_reachable is None else bool(rare_candy_reachable))


def playable_from_hand(cid, *, stats, zones: Zones) -> bool:
    """True for everything that is not an Evolution, and for every Evolution whose chain still
    grounds out. False ONLY when the chain is provably broken."""
    if stats is None or cid is None:
        return True
    return _playable(stats.get(cid), stats=stats, zones=zones, seen=frozenset())


def _playable(stat, *, stats, zones: Zones, seen: frozenset) -> bool:
    """``seen`` carries the previous-stage NAMES on this path, so a malformed mutually-evolving pool
    terminates — and grounds out UNPLAYABLE, since such a chain never reaches a Basic."""
    base = getattr(stat, "evolvesFrom", None) if stat is not None else None
    if not base:
        return True                       # unknown card, Trainer/Energy, or a Basic — no claim owed
    base_ids = stats.ids_for_name(base)
    if not base_ids:
        return True                       # unreadable is not unplayable
    if base in zones.in_play:
        return True                       # the body is already down; evolve onto it
    if base not in seen and base in zones.reachable and any(
            _playable(stats.get(i), stats=stats, zones=zones, seen=seen | {base})
            for i in base_ids):
        return True
    return _rare_candy_reaches(stat, stats=stats, zones=zones, base_ids=base_ids)


def _rare_candy_reaches(stat, *, stats, zones: Zones, base_ids) -> bool:
    """With a Rare Candy reachable a Stage 2 needs only its ROOT Basic. The root is read off the
    chain and CONFIRMED Basic — the card says *"Choose 1 of your Basic Pokémon in play"*."""
    if zones.rare_candy is False or not getattr(stat, "stage2", False):
        return False
    if zones.rare_candy is None:
        return True                   # no tag table to read — no claim about the escape either way
    for s1_id in base_ids:
        s1 = stats.get(s1_id)
        root = getattr(s1, "evolvesFrom", None) if s1 is not None else None
        if root and _is_basic(root, stats) and (root in zones.in_play or root in zones.reachable):
            return True
    return False


def _is_basic(name, stats) -> bool:
    """Truthiness, not ``is None``, so this and `gate_library.is_evolution` cannot disagree about a
    card whose ``evolvesFrom`` is an empty string."""
    return any(not getattr(stats.get(i), "evolvesFrom", None) for i in stats.ids_for_name(name))
