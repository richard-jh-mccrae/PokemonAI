"""The unified Pokémon store stays true to the engine defs, the tag table, and the clause store.

Card modules are generated data; these guards are what lets a human edit slip be caught, so every
fact class (printed stats, attacks, tags, Ability clauses, default Roles) is asserted at its source."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.cards import CardFunctions, pokemon_card_store, pokemon_default_roles
from common.cards.card_facts import Clause

REPO = Path(__file__).resolve().parents[2]
DECKS = ("dragapult_ex", "mega_lucario", "mega_starmie")


@pytest.fixture(scope="module")
def defs():
    cards = {c["cardId"]: c for c in json.loads(
        (REPO / "src" / "cgpy" / "defs" / "card_data.json").read_text(encoding="utf-8"))}
    attacks = {a["attackId"]: a for a in json.loads(
        (REPO / "src" / "cgpy" / "defs" / "attack_data.json").read_text(encoding="utf-8"))}
    return cards, attacks


def _clause_projection(clause: Clause) -> dict:
    return {"kind": clause.kind, **clause.params}


def test_store_covers_every_pokemon_in_the_three_decks(defs):
    cards, _ = defs
    expected = set()
    for deck in DECKS:
        text = (REPO / "src" / "agents" / deck / "deck.csv").read_text(encoding="utf-8")
        expected.update(i for i in (int(line) for line in text.splitlines() if line.strip())
                        if cards[i]["cardType"] == 0)
    assert set(pokemon_card_store()) == expected


def test_card_facts_match_the_engine_defs(defs):
    cards, attacks = defs
    for card_id, card in pokemon_card_store().items():
        source = cards[card_id]
        stage = "stage2" if source["stage2"] else "stage1" if source["stage1"] else "basic"
        assert (card.name, card.hp, card.energy_type, card.stage) == (
            source["name"], source["hp"], source["energyType"], stage), card_id
        assert (card.evolves_from, card.ex, card.mega_ex, card.tera) == (
            source["evolvesFrom"], source["ex"], source["megaEx"], source["tera"]), card_id
        assert (card.weakness, card.resistance, card.retreat_cost) == (
            source["weakness"], source["resistance"], source["retreatCost"]), card_id
        assert [a.attack_id for a in card.attacks] == source["attacks"], card_id
        for attack in card.attacks:
            wire = attacks[attack.attack_id]
            assert (attack.name, attack.damage, list(attack.cost), attack.text) == (
                wire["name"].strip(), wire["damage"], wire["energies"], wire["text"]), card_id
        assert [a.name for a in card.abilities] == [
            s["name"].strip() for s in source.get("skills") or []], card_id
        assert [a.text for a in card.abilities] == [
            s["text"] for s in source.get("skills") or []], card_id


def test_tags_match_the_shipped_tag_table():
    functions = CardFunctions.load()
    for card_id, card in pokemon_card_store().items():
        assert card.tags == frozenset(functions.tags(card_id)), card_id


def test_ability_clauses_stay_synced_with_the_clause_store():
    effects = json.loads(
        (REPO / "src" / "common" / "card_effects.json").read_text(encoding="utf-8"))
    for card_id, card in pokemon_card_store().items():
        shipped = effects.get(str(card_id))
        if shipped is None or not card.abilities:
            continue
        mine = [_clause_projection(c) for a in card.abilities for c in a.clauses]
        assert mine == shipped, card_id
    # Aura Jab's rider ships under card 678 with an `on_attack` trigger; on the Attack the
    # trigger is positional, so the store carries the same clause minus that one key.
    aura_jab = next(a for a in pokemon_card_store()[678].attacks if a.attack_id == 982)
    shipped_678 = [{k: v for k, v in c.items() if k != "trigger"} for c in effects["678"]]
    assert [_clause_projection(c) for c in aura_jab.clauses] == shipped_678


def test_every_effect_text_carries_a_clause_encoding():
    for card in pokemon_card_store().values():
        for attack in card.attacks:
            assert not attack.text or attack.clauses, (card.card_id, attack.name)
        for ability in card.abilities:
            assert ability.clauses, (card.card_id, ability.name)


def test_default_roles_pin():
    roles = pokemon_default_roles()
    assert roles[305] == ("support_pokemon", "retreat_assist", "draw_engine")  # forward Dudunsparce
    assert roles[119] == ("support_pokemon", "draw_engine")                    # forward Drakloak
    assert roles[666] == ("accel_source",)                    # accel alone is not support-shaped
    assert 121 not in roles and 678 not in roles and 1031 not in roles         # plain attackers


def test_default_roles_match_the_shipped_derivation():
    try:
        from common.scouting.provider import EngineCardStatProvider
        stats = EngineCardStatProvider()
        stats.get(66)
    except Exception:
        pytest.skip("engine unavailable on this box")
    from common.pokemon_roles import general_pokemon_roles
    expected = general_pokemon_roles(pokemon_card_store().keys(), stats, CardFunctions.load())
    assert {k: tuple(v) for k, v in expected.items()} == dict(pokemon_default_roles())


def test_the_store_is_read_only():
    with pytest.raises(TypeError):
        pokemon_card_store()[666] = None
