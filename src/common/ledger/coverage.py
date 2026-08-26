from __future__ import annotations

from dataclasses import fields

from common.cards import FUNCTION_CATALOG
from common.observation.nodes import Body, Card, Looking, SelectPrompt, Side, Turn
from common.observation.state import ObservationState


OBSERVATION_FIELD_OWNERS = {
    ObservationState: {
        "seat": "identity", "me": "value", "them": "value", "turn": "value",
        "stadium": "value", "looking": "legal", "select": "legal",
        "decklist": "belief", "deck_counts": "value", "knowledge": "belief",
        "legal_actions": "legal", "events": "value", "_pieces": "identity",
    },
    Side: {
        "active": "value", "active_hidden": "belief", "bench": "value",
        "bench_max": "value", "deck_count": "value", "hand": "value",
        "hand_count": "value", "discard": "value", "prize_count": "value",
        "poisoned": "value", "burned": "value", "asleep": "value",
        "paralyzed": "value", "confused": "value",
    },
    Body: {
        "card": "value", "hp": "value", "max_hp": "value",
        "appeared_this_turn": "value", "energies": "value",
        "energy_cards": "value", "tools": "value", "pre_evolution": "value",
        "digest": "identity",
    },
    Card: {"card_id": "value", "serial": "identity", "owner": "value"},
    Turn: {
        "number": "value", "first_player": "value", "supporter_played": "legal",
        "stadium_played": "legal", "energy_attached": "legal",
        "retreated": "legal", "result": "value",
    },
    Looking: {"count": "legal", "cards": "legal"},
    SelectPrompt: {
        "type": "legal", "context": "legal", "min_count": "legal",
        "max_count": "legal", "remain_damage_counter": "legal",
        "remain_energy_cost": "legal", "options": "legal", "deck": "legal",
        "context_card": "legal", "effect": "legal",
    },
}

DIRECT_CAPABILITY_CLAUSES = frozenset({
    "accel", "ability_suppression", "attack_lock", "bench_snipe", "bench_spread",
    "confuse", "damage_reduction", "draw", "energy_recur", "fetch", "heal",
    "ignores_effects", "ignores_wr", "item_lock", "ko", "move_damage",
    "move_energy", "no_retreat", "prevent_damage", "requires_bench",
    "retreat_lock",
})
SUCCESSOR_CLAUSES = frozenset(FUNCTION_CATALOG.kinds) - DIRECT_CAPABILITY_CLAUSES


def unowned_observation_fields() -> tuple[str, ...]:
    missing = []
    for node, owners in OBSERVATION_FIELD_OWNERS.items():
        missing.extend(f"{node.__name__}.{field.name}" for field in fields(node)
                       if field.name not in owners)
    return tuple(sorted(missing))


def unowned_clause_kinds() -> tuple[str, ...]:
    return tuple(sorted(set(FUNCTION_CATALOG.kinds)
                        - DIRECT_CAPABILITY_CLAUSES - SUCCESSOR_CLAUSES))


__all__ = (
    "DIRECT_CAPABILITY_CLAUSES", "OBSERVATION_FIELD_OWNERS", "SUCCESSOR_CLAUSES",
    "unowned_clause_kinds", "unowned_observation_fields",
)
