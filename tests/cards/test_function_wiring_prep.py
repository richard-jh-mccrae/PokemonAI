"""The facts-to-functions seam, pinned before the wiring pass (ADR-0143).

Two kinds of guard: the store must EXPRESS everything the functions will read (typed ability
energy, the attack index, the derived properties), and the two silent traps must stay pinned —
each trap test asserts today's wrong-but-quiet reading, so the wiring pass is forced to flip it
rather than regress it invisibly."""
from __future__ import annotations

import pytest

from common.cards import attack_index, pokemon_card_store
from common.cards.card_facts import DARKNESS, FIGHTING
from common.cards.functions.attack_lock import fold_attack_locks
from common.cards.functions.damage import bench_reach


def test_ability_energy_requirements_are_typed():
    """The exact energy an Ability needs is a typed field, never only a prose-like string."""
    adrena = pokemon_card_store()[112].abilities[0].clause("move_damage")
    assert adrena.condition_energy_type == DARKNESS
    lunar = pokemon_card_store()[675].abilities[0].clause("draw")
    assert (lunar.rider_energy_type, lunar.rider_amount) == (FIGHTING, 1)


def test_attack_index_serves_every_attack_exactly_once():
    store = pokemon_card_store()
    expected = {a.attack_id for card in store.values() for a in card.attacks}
    assert set(attack_index()) == expected
    assert attack_index()[982] is store[678].attacks[0]      # the record, not a copy


def test_derived_properties_read_off_the_record():
    store = pokemon_card_store()
    assert store[121].is_rule_box and store[1031].is_rule_box
    assert not store[66].is_rule_box
    assert store[66].has_ability and not store[119].has_ability
    # A Mega Evolution ex gives up THREE prizes; the first pin here said 2 and the wiring
    # pass caught the drift against the engine provider (m8 hard gates flipped on it).
    assert store[1030].prize_value == 1 and store[121].prize_value == 2
    assert store[678].prize_value == 3 and store[1031].prize_value == 3


def test_clause_lookup_on_every_record_kind():
    from common.cards import card_store
    assert attack_index()[183].clause("bench_snipe").amount == 100        # Cruel Arrow
    assert attack_index()[183].clause("recoil") is None
    assert card_store()[1121].clause("fetch").cost == "discard_2"         # Ultra Ball
    assert card_store()[17].clause("energy_provide").amount_on_evolution == 3   # Ignition


def test_bench_reach_reads_the_store_attack_clauses():
    """The trap this pinned is FLIPPED: `bench_reach` reads the Attack record's bench_snipe and
    bench_spread clauses, so a store Attack now reports its printed reach."""
    assert bench_reach(attack_index()[183]) == 100
    assert bench_reach(attack_index()[1487]) == 50
    assert bench_reach(attack_index()[154]) == 60


def test_the_attack_lock_fold_reads_the_store_records():
    """The trap this pinned is FLIPPED: the fold now resolves attack ids through the store's
    `attack_index()` and reads the printed `same_attack_lock` clause off the Attack record."""
    assert attack_index()[983].clause("same_attack_lock") is not None     # Mega Brave

    logs = ({"type": 15, "serial": 7, "attackId": 983},)
    assert fold_attack_locks(None, logs, turn=4) == {"7": {"983": 6}}
