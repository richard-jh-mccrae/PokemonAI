"""Linear Ledger evaluation: extract board facts, then apply configured coefficients once."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math

from common.observation import ObservationState
from common.observation.nodes import Body, Side
from common.cards import card_clauses
from common.cards.card_facts import EnergyCard, PokemonCard

from .activation import (DAMAGE_UNIT_HP, ActivationCompiler, ActivationEnvironment,
                         FeatureActivation)
from .features import FEATURE_CATALOG
from .prizes import PrizeMap, derive_prize_map
from .worth import (Demand, DemandState, EvaluationModel, _liveness, _unfilled,
                    any_attack_payable,
                    development_reach_units,
                    legal_line_reach, line_reach, opponent_evaluation,
                    opponent_line_reach, best_payable_damage, usable_units)


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
    prize_map: PrizeMap | None = None

    def part(self, name: str) -> float:
        return next((value for label, value in self.parts if label == name), 0.0)


DRAW_RESULT_CODE = 2


class _Trace:
    def __init__(self, ctx: EvaluationModel):
        self.ctx = ctx
        self.compiler = ActivationCompiler()
        self.by_feature: dict[str, float] = {}
        self.provenance: dict[str, set[str]] = {}
        self.by_part: dict[str, float] = {}
        self.gaps: list[str] = []

    def emit(self, part: str, source: str, claims, activation: float, *,
             provenance: str | None = None, **environment) -> None:
        claims = tuple(claims)
        if not self.compiler.catalog.has_activation_rules(source, claims):
            raise KeyError(f"Feature Catalog has no {source!r} rule for {claims!r}")
        compiled = self.compiler.compile(
            source, claims, ActivationEnvironment(scale=activation, **environment))
        for item in compiled:
            self.record(part, item, provenance=provenance)

    def record(self, part: str, item: FeatureActivation, *,
               provenance: str | None = None) -> None:
        feature = item.feature
        activation = float(item.value)
        if not math.isfinite(activation):
            raise ValueError(f"non-finite activation for {feature!r}")
        if not activation:
            return
        if feature not in FEATURE_CATALOG:
            raise KeyError(f"unregistered Valuation Feature {feature!r}")
        self.by_feature[feature] = self.by_feature.get(feature, 0.0) + activation
        self.provenance.setdefault(feature, set()).update(
            item.provenance or (provenance or part,))
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
    opponent = opponent_evaluation(board, ctx)
    if opponent is not None:
        trace.gaps.extend(opponent.failures)
    _opponent_traits(trace, ctx, board, opponent)
    result = board.turn.result
    if isinstance(result, int) and not isinstance(result, bool) \
            and result >= 0 and result != DRAW_RESULT_CODE:
        trace.emit("result", "observation", ("terminal_win",),
                   1.0 if result == board.seat else -1.0)

    for label, side, sign in (("me", board.me, 1.0), ("them", board.them, -1.0)):
        _side(trace, label, side, sign, ctx, board, opponent,
              deck_counts=board.deck_counts if sign > 0 else None)

    trace.emit("prize_race", "observation", ("prize_advantage",),
               board.them.prize_count - board.me.prize_count)
    prize_map = derive_prize_map(board, ctx)
    trace.emit("prize_map", "observation", ("prize_advantage",), prize_map.overrun)
    result = trace.finish()
    return Valuation(result.total, result.parts, result.gaps, result.activations,
                     result.contributions, prize_map)


def _opponent_traits(trace: _Trace, ctx: EvaluationModel, board: ObservationState,
                     opponent) -> None:
    if opponent is None:
        return
    compiler = ActivationCompiler()
    for candidate in opponent.candidates:
        for trait in candidate.traits:
            if trait.value is False:
                continue
            provenance = f"belief:{candidate.archetype or 'anonymous'}:{trait.name}"
            activations = compiler.compile(
                "opponent_trait", (trait.name,), ActivationEnvironment(
                    scale=candidate.probability, provenance=(provenance,), board=board,
                    evaluation_model=ctx, opponent=board.them, candidate=candidate,
                    claim_value=trait.value))
            for activation in activations:
                trace.record("opponent.traits", activation, provenance=provenance)
        for mechanic in candidate.mechanics:
            provenance = f"cards:{candidate.archetype or 'anonymous'}:{mechanic.name}"
            activations = compiler.compile(
                "opponent_mechanic", (mechanic.name,), ActivationEnvironment(
                    scale=candidate.probability * mechanic.probability,
                    provenance=(provenance,), board=board, evaluation_model=ctx,
                    candidate=candidate))
            for activation in activations:
                trace.record("opponent.mechanics", activation, provenance=provenance)
    trace.emit("opponent.beliefs", "observation", ("unknown_opponent_archetype",),
               opponent.unknown_mass)


def _side(trace: _Trace, label: str, side: Side, sign: float, ctx: EvaluationModel,
          board: ObservationState, opponent, *, deck_counts) -> None:
    doomed = _active_doomed(board.them if sign > 0 else board.me, side, ctx)
    demand = Demand.read(side, ctx, board.turn)
    reach = (line_reach(
        demand.hand_name_counts, deck_counts, ctx, hand=demand.hand, turn=board.turn)
        if sign > 0 else opponent_line_reach(ctx, opponent))
    seen: dict[int, int] = {}
    for body in side.bodies:
        body_reach = legal_line_reach(body, reach, ctx, demand.hand, board.turn)
        _body(trace, f"{label}.bodies", body, sign, ctx, own=sign > 0,
              active=body is side.active, doomed=doomed and body is side.active,
              reach=body_reach, opponent=opponent)
        opposing_side = board.them if sign > 0 else board.me
        _situational_functions(
            trace, f"{label}.bodies", ctx.facts(body.card.card_id), side, opposing_side,
            demand, ctx,
            deck_counts, sign=sign)
        copies = seen.get(body.card.card_id, 0)
        if copies:
            trace.emit(f"{label}.bodies", "observation", ("surplus_in_play_copy",),
                       -sign * copies)
        seen[body.card.card_id] = copies + 1

    if side.active is not None:
        trace.emit(f"{label}.active", "observation", ("active_body",), sign)
        if not any_attack_payable(ctx.facts(side.active.card.card_id), side.active.energies):
            trace.emit(f"{label}.active", "observation", ("unready_active",), -sign)
    trace.emit(f"{label}.bench_slots", "observation", ("open_bench_slot",),
               sign * max(0, side.bench_max - len(side.bench)))
    trace.emit(f"{label}.liability", "observation", ("extra_prize_liability",),
               -sign * sum(max(0, _prize_value(body, ctx) - 1)
                           for body in side.bodies))

    if sign > 0 and side.hand is not None:
        demand = Demand.read(side, ctx, board.turn)
        copies = Counter(demand.body_id_counts)
        for card in side.hand:
            facts = ctx.facts(card.card_id)
            claim, capacity = _hand_claim(
                card.card_id, facts, demand, copies[card.card_id], ctx, deck_counts)
            placement = {
                "card_in_hand": "in_hand_live",
                "dead_hand_card": "in_hand_dead",
                "setup_hand_card": "in_hand_setup",
                "colorless_only_hand_card": "in_hand_colorless",
                "surplus_hand_copy": "in_hand_surplus",
            }[claim]
            _card(trace, f"{label}.hand", card.card_id, facts, sign, ctx, own=True,
                  placement=placement, opponent=opponent)
            _situational_functions(
                trace, f"{label}.hand", facts, side, board.them, demand, ctx,
                deck_counts, sign=sign)
            trace.emit(f"{label}.hand", "observation", (claim,), sign)
            if (isinstance(facts, PokemonCard) and facts.evolves_from
                    and demand.body_name_counts.get(facts.evolves_from, 0)):
                trace.emit(f"{label}.hand", "observation",
                           ("ready_evolution_in_hand",), sign)
            copies[card.card_id] += 1
    else:
        trace.emit(f"{label}.hand", "observation", ("unknown_opponent_hand_card",),
                   sign * side.hand_count)
        trace.emit(f"{label}.hand", "observation", ("card_in_hand",),
                   sign * side.hand_count)

    if sign > 0 and deck_counts is not None:
        for card_id, count in deck_counts:
            facts = ctx.facts(card_id)
            _card(trace, f"{label}.deck", card_id, facts, sign * count, ctx, own=True,
                  placement="in_deck", opponent=opponent)
            trace.emit(f"{label}.deck", "observation", ("card_in_deck",),
                       sign * count)
    else:
        unknown = ("unknown_own_deck_card" if sign > 0
                   else "unknown_opponent_deck_card")
        trace.emit(f"{label}.deck", "observation", (unknown,), sign * side.deck_count)
        trace.emit(f"{label}.deck", "observation", ("card_in_deck",),
                   sign * side.deck_count)

    for card in side.discard:
        _card(trace, f"{label}.discard", card.card_id, ctx.facts(card.card_id), sign, ctx,
              own=sign > 0, placement="in_discard", opponent=opponent)
        trace.emit(f"{label}.discard", "observation", ("card_in_discard",), sign)

    for status in ("asleep", "paralyzed", "confused", "poisoned", "burned"):
        trace.emit(f"{label}.status", "observation", (f"{status}_status",),
                   -sign * float(getattr(side, status, 0) or 0))


def _body(trace: _Trace, part: str, body: Body, sign: float, ctx: EvaluationModel, *,
          own: bool, active: bool, doomed: bool, reach, opponent) -> None:
    body_facts = ctx.facts(body.card.card_id)
    if body_facts is not None and not isinstance(body_facts, PokemonCard):
        trace.emit(part, "observation", ("uncovered_card",), sign)
        trace.emit(part, "observation", ("card_in_play",), sign)
        trace.emit(part, "observation", ("body_hp_units",),
                   sign * body.max_hp / DAMAGE_UNIT_HP)
        trace.gaps.append(f"{part}: non-Pokemon body {body.card.card_id}")
        return
    _card(trace, part, body.card.card_id, body_facts, sign, ctx, own=own,
          placement="in_play", opponent=opponent)
    trace.emit(part, "observation", ("card_in_play",), sign)
    trace.emit(part, "observation", ("body_hp_units",),
               sign * body.max_hp / DAMAGE_UNIT_HP)
    missing = 0.0
    if body.max_hp > 0:
        missing = max(0.0, min(1.0, (body.max_hp - max(0, body.hp)) / body.max_hp))
        trace.emit(part, "observation", ("body_damage_fraction",), -sign * missing)
    if doomed:
        trace.emit(part, "observation", ("doomed_active",), -sign)

    usable = usable_units(body_facts, body.energies, ctx, reach)
    visible_reach, next_reach = development_reach_units(
        body_facts, body.energies, ctx, reach)
    useless = max(0, len(body.energies) - usable)
    rentals = 0
    energy_rows = []
    for card in body.energy_cards:
        facts = ctx.facts(card.card_id)
        riders = tuple(clause.rider for clause in card_clauses(facts)
                       if clause.rider is not None)
        rental = (() if active else ActivationCompiler().compile(
            "attached_energy", riders, ActivationEnvironment(scale=sign)))
        energy_rows.append((card, facts, rental))
    priced_energy_cards = [card for card, _facts, rental in energy_rows if not rental]
    interaction_amount = (sign * min(1.0, usable / len(priced_energy_cards))
                          if priced_energy_cards else 0.0)
    for card, facts, rental in energy_rows:
        if rental:
            rentals += 1
            for activation in rental:
                trace.record(part, activation)
            continue
        _card(trace, part, card.card_id, facts, sign, ctx, own=own,
              placement="attached_usable", interaction_amount=interaction_amount,
              opponent=opponent)
    if body.energies and not body.energy_cards:
        trace.emit(part, "card", ("kind:energy",), sign * len(body.energies))
    usable = max(0, usable - rentals)
    trace.emit(part, "observation", ("usable_attached_energy",), sign * usable)
    trace.emit(part, "observation", ("visible_development_reach",),
               sign * visible_reach)
    trace.emit(part, "observation", ("next_turn_development_reach",), sign * next_reach)
    trace.emit(part, "observation", ("useless_attached_energy",), sign * useless)
    trace.emit(part, "observation", ("usable_energy_on_damaged_body",),
               sign * usable * missing)
    trace.emit(part, "observation", ("concentrated_energy",),
               sign * max(0, usable - 1))

    for card in body.tools:
        _card(trace, part, card.card_id, ctx.facts(card.card_id), sign, ctx, own=own,
              placement="tool_attached", opponent=opponent)
        trace.emit(part, "observation", ("attached_tool",), sign)
    for card in body.pre_evolution:
        _card(trace, part, card.card_id, ctx.facts(card.card_id), sign, ctx, own=own,
              placement="under_body", opponent=opponent)
        trace.emit(part, "observation", ("card_under_body",), sign)


def _card(trace: _Trace, part: str, card_id: int, facts, amount: float,
          ctx: EvaluationModel, *, own: bool, placement: str,
          interaction_amount: float | None = None, opponent=None) -> None:
    situated = amount if interaction_amount is None else interaction_amount
    declared = ctx.card_roles(card_id) if own else ()
    roles = set(declared or getattr(facts, "default_roles", ()) or ())
    expected: dict[str, float] = {role: 1.0 for role in roles}
    for role, probability in expected.items():
        trace.emit(part, "card", (f"role:{role}",), amount * probability)
        trace.emit(part, "card", (f"role:{role}:{placement}",),
                   situated * probability)
    if not own and opponent is not None:
        for candidate in opponent.candidates:
            for role in candidate.roles.get(int(card_id), ()):
                if role not in roles:
                    trace.emit(
                        part, "card", (f"role:{role}",), amount * candidate.probability,
                        provenance=f"{part}:belief:{candidate.archetype or 'anonymous'}")
                    trace.emit(
                        part, "card", (f"role:{role}:{placement}",),
                        situated * candidate.probability,
                        provenance=f"{part}:belief:{candidate.archetype or 'anonymous'}")

    if facts is None:
        trace.emit(part, "observation", ("uncovered_card",), amount)
        trace.gaps.append(f"{part}: unknown card {int(card_id)}")
        return
    if getattr(facts, "covers", None) != "full":
        trace.emit(part, "observation", ("uncovered_card",), amount)
        verdict = getattr(facts, "covers", None) or "unruled"
        trace.gaps.append(f"{part}: incomplete card coverage {int(card_id)} ({verdict})")
    if isinstance(facts, PokemonCard):
        kind = "pokemon"
    elif isinstance(facts, EnergyCard):
        kind = "special_energy" if facts.kind == "special_energy" else "energy"
    else:
        kind = getattr(facts, "kind", "item")
    trace.emit(part, "card", (f"kind:{kind}",), amount)
    trace.emit(part, "card", (f"kind:{kind}:{placement}",), situated)


def _hand_claim(card_id, facts, demand: Demand, copies_before: int,
                ctx: EvaluationModel, deck_counts) -> tuple[str, int | None]:
    scale, capacity = _liveness(card_id, facts, demand, ctx, deck_counts)
    if capacity is not None and copies_before >= capacity:
        return "surplus_hand_copy", capacity
    if scale is DemandState.DEAD:
        return "dead_hand_card", capacity
    if scale is DemandState.SETUP:
        return "setup_hand_card", capacity
    if scale is DemandState.COLORLESS_ONLY:
        return "colorless_only_hand_card", capacity
    return "card_in_hand", capacity


def _situational_functions(trace: _Trace, part: str, facts, side: Side, opponent: Side,
                           demand: Demand, ctx: EvaluationModel, deck_counts, *, sign: float) -> None:
    kinds = {clause.kind for clause in card_clauses(facts)}
    environment = ActivationEnvironment(
        scale=sign, evaluation_model=ctx, side=side, opponent=opponent,
        demand=demand, facts=facts, deck_counts=deck_counts)
    for activation in ActivationCompiler().compile("function", kinds, environment):
        trace.record(part, activation)


def _active_doomed(attacker: Side, defender: Side, ctx: EvaluationModel) -> bool:
    if attacker.active is None or defender.active is None:
        return False
    if defender.active.hp <= 0:
        return True
    damage = best_payable_damage(ctx.facts(attacker.active.card.card_id),
                                 attacker.active.energies,
                                 ctx.facts(defender.active.card.card_id))
    return 0 < defender.active.hp <= damage


def _prize_value(body: Body, ctx: EvaluationModel) -> int:
    return getattr(ctx.facts(body.card.card_id), "prize_value", 1)


__all__ = ("FeatureActivation", "FeatureContribution", "Valuation", "evaluate")
