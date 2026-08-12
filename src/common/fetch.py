"""Pure card-class predicates for Bellman reveal windows."""
from __future__ import annotations


FETCH_POKEMON_TARGETS = frozenset({
    "pokemon", "basic_pokemon", "mega", "evolution", "stage1", "stage2", "tera",
    "pokemon_ex",
})
REACH, DEADNESS, WINDOW = "reach", "deadness", "window"
READINGS = frozenset({REACH, DEADNESS, WINDOW})
_CONDITIONAL_FETCH_FIELDS = ("trigger", "dig", "condition", "name_family")
_COLOUR_NARROWED_READINGS = frozenset({REACH, WINDOW})


def fetch_is_unconditional(clause: dict) -> bool:
    return not any(clause.get(field) for field in _CONDITIONAL_FETCH_FIELDS)


def _pokemon_body_matches(clause: dict, stat, reading: str) -> bool:
    if clause.get("no_rule_box") and getattr(stat, "is_ex_body", False):
        return False
    if clause.get("no_ability") and getattr(stat, "hasAbility", False):
        return False
    energy_type = clause.get("energy_type")
    if (reading in _COLOUR_NARROWED_READINGS and energy_type is not None
            and getattr(stat, "energyType", None) != energy_type):
        return False
    hp_max = clause.get("hp_max")
    return hp_max is None or getattr(stat, "hp", 0) <= hp_max


def fetch_target_matches(clause: dict, stat, *, reading: str = REACH) -> bool:
    """Whether ``stat`` belongs to a declared fetch class under a safe named reading."""
    if stat is None:
        return False
    reading = reading if reading in READINGS else REACH
    if reading == REACH and not fetch_is_unconditional(clause):
        return False
    target = clause.get("target")
    energy_type = clause.get("energy_type")
    if target == "any":
        return reading == DEADNESS
    if target == "basic_energy":
        return stat.is_basic_energy and (
            energy_type is None or getattr(stat, "energyType", None) == energy_type)
    if target == "energy":
        return stat.is_energy and (
            energy_type is None or getattr(stat, "energyType", None) == energy_type)
    if target == "supporter":
        return reading != REACH and bool(getattr(stat, "is_supporter", False))
    if target == "item":
        return bool(getattr(stat, "is_item", False))
    if target == "tool":
        return bool(getattr(stat, "is_tool", False))
    if target == "stadium":
        return bool(getattr(stat, "is_stadium", False))
    if target == "trainer":
        return not stat.is_pokemon and not stat.is_energy
    if target not in FETCH_POKEMON_TARGETS or not stat.is_pokemon:
        return False
    if target == "mega" and not getattr(stat, "megaEx", False):
        return False
    if target == "evolution" and not getattr(stat, "evolvesFrom", None):
        return False
    if target == "basic_pokemon" and getattr(stat, "evolvesFrom", None):
        return False
    if target == "stage1" and getattr(stat, "stage", None) != "stage1":
        return False
    if target == "stage2" and getattr(stat, "stage", None) != "stage2":
        return False
    if target == "tera" and not getattr(stat, "tera", False):
        return False
    if target == "pokemon_ex" and not getattr(stat, "is_ex_body", False):
        return False
    return _pokemon_body_matches(clause, stat, reading)


__all__ = ("WINDOW", "fetch_target_matches")
