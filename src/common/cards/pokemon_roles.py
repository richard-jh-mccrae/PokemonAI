"""The Pokémon Role vocabulary, and how a body's Roles resolve.

One vocabulary serves both directions: the same word that says how to PLAY our body says what to
do about theirs — you promote your own primary attacker and you aim at theirs. A Role is authored
on the card from its own text (`PokemonCard.default_roles`), never inferred from prize count: a
two-prize Supporter-fetcher is a fat TARGET, which is a fact about prizes, not about its job.
A deck overrides any of it for the game it intends to play."""
from __future__ import annotations

from typing import Mapping

from common.cards.card_facts import PokemonCard

#: The closed vocabulary, and what each word claims about the body carrying it.
POKEMON_ROLES: dict[str, str] = {
    "primary_attacker": "the body this line wins with; keep it fed and alive",
    "backup_attacker": "attacks for real damage, but is not the win condition",
    "sniper": "reaches past the Active to a benched target",
    "draw_engine": "its Ability draws or digs",
    "search_engine": "its reusable in-play effect searches for setup resources",
    "healer": "its reusable in-play effect sustains damaged bodies",
    "stall_pokemon": "absorbs or denies tempo while the deck advances its plan",
    "supporter_tutor": "its Ability fetches a Supporter",
    "accel_source": "puts Energy into play faster than the one-per-turn attachment",
    "counter_mover": "relocates damage counters already on the board",
    "item_locker": "denies the opponent their Item cards",
    "retreat_assist": "moves a body out of the Active Spot without paying full Retreat",
    "gust": "drags a benched opponent into the Active Spot",
    "support_pokemon": "does its work from the bench without attacking",
}


def default_pokemon_roles(cards: Mapping[int, PokemonCard]) -> dict[int, tuple[str, ...]]:
    """Every body's authored Roles. Empty entries are dropped so a hole reads as a hole."""
    return {card_id: card.default_roles
            for card_id, card in cards.items() if card.default_roles}


def resolve_pokemon_roles(cards: Mapping[int, PokemonCard],
                          declared: Mapping[int, list] | None = None) -> dict[int, tuple[str, ...]]:
    """A deck's declaration REPLACES the card's default rather than adding to it — a deck that
    calls a body a wall means it is a wall, not a wall that is also still an attacker."""
    roles = default_pokemon_roles(cards)
    for card_id, deck_roles in (declared or {}).items():
        if int(card_id) in cards and deck_roles:
            roles[int(card_id)] = tuple(deck_roles)
    return roles


def undeclared_pokemon_roles(roles) -> list[str]:
    """Empty is the contract; a word outside the vocabulary is a typo, not a new Role."""
    return sorted({role for role in roles if role not in POKEMON_ROLES})


__all__ = ("POKEMON_ROLES", "default_pokemon_roles", "resolve_pokemon_roles",
           "undeclared_pokemon_roles")
