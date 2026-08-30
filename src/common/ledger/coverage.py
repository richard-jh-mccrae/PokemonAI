from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from types import MappingProxyType

from common.cards import FUNCTION_CATALOG, card_clauses, card_store
from common.cards.card_facts import EnergyCard, PokemonCard, TrainerCard
from common.observation.knowledge import (
    KnownAttackLocks, KnownDeckTop, KnownOwnPrizes, LegalKnowledge,
    OpponentBelief, OpponentCandidatePosterior, OpponentDecisionEvidence,
)
from common.observation.nodes import (
    Body, Card, CardBag, HiddenHand, Looking, Option, SelectPrompt, Side, Turn,
    VisibleHand,
)
from common.observation.state import ObservationEvent, ObservationState

from .features import FEATURE_CATALOG


OBSERVATION_FIELD_OWNERS = {
    ObservationState: {
        "seat": "identity", "me": "container", "them": "container", "turn": "container",
        "stadium": "value", "looking": "legal", "select": "legal",
        "decklist": "identity", "deck_counts": "value", "knowledge": "container",
        "legal_actions": "legal", "events": "container", "_pieces": "identity",
    },
    Side: {
        "active": "value", "active_hidden": "belief", "bench": "value",
        "bench_max": "value", "deck_count": "value", "hand": "value",
        "hand_count": "value", "discard": "value", "prize_count": "value",
        "poisoned": "value", "burned": "value", "asleep": "value",
        "paralyzed": "value", "confused": "value",
    },
    Body: {
        "card": "container", "hp": "value", "max_hp": "value",
        "appeared_this_turn": "value", "energies": "value",
        "energy_cards": "value", "tools": "value", "pre_evolution": "value",
        "digest": "identity",
    },
    Card: {"card_id": "value", "serial": "identity", "owner": "value"},
    Turn: {
        "number": "value", "first_player": "conditional", "supporter_played": "conditional",
        "stadium_played": "legal", "energy_attached": "conditional",
        "retreated": "conditional", "result": "value",
    },
    Looking: {"count": "legal", "cards": "legal"},
    SelectPrompt: {
        "type": "legal", "context": "legal", "min_count": "legal",
        "max_count": "legal", "remain_damage_counter": "legal",
        "remain_energy_cost": "legal", "options": "legal", "deck": "legal",
        "context_card": "legal", "effect": "legal",
    },
    CardBag: {"cards": "container", "counts": "identity", "digest": "identity"},
    VisibleHand: {"bag": "container"},
    HiddenHand: {"count": "alias"},
    Option: {
        "area": "legal", "attackId": "legal", "cardId": "legal",
        "count": "legal", "energyIndex": "legal", "inPlayArea": "legal",
        "inPlayIndex": "legal", "index": "legal", "number": "legal",
        "playerIndex": "legal", "serial": "identity",
        "specialConditionType": "legal", "toolIndex": "legal", "type": "legal",
    },
    KnownOwnPrizes: {"cards": "value"},
    KnownDeckTop: {"cards": "value"},
    KnownAttackLocks: {"locks": "legal"},
    OpponentCandidatePosterior: {"archetype": "belief", "probability": "belief"},
    OpponentDecisionEvidence: {
        "snapshot_identity": "identity", "candidates": "container",
        "revealed_card_ids": "identity", "in_play_card_ids": "identity",
        "public_resources": "identity", "unknown_mass": "belief",
        "failures": "identity", "public_events": "identity",
    },
    OpponentBelief: {
        "evidence": "identity", "probabilities": "identity",
        "decision_evidence": "container",
    },
    LegalKnowledge: {
        "own_prizes": "container", "known_top": "container",
        "attack_locks": "legal", "opponent": "container",
    },
    ObservationEvent: {
        "kind": "value", "public_fields": "value",
        "recognized": "value",
    },
}

OBSERVATION_FIELD_FEATURES = MappingProxyType({
    "ObservationState.stadium": ("option.search",),
    "ObservationState.deck_counts": ("option.attack",),
    "Side.active": ("active.premium",),
    "Side.active_hidden": ("belief.unknown_card",),
    "Side.bench": ("combat.realization", "body.development", "bench.full"),
    "Side.bench_max": ("bench.open_slot",),
    "Side.deck_count": ("resource.opponent_hidden_deck",),
    "Side.hand": ("option.attack",),
    "Side.hand_count": ("resource.opponent_hidden_option",),
    "Side.discard": ("zone.in_discard",),
    "Side.prize_count": ("prize.race", "prize.overrun"),
    "Side.poisoned": ("status.poisoned",),
    "Side.burned": ("status.burned",),
    "Side.asleep": ("status.asleep",),
    "Side.paralyzed": ("status.paralyzed",),
    "Side.confused": ("status.confused",),
    "Body.hp": ("damage.floor",),
    "Body.max_hp": ("body.hp_per_100",),
    "Body.appeared_this_turn": ("development.visible_reach",),
    "Body.energies": ("zone.attached_usable",),
    "Body.energy_cards": ("interaction.kind.energy.attached_usable",),
    "Body.tools": ("zone.tool_attached",),
    "Body.pre_evolution": ("zone.under_body",),
    "Card.card_id": ("combat.realization",),
    "Card.owner": ("option.search",),
    "Turn.number": ("development.visible_reach",),
    "Turn.first_player": ("ability.search_cards",),
    "Turn.supporter_played": ("option.draw",),
    "Turn.energy_attached": ("option.energy",),
    "Turn.retreated": ("function.attack.modifier", "option.energy"),
    "Turn.result": ("result.win",),
    "KnownOwnPrizes.cards": ("option.search",),
    "KnownDeckTop.cards": ("option.search",),
    "OpponentCandidatePosterior.archetype": (
        "trait.tempo.fast", "trait.tempo.slow"),
    "OpponentCandidatePosterior.probability": ("trait.tempo.fast",),
    "OpponentDecisionEvidence.unknown_mass": ("belief.unknown_archetype",),
    "ObservationEvent.kind": ("ability.draw_cards",),
    "ObservationEvent.public_fields": ("ability.draw_cards",),
    "ObservationEvent.recognized": ("ability.draw_cards",),
})

OBSERVATION_FIELD_EXPECTATIONS = MappingProxyType({
    f"{node.__name__}.{name}": owner in {"value", "belief", "conditional"}
    for node, owners in OBSERVATION_FIELD_OWNERS.items()
    for name, owner in owners.items()
})


class ClauseValuationMode(str, Enum):
    DIRECT_EQUATION = "direct-equation"
    SUCCESSOR_DELTA = "successor-delta"


class ClauseParameterDirection(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    EFFECT = "effect"
    EXCLUSION = "exclusion"
    OPPONENT_EFFECT = "opponent-effect"
    RIDER = "rider"
    TARGET = "target"


CLAUSE_PARAMETER_CONTRACTS = MappingProxyType({
    "allowance": ClauseValuationMode.DIRECT_EQUATION,
    "amount": ClauseValuationMode.DIRECT_EQUATION,
    "amount_if": ClauseValuationMode.DIRECT_EQUATION,
    "amount_on_evolution": ClauseValuationMode.DIRECT_EQUATION,
    "amount_per": ClauseValuationMode.DIRECT_EQUATION,
    "applies_to": ClauseValuationMode.DIRECT_EQUATION,
    "attack": ClauseValuationMode.DIRECT_EQUATION,
    "choice": ClauseValuationMode.DIRECT_EQUATION,
    "chooser": ClauseValuationMode.DIRECT_EQUATION,
    "condition": ClauseValuationMode.DIRECT_EQUATION,
    "condition_energy_type": ClauseValuationMode.DIRECT_EQUATION,
    "cost": ClauseValuationMode.DIRECT_EQUATION,
    "cost_required": ClauseValuationMode.DIRECT_EQUATION,
    "cost_units": ClauseValuationMode.DIRECT_EQUATION,
    "count": ClauseValuationMode.DIRECT_EQUATION,
    "dest": ClauseValuationMode.DIRECT_EQUATION,
    "dig": ClauseValuationMode.DIRECT_EQUATION,
    "dig_from": ClauseValuationMode.DIRECT_EQUATION,
    "distinct_types": ClauseValuationMode.DIRECT_EQUATION,
    "duration": ClauseValuationMode.DIRECT_EQUATION,
    "each_of": ClauseValuationMode.DIRECT_EQUATION,
    "effect": ClauseValuationMode.DIRECT_EQUATION,
    "energy": ClauseValuationMode.DIRECT_EQUATION,
    "energy_type": ClauseValuationMode.DIRECT_EQUATION,
    "evolves_into_type": ClauseValuationMode.DIRECT_EQUATION,
    "exclude_name": ClauseValuationMode.DIRECT_EQUATION,
    "granted_action": ClauseValuationMode.DIRECT_EQUATION,
    "hp_max": ClauseValuationMode.DIRECT_EQUATION,
    "includes_effects": ClauseValuationMode.DIRECT_EQUATION,
    "name": ClauseValuationMode.DIRECT_EQUATION,
    "name_family": ClauseValuationMode.DIRECT_EQUATION,
    "named": ClauseValuationMode.DIRECT_EQUATION,
    "new_weakness": ClauseValuationMode.DIRECT_EQUATION,
    "no_ability": ClauseValuationMode.DIRECT_EQUATION,
    "no_rule_box": ClauseValuationMode.DIRECT_EQUATION,
    "no_stack": ClauseValuationMode.DIRECT_EQUATION,
    "on": ClauseValuationMode.DIRECT_EQUATION,
    "opponent_amount": ClauseValuationMode.DIRECT_EQUATION,
    "opponent_amount_if": ClauseValuationMode.DIRECT_EQUATION,
    "optional": ClauseValuationMode.DIRECT_EQUATION,
    "per": ClauseValuationMode.DIRECT_EQUATION,
    "random": ClauseValuationMode.DIRECT_EQUATION,
    "remaining_hp": ClauseValuationMode.DIRECT_EQUATION,
    "restriction": ClauseValuationMode.DIRECT_EQUATION,
    "rider": ClauseValuationMode.DIRECT_EQUATION,
    "rider_amount": ClauseValuationMode.DIRECT_EQUATION,
    "rider_energy_type": ClauseValuationMode.DIRECT_EQUATION,
    "scope": ClauseValuationMode.DIRECT_EQUATION,
    "source": ClauseValuationMode.DIRECT_EQUATION,
    "source_class": ClauseValuationMode.DIRECT_EQUATION,
    "symmetric": ClauseValuationMode.DIRECT_EQUATION,
    "target": ClauseValuationMode.DIRECT_EQUATION,
    "target_class": ClauseValuationMode.DIRECT_EQUATION,
    "target_condition": ClauseValuationMode.DIRECT_EQUATION,
    "target_type": ClauseValuationMode.DIRECT_EQUATION,
    "timing": ClauseValuationMode.DIRECT_EQUATION,
    "to_hand": ClauseValuationMode.DIRECT_EQUATION,
    "to_hand_size": ClauseValuationMode.DIRECT_EQUATION,
    "trigger": ClauseValuationMode.DIRECT_EQUATION,
    "type": ClauseValuationMode.DIRECT_EQUATION,
    "window": ClauseValuationMode.DIRECT_EQUATION,
    "zone": ClauseValuationMode.DIRECT_EQUATION,
})

CLAUSE_PARAMETER_DIRECTION_CONTRACTS = MappingProxyType({
    "allowance": ClauseParameterDirection.POSITIVE,
    "applies_to": ClauseParameterDirection.EFFECT,
    "attack": ClauseParameterDirection.NEGATIVE,
    "choice": ClauseParameterDirection.POSITIVE,
    "chooser": ClauseParameterDirection.NEGATIVE,
    "cost": ClauseParameterDirection.NEGATIVE,
    "cost_required": ClauseParameterDirection.NEGATIVE,
    "cost_units": ClauseParameterDirection.NEGATIVE,
    "dest": ClauseParameterDirection.POSITIVE,
    "dig": ClauseParameterDirection.POSITIVE,
    "dig_from": ClauseParameterDirection.POSITIVE,
    "distinct_types": ClauseParameterDirection.POSITIVE,
    "duration": ClauseParameterDirection.POSITIVE,
    "each_of": ClauseParameterDirection.EFFECT,
    "effect": ClauseParameterDirection.EFFECT,
    "energy": ClauseParameterDirection.POSITIVE,
    "energy_type": ClauseParameterDirection.POSITIVE,
    "evolves_into_type": ClauseParameterDirection.POSITIVE,
    "exclude_name": ClauseParameterDirection.EXCLUSION,
    "granted_action": ClauseParameterDirection.POSITIVE,
    "hp_max": ClauseParameterDirection.POSITIVE,
    "includes_effects": ClauseParameterDirection.POSITIVE,
    "name": ClauseParameterDirection.POSITIVE,
    "name_family": ClauseParameterDirection.POSITIVE,
    "named": ClauseParameterDirection.POSITIVE,
    "new_weakness": ClauseParameterDirection.POSITIVE,
    "no_ability": ClauseParameterDirection.POSITIVE,
    "no_rule_box": ClauseParameterDirection.POSITIVE,
    "no_stack": ClauseParameterDirection.NEGATIVE,
    "on": ClauseParameterDirection.EFFECT,
    "optional": ClauseParameterDirection.POSITIVE,
    "random": ClauseParameterDirection.NEGATIVE,
    "restriction": ClauseParameterDirection.NEGATIVE,
    "rider": ClauseParameterDirection.RIDER,
    "rider_amount": ClauseParameterDirection.RIDER,
    "rider_energy_type": ClauseParameterDirection.POSITIVE,
    "scope": ClauseParameterDirection.POSITIVE,
    "source": ClauseParameterDirection.POSITIVE,
    "source_class": ClauseParameterDirection.POSITIVE,
    "symmetric": ClauseParameterDirection.OPPONENT_EFFECT,
    "target": ClauseParameterDirection.TARGET,
    "target_class": ClauseParameterDirection.POSITIVE,
    "target_condition": ClauseParameterDirection.POSITIVE,
    "target_type": ClauseParameterDirection.POSITIVE,
    "timing": ClauseParameterDirection.POSITIVE,
    "trigger": ClauseParameterDirection.POSITIVE,
    "type": ClauseParameterDirection.POSITIVE,
    "window": ClauseParameterDirection.POSITIVE,
    "zone": ClauseParameterDirection.POSITIVE,
})

CLAUSE_EFFECT_DIRECTIONS = MappingProxyType({
    "attack_fails_on_tails": -1,
    "damage_boost": 1,
    "damage_counters": -1,
    "damage_protection": 1,
    "damage_reduction": 1,
    "discard_opp_energy": 1,
    "evolve_early": 1,
    "gust": 1,
    "prevent_damage": 1,
    "prevent_damage_counters": 1,
    "shuffle_into_deck": 1,
    "special_condition_immunity": 1,
})

CLAUSE_RIDER_DIRECTIONS = MappingProxyType({
    "attached_cards_too": 1,
    "both_hands_to_bottom": 1,
    "bounce_energy_to_hand": -1,
    "confuse_target": 1,
    "cure_existing": 1,
    "damage_new_active": 1,
    "discard_basic_f_energy": -1,
    "discard_eot": -1,
    "discard_own_energy": -1,
    "discard_remainder": -1,
    "draw_1": 1,
    "heal_30_target": 1,
    "other_to_bottom": -1,
    "poison_new_active": 1,
    "recoil": -1,
    "self_ko": -1,
    "self_switch": 1,
    "shuffle_before_place": 1,
    "shuffle_both_hands": 1,
    "shuffle_counted_into_deck": -1,
    "shuffle_own_hand_in": -1,
    "shuffle_self_in": -1,
    "skip_stage1": 1,
})

CLAUSE_HARMFUL_OWN_TARGETS = frozenset({
    ("bench_spread", "own_bench"),
    ("confuse", "self"),
    ("energy_bounce", "self"),
    ("ko", "both_actives"),
    ("mill", "self"),
})


def clause_effect_direction(clause):
    if clause.effect == "hp_delta":
        return 1 if float(clause.amount) > 0 else -1
    if clause.effect is not None:
        return CLAUSE_EFFECT_DIRECTIONS[str(clause.effect)]
    if clause.kind == "ability_suppression":
        return -1
    return 1


def clause_parameter_expected_direction(parameter, value, clause):
    contract = CLAUSE_PARAMETER_DIRECTION_CONTRACTS[str(parameter)]
    if contract is ClauseParameterDirection.POSITIVE:
        return 1
    if contract is ClauseParameterDirection.NEGATIVE:
        return -1
    if contract is ClauseParameterDirection.EFFECT:
        return clause_effect_direction(clause)
    if contract is ClauseParameterDirection.EXCLUSION:
        return (1 if clause.kind == "checkup_trigger"
                and clause.effect == "damage_counters" else -1)
    if contract is ClauseParameterDirection.OPPONENT_EFFECT:
        return -clause_effect_direction(clause)
    if contract is ClauseParameterDirection.RIDER:
        return CLAUSE_RIDER_DIRECTIONS[str(clause.rider)]
    if contract is ClauseParameterDirection.TARGET:
        return -1 if (clause.kind, str(value)) in CLAUSE_HARMFUL_OWN_TARGETS else 1
    raise AssertionError(f"unhandled direction contract {contract!r}")


CLAUSE_PRIMARY_PARAMETER_FEATURES = MappingProxyType({
    ("amount", "accel"): "function.accel.open_energy_slot",
    ("amount", "attack_cost_reduction"): "function.cost_reduction.open_cost",
    ("amount", "attack_debuff"): "function.status.active_target",
    ("amount", "bench_snipe"): "function.bench_pressure.target_count",
    ("amount", "bench_spread"): "function.bench_pressure.target_count",
    ("amount", "checkup_trigger"): "ability.damage_move",
    ("amount", "coin"): "function.attack.modifier",
    ("amount", "cost_reduction"): "function.cost_reduction.open_cost",
    ("amount", "damage_boost"): "function.attack.modifier",
    ("amount", "damage_counters"): "function.bench_pressure.target_count",
    ("amount", "damage_reduction"): "function.protection.incoming_pressure",
    ("amount", "deck_top"): "option.search",
    ("amount", "discard_opp_energy"): "function.denial.opponent_resource",
    ("amount", "draw"): "ability.draw_cards",
    ("amount", "energy_bounce"): "function.denial.opponent_resource",
    ("amount", "energy_provide"): "function.energy.provision",
    ("amount", "energy_recur"): "function.accel.open_energy_slot",
    ("amount", "fetch"): "ability.search_cards",
    ("amount", "gust"): "function.gust.bench_target",
    ("amount", "heal"): "function.heal.damage_present",
    ("amount", "hp_bonus"): "function.protection.incoming_pressure",
    ("amount", "mill"): "function.disruption.deck",
    ("amount", "move_damage"): "function.move_damage.damage_present",
    ("amount", "move_energy"): "function.accel.open_energy_slot",
    ("amount", "opp_hand_to_deck"): "function.disruption.opponent_hand",
    ("amount", "recoil"): "function.self_cost.exposure",
    ("amount", "requires_bench_count"): "combat.realization",
    ("amount", "retreat_reduction"): "function.cost_reduction.open_cost",
    ("amount", "self_discard_energy"): "function.self_cost.exposure",
    ("amount", "self_mill"): "function.self_cost.exposure",
    ("amount", "stadium_static"): "function.stadium.board_fit",
    ("amount", "stadium_trigger"): "function.stadium.board_fit",
    ("amount_if", "draw"): "ability.draw_cards",
    ("amount_on_evolution", "energy_provide"):
        "continuation.multi_provision_in_hand",
    ("amount_per", "draw"): "ability.draw_cards",
    ("amount_per", "hp_bonus"): "function.protection.incoming_pressure",
    ("condition", "ability_suppression"): "function.suppression.ability_target",
    ("condition", "accel"): "function.accel.open_energy_slot",
    ("condition", "attack_cost_reduction"): "function.cost_reduction.open_cost",
    ("condition", "attack_twice"): "combat.realization",
    ("condition", "cost_reduction"): "function.cost_reduction.open_cost",
    ("condition", "damage_boost"): "function.attack.modifier",
    ("condition", "draw"): "ability.draw_cards",
    ("condition", "evolve_early"): "function.development.board_fit",
    ("condition", "fetch"): "ability.search_cards",
    ("condition", "first_turn_attack_permission"): "ability.search_cards",
    ("condition", "gust"): "function.gust.bench_target",
    ("condition", "heal"): "function.heal.damage_present",
    ("condition", "move_damage"): "function.move_damage.damage_present",
    ("condition", "prevent_damage"): "function.protection.incoming_pressure",
    ("condition", "self_shuffle_in"): "function.self_cost.exposure",
    ("condition", "stadium_static"): "function.stadium.board_fit",
    ("condition", "survive_ko"): "ability.denial",
    ("condition_energy_type", "move_damage"): "function.move_damage.damage_present",
    ("count", "bench_snipe"): "combat.realization",
    ("count", "coin"): "function.attack.modifier",
    ("opponent_amount", "draw"): "ability.resource_cost",
    ("opponent_amount_if", "draw"): "ability.resource_cost",
    ("per", "coin"): "function.attack.modifier",
    ("per", "damage_boost"): "function.attack.modifier",
    ("per", "damage_counters"): "function.bench_pressure.target_count",
    ("remaining_hp", "survive_ko"): "ability.denial",
    ("to_hand", "accel"): "option.acceleration",
    ("to_hand_size", "draw"): "ability.draw_cards",
})


def clause_primary_parameter_expected_direction(parameter, value, clause):
    parameter = str(parameter)
    if parameter == "amount":
        return -1 if clause.kind in {
            "recoil", "requires_bench_count", "self_discard_energy", "self_mill",
        } or (clause.kind == "mill" and clause.target == "self") \
            or (clause.kind == "bench_spread" and clause.target == "own_bench") \
            else 1
    if parameter == "amount_if":
        branch_amount = value.get("amount", value.get("to_hand_size", 0))
        base_amount = clause.amount if clause.amount is not None else clause.to_hand_size or 0
        return 1 if float(branch_amount) > float(base_amount) else -1
    if parameter in {
            "amount_on_evolution", "amount_per", "condition_energy_type", "count",
            "remaining_hp", "to_hand", "to_hand_size"}:
        return 1
    if parameter == "condition":
        return -1 if clause.kind == "self_shuffle_in" else 1
    if parameter in {"opponent_amount", "opponent_amount_if"}:
        return -1
    if parameter == "per":
        return -1 if value == "heads" else 1
    raise KeyError(f"no primary direction contract for {parameter!r}")


def clause_parameter_sensitivity_contract(parameter, value, clause, placement=None):
    parameter = str(parameter)
    if parameter in CLAUSE_PARAMETER_DIRECTION_CONTRACTS:
        return (None, clause_parameter_expected_direction(parameter, value, clause))
    feature = CLAUSE_PRIMARY_PARAMETER_FEATURES[(parameter, clause.kind)]
    if placement == "trainer" and clause.kind == "draw" \
            and not parameter.startswith("opponent_amount"):
        feature = "option.draw"
    if placement == "trainer" and clause.kind == "fetch":
        feature = "option.search"
    if parameter == "condition" and clause.kind == "fetch" \
            and placement == "ability":
        feature = "ability.search_cards"
    return (feature,
            clause_primary_parameter_expected_direction(parameter, value, clause))


CLAUSE_PARAMETER_DIRECT_EQUATIONS = MappingProxyType({
    "allowance": "evaluate._situational_functions",
    "amount": "capabilities.clause_value_units",
    "amount_if": "cards.functions.draw.draw_branches",
    "amount_on_evolution": "activation._provision",
    "amount_per": "capabilities._per_units",
    "applies_to": "evaluate._situational_functions",
    "attack": "evaluate._situational_functions",
    "choice": "evaluate._situational_functions",
    "chooser": "evaluate._situational_functions",
    "condition": "capabilities._condition_probability",
    "condition_energy_type": "capabilities._condition_probability",
    "cost": "capabilities.clause_cost_units",
    "cost_required": "evaluate._situational_functions",
    "cost_units": "evaluate._situational_functions",
    "count": "capabilities.clause_value_units",
    "dest": "evaluate._situational_functions",
    "dig": "evaluate._situational_functions",
    "dig_from": "evaluate._situational_functions",
    "distinct_types": "evaluate._situational_functions",
    "duration": "evaluate._situational_functions",
    "each_of": "evaluate._situational_functions",
    "effect": "evaluate._situational_functions",
    "energy": "evaluate._situational_functions",
    "energy_type": "evaluate._situational_functions",
    "evolves_into_type": "evaluate._situational_functions",
    "exclude_name": "evaluate._situational_functions",
    "granted_action": "evaluate._situational_functions",
    "hp_max": "evaluate._situational_functions",
    "includes_effects": "evaluate._situational_functions",
    "name": "evaluate._situational_functions",
    "name_family": "evaluate._situational_functions",
    "named": "evaluate._situational_functions",
    "new_weakness": "evaluate._situational_functions",
    "no_ability": "evaluate._situational_functions",
    "no_rule_box": "evaluate._situational_functions",
    "no_stack": "evaluate._situational_functions",
    "on": "evaluate._situational_functions",
    "opponent_amount": "cards.functions.draw.draw_branches",
    "opponent_amount_if": "cards.functions.draw.draw_branches",
    "optional": "evaluate._situational_functions",
    "per": "capabilities._per_units",
    "random": "evaluate._situational_functions",
    "remaining_hp": "capabilities._ability_capability",
    "restriction": "evaluate._situational_functions",
    "rider": "capabilities.clause_rider_cost_units",
    "rider_amount": "evaluate._situational_functions",
    "rider_energy_type": "evaluate._situational_functions",
    "scope": "evaluate._situational_functions",
    "source": "evaluate._situational_functions",
    "source_class": "evaluate._situational_functions",
    "symmetric": "evaluate._situational_functions",
    "target": "activation.target_transforms",
    "target_class": "evaluate._situational_functions",
    "target_condition": "evaluate._situational_functions",
    "target_type": "evaluate._situational_functions",
    "timing": "evaluate._situational_functions",
    "to_hand": "capabilities.card_option_units",
    "to_hand_size": "cards.functions.draw.draw_branches",
    "trigger": "evaluate._situational_functions",
    "type": "evaluate._situational_functions",
    "window": "evaluate._situational_functions",
    "zone": "evaluate._situational_functions",
})

CLAUSE_PARAMETER_BRANCH_CONTRACTS = MappingProxyType({
    "amount_if": MappingProxyType({
        "all_own_pokemon_team_rocket": frozenset({"to_hand_size"}),
        "coin_tails": frozenset({"amount"}),
        "exactly_6_prizes_remaining": frozenset({"amount"}),
        "hand_size_10_plus_after_draw": frozenset({"amount"}),
        "opp_3_or_fewer_prizes": frozenset({"amount"}),
    }),
    "opponent_amount_if": MappingProxyType({
        "coin_tails": frozenset({"amount"}),
    }),
})

CLAUSE_PARAMETER_VALUE_CONTRACTS = MappingProxyType({
    "per": frozenset({
        "all_bench", "basic_energy_discarded_this_way", "basic_energy_in_opp_discard",
        "basic_energy_own_discard", "card_in_opp_hand", "card_in_own_hand",
        "damage_counter_on_self", "damage_counter_own_bench", "damage_counter_self",
        "energy_discarded_this_way", "energy_on_both_actives", "energy_on_opp_active",
        "energy_on_own_all", "ethans_adventure_in_own_discard", "heads", "my_ancient",
        "opp_bench", "opp_prizes_taken", "own_bench",
    }),
    "amount_per": frozenset({"attached_fighting_energy", "my_ancient", "their_bench"}),
    "cost": frozenset({
        "bottom_2", "discard_1", "discard_2", "discard_3", "discard_hand",
        "shuffle_3_energy_into_deck",
    }),
    "rider": frozenset({
        "attached_cards_too", "both_hands_to_bottom", "bounce_energy_to_hand",
        "confuse_target", "cure_existing", "damage_new_active", "discard_basic_f_energy",
        "discard_eot", "discard_own_energy", "discard_remainder", "draw_1",
        "heal_30_target", "other_to_bottom", "poison_new_active", "recoil", "self_ko",
        "self_switch", "shuffle_before_place", "shuffle_both_hands",
        "shuffle_counted_into_deck", "shuffle_own_hand_in", "shuffle_self_in",
        "skip_stage1",
    }),
    "condition": frozenset({
        "active_has_festival_lead", "bench_has_named", "damage_200_plus",
        "dark_energy_attached", "energy_3_plus", "festival_grounds_in_play",
        "first_turn", "full_hp", "going_second_first_turn",
        "more_prizes_remaining_than_opp", "moved_to_active_this_turn",
        "name_in_opp_discard", "not_first_turn", "once_per_turn_ability",
        "opp_active_damaged", "opp_active_ex", "other_ancient_attacked_last_turn",
        "own_bench_damaged", "played_supporter_this_turn", "pokemon_ko_last_turn",
        "remaining_hp_30_or_less", "self_active", "self_damage_counters_2_plus",
        "self_special_condition", "solrock_in_play", "team_rocket_energy_attached",
        "went_first",
    }),
    "target": frozenset({
        "any", "any_pokemon", "basic", "basic_energy", "basic_pokemon", "bench_only",
        "benched", "both_actives", "defending", "energy", "evolution", "future", "item",
        "mega", "opp_active", "opp_any", "opp_bench", "opp_dragon_pokemon", "opponent",
        "opponent_active", "own_bench", "own_line", "own_type", "pokemon",
        "pokemon_or_basic_energy", "pokemon_ex",
        "self", "stadium", "stage1", "stage2", "supporter", "tera", "tool", "trainer",
    }),
})

CLAUSE_PARAMETER_PLACEMENT_CONTRACTS = MappingProxyType({
    "cost": MappingProxyType({
        ("ability", "draw"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "bench_snipe"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "draw"): ClauseValuationMode.DIRECT_EQUATION,
        ("trainer", "draw"): ClauseValuationMode.DIRECT_EQUATION,
        ("trainer", "fetch"): ClauseValuationMode.DIRECT_EQUATION,
    }),
    "target": MappingProxyType({
        ("ability", "ability_suppression"): ClauseValuationMode.DIRECT_EQUATION,
        ("ability", "accel"): ClauseValuationMode.DIRECT_EQUATION,
        ("ability", "damage_boost"): ClauseValuationMode.DIRECT_EQUATION,
        ("ability", "damage_counters"): ClauseValuationMode.DIRECT_EQUATION,
        ("ability", "energy_recur"): ClauseValuationMode.DIRECT_EQUATION,
        ("ability", "fetch"): ClauseValuationMode.DIRECT_EQUATION,
        ("ability", "gust"): ClauseValuationMode.DIRECT_EQUATION,
        ("ability", "self_switch"): ClauseValuationMode.DIRECT_EQUATION,
        ("ability", "weakness_override"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "accel"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "attack_debuff"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "bench_snipe"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "bench_spread"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "coin"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "confuse"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "damage_counters"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "energy_bounce"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "energy_recur"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "fetch"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "gust"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "ko"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "mill"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "no_retreat"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "retreat_lock"): ClauseValuationMode.DIRECT_EQUATION,
        ("attack", "sleep"): ClauseValuationMode.DIRECT_EQUATION,
        ("energy", "fetch"): ClauseValuationMode.DIRECT_EQUATION,
        ("trainer", "accel"): ClauseValuationMode.DIRECT_EQUATION,
        ("trainer", "coin"): ClauseValuationMode.DIRECT_EQUATION,
        ("trainer", "damage_boost"): ClauseValuationMode.DIRECT_EQUATION,
        ("trainer", "fetch"): ClauseValuationMode.DIRECT_EQUATION,
        ("trainer", "gust"): ClauseValuationMode.DIRECT_EQUATION,
        ("trainer", "heal"): ClauseValuationMode.DIRECT_EQUATION,
        ("trainer", "stadium_static"): ClauseValuationMode.DIRECT_EQUATION,
    }),
    "rider": MappingProxyType({
        ("attached_cards_too", "attack", "coin"): ClauseValuationMode.DIRECT_EQUATION,
        ("both_hands_to_bottom", "trainer", "draw"): ClauseValuationMode.DIRECT_EQUATION,
        ("bounce_energy_to_hand", "trainer", "heal"): ClauseValuationMode.DIRECT_EQUATION,
        ("confuse_target", "trainer", "gust"): ClauseValuationMode.DIRECT_EQUATION,
        ("cure_existing", "trainer", "stadium_static"): ClauseValuationMode.DIRECT_EQUATION,
        ("damage_new_active", "attack", "gust"): ClauseValuationMode.DIRECT_EQUATION,
        ("discard_basic_f_energy", "ability", "draw"): ClauseValuationMode.DIRECT_EQUATION,
        ("discard_eot", "energy", "energy_provide"): ClauseValuationMode.DIRECT_EQUATION,
        ("discard_own_energy", "trainer", "heal"): ClauseValuationMode.DIRECT_EQUATION,
        ("discard_remainder", "trainer", "fetch"): ClauseValuationMode.DIRECT_EQUATION,
        ("draw_1", "ability", "accel"): ClauseValuationMode.DIRECT_EQUATION,
        ("heal_30_target", "ability", "accel"): ClauseValuationMode.DIRECT_EQUATION,
        ("other_to_bottom", "ability", "draw"): ClauseValuationMode.DIRECT_EQUATION,
        ("poison_new_active", "ability", "self_switch"): ClauseValuationMode.DIRECT_EQUATION,
        ("recoil", "attack", "damage_boost"): ClauseValuationMode.DIRECT_EQUATION,
        ("self_ko", "ability", "damage_counters"): ClauseValuationMode.DIRECT_EQUATION,
        ("self_switch", "trainer", "draw"): ClauseValuationMode.DIRECT_EQUATION,
        ("self_switch", "trainer", "gust"): ClauseValuationMode.DIRECT_EQUATION,
        ("shuffle_before_place", "trainer", "fetch"): ClauseValuationMode.DIRECT_EQUATION,
        ("shuffle_both_hands", "trainer", "draw"): ClauseValuationMode.DIRECT_EQUATION,
        ("shuffle_counted_into_deck", "attack", "damage_boost"): ClauseValuationMode.DIRECT_EQUATION,
        ("shuffle_own_hand_in", "trainer", "draw"): ClauseValuationMode.DIRECT_EQUATION,
        ("shuffle_self_in", "ability", "draw"): ClauseValuationMode.DIRECT_EQUATION,
        ("skip_stage1", "trainer", "fetch"): ClauseValuationMode.DIRECT_EQUATION,
    }),
})

def clause_parameter_mode(parameter, value, placement, kind):
    contracts = CLAUSE_PARAMETER_PLACEMENT_CONTRACTS.get(parameter)
    if contracts is None:
        return CLAUSE_PARAMETER_CONTRACTS[parameter]
    key = ((str(value), placement, kind) if parameter == "rider"
           else (placement, kind))
    return contracts[key]


def placed_clauses(facts):
    if isinstance(facts, TrainerCard):
        yield from (("trainer", clause) for clause in facts.clauses)
    elif isinstance(facts, EnergyCard):
        yield from (("energy", clause) for clause in facts.clauses)
    elif isinstance(facts, PokemonCard):
        yield from (("ability", clause)
                    for ability in facts.abilities for clause in ability.clauses)
        yield from (("attack", clause)
                    for attack in facts.attacks for clause in attack.clauses)


class DirectEquationOwner(str, Enum):
    ACCELERATION = "capability.acceleration"
    ATTACK = "capability.attack"
    ATTACK_GATE = "capability.attack_gate"
    BENCH_REACH = "capability.bench_reach"
    DAMAGE_MOVE = "capability.damage_move"
    DENIAL = "capability.denial"
    DRAW = "capability.draw"
    HEALING = "capability.healing"
    KNOCKOUT = "capability.knockout"
    PROTECTION = "capability.protection"
    SEARCH = "capability.search"
    FUNCTION = "activation.function"


@dataclass(frozen=True, slots=True)
class ClauseValuationContract:
    kind: str
    mode: ClauseValuationMode
    owner: DirectEquationOwner
    features: tuple[str, ...]
    witness: str


def _clause(kind, mode, owner, *features):
    return ClauseValuationContract(
        kind, mode, DirectEquationOwner(owner), features, f"clause:{kind}")


_D = ClauseValuationMode.DIRECT_EQUATION

CLAUSE_VALUATION_CONTRACTS = MappingProxyType({
    "ability_suppression": _clause(
        "ability_suppression", _D, "capability.denial",
        "ability.denial", "function.suppression.ability_target"),
    "accel": _clause(
        "accel", _D, "capability.acceleration",
        "ability.acceleration", "function.accel.open_energy_slot"),
    "attack_cost_reduction": _clause(
        "attack_cost_reduction", _D, "activation.function",
        "function.cost_reduction.open_cost"),
    "attack_debuff": _clause(
        "attack_debuff", _D, "activation.function", "function.status.active_target"),
    "attack_lock": _clause(
        "attack_lock", _D, "capability.denial",
        "ability.denial", "function.denial.opponent_resource"),
    "attack_twice": _clause(
        "attack_twice", _D, "activation.function", "combat.realization"),
    "bench_snipe": _clause(
        "bench_snipe", _D, "capability.bench_reach",
        "combat.realization", "function.bench_pressure.target_count"),
    "bench_spread": _clause(
        "bench_spread", _D, "capability.bench_reach",
        "combat.realization", "function.bench_pressure.target_count"),
    "checkup_trigger": _clause(
        "checkup_trigger", _D, "activation.function", "ability.damage_move"),
    "coin": _clause(
        "coin", _D, "activation.function",
        "combat.realization", "function.attack.modifier"),
    "confuse": _clause(
        "confuse", _D, "activation.function", "function.status.active_target"),
    "copy_attack": _clause(
        "copy_attack", _D, "activation.function",
        "combat.realization", "function.attack.copy_source"),
    "cost_reduction": _clause(
        "cost_reduction", _D, "activation.function",
        "function.cost_reduction.open_cost"),
    "damage_boost": _clause(
        "damage_boost", _D, "activation.function",
        "combat.realization", "function.attack.modifier"),
    "damage_counters": _clause(
        "damage_counters", _D, "activation.function",
        "function.bench_pressure.target_count"),
    "damage_protection": _clause(
        "damage_protection", _D, "activation.function",
        "active.doomed", "function.protection.incoming_pressure"),
    "damage_reduction": _clause(
        "damage_reduction", _D, "capability.protection",
        "ability.denial", "function.protection.incoming_pressure"),
    "deck_top": _clause(
        "deck_top", _D, "activation.function", "option.search"),
    "discard_opp_energy": _clause(
        "discard_opp_energy", _D, "activation.function",
        "function.denial.opponent_resource"),
    "draw": _clause(
        "draw", _D, "capability.draw",
        "ability.draw_cards", "ability.resource_cost"),
    "energy_bounce": _clause(
        "energy_bounce", _D, "activation.function", "function.denial.opponent_resource"),
    "energy_double": _clause(
        "energy_double", _D, "activation.function", "function.accel.open_energy_slot"),
    "energy_provide": _clause(
        "energy_provide", _D, "activation.function",
        "continuation.multi_provision_in_hand", "function.energy.provision"),
    "energy_recur": _clause(
        "energy_recur", _D, "capability.acceleration",
        "ability.acceleration", "function.accel.open_energy_slot"),
    "evolve_early": _clause(
        "evolve_early", _D, "activation.function", "function.development.board_fit"),
    "fetch": _clause(
        "fetch", _D, "capability.search",
        "ability.search_cards", "option.search"),
    "first_turn_attack_permission": _clause(
        "first_turn_attack_permission", _D, "activation.function", "ability.search_cards"),
    "grant_prevo_attacks": _clause(
        "grant_prevo_attacks", _D, "activation.function", "ability.future"),
    "gust": _clause(
        "gust", _D, "activation.function", "function.gust.bench_target"),
    "heal": _clause(
        "heal", _D, "capability.healing",
        "ability.healing", "function.heal.damage_present"),
    "hp_bonus": _clause(
        "hp_bonus", _D, "activation.function", "function.protection.incoming_pressure"),
    "ignores_effects": _clause(
        "ignores_effects", _D, "capability.attack",
        "combat.realization", "function.attack.piercing"),
    "ignores_wr": _clause(
        "ignores_wr", _D, "capability.attack",
        "combat.realization", "function.attack.piercing"),
    "item_lock": _clause(
        "item_lock", _D, "capability.denial",
        "ability.denial", "function.denial.opponent_resource"),
    "ko": _clause(
        "ko", _D, "capability.knockout",
        "combat.realization", "function.ko.active_target",
        "function.ko.self_prize_liability"),
    "mill": _clause(
        "mill", _D, "activation.function", "function.disruption.deck"),
    "move_damage": _clause(
        "move_damage", _D, "capability.damage_move",
        "ability.damage_move", "function.move_damage.damage_present"),
    "move_energy": _clause(
        "move_energy", _D, "capability.acceleration",
        "ability.acceleration", "function.accel.open_energy_slot"),
    "no_retreat": _clause(
        "no_retreat", _D, "capability.denial",
        "ability.denial", "function.denial.opponent_resource"),
    "no_weakness": _clause(
        "no_weakness", _D, "activation.function", "ability.denial"),
    "opp_hand_to_deck": _clause(
        "opp_hand_to_deck", _D, "activation.function",
        "function.disruption.opponent_hand"),
    "prevent_damage": _clause(
        "prevent_damage", _D, "capability.protection",
        "ability.denial", "function.protection.incoming_pressure"),
    "prevent_effects": _clause(
        "prevent_effects", _D, "activation.function",
        "function.protection.incoming_pressure"),
    "push_out": _clause(
        "push_out", _D, "activation.function", "function.switch.active_pressure"),
    "recoil": _clause(
        "recoil", _D, "activation.function", "function.self_cost.exposure"),
    "requires_bench": _clause(
        "requires_bench", _D, "capability.attack_gate", "combat.realization"),
    "requires_bench_count": _clause(
        "requires_bench_count", _D, "activation.function", "combat.realization"),
    "requires_stadium": _clause(
        "requires_stadium", _D, "activation.function", "combat.realization"),
    "retreat_lock": _clause(
        "retreat_lock", _D, "capability.denial",
        "ability.denial", "function.denial.opponent_resource"),
    "retreat_reduction": _clause(
        "retreat_reduction", _D, "activation.function",
        "function.cost_reduction.open_cost"),
    "same_attack_lock": _clause(
        "same_attack_lock", _D, "activation.function", "ability.resource_cost"),
    "self_discard_energy": _clause(
        "self_discard_energy", _D, "activation.function", "function.self_cost.exposure"),
    "self_mill": _clause(
        "self_mill", _D, "activation.function", "function.self_cost.exposure"),
    "self_return": _clause(
        "self_return", _D, "activation.function", "function.self_cost.exposure"),
    "self_shuffle_in": _clause(
        "self_shuffle_in", _D, "activation.function", "function.self_cost.exposure"),
    "self_switch": _clause(
        "self_switch", _D, "activation.function", "function.switch.active_pressure"),
    "setup_active": _clause(
        "setup_active", _D, "activation.function", "ability.future"),
    "sleep": _clause(
        "sleep", _D, "activation.function", "function.status.active_target"),
    "stadium_static": _clause(
        "stadium_static", _D, "activation.function", "function.stadium.board_fit"),
    "stadium_trigger": _clause(
        "stadium_trigger", _D, "activation.function", "function.stadium.board_fit"),
    "survive_ko": _clause(
        "survive_ko", _D, "activation.function", "ability.denial"),
    "switch_self": _clause(
        "switch_self", _D, "activation.function", "function.switch.active_pressure"),
    "weakness_override": _clause(
        "weakness_override", _D, "activation.function", "ability.denial"),
})

DIRECT_CAPABILITY_CLAUSES = frozenset(
    kind for kind, contract in CLAUSE_VALUATION_CONTRACTS.items()
    if contract.mode is ClauseValuationMode.DIRECT_EQUATION)
SUCCESSOR_CLAUSES = frozenset(
    kind for kind, contract in CLAUSE_VALUATION_CONTRACTS.items()
    if contract.mode is ClauseValuationMode.SUCCESSOR_DELTA)


def clause_contract_findings(kinds=FUNCTION_CATALOG.kinds,
                             contracts=CLAUSE_VALUATION_CONTRACTS) -> tuple[str, ...]:
    expected = {str(kind) for kind in kinds}
    declared = {str(kind) for kind in contracts}
    findings = [f"missing clause contract: {kind}" for kind in sorted(expected - declared)]
    findings.extend(f"unknown clause contract: {kind}" for kind in sorted(declared - expected))
    for key in sorted(expected & declared):
        contract = contracts[key]
        if contract.kind != key:
            findings.append(f"clause contract key mismatch: {key}")
        if not contract.owner:
            findings.append(f"clause contract missing owner: {key}")
        if not contract.features:
            findings.append(f"clause contract missing features: {key}")
        if not contract.witness:
            findings.append(f"clause contract missing witness: {key}")
        for feature in contract.features:
            if feature not in FEATURE_CATALOG:
                findings.append(f"clause contract unknown feature: {key}:{feature}")
    return tuple(findings)


def clause_parameter_findings(cards=None) -> tuple[str, ...]:
    declared = set(CLAUSE_PARAMETER_CONTRACTS)
    expected = {
        parameter for kind in FUNCTION_CATALOG.kinds
        for parameter in FUNCTION_CATALOG[kind].parameters
    }
    findings = [f"missing clause parameter contract: {name}"
                for name in sorted(expected - declared)]
    findings.extend(f"unknown clause parameter contract: {name}"
                    for name in sorted(declared - expected))
    direct = {name for name, mode in CLAUSE_PARAMETER_CONTRACTS.items()
              if mode is ClauseValuationMode.DIRECT_EQUATION}
    equations = set(CLAUSE_PARAMETER_DIRECT_EQUATIONS)
    findings.extend(f"missing direct parameter equation: {name}"
                    for name in sorted(direct - equations))
    findings.extend(f"non-direct parameter equation: {name}"
                    for name in sorted(equations - direct))
    cards = card_store() if cards is None else cards
    for parameter, contracts in CLAUSE_PARAMETER_PLACEMENT_CONTRACTS.items():
        observed = {
            ((str(value), placement, clause.kind) if parameter == "rider"
             else (placement, clause.kind))
            for facts in cards.values()
            for placement, clause in placed_clauses(facts)
            if (value := getattr(clause, parameter, None)) is not None
        }
        declared_rows = set(contracts)
        findings.extend(
            f"missing clause parameter placement contract: {parameter}={row!r}"
            for row in sorted(observed - declared_rows))
        findings.extend(
            f"stale clause parameter placement contract: {parameter}={row!r}"
            for row in sorted(declared_rows - observed))
    for parameter, contracted_values in CLAUSE_PARAMETER_VALUE_CONTRACTS.items():
        observed = {
            str(value)
            for facts in cards.values()
            for clause in card_clauses(facts)
            if (value := getattr(clause, parameter, None)) is not None
        }
        findings.extend(
            f"unpriced clause parameter value: {parameter}={value}"
            for value in sorted(observed - set(contracted_values)))
        findings.extend(
            f"stale clause parameter value contract: {parameter}={value}"
            for value in sorted(set(contracted_values) - observed))
    for parameter, contracts in CLAUSE_PARAMETER_BRANCH_CONTRACTS.items():
        observed = {
            (str(branch.get("condition")), frozenset(set(branch) - {"condition"}))
            for facts in cards.values()
            for clause in card_clauses(facts)
            if isinstance((branch := getattr(clause, parameter, None)), dict)
        }
        expected_branches = {
            (condition, fields) for condition, fields in contracts.items()
        }
        findings.extend(
            f"unpriced conditional parameter: {parameter}={condition}:{sorted(fields)}"
            for condition, fields in sorted(observed - expected_branches,
                                             key=lambda item: item[0]))
        findings.extend(
            f"stale conditional parameter contract: {parameter}={condition}:{sorted(fields)}"
            for condition, fields in sorted(expected_branches - observed,
                                             key=lambda item: item[0]))
    return tuple(findings)


def unowned_observation_fields() -> tuple[str, ...]:
    missing = []
    for node, owners in OBSERVATION_FIELD_OWNERS.items():
        missing.extend(f"{node.__name__}.{field.name}" for field in fields(node)
                       if field.name not in owners)
    return tuple(sorted(missing))


def observation_contract_findings() -> tuple[str, ...]:
    expected = {
        f"{node.__name__}.{name}"
        for node, owners in OBSERVATION_FIELD_OWNERS.items()
        for name, owner in owners.items() if owner in {"value", "belief", "conditional"}
    }
    declared = set(OBSERVATION_FIELD_FEATURES)
    findings = [f"missing observation witness: {name}"
                for name in sorted(expected - declared)]
    findings.extend(f"non-valued observation witness: {name}"
                    for name in sorted(declared - expected))
    all_fields = {
        f"{node.__name__}.{name}"
        for node, owners in OBSERVATION_FIELD_OWNERS.items()
        for name in owners
    }
    expectations = set(OBSERVATION_FIELD_EXPECTATIONS)
    findings.extend(f"missing observation expectation: {name}"
                    for name in sorted(all_fields - expectations))
    findings.extend(f"unknown observation expectation: {name}"
                    for name in sorted(expectations - all_fields))
    for name, feature_keys in OBSERVATION_FIELD_FEATURES.items():
        if not feature_keys:
            findings.append(f"observation witness has no features: {name}")
        for feature in feature_keys:
            if feature not in FEATURE_CATALOG:
                findings.append(f"observation witness unknown feature: {name}:{feature}")
            elif FEATURE_CATALOG[feature].default == 0.0:
                findings.append(f"observation witness zero seed: {name}:{feature}")
    return tuple(findings)


def unowned_clause_kinds() -> tuple[str, ...]:
    return tuple(sorted(set(FUNCTION_CATALOG.kinds) - set(CLAUSE_VALUATION_CONTRACTS)))


def card_coverage_gap(card_id, facts) -> str | None:
    if facts is None:
        return f"unknown card {int(card_id)}"
    verdict = getattr(facts, "covers", None)
    if verdict == "full":
        return None
    if verdict == "partial":
        return f"incomplete card coverage {int(card_id)} (partial)"
    return f"incomplete card coverage {int(card_id)} (unruled)"


__all__ = (
    "CLAUSE_PARAMETER_BRANCH_CONTRACTS", "CLAUSE_PARAMETER_CONTRACTS",
    "CLAUSE_PARAMETER_DIRECT_EQUATIONS", "CLAUSE_PARAMETER_PLACEMENT_CONTRACTS",
    "CLAUSE_PARAMETER_VALUE_CONTRACTS",
    "CLAUSE_VALUATION_CONTRACTS", "DIRECT_CAPABILITY_CLAUSES",
    "OBSERVATION_FIELD_EXPECTATIONS", "OBSERVATION_FIELD_FEATURES",
    "OBSERVATION_FIELD_OWNERS", "SUCCESSOR_CLAUSES",
    "ClauseValuationContract", "ClauseValuationMode", "DirectEquationOwner",
    "card_coverage_gap", "clause_contract_findings", "clause_parameter_findings", "clause_parameter_mode",
    "observation_contract_findings", "unowned_clause_kinds", "unowned_observation_fields",
    "placed_clauses",
)
