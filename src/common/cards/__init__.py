"""Card knowledge under one roof: the `CardFunctions` tag table and the unified card store.

`card_store()` builds `{card_id: PokemonCard | TrainerCard | EnergyCard}` once per process from
the modules under `pokemon_cards/`, `trainer_cards/` and `energy_cards/`;
`pokemon_default_roles()` derives the deck-independent Roles beside it."""
from __future__ import annotations

import importlib
import pkgutil
from functools import lru_cache
from types import MappingProxyType
from typing import Mapping

from common.cards.card_facts import (
    Ability, Attack, Clause, EnergyCard, PokemonCard, TrainerCard)
from common.cards.tags import CardFunctions
from common.cards.pokemon_roles import default_pokemon_roles


def _load_package(package) -> dict:
    store: dict = {}
    for module_info in pkgutil.iter_modules(package.__path__):
        card = importlib.import_module(f"{package.__name__}.{module_info.name}").CARD
        if card.card_id in store:
            raise ValueError(f"duplicate card id {card.card_id} in {package.__name__}")
        store[card.card_id] = card
    return store


@lru_cache(maxsize=1)
def pokemon_card_store() -> Mapping[int, PokemonCard]:
    from common.cards import pokemon_cards as package
    return MappingProxyType(_load_package(package))


@lru_cache(maxsize=1)
def trainer_card_store() -> Mapping[int, TrainerCard]:
    from common.cards import trainer_cards as package
    return MappingProxyType(_load_package(package))


@lru_cache(maxsize=1)
def energy_card_store() -> Mapping[int, EnergyCard]:
    from common.cards import energy_cards as package
    return MappingProxyType(_load_package(package))


@lru_cache(maxsize=1)
def card_store() -> Mapping[int, PokemonCard | TrainerCard | EnergyCard]:
    stores = (pokemon_card_store(), trainer_card_store(), energy_card_store())
    union: dict = {}
    for store in stores:
        overlap = union.keys() & store.keys()
        if overlap:
            raise ValueError(f"card ids in more than one store: {sorted(overlap)}")
        union.update(store)
    return MappingProxyType(union)


@lru_cache(maxsize=1)
def pokemon_default_roles() -> Mapping[int, tuple[str, ...]]:
    return MappingProxyType(default_pokemon_roles(pokemon_card_store()))


__all__ = ("Ability", "Attack", "CardFunctions", "Clause", "EnergyCard", "PokemonCard",
           "TrainerCard", "card_store", "energy_card_store", "pokemon_card_store",
           "pokemon_default_roles", "trainer_card_store")
