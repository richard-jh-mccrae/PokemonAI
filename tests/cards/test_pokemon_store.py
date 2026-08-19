"""Pokémon records stay true to the engine defs, the tag table, and the clause store.

Card modules are generated data; these guards are what lets a human edit slip be caught, so every
fact class (printed stats, attacks, tags, Ability clauses, both Role layers) is asserted at its
source. Coverage of the decklists is `test_card_store.py`'s job, not this file's."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from cards_helpers import REPO, engine_attacks, engine_cards, engine_stage  # noqa: F401  fixtures

from common.cards import CardFunctions, pokemon_card_store, pokemon_default_roles
from common.cards.card_facts import Clause
from common.cards.pokemon_roles import purpose_pokemon_roles, structural_pokemon_roles


def _clause_projection(clause: Clause) -> dict:
    return {"kind": clause.kind, **clause.params}


@pytest.fixture(scope="module")
def stats():
    """The engine-backed provider the store's derivations mirror; absent on a DLL-less box."""
    try:
        from common.scouting.provider import EngineCardStatProvider
        provider = EngineCardStatProvider()
        provider.get(66)
    except Exception:
        pytest.skip("engine unavailable on this box")
    return provider


def test_card_facts_match_the_engine_defs(engine_cards, engine_attacks):
    for card_id, card in pokemon_card_store().items():
        source = engine_cards[card_id]
        assert (card.name, card.hp, card.energy_type, card.stage) == (
            source["name"], source["hp"], source["energyType"], engine_stage(source)), card_id
        assert (card.evolves_from, card.ex, card.mega_ex, card.tera) == (
            source["evolvesFrom"], source["ex"], source["megaEx"], source["tera"]), card_id
        assert (card.weakness, card.resistance, card.retreat_cost) == (
            source["weakness"], source["resistance"], source["retreatCost"]), card_id
        assert [a.attack_id for a in card.attacks] == source["attacks"], card_id
        for attack in card.attacks:
            wire = engine_attacks[attack.attack_id]
            assert (attack.name, attack.damage, list(attack.cost), attack.text) == (
                wire["name"].strip(), wire["damage"], wire["energies"], wire["text"]), card_id
        assert [(a.name, a.text) for a in card.abilities] == [
            (s["name"].strip(), s["text"]) for s in source.get("skills") or []], card_id


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
    assert roles[121] == ("primary_attacker",)                       # a 2-prize body
    assert roles[1030] == ("fragile_preevo",)                        # its line attacks forward
    assert roles[674] == ("backup_attacker",)                        # attacks, nothing forward
    assert roles[305] == ("fragile_preevo", "support_pokemon", "retreat_assist", "draw_engine")
    assert roles[666] == ("backup_attacker", "accel_source")   # accel alone is not support-shaped


def test_the_structural_layer_matches_the_shipped_ladder(stats):
    """Feeding `derive_general_roles` from store records must rule exactly as `CardStat` does."""
    from common.scouting.matchup_plan import BodyFacts, derive_general_roles
    functions = CardFunctions.load()
    expected = derive_general_roles({
        card_id: BodyFacts(
            tags=frozenset(functions.tags(card_id)),
            prize_value=int(stats.get(card_id).prize_value),
            own_damage=float(getattr(stats.get(card_id), "maxDamage", 0) or 0),
            forward_damage=float(stats.forward_max_damage(card_id) or 0))
        for card_id in pokemon_card_store()})
    assert structural_pokemon_roles(pokemon_card_store()) == expected


def test_the_purpose_layer_matches_the_shipped_derivation(stats):
    from common.pokemon_roles import general_pokemon_roles
    expected = general_pokemon_roles(pokemon_card_store().keys(), stats, CardFunctions.load())
    assert {k: tuple(v) for k, v in expected.items()} == purpose_pokemon_roles(
        pokemon_card_store())


def test_the_store_is_read_only():
    with pytest.raises(TypeError):
        pokemon_card_store()[666] = None
