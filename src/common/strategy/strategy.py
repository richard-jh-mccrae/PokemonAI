"""Deck declarations consumed by the live Ledger runtime."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from common.cards import card_store
from common.cards.card_facts import PokemonCard
from common.cards.pokemon_roles import POKEMON_ROLES, resolve_pokemon_roles


PrizeSelector = int | str


def _selectors(values) -> tuple[PrizeSelector, ...]:
    selectors = []
    for value in values or ():
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise TypeError("a Prize Plan selector must be a card ID or Pokemon Role")
        selector = int(value) if isinstance(value, int) else str(value)
        if isinstance(selector, int) and selector <= 0:
            raise ValueError("a Prize Plan card ID must be positive")
        if isinstance(selector, str) and selector not in POKEMON_ROLES:
            raise ValueError(f"unknown Pokemon Role {selector!r}")
        selectors.append(selector)
    if len(set(selectors)) != len(selectors):
        raise ValueError("Prize Plan selectors must be unique within each list")
    return tuple(selectors)


@dataclass(frozen=True)
class PrizePlan:
    """Sparse preservation and sacrifice preferences for the dynamic Prize Map."""

    protect: tuple[PrizeSelector, ...] = ()
    offer: tuple[PrizeSelector, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "protect", _selectors(self.protect))
        object.__setattr__(self, "offer", _selectors(self.offer))

    @property
    def identity(self) -> str:
        payload = {"protect": self.protect, "offer": self.offer}
        return hashlib.blake2b(
            json.dumps(payload, sort_keys=True).encode("utf-8"), digest_size=8).hexdigest()


class Roles(dict):
    """Own-deck Pokemon Role declarations; card records own evolution relationships."""

    def __init__(self, cards=None):
        super().__init__({int(card_id): list(card_roles)
                          for card_id, card_roles in (cards or {}).items()})

    def resolve(self, deck) -> "Roles":
        """Overlay deck declarations on the unified card records."""
        card_ids = tuple(sorted(set(int(card_id) for card_id in deck)))
        store = card_store()
        pokemon = {card_id: record for card_id in card_ids
                   if isinstance(record := store.get(card_id), PokemonCard)}
        cards = {card_id: list(card_roles) for card_id, card_roles
                 in resolve_pokemon_roles(pokemon, declared=self).items()}
        return Roles(cards)


@dataclass
class Strategy:
    """Complete deck-specific input to the live runtime."""

    name: str = ""
    roles: Roles = field(default_factory=Roles)
    starter_priority: tuple[int, ...] = ()
    params: dict = field(default_factory=dict)
    ledger_overlay: dict[str, float] = field(default_factory=dict)
    prize_plan: PrizePlan = field(default_factory=PrizePlan)

    def __post_init__(self) -> None:
        self.starter_priority = tuple(int(card_id) for card_id in self.starter_priority)
        self.ledger_overlay = {str(name): float(value)
                               for name, value in self.ledger_overlay.items()}
        if not isinstance(self.prize_plan, PrizePlan):
            raise TypeError("strategy prize_plan must be a PrizePlan")


__all__ = ["PrizePlan", "PrizeSelector", "Roles", "Strategy"]
