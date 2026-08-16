"""Which attacks a body has locked itself out of, folded from the public ATTACK log.

An attack reading "During your next turn, this Pokémon can't use <attack>" is ENFORCED by the
engine, which omits it from the menu. The observation carries no marker for it, so `BoardPotential`
would keep crediting a spent one-shot attack as reachable value and fire it a turn early.
`AttackStat.nextTurnSameAttackLock` records the printed fact; this module supplies the missing board
state, from the one signal every transition provider publishes.

Pure: no engine, no provider, no observation mutation. The fold is monotonic, so replaying an
already-folded log delta cannot retract a lock.
"""
from __future__ import annotations

from collections.abc import Mapping


LOG_TURN_START = 2
LOG_ATTACK = 15
#: Turns alternate between seats, so "your next turn" is two global turns on — the same stride the
#: engine stamps when a self-locking attack resolves.
LOCK_TURN_STRIDE = 2


def _self_locking(stats, attack_id: int) -> bool:
    lookup = getattr(stats, "attack", None) if stats is not None else None
    attack = lookup(int(attack_id)) if lookup is not None else None
    return bool(getattr(attack, "nextTurnSameAttackLock", False)
                or getattr(attack, "nextTurnSelfLock", False))


def fold_attack_locks(prior: Mapping | None, logs, *, stats, turn: int) -> dict:
    """``{"serial": {"attack_id": locked_turn}}`` after applying one log delta.

    ``turn`` is the observation's turn at the END of the delta. A delta that spans a turn boundary
    carries its own ``TURN_START`` markers, so the walk counts backwards from ``turn`` to place each
    ATTACK on the turn it actually happened rather than on the turn we read it.

    Keys are STRINGS. This map rides inside the observation, which both providers round-trip through
    JSON, and JSON has no integer keys — an int-keyed map comes back stringified and every lookup
    silently misses. Canonical string keys make the round trip a no-op instead.
    """
    locks = {str(serial): dict(rows) for serial, rows in (prior or {}).items()}
    entries = tuple(logs or ())
    starts = sum(1 for entry in entries if int(entry.get("type", -1)) == LOG_TURN_START)
    current = int(turn) - starts
    for entry in entries:
        kind = int(entry.get("type", -1))
        if kind == LOG_TURN_START:
            current += 1
            continue
        if kind != LOG_ATTACK:
            continue
        serial, attack_id = entry.get("serial"), entry.get("attackId")
        if serial is None or attack_id is None or not _self_locking(stats, attack_id):
            continue
        rows = locks.setdefault(str(int(serial)), {})
        locked = current + LOCK_TURN_STRIDE
        key = str(int(attack_id))
        rows[key] = max(int(rows.get(key, locked)), locked)
    return locks


def body_serials(body: Mapping) -> tuple[str, ...]:
    """A body's own serial plus every card beneath it — a lock predates an evolution on the stack."""
    serials = []
    if body.get("serial") is not None:
        serials.append(str(int(body["serial"])))
    for card in body.get("preEvolution") or ():
        if card and card.get("serial") is not None:
            serials.append(str(int(card["serial"])))
    return tuple(serials)


def locked_attack_ids(locks: Mapping | None, body: Mapping, turn: int) -> frozenset:
    """Attack ids this body may not use at ``turn`` or on its next attacking turn.

    A lock stamped for turn ``L`` bars the attack exactly at ``L``. Reading it as barred for every
    turn from ``L`` onward under-credits our own readiness by at most one turn — the safe direction,
    since over-credit is what buys a knockout the agent cannot actually make.
    """
    if not locks:
        return frozenset()
    barred = set()
    for serial in body_serials(body):
        for attack_id, locked_turn in (locks.get(serial) or {}).items():
            if int(locked_turn) >= int(turn):
                barred.add(int(attack_id))
    return frozenset(barred)


__all__ = ("LOCK_TURN_STRIDE", "body_serials", "fold_attack_locks", "locked_attack_ids")
