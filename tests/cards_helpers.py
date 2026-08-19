"""The shipped decklists and engine defs, stated ONCE for every card-store test.

A test asserting COVERAGE and a test asserting FACTS must read the same deck list, or the pair
can agree while both are wrong about which cards the store owes."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest
from cgpy.schema import CardType

REPO = Path(__file__).resolve().parents[1]

#: Every deck the store must cover. The ONE place this list lives.
DECKS = ("dragapult_ex", "mega_lucario", "mega_starmie")

TRAINER_KINDS = {CardType.ITEM: "item", CardType.TOOL: "tool",
                 CardType.SUPPORTER: "supporter", CardType.STADIUM: "stadium"}
ENERGY_KINDS = {CardType.BASIC_ENERGY: "basic_energy",
                CardType.SPECIAL_ENERGY: "special_energy"}


@lru_cache(maxsize=1)
def engine_card_defs() -> dict:
    return {c["cardId"]: c for c in json.loads(
        (REPO / "src" / "cgpy" / "defs" / "card_data.json").read_text(encoding="utf-8"))}


@lru_cache(maxsize=1)
def engine_attack_defs() -> dict:
    return {a["attackId"]: a for a in json.loads(
        (REPO / "src" / "cgpy" / "defs" / "attack_data.json").read_text(encoding="utf-8"))}


@lru_cache(maxsize=None)
def deck_card_ids(deck: str) -> tuple[int, ...]:
    """Every slot of one decklist, duplicates included — the file is one card id per line."""
    text = (REPO / "src" / "agents" / deck / "deck.csv").read_text(encoding="utf-8")
    return tuple(int(line) for line in text.splitlines() if line.strip())


def all_deck_card_ids() -> frozenset:
    return frozenset(card_id for deck in DECKS for card_id in deck_card_ids(deck))


def deck_card_ids_of_kind(*card_types: int) -> set:
    """The deck ids the engine calls one of ``card_types`` — how each store's owed set is stated."""
    defs = engine_card_defs()
    return {card_id for card_id in all_deck_card_ids()
            if defs[card_id]["cardType"] in card_types}


def engine_stage(card: dict) -> str:
    return "stage2" if card["stage2"] else "stage1" if card["stage1"] else "basic"


@pytest.fixture(scope="session")
def engine_cards() -> dict:
    return engine_card_defs()


@pytest.fixture(scope="session")
def engine_attacks() -> dict:
    return engine_attack_defs()
