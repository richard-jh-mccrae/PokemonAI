from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class OpponentTrait:
    name: str
    value: bool | str


class TraitCatalog:
    def __init__(self, value_types, domains=None):
        self._types = MappingProxyType(dict(value_types))
        self._domains = MappingProxyType(dict(domains or {}))

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._types))

    def compile(self, claims) -> tuple[OpponentTrait, ...]:
        traits = []
        for name, value in (claims or {}).items():
            if name not in self._types:
                raise KeyError(f"unknown opponent Trait {name!r}")
            expected = self._types[name]
            if not isinstance(value, expected):
                raise TypeError(f"opponent Trait {name!r} requires {expected.__name__}")
            if name in self._domains and value not in self._domains[name]:
                raise ValueError(f"opponent Trait {name!r} requires one of "
                                 f"{sorted(self._domains[name])}")
            traits.append(OpponentTrait(str(name), value))
        return tuple(sorted(traits, key=lambda trait: trait.name))

    def validate(self, traits) -> tuple[OpponentTrait, ...]:
        normalized = tuple(traits or ())
        if any(not isinstance(trait, OpponentTrait) for trait in normalized):
            raise TypeError("opponent traits must be OpponentTrait values")
        if len({trait.name for trait in normalized}) != len(normalized):
            raise ValueError("opponent Trait names must be unique")
        compiled = self.compile({trait.name: trait.value for trait in normalized})
        return compiled


TRAIT_CATALOG = TraitCatalog({
    "opp_accel_dependent": bool,
    "opp_caps_big_hits": bool,
    "opp_comeback_disruptor": bool,
    "opp_deckout_vulnerable": bool,
    "opp_donk_vulnerable": bool,
    "opp_effect_immune_bodies": bool,
    "opp_ex_damage_immune": bool,
    "opp_hand_size_attacker": bool,
    "opp_is_engine_dependent": bool,
    "opp_is_heal_wall": bool,
    "opp_item_locks": bool,
    "opp_no_pivot": bool,
    "opp_pierces_active_effects": bool,
    "opp_single_prize": bool,
    "opp_special_energy_fragile": bool,
    "opp_spreads_bench": bool,
    "opp_tempo": str,
}, domains={"opp_tempo": frozenset({"fast", "midrange", "slow"})})


__all__ = ("OpponentTrait", "TRAIT_CATALOG", "TraitCatalog")
