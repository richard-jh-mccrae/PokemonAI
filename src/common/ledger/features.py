from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from types import MappingProxyType



CATALOG_ID_DIGEST_BYTES = 16


ACTIVATION_OPERATIONS = frozenset({
    "ability_target", "active_retreat_cost", "active_target", "active_tool_count",
    "bench_pressure_target", "bench_target", "board_body_count", "body_clause_count",
    "body_flag_count",
    "constant", "copy_attack_source", "evolution_target",
    "incoming_pressure", "mill_target", "multi_provision_capacity", "open_cost",
    "open_energy_slot",
    "opponent_bench", "opponent_empty_bench",
    "opponent_damage_units", "opponent_deck_count", "opponent_energy_count",
    "opponent_hand_count", "opponent_single_prize_count",
    "opponent_special_energy_count", "own_bench_count", "own_damage_units",
    "own_hand_count", "own_item_count", "own_max_attack_units", "prize_difference",
    "side_damage_units", "side_status_count", "status_target",
    "stadium_board_fit", "switch_target", "piercing_target", "self_ko_liability",
    "turn_number",
})


@dataclass(frozen=True, slots=True)
class ActivationRule:
    source: str
    claims: tuple[str, ...]
    operation: str
    argument: str | None = None
    parameters: tuple[str, ...] = ()

    def __post_init__(self):
        claims = tuple(sorted({str(claim) for claim in self.claims}))
        if not self.source or not claims or not self.operation:
            raise ValueError("activation rule requires source, claims, and operation")
        object.__setattr__(self, "source", str(self.source))
        object.__setattr__(self, "claims", claims)
        object.__setattr__(self, "operation", str(self.operation))
        if self.argument is not None:
            object.__setattr__(self, "argument", str(self.argument))
        object.__setattr__(self, "parameters", tuple(str(value) for value in self.parameters))


class FeatureDisposition(str, Enum):
    ACTIVE = "active"
    ALIAS = "alias"
    LEGALITY_ONLY = "legality-only"
    CONDITIONAL = "conditional"
    RETIRED = "retired"
    AWAITING_SEED = "awaiting-seed"


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    key: str
    default: float
    activation_shape: str = "scalar"
    rules: tuple[ActivationRule, ...] = ()
    disposition: FeatureDisposition = FeatureDisposition.ACTIVE
    replacement: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "key", str(self.key))
        object.__setattr__(self, "default", float(self.default))
        if not math.isfinite(self.default):
            raise ValueError("feature default must be finite")
        object.__setattr__(self, "activation_shape", str(self.activation_shape))
        object.__setattr__(self, "rules", tuple(self.rules))
        disposition = FeatureDisposition(self.disposition)
        object.__setattr__(self, "disposition", disposition)
        replacement = None if self.replacement is None else str(self.replacement)
        if disposition is FeatureDisposition.ALIAS and not replacement:
            raise ValueError("alias feature requires a replacement")
        if disposition is not FeatureDisposition.ALIAS and replacement is not None:
            raise ValueError("only alias features may name a replacement")
        if disposition is not FeatureDisposition.ACTIVE and self.default != 0.0:
            raise ValueError("non-active feature default must be zero")
        if disposition is not FeatureDisposition.ACTIVE and self.rules:
            raise ValueError("non-active feature cannot own activation rules")
        object.__setattr__(self, "replacement", replacement)


class FeatureCatalog:
    def __init__(self, specs, *, schema_version: int):
        specs = tuple(specs)
        by_key = {spec.key: spec for spec in specs}
        if len(by_key) != len(specs):
            raise ValueError("feature keys must be unique")
        if any(not isinstance(rule, ActivationRule)
               for spec in specs for rule in spec.rules):
            raise TypeError("feature activation rules must be ActivationRule values")
        for spec in specs:
            if spec.disposition is FeatureDisposition.ALIAS:
                if spec.replacement not in by_key:
                    raise KeyError(f"unknown alias replacement {spec.replacement!r}")
                if by_key[spec.replacement].disposition is not FeatureDisposition.ACTIVE:
                    raise ValueError("alias replacement must be active")
        unknown_operations = {rule.operation for spec in specs for rule in spec.rules} \
            - ACTIVATION_OPERATIONS
        if unknown_operations:
            raise KeyError(f"unknown activation operation {sorted(unknown_operations)[0]!r}")
        self._specs = MappingProxyType(by_key)
        indexed = {}
        for spec in (by_key[key] for key in sorted(by_key)
                     if by_key[key].disposition is FeatureDisposition.ACTIVE):
            for rule in spec.rules:
                for claim in rule.claims:
                    indexed.setdefault((rule.source, claim), []).append((spec, rule))
        self._rules_by_source_claim = MappingProxyType({
            key: tuple(value) for key, value in indexed.items()})
        self._rule_order = {
            (spec.key, rule): index
            for spec in specs for index, rule in enumerate(spec.rules)}
        self._activation_rules_cache = {}
        self.schema_version = int(schema_version)

    def __contains__(self, key) -> bool:
        return str(key) in self._specs

    def __getitem__(self, key: str) -> FeatureSpec:
        return self._specs[str(key)]

    @cached_property
    def priced_keys(self) -> tuple[str, ...]:
        return tuple(spec.key for spec in self.priced_specs)

    @cached_property
    def priced_specs(self) -> tuple[FeatureSpec, ...]:
        return tuple(spec for spec in self.specs
                     if spec.disposition is FeatureDisposition.ACTIVE)

    @cached_property
    def specs(self) -> tuple[FeatureSpec, ...]:
        return tuple(self._specs[key] for key in sorted(self._specs))

    def activation_rules(self, source: str, claims) -> tuple[tuple[FeatureSpec, ActivationRule], ...]:
        cache_key = (str(source), tuple(sorted({str(claim) for claim in claims})))
        cached = self._activation_rules_cache.get(cache_key)
        if cached is not None:
            return cached
        found = {}
        for claim in cache_key[1]:
            for spec, rule in self._rules_by_source_claim.get((cache_key[0], claim), ()):
                found[(spec.key, rule)] = (spec, rule)
        compiled = tuple(found[key] for key in sorted(
            found, key=lambda item: (item[0], self._rule_order[item])))
        self._activation_rules_cache[cache_key] = compiled
        return compiled

    def has_activation_rules(self, source: str, claims) -> bool:
        return any((str(source), str(claim)) in self._rules_by_source_claim
                   for claim in claims)

    @cached_property
    def identity(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "specs": tuple((spec.key, spec.default, spec.activation_shape,
                            spec.disposition.value, spec.replacement,
                            tuple((rule.source, rule.claims, rule.operation, rule.argument,
                                   rule.parameters)
                                  for rule in spec.rules))
                           for spec in self.specs),
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.blake2b(blob, digest_size=CATALOG_ID_DIGEST_BYTES).hexdigest()


def _rule(source, claims, operation, argument=None, parameters=()):
    return ActivationRule(source, tuple(claims), operation, argument, tuple(parameters))


_DECLARED_RULES = {
    "action.damage_counter_progress": _rule(
        "action", ("damage_counter_progress",), "constant"),
    "action.overkill_counter": _rule("action", ("overkill_counter",), "constant"),
    "action.draw_before_refresh": _rule(
        "action", ("draw_before_refresh",), "constant"),
    "action.gust_spend": _rule("action", ("gust_spend",), "constant"),
    "action.play_before_refresh": _rule(
        "action", ("play_before_refresh",), "constant"),
    "action.dead_play": _rule(
        "action", ("dead_play",), "constant"),
    "action.dead_discard": _rule(
        "action", ("dead_discard",), "constant"),
    "action.body_ability_ready": _rule(
        "action", ("body_ability_ready",), "constant"),
    "action.body_copy_overflow": _rule(
        "action", ("body_copy_overflow",), "constant"),
    "action.retreat_doomed_denial": _rule(
        "action", ("retreat_doomed_denial",), "constant"),
    "action.acceleration_phase_fit": _rule(
        "action", ("acceleration_phase_fit",), "constant"),
    "ability.resource_cost": _rule(
        "draw_effect", ("opponent_cards",), "constant"),
    "ability.damage_move": _rule(
        "option", ("ability.damage_move",), "constant"),
    "function.gust.bench_target": _rule("function", ("gust",), "bench_target"),
    "function.heal.damage_present": _rule("function", ("heal",), "constant"),
    "function.accel.open_energy_slot": _rule(
        "function", ("accel", "energy_double", "energy_recur", "move_energy"),
        "open_energy_slot"),
    "function.switch.active_pressure": _rule(
        "function", ("self_switch", "switch_self", "push_out"), "switch_target"),
    "function.disruption.opponent_hand": _rule(
        "function", ("opp_hand_to_deck",), "opponent_hand_count"),
    "function.disruption.deck": _rule(
        "function", ("mill",), "mill_target"),
    "function.denial.opponent_resource": _rule(
        "function", ("discard_opp_energy", "energy_bounce", "item_lock", "attack_lock",
                     "no_retreat", "retreat_lock"), "opponent_energy_count"),
    "function.bench_pressure.target_count": _rule(
        "function", ("bench_snipe", "bench_spread", "damage_counters"),
        "bench_pressure_target"),
    "function.protection.incoming_pressure": _rule(
        "function", ("damage_protection", "damage_reduction", "prevent_damage",
                     "prevent_effects", "hp_bonus"), "incoming_pressure"),
    "function.status.active_target": _rule(
        "function", ("attack_debuff", "confuse", "sleep"), "status_target"),
    "function.cost_reduction.open_cost": _rule(
        "function", ("attack_cost_reduction", "cost_reduction", "retreat_reduction"),
        "open_cost"),
    "function.self_cost.exposure": _rule(
        "function", ("recoil", "self_discard_energy", "self_mill", "self_return",
                     "self_shuffle_in"), "constant"),
    "function.suppression.ability_target": _rule(
        "function", ("ability_suppression",), "ability_target"),
    "function.development.board_fit": _rule(
        "function", ("evolve_early",), "evolution_target"),
    "function.move_damage.damage_present": _rule(
        "function", ("move_damage",), "own_damage_units"),
    "function.ko.active_target": _rule(
        "function", ("ko",), "active_target"),
    "function.ko.self_prize_liability": _rule(
        "function", ("ko",), "self_ko_liability"),
    "function.stadium.board_fit": _rule(
        "function", ("stadium_static", "stadium_trigger"), "stadium_board_fit"),
    "function.attack.modifier": _rule(
        "function", ("damage_boost", "coin"), "active_target"),
    "function.attack.copy_source": _rule(
        "function", ("copy_attack",), "copy_attack_source"),
    "function.attack.piercing": _rule(
        "function", ("ignores_effects", "ignores_wr"), "piercing_target"),
    "function.energy.provision": _rule(
        "function", ("energy_provide",), "open_energy_slot"),
    "continuation.multi_provision_in_hand": _rule(
        "function", ("energy_provide",), "multi_provision_capacity"),
}

_OBSERVATION_CLAIMS = {
    "zone.in_play": "card_in_play",
    "zone.in_hand": "card_in_hand",
    "zone.in_deck": "card_in_deck",
    "zone.in_discard": "card_in_discard",
    "zone.under_body": "card_under_body",
    "zone.attached_usable": "usable_attached_energy",
    "zone.attached_useless": "useless_attached_energy",
    "energy.end_of_turn_rental": "end_of_turn_rental",
    "zone.tool_attached": "attached_tool",
    "demand.dead": "dead_hand_card",
    "demand.colorless_only": "colorless_only_hand_card",
    "demand.setup": "setup_hand_card",
    "development.ready_evolution": "evolution_access",
    "development.visible_reach": "visible_development_reach",
    "development.feasible_hand_link": "feasible_hand_link",
    "development.basic_hand_link": "basic_hand_link",
    "development.reserve_hand_link": "reserve_hand_link",
    "copy.surplus": "surplus_hand_copy",
    "copy.surplus_in_play": "surplus_in_play_copy",
    "copy.basic_energy_surplus": "surplus_basic_energy",
    "interaction.synergy.in_hand": "synergy_in_hand",
    "damage.floor": "body_damage_fraction",
    "body.hp_per_100": "body_hp_units",
    "bench.open_slot": "open_bench_slot",
    "body.development": "developed_body",
    "bench.full": "full_bench",
    "body.prize_liability": "extra_prize_liability",
    "energy.concentration": "concentrated_energy",
    "active.doomed": "doomed_active",
    "active.terminal_liability": "terminal_active_liability",
    "active.premium": "active_body",
    "active.unready_fraction": "unready_active",
    "active.retreat_ready": "retreat_ready_active",
    "active.damage_pressure": "active_damage_pressure",
    "combat.realization": "combat_realization",
    "ability.draw_cards": "ability_draw_cards",
    "ability.search_cards": "ability_search_cards",
    "ability.damage_move": "ability_damage_move",
    "ability.healing": "ability_healing",
    "ability.acceleration": "ability_acceleration",
    "ability.denial": "ability_denial",
    "ability.resource_cost": "ability_resource_cost",
    "ability.self_cost": "ability_self_cost",
    "ability.future": "ability_future",
    "mobility.retreat_progress": "retreat_progress",
    "resource.discard_recoverable": "recoverable_discard_card",
    "resource.opponent_hidden_option": "opponent_hidden_option_value",
    "resource.opponent_hidden_deck": "opponent_hidden_deck_value",
    "prize.race": "prize_advantage",
    "prize.overrun": "prize_overrun",
    "result.win": "terminal_win",
    "belief.unknown_card": "unknown_card_belief",
    "coverage.unknown_card": "uncovered_card",
    "belief.unknown_deck_card": "unknown_own_deck_card",
    "belief.unknown_archetype": "unknown_opponent_archetype",
    "context.opponent_unknown_card": "unknown_opponent_card",
    "context.opponent_unknown_hand": "unknown_opponent_hand_card",
    "context.opponent_unknown_deck": "unknown_opponent_deck_card",
    "context.damaged_attached": "usable_energy_on_damaged_body",
    "context.damaged_active_threat": "damaged_active_threat",
    "status.asleep": "asleep_status",
    "status.paralyzed": "paralyzed_status",
    "status.confused": "confused_status",
    "status.poisoned": "poisoned_status",
    "status.burned": "burned_status",
}

_CONTINUATION_CLAIMS = {
    "action.opportunity_cost": "continued_action",
    "continuation.zone_created": "zone_created",
    "continuation.zone_replaced": "zone_replaced",
    "continuation.allowance_consumed": "allowance_consumed",
    "continuation.usable_output": "usable_output",
    "continuation.opportunity_created": "opportunity_created",
    "continuation.opportunity_preserved": "opportunity_preserved",
    "continuation.opportunity_consumed": "opportunity_consumed",
    "continuation.information_value": "information_value",
}

_TRAIT_RULES = {
    "trait.deckout_vulnerability": _rule(
        "opponent_trait", ("deckout_vulnerability",), "opponent_deck_count"),
    "trait.heal_wall": _rule("opponent_trait", ("heal_wall",), "opponent_damage_units"),
    "trait.opening_fragility": _rule(
        "opponent_trait", ("opening_fragility",), "opponent_empty_bench"),
    **{f"trait.tempo.{tempo}": _rule(
        "opponent_trait", ("tempo",), "constant", tempo)
       for tempo in ("fast", "midrange", "slow")},
    **{f"trait.tempo.{tempo}.turn": _rule(
        "opponent_trait", ("tempo",), "turn_number", tempo)
       for tempo in ("fast", "midrange", "slow")},
}

_MECHANIC_RULES = {
    "mechanic.comeback_disruption": _rule(
        "opponent_mechanic", ("comeback_disruption",), "prize_difference"),
    "mechanic.damage_cap": _rule(
        "opponent_mechanic", ("damage_cap",), "own_max_attack_units"),
    "mechanic.effect_immunity": _rule(
        "opponent_mechanic", ("effect_immunity",), "body_clause_count",
        parameters=("attack_debuff", "attack_lock", "burn", "confuse", "damage_counters",
                    "discard_opp_energy", "no_retreat", "poison", "push_out",
                    "retreat_lock", "sleep")),
    "mechanic.effect_immunity.ex_body_count": _rule(
        "opponent_mechanic", ("effect_immunity",), "body_flag_count",
        parameters=("ex", "mega_ex")),
    "mechanic.hand_size_attack": _rule(
        "opponent_mechanic", ("hand_size_attack",), "own_hand_count"),
    "mechanic.item_lock": _rule(
        "opponent_mechanic", ("item_lock",), "own_item_count"),
    "mechanic.no_pivot": _rule(
        "opponent_mechanic", ("no_pivot",), "side_status_count", "them"),
    "mechanic.no_pivot.retreat_cost": _rule(
        "opponent_mechanic", ("no_pivot",), "active_retreat_cost", "them"),
    "mechanic.piercing": _rule(
        "opponent_mechanic", ("piercing",), "side_status_count", "me"),
    "mechanic.piercing.active_tools": _rule(
        "opponent_mechanic", ("piercing",), "active_tool_count", "me"),
    "mechanic.single_prize": _rule(
        "opponent_mechanic", ("single_prize",), "opponent_single_prize_count"),
    "mechanic.special_energy_only": _rule(
        "opponent_mechanic", ("special_energy_only",), "opponent_special_energy_count"),
    "mechanic.spread": _rule(
        "opponent_mechanic", ("spread",), "own_bench_count"),
}

_KIND_DEFAULTS = {
    "pokemon": 0.12,
    "item": 0.10,
    "supporter": 0.15,
    "tool": 0.08,
    "stadium": 0.10,
    "energy": 0.20,
    "special_energy": 0.05,
}

_PLACEMENT_FACTORS = {
    "in_play": 1.0,
    "in_hand_live": 0.80,
    "in_hand_dead": 0.80 * 0.20,
    "in_hand_setup": 0.80 * 0.60,
    "in_hand_colorless": 0.80 * 0.60,
    "in_hand_surplus": 0.80 * 0.40,
    "in_deck": 0.15,
    "in_discard": 0.10,
    "under_body": 0.65,
    "tool_attached": 0.50,
    "attached_usable": 1.0,
}

_HAND_PLACEMENTS = (
    "in_hand_live", "in_hand_dead", "in_hand_setup", "in_hand_colorless",
    "in_hand_surplus",
)
_POKEMON_PLACEMENTS = ("in_play", *_HAND_PLACEMENTS, "in_deck", "in_discard", "under_body")
_KIND_PLACEMENTS = {
    "pokemon": _POKEMON_PLACEMENTS,
    "item": (*_HAND_PLACEMENTS, "in_deck", "in_discard"),
    "supporter": (*_HAND_PLACEMENTS, "in_deck", "in_discard"),
    "tool": (*_HAND_PLACEMENTS, "in_deck", "in_discard", "tool_attached"),
    "stadium": (*_HAND_PLACEMENTS, "in_deck", "in_discard"),
    "energy": (*_HAND_PLACEMENTS, "in_deck", "in_discard", "attached_usable"),
    "special_energy": (*_HAND_PLACEMENTS, "in_deck", "in_discard", "attached_usable"),
}

_SCALAR_DEFAULTS = {
    "action.acceleration_phase_fit": 1.0,
    "action.damage_counter_progress": 1.0,
    "action.overkill_counter": -100.0,
    "action.draw_before_refresh": -0.75,
    "action.gust_spend": -1.25,
    "action.play_before_refresh": -0.20,
    "action.dead_play": -0.20,
    "action.dead_discard": 0.15,
    "action.body_ability_ready": 0.40,
    "action.body_copy_overflow": -0.30,
    "action.retreat_doomed_denial": -1.0,
    "zone.in_play": 0.002,
    "zone.in_hand": 0.01,
    "zone.in_deck": 0.001,
    "zone.in_discard": 0.001,
    "zone.under_body": 0.002,
    "zone.attached_usable": 0.004,
    "zone.attached_useless": -0.09,
    "energy.end_of_turn_rental": -0.25,
    "zone.tool_attached": 0.002,
    "demand.dead": -0.04,
    "demand.colorless_only": -0.02,
    "demand.setup": 0.032,
    "development.ready_evolution": 0.50,
    "development.visible_reach": 0.0161,
    "development.feasible_hand_link": 0.13,
    "development.basic_hand_link": 0.25,
    "development.reserve_hand_link": 0.06,
    "copy.surplus": -0.03,
    "copy.surplus_in_play": -1.0,
    "copy.basic_energy_surplus": -0.04,
    "interaction.synergy.in_hand": 0.351,
    "damage.floor": 0.75,
    "body.hp_per_100": 0.05,
    "bench.open_slot": 0.15,
    "body.development": 0.31,
    "bench.full": -0.30,
    "body.prize_liability": 0.26,
    "energy.concentration": 0.34,
    "active.doomed": 0.40,
    "active.terminal_liability": 100.0,
    "active.premium": 0.08,
    "active.unready_fraction": 0.08,
    "active.retreat_ready": 0.04,
    "active.damage_pressure": 0.02,
    "combat.realization": 1.0,
    "ability.draw_cards": 0.062,
    "ability.search_cards": 0.10,
    "ability.damage_move": 0.321,
    "ability.healing": 0.25,
    "ability.acceleration": 0.25,
    "ability.denial": 0.20,
    "ability.resource_cost": -0.08,
    "ability.self_cost": -0.12,
    "ability.future": 0.12,
    "mobility.retreat_progress": 0.10,
    "resource.discard_recoverable": 0.022,
    "resource.opponent_hidden_option": 0.08,
    "resource.opponent_hidden_deck": 0.015,
    "prize.race": 1.0,
    "prize.overrun": 0.20,
    "result.win": 100.0,
    "belief.unknown_card": 0.02,
    "coverage.unknown_card": -0.25,
    "belief.unknown_deck_card": 0.0075,
    "belief.unknown_archetype": -0.02,
    "context.opponent_unknown_card": 0.01,
    "context.opponent_unknown_hand": 0.01,
    "context.opponent_unknown_deck": 0.002,
    "context.damaged_attached": -1.0,
    "context.damaged_active_threat": -1.0,
    "continuation.multi_provision_in_hand": 0.05,
    "continuation.zone_created": 0.01,
    "continuation.zone_replaced": 0.005,
    "continuation.allowance_consumed": -0.01,
    "continuation.usable_output": 0.012,
    "continuation.opportunity_created": 0.02,
    "continuation.opportunity_preserved": 0.002,
    "continuation.opportunity_consumed": -0.002,
    "continuation.information_value": 0.55,
    "function.gust.bench_target": 0.03,
    "function.heal.damage_present": 0.03,
    "function.accel.open_energy_slot": 0.04,
    "function.switch.active_pressure": 0.03,
    "function.disruption.opponent_hand": 0.005,
    "function.disruption.deck": 0.005,
    "function.denial.opponent_resource": 0.02,
    "function.bench_pressure.target_count": 0.01,
    "function.protection.incoming_pressure": 0.02,
    "function.status.active_target": 0.05,
    "function.cost_reduction.open_cost": 0.02,
    "function.self_cost.exposure": -0.04,
    "function.suppression.ability_target": 0.02,
    "function.development.board_fit": 0.02,
    "function.move_damage.damage_present": 0.03,
    "function.ko.active_target": 0.05,
    "function.ko.self_prize_liability": -1.0,
    "function.stadium.board_fit": 0.100,
    "function.attack.modifier": 0.03,
    "function.attack.copy_source": 0.03,
    "function.attack.piercing": 0.03,
    "function.energy.provision": 0.04,
    "action.opportunity_cost": 0.065,
    "status.asleep": 0.20,
    "status.paralyzed": 0.20,
    "status.confused": 0.15,
    "status.poisoned": 0.10,
    "status.burned": 0.15,
}

CLAUSE_PARAMETER_QUALIFIERS = frozenset((
    "allowance", "applies_to", "attack", "choice", "chooser", "cost",
    "cost_required", "cost_units", "dest", "dig", "dig_from",
    "distinct_types", "duration", "each_of", "effect", "energy",
    "energy_type", "evolves_into_type", "exclude_name", "granted_action",
    "hp_max", "includes_effects", "name", "name_family", "named",
    "new_weakness", "no_ability", "no_rule_box", "no_stack", "on",
    "optional", "random", "restriction", "rider", "rider_amount",
    "rider_energy_type", "scope", "source", "source_class", "symmetric",
    "target", "target_class", "target_condition", "target_type", "timing",
    "trigger", "type", "window", "zone",
))

OPTION_DEFAULTS = MappingProxyType({
    "option.hp": 0.02,
    "option.attack": 0.12,
    "option.draw": 0.08,
    "option.search": 0.10,
    "option.acceleration": 0.25,
    "option.denial": 0.30,
    "option.healing": 0.25,
    "option.mobility": 0.10,
    "option.energy": 0.10,
    "option.cost": -0.10,
})

OPTION_DEPTH_DEFAULTS = MappingProxyType({
    f"option.depth.{key.removeprefix('option.')}": -value / 2
    for key, value in OPTION_DEFAULTS.items()
} | {
    "option.depth.ability.damage_move": -_SCALAR_DEFAULTS["ability.damage_move"] / 2,
})

_BELIEF_DEFAULTS = {
    "mechanic.comeback_disruption": -0.04,
    "mechanic.damage_cap": -0.03,
    "mechanic.effect_immunity": -0.04,
    "mechanic.effect_immunity.ex_body_count": -0.02,
    "mechanic.hand_size_attack": -0.01,
    "mechanic.item_lock": -0.01,
    "mechanic.no_pivot": 0.03,
    "mechanic.no_pivot.retreat_cost": 0.01,
    "mechanic.piercing": -0.03,
    "mechanic.piercing.active_tools": -0.02,
    "mechanic.single_prize": -0.03,
    "mechanic.special_energy_only": 0.03,
    "mechanic.spread": -0.02,
    "trait.deckout_vulnerability": -0.002,
    "trait.heal_wall": -0.02,
    "trait.opening_fragility": 0.04,
    "trait.tempo.fast": -0.04,
    "trait.tempo.midrange": -0.02,
    "trait.tempo.slow": 0.02,
    "trait.tempo.fast.turn": -0.001,
    "trait.tempo.midrange.turn": -0.0005,
    "trait.tempo.slow.turn": 0.0005,
}


FEATURE_CATALOG = FeatureCatalog(
    tuple(FeatureSpec(key, value, rules=(
        *((_DECLARED_RULES[key],) if key in _DECLARED_RULES else ()),
        *((_rule("observation", (_OBSERVATION_CLAIMS[key],), "constant"),)
          if key in _OBSERVATION_CLAIMS else ()),
        *((_rule("continuation", (_CONTINUATION_CLAIMS[key],), "constant"),)
          if key in _CONTINUATION_CLAIMS else ()),
    ))
          for key, value in _SCALAR_DEFAULTS.items())
    + tuple(FeatureSpec(key, value, "posterior",
                        ((_TRAIT_RULES[key],) if key in _TRAIT_RULES
                         else (_MECHANIC_RULES[key],)))
            for key, value in _BELIEF_DEFAULTS.items())
    + tuple(FeatureSpec(f"kind.{kind}", value, "count",
                        (_rule("card", (f"kind:{kind}",), "constant"),))
            for kind, value in _KIND_DEFAULTS.items())
    + tuple(FeatureSpec(f"interaction.kind.{kind}.{placement}",
                        value * factor,
                        "situational_count",
                        (_rule("card", (f"kind:{kind}:{placement}",), "constant"),))
            for kind, value in _KIND_DEFAULTS.items()
            for placement in _KIND_PLACEMENTS[kind]
            for factor in (_PLACEMENT_FACTORS[placement],))
    + tuple(FeatureSpec(key, value, "option_units",
                        (_rule("option", (key,), "constant"),))
            for key, value in OPTION_DEFAULTS.items())
    + tuple(FeatureSpec(key, value, "option_depth_units",
                        (_rule("option_depth", (key,), "constant"),))
            for key, value in OPTION_DEPTH_DEFAULTS.items())
    + tuple(FeatureSpec(key, 0.0, disposition=FeatureDisposition.RETIRED)
            for key in (
                "resource.hand_option", "resource.stadium_option",
                "resource.deck_option", "resource.prize_locked",
                "resource.known_top_option",
                "combat.attack_now", "combat.attack_progress",
                "combat.attack_future", "combat.bench_reach",
                "combat.active_threat", "combat.line_potential",
                "combat.prize_phase_fit", "bench.developed_body",
                "combat.realized_ko",
                "development.hand_line", "development.next_turn_reach",
                "function.draw.available", "function.draw.hand_count",
                "function.fetch.live_target"))
    + tuple(FeatureSpec(
        f"clause.parameter.{parameter}", 0.0,
        disposition=FeatureDisposition.RETIRED)
            for parameter in CLAUSE_PARAMETER_QUALIFIERS),
    schema_version=24,
)


__all__ = ("ACTIVATION_OPERATIONS", "ActivationRule", "CLAUSE_PARAMETER_QUALIFIERS",
           "FEATURE_CATALOG",
           "OPTION_DEFAULTS", "OPTION_DEPTH_DEFAULTS",
           "FeatureCatalog", "FeatureDisposition", "FeatureSpec")
