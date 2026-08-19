"""The Energy store stays true to the engine defs, and the union store covers the full decklists."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.cards import CardFunctions, card_store, energy_card_store
from common.cards.card_facts import Clause

REPO = Path(__file__).resolve().parents[2]
DECKS = ("dragapult_ex", "mega_lucario", "mega_starmie")
KIND = {5: "basic_energy", 6: "special_energy"}


@pytest.fixture(scope="module")
def defs():
    return {c["cardId"]: c for c in json.loads(
        (REPO / "src" / "cgpy" / "defs" / "card_data.json").read_text(encoding="utf-8"))}


def _deck_ids() -> set[int]:
    ids: set[int] = set()
    for deck in DECKS:
        text = (REPO / "src" / "agents" / deck / "deck.csv").read_text(encoding="utf-8")
        ids.update(int(line) for line in text.splitlines() if line.strip())
    return ids


def test_store_covers_every_energy_in_the_three_decks(defs):
    expected = {i for i in _deck_ids() if defs[i]["cardType"] in KIND}
    assert set(energy_card_store()) == expected


def test_energy_facts_match_the_engine_defs(defs):
    for card_id, card in energy_card_store().items():
        source = defs[card_id]
        skills = source.get("skills") or []
        assert (card.name, card.kind, card.provides) == (
            source["name"], KIND[source["cardType"]], source["energyType"]), card_id
        assert card.text == (skills[0]["text"] if skills else ""), card_id
        assert card.tags == frozenset(CardFunctions.load().tags(card_id)), card_id


def test_ignition_clauses_stay_synced_with_the_clause_store():
    effects = json.loads(
        (REPO / "src" / "common" / "card_effects.json").read_text(encoding="utf-8"))
    mine = [{"kind": c.kind, **c.params} for c in energy_card_store()[17].clauses]
    assert mine == effects["17"]
    for card in energy_card_store().values():
        if card.kind == "special_energy":
            assert card.clauses, card.card_id


def test_the_union_store_covers_every_card_in_all_three_decklists():
    union = card_store()
    for deck in DECKS:
        text = (REPO / "src" / "agents" / deck / "deck.csv").read_text(encoding="utf-8")
        missing = [i for i in (int(line) for line in text.splitlines() if line.strip())
                   if i not in union]
        assert missing == [], deck
