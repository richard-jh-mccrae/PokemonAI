"""Default Roles readable off a Card's own facts — the deck-independent slice of the Role system.

Two layers, each mirroring a shipped derivation over store facts instead of `CardStat`: the ONE
structural tier role from `derive_general_roles` (what this body IS — first match wins, listed
first) and the purpose roles from `general_pokemon_roles` (what it DOES). Every Pokémon gets a
structural role, so no body is roleless. Deck intent — which attacker is primary THIS game, which
body is the sacrificial wall — never lives here; it stays a per-match overlay beside the store."""
from __future__ import annotations

from typing import Mapping

from common.cards.card_facts import PokemonCard
from common.scouting.matchup_plan import BodyFacts, derive_general_roles


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


def _forward_index(cards: Mapping[int, PokemonCard]) -> dict[str, list]:
    forward: dict[str, list] = {}
    for card in cards.values():
        if card.evolves_from:
            forward.setdefault(card.evolves_from, []).append(card.card_id)
    return forward


def _forward_line(name: str, cards: Mapping[int, PokemonCard], forward: Mapping) -> list[int]:
    line: list[int] = []
    frontier = [name]
    while frontier:
        for forward_id in forward.get(frontier.pop(), ()):
            line.append(forward_id)
            frontier.append(cards[forward_id].name)
    return line


def _max_damage(card: PokemonCard) -> float:
    return float(max((attack.damage for attack in card.attacks), default=0))


def structural_pokemon_roles(cards: Mapping[int, PokemonCard]) -> dict[int, str]:
    """One tier role per body. The damage-boost/free-retreat/ability-fuel legs of `BodyFacts` stay
    default, so the `enabler` branch needs `CardStat` fields no store record carries."""
    forward = _forward_index(cards)
    facts = {}
    for card in cards.values():
        line = _forward_line(card.name, cards, forward)
        facts[card.card_id] = BodyFacts(
            tags=card.tags,
            prize_value=card.prize_value,
            own_damage=_max_damage(card),
            forward_damage=max((_max_damage(cards[i]) for i in line), default=0.0))
    return derive_general_roles(facts)


def purpose_pokemon_roles(cards: Mapping[int, PokemonCard]) -> dict[int, tuple[str, ...]]:
    """A pre-evolution inherits its forward line's purpose, so a Staryu reads as its Starmie does."""
    forward = _forward_index(cards)
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


def default_pokemon_roles(cards: Mapping[int, PokemonCard]) -> dict[int, tuple[str, ...]]:
    structural, purpose = structural_pokemon_roles(cards), purpose_pokemon_roles(cards)
    out: dict[int, tuple[str, ...]] = {}
    for card_id in cards:
        tier = structural.get(card_id)
        roles = ((tier,) if tier else ()) + tuple(
            role for role in purpose.get(card_id, ()) if role != tier)
        if roles:
            out[card_id] = roles
    return out


__all__ = ("default_pokemon_roles", "purpose_pokemon_roles", "structural_pokemon_roles")
