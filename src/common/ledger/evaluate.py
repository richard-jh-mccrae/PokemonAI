"""Linear Ledger evaluation: extract board facts, then apply configured coefficients once."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from common.observation import ObservationState
from common.observation.nodes import Body, Side
from common.cards import card_clauses
from common.cards.card_facts import EnergyCard, PokemonCard

from .features import FEATURE_CATALOG
from .worth import (Demand, DemandState, EvaluationModel, _liveness, _unfilled,
                    any_attack_payable,
                    development_reach_units,
                    legal_line_reach, line_reach, opponent_line_reach, best_payable_damage,
                    usable_units)


@dataclass(frozen=True)
class FeatureActivation:
    feature: str
    value: float
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class FeatureContribution:
    feature: str
    activation: float
    coefficient: float
    value: float
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class Valuation:
    total: float
    parts: tuple[tuple[str, float], ...]
    gaps: tuple[str, ...]
    activations: tuple[FeatureActivation, ...] = ()
    contributions: tuple[FeatureContribution, ...] = ()

    def part(self, name: str) -> float:
        return next((value for label, value in self.parts if label == name), 0.0)


class _Trace:
    def __init__(self, ctx: EvaluationModel):
        self.ctx = ctx
        self.by_feature: dict[str, float] = {}
        self.provenance: dict[str, set[str]] = {}
        self.by_part: dict[str, float] = {}
        self.gaps: list[str] = []

    def add(self, part: str, feature: str, activation: float, *,
            provenance: str | None = None) -> None:
        activation = float(activation)
        if not activation:
            return
        if feature not in FEATURE_CATALOG:
            raise KeyError(f"unregistered Valuation Feature {feature!r}")
        self.by_feature[feature] = self.by_feature.get(feature, 0.0) + activation
        self.provenance.setdefault(feature, set()).add(provenance or part)
        self.by_part[part] = self.by_part.get(part, 0.0) + (
            activation * self.ctx.configuration[feature])

    def finish(self) -> Valuation:
        activations = tuple(FeatureActivation(
            feature, value, tuple(sorted(self.provenance[feature])))
                            for feature, value in sorted(self.by_feature.items()))
        contributions = tuple(FeatureContribution(
            item.feature, item.value, self.ctx.configuration[item.feature],
            item.value * self.ctx.configuration[item.feature], item.provenance)
            for item in activations)
        total = sum(item.value for item in contributions)
        return Valuation(total, tuple(sorted(self.by_part.items())), tuple(self.gaps),
                         activations, contributions)


def evaluate(board: ObservationState, ctx: EvaluationModel) -> Valuation:
    trace = _Trace(ctx)
    _opponent_traits(trace, ctx, board)
    result = board.turn.result
    if isinstance(result, int) and not isinstance(result, bool) and result >= 0 and result != 2:
        trace.add("result", "result.win", 1.0 if result == board.seat else -1.0)

    for label, side, sign in (("me", board.me, 1.0), ("them", board.them, -1.0)):
        _side(trace, label, side, sign, ctx, board,
              deck_counts=board.deck_counts if sign > 0 else None)

    trace.add("prize_race", "prize.race",
              board.them.prize_count - board.me.prize_count)
    return trace.finish()


def _opponent_traits(trace: _Trace, ctx: EvaluationModel, board: ObservationState) -> None:
    if ctx.opponent is None:
        return
    for candidate in ctx.opponent.candidates:
        for trait in candidate.traits:
            if trait.value is False:
                continue
            feature = (f"trait.{trait.name}.{trait.value}" if isinstance(trait.value, str)
                       else f"trait.{trait.name}")
            context = _trait_context(trait.name, board, ctx, trait.value)
            trace.add(
                "opponent.traits", feature, candidate.probability * context,
                provenance=f"belief:{candidate.archetype or 'anonymous'}:{trait.name}")
    trace.add("opponent.beliefs", "belief.unknown_archetype", ctx.opponent.unknown_mass)


def _trait_context(name: str, board: ObservationState, ctx: EvaluationModel, value=None) -> float:
    """Observable exposure that makes an opponent claim relevant on this board."""
    if name == "opp_item_locks":
        return sum(getattr(ctx.facts(card.card_id), "kind", None) == "item"
                   for card in (board.me.hand or ()))
    if name == "opp_spreads_bench":
        return len(board.me.bench)
    if name == "opp_hand_size_attacker":
        return board.me.hand_count
    if name == "opp_special_energy_fragile":
        return sum(getattr(ctx.facts(card.card_id), "kind", None) == "special_energy"
                   for body in board.me.bodies for card in body.energy_cards)
    if name == "opp_deckout_vulnerable":
        return max(0, 10 - board.them.deck_count)
    if name == "opp_is_engine_dependent":
        return sum(bool(
            {"draw_engine", "search_engine"}.intersection(
                getattr(ctx.facts(body.card.card_id), "default_roles", ()) or ())
            or {"draw", "fetch"}.intersection(
                clause.kind for clause in card_clauses(ctx.facts(body.card.card_id))))
                   for body in board.them.bodies)
    if name == "opp_donk_vulnerable":
        return float(len(board.them.bench) == 0)
    if name == "opp_no_pivot":
        active = board.them.active
        if active is None:
            return 0.0
        pressured = any(getattr(board.them, status) for status in (
            "asleep", "paralyzed", "confused", "poisoned", "burned"))
        return float(pressured or getattr(ctx.facts(active.card.card_id), "retreat_cost", 0) > 0)
    if name == "opp_is_heal_wall":
        return sum(max(0, body.max_hp - body.hp) for body in board.them.bodies) / 100.0
    if name == "opp_single_prize":
        return sum(_prize_value(body, ctx) == 1 for body in board.them.bodies)
    if name == "opp_accel_dependent":
        return sum(len(body.energies) for body in board.them.bodies)
    if name == "opp_caps_big_hits":
        return max((attack.damage for body in board.me.bodies
                    for attack in getattr(ctx.facts(body.card.card_id), "attacks", ()) or ()), default=0) / 100.0
    if name == "opp_comeback_disruptor":
        return max(0, board.them.prize_count - board.me.prize_count)
    if name == "opp_effect_immune_bodies":
        effect_kinds = {
            "attack_debuff", "attack_lock", "burn", "confuse", "damage_counters",
            "discard_opp_energy", "no_retreat", "poison", "push_out", "retreat_lock",
            "sleep",
        }
        return sum(bool(effect_kinds.intersection(
            clause.kind for clause in attack.clauses))
                   for body in board.me.bodies
                   for attack in getattr(ctx.facts(body.card.card_id), "attacks", ()) or ())
    if name == "opp_ex_damage_immune":
        return sum(bool(getattr(ctx.facts(body.card.card_id), "ex", False)
                        or getattr(ctx.facts(body.card.card_id), "mega_ex", False))
                   for body in board.me.bodies)
    if name == "opp_pierces_active_effects":
        active = board.me.active
        statuses = sum(bool(getattr(board.me, status)) for status in (
            "asleep", "paralyzed", "confused", "poisoned", "burned"))
        return statuses + (len(active.tools) if active is not None else 0)
    if name == "opp_tempo":
        turn = max(0, board.turn.number)
        return {"fast": 1.0 / (turn + 1.0), "midrange": 1.0,
                "slow": turn / (turn + 1.0)}[value]
    raise KeyError(f"opponent Trait {name!r} has no context compiler")


def _side(trace: _Trace, label: str, side: Side, sign: float, ctx: EvaluationModel,
          board: ObservationState, *, deck_counts) -> None:
    doomed = _active_doomed(board.them if sign > 0 else board.me, side, ctx)
    demand = Demand.read(side, ctx, board.turn)
    reach = (line_reach(
        demand.hand_name_counts, deck_counts, ctx, hand=demand.hand, turn=board.turn)
        if sign > 0 else opponent_line_reach(ctx))
    seen: dict[int, int] = {}
    for body in side.bodies:
        body_reach = legal_line_reach(body, reach, ctx, demand.hand, board.turn)
        _body(trace, f"{label}.bodies", body, sign, ctx, own=sign > 0,
              active=body is side.active, doomed=doomed and body is side.active,
              reach=body_reach)
        opponent = board.them if sign > 0 else board.me
        _situational_functions(
            trace, f"{label}.bodies", ctx.facts(body.card.card_id), side, opponent, demand, ctx,
            deck_counts, sign=sign)
        copies = seen.get(body.card.card_id, 0)
        if copies:
            trace.add(f"{label}.bodies", "copy.surplus_in_play", -sign * copies)
        seen[body.card.card_id] = copies + 1

    if side.active is not None:
        trace.add(f"{label}.active", "active.premium", sign)
        if not any_attack_payable(ctx.facts(side.active.card.card_id), side.active.energies):
            trace.add(f"{label}.active", "active.unready_fraction", -sign)
    trace.add(f"{label}.bench_slots", "bench.open_slot",
              sign * max(0, side.bench_max - len(side.bench)))
    trace.add(f"{label}.liability", "body.prize_liability", -sign * sum(
        max(0, _prize_value(body, ctx) - 1) for body in side.bodies))

    if sign > 0 and side.hand is not None:
        demand = Demand.read(side, ctx, board.turn)
        copies = Counter(demand.body_id_counts)
        for card in side.hand:
            facts = ctx.facts(card.card_id)
            provision = (facts.clause("energy_provide")
                         if isinstance(facts, EnergyCard) else None)
            evolved_targets = [body for body in demand.bodies
                               if getattr(ctx.facts(body.card.card_id), "evolves_from", None)]
            if (provision is not None and provision.amount_on_evolution
                    and any(_can_absorb_multi_provision(body, provision, ctx)
                            for body in evolved_targets)):
                extra = max(0, int(provision.amount_on_evolution)
                            - int(provision.amount or 1))
                trace.add(f"{label}.hand", "continuation.multi_provision_in_hand",
                          sign * extra)
            feature, capacity = _hand_feature(
                card.card_id, facts, demand, copies[card.card_id], ctx, deck_counts)
            placement = {
                "zone.in_hand": "in_hand_live",
                "demand.dead": "in_hand_dead",
                "demand.setup": "in_hand_setup",
                "demand.colorless_only": "in_hand_colorless",
                "copy.surplus": "in_hand_surplus",
            }[feature]
            _card(trace, f"{label}.hand", card.card_id, facts, sign, ctx, own=True,
                  placement=placement)
            _situational_functions(
                trace, f"{label}.hand", facts, side, board.them, demand, ctx,
                deck_counts, sign=sign)
            trace.add(f"{label}.hand", feature, sign)
            if (isinstance(facts, PokemonCard) and facts.evolves_from
                    and demand.body_name_counts.get(facts.evolves_from, 0)):
                trace.add(f"{label}.hand", "development.ready_evolution", sign)
            copies[card.card_id] += 1
    else:
        trace.add(f"{label}.hand", "context.opponent_unknown_hand",
                  sign * side.hand_count)
        trace.add(f"{label}.hand", "zone.in_hand", sign * side.hand_count)

    if sign > 0 and deck_counts is not None:
        for card_id, count in deck_counts:
            facts = ctx.facts(card_id)
            _card(trace, f"{label}.deck", card_id, facts, sign * count, ctx, own=True,
                  placement="in_deck")
            trace.add(f"{label}.deck", "zone.in_deck", sign * count)
    else:
        unknown = ("belief.unknown_deck_card" if sign > 0
                   else "context.opponent_unknown_deck")
        trace.add(f"{label}.deck", unknown, sign * side.deck_count)
        trace.add(f"{label}.deck", "zone.in_deck", sign * side.deck_count)

    for card in side.discard:
        _card(trace, f"{label}.discard", card.card_id, ctx.facts(card.card_id), sign, ctx, own=sign > 0,
              placement="in_discard")
        trace.add(f"{label}.discard", "zone.in_discard", sign)

    for status in ("asleep", "paralyzed", "confused", "poisoned", "burned"):
        trace.add(f"{label}.status", f"status.{status}",
                  -sign * float(getattr(side, status, 0) or 0))


def _body(trace: _Trace, part: str, body: Body, sign: float, ctx: EvaluationModel, *,
          own: bool, active: bool, doomed: bool, reach) -> None:
    body_facts = ctx.facts(body.card.card_id)
    _card(trace, part, body.card.card_id, body_facts, sign, ctx, own=own,
          placement="in_play")
    trace.add(part, "zone.in_play", sign)
    trace.add(part, "body.hp_per_100", sign * body.max_hp / 100.0)
    missing = 0.0
    if body.max_hp > 0:
        missing = max(0.0, min(1.0, (body.max_hp - max(0, body.hp)) / body.max_hp))
        trace.add(part, "damage.floor", -sign * missing)
    if doomed:
        trace.add(part, "active.doomed", -sign)

    usable = usable_units(body_facts, body.energies, ctx, reach)
    visible_reach, next_reach = development_reach_units(
        body_facts, body.energies, ctx, reach)
    useless = max(0, len(body.energies) - usable)
    rentals = 0
    priced_energy_cards = [card for card in body.energy_cards
                           if active or not _discards_end_of_turn(ctx.facts(card.card_id))]
    interaction_amount = (sign * min(1.0, usable / len(priced_energy_cards))
                          if priced_energy_cards else 0.0)
    for card in body.energy_cards:
        facts = ctx.facts(card.card_id)
        if not active and _discards_end_of_turn(facts):
            rentals += 1
            continue
        _card(trace, part, card.card_id, facts, sign, ctx, own=own,
              placement="attached_usable", interaction_amount=interaction_amount)
    if body.energies and not body.energy_cards:
        trace.add(part, "kind.energy", sign * len(body.energies))
    usable = max(0, usable - rentals)
    trace.add(part, "zone.attached_usable", sign * usable)
    trace.add(part, "development.visible_reach", sign * visible_reach)
    trace.add(part, "development.next_turn_reach", sign * next_reach)
    trace.add(part, "zone.attached_useless", sign * useless)
    trace.add(part, "context.damaged_attached", sign * usable * missing)
    trace.add(part, "energy.concentration", sign * max(0, usable - 1))

    for card in body.tools:
        _card(trace, part, card.card_id, ctx.facts(card.card_id), sign, ctx, own=own,
              placement="tool_attached")
        trace.add(part, "zone.tool_attached", sign)
    for card in body.pre_evolution:
        _card(trace, part, card.card_id, ctx.facts(card.card_id), sign, ctx, own=own,
              placement="under_body")
        trace.add(part, "zone.under_body", sign)


def _card(trace: _Trace, part: str, card_id: int, facts, amount: float,
          ctx: EvaluationModel, *, own: bool, placement: str,
          interaction_amount: float | None = None) -> None:
    situated = amount if interaction_amount is None else interaction_amount
    declared = ctx.card_roles(card_id) if own else ()
    roles = set(declared or getattr(facts, "default_roles", ()) or ())
    expected: dict[str, float] = {role: 1.0 for role in roles}
    if not own and ctx.opponent is not None:
        observed = set(ctx.opponent.observed_roles.get(int(card_id), ()))
        for role in observed:
            expected[role] = 1.0
    for role, probability in expected.items():
        trace.add(part, f"role.{role}", amount * probability)
        trace.add(part, f"interaction.role.{role}.{placement}", situated * probability)
    if not own and ctx.opponent is not None:
        observed = set(ctx.opponent.observed_roles.get(int(card_id), ()))
        for candidate in ctx.opponent.candidates:
            for role in candidate.roles.get(int(card_id), ()):
                if role not in observed and role not in roles:
                    trace.add(
                        part, f"role.{role}", amount * candidate.probability,
                        provenance=f"{part}:belief:{candidate.archetype or 'anonymous'}")
                    trace.add(
                        part, f"interaction.role.{role}.{placement}",
                        situated * candidate.probability,
                        provenance=f"{part}:belief:{candidate.archetype or 'anonymous'}")

    if facts is None:
        trace.add(part, "coverage.unknown_card", amount)
        trace.gaps.append(f"{part}: unknown card {int(card_id)}")
        return
    if getattr(facts, "covers", None) != "full":
        trace.add(part, "coverage.unknown_card", amount)
        verdict = getattr(facts, "covers", None) or "unruled"
        trace.gaps.append(f"{part}: incomplete card coverage {int(card_id)} ({verdict})")
    if isinstance(facts, PokemonCard):
        kind = "pokemon"
    elif isinstance(facts, EnergyCard):
        kind = "special_energy" if facts.kind == "special_energy" else "energy"
    else:
        kind = getattr(facts, "kind", "item")
    trace.add(part, f"kind.{kind}", amount)
    trace.add(part, f"interaction.kind.{kind}.{placement}", situated)
def _hand_feature(card_id, facts, demand: Demand, copies_before: int,
                  ctx: EvaluationModel, deck_counts) -> tuple[str, int | None]:
    scale, capacity = _liveness(card_id, facts, demand, ctx, deck_counts)
    if capacity is not None and copies_before >= capacity:
        return "copy.surplus", capacity
    if scale is DemandState.DEAD:
        return "demand.dead", capacity
    if scale is DemandState.SETUP:
        return "demand.setup", capacity
    if scale is DemandState.COLORLESS_ONLY:
        return "demand.colorless_only", capacity
    return "zone.in_hand", capacity


def _situational_functions(trace: _Trace, part: str, facts, side: Side, opponent: Side,
                           demand: Demand, ctx: EvaluationModel, deck_counts, *, sign: float) -> None:
    clauses = list(getattr(facts, "clauses", ()) or ())
    for ability in getattr(facts, "abilities", ()) or ():
        clauses.extend(ability.clauses)
    for attack in getattr(facts, "attacks", ()) or ():
        clauses.extend(attack.clauses)
    kinds = {clause.kind for clause in clauses}
    def emit(feature, value):
        trace.add(part, feature, sign * value)
    if "draw" in kinds:
        emit("function.draw.hand_deficit", max(0, 7 - side.hand_count) / 7)
    if "fetch" in kinds:
        state, _capacity = _liveness(0, facts, demand, ctx, deck_counts)
        emit("function.fetch.live_target", float(state is not DemandState.DEAD))
    if "gust" in kinds:
        emit("function.gust.bench_target", float(bool(opponent.bench)))
    if "heal" in kinds:
        damage = sum(max(0, body.max_hp - body.hp) for body in side.bodies)
        emit("function.heal.damage_present", min(1.0, damage / 100.0))
    if kinds.intersection({"accel", "energy_double", "energy_recur", "move_energy"}):
        open_slots = sum(any(_unfilled(attack.cost, Counter(body.energies)) != (Counter(), 0)
                             for attack in getattr(ctx.facts(body.card.card_id), "attacks", ()) or ())
                         for body in side.bodies)
        emit("function.accel.open_energy_slot", min(1.0, open_slots))
    if kinds.intersection({"self_switch", "switch_self", "push_out"}):
        emit("function.switch.active_pressure", float(side.active is not None and bool(side.bench)))
    if kinds.intersection({"opp_hand_to_deck", "mill"}):
        emit("function.disruption.opponent_hand", max(0, opponent.hand_count - 3) / 4)
    if kinds.intersection({"discard_opp_energy", "energy_bounce", "item_lock", "attack_lock",
                           "no_retreat", "retreat_lock"}):
        resources = sum(len(body.energies) for body in opponent.bodies)
        emit("function.denial.opponent_resource", min(1.0, resources))
    if kinds.intersection({"bench_snipe", "bench_spread", "damage_counters"}):
        emit("function.bench_pressure.target_count", len(opponent.bench))
    if kinds.intersection({"damage_protection", "damage_reduction", "prevent_damage",
                           "prevent_effects", "hp_bonus"}):
        pressure = max((attack.damage for body in opponent.bodies
                        for attack in getattr(ctx.facts(body.card.card_id), "attacks", ()) or ()), default=0)
        emit("function.protection.incoming_pressure", pressure / 100.0)
    if kinds.intersection({"attack_debuff", "burn", "confuse", "sleep"}):
        emit("function.status.active_target", float(opponent.active is not None))
    if kinds.intersection({"attack_cost_reduction", "cost_reduction", "retreat_reduction"}):
        open_cost = sum(bool(_unfilled(attack.cost, Counter(body.energies)) != (Counter(), 0))
                        for body in side.bodies
                        for attack in getattr(ctx.facts(body.card.card_id), "attacks", ()) or ())
        emit("function.cost_reduction.open_cost", min(1.0, open_cost))
    if kinds.intersection({"recoil", "self_discard_energy", "self_mill", "self_return",
                           "self_shuffle_in"}):
        emit("function.self_cost.exposure", 1.0)
    if "ability_suppression" in kinds:
        emit("function.suppression.ability_target", sum(
            bool(getattr(ctx.facts(body.card.card_id), "abilities", ()))
            for body in opponent.bodies))
    if "evolve_early" in kinds:
        emit("function.development.board_fit", sum(
            bool(getattr(ctx.facts(body.card.card_id), "evolves_from", None))
            for body in side.bodies))
    if "move_damage" in kinds:
        damage = sum(max(0, body.max_hp - body.hp) for body in side.bodies)
        emit("function.move_damage.damage_present", damage / 100.0)
    if "ko" in kinds:
        emit("function.ko.active_target", float(opponent.active is not None))
    if kinds.intersection({"stadium_static", "stadium_trigger"}):
        emit("function.stadium.board_fit", len(side.bodies) + len(opponent.bodies))


def _active_doomed(attacker: Side, defender: Side, ctx: EvaluationModel) -> bool:
    if attacker.active is None or defender.active is None:
        return False
    if defender.active.hp <= 0:
        return True
    damage = best_payable_damage(ctx.facts(attacker.active.card.card_id),
                                 attacker.active.energies,
                                 ctx.facts(defender.active.card.card_id))
    return 0 < defender.active.hp <= damage


def _can_absorb_multi_provision(body: Body, provision, ctx: EvaluationModel) -> bool:
    amount = int(provision.amount_on_evolution or 0)
    attached = Counter(body.energies)
    return any(sum(open_typed.values()) + open_colorless >= amount
               for attack in getattr(ctx.facts(body.card.card_id), "attacks", ()) or ()
               for open_typed, open_colorless in [_unfilled(attack.cost, attached)])


def _discards_end_of_turn(facts) -> bool:
    clause = facts.clause("energy_provide") if facts is not None else None
    return clause is not None and clause.rider == "discard_eot"


def _prize_value(body: Body, ctx: EvaluationModel) -> int:
    return getattr(ctx.facts(body.card.card_id), "prize_value", 1)


__all__ = ("FeatureActivation", "FeatureContribution", "Valuation", "evaluate")
