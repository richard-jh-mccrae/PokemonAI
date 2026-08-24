"""The unified per-card records: printed facts and machine-readable effect Clauses.

One frozen record per printing — `PokemonCard` under `pokemon_cards/`, `TrainerCard` under
`trainer_cards/` — served as one dict by `common.cards.card_store()`. Every field is stored,
none derived at query time, so a mid-game read is one dict hit plus attribute access.
`Clause` is a `kind` plus that card's own named parameters; unset parameters read as None, so the
vocabulary can grow per card without touching this module. Amounts are DAMAGE POINTS; Energy codes are the engine
wire ints, defined here so the function modules read them off the ground layer."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

# Values verbatim from the engine wire enum (`cg.api` EnergyType).
COLORLESS, GRASS, FIRE, WATER, LIGHTNING = 0, 1, 2, 3, 4
PSYCHIC, FIGHTING, DARKNESS, METAL, DRAGON, WILDCARD = 5, 6, 7, 8, 9, 10

BASIC, STAGE1, STAGE2 = "basic", "stage1", "stage2"
ITEM, TOOL, SUPPORTER, STADIUM = "item", "tool", "supporter", "stadium"
BASIC_ENERGY, SPECIAL_ENERGY = "basic_energy", "special_energy"


def _hashable(value):
    """A JSON-ish parameter value as a hashable equivalent (lists/dicts arrive from the store)."""
    if isinstance(value, dict):
        return tuple(sorted((str(key), _hashable(child)) for key, child in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_hashable(child) for child in value)
    return value


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
        # Built from the values `__eq__` compares (not their repr), so 1/True stay one entry.
        return hash((self.kind, frozenset(
            (key, _hashable(value)) for key, value in self.params.items())))

    def __repr__(self):
        parts = "".join(f", {key}={value!r}" for key, value in self.params.items())
        return f"Clause(kind={self.kind!r}{parts})"


def _first_clause(clauses: tuple, kind: str) -> Clause | None:
    """A plain scan IS the fast path: a record carries at most a handful of clauses."""
    return next((clause for clause in clauses if clause.kind == kind), None)


@dataclass(frozen=True, slots=True)
class Attack:
    attack_id: int
    name: str
    cost: tuple[int, ...]
    damage: int
    text: str = ""
    clauses: tuple[Clause, ...] = ()
    #: Corrections to the ENGINE's stat row for this attack (ADR-0108): fields the CSV gets
    #: wrong, authored per attack; the stat provider overlays them onto its cache.
    damage_fix: int | None = None
    damage_min: int | None = None
    damage_max: int | None = None
    scale_var: str | None = None
    scale_per_unit: int | None = None
    scale_filter: tuple[int, ...] | None = None

    def clause(self, kind: str) -> Clause | None:
        return _first_clause(self.clauses, kind)

    def engine_overrides(self) -> dict:
        """The stat-provider patch this record authors, in the engine's own field names."""
        pairs = (("damage", self.damage_fix), ("damageMin", self.damage_min),
                 ("damageMax", self.damage_max), ("scaleVar", self.scale_var),
                 ("scalePerUnit", self.scale_per_unit),
                 ("scaleFilter", list(self.scale_filter) if self.scale_filter is not None
                  else None))
        return {name: value for name, value in pairs if value is not None}


@dataclass(frozen=True, slots=True)
class Ability:
    name: str
    text: str = ""
    clauses: tuple[Clause, ...] = ()

    def clause(self, kind: str) -> Clause | None:
        return _first_clause(self.clauses, kind)


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
    #: This body's own job, authored from its text — see `pokemon_roles.POKEMON_ROLES`. A deck
    #: that wants a different job for it overrides; prize count never enters this.
    default_roles: tuple[str, ...] = ()
    #: Clause-set completeness verdict ("full" | "partial"; None = unruled). The reasons live
    #: with the authoring source, `tools/meta_tracker/effect_overrides.json`.
    covers: str | None = None
    #: Cards this one's OWN text names to function (Solrock/Lunatone). Symmetric by construction.
    synergy: tuple[str, ...] = ()
    abilities: tuple[Ability, ...] = ()
    attacks: tuple[Attack, ...] = ()

    @property
    def prize_value(self) -> int:
        """A Mega Evolution Pokemon ex gives up THREE prizes (rulebook L337ff), a plain ex two."""
        return 3 if self.mega_ex else 2 if self.ex else 1

    @property
    def is_rule_box(self) -> bool:
        return self.ex or self.mega_ex

    @property
    def has_ability(self) -> bool:
        return bool(self.abilities)


@dataclass(frozen=True, slots=True)
class TrainerCard:
    """Class rules (one Supporter a turn, Tools attach, Stadiums replace) follow from `kind`."""
    card_id: int
    name: str
    kind: str
    text: str = ""
    ace_spec: bool = False
    clauses: tuple[Clause, ...] = ()
    covers: str | None = None

    def clause(self, kind: str) -> Clause | None:
        return _first_clause(self.clauses, kind)


@dataclass(frozen=True, slots=True)
class EnergyCard:
    """`provides` is the COLOUR yielded once attached; one unit unless a clause says otherwise."""
    card_id: int
    name: str
    kind: str
    provides: int = COLORLESS
    text: str = ""
    clauses: tuple[Clause, ...] = ()
    covers: str | None = None

    def clause(self, kind: str) -> Clause | None:
        return _first_clause(self.clauses, kind)


__all__ = ("Ability", "Attack", "Clause", "EnergyCard", "PokemonCard", "TrainerCard",
           "BASIC", "STAGE1", "STAGE2", "ITEM", "TOOL", "SUPPORTER", "STADIUM",
           "BASIC_ENERGY", "SPECIAL_ENERGY",
           "COLORLESS", "GRASS", "FIRE", "WATER", "LIGHTNING", "PSYCHIC", "FIGHTING",
           "DARKNESS", "METAL", "DRAGON", "WILDCARD")
