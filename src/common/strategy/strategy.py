"""Deck declarations consumed by the Bellman runtime.

Decks provide Roles, Strategies, relationships, prize routes, upward-only Worth,
and an optional observable-potential extension. Action policy does not belong here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from common.cards import card_store
from common.cards.card_facts import PokemonCard
from common.cards.pokemon_roles import resolve_pokemon_roles

STANDARD_PRIZES_TO_WIN = 6


@dataclass(frozen=True)
class Ready:
    """Optional declared Energy threshold for an evolution-line payoff."""

    energy: int | None = None


@dataclass(frozen=True)
class Line:
    """Normalized evolution path derived from :class:`Roles`."""

    path: tuple[int, ...]
    payoff: int
    role: str = "primary_attacker"
    ready: Ready = Ready()


@dataclass(frozen=True)
class PrizePlan:
    """Preferred order(s) in which the opponent takes our Pokémon prizes."""

    routes: tuple[tuple[int, ...], ...]
    prizes_to_win: int = STANDARD_PRIZES_TO_WIN

    def __post_init__(self) -> None:
        routes = tuple(tuple(int(card_id) for card_id in route) for route in self.routes)
        if not routes or any(not route for route in routes):
            raise ValueError("a prize plan requires at least one non-empty route")
        if int(self.prizes_to_win) <= 0:
            raise ValueError("prizes_to_win must be positive")
        object.__setattr__(self, "routes", routes)
        object.__setattr__(self, "prizes_to_win", int(self.prizes_to_win))


class Roles(dict):
    """Pokémon doctrine roles plus ``source -> target`` evolution relationships."""

    _LINE_ROLE_PRIORITY = ("primary_attacker", "backup_attacker")

    def __init__(self, cards=None, *, evolves=None, ready=None):
        super().__init__({int(card_id): list(card_roles)
                          for card_id, card_roles in (cards or {}).items()})
        self.evolves = {int(source): int(target)
                        for source, target in (evolves or {}).items()}
        self.ready = {
            int(card_id): (threshold if isinstance(threshold, Ready) else Ready(int(threshold)))
            for card_id, threshold in (ready or {}).items()
        }
        self._lines = self._normalize_lines()

    @property
    def lines(self) -> tuple[Line, ...]:
        return self._lines

    def resolve(self, deck) -> "Roles":
        """Roles and evolution come from the unified card records (ADR-0143): authored
        defaults, REPLACED by this deck's declarations; ancestry from `evolves_from`."""
        card_ids = tuple(sorted(set(int(card_id) for card_id in deck)))
        store = card_store()
        pokemon = {card_id: record for card_id in card_ids
                   if isinstance(record := store.get(card_id), PokemonCard)}
        evolves = dict(self.evolves)
        if not evolves:
            names: dict[str, list[int]] = {}
            for card_id, record in pokemon.items():
                names.setdefault(record.name, []).append(card_id)
            for card_id, record in pokemon.items():
                parents = names.get(record.evolves_from or "", ())
                if len(parents) == 1:
                    evolves[int(parents[0])] = card_id
        cards = {card_id: list(card_roles) for card_id, card_roles
                 in resolve_pokemon_roles(pokemon, declared=self).items()}
        relevant = {
            card_id for card_id, card_roles in cards.items()
            if any(role in card_roles for role in self._LINE_ROLE_PRIORITY)
        }
        changed = True
        while changed:
            changed = False
            for source, target in evolves.items():
                if target in relevant and source not in relevant:
                    relevant.add(source)
                    changed = True
        evolves = {
            source: target for source, target in evolves.items()
            if source in relevant and target in relevant
        }
        return Roles(cards, evolves=evolves, ready=self.ready)

    def _normalize_lines(self) -> tuple[Line, ...]:
        if not self.evolves:
            return ()
        targets = set(self.evolves.values())
        roots = tuple(source for source in self.evolves if source not in targets)
        if not roots:
            raise ValueError("evolution relationships must not contain a cycle")
        lines, visited = [], set()
        for root in roots:
            path, seen = [root], {root}
            while path[-1] in self.evolves:
                source, target = path[-1], self.evolves[path[-1]]
                if target in seen:
                    raise ValueError("evolution relationships must not contain a cycle")
                visited.add(source)
                path.append(target)
                seen.add(target)
            payoff = path[-1]
            payoff_roles = set(self.get(payoff, ()))
            role = next((candidate for candidate in self._LINE_ROLE_PRIORITY
                         if candidate in payoff_roles), None)
            if role is None:
                raise ValueError(f"evolution payoff {payoff} requires an attacker role")
            lines.append(Line(tuple(path), payoff, role, self.ready.get(payoff, Ready())))
        if visited != set(self.evolves):
            raise ValueError("every evolution relationship must belong to a rooted line")
        return tuple(lines)


@dataclass
class Strategy:
    """Complete deck-specific input to the shared runtime."""

    name: str = ""
    roles: Roles = field(default_factory=Roles)
    starter_priority: tuple[int, ...] = ()
    params: dict = field(default_factory=dict)
    partners: dict[int, tuple[int, ...]] = field(default_factory=dict)
    worth_overrides: dict[int, float] = field(default_factory=dict)
    pilot_overrides: dict[str, float] = field(default_factory=dict)
    ledger_overlay: dict[str, float] = field(default_factory=dict)
    prize_plan: PrizePlan | None = None
    lines: tuple[Line, ...] = field(init=False)

    def __post_init__(self) -> None:
        self.starter_priority = tuple(int(card_id) for card_id in self.starter_priority)
        self.partners = {int(card_id): tuple(int(partner) for partner in partners)
                         for card_id, partners in self.partners.items()}
        self.worth_overrides = {int(card_id): float(value)
                                for card_id, value in self.worth_overrides.items()}
        self.pilot_overrides = {str(name): float(value)
                                for name, value in self.pilot_overrides.items()}
        self.ledger_overlay = {str(name): float(value)
                               for name, value in self.ledger_overlay.items()}
        self.lines = tuple(self.roles.lines)


__all__ = ["Line", "PrizePlan", "Ready", "Roles", "Strategy"]
