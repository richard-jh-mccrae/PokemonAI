"""A self-locking attack is board state the observation does not carry (see common.cards.functions.attack_lock)."""
from __future__ import annotations

import json

import pytest

from common.cards.functions.attack_lock import LOCK_TURN_STRIDE, fold_attack_locks, locked_attack_ids


MEGA_BRAVE, AURA_JAB = 983, 982
LOG_TURN_START, LOG_ATTACK = 2, 15


class _Stats:
    """Only Mega Brave carries the printed "can't use this next turn" clause."""

    def attack(self, attack_id):
        return type("AttackStat", (), {
            "nextTurnSameAttackLock": int(attack_id) == MEGA_BRAVE,
            "nextTurnSelfLock": False,
        })()


def _attack(serial, attack_id):
    return {"type": LOG_ATTACK, "serial": serial, "attackId": attack_id}


def _body(serial, beneath=()):
    return {"serial": serial, "preEvolution": [{"serial": s} for s in beneath]}


def test_a_self_locking_attack_bars_itself_two_global_turns_on():
    locks = fold_attack_locks({}, [_attack(86, MEGA_BRAVE)], stats=_Stats(), turn=8)

    assert locked_attack_ids(locks, _body(86), 8) == frozenset({MEGA_BRAVE})
    assert locked_attack_ids(locks, _body(86), 8 + LOCK_TURN_STRIDE) == frozenset({MEGA_BRAVE})
    assert locked_attack_ids(locks, _body(86), 11) == frozenset()


def test_an_attack_without_the_printed_clause_never_locks():
    locks = fold_attack_locks({}, [_attack(86, AURA_JAB)], stats=_Stats(), turn=8)

    assert locks == {}
    assert locked_attack_ids(locks, _body(86), 8) == frozenset()


def test_a_lock_binds_one_body_not_every_copy_of_the_card():
    locks = fold_attack_locks({}, [_attack(86, MEGA_BRAVE)], stats=_Stats(), turn=8)

    assert locked_attack_ids(locks, _body(99), 8) == frozenset()


def test_a_lock_survives_the_evolution_stacked_on_top_of_it():
    """`attack_locks` lives on the body, which keeps its identity when a card is stacked on it."""
    locks = fold_attack_locks({}, [_attack(7, MEGA_BRAVE)], stats=_Stats(), turn=8)

    assert locked_attack_ids(locks, _body(86, beneath=(7,)), 8) == frozenset({MEGA_BRAVE})


def test_a_delta_spanning_a_turn_boundary_dates_the_attack_to_its_own_turn():
    """`logs` is a delta; without the TURN_START walk the lock would be stamped two turns late."""
    spanning = [_attack(86, MEGA_BRAVE), {"type": LOG_TURN_START}, {"type": LOG_TURN_START}]

    assert fold_attack_locks({}, spanning, stats=_Stats(), turn=10) == {
        "86": {"983": 8 + LOCK_TURN_STRIDE}}


def test_the_fold_is_monotonic_across_repeated_deltas():
    once = fold_attack_locks({}, [_attack(86, MEGA_BRAVE)], stats=_Stats(), turn=8)
    twice = fold_attack_locks(once, [], stats=_Stats(), turn=10)

    assert locked_attack_ids(twice, _body(86), 10) == frozenset({MEGA_BRAVE})


def test_the_lock_map_survives_a_json_round_trip():
    """It rides inside the observation, and both providers round-trip that through JSON. An
    int-keyed map comes back stringified and every lookup silently misses."""
    locks = fold_attack_locks({}, [_attack(86, MEGA_BRAVE)], stats=_Stats(), turn=8)
    restored = json.loads(json.dumps(locks))

    assert restored == locks
    assert locked_attack_ids(restored, _body(86), 8) == frozenset({MEGA_BRAVE})


@pytest.mark.parametrize("empty", [None, {}])
def test_no_locks_bars_nothing(empty):
    assert locked_attack_ids(empty, _body(86), 8) == frozenset()
