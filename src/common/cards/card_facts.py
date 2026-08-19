"""The unified per-card records: printed facts, tags, and machine-readable effect Clauses.

One frozen record per printing — `PokemonCard` under `pokemon_cards/`, `TrainerCard` under
`trainer_cards/` — served as one dict by `common.cards.card_store()`. Every field is stored,
none derived at query time, so a mid-game read is one dict hit plus attribute access.
`Clause` is a `kind` plus that card's own named parameters (the `card_effects.json`
vocabulary); an unset parameter reads as None, so the vocabulary can grow per card without
touching this module. Amounts are DAMAGE POINTS, never counters; Energy codes are the engine
wire ints re-exported here under their short names."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from .functions.energy import (
    ENERGY_COLORLESS as COLORLESS, ENERGY_GRASS as GRASS, ENERGY_FIRE as FIRE,
    ENERGY_WATER as WATER, ENERGY_LIGHTNING as LIGHTNING, ENERGY_PSYCHIC as PSYCHIC,
    ENERGY_FIGHTING as FIGHTING, ENERGY_DARKNESS as DARKNESS, ENERGY_METAL as METAL,
    ENERGY_DRAGON as DRAGON)

BASIC, STAGE1, STAGE2 = "basic", "stage1", "stage2"
ITEM, TOOL, SUPPORTER, STADIUM = "item", "tool", "supporter", "stadium"
BASIC_ENERGY, SPECIAL_ENERGY = "basic_energy", "special_energy"


class Clause:
    """One effect leg: a `kind` plus that card's named parameters; an unset parameter reads None."""
    __slots__ = ("kind", "params")

    def __init__(self, kind: str, **params):
        object.__setattr__(self, "kind", str(kind))
        object.__setattr__(self, "params", MappingProxyType(dict(params)))

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return self.params.get(name)

    def __setattr__(self, name, value):
        raise AttributeError("Clause is frozen")

    def __eq__(self, other):
        return (isinstance(other, Clause) and self.kind == other.kind
                and dict(self.params) == dict(other.params))

    def __hash__(self):
        return hash((self.kind, repr(sorted(self.params.items()))))

    def __repr__(self):
        parts = "".join(f", {key}={value!r}" for key, value in self.params.items())
        return f"Clause(kind={self.kind!r}{parts})"


@dataclass(frozen=True, slots=True)
class Attack:
    attack_id: int
    name: str
    cost: tuple[int, ...]
    damage: int
    text: str = ""
    clauses: tuple[Clause, ...] = ()


@dataclass(frozen=True, slots=True)
class Ability:
    name: str
    text: str = ""
    clauses: tuple[Clause, ...] = ()


@dataclass(frozen=True, slots=True)
class PokemonCard:
    card_id: int
    name: str
    hp: int
    energy_type: int
    stage: str
    evolves_from: str | None = None
    ex: bool = False
    mega_ex: bool = False
    tera: bool = False
    weakness: int | None = None
    resistance: int | None = None
    retreat_cost: int = 0
    tags: frozenset = frozenset()
    #: This body's own job, authored from its text — see `pokemon_roles.POKEMON_ROLES`. A deck
    #: that wants a different job for it overrides; prize count never enters this.
    default_roles: tuple[str, ...] = ()
    #: Cards this one's OWN text names to function (Solrock/Lunatone). Symmetric by construction.
    synergy: tuple[str, ...] = ()
    abilities: tuple[Ability, ...] = ()
    attacks: tuple[Attack, ...] = ()

    @property
    def prize_value(self) -> int:
        return 2 if self.ex or self.mega_ex else 1


@dataclass(frozen=True, slots=True)
class TrainerCard:
    """Class rules (one Supporter a turn, Tools attach, Stadiums replace) follow from `kind`."""
    card_id: int
    name: str
    kind: str
    text: str = ""
    ace_spec: bool = False
    tags: frozenset = frozenset()
    clauses: tuple[Clause, ...] = ()


@dataclass(frozen=True, slots=True)
class EnergyCard:
    """`provides` is the COLOUR yielded once attached; one unit unless a clause says otherwise."""
    card_id: int
    name: str
    kind: str
    provides: int = COLORLESS
    text: str = ""
    tags: frozenset = frozenset()
    clauses: tuple[Clause, ...] = ()


__all__ = ("Ability", "Attack", "Clause", "EnergyCard", "PokemonCard", "TrainerCard",
           "BASIC", "STAGE1", "STAGE2", "ITEM", "TOOL", "SUPPORTER", "STADIUM",
           "BASIC_ENERGY", "SPECIAL_ENERGY",
           "COLORLESS", "GRASS", "FIRE", "WATER", "LIGHTNING", "PSYCHIC", "FIGHTING",
           "DARKNESS", "METAL", "DRAGON")
