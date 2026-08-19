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
from common.cards.pokemon_roles import resolve_pokemon_roles


def _clause_projection(clause: Clause) -> dict:
    return {"kind": clause.kind, **clause.params}


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
    assert roles[121] == ("primary_attacker", "sniper")     # Phantom Dive reaches their Bench
    assert roles[1030] == ("primary_attacker",)             # a Staryu is the Starmie line
    assert roles[676] == ("backup_attacker",)
    assert roles[1071] == ("supporter_tutor",)              # 2 prizes, but that is not its job
    assert roles[140] == ("draw_engine",)                   # likewise


def test_no_role_is_assigned_by_prize_count():
    """The two-prize bodies do not share a Role, and two of them never attack for the deck."""
    roles = pokemon_default_roles()
    two_prize = {card_id for card_id, card in pokemon_card_store().items()
                 if card.prize_value == 2}
    assert two_prize == {121, 140, 678, 1031, 1071}
    assert "primary_attacker" not in roles[140] + roles[1071]


def test_a_deck_declaration_replaces_the_default():
    resolved = resolve_pokemon_roles(pokemon_card_store(), {140: ["backup_attacker"]})
    assert resolved[140] == ("backup_attacker",)            # dragapult_ex's own reading
    assert resolved[121] == pokemon_default_roles()[121]    # everything else untouched


def test_synergy_is_symmetric_and_names_real_cards():
    store = pokemon_card_store()
    by_name = {card.name: card for card in store.values()}
    for card in store.values():
        for partner_name in card.synergy:
            partner = by_name.get(partner_name)
            assert partner is not None, (card.card_id, partner_name)
            assert card.name in partner.synergy, f"{card.name}/{partner_name} is one-way"
    assert store[675].synergy == ("Solrock",) and store[676].synergy == ("Lunatone",)


def test_a_card_whose_text_names_another_card_declares_the_synergy():
    """Solrock's `requires_bench` clause and Lunatone's condition are the printed halves of the
    same pairing; the authored field must not disagree with them."""
    store = pokemon_card_store()
    named = {clause.name for card in store.values() for attack in card.attacks
             for clause in attack.clauses if clause.name}
    for partner_name in named:
        holders = [c for c in store.values() if any(
            cl.name == partner_name for a in c.attacks for cl in a.clauses)]
        for holder in holders:
            assert partner_name in holder.synergy, (holder.card_id, partner_name)


def test_the_store_is_read_only():
    with pytest.raises(TypeError):
        pokemon_card_store()[666] = None
