"""Inferred Pokémon Roles for cards WITHOUT a store record — opponent-side coverage."""
from __future__ import annotations


def _purpose_roles(stat, tags) -> list[str]:
    roles = []
    if "draw" in tags or "dig" in tags or any(tag.startswith("dig:") for tag in tags):
        roles.append("draw_engine")
    if "item_lock" in tags:
        roles.append("item_locker")
    if tags & {"search", "supporter_tutor"}:
        roles.append("search_engine")
    if "switch" in tags or getattr(stat, "retreatFreeGrant", None):
        roles.append("retreat_assist")
    if {"heal", "spread"} <= tags:
        roles.append("counter_mover")
    elif "heal" in tags:
        roles.append("healer")
    if "stall" in tags and "draw_engine" not in roles:
        roles.append("stall_pokemon")
    if "energy_accel" in tags:
        roles.append("accel_source")
    return roles


def general_pokemon_roles(card_ids, stats, functions=None) -> dict[int, list[str]]:
    roles: dict[int, list[str]] = {}
    for card_id in set(int(value) for value in card_ids):
        stat = stats.get(card_id) if stats is not None else None
        if stat is None or not getattr(stat, "is_pokemon", getattr(stat, "hp", 0) > 0):
            continue
        tags = frozenset(functions.tags(card_id)) if functions is not None else frozenset()
        card_roles = _purpose_roles(stat, tags)
        forward_ids = (stats.forward_card_ids(card_id)
                       if stats is not None and hasattr(stats, "forward_card_ids") else ())
        for forward_id in forward_ids:
            forward_stat = stats.get(forward_id)
            forward_tags = (frozenset(functions.tags(forward_id))
                            if functions is not None else frozenset())
            for role in _purpose_roles(forward_stat, forward_tags):
                if role not in card_roles:
                    card_roles.append(role)
        support_roles = set(card_roles) - {"accel_source"}
        if support_roles:
            card_roles.insert(0, "support_pokemon")
        if card_roles:
            roles[card_id] = card_roles
    return roles


__all__ = ("general_pokemon_roles",)
