"""Linear Ledger evaluation: extract board facts, then apply configured coefficients once."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import math

from common.observation import ObservationState
from common.observation.knowledge import KnownDeckTop, KnownOwnPrizes
from common.observation.nodes import Body, Side
from common.cards import card_clauses
from common.cards.card_facts import COLORLESS, SPECIAL_ENERGY, EnergyCard, PokemonCard
from common.cards.functions.energy import provision_units

from .activation import (DAMAGE_UNIT_HP, ActivationCompiler, ActivationEnvironment,
                         FeatureActivation)
from .capabilities import (best_current_damage, body_capability, card_option_units,
                           card_option_value, clause_value_units, hidden_zone_expectation,
                           expected_draw_counts, recoverable_discard_ids,
                           FUTURE_TURN_DISCOUNT)
from .coverage import card_coverage_gap
from .features import FEATURE_CATALOG
from .prizes import PrizeMap, derive_prize_map
from .portfolio import feasible_option_portfolio_result
from .worth import (Demand, DemandState, EvaluationModel, Reach, _liveness, _unfilled,
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


@dataclass(frozen=True)
class EvaluationSnapshot:
    valuation_key: str
    model_identity: str
    groups: tuple[tuple[str, Valuation], ...]
    valuation: Valuation
    opponent: object | None
    reused_groups: tuple[str, ...] = ()


DRAW_RESULT_CODE = 2


class _Trace:
    def __init__(self, ctx: EvaluationModel):
        self.ctx = ctx
        self.compiler = ActivationCompiler()
        self.provenance: dict[str, set[str]] = {}
        self.by_owner: dict[tuple[str, tuple[str, ...]], list[float]] = {}
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
        owner_tokens = (*item.provenance,)
        if provenance:
            owner_tokens = (*owner_tokens, provenance)
        owner = tuple(sorted(set(owner_tokens)))
        if not owner:
            owner = (part,)
        self.provenance.setdefault(feature, set()).update(owner)
        key = (feature, owner)
        self.by_owner.setdefault(key, []).append(activation)
        self.by_part[part] = self.by_part.get(part, 0.0) + (
            activation * self.ctx.configuration[feature])

    def finish(self) -> Valuation:
        contributions = tuple(FeatureContribution(
            feature, activation, self.ctx.configuration[feature],
            activation * self.ctx.configuration[feature], owner)
            for (feature, owner), values in sorted(self.by_owner.items())
            if (activation := math.fsum(values)))
        owner_values = {}
        for item in contributions:
            owner_values.setdefault(item.feature, []).append(item.activation)
        activations = tuple(FeatureActivation(
            feature, math.fsum(values), tuple(sorted(self.provenance[feature])))
            for feature, values in sorted(owner_values.items())
            if math.fsum(values))
        total = sum(item.value for item in contributions)
        return Valuation(total, tuple(sorted(self.by_part.items())), tuple(self.gaps),
                         activations, contributions)


EVALUATION_GROUPS = ("context", "me", "them", "public")
OPPONENT_BELIEF_PATH = ("knowledge", "opponent_belief")
PRIZE_PHASE_PIVOT = 4
ROUTE_STORED_ENERGY_VALUE = 0.5


def evaluate(board: ObservationState, ctx: EvaluationModel) -> Valuation:
    return evaluate_snapshot(board, ctx).valuation


def evaluate_snapshot(board: ObservationState, ctx: EvaluationModel, *,
                      parent: EvaluationSnapshot | None = None,
                      delta=None) -> EvaluationSnapshot:
    reusable = (parent is not None and delta is not None
                and parent.model_identity == ctx.identity)
    dirty = set(EVALUATION_GROUPS if not reusable else _dirty_groups(delta))
    previous = {} if not reusable else dict(parent.groups)
    belief_dirty = not reusable or any(
        tuple(path) == OPPONENT_BELIEF_PATH
        for path in getattr(delta, "parts", ()))
    opponent = (opponent_evaluation(board, ctx) if belief_dirty else parent.opponent)
    groups = []
    reused = []
    prize_map = None
    for name in EVALUATION_GROUPS:
        if name not in dirty and name in previous:
            valuation = previous[name]
            reused.append(name)
        elif name == "context":
            valuation = _context_group(board, ctx, opponent)
        elif name == "me":
            valuation = _side_group("me", board.me, 1.0, board, ctx, opponent)
        elif name == "them":
            valuation = _side_group("them", board.them, -1.0, board, ctx, opponent)
        else:
            valuation, prize_map = _public_group(board, ctx)
        groups.append((name, valuation))
    if prize_map is None:
        prize_map = parent.valuation.prize_map if reusable else derive_prize_map(board, ctx)
    valuation = _combine_groups(tuple(groups), ctx, prize_map)
    return EvaluationSnapshot(
        board.valuation_key, ctx.identity, tuple(groups), valuation, opponent, tuple(reused))


def _dirty_groups(delta) -> frozenset[str]:
    dirty = set()
    for path in getattr(delta, "parts", ()):
        root = path[0] if path else ""
        if root in {"select", "looking"}:
            continue
        if root == "knowledge" and path[1:] == ("attack_locks",):
            continue
        if root == "knowledge" and path[1:] == ("deck_top",):
            dirty.add("public")
            continue
        if root in {"me", "them"}:
            dirty.update(("me", "them", "public"))
        elif root == "knowledge":
            dirty.update(EVALUATION_GROUPS)
        elif root in {"turn", "stadium", "events", "logs", "legal_actions"}:
            dirty.update(EVALUATION_GROUPS)
        else:
            dirty.update(EVALUATION_GROUPS)
    return frozenset(dirty)


def _context_group(board, ctx, opponent) -> Valuation:
    trace = _Trace(ctx)
    if opponent is not None:
        trace.gaps.extend(opponent.failures)
    _opponent_traits(trace, ctx, board, opponent)
    result = board.turn.result
    if isinstance(result, int) and not isinstance(result, bool) \
            and result >= 0 and result != DRAW_RESULT_CODE:
        trace.emit("result", "observation", ("terminal_win",),
                   1.0 if result == board.seat else -1.0)
    return trace.finish()


def _side_group(label, side, sign, board, ctx, opponent) -> Valuation:
    trace = _Trace(ctx)
    _side(trace, label, side, sign, ctx, board, opponent,
          deck_counts=board.deck_counts if sign > 0 else None)
    return trace.finish()


def _sequenced_portfolio(values) -> float:
    ordered = sorted((float(value) for value in values if value > 0), reverse=True)
    return sum(value * FUTURE_TURN_DISCOUNT ** index
               for index, value in enumerate(ordered))


@dataclass(frozen=True)
class _DevelopmentOpportunity:
    attack: float
    ability: float
    evolution: int | None
    typed_energy: tuple[tuple[int, int], ...]
    energy_units: int
    ability_claims: tuple[str, ...]
    bench_units: int = 0


def _development_attack_claim(body, reach, ctx):
    from .worth import _forward_lines

    facts = ctx.facts(body.card.card_id)
    candidates = []
    cards = [(None, facts)]
    cards.extend((card_id, ctx.facts(card_id))
                 for card_id in _forward_lines().get(getattr(facts, "name", None), ())
                 if (reach or {}).get(card_id, Reach.ABSENT) is not Reach.ABSENT)
    attached = Counter(body.energies)
    for target, candidate in cards:
        for attack in getattr(candidate, "attacks", ()) or ():
            typed, colorless = _unfilled(attack.cost, attached)
            missing = sum(typed.values()) + colorless
            impact = max(int(attack.damage or 0), int(attack.damage_fix or 0),
                         int(attack.damage_max or 0))
            candidates.append((impact, -missing, target, tuple(sorted(typed.items())), missing))
    if not candidates:
        return None, (), 0, 0.0
    def candidate_rank(row):
        impact, missing_rank, target, _typed, _missing = row
        return impact, missing_rank, -1 if target is None else target

    _impact, _missing_rank, target, typed, missing = max(
        candidates, key=candidate_rank)
    return target, typed, missing, _impact / DAMAGE_UNIT_HP


def _development_ability_claims(facts) -> tuple[str, ...]:
    claims = set()
    for clause in card_clauses(facts):
        if clause.trigger != "ability" and clause.kind not in {
                "draw", "fetch", "accel", "energy_recur", "move_damage", "heal"}:
            continue
        allowance = getattr(clause, "allowance", None)
        if allowance == "card":
            claims.add(f"ability:card:{getattr(facts, 'name', '')}")
    return tuple(sorted(claims))


def _development_energy_capacities(side, deck_counts, ctx):
    typed = Counter()
    total = 0
    counts = Counter(card.card_id for card in tuple(side.hand))
    counts.update({card_id: count for card_id, count in deck_counts or ()})
    for card_id, count in counts.items():
        facts = ctx.facts(card_id)
        if not isinstance(facts, EnergyCard):
            continue
        units = int(provision_units(facts)) * max(0, count)
        typed[facts.provides] += units
        total += units
    return typed, total


def _projected_evolution_capability(body, target, side, opposing_side, board, ctx):
    facts = ctx.facts(target)
    if not isinstance(facts, PokemonCard):
        return None
    damage = max(0, body.max_hp - body.hp)
    evolved = replace(
        body, card=replace(body.card, card_id=target),
        hp=max(0, int(facts.hp) - damage), max_hp=int(facts.hp),
        appeared_this_turn=False,
        pre_evolution=(*body.pre_evolution, body.card))
    projected_side = replace(
        side,
        active=evolved if side.active is body else side.active,
        bench=tuple(evolved if candidate is body else candidate
                    for candidate in side.bench))
    projected_board = replace(
        board,
        me=projected_side if side is board.me else board.me,
        them=projected_side if side is board.them else board.them)
    return body_capability(
        evolved, projected_side, opposing_side, projected_board, ctx, reach={})


def _basic_hand_development_opportunities(side, opposing_side, board, ctx):
    opportunities = []
    for card in tuple(side.hand):
        facts = ctx.facts(card.card_id)
        if not isinstance(facts, PokemonCard) or facts.evolves_from is not None:
            continue
        attacks = []
        for attack in facts.attacks:
            typed, colorless = _unfilled(attack.cost, Counter())
            missing = sum(typed.values()) + colorless
            impact = max(int(attack.damage or 0), int(attack.damage_fix or 0),
                         int(attack.damage_max or 0)) / DAMAGE_UNIT_HP
            attacks.append((impact, -missing, tuple(sorted(typed.items())), missing))
        attack, _rank, typed, missing = max(
            attacks, default=(0.0, 0, (), 0), key=lambda row: (row[0], row[1]))
        body = Body(card, int(facts.hp), int(facts.hp), False, (), (), (), (), b"")
        projected_side = replace(side, bench=(*side.bench, body))
        projected_board = replace(
            board,
            me=projected_side if side is board.me else board.me,
            them=projected_side if side is board.them else board.them)
        capability = body_capability(
            body, projected_side, opposing_side, projected_board, ctx, reach={})
        ability = max(0.0, sum((
            capability.draw_cards, capability.search_cards,
            capability.damage_move, capability.healing,
            capability.acceleration, capability.denial,
            capability.ability_future)) - capability.resource_cost - capability.self_cost)
        if attack > 0 or ability > 0:
            opportunities.append(_DevelopmentOpportunity(
                attack, ability, None, typed, missing,
                _development_ability_claims(facts), bench_units=1))
    return opportunities


def _feasible_development_portfolio(rows, side, deck_counts, ctx, *,
                                    board=None, opposing_side=None):
    hand_counts = Counter(card.card_id for card in tuple(side.hand))
    deck_supply = dict(deck_counts or ())
    opportunities = []
    evolution_capacities = {}
    acceleration = 0
    for body, capability, reach in rows:
        attack = max(capability.attack_future,
                     capability.attack_now if body is not side.active else 0.0)
        ability = max(0.0, capability.ability_future)
        acceleration += max(0, int(capability.acceleration))
        target, typed, missing, full_attack = _development_attack_claim(body, reach, ctx)
        if target is not None and board is not None and opposing_side is not None:
            projected = _projected_evolution_capability(
                body, target, side, opposing_side, board, ctx)
            if projected is not None:
                ability = max(ability, sum((
                    projected.draw_cards, projected.search_cards,
                    projected.damage_move, projected.healing,
                    projected.acceleration, projected.denial,
                    projected.ability_future))
                    - projected.resource_cost - projected.self_cost)
        if not body.energies:
            attack = max(attack, full_attack)
        if attack <= 0 and ability <= 0:
            continue
        if target is not None:
            status = (reach or {}).get(target, Reach.ABSENT)
            evolution_capacities[target] = (
                hand_counts[target] if status is Reach.HAND else
                hand_counts[target] + deck_supply.get(target, 0))
        target_facts = ctx.facts(target) if target is not None else ctx.facts(
            body.card.card_id)
        opportunities.append(_DevelopmentOpportunity(
            attack, ability, target,
            (() if body.energies else typed),
            (0 if body.energies else missing),
            _development_ability_claims(target_facts)))
    if board is not None and opposing_side is not None:
        opportunities.extend(_basic_hand_development_opportunities(
            side, opposing_side, board, ctx))
    if not opportunities:
        return 0.0, 0.0

    energy_capacities, total_energy = _development_energy_capacities(
        side, deck_counts, ctx)
    energy_types = tuple(sorted(energy_capacities))
    evolution_ids = tuple(sorted(evolution_capacities))
    ability_keys = tuple(sorted({claim for item in opportunities
                                 for claim in item.ability_claims}))
    initial_resources = ((0,) * len(evolution_ids), (0,) * len(energy_types),
                         0, 0, 0, (0,) * len(ability_keys), 0)
    states = {(0, initial_resources): (0.0, 0.0)}
    development_horizon = len(side.bodies) + max(
        0, side.bench_max - len(side.bench))
    attack_weight = ctx.configuration["combat.attack_future"]
    ability_weight = ctx.configuration["ability.future"]
    for _step in range(len(opportunities)):
        expanded = dict(states)
        for (mask, resources), totals in states.items():
            (evolution_used, typed_used, total_used, bench_used,
             accel_used, ability_used, elapsed) = resources
            for index, opportunity in enumerate(opportunities):
                if mask & (1 << index):
                    continue
                variants = [(opportunity.attack, opportunity.ability,
                             opportunity.typed_energy, opportunity.energy_units)]
                if opportunity.ability > 0 and opportunity.energy_units:
                    variants.append((0.0, opportunity.ability, (), 0))
                for attack, ability, typed_energy, energy_units in variants:
                    next_evolution = list(evolution_used)
                    if opportunity.evolution is not None:
                        position = evolution_ids.index(opportunity.evolution)
                        next_evolution[position] += 1
                        if next_evolution[position] > evolution_capacities[
                                opportunity.evolution]:
                            continue
                    next_typed = list(typed_used)
                    feasible = True
                    for energy_type, amount in typed_energy:
                        if energy_type not in energy_types:
                            feasible = False
                            break
                        position = energy_types.index(energy_type)
                        next_typed[position] += amount
                        if next_typed[position] > energy_capacities[energy_type]:
                            feasible = False
                            break
                    if not feasible or total_used + energy_units > total_energy:
                        continue
                    next_bench = bench_used + opportunity.bench_units
                    if next_bench > max(0, side.bench_max - len(side.bench)):
                        continue
                    next_ability = list(ability_used)
                    for claim in opportunity.ability_claims:
                        position = ability_keys.index(claim)
                        next_ability[position] += 1
                        if next_ability[position] > 1:
                            feasible = False
                            break
                    if not feasible:
                        continue
                    remaining_acceleration = max(0, acceleration - accel_used)
                    for accelerated in range(min(energy_units,
                                                 remaining_acceleration) + 1):
                        turns = max(int(opportunity.evolution is not None),
                                    opportunity.bench_units,
                                    energy_units - accelerated,
                                    int(bool(attack or ability)))
                        next_elapsed = elapsed + turns
                        if next_elapsed > development_horizon:
                            continue
                        discount = FUTURE_TURN_DISCOUNT ** max(0, next_elapsed - 1)
                        candidate = (totals[0] + attack * discount,
                                     totals[1] + ability * discount)
                        next_resources = (tuple(next_evolution), tuple(next_typed),
                                          total_used + energy_units, next_bench,
                                          accel_used + accelerated, tuple(next_ability),
                                          next_elapsed)
                        key = (mask | (1 << index), next_resources)
                        incumbent = expanded.get(key)
                        worth = candidate[0] * attack_weight + candidate[1] * ability_weight
                        if incumbent is None or worth > (
                                incumbent[0] * attack_weight
                                + incumbent[1] * ability_weight):
                            expanded[key] = candidate
        states = expanded
    return max(states.values(), key=lambda totals: (
        totals[0] * attack_weight + totals[1] * ability_weight, totals))


def _emit_option(trace, part, units, scale, *, provenance=None,
                 provenance_features=()) -> None:
    for feature, value in units.activations():
        trace.emit(part, "option", (feature,), scale * value,
                   provenance=(provenance if feature in provenance_features else None))


def _situational_worth(facts, side, opponent, demand, ctx, deck_counts, board):
    trace = _Trace(ctx)
    _situational_functions(
        trace, "portfolio", facts, side, opponent, demand, ctx, deck_counts,
        board, sign=1.0)
    return trace.finish().total


def _slot_option(open_slots) -> float:
    return float(open_slots)


def _public_group(board, ctx) -> tuple[Valuation, PrizeMap]:
    trace = _Trace(ctx)
    trace.emit("prize_race", "observation", ("prize_advantage",),
               board.them.prize_count - board.me.prize_count)
    prize_map = derive_prize_map(board, ctx)
    trace.emit("prize_map", "observation", ("prize_advantage",), prize_map.overrun)
    for card in board.stadium:
        facts = ctx.facts(card.card_id)
        sign = 1.0 if card.owner is None or card.owner == board.seat else -1.0
        side, opposing = ((board.me, board.them) if sign > 0
                          else (board.them, board.me))
        _emit_option(trace, "stadium", card_option_units(
            facts, side, opposing, board, ctx), sign)
        _situational_functions(
            trace, "stadium", facts, side, opposing,
            Demand.read(side, ctx, board.turn), ctx,
            board.deck_counts if sign > 0 else None, board, sign=sign)
    if isinstance(board.knowledge.own_prizes, KnownOwnPrizes):
        for card_id, count in board.knowledge.own_prizes.cards:
            _emit_option(trace, "me.prizes", card_option_units(
                ctx.facts(card_id), board.me, board.them, board, ctx), -count)
    if isinstance(board.knowledge.known_top, KnownDeckTop):
        for depth, row in enumerate(board.knowledge.known_top.cards):
            card_id = row[1]
            units = card_option_units(
                ctx.facts(card_id), board.me, board.them, board, ctx)
            _emit_option(trace, "me.deck_top", units, 1.0)
            for feature, value in units.activations():
                depth_feature = f"option.depth.{feature.removeprefix('option.')}"
                trace.emit("me.deck_top", "option_depth", (depth_feature,),
                           depth * value)
    return trace.finish(), prize_map


def _combine_groups(groups, ctx, prize_map) -> Valuation:
    provenance = {}
    owned = {}
    parts = {}
    gaps = []
    for _name, valuation in groups:
        gaps.extend(valuation.gaps)
        for label, value in valuation.parts:
            parts[label] = parts.get(label, 0.0) + value
        for item in valuation.activations:
            provenance.setdefault(item.feature, set()).update(item.provenance)
        for item in valuation.contributions:
            key = (item.feature, item.provenance)
            owned.setdefault(key, []).append(item.activation)
    contributions = tuple(FeatureContribution(
        feature, activation, ctx.configuration[feature],
        activation * ctx.configuration[feature], owner)
        for (feature, owner), values in sorted(owned.items())
        if (activation := math.fsum(values)))
    compiled_values = {}
    for item in contributions:
        compiled_values.setdefault(item.feature, []).append(item.activation)
    compiled = tuple(FeatureActivation(
        feature, math.fsum(values), tuple(sorted(provenance[feature])))
        for feature, values in sorted(compiled_values.items()) if math.fsum(values))
    return Valuation(sum(item.value for item in contributions), tuple(sorted(parts.items())),
                     tuple(gaps), compiled, contributions, prize_map)


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
    opposing_side = board.them if sign > 0 else board.me
    doomed = _active_doomed(
        board.them if sign > 0 else board.me, side, ctx, board)
    if side.active_hidden:
        trace.emit(f"{label}.active", "observation", ("unknown_card_belief",), -1.0)
    demand = Demand.read(side, ctx, board.turn)
    reach = (line_reach(
        demand.hand_name_counts, deck_counts, ctx, hand=demand.hand, turn=board.turn)
        if sign > 0 else opponent_line_reach(ctx, opponent))
    seen: dict[int, int] = {}
    body_reaches = {}
    capabilities = []
    for body in side.bodies:
        body_reach = legal_line_reach(body, reach, ctx, demand.hand, board.turn)
        body_reaches[body.card.serial] = body_reach
        capability = body_capability(
            body, side, opposing_side, board, ctx,
            reach=body_reach)
        capabilities.append((body, capability))
        _body(trace, f"{label}.bodies", body, sign, ctx, own=sign > 0,
              active=body is side.active, doomed=doomed and body is side.active,
              terminal=(doomed and body is side.active
                        and _prize_value(body, ctx) >= opposing_side.prize_count),
              reach=body_reach, opponent=opponent, side=side,
              opposing_side=opposing_side, board=board,
              capability=capability, demand=demand)
        copies = seen.get(body.card.card_id, 0)
        if copies:
            trace.emit(f"{label}.bodies", "observation", ("surplus_in_play_copy",),
                       sign * copies)
        seen[body.card.card_id] = copies + 1

    active_capability = next((value for body, value in capabilities
                              if body is side.active), None)
    trace.emit(f"{label}.combat", "observation", ("attack_now",),
               sign * (0.0 if active_capability is None
                       else active_capability.attack_now))
    trace.emit(f"{label}.combat", "observation", ("bench_reach",),
               sign * (0.0 if active_capability is None
                       else active_capability.bench_reach))
    trace.emit(f"{label}.combat", "observation", ("active_threat",),
               sign * (0.0 if active_capability is None
                       else active_capability.attack_potential))
    trace.emit(f"{label}.combat", "observation", ("attack_progress",), sign * _sequenced_portfolio(
        value.attack_progress for _body_node, value in capabilities))
    future_attack, future_ability = _feasible_development_portfolio((
        (body, value, body_reaches.get(body.card.serial))
        for body, value in capabilities), side, deck_counts, ctx,
        board=board, opposing_side=opposing_side)
    trace.emit(f"{label}.combat", "observation", ("attack_future",),
               sign * future_attack)
    trace.emit(f"{label}.abilities", "observation", ("ability_future",),
               sign * future_ability)
    trace.emit(f"{label}.combat", "observation", ("line_potential",), sign * _sequenced_portfolio(
        value.line_potential for _body_node, value in capabilities))
    trace.emit(f"{label}.combat", "observation", ("prize_phase_fit",), sign * _sequenced_portfolio(
        _prize_phase_fit(body, value, opposing_side.prize_count, ctx)
        for body, value in capabilities))

    if side.active is not None and (side.active.max_hp <= 0 or side.active.hp > 0):
        trace.emit(f"{label}.active", "observation", ("active_body",), sign)
        active_facts = ctx.facts(side.active.card.card_id)
        if not any_attack_payable(active_facts, side.active.energies):
            trace.emit(f"{label}.active", "observation", ("unready_active",), -sign)
        retreat_cost = int(getattr(active_facts, "retreat_cost", 0) or 0)
        if side.bench and retreat_cost and len(side.active.energies) >= retreat_cost:
            trace.emit(f"{label}.active", "observation", ("retreat_ready_active",), sign)
        trace.emit(f"{label}.active", "observation", ("active_damage_pressure",),
                   sign * _damage_pressure(active_facts) / DAMAGE_UNIT_HP)
    trace.emit(f"{label}.bench_slots", "observation", ("open_bench_slot",),
               sign * _slot_option(max(0, side.bench_max - len(side.bench))))
    trace.emit(f"{label}.bench_slots", "observation", ("developed_bench_body",),
               sign * len(side.bench))
    trace.emit(f"{label}.bench_slots", "observation", ("full_bench",),
               sign * float(len(side.bench) >= side.bench_max))
    trace.emit(f"{label}.liability", "observation", ("extra_prize_liability",),
               -sign * sum(max(0, _prize_value(body, ctx) - 1)
                           for body in side.bodies
                           if body.max_hp <= 0 or body.hp > 0))

    option_cache = {}

    def option_units(facts):
        card_id = getattr(facts, "card_id", None)
        if card_id not in option_cache:
            option_cache[card_id] = card_option_units(
                facts, side, opposing_side, board, ctx, reaches=body_reaches)
        return option_cache[card_id]

    def option_value(facts):
        return option_units(facts).total

    if sign > 0 and side.hand is not None:
        copies = Counter(demand.body_id_counts)
        basic_energy = Counter()
        portfolio_entries = []
        portfolio_functions = []
        portfolio_sources = []
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
            trace.emit(f"{label}.hand", "observation", (claim,), sign)
            if claim != "dead_hand_card":
                portfolio_entries.append((
                    facts, option_units(facts),
                    _situational_worth(
                        facts, side, board.them, demand, ctx, deck_counts, board)))
                portfolio_functions.append(facts)
                portfolio_sources.append(card)
            if (isinstance(facts, EnergyCard) and facts.kind != SPECIAL_ENERGY
                    and basic_energy[facts.provides]):
                trace.emit(f"{label}.hand", "observation", ("surplus_basic_energy",), sign)
            if (getattr(facts, "synergy", ())
                    and any(demand.body_name_counts.get(name, 0) for name in facts.synergy)):
                trace.emit(f"{label}.hand", "observation", ("synergy_in_hand",), sign)
            if (isinstance(facts, PokemonCard) and facts.evolves_from
                    and (demand.body_name_counts.get(facts.evolves_from, 0)
                         or demand.hand_name_counts.get(facts.evolves_from, 0))):
                trace.emit(f"{label}.hand", "observation",
                           ("evolution_access",), sign)
            copies[card.card_id] += 1
            if isinstance(facts, EnergyCard) and facts.kind != SPECIAL_ENERGY:
                basic_energy[facts.provides] += 1
        portfolio = feasible_option_portfolio_result(
            portfolio_entries, side, board, ctx, hand_size=len(side.hand))
        for index, units in portfolio.selected_units:
            source = portfolio_sources[index]
            provenance = (f"feasible_option_portfolio:serial:{source.serial}"
                          if source.serial is not None else
                          f"feasible_option_portfolio:card:{source.card_id}")
            _emit_option(
                trace, f"{label}.hand", units, sign, provenance=provenance,
                provenance_features=tuple(
                    feature for feature, _value in units.activations()))
            _situational_functions(
                trace, f"{label}.hand", portfolio_functions[index], side, board.them,
                demand, ctx, deck_counts, board, sign=sign, provenance=provenance)
    else:
        trace.emit(f"{label}.hand", "observation", ("unknown_opponent_hand_card",),
                   sign * side.hand_count)
        trace.emit(f"{label}.hand", "observation", ("card_in_hand",),
                   sign * side.hand_count)
        trace.emit(f"{label}.hand", "observation", ("opponent_hidden_option_value",),
                   sign * hidden_zone_expectation(
                       side.hand_count, side, board.me, board, ctx, opponent,
                       option_value=option_value))

    if sign > 0 and deck_counts is not None:
        deck_options = {key: 0.0 for key, _value in card_option_units(
            None, side, opposing_side, board, ctx).activations()}
        deck_cards = 0
        for card_id, count in deck_counts:
            facts = ctx.facts(card_id)
            _card(trace, f"{label}.deck", card_id, facts, sign * count, ctx, own=True,
                  placement="in_deck", opponent=opponent)
            trace.emit(f"{label}.deck", "observation", ("card_in_deck",),
                       sign * count)
            for key, value in option_units(facts).activations():
                deck_options[key] += count * value
            deck_cards += count
        for key, value in deck_options.items():
            trace.emit(f"{label}.deck", "option", (key,),
                       sign * value / max(1, deck_cards))
    else:
        unknown = ("unknown_own_deck_card" if sign > 0
                   else "unknown_opponent_deck_card")
        trace.emit(f"{label}.deck", "observation", (unknown,), sign * side.deck_count)
        trace.emit(f"{label}.deck", "observation", ("card_in_deck",),
                   sign * side.deck_count)
        if sign < 0:
            trace.emit(f"{label}.deck", "observation",
                       ("opponent_hidden_deck_value",),
                       sign * hidden_zone_expectation(
                           side.deck_count, side, board.me, board, ctx, opponent,
                           option_value=option_value))

    recoverable = recoverable_discard_ids(side, ctx)
    for card in side.discard:
        _card(trace, f"{label}.discard", card.card_id, ctx.facts(card.card_id), sign, ctx,
              own=sign > 0, placement="in_discard", opponent=opponent)
        trace.emit(f"{label}.discard", "observation", ("card_in_discard",), sign)
        if card.card_id in recoverable:
            trace.emit(f"{label}.discard", "observation",
                       ("recoverable_discard_card",), sign)

    for status in ("asleep", "paralyzed", "confused", "poisoned", "burned"):
        trace.emit(f"{label}.status", "observation", (f"{status}_status",),
                   -sign * float(getattr(side, status, 0) or 0))


def _body(trace: _Trace, part: str, body: Body, sign: float, ctx: EvaluationModel, *,
          own: bool, active: bool, doomed: bool, terminal: bool, reach, opponent, side: Side,
          opposing_side: Side, board: ObservationState, capability, demand: Demand) -> None:
    body_facts = ctx.facts(body.card.card_id)
    if body_facts is not None and not isinstance(body_facts, PokemonCard):
        trace.emit(part, "observation", ("uncovered_card",), abs(sign))
        trace.emit(part, "observation", ("card_in_play",), sign)
        trace.emit(part, "observation", ("body_hp_units",),
                   sign * body.max_hp / DAMAGE_UNIT_HP)
        trace.gaps.append(f"{part}: non-Pokemon body {body.card.card_id}")
        return
    if body.max_hp > 0 and body.hp <= 0:
        trace.emit(part, "observation", ("body_damage_fraction",), -sign)
        trace.emit(part, "observation", ("realized_knockout",),
                   -sign * _prize_value(body, ctx))
        return
    _card(trace, part, body.card.card_id, body_facts, sign, ctx, own=own,
          placement="in_play", opponent=opponent)
    trace.emit(part, "observation", ("card_in_play",), sign)
    trace.emit(part, "observation", ("body_hp_units",),
               sign * body.max_hp / DAMAGE_UNIT_HP)
    if body_facts is not None and body_facts.evolves_from:
        trace.emit(part, "observation", ("evolution_access",), sign)
    missing = 0.0
    if body.max_hp > 0:
        missing = max(0.0, min(1.0, (body.max_hp - max(0, body.hp)) / body.max_hp))
        trace.emit(part, "observation", ("body_damage_fraction",), -sign * missing)
    if doomed:
        trace.emit(part, "observation", ("doomed_active",), -sign)
    if terminal:
        trace.emit(part, "observation", ("terminal_active_liability",), -sign)

    for claim, value in (
            ("ability_draw_cards", capability.draw_cards),
            ("ability_search_cards", capability.search_cards),
            ("ability_damage_move", capability.damage_move),
            ("ability_healing", capability.healing),
            ("ability_acceleration", capability.acceleration),
            ("ability_denial", capability.denial),
            ("ability_resource_cost", capability.resource_cost),
            ("ability_self_cost", capability.self_cost),
            ("retreat_progress", capability.retreat_progress)):
        trace.emit(part, "observation", (claim,), sign * value)
    _situational_functions(
        trace, part, body_facts, side, opposing_side, demand, ctx,
        board.deck_counts if own else None, board, sign=sign, body=body)
    trace.gaps.extend(f"{part}: {gap}" for gap in capability.gaps)

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
        rental = "discard_eot" in riders
        energy_rows.append((card, facts, rental))
    priced_energy_cards = [card for card, _facts, rental in energy_rows if not rental]
    interaction_amount = (sign * min(1.0, usable / len(priced_energy_cards))
                          if priced_energy_cards else 0.0)
    for card, facts, rental in energy_rows:
        if rental:
            rentals += 1
            continue
        _card(trace, part, card.card_id, facts, sign, ctx, own=own,
              placement="attached_usable", interaction_amount=interaction_amount,
              opponent=opponent)
        _situational_functions(
            trace, part, facts, side, opposing_side, demand, ctx,
            board.deck_counts if own else None, board, sign=sign, body=body)
    if body.energies and not body.energy_cards:
        trace.emit(part, "card", ("kind:energy",), sign * len(body.energies))
    rental_units = sum(provision_units(
        facts, evolved=bool(getattr(body_facts, "evolves_from", None)))
                       for _card, facts, rental in energy_rows if rental)
    usable = max(0, usable - rental_units)
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
        _situational_functions(
            trace, part, ctx.facts(card.card_id), side, opposing_side, demand, ctx,
            board.deck_counts if own else None, board, sign=sign, body=body)
        trace.emit(part, "observation", ("attached_tool",), sign)
    for card in body.pre_evolution:
        _card(trace, part, card.card_id, ctx.facts(card.card_id), sign, ctx, own=own,
              placement="under_body", opponent=opponent)
        trace.emit(part, "observation", ("card_under_body",), sign)


def _card(trace: _Trace, part: str, card_id: int, facts, amount: float,
          ctx: EvaluationModel, *, own: bool, placement: str,
          interaction_amount: float | None = None, opponent=None) -> None:
    situated = amount if interaction_amount is None else interaction_amount
    coverage_gap = card_coverage_gap(card_id, facts)
    if facts is None:
        trace.emit(part, "observation", ("uncovered_card",), abs(amount))
        trace.gaps.append(f"{part}: {coverage_gap}")
        return
    if coverage_gap is not None:
        trace.emit(part, "observation", ("uncovered_card",), abs(amount))
        trace.gaps.append(f"{part}: {coverage_gap}")
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
                           demand: Demand, ctx: EvaluationModel, deck_counts,
                           board: ObservationState, *, sign: float, body=None,
                           provenance: str | None = None) -> None:
    clauses = card_clauses(facts)
    compiler = ActivationCompiler()
    for clause in clauses:
        units = clause_value_units(
            clause, facts, side, opponent, board, ctx, body=body)
        environment = ActivationEnvironment(
            scale=sign * units, board=board, evaluation_model=ctx, side=side,
            opponent=opponent, demand=demand, facts=facts,
            deck_counts=deck_counts, clause=clause, body=body)
        for activation in compiler.compile("function", (clause.kind,), environment):
            trace.record(part, activation, provenance=provenance)
        for parameter, value in clause.params.items():
            parameter_environment = ActivationEnvironment(
                scale=sign, board=board, evaluation_model=ctx, side=side,
                opponent=opponent, demand=demand, facts=facts,
                deck_counts=deck_counts, claim_value=value, clause=clause, body=body)
            for activation in compiler.compile(
                    "clause_parameter", (parameter,), parameter_environment):
                trace.record(part, activation, provenance=provenance)
        if clause.kind == "draw":
            _mine, theirs = expected_draw_counts(
                clause, side, opponent, ctx,
                cards_leaving_hand=int(not isinstance(facts, PokemonCard)))
            opponent_draw = ActivationEnvironment(
                scale=sign * theirs, board=board, evaluation_model=ctx,
                side=side, opponent=opponent, facts=facts, clause=clause, body=body)
            for activation in compiler.compile(
                    "draw_effect", ("opponent_cards",), opponent_draw):
                trace.record(part, activation, provenance=provenance)
        if clause.rider == "shuffle_both_hands":
            rider = ActivationEnvironment(
                scale=sign, board=board, evaluation_model=ctx, side=side,
                opponent=opponent, demand=demand, facts=facts,
                deck_counts=deck_counts, clause=clause, body=body)
            for activation in compiler.compile(
                    "function", ("opp_hand_to_deck",), rider):
                trace.record(part, activation, provenance=provenance)


def _active_doomed(attacker: Side, defender: Side, ctx: EvaluationModel,
                   board: ObservationState | None = None) -> bool:
    if attacker.active is None or defender.active is None:
        return False
    if defender.active.hp <= 0:
        return True
    damage = (best_payable_damage(ctx.facts(attacker.active.card.card_id),
                                  attacker.active.energies,
                                  ctx.facts(defender.active.card.card_id))
              if board is None else
              best_current_damage(attacker.active, attacker, defender, board, ctx))
    return 0 < defender.active.hp <= damage


def _prize_phase_fit(body, capability, opposing_prizes, ctx) -> float:
    facts = ctx.facts(body.card.card_id)
    if facts is None:
        return 0.0
    from .worth import _forward_lines

    line = (facts, *(ctx.facts(card_id)
                     for card_id in _forward_lines().get(facts.name, ())))
    route_prizes = max((int(getattr(card, "prize_value", 1) or 1)
                        for card in line if card is not None), default=1)
    if (route_prizes > 1) != (int(opposing_prizes) <= PRIZE_PHASE_PIVOT):
        return 0.0
    readiness = (capability.attack_now + capability.attack_progress
                 + capability.attack_future)
    return readiness + len(body.energies) * ROUTE_STORED_ENERGY_VALUE


def _damage_pressure(facts) -> int:
    return max((max((int(attack.damage or 0), *(int(clause.amount or 0)
                       for clause in attack.clauses if clause.kind == "bench_snipe")))
                for attack in getattr(facts, "attacks", ()) or ()), default=0)


def _prize_value(body: Body, ctx: EvaluationModel) -> int:
    return getattr(ctx.facts(body.card.card_id), "prize_value", 1)


__all__ = ("EvaluationSnapshot", "FeatureActivation", "FeatureContribution", "Valuation",
           "evaluate", "evaluate_snapshot")
