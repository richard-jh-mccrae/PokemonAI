"""Which attacks a body has locked itself out of, folded from the public ATTACK log.

An attack reading "During your next turn, this Pokémon can't use <attack>" is ENFORCED by the
engine, which omits it from the menu. The observation carries no marker for it, so `BoardPotential`
would keep crediting a spent one-shot attack as reachable value and fire it a turn early. The
Attack record's `same_attack_lock` clause records the printed fact; this module supplies the
missing board state, from the one signal every transition provider publishes.

No engine, no provider, no observation mutation; attack ids resolve through the store's
`attack_index()` unless a caller injects its own records. The fold is monotonic, so replaying an
already-folded log delta cannot retract a lock.
"""
from __future__ import annotations

from collections.abc import Mapping


LOG_TURN_START = 2
LOG_ATTACK = 15
#: Turns alternate between seats, so "your next turn" is two global turns on — the same stride the
#: engine stamps when a self-locking attack resolves.
LOCK_TURN_STRIDE = 2


def _attack_records(attacks) -> Mapping:
    if attacks is not None:
        return attacks
    from .. import attack_index
    return attack_index()


def _self_locking(attack) -> bool:
    return attack is not None and attack.clause("same_attack_lock") is not None


def fold_attack_locks(prior: Mapping | None, logs, *, turn: int, attacks=None) -> dict:
    """``{"serial": {"attack_id": locked_turn}}`` after one log delta ending at ``turn``."""
    # Walk back from `turn` over the delta's own TURN_START markers to date each ATTACK. Keys are
    # STRINGS: both providers round-trip this map through JSON, which returns int keys stringified.
    records = _attack_records(attacks)
    locks = {str(serial): dict(rows) for serial, rows in (prior or {}).items()}
    # A malformed row (None, non-dict, non-numeric field) is skipped, never fatal: losing one
    # lock record is conservative; killing the decision that reads the log is not.
    entries = tuple(entry for entry in (logs or ()) if isinstance(entry, dict))
    starts = sum(1 for entry in entries if _int_or(entry.get("type"), -1) == LOG_TURN_START)
    current = int(turn) - starts
    for entry in entries:
        kind = _int_or(entry.get("type"), -1)
        if kind == LOG_TURN_START:
            current += 1
            continue
        if kind != LOG_ATTACK:
            continue
        serial = _int_or(entry.get("serial"), None)
        attack_id = _int_or(entry.get("attackId"), None)
        if serial is None or attack_id is None \
                or not _self_locking(records.get(attack_id)):
            continue
        rows = locks.setdefault(str(serial), {})
        locked = current + LOCK_TURN_STRIDE
        key = str(attack_id)
        rows[key] = max(_int_or(rows.get(key), locked), locked)
    return locks


def _int_or(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def body_serials(body: Mapping) -> tuple[str, ...]:
    """A body's serial plus every card beneath it: a lock predates an evolution on the stack."""
    serials = []
    if body.get("serial") is not None:
        serials.append(str(int(body["serial"])))
    for card in body.get("preEvolution") or ():
        if card and card.get("serial") is not None:
            serials.append(str(int(card["serial"])))
    return tuple(serials)


def locked_attack_ids(locks: Mapping | None, body: Mapping, turn: int) -> frozenset:
    """Attack ids this body may not use at ``turn``, on either seat."""
    # A lock stamped for L bars exactly L; reading L-onward as barred can under-credit our own
    # readiness by a turn, which is the safe side — over-credit buys a knockout we cannot make.
    if not locks:
        return frozenset()
    barred = set()
    for serial in body_serials(body):
        for attack_id, locked_turn in (locks.get(serial) or {}).items():
            if int(locked_turn) >= int(turn):
                barred.add(int(attack_id))
    return frozenset(barred)


__all__ = ("LOCK_TURN_STRIDE", "body_serials", "fold_attack_locks", "locked_attack_ids")
