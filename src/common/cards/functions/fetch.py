"""Pure card-class predicates for Ledger demand and offline transition windows."""
from __future__ import annotations

from ..card_facts import (
    BASIC_ENERGY, ITEM, STADIUM, STAGE1, STAGE2, SUPPORTER, TOOL, EnergyCard, PokemonCard,
    TrainerCard)


FETCH_POKEMON_TARGETS = frozenset({
    "pokemon", "basic_pokemon", "mega", "evolution", "stage1", "stage2", "tera",
    "pokemon_ex",
})
REACH, DEADNESS, WINDOW = "reach", "deadness", "window"
READINGS = frozenset({REACH, DEADNESS, WINDOW})
_CONDITIONAL_FETCH_FIELDS = ("trigger", "dig", "condition", "name_family")
_COLOUR_NARROWED_READINGS = frozenset({REACH, WINDOW})


def fetch_is_unconditional(clause) -> bool:
    return not any(clause.params.get(field) for field in _CONDITIONAL_FETCH_FIELDS)


def _pokemon_body_matches(clause, card: PokemonCard, reading: str) -> bool:
    if clause.no_rule_box and card.is_rule_box:
        return False
    if clause.no_ability and card.has_ability:
        return False
    if (reading in _COLOUR_NARROWED_READINGS and clause.energy_type is not None
            and card.energy_type != clause.energy_type):
        return False
    return clause.hp_max is None or card.hp <= clause.hp_max


def fetch_target_matches(clause, card, *, reading: str = REACH) -> bool:
    """Whether the card record belongs to a declared fetch class under a safe named reading."""
    if card is None:
        return False
    reading = reading if reading in READINGS else REACH
    if reading == REACH and not fetch_is_unconditional(clause):
        return False
    target = clause.target
    if target == "any":
        return reading == DEADNESS
    if target == "basic_energy":
        return (isinstance(card, EnergyCard) and card.kind == BASIC_ENERGY
                and (clause.energy_type is None or card.provides == clause.energy_type))
    if target == "energy":
        return (isinstance(card, EnergyCard)
                and (clause.energy_type is None or card.provides == clause.energy_type))
    if target == "supporter":
        return (reading != REACH
                and isinstance(card, TrainerCard) and card.kind == SUPPORTER)
    if target == "item":
        return isinstance(card, TrainerCard) and card.kind == ITEM
    if target == "tool":
        return isinstance(card, TrainerCard) and card.kind == TOOL
    if target == "stadium":
        return isinstance(card, TrainerCard) and card.kind == STADIUM
    if target == "trainer":
        return isinstance(card, TrainerCard)
    if target not in FETCH_POKEMON_TARGETS or not isinstance(card, PokemonCard):
        return False
    if target == "mega" and not card.mega_ex:
        return False
    if target == "evolution" and not card.evolves_from:
        return False
    if target == "basic_pokemon" and card.evolves_from:
        return False
    if target == "stage1" and card.stage != STAGE1:
        return False
    if target == "stage2" and card.stage != STAGE2:
        return False
    if target == "tera" and not card.tera:
        return False
    if target == "pokemon_ex" and not card.is_rule_box:
        return False
    return _pokemon_body_matches(clause, card, reading)


__all__ = ("WINDOW", "fetch_target_matches")
