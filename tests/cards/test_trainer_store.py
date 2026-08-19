"""The Trainer store stays true to the engine defs, the tag table, and the audited clause store."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.cards import CardFunctions, card_store, pokemon_card_store, trainer_card_store
from common.cards.card_facts import Clause

REPO = Path(__file__).resolve().parents[2]
DECKS = ("dragapult_ex", "mega_lucario", "mega_starmie")
KIND = {1: "item", 2: "tool", 3: "supporter", 4: "stadium"}


@pytest.fixture(scope="module")
def defs():
    return {c["cardId"]: c for c in json.loads(
        (REPO / "src" / "cgpy" / "defs" / "card_data.json").read_text(encoding="utf-8"))}


def test_store_covers_every_trainer_in_the_three_decks(defs):
    expected = set()
    for deck in DECKS:
        text = (REPO / "src" / "agents" / deck / "deck.csv").read_text(encoding="utf-8")
        expected.update(i for i in (int(line) for line in text.splitlines() if line.strip())
                        if defs[i]["cardType"] in KIND)
    assert set(trainer_card_store()) == expected


def test_trainer_facts_match_the_engine_defs(defs):
    for card_id, card in trainer_card_store().items():
        source = defs[card_id]
        skills = source.get("skills") or []
        assert (card.name, card.kind, card.ace_spec) == (
            source["name"], KIND[source["cardType"]], source["aceSpec"]), card_id
        assert card.text == (skills[0]["text"] if skills else ""), card_id


def test_trainer_tags_match_the_shipped_tag_table():
    functions = CardFunctions.load()
    for card_id, card in trainer_card_store().items():
        assert card.tags == frozenset(functions.tags(card_id)), card_id


def test_trainer_clauses_stay_synced_with_the_clause_store():
    effects = json.loads(
        (REPO / "src" / "common" / "card_effects.json").read_text(encoding="utf-8"))
    unsynced = []
    for card_id, card in trainer_card_store().items():
        shipped = effects.get(str(card_id))
        if shipped is None:
            continue
        if [{"kind": c.kind, **c.params} for c in card.clauses] != shipped:
            unsynced.append(card_id)
    assert unsynced == []
    # The two Tools have no audited entry; their continuous modifiers are pinned here instead.
    assert trainer_card_store()[1159].clauses == (Clause("hp_bonus", amount=100),)
    assert trainer_card_store()[1174].clauses == (Clause("retreat_reduction", amount=2),)


def test_every_trainer_carries_at_least_one_clause():
    for card in trainer_card_store().values():
        assert card.clauses, (card.card_id, card.name)


def test_the_union_store_serves_every_kind_read_only():
    from common.cards import energy_card_store
    union = card_store()
    assert len(union) == (len(pokemon_card_store()) + len(trainer_card_store())
                          + len(energy_card_store()))
    assert not (pokemon_card_store().keys() & trainer_card_store().keys())
    with pytest.raises(TypeError):
        union[1121] = None


def test_clause_open_parameters():
    clause = Clause("fetch", target="pokemon", zone="deck")
    assert (clause.kind, clause.target, clause.zone) == ("fetch", "pokemon", "deck")
    assert clause.hp_max is None                      # unset parameter reads as None
    assert clause == Clause("fetch", zone="deck", target="pokemon")
    assert clause != Clause("fetch", target="pokemon")
    with pytest.raises(AttributeError):
        clause.kind = "gust"
