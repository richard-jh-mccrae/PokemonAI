from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math

from common.cards import card_clauses

from .features import (ACTIVATION_OPERATIONS, FEATURE_CATALOG, ActivationRule,
                       FeatureCatalog)


@dataclass(frozen=True, slots=True)
class FeatureActivation:
    feature: str
    value: float
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ActivationEnvironment:
    scale: float = 1.0
    provenance: tuple[str, ...] = ()
    board: object | None = None
    evaluation_model: object | None = None
    side: object | None = None
    opponent: object | None = None
    demand: object | None = None
    facts: object | None = None
    deck_counts: object | None = None
    candidate: object | None = None
    claim_value: object | None = None


class ActivationCompiler:
    def __init__(self, catalog: FeatureCatalog = FEATURE_CATALOG):
        self.catalog = catalog

    def compile(self, source: str, claims, environment: ActivationEnvironment
                ) -> tuple[FeatureActivation, ...]:
        activations = []
        seen = set()
        for spec, rule in self.catalog.activation_rules(source, claims):
            if spec.key in seen:
                continue
            if (rule.argument is not None and environment.claim_value is not None
                    and str(environment.claim_value) != rule.argument):
                continue
            try:
                operation = _OPERATIONS[rule.operation]
            except KeyError:
                raise KeyError(f"unknown activation operation {rule.operation!r}") from None
            value = float(environment.scale) * float(operation(environment, rule))
            if not math.isfinite(value):
                raise ValueError(f"non-finite activation for {spec.key!r}")
            if value:
                activations.append(FeatureActivation(
                    spec.key, value, tuple(environment.provenance)))
            seen.add(spec.key)
        return tuple(activations)


def _constant(environment, rule):
    return 1.0


def _side_hand_count(environment, rule):
    return environment.side.hand_count


def _fetch_live_target(environment, rule):
    from .worth import DemandState, _liveness

    state, _capacity = _liveness(
        0, environment.facts, environment.demand, environment.evaluation_model,
        environment.deck_counts)
    return float(state is not DemandState.DEAD)


def _bench_target(environment, rule):
    return float(bool(environment.opponent.bench))


def _side_damage_units(environment, rule):
    return sum(max(0, body.max_hp - body.hp) for body in environment.side.bodies) / DAMAGE_UNIT_HP


def _open_energy_slot(environment, rule):
    from .worth import _unfilled

    open_slots = sum(any(_unfilled(attack.cost, Counter(body.energies)) != (Counter(), 0)
                         for attack in getattr(environment.evaluation_model.facts(
                             body.card.card_id), "attacks", ()) or ())
                     for body in environment.side.bodies)
    return open_slots


def _switch_target(environment, rule):
    return float(environment.side.active is not None and bool(environment.side.bench))


def _opponent_hand_count(environment, rule):
    return environment.opponent.hand_count


def _opponent_energy_count(environment, rule):
    return sum(len(body.energies) for body in environment.opponent.bodies)


def _opponent_bench(environment, rule):
    return len(environment.opponent.bench)


def _opponent_empty_bench(environment, rule):
    return float(not environment.opponent.bench)


def _incoming_pressure(environment, rule):
    pressure = max((attack.damage for body in environment.opponent.bodies
                    for attack in getattr(environment.evaluation_model.facts(
                        body.card.card_id), "attacks", ()) or ()), default=0)
    return pressure / DAMAGE_UNIT_HP


def _active_target(environment, rule):
    return float(environment.opponent.active is not None)


def _open_cost(environment, rule):
    from .worth import _unfilled

    open_cost = sum(bool(_unfilled(attack.cost, Counter(body.energies)) != (Counter(), 0))
                    for body in environment.side.bodies
                    for attack in getattr(environment.evaluation_model.facts(
                        body.card.card_id), "attacks", ()) or ())
    return open_cost


def _ability_target(environment, rule):
    return sum(bool(getattr(environment.evaluation_model.facts(
        body.card.card_id), "abilities", ())) for body in environment.opponent.bodies)


def _evolution_target(environment, rule):
    return sum(bool(getattr(environment.evaluation_model.facts(
        body.card.card_id), "evolves_from", None)) for body in environment.side.bodies)


def _own_damage_units(environment, rule):
    return _side_damage_units(environment, rule)


def _board_body_count(environment, rule):
    return len(environment.side.bodies) + len(environment.opponent.bodies)


def _opponent_deck_count(environment, rule):
    return environment.board.them.deck_count


def _opponent_damage_units(environment, rule):
    return sum(max(0, body.max_hp - body.hp)
               for body in environment.board.them.bodies) / DAMAGE_UNIT_HP


def _candidate_role_bodies(environment, rule):
    return sum(rule.argument in environment.candidate.roles.get(body.card.card_id, ())
               for body in environment.board.them.bodies)


def _turn_number(environment, rule):
    return max(0, environment.board.turn.number)


def _own_item_count(environment, rule):
    return sum(getattr(environment.evaluation_model.facts(card.card_id), "kind", None) == "item"
               for card in (environment.board.me.hand or ()))


def _own_bench_count(environment, rule):
    return len(environment.board.me.bench)


def _own_hand_count(environment, rule):
    return environment.board.me.hand_count


def _opponent_special_energy_count(environment, rule):
    return sum(getattr(environment.evaluation_model.facts(card.card_id), "kind", None)
               == "special_energy"
               for body in environment.board.them.bodies for card in body.energy_cards)


def _side_status_count(environment, rule):
    side = environment.board.me if rule.argument == "me" else environment.board.them
    return sum(bool(getattr(side, status)) for status in STATUS_FIELDS)


def _active_retreat_cost(environment, rule):
    side = environment.board.me if rule.argument == "me" else environment.board.them
    active = side.active
    if active is None:
        return 0.0
    return getattr(environment.evaluation_model.facts(
        active.card.card_id), "retreat_cost", 0)


def _active_tool_count(environment, rule):
    side = environment.board.me if rule.argument == "me" else environment.board.them
    return 0 if side.active is None else len(side.active.tools)


def _opponent_single_prize_count(environment, rule):
    return sum(_prize_value(body, environment.evaluation_model) == 1
               for body in environment.board.them.bodies)


def _own_max_attack_units(environment, rule):
    return max((attack.damage for body in environment.board.me.bodies
                for attack in getattr(environment.evaluation_model.facts(
                    body.card.card_id), "attacks", ()) or ()), default=0) / DAMAGE_UNIT_HP


def _prize_difference(environment, rule):
    return environment.board.them.prize_count - environment.board.me.prize_count


def _multi_provision_capacity(environment, rule):
    from .worth import _unfilled

    provision = environment.facts.clause("energy_provide")
    if provision is None or not provision.amount_on_evolution:
        return 0.0
    amount = int(provision.amount_on_evolution)
    evolved_targets = [body for body in environment.demand.bodies
                       if getattr(environment.evaluation_model.facts(
                           body.card.card_id), "evolves_from", None)]
    can_absorb = any(
        sum(open_typed.values()) + open_colorless >= amount
        for body in evolved_targets
        for attack in getattr(environment.evaluation_model.facts(
            body.card.card_id), "attacks", ()) or ()
        for open_typed, open_colorless in [
            _unfilled(attack.cost, Counter(body.energies))])
    return max(0, amount - int(provision.amount or 1)) if can_absorb else 0.0


def _body_clause_count(environment, rule):
    kinds = set(rule.parameters)
    return sum(bool(kinds.intersection(
        clause.kind for clause in card_clauses(environment.evaluation_model.facts(
            body.card.card_id)))) for body in environment.board.me.bodies)


def _body_flag_count(environment, rule):
    return sum(any(bool(getattr(environment.evaluation_model.facts(
        body.card.card_id), flag, False)) for flag in rule.parameters)
               for body in environment.board.me.bodies)


def _prize_value(body, evaluation_model):
    facts = evaluation_model.facts(body.card.card_id)
    return int(getattr(facts, "prize_value", 1) or 1)


DAMAGE_UNIT_HP = 100.0
STATUS_FIELDS = ("asleep", "paralyzed", "confused", "poisoned", "burned")


_OPERATIONS = {
    "ability_target": _ability_target,
    "active_target": _active_target,
    "bench_target": _bench_target,
    "board_body_count": _board_body_count,
    "candidate_role_bodies": _candidate_role_bodies,
    "constant": _constant,
    "evolution_target": _evolution_target,
    "fetch_live_target": _fetch_live_target,
    "side_hand_count": _side_hand_count,
    "incoming_pressure": _incoming_pressure,
    "multi_provision_capacity": _multi_provision_capacity,
    "open_cost": _open_cost,
    "open_energy_slot": _open_energy_slot,
    "opponent_bench": _opponent_bench,
    "opponent_empty_bench": _opponent_empty_bench,
    "opponent_damage_units": _opponent_damage_units,
    "opponent_deck_count": _opponent_deck_count,
    "opponent_hand_count": _opponent_hand_count,
    "opponent_energy_count": _opponent_energy_count,
    "opponent_single_prize_count": _opponent_single_prize_count,
    "opponent_special_energy_count": _opponent_special_energy_count,
    "own_bench_count": _own_bench_count,
    "side_damage_units": _side_damage_units,
    "own_damage_units": _own_damage_units,
    "body_clause_count": _body_clause_count,
    "body_flag_count": _body_flag_count,
    "own_hand_count": _own_hand_count,
    "own_item_count": _own_item_count,
    "own_max_attack_units": _own_max_attack_units,
    "side_status_count": _side_status_count,
    "active_retreat_cost": _active_retreat_cost,
    "active_tool_count": _active_tool_count,
    "prize_difference": _prize_difference,
    "switch_target": _switch_target,
    "turn_number": _turn_number,
}
if set(_OPERATIONS) != ACTIVATION_OPERATIONS:
    raise RuntimeError("activation operation implementation disagrees with catalog schema")


__all__ = ("DAMAGE_UNIT_HP", "ActivationCompiler", "ActivationEnvironment",
           "FeatureActivation")
