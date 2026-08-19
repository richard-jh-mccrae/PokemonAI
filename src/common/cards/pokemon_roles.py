"""Default Roles readable off a Card's own facts — the deck-independent slice of the Role system.

Mirrors `common.pokemon_roles.general_pokemon_roles` over the unified store: a pre-evolution
inherits its forward line's roles, and any support-shaped role prefixes `support_pokemon`.
Deck intent (primary_attacker, backup_attacker, staller) never lives here — it stays a
per-match overlay filled from the deck's declarations or the scouting Read."""
from __future__ import annotations

from typing import Mapping

from common.cards.card_facts import PokemonCard


def _purpose_roles(tags: frozenset) -> list[str]:
    roles = []
    if "draw" in tags or "dig" in tags or any(tag.startswith("dig:") for tag in tags):
        roles.append("draw_engine")
    if "item_lock" in tags:
        roles.append("item_locker")
    if tags & {"search", "supporter_tutor"}:
        roles.append("search_engine")
    if "switch" in tags:
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


def default_pokemon_roles(cards: Mapping[int, PokemonCard]) -> dict[int, tuple[str, ...]]:
    forward: dict[str, list[int]] = {}
    for card in cards.values():
        if card.evolves_from:
            forward.setdefault(card.evolves_from, []).append(card.card_id)
    roles: dict[int, tuple[str, ...]] = {}
    for card in cards.values():
        card_roles = _purpose_roles(card.tags)
        for forward_id in _forward_line(card.name, cards, forward):
            for role in _purpose_roles(cards[forward_id].tags):
                if role not in card_roles:
                    card_roles.append(role)
        if set(card_roles) - {"accel_source"}:
            card_roles.insert(0, "support_pokemon")
        if card_roles:
            roles[card.card_id] = tuple(card_roles)
    return roles


def _forward_line(name: str, cards: Mapping[int, PokemonCard], forward: Mapping[str, list]) -> list[int]:
    line: list[int] = []
    frontier = [name]
    while frontier:
        for forward_id in forward.get(frontier.pop(), ()):
            line.append(forward_id)
            frontier.append(cards[forward_id].name)
    return line


__all__ = ("default_pokemon_roles",)
