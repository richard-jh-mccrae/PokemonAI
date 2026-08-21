"""Pokémon records stay true to the engine defs, the tag table, and the clause store.

Card modules are generated data; these guards are what lets a human edit slip be caught, so every
fact class (printed stats, attacks, tags, Ability clauses, both Role layers) is asserted at its
source. Coverage of the decklists is `test_card_store.py`'s job, not this file's."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from cards_helpers import REPO, engine_attacks, engine_cards, engine_stage  # noqa: F401  fixtures

from common.cards import CardFunctions, attack_index, pokemon_card_store, pokemon_default_roles
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


def test_hand_encoded_attack_clauses_pin_to_their_printed_text():
    """Literal field-for-field pins for the hand-authored attack clauses (the Tool pattern from
    test_trainer_store.py); each expected tuple was checked against the record's printed text."""
    index = attack_index()
    assert index[141].name == "Mind Bend"                    # Munkidori: "...is now Confused."
    assert index[141].clauses == (Clause("confuse", target="opp_active"),)
    assert index[323].name == "Itchy Pollen"                 # Budew: "...can't play any Item cards"
    assert index[323].clauses == (Clause("item_lock", duration="opp_next_turn"),)
    assert index[423].name == "Trading Places"               # Dunsparce: "Switch this Pokémon..."
    assert index[423].clauses == (Clause("switch_self"),)
    assert index[965].name == "Turbo Flare"                  # Cinderace: "...up to 3 Basic Energy"
    assert index[965].clauses == (Clause("accel", amount=3, zone="deck", target="bench_only"),)
    assert index[978].name == "Wild Press"                   # Hariyama: "...70 damage to itself."
    assert index[978].clauses == (Clause("recoil", amount=70),)
    assert index[981].name == "Accelerating Stab"            # Riolu: "...can't use Accelerating Stab."
    assert index[981].clauses == (Clause("same_attack_lock", duration="next_turn"),)
    assert index[1546].name == "Tuck Tail"                   # Meowth ex: "...into your hand."
    assert index[1546].clauses == (Clause("self_return", dest="hand"),)


def test_cinderace_setup_active_ability_pins_to_its_printed_text():
    explosiveness = pokemon_card_store()[666].abilities[0]
    assert explosiveness.name == "Explosiveness"             # "...put it face down in the Active Spot."
    assert explosiveness.clauses == (Clause("setup_active", trigger="setup"),)


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
    """OUR decks' multi-prize bodies do not share a Role, and two of them never attack for the
    deck. Scoped to the shipped decks: the Brief-deck records carry archetype roles instead."""
    from cards_helpers import all_deck_card_ids

    roles = pokemon_default_roles()
    multi_prize = {card_id for card_id, card in pokemon_card_store().items()
                   if card.prize_value > 1 and card_id in all_deck_card_ids()}
    assert multi_prize == {121, 140, 678, 1031, 1071}
    # A Mega Evolution ex gives up three prizes; a plain ex two.
    assert {card.prize_value for card in map(pokemon_card_store().get, (678, 1031))} == {3}
    assert {card.prize_value for card in map(pokemon_card_store().get, (121, 140, 1071))} == {2}
    assert "primary_attacker" not in roles[140] + roles[1071]


def test_a_deck_declaration_replaces_the_default():
    resolved = resolve_pokemon_roles(pokemon_card_store(), {140: ["backup_attacker"]})
    assert resolved[140] == ("backup_attacker",)            # dragapult_ex's own reading
    assert resolved[121] == pokemon_default_roles()[121]    # everything else untouched


def test_a_declaration_for_an_unknown_card_is_ignored():
    resolved = resolve_pokemon_roles(pokemon_card_store(), {999_999: ["gust"]})
    assert 999_999 not in resolved


def test_an_empty_declaration_keeps_the_card_default():
    """A deck that says NOTHING about a body has not overridden it — [] is silence, not a veto."""
    resolved = resolve_pokemon_roles(pokemon_card_store(), {140: []})
    assert resolved[140] == pokemon_default_roles()[140]


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
