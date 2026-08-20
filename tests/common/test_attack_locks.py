"""A self-locking attack is board state the observation does not carry (see common.cards.functions.attack_lock)."""
from __future__ import annotations

import json

import pytest

from common.cards.functions.attack_lock import (
    LOCK_TURN_STRIDE, carry_attack_locks, fold_attack_locks, locked_attack_ids)


#: Real store attacks: only Mega Brave (983) prints the "can't use this next turn" clause;
#: Aura Jab (982) does not. The fold reads both straight off `attack_index()`.
MEGA_BRAVE, AURA_JAB = 983, 982
LOG_TURN_START, LOG_ATTACK = 2, 15


def _attack(serial, attack_id):
    return {"type": LOG_ATTACK, "serial": serial, "attackId": attack_id}


def _body(serial, beneath=()):
    return {"serial": serial, "preEvolution": [{"serial": s} for s in beneath]}


def test_a_self_locking_attack_bars_itself_two_global_turns_on():
    locks = fold_attack_locks({}, [_attack(86, MEGA_BRAVE)], turn=8)

    assert locked_attack_ids(locks, _body(86), 8) == frozenset({MEGA_BRAVE})
    assert locked_attack_ids(locks, _body(86), 8 + LOCK_TURN_STRIDE) == frozenset({MEGA_BRAVE})
    assert locked_attack_ids(locks, _body(86), 11) == frozenset()


def test_an_attack_without_the_printed_clause_never_locks():
    locks = fold_attack_locks({}, [_attack(86, AURA_JAB)], turn=8)

    assert locks == {}
    assert locked_attack_ids(locks, _body(86), 8) == frozenset()


def test_a_lock_binds_one_body_not_every_copy_of_the_card():
    locks = fold_attack_locks({}, [_attack(86, MEGA_BRAVE)], turn=8)

    assert locked_attack_ids(locks, _body(99), 8) == frozenset()


def test_a_lock_survives_the_evolution_stacked_on_top_of_it():
    """`attack_locks` lives on the body, which keeps its identity when a card is stacked on it."""
    locks = fold_attack_locks({}, [_attack(7, MEGA_BRAVE)], turn=8)

    assert locked_attack_ids(locks, _body(86, beneath=(7,)), 8) == frozenset({MEGA_BRAVE})


def test_a_delta_spanning_a_turn_boundary_dates_the_attack_to_its_own_turn():
    """`logs` is a delta; without the TURN_START walk the lock would be stamped two turns late."""
    spanning = [_attack(86, MEGA_BRAVE), {"type": LOG_TURN_START}, {"type": LOG_TURN_START}]

    assert fold_attack_locks({}, spanning, turn=10) == {
        "86": {"983": 8 + LOCK_TURN_STRIDE}}


def test_the_fold_is_monotonic_across_repeated_deltas():
    once = fold_attack_locks({}, [_attack(86, MEGA_BRAVE)], turn=8)
    twice = fold_attack_locks(once, [], turn=10)

    assert locked_attack_ids(twice, _body(86), 10) == frozenset({MEGA_BRAVE})


def test_the_lock_map_survives_a_json_round_trip():
    """It rides inside the observation, and both providers round-trip that through JSON. An
    int-keyed map comes back stringified and every lookup silently misses."""
    locks = fold_attack_locks({}, [_attack(86, MEGA_BRAVE)], turn=8)
    restored = json.loads(json.dumps(locks))

    assert restored == locks
    assert locked_attack_ids(restored, _body(86), 8) == frozenset({MEGA_BRAVE})


@pytest.mark.parametrize("empty", [None, {}])
def test_no_locks_bars_nothing(empty):
    assert locked_attack_ids(empty, _body(86), 8) == frozenset()


def test_carrying_an_empty_ledger_leaves_the_observation_key_absent():
    """The key is part of state identity: an empty `{}` present here would never match the
    absent key on the live observation the next turn arrives as."""
    observation = {"logs": [_attack(86, AURA_JAB)], "current": {"turn": 8}}
    carry_attack_locks(None, observation)
    assert "attack_locks" not in observation


def test_carrying_a_lock_writes_the_folded_ledger_onto_the_observation():
    observation = {"logs": [_attack(86, MEGA_BRAVE)], "current": {"turn": 8}}
    carry_attack_locks({}, observation)
    assert observation["attack_locks"] == {"86": {"983": 8 + LOCK_TURN_STRIDE}}


def test_a_parent_ledger_survives_a_step_with_no_new_attacks():
    observation = {"logs": [], "current": {"turn": 9}}
    carry_attack_locks({"attack_locks": {"86": {"983": 10}}}, observation)
    assert observation["attack_locks"] == {"86": {"983": 10}}


def test_refolding_the_same_nonempty_delta_never_retracts_a_lock():
    delta = [_attack(86, MEGA_BRAVE)]
    once = fold_attack_locks({}, delta, turn=8)
    assert fold_attack_locks(once, delta, turn=8) == once                # idempotent
    # A replay dated later can only push the lock FORWARD (10 -> 12), never retract it.
    assert fold_attack_locks(once, delta, turn=10) == {"86": {"983": 12}}


def test_a_log_row_missing_its_serial_or_attack_id_is_skipped_not_crashed():
    rows = [{"type": LOG_ATTACK, "serial": None, "attackId": MEGA_BRAVE},
            {"type": LOG_ATTACK, "serial": 86, "attackId": None}]
    assert fold_attack_locks({}, rows, turn=8) == {}


def test_a_body_with_no_serial_is_barred_from_nothing():
    locks = fold_attack_locks({}, [_attack(86, MEGA_BRAVE)], turn=8)
    assert locked_attack_ids(locks, {"serial": None, "preEvolution": None}, 8) == frozenset()
