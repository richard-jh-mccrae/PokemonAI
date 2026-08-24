"""Bellman-only attack-lock reads over the live transition log fold."""
from __future__ import annotations

from collections.abc import Mapping


def _body_serials(body: Mapping) -> tuple[str, ...]:
    serials = []
    if body.get("serial") is not None:
        serials.append(str(int(body["serial"])))
    for card in body.get("preEvolution") or ():
        if card and card.get("serial") is not None:
            serials.append(str(int(card["serial"])))
    return tuple(serials)


def locked_attack_ids(locks: Mapping | None, body: Mapping, turn: int) -> frozenset:
    if not locks:
        return frozenset()
    barred = set()
    for serial in _body_serials(body):
        for attack_id, locked_turn in (locks.get(serial) or {}).items():
            if int(locked_turn) >= int(turn):
                barred.add(int(attack_id))
    return frozenset(barred)
