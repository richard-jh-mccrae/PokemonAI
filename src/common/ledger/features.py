from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from common.cards.function_catalog import FUNCTION_FEATURES
from common.cards.pokemon_roles import POKEMON_ROLES


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    key: str
    default: float
    activation_shape: str = "scalar"


class FeatureCatalog:
    def __init__(self, specs, *, schema_version: int):
        specs = tuple(specs)
        by_key = {spec.key: spec for spec in specs}
        if len(by_key) != len(specs):
            raise ValueError("feature keys must be unique")
        self._specs = MappingProxyType(by_key)
        self.schema_version = int(schema_version)

    def __contains__(self, key) -> bool:
        return str(key) in self._specs

    def __getitem__(self, key: str) -> FeatureSpec:
        return self._specs[str(key)]

    @property
    def priced_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

_ROLE_DEFAULTS = {
    "primary_attacker": 0.50,
    "backup_attacker": 0.35,
    "sniper": 0.35,
    "draw_engine": 0.40,
    "search_engine": 0.40,
    "healer": 0.30,
    "stall_pokemon": 0.25,
    "supporter_tutor": 0.30,
    "accel_source": 0.35,
    "counter_mover": 0.25,
    "item_locker": 0.30,
    "retreat_assist": 0.20,
    "gust": 0.30,
    "support_pokemon": 0.25,
}

_KIND_DEFAULTS = {
    "pokemon": 0.12,
    "item": 0.10,
    "supporter": 0.15,
    "tool": 0.08,
    "stadium": 0.10,
    "energy": 0.10,
    "special_energy": 0.05,
}

_PLACEMENT_FACTORS = {
    "in_play": 1.0,
    "in_hand_live": 0.65,
    "in_hand_dead": 0.65 * 0.25,
    "in_hand_setup": 0.65 * 0.70,
    "in_hand_colorless": 0.65 * 0.70,
    "in_hand_surplus": 0.65 * 0.60,
    "in_deck": 0.15,
    "in_discard": 0.10,
    "under_body": 0.65,
    "tool_attached": 0.90,
    "attached_usable": 1.0,
}

_HAND_PLACEMENTS = (
    "in_hand_live", "in_hand_dead", "in_hand_setup", "in_hand_colorless",
    "in_hand_surplus",
)
_ROLE_PLACEMENTS = ("in_play", *_HAND_PLACEMENTS, "in_deck", "in_discard", "under_body")
_KIND_PLACEMENTS = {
    "pokemon": _ROLE_PLACEMENTS,
    "item": (*_HAND_PLACEMENTS, "in_deck", "in_discard"),
    "supporter": (*_HAND_PLACEMENTS, "in_deck", "in_discard"),
    "tool": (*_HAND_PLACEMENTS, "in_deck", "in_discard", "tool_attached"),
    "stadium": (*_HAND_PLACEMENTS, "in_deck", "in_discard"),
    "energy": (*_HAND_PLACEMENTS, "in_deck", "in_discard", "attached_usable"),
    "special_energy": (*_HAND_PLACEMENTS, "in_deck", "in_discard", "attached_usable"),
}

_SCALAR_DEFAULTS = {
    "zone.in_play": 0.0,
    "zone.in_hand": 0.0,
    "zone.in_deck": 0.0,
    "zone.in_discard": 0.0,
    "zone.under_body": 0.0,
    "zone.attached_usable": 0.0,
    "zone.attached_useless": 0.0,
    "zone.tool_attached": 0.0,
    "demand.dead": 0.0,
    "demand.colorless_only": 0.0,
    "demand.setup": 0.0,
    "development.ready_evolution": 0.12,
    "development.visible_reach": 0.08,
    "development.next_turn_reach": 0.04,
    "copy.surplus": -0.03,
    "copy.surplus_in_play": 0.20,
    "damage.floor": 0.30,
    "body.hp_per_100": 0.02,
    "bench.open_slot": 0.02,
    "body.prize_liability": 0.04,
    "energy.concentration": 0.10,
    "active.doomed": 0.40,
    "active.premium": 0.08,
    "active.unready_fraction": 0.04,
    "prize.race": 1.0,
    "result.win": 100.0,
    "belief.unknown_card": 0.0,
    "coverage.unknown_card": 0.0,
    "belief.unknown_deck_card": 0.0075,
    "belief.unknown_archetype": 0.0,
    "context.opponent_unknown_card": 0.0,
    "context.opponent_unknown_hand": 0.078,
    "context.opponent_unknown_deck": 0.018,
    "context.damaged_attached": -1.0,
    "continuation.multi_provision_in_hand": 0.05,
    "continuation.zone_created": 0.001,
    "continuation.zone_replaced": 0.0002,
    "continuation.allowance_consumed": -0.001,
    "continuation.usable_output": 0.001,
    "continuation.opportunity_created": 0.001,
    "continuation.opportunity_preserved": 0.0005,
    "continuation.opportunity_consumed": -0.001,
    "function.draw.hand_deficit": 0.0,
    "function.fetch.live_target": 0.0,
    "function.gust.bench_target": 0.0,
    "function.heal.damage_present": 0.0,
    "function.accel.open_energy_slot": 0.0,
    "function.switch.active_pressure": 0.0,
    "function.disruption.opponent_hand": 0.0,
    "function.denial.opponent_resource": 0.0,
    "function.bench_pressure.target_count": 0.0,
    "function.protection.incoming_pressure": 0.0,
    "function.status.active_target": 0.0,
    "function.cost_reduction.open_cost": 0.0,
    "function.self_cost.exposure": 0.0,
    "function.suppression.ability_target": 0.0,
    "function.development.board_fit": 0.0,
    "function.move_damage.damage_present": 0.0,
    "function.ko.active_target": 0.0,
    "function.stadium.board_fit": 0.0,
    "action.opportunity_cost": 0.001,
    "status.asleep": 0.15,
    "status.paralyzed": 0.15,
    "status.confused": 0.08,
    "status.poisoned": 0.08,
    "status.burned": 0.08,
}

_BELIEF_DEFAULTS = {
    "mechanic.comeback_disruption": 0.0,
    "mechanic.damage_cap": 0.0,
    "mechanic.effect_immunity": 0.0,
    "mechanic.hand_size_attack": 0.0,
    "mechanic.item_lock": 0.0,
    "mechanic.no_pivot": 0.0,
    "mechanic.piercing": 0.0,
    "mechanic.single_prize": 0.0,
    "mechanic.special_energy_only": 0.0,
    "mechanic.spread": 0.0,
    "trait.deckout_vulnerability": 0.0,
    "trait.heal_wall": 0.0,
    "trait.opening_fragility": 0.0,
    "trait.tempo.fast": 0.0,
    "trait.tempo.midrange": 0.0,
    "trait.tempo.slow": 0.0,
}


FEATURE_CATALOG = FeatureCatalog(
    tuple(FeatureSpec(key, value) for key, value in _SCALAR_DEFAULTS.items())
    + tuple(FeatureSpec(key, value, "posterior")
            for key, value in _BELIEF_DEFAULTS.items())
    + tuple(FeatureSpec(f"trait.setup_dependency.{role}", 0.0, "posterior")
            for role in POKEMON_ROLES)
    + tuple(FeatureSpec(f"kind.{kind}", value, "count")
            for kind, value in _KIND_DEFAULTS.items())
    + tuple(FeatureSpec(f"role.{role}", _ROLE_DEFAULTS[role],
                        "count")
            for role in POKEMON_ROLES)
    + tuple(FeatureSpec(f"interaction.role.{role}.{placement}",
                        value * factor,
                        "situational_count")
            for role, value in _ROLE_DEFAULTS.items()
            for placement in _ROLE_PLACEMENTS
            for factor in (_PLACEMENT_FACTORS[placement],))
    + tuple(FeatureSpec(f"interaction.kind.{kind}.{placement}",
                        value * factor,
                        "situational_count")
            for kind, value in _KIND_DEFAULTS.items()
            for placement in _KIND_PLACEMENTS[kind]
            for factor in (_PLACEMENT_FACTORS[placement],)),
    schema_version=1,
)
_missing_function_features = set(FUNCTION_FEATURES.values()) - set(FEATURE_CATALOG.priced_keys)
if _missing_function_features:
    raise ValueError(f"card Function outputs lack Feature entries: {sorted(_missing_function_features)}")


__all__ = ("FEATURE_CATALOG", "FeatureCatalog", "FeatureSpec")
