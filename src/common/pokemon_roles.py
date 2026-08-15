"""Deck-independent Pokémon Roles shared by own-deck and opponent resolution."""
from __future__ import annotations


_SUPPORT_TAGS = frozenset({
    "dig", "draw", "heal", "item_lock", "search", "stall", "supporter_tutor", "switch",
})
_SUPPORT_NAMES = frozenset({"Dunsparce"})


def general_pokemon_roles(card_ids, stats, functions=None) -> dict[int, list[str]]:
    roles: dict[int, list[str]] = {}
    for card_id in set(int(value) for value in card_ids):
        stat = stats.get(card_id) if stats is not None else None
        if stat is None or not getattr(stat, "is_pokemon", getattr(stat, "hp", 0) > 0):
            continue
        tags = frozenset(functions.tags(card_id)) if functions is not None else frozenset()
        card_roles = roles.setdefault(card_id, [])
        if (tags & _SUPPORT_TAGS or getattr(stat, "name", "") in _SUPPORT_NAMES
                or getattr(stat, "retreatFreeGrant", None)):
            card_roles.append("support_pokemon")
        if "energy_accel" in tags:
            card_roles.append("accel_source")
        if {"heal", "spread"} <= tags:
            card_roles.append("counter_mover")
        if not card_roles:
            roles.pop(card_id)
    return roles


__all__ = ("general_pokemon_roles",)
