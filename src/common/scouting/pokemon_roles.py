"""Inferred Pokémon Roles for cards WITHOUT a store record — opponent-side coverage."""
from __future__ import annotations

from common.cards import card_clauses, card_store


def _purpose_roles(stat, record) -> list[str]:
    roles = list(getattr(record, "default_roles", ()) or ())
    kinds = {clause.kind for clause in card_clauses(record)} if record is not None else set()
    if "draw" in kinds and "draw_engine" not in roles:
        roles.append("draw_engine")
    if "item_lock" in kinds and "item_locker" not in roles:
        roles.append("item_locker")
    if "fetch" in kinds and "search_engine" not in roles:
        roles.append("search_engine")
    if ({"switch_self", "self_switch"} & kinds or getattr(stat, "retreatFreeGrant", None)):
        if "retreat_assist" not in roles:
            roles.append("retreat_assist")
    if {"heal", "move_damage"} <= kinds:
        roles.append("counter_mover")
    elif "heal" in kinds and "healer" not in roles:
        roles.append("healer")
    if "accel" in kinds and "accel_source" not in roles:
        roles.append("accel_source")
    return list(dict.fromkeys(roles))


def general_pokemon_roles(card_ids, stats) -> dict[int, list[str]]:
    store = card_store()
    roles: dict[int, list[str]] = {}
    for card_id in set(int(value) for value in card_ids):
        stat = stats.get(card_id) if stats is not None else None
        if stat is None or not getattr(stat, "is_pokemon", getattr(stat, "hp", 0) > 0):
            continue
        card_roles = _purpose_roles(stat, store.get(card_id))
        forward_ids = (stats.forward_card_ids(card_id)
                       if stats is not None and hasattr(stats, "forward_card_ids") else ())
        for forward_id in forward_ids:
            forward_stat = stats.get(forward_id)
            for role in _purpose_roles(forward_stat, store.get(int(forward_id))):
                if role not in card_roles:
                    card_roles.append(role)
        support_roles = set(card_roles) - {"accel_source"}
        if support_roles:
            card_roles.insert(0, "support_pokemon")
        if card_roles:
            roles[card_id] = card_roles
    return roles


__all__ = ("general_pokemon_roles",)
