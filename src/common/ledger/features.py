from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from types import MappingProxyType



CATALOG_ID_DIGEST_BYTES = 16


ACTIVATION_OPERATIONS = frozenset({
    "ability_target", "active_retreat_cost", "active_target", "active_tool_count",
    "bench_target", "board_body_count", "body_clause_count", "body_flag_count",
    "candidate_role_bodies", "constant", "evolution_target", "fetch_live_target",
    "incoming_pressure", "multi_provision_capacity", "open_cost", "open_energy_slot",
    "opponent_bench", "opponent_empty_bench",
    "opponent_damage_units", "opponent_deck_count", "opponent_energy_count",
    "opponent_hand_count", "opponent_single_prize_count",
    "opponent_special_energy_count", "own_bench_count", "own_damage_units",
    "own_hand_count", "own_item_count", "own_max_attack_units", "prize_difference",
    "side_damage_units", "side_hand_count", "side_status_count", "switch_target",
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


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    key: str
    default: float
    activation_shape: str = "scalar"
    rules: tuple[ActivationRule, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "key", str(self.key))
        object.__setattr__(self, "default", float(self.default))
        if not math.isfinite(self.default):
            raise ValueError("feature default must be finite")
        object.__setattr__(self, "activation_shape", str(self.activation_shape))
        object.__setattr__(self, "rules", tuple(self.rules))


class FeatureCatalog:
    def __init__(self, specs, *, schema_version: int):
        specs = tuple(specs)
        by_key = {spec.key: spec for spec in specs}
        if len(by_key) != len(specs):
            raise ValueError("feature keys must be unique")
        if any(not isinstance(rule, ActivationRule)
               for spec in specs for rule in spec.rules):
            raise TypeError("feature activation rules must be ActivationRule values")
        unknown_operations = {rule.operation for spec in specs for rule in spec.rules} \
            - ACTIVATION_OPERATIONS
        if unknown_operations:
            raise KeyError(f"unknown activation operation {sorted(unknown_operations)[0]!r}")
        self._specs = MappingProxyType(by_key)
        indexed = {}
        for spec in (by_key[key] for key in sorted(by_key)):
            for rule in spec.rules:
                for claim in rule.claims:
                    indexed.setdefault((rule.source, claim), []).append((spec, rule))
        self._rules_by_source_claim = MappingProxyType({
            key: tuple(value) for key, value in indexed.items()})
        self.schema_version = int(schema_version)

    def __contains__(self, key) -> bool:
        return str(key) in self._specs

    def __getitem__(self, key: str) -> FeatureSpec:
        return self._specs[str(key)]

    @property
    def priced_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    @property
    def specs(self) -> tuple[FeatureSpec, ...]:
        return tuple(self._specs[key] for key in sorted(self._specs))

    def activation_rules(self, source: str, claims) -> tuple[tuple[FeatureSpec, ActivationRule], ...]:
        found = {}
        for claim in {str(claim) for claim in claims}:
            for spec, rule in self._rules_by_source_claim.get((str(source), claim), ()):
                found[(spec.key, rule)] = (spec, rule)
        return tuple(found[key] for key in sorted(found, key=lambda item: (
            item[0], self[item[0]].rules.index(item[1]))))

    def has_activation_rules(self, source: str, claims) -> bool:
        return any((str(source), str(claim)) in self._rules_by_source_claim
                   for claim in claims)

    @property
    def identity(self) -> str:
        payload = {
            "schema_version": self.schema_version,
            "specs": tuple((spec.key, spec.default, spec.activation_shape,
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
    "function.draw.available": _rule("function", ("draw",), "constant"),
    "function.draw.hand_count": _rule("function", ("draw",), "side_hand_count"),
    "function.fetch.live_target": _rule("function", ("fetch",), "fetch_live_target"),
    "function.gust.bench_target": _rule("function", ("gust",), "bench_target"),
    "function.heal.damage_present": _rule("function", ("heal",), "side_damage_units"),
    "function.accel.open_energy_slot": _rule(
        "function", ("accel", "energy_double", "energy_recur", "move_energy"),
        "open_energy_slot"),
    "function.switch.active_pressure": _rule(
        "function", ("self_switch", "switch_self", "push_out"), "switch_target"),
    "function.disruption.opponent_hand": _rule(
        "function", ("opp_hand_to_deck", "mill"), "opponent_hand_count"),
    "function.denial.opponent_resource": _rule(
        "function", ("discard_opp_energy", "energy_bounce", "item_lock", "attack_lock",
                     "no_retreat", "retreat_lock"), "opponent_energy_count"),
    "function.bench_pressure.target_count": _rule(
        "function", ("bench_snipe", "bench_spread", "damage_counters"),
        "opponent_bench"),
    "function.protection.incoming_pressure": _rule(
        "function", ("damage_protection", "damage_reduction", "prevent_damage",
                     "prevent_effects", "hp_bonus"), "incoming_pressure"),
    "function.status.active_target": _rule(
        "function", ("attack_debuff", "confuse", "sleep"), "active_target"),
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
    "function.stadium.board_fit": _rule(
        "function", ("stadium_static", "stadium_trigger"), "board_body_count"),
    "continuation.multi_provision_in_hand": _rule(
        "function", ("energy_provide",), "multi_provision_capacity"),
    "energy.end_of_turn_rental": _rule(
        "attached_energy", ("discard_eot",), "constant"),
}

_OBSERVATION_CLAIMS = {
    "zone.in_play": "card_in_play",
    "zone.in_hand": "card_in_hand",
    "zone.in_deck": "card_in_deck",
    "zone.in_discard": "card_in_discard",
    "zone.under_body": "card_under_body",
    "zone.attached_usable": "usable_attached_energy",
    "zone.attached_useless": "useless_attached_energy",
    "zone.tool_attached": "attached_tool",
    "demand.dead": "dead_hand_card",
    "demand.colorless_only": "colorless_only_hand_card",
    "demand.setup": "setup_hand_card",
    "development.ready_evolution": "evolution_access",
    "development.visible_reach": "visible_development_reach",
    "development.next_turn_reach": "next_turn_development_reach",
    "copy.surplus": "surplus_hand_copy",
    "copy.surplus_in_play": "surplus_in_play_copy",
    "copy.basic_energy_surplus": "surplus_basic_energy",
    "interaction.synergy.in_hand": "synergy_in_hand",
    "damage.floor": "body_damage_fraction",
    "body.hp_per_100": "body_hp_units",
    "bench.open_slot": "open_bench_slot",
    "body.prize_liability": "extra_prize_liability",
    "energy.concentration": "concentrated_energy",
    "active.doomed": "doomed_active",
    "active.premium": "active_body",
    "active.unready_fraction": "unready_active",
    "active.retreat_ready": "retreat_ready_active",
    "active.damage_pressure": "active_damage_pressure",
    "combat.attack_now": "attack_now",
    "combat.attack_progress": "attack_progress",
    "combat.attack_future": "attack_future",
    "combat.bench_reach": "bench_reach",
    "combat.active_threat": "active_threat",
    "combat.line_potential": "line_potential",
    "combat.realized_ko": "realized_knockout",
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
    "resource.hand_option": "hand_option_value",
    "resource.discard_recoverable": "recoverable_discard_card",
    "resource.stadium_option": "stadium_option_value",
    "resource.opponent_hidden_option": "opponent_hidden_option_value",
    "resource.deck_option": "deck_option_value",
    "resource.opponent_hidden_deck": "opponent_hidden_deck_value",
    "resource.prize_locked": "known_prize_option_value",
    "prize.race": "prize_advantage",
    "result.win": "terminal_win",
    "belief.unknown_card": "unknown_card_belief",
    "coverage.unknown_card": "uncovered_card",
    "belief.unknown_deck_card": "unknown_own_deck_card",
    "belief.unknown_archetype": "unknown_opponent_archetype",
    "context.opponent_unknown_card": "unknown_opponent_card",
    "context.opponent_unknown_hand": "unknown_opponent_hand_card",
    "context.opponent_unknown_deck": "unknown_opponent_deck_card",
    "context.damaged_attached": "usable_energy_on_damaged_body",
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
    "development.visible_reach": 0.0,
    "development.next_turn_reach": 0.0,
    "copy.surplus": -0.03,
    "copy.surplus_in_play": 0.0,
    "copy.basic_energy_surplus": -0.04,
    "interaction.synergy.in_hand": 0.40,
    "damage.floor": 0.30,
    "body.hp_per_100": 0.02,
    "bench.open_slot": 0.15,
    "body.prize_liability": 0.04,
    "energy.concentration": 0.10,
    "active.doomed": 0.40,
    "active.premium": 0.08,
    "active.unready_fraction": 0.0,
    "active.retreat_ready": 0.0,
    "active.damage_pressure": 0.0,
    "combat.attack_now": 0.35,
    "combat.attack_progress": 0.20,
    "combat.attack_future": 0.12,
    "combat.bench_reach": 0.10,
    "combat.active_threat": 0.12,
    "combat.line_potential": 0.40,
    "combat.realized_ko": 1.0,
    "ability.draw_cards": 0.08,
    "ability.search_cards": 0.10,
    "ability.damage_move": 0.30,
    "ability.healing": 0.25,
    "ability.acceleration": 0.25,
    "ability.denial": 0.20,
    "ability.resource_cost": -0.08,
    "ability.self_cost": -0.12,
    "ability.future": 0.12,
    "mobility.retreat_progress": 0.10,
    "resource.hand_option": 0.15,
    "resource.discard_recoverable": 0.08,
    "resource.stadium_option": 0.20,
    "resource.opponent_hidden_option": 0.08,
    "resource.deck_option": 0.10,
    "resource.opponent_hidden_deck": 0.015,
    "resource.prize_locked": -0.08,
    "prize.race": 1.0,
    "result.win": 100.0,
    "belief.unknown_card": 0.0,
    "coverage.unknown_card": 0.0,
    "belief.unknown_deck_card": 0.0075,
    "belief.unknown_archetype": 0.0,
    "context.opponent_unknown_card": 0.0,
    "context.opponent_unknown_hand": 0.0,
    "context.opponent_unknown_deck": 0.0,
    "context.damaged_attached": -1.0,
    "continuation.multi_provision_in_hand": 0.05,
    "energy.end_of_turn_rental": 0.0,
    "continuation.zone_created": 0.0,
    "continuation.zone_replaced": 0.0,
    "continuation.allowance_consumed": 0.0,
    "continuation.usable_output": 0.0,
    "continuation.opportunity_created": 0.0,
    "continuation.opportunity_preserved": 0.0,
    "continuation.opportunity_consumed": 0.0,
    "continuation.information_value": 0.55,
    "function.draw.available": 0.0,
    "function.draw.hand_count": 0.0,
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
    "action.opportunity_cost": 0.0,
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
    "mechanic.effect_immunity.ex_body_count": 0.0,
    "mechanic.hand_size_attack": 0.0,
    "mechanic.item_lock": 0.0,
    "mechanic.no_pivot": 0.0,
    "mechanic.no_pivot.retreat_cost": 0.0,
    "mechanic.piercing": 0.0,
    "mechanic.piercing.active_tools": 0.0,
    "mechanic.single_prize": 0.0,
    "mechanic.special_energy_only": 0.0,
    "mechanic.spread": 0.0,
    "trait.deckout_vulnerability": 0.0,
    "trait.heal_wall": 0.0,
    "trait.opening_fragility": 0.0,
    "trait.tempo.fast": 0.0,
    "trait.tempo.midrange": 0.0,
    "trait.tempo.slow": 0.0,
    "trait.tempo.fast.turn": 0.0,
    "trait.tempo.midrange.turn": 0.0,
    "trait.tempo.slow.turn": 0.0,
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
            for factor in (_PLACEMENT_FACTORS[placement],)),
    schema_version=4,
)


__all__ = ("ACTIVATION_OPERATIONS", "ActivationRule", "FEATURE_CATALOG",
           "FeatureCatalog", "FeatureSpec")
