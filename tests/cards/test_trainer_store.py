"""Trainer records stay true to the engine defs, the tag table, and the audited clause store."""
from __future__ import annotations

import json

import pytest
from cards_helpers import REPO, TRAINER_KINDS, engine_cards  # noqa: F401  engine_cards is a fixture

from common.cards import CardFunctions, trainer_card_store
from common.cards.card_facts import Clause


def test_trainer_facts_match_the_engine_defs(engine_cards):
    for card_id, card in trainer_card_store().items():
        source = engine_cards[card_id]
        skills = source.get("skills") or []
        assert (card.name, card.kind, card.ace_spec) == (
            source["name"], TRAINER_KINDS[source["cardType"]], source["aceSpec"]), card_id
        assert card.text == (skills[0]["text"] if skills else ""), card_id


def test_trainer_tags_match_the_shipped_tag_table():
    functions = CardFunctions.load()
    for card_id, card in trainer_card_store().items():
        assert card.tags == frozenset(functions.tags(card_id)), card_id


def test_trainer_clauses_stay_synced_with_the_clause_store():
    effects = json.loads(
        (REPO / "src" / "common" / "card_effects.json").read_text(encoding="utf-8"))
    unsynced = [card_id for card_id, card in trainer_card_store().items()
                if effects.get(str(card_id)) is not None
                and [{"kind": c.kind, **c.params} for c in card.clauses] != effects[str(card_id)]]
    assert unsynced == []
    # The two Tools have no audited entry; their continuous modifiers are pinned here instead.
    assert trainer_card_store()[1159].clauses == (Clause("hp_bonus", amount=100),)
    assert trainer_card_store()[1174].clauses == (Clause("retreat_reduction", amount=2),)


def test_every_trainer_carries_at_least_one_clause():
    for card in trainer_card_store().values():
        assert card.clauses, (card.card_id, card.name)


def test_equal_clauses_hash_equal_even_across_numeric_types():
    """1 == True in Python, so two clauses differing only that way are equal — and equal
    objects must hash equal or set/dict lookups silently split them."""
    a, b = Clause("draw", amount=1), Clause("draw", amount=True)
    assert a == b and hash(a) == hash(b)
    assert len({a, b}) == 1
    c = Clause("fetch", target="pokemon", filter=["Solrock", "Lunatone"])
    assert hash(c) == hash(Clause("fetch", target="pokemon", filter=["Solrock", "Lunatone"]))


def test_clause_open_parameters():
    clause = Clause("fetch", target="pokemon", zone="deck")
    assert (clause.kind, clause.target, clause.zone) == ("fetch", "pokemon", "deck")
    assert clause.hp_max is None                      # unset parameter reads as None
    assert clause == Clause("fetch", zone="deck", target="pokemon")
    assert clause != Clause("fetch", target="pokemon")
    with pytest.raises(AttributeError):
        clause.kind = "gust"
