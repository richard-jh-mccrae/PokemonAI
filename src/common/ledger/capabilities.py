from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

from common.cards import card_clauses
from common.cards.card_facts import (
    BASIC_ENERGY, COLORLESS, SUPPORTER, WILDCARD, EnergyCard, PokemonCard,
    TrainerCard,
)
from common.cards.functions.damage import bench_reach
from common.cards.functions.draw import draw_branches
from common.cards.functions.energy import provision_units
from common.cards.functions.fetch import DEADNESS, fetch_target_matches


WEAKNESS_MULTIPLIER = 2
RESISTANCE_REDUCTION = 30
COMPLETION_EXPONENT = 2
DEFAULT_PRIZE_COUNT = 6
DAMAGE_UNIT_HP = 100
DAMAGE_COUNTER_HP = 10
DAMAGE_RANGE_BOUND_COUNT = 2
FUTURE_TURN_DISCOUNT = 0.8
DISCARD_AREA = 3
IN_PLAY_AREAS = frozenset((4, 5))
KNOCKOUT_EVENT_KINDS = frozenset((6, 7))


def _quantity(value, default=0.0) -> float:
    try:
        return float(default if value is None else value)
    except (TypeError, ValueError):
        return float(default)


@dataclass(frozen=True, slots=True)
class Capability:
    attack_now: float = 0.0
    attack_progress: float = 0.0
    attack_future: float = 0.0
    attack_potential: float = 0.0
    line_potential: float = 0.0
    bench_reach: float = 0.0
    draw_cards: float = 0.0
    search_cards: float = 0.0
    damage_move: float = 0.0
    healing: float = 0.0
    acceleration: float = 0.0
    denial: float = 0.0
    resource_cost: float = 0.0
    self_cost: float = 0.0
    ability_future: float = 0.0
    retreat_progress: float = 0.0
    gaps: tuple[str, ...] = ()

    def value(self, configuration) -> float:
        values = {
            "combat.attack_now": self.attack_now,
            "combat.attack_progress": self.attack_progress,
            "combat.attack_future": self.attack_future,
            "combat.active_threat": self.attack_potential,
            "combat.line_potential": self.line_potential,
            "combat.bench_reach": self.bench_reach,
            "ability.draw_cards": self.draw_cards,
            "ability.search_cards": self.search_cards,
            "ability.damage_move": self.damage_move,
            "ability.healing": self.healing,
            "ability.acceleration": self.acceleration,
            "ability.denial": self.denial,
            "ability.resource_cost": self.resource_cost,
            "ability.self_cost": self.self_cost,
            "ability.future": self.ability_future,
            "mobility.retreat_progress": self.retreat_progress,
        }
        return sum(activation * configuration[key] for key, activation in values.items())


def unmet_cost_slots(provisions, requirements) -> tuple[int, ...]:
    remaining = [int(unit) for unit in provisions]
    unpaid = []
    colorless = []
    for slot, required in enumerate(requirements):
        if int(required) == COLORLESS:
            colorless.append(slot)
            continue
        found = next((index for index, supplied in enumerate(remaining)
                      if supplied in {int(required), WILDCARD}), None)
        if found is None:
            unpaid.append(slot)
        else:
            remaining.pop(found)
    paid_colorless = min(len(colorless), len(remaining))
    return tuple((*unpaid, *colorless[paid_colorless:]))


def payment_fraction(provisions, requirements) -> float:
    requirements = tuple(requirements)
    if not requirements:
        return 1.0
    return (len(requirements) - len(unmet_cost_slots(provisions, requirements))) \
        / len(requirements)


def _side_names(side, ctx, *, bench_only=False) -> tuple[str, ...]:
    bodies = side.bench if bench_only else side.bodies
    return tuple(facts.name for body in bodies
                 if isinstance((facts := ctx.facts(body.card.card_id)), PokemonCard))


def _condition_probability(condition, body, side, board, ctx, *, clause=None) -> float | None:
    if not condition:
        return 1.0
    condition = str(condition)
    if condition.endswith("_in_play"):
        wanted = condition.removesuffix("_in_play").replace("_", " ").casefold()
        return float(any(name.casefold() == wanted for name in _side_names(side, ctx)))
    if condition.endswith("_on_bench"):
        wanted = condition.removesuffix("_on_bench").replace("_", " ").casefold()
        return float(any(name.casefold() == wanted
                         for name in _side_names(side, ctx, bench_only=True)))
    if condition in {"dark_energy_attached", "energy_type_attached"}:
        energy_type = getattr(clause, "condition_energy_type", None)
        return float(energy_type is not None and int(energy_type) in body.energies)
    if condition == "damaged":
        return float(body.hp < body.max_hp)
    if condition == "stadium_in_play":
        return float(bool(board.stadium))
    if condition == "pokemon_ko_last_turn":
        return 1.0 if _knockout_visible(board) else 0.0
    if condition in {"exactly_6_prizes_remaining", "opp_3_or_fewer_prizes"}:
        return 1.0
    return None


def _knockout_visible(board) -> bool:
    for event in board.events:
        fields = dict(event.public_fields)
        if event.kind in KNOCKOUT_EVENT_KINDS \
                and fields.get("fromArea") in IN_PLAY_AREAS \
                and fields.get("toArea") == DISCARD_AREA:
            return True
    return False


def _scale_value(name, attacker, defender, attacker_body, defender_body, ctx) -> int | None:
    values = {
        "atk_hand": attacker.hand_count,
        "def_hand": defender.hand_count,
        "atk_active_energy": len(attacker_body.energies),
        "def_active_energy": 0 if defender_body is None else len(defender_body.energies),
        "atk_bench": len(attacker.bench),
        "def_bench": len(defender.bench),
        "both_bench": len(attacker.bench) + len(defender.bench),
        "both_active_energy": (len(attacker_body.energies)
                               + (0 if defender_body is None else len(defender_body.energies))),
        "atk_self_counters": max(
            0, attacker_body.max_hp - attacker_body.hp) // DAMAGE_COUNTER_HP,
        "def_counters": (0 if defender_body is None else
                         max(0, defender_body.max_hp - defender_body.hp)
                         // DAMAGE_COUNTER_HP),
        "atk_prizes_taken": max(0, DEFAULT_PRIZE_COUNT - attacker.prize_count),
        "def_prizes_taken": max(0, DEFAULT_PRIZE_COUNT - defender.prize_count),
        "atk_bench_stage2": sum(
            getattr(ctx.facts(body.card.card_id), "stage", None) == "stage2"
            for body in attacker.bench),
        "def_counters_all": sum(max(0, body.max_hp - body.hp) // DAMAGE_COUNTER_HP
                                for body in defender.bodies),
        "def_ex_in_play": sum(bool(getattr(ctx.facts(body.card.card_id), "ex", False)
                                   or getattr(ctx.facts(body.card.card_id), "mega_ex", False))
                              for body in defender.bodies),
    }
    return values.get(str(name))


def attack_damage(attack, attacker_facts, defender_facts, attacker_body,
                  attacker, defender, ctx) -> float:
    partner = attack.clause("requires_bench")
    if partner is not None and partner.name not in _side_names(attacker, ctx, bench_only=True):
        return 0.0
    damage = float(attack.damage_fix if attack.damage_fix is not None else attack.damage or 0)
    if not damage and attack.damage_min is not None and attack.damage_max is not None:
        damage = (float(attack.damage_min) + float(attack.damage_max)) \
            / DAMAGE_RANGE_BOUND_COUNT
    if attack.scale_var and attack.scale_per_unit:
        units = _scale_value(attack.scale_var, attacker, defender, attacker_body,
                             defender.active, ctx)
        if units is not None:
            damage += float(attack.scale_per_unit) * units
    if attack.clause("ko") is not None and defender.active is not None:
        damage = max(damage, float(defender.active.hp))
    if not damage or attack.clause("ignores_wr") is not None or defender_facts is None:
        return max(0.0, damage)
    attacker_type = getattr(attacker_facts, "energy_type", None)
    if defender_facts.weakness == attacker_type:
        damage *= WEAKNESS_MULTIPLIER
    if defender_facts.resistance == attacker_type:
        damage = max(0.0, damage - RESISTANCE_REDUCTION)
    if attack.clause("ignores_effects") is None:
        for clause in card_clauses(defender_facts):
            if clause.kind == "damage_reduction" and clause.amount:
                damage = max(0.0, damage - float(clause.amount))
            if clause.kind == "prevent_damage" and clause.condition in {None, "always"}:
                return 0.0
    return max(0.0, damage)


def _target_impact(damage: float, target, ctx) -> float:
    if target is None or damage <= 0:
        return max(0.0, damage) / DAMAGE_UNIT_HP
    live_hp = max(1, target.hp)
    progress = min(damage, live_hp) / DAMAGE_UNIT_HP
    if damage >= live_hp:
        progress += float(getattr(ctx.facts(target.card.card_id), "prize_value", 1))
    return progress


def _attack_impact(attack, facts, body, side, opponent, ctx) -> tuple[float, float]:
    defender_facts = (None if opponent.active is None else
                      ctx.facts(opponent.active.card.card_id))
    active = _target_impact(
        attack_damage(attack, facts, defender_facts, body, side, opponent, ctx),
        opponent.active, ctx)
    reach = float(bench_reach(attack))
    bench = max((_target_impact(reach, target, ctx) for target in opponent.bench), default=0.0)
    return active + bench, bench


def _ability_capability(body, facts, side, opponent, board, ctx) -> Capability:
    values = {name: 0.0 for name in (
        "draw_cards", "search_cards", "damage_move", "healing", "acceleration",
        "denial", "resource_cost", "self_cost", "ability_future")}
    gaps = []
    for ability in facts.abilities:
        for clause in ability.clauses:
            gate = _condition_probability(clause.condition, body, side, board, ctx,
                                          clause=clause)
            if gate is None:
                gaps.append(f"unsupported condition {clause.condition!r} on {facts.card_id}")
                continue
            if gate <= 0:
                continue
            if clause.kind == "draw":
                branches = draw_branches(
                    clause, side.prize_count, opponent.prize_count,
                    my_hand_size=side.hand_count)
                amount = (_quantity(clause.amount) if not branches else
                          sum(mine for mine, _theirs in branches) / len(branches))
                values["draw_cards"] += gate * amount
                if clause.rider and str(clause.rider).startswith("discard_"):
                    values["resource_cost"] += gate * _quantity(clause.rider_amount, 1)
                if clause.rider in {"shuffle_self_in", "self_shuffle_in"}:
                    values["self_cost"] += gate
            elif clause.kind == "fetch" and clause.trigger != "on_bench_play":
                values["search_cards"] += gate * _quantity(clause.amount, 1)
            elif clause.kind == "move_damage":
                amount = _quantity(clause.amount)
                movable = min(amount,
                              sum(max(0, other.max_hp - other.hp) for other in side.bodies))
                room = max((target.hp for target in opponent.bodies), default=0)
                immediate = min(movable, room) / DAMAGE_UNIT_HP
                potential = min(amount, room) / DAMAGE_UNIT_HP
                values["damage_move"] += gate * immediate
                values["ability_future"] += gate * max(0.0, potential - immediate)
            elif clause.kind == "heal":
                damaged = sum(max(0, other.max_hp - other.hp) for other in side.bodies)
                values["healing"] += gate * min(
                    _quantity(clause.amount), damaged) / DAMAGE_UNIT_HP
            elif clause.kind in {"accel", "energy_recur", "move_energy"}:
                available = len(side.discard) if clause.zone == "discard" else 1
                values["acceleration"] += gate * min(_quantity(clause.amount, 1), available)
            elif clause.kind in {"ability_suppression", "attack_lock", "item_lock",
                                 "no_retreat", "retreat_lock"}:
                values["denial"] += gate
    return Capability(**values, gaps=tuple(gaps))


def _reachable_evolutions(facts, ctx, reach):
    from .worth import Reach, _forward_lines

    for card_id in _forward_lines().get(facts.name, ()):
        status = (reach or {}).get(card_id, Reach.ABSENT)
        scale = (1.0 if status in {Reach.HAND, Reach.FETCHABLE} else
                 1.0 if status is Reach.NEXT_TURN else
                 max(0.0, min(1.0, float(status))) if isinstance(status, (int, float)) else 0.0)
        target = ctx.facts(card_id)
        if scale > 0 and isinstance(target, PokemonCard):
            yield target, scale


def body_capability(body, side, opponent, board, ctx, *, reach=None) -> Capability:
    if body.max_hp > 0 and body.hp <= 0:
        return Capability()
    body = _without_bench_rentals(body, side, ctx)
    facts = ctx.facts(body.card.card_id)
    if not isinstance(facts, PokemonCard):
        return Capability(gaps=(f"body {body.card.card_id} has no Pokemon facts",))
    immediate = progress = bench = potential = 0.0
    for attack in facts.attacks:
        impact, attack_bench = _attack_impact(attack, facts, body, side, opponent, ctx)
        printed = max(float(attack.damage or attack.damage_fix or attack.damage_max or 0),
                      float(bench_reach(attack))) / DAMAGE_UNIT_HP
        potential = max(potential, max(impact, printed) / max(1, len(attack.cost)))
        fraction = payment_fraction(body.energies, attack.cost)
        if fraction >= 1.0:
            immediate = max(immediate, impact)
            bench = max(bench, attack_bench)
        else:
            progress = max(progress, impact * fraction ** COMPLETION_EXPONENT)
    future = 0.0
    for evolved, scale in _reachable_evolutions(facts, ctx, reach):
        for attack in evolved.attacks:
            impact, _attack_bench = _attack_impact(
                attack, evolved, body, side, opponent, ctx)
            fraction = payment_fraction(body.energies, attack.cost)
            future = max(future, scale * impact * fraction ** COMPLETION_EXPONENT)
    from .worth import _forward_lines

    line = (facts, *(ctx.facts(card_id)
                     for card_id in _forward_lines().get(facts.name, ())))
    line_potential = max((
        (float(attack.damage or attack.damage_fix or attack.damage_max or 0)
         + float(bench_reach(attack))) / DAMAGE_UNIT_HP / max(1, len(attack.cost))
        for card in line if isinstance(card, PokemonCard) for attack in card.attacks),
        default=potential)
    ability = _ability_capability(body, facts, side, opponent, board, ctx)
    retreat = ((1.0 if facts.retreat_cost <= 0 else
                min(1.0, len(body.energies) / facts.retreat_cost))
               if body is side.active and side.bench else 0.0)
    return replace(ability, attack_now=immediate, attack_progress=progress,
                   attack_future=future, attack_potential=potential,
                   line_potential=line_potential, bench_reach=bench,
                   retreat_progress=retreat)


def _without_bench_rentals(body, side, ctx):
    if body is side.active or not body.energy_cards:
        return body
    provisions = list(body.energies)
    changed = False
    for card in body.energy_cards:
        facts = ctx.facts(card.card_id)
        if not any(clause.rider == "discard_eot" for clause in card_clauses(facts)):
            continue
        supplied = getattr(facts, "provides", None)
        index = next((index for index, unit in enumerate(provisions)
                      if supplied is None or unit == supplied), None)
        if index is not None:
            provisions.pop(index)
            changed = True
    return replace(body, energies=tuple(provisions)) if changed else body


def best_current_damage(body, side, opponent, board, ctx) -> float:
    facts = ctx.facts(body.card.card_id)
    if not isinstance(facts, PokemonCard):
        return 0.0
    defender_facts = (None if opponent.active is None else
                      ctx.facts(opponent.active.card.card_id))
    return max((attack_damage(
        attack, facts, defender_facts, body, side, opponent, ctx)
        for attack in facts.attacks
        if payment_fraction(body.energies, attack.cost) >= 1.0), default=0.0)


def energy_marginal(body, energy_facts, side, opponent, board, ctx, *, reach=None) -> float:
    if not isinstance(energy_facts, EnergyCard):
        return 0.0
    if body is not side.active and any(
            clause.rider == "discard_eot" for clause in card_clauses(energy_facts)):
        return 0.0
    facts = ctx.facts(body.card.card_id)
    units = provision_units(energy_facts, evolved=bool(getattr(facts, "evolves_from", None)))
    supplied = int(energy_facts.provides)
    before = body_capability(body, side, opponent, board, ctx, reach=reach)
    after_body = replace(body, energies=(*body.energies, *((supplied,) * units)))
    after_side = replace(
        side,
        active=after_body if side.active is body else side.active,
        bench=tuple(after_body if item is body else item for item in side.bench),
    )
    after = body_capability(after_body, after_side, opponent, board, ctx, reach=reach)
    return after.value(ctx.configuration) - before.value(ctx.configuration)


def best_energy_marginal(energy_facts, side, opponent, board, ctx, reaches=None) -> float:
    reaches = reaches or {}
    return max((energy_marginal(
        body, energy_facts, side, opponent, board, ctx,
        reach=reaches.get(body.card.serial)) for body in side.bodies), default=0.0)


def recoverable_discard_ids(side, ctx) -> frozenset[int]:
    sources = tuple(side.hand or ()) + tuple(
        card for body in side.bodies for card in (body.card, *body.tools))
    discard = tuple(side.discard)
    recoverable = set()
    for source in sources:
        for clause in card_clauses(ctx.facts(source.card_id)):
            if clause.kind not in {"fetch", "energy_recur"} or clause.zone != "discard":
                continue
            for card in discard:
                facts = ctx.facts(card.card_id)
                if clause.kind == "energy_recur":
                    if isinstance(facts, EnergyCard) and (
                            clause.energy_type is None or facts.provides == clause.energy_type):
                        recoverable.add(card.card_id)
                elif fetch_target_matches(clause, facts, reading=DEADNESS):
                    recoverable.add(card.card_id)
    return frozenset(recoverable)


def card_option_value(facts, side, opponent, board, ctx, *, reaches=None) -> float:
    if isinstance(facts, EnergyCard):
        hand = tuple(side.hand)
        copies = sum(
            isinstance(held, EnergyCard)
            and held.kind == facts.kind and held.provides == facts.provides
            for card in hand if (held := ctx.facts(card.card_id)) is not None)
        return max(0.0, best_energy_marginal(
            facts, side, opponent, board, ctx, reaches=reaches)) / max(1, copies)
    if isinstance(facts, PokemonCard):
        deployable = (facts.evolves_from is None and len(side.bench) < side.bench_max) \
            or any(getattr(ctx.facts(body.card.card_id), "name", None) == facts.evolves_from
                   for body in side.bodies)
        if not deployable:
            return 0.0
        configuration = ctx.configuration
        from .worth import _forward_lines

        line = (facts, *(ctx.facts(card_id)
                         for card_id in _forward_lines().get(facts.name, ())))
        line = tuple(card for card in line if isinstance(card, PokemonCard))
        attack = max(((float(item.damage or item.damage_fix or item.damage_max or 0)
                       + float(bench_reach(item)))
                      / DAMAGE_UNIT_HP / max(1, len(item.cost))
                      for card in line for item in card.attacks), default=0.0)
        draw = max((sum(_quantity(clause.amount) * _prospective_condition(
            clause.condition, side, board, ctx) for clause in ability.clauses
                              if clause.kind == "draw")
                    for card in line for ability in card.abilities), default=0.0)
        self_cost = max((sum(_prospective_condition(clause.condition, side, board, ctx)
                             for clause in ability.clauses
                             if clause.rider in {"shuffle_self_in", "self_shuffle_in"})
                         for card in line for ability in card.abilities), default=0.0)
        return (facts.hp / DAMAGE_UNIT_HP * configuration["body.hp_per_100"]
                + attack * configuration["combat.attack_future"]
                + draw * configuration["ability.draw_cards"]
                + self_cost * configuration["ability.self_cost"])
    if isinstance(facts, TrainerCard):
        availability = (FUTURE_TURN_DISCOUNT
                        if facts.kind == SUPPORTER and board.turn.supporter_played else 1.0)
        value = 0.0
        configuration = ctx.configuration
        for clause in facts.clauses:
            if clause.kind == "draw":
                branches = draw_branches(
                    clause, side.prize_count, opponent.prize_count,
                    my_hand_size=side.hand_count)
                target = (_quantity(clause.amount) if not branches else
                          sum(mine for mine, _theirs in branches) / len(branches))
                if clause.rider == "shuffle_own_hand_in":
                    target = max(0.0, target - max(0, side.hand_count - 1))
                value += configuration["ability.draw_cards"] * target
                if clause.rider == "shuffle_own_hand_in":
                    value -= sum(max(0.0, card_option_value(
                        held, side, opponent, board, ctx, reaches=reaches))
                        for card in tuple(side.hand)
                        if not isinstance((held := ctx.facts(card.card_id)), TrainerCard))
            elif clause.kind == "fetch":
                value += configuration["ability.search_cards"] * _quantity(clause.amount, 1)
            elif clause.kind in {"accel", "energy_recur", "move_energy"}:
                value += configuration["ability.acceleration"] * _quantity(clause.amount, 1)
                value += configuration["ability.search_cards"] * _quantity(clause.to_hand)
            elif clause.kind in {"gust", "heal", "switch_self", "push_out",
                                 "opp_hand_to_deck", "discard_opp_energy"}:
                value += configuration["ability.denial"]
        return availability * max(0.0, value)
    return 0.0


def hidden_zone_expectation(count, side, opponent_side, board, ctx, belief, *,
                            option_value=None) -> float:
    if belief is None or not belief.candidates:
        return float(count)
    expectation = float(belief.unknown_mass)
    represented = float(belief.unknown_mass)
    option_value = (lambda facts: card_option_value(
        facts, side, opponent_side, board, ctx)) if option_value is None else option_value
    for candidate in belief.candidates:
        resources = tuple((int(card_id), max(0.0, float(probability)))
                          for card_id, probability in candidate.resources.items()
                          if probability > 0)
        mass = sum(probability for _card_id, probability in resources)
        quality = (1.0 if not mass else sum(
            probability * (1.0 + max(0.0, option_value(ctx.facts(card_id))))
            for card_id, probability in resources) / mass)
        expectation += candidate.probability * quality
        represented += candidate.probability
    expectation += max(0.0, 1.0 - represented)
    return float(count) * expectation


def _prospective_condition(condition, side, board, ctx) -> float:
    if not condition:
        return 1.0
    condition = str(condition)
    if condition.endswith("_in_play"):
        wanted = condition.removesuffix("_in_play").replace("_", " ").casefold()
        return float(any(name.casefold() == wanted for name in _side_names(side, ctx)))
    if condition == "pokemon_ko_last_turn":
        return float(_knockout_visible(board))
    return 0.0


__all__ = (
    "Capability", "attack_damage", "best_current_damage", "best_energy_marginal",
    "body_capability",
    "card_option_value", "energy_marginal", "hidden_zone_expectation", "payment_fraction",
    "recoverable_discard_ids", "unmet_cost_slots",
)
