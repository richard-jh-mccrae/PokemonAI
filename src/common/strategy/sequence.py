"""ORACLE: Horizon-2 attack sequence — ADR-0061. A locking attack's value includes its FORCED
follow-up.

The two locks are structurally different. A SAME-ATTACK lock costs ZERO damage over two turns
(270 + 130 == 130 + 270 — you could never repeat it anyway); a FULL lock costs an entire turn of
offense. The retired flat `_LOCK_COST` charged one constant for both.

Multi-turn reasoning WITHOUT a search: when an attack locks, next turn's option set is forced and
known, so the sequence is evaluated rather than explored.
"""
from __future__ import annotations


def followup_damage(attack_id, *, affordable: dict, full_lock: bool,
                    same_attack_lock: bool) -> int:
    """Damage this Pokémon can still deal NEXT turn, having used ``attack_id`` this turn, over the
    ``affordable`` menu. 0 when nothing is left — the CALLER must still let a lone chip beat passing."""
    if full_lock:
        return 0                                     # "can't use attacks": the turn is simply gone
    if same_attack_lock:
        return max((d for a, d in affordable.items() if a != attack_id), default=0)
    return max(affordable.values(), default=0)       # no lock: the whole menu is still there


def sequence_damage(this_turn: int | float, followup: int | float, *, weight: float) -> float:
    """Two-turn damage: this attack now plus ``weight`` × the forced follow-up (``weight`` < 1, so a
    tie is won front-loaded). Pass ``followup=0`` when `active_doomed` — every lock is then free."""
    return this_turn + weight * followup
