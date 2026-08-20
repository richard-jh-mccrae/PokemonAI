"""The two coverage guarantees: a record for every deck slot, a Role for every Pokémon.

Kept apart from the per-kind fact tests because these are what the store PROMISES; a fact test
can only check the cards that happen to be present, and would pass an empty store."""
from __future__ import annotations

import pytest
from cards_helpers import (
    DECKS, ENERGY_KINDS, REPO, TRAINER_KINDS, all_deck_card_ids, deck_card_ids,
    deck_card_ids_of_kind, engine_card_defs)
from cgpy.schema import CardType

from common.cards import (
    card_store, energy_card_store, pokemon_card_store, pokemon_default_roles, trainer_card_store)
from common.cards.pokemon_roles import undeclared_pokemon_roles


@pytest.mark.parametrize("deck", DECKS)
def test_every_card_in_every_deck_has_a_record(deck):
    store = card_store()
    missing = sorted({card_id for card_id in deck_card_ids(deck) if card_id not in store})
    assert missing == [], f"{deck}: no card record for {missing}"


def test_every_pokemon_has_at_least_one_role():
    roles = pokemon_default_roles()
    unroled = sorted(card_id for card_id in pokemon_card_store() if not roles.get(card_id))
    assert unroled == [], f"Pokémon with no default Role: {unroled}"


def test_every_emitted_role_is_declared_vocabulary():
    emitted = {role for roles in pokemon_default_roles().values() for role in roles}
    assert undeclared_pokemon_roles(emitted) == []


@pytest.mark.parametrize("store,card_types", [
    (pokemon_card_store, (CardType.POKEMON,)),
    (trainer_card_store, tuple(TRAINER_KINDS)),
    (energy_card_store, tuple(ENERGY_KINDS)),
])
def test_each_store_holds_exactly_its_kind_of_deck_card(store, card_types):
    assert set(store()) == deck_card_ids_of_kind(*card_types)


def test_the_union_is_the_three_stores_with_no_overlap_and_no_stray():
    union = card_store()
    assert len(union) == sum(
        len(store()) for store in (pokemon_card_store, trainer_card_store, energy_card_store))
    assert set(union) == all_deck_card_ids()


def test_the_record_type_matches_what_the_engine_calls_the_card():
    defs, union = engine_card_defs(), card_store()
    for card_id, card in union.items():
        card_type = defs[card_id]["cardType"]
        expected = ("PokemonCard" if card_type == CardType.POKEMON
                    else "TrainerCard" if card_type in TRAINER_KINDS else "EnergyCard")
        assert type(card).__name__ == expected, card_id


def test_card_facts_is_a_leaf_module():
    """The records are the ground layer: functions read them, never the reverse. Executing the
    file alone in a fresh interpreter, with no repo on the path, proves it imports only stdlib."""
    import subprocess
    import sys
    probe = ("import importlib.util, sys; "
             "spec = importlib.util.spec_from_file_location('card_facts_probe', sys.argv[1]); "
             "module = importlib.util.module_from_spec(spec); "
             "sys.modules['card_facts_probe'] = module; spec.loader.exec_module(module); "
             "sys.exit(1 if any(name.startswith('common') for name in sys.modules) else 0)")
    path = str(REPO / "src" / "common" / "cards" / "card_facts.py")
    assert subprocess.run([sys.executable, "-c", probe, path]).returncode == 0


def test_the_union_store_is_read_only():
    with pytest.raises(TypeError):
        card_store()[1121] = None
