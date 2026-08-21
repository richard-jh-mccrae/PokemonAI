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


BRIEFS_DIR = REPO / "src" / "common" / "scouting" / "briefs"


@lru_cache(maxsize=1)
def brief_card_ids() -> frozenset:
    """Every printing a scouting Brief names (pokemon and key_cards) — the store's second
    coverage promise since the 2026-08-20 brief-deck authoring sweep."""
    by_name: dict = {}
    for card_id, card in engine_card_defs().items():
        by_name.setdefault(card["name"], []).append(card_id)
    ids = set()
    for path in sorted(BRIEFS_DIR.glob("*.json")):
        brief = json.loads(path.read_text(encoding="utf-8"))
        for row in (brief.get("pokemon") or []) + (brief.get("key_cards") or []):
            name = row.get("card")
            if not name:
                continue
            resolved = (by_name.get(name) or by_name.get(name.replace("'", "’"))
                        or by_name.get(name.replace("’", "'")) or ())
            ids.update(resolved)
    return frozenset(ids)


def core_card_ids() -> frozenset:
    """The strict tier: decks + Brief printings, owed complete records (roles, clauses)."""
    return all_deck_card_ids() | brief_card_ids()


@lru_cache(maxsize=1)
def tail_card_ids() -> frozenset:
    """The honest-partial tier retained by the explicit store coverage manifest."""
    ids = set(json.loads((REPO / "tools" / "meta_tracker" / "store_card_ids.json")
                         .read_text(encoding="utf-8")))
    return frozenset(ids - core_card_ids())


def all_covered_card_ids() -> frozenset:
    return core_card_ids() | tail_card_ids()


def deck_card_ids_of_kind(*card_types: int) -> set:
    """The covered ids the engine calls one of ``card_types`` — each store's owed set."""
    defs = engine_card_defs()
    return {card_id for card_id in all_covered_card_ids()
            if defs[card_id]["cardType"] in card_types}


def engine_stage(card: dict) -> str:
    return "stage2" if card["stage2"] else "stage1" if card["stage1"] else "basic"


@pytest.fixture(scope="session")
def engine_cards() -> dict:
    return engine_card_defs()


@pytest.fixture(scope="session")
def engine_attacks() -> dict:
    return engine_attack_defs()
