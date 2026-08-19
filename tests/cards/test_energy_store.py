"""Energy records stay true to the engine defs and the audited clause store."""
from __future__ import annotations

import json

from cards_helpers import ENERGY_KINDS, REPO, engine_cards  # noqa: F401  engine_cards is a fixture
from cgpy.schema import CardType

from common.cards import CardFunctions, energy_card_store


def test_energy_facts_match_the_engine_defs(engine_cards):
    functions = CardFunctions.load()
    for card_id, card in energy_card_store().items():
        source = engine_cards[card_id]
        skills = source.get("skills") or []
        assert (card.name, card.kind, card.provides) == (
            source["name"], ENERGY_KINDS[source["cardType"]], source["energyType"]), card_id
        assert card.text == (skills[0]["text"] if skills else ""), card_id
        assert card.tags == frozenset(functions.tags(card_id)), card_id


def test_special_energy_clauses_stay_synced_with_the_clause_store(engine_cards):
    effects = json.loads(
        (REPO / "src" / "common" / "card_effects.json").read_text(encoding="utf-8"))
    for card_id, card in energy_card_store().items():
        shipped = effects.get(str(card_id))
        if shipped is not None:
            assert [{"kind": c.kind, **c.params} for c in card.clauses] == shipped, card_id
        # A Basic Energy needs no clause: its whole behaviour is the colour it provides.
        if engine_cards[card_id]["cardType"] == CardType.SPECIAL_ENERGY:
            assert card.clauses, card_id
