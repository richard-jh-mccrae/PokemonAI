"""Price one option: the engine plays it, ObservationState digests the reprint, the Ledger differences.

Every transition node the providers emit is priced here. A forced follow-up chain (Ultra Ball's
discard pick, then its fetch pick) is resolved inside the preview — each sub-menu chosen by the
same Ledger greedily, expected value at chance points — and the sub-choices are ADVISORY: the
real prompt re-decides on the real board when it arrives. A capped or unpriceable chain scores
the last board it could see and logs the gap; it never deletes the root option (the end-chain
lesson: a cap must not veto the action carrying the turn's value)."""
from __future__ import annotations

import math
import hashlib
from collections import Counter
from dataclasses import dataclass

from common.algebra import (Actor, Chance, Choice, Deterministic, Refresh, RevealChoice,
                            Terminal, Unknown)
from common.observation import ObservationState, ObservationStateBuilder
from common.strategy.context import _MAIN

from .chance import refresh_outcomes
from .evaluate import FeatureActivation, FeatureContribution, Valuation, evaluate
from .prizes import PrizeMap
from .worth import EvaluationModel

@dataclass(frozen=True)
class ContinuationFootprint:
    state_delta: float
    action_opportunity: float
    continues_turn: bool
    zones_created: tuple[str, ...] = ()
    zones_replaced: tuple[str, ...] = ()
    allowances_consumed: tuple[str, ...] = ()
    immediately_usable_outputs: tuple[str, ...] = ()
    opportunities_created: tuple[str, ...] = ()
    opportunities_preserved: tuple[str, ...] = ()
    opportunities_consumed: tuple[str, ...] = ()
    activations: tuple[FeatureActivation, ...] = ()
    contributions: tuple[FeatureContribution, ...] = ()


@dataclass(frozen=True)
class OptionPrice:
    action: object
    swing: float
    ends_turn: bool
    gaps: tuple[str, ...]
    footprint: ContinuationFootprint = ContinuationFootprint(0.0, 0.0, False)
    prize_map: PrizeMap | None = None


@dataclass(frozen=True)
class _RawFootprint:
    zones_created: tuple[str, ...] = ()
    zones_replaced: tuple[str, ...] = ()
    allowances_consumed: tuple[str, ...] = ()
    immediately_usable_outputs: tuple[str, ...] = ()
    opportunities_created: tuple[str, ...] = ()
    opportunities_preserved: tuple[str, ...] = ()
    opportunities_consumed: tuple[str, ...] = ()
    activations: tuple[tuple[str, float], ...] = ()


def price_actions(state, board: ObservationState, baseline: float, provider,
                  ctx: EvaluationModel) -> tuple[OptionPrice, ...]:
    prices = []
    baseline_valuation = evaluate(board, ctx)
    for action in provider.actions(state):
        if action.identity.kind == "end":
            # The one free action: ending the turn is the zero every other option must beat.
            prices.append(OptionPrice(
                action, 0.0, True, (), ContinuationFootprint(0.0, 0.0, False),
                baseline_valuation.prize_map))
            continue
        walk = _Walk(provider, ctx, board.decklist)
        node = provider.transition(state, action)
        successor, end_probability, landings = walk.node(
            state, board, node, ctx.compute.chain_depth_cap)
        ends_turn = end_probability >= 1.0
        state_delta = successor.total - baseline
        activation = -(1.0 - end_probability)
        opportunity_coefficient = ctx.configuration["action.opportunity_cost"]
        opportunity_cost = activation * opportunity_coefficient
        action_contribution = (() if not activation else (
            FeatureContribution("action.opportunity_cost", activation,
                                opportunity_coefficient, opportunity_cost,
                                ("continuation",)),))
        state_contributions = _state_contributions(baseline_valuation, successor, ctx)
        footprint_values = _root_footprint(
            board, provider, state, landings, walk.gaps)
        footprint_contributions = _footprint_contributions(footprint_values, ctx)
        opportunity_cost += sum(item.value for item in footprint_contributions)
        contributions = (*state_contributions, *action_contribution,
                         *footprint_contributions)
        activations = tuple(FeatureActivation(
            item.feature, item.activation, item.provenance) for item in contributions)
        footprint = ContinuationFootprint(
            state_delta, opportunity_cost, end_probability < 1.0,
            footprint_values.zones_created, footprint_values.zones_replaced,
            footprint_values.allowances_consumed,
            footprint_values.immediately_usable_outputs,
            footprint_values.opportunities_created,
            footprint_values.opportunities_preserved,
            footprint_values.opportunities_consumed, activations, contributions)
        swing = footprint.state_delta + footprint.action_opportunity
        if not math.isfinite(swing):
            # Belt behind configuration validation: a NaN/inf swing would make every price
            # unrankable. Score neutral, SAY SO — a visible gap, never a silent absorb.
            walk.gaps.append(f"non-finite price for {action.identity}; scored zero")
            swing = 0.0
        prices.append(OptionPrice(action, swing, ends_turn, tuple(walk.gaps), footprint,
                                  successor.prize_map))
    return tuple(prices)


class _Walk:
    """One root option's preview: a node budget, a gap log, and the recursion over nodes."""

    def __init__(self, provider, ctx: EvaluationModel, decklist):
        self.provider = provider
        self.ctx = ctx
        self.decklist = decklist
        self.gaps: list[str] = []
        self.nodes = 0

    def node(self, state, board: ObservationState, node, depth: int):
        self.nodes += 1
        if isinstance(node, Terminal):
            successor = self._typed(node.state, board)
            return evaluate(successor, self.ctx), 1.0, ((1.0, node.state, successor, True),)
        # The budget binds EVERY recursive node type, not just forced-menu walks: a wide or
        # nested chance tree must also land on the cap instead of running past it.
        if depth <= 0 or self.nodes >= self.ctx.compute.chain_node_cap:
            if isinstance(node, Deterministic):
                board = self._typed(node.state, board)
            self.gaps.append("chain capped; scored mid-effect board")
            landing_state = node.state if isinstance(node, Deterministic) else state
            return evaluate(board, self.ctx), 0.0, ((1.0, landing_state, board, False),)
        if isinstance(node, Deterministic):
            return self.deterministic(node.state, self._typed(node.state, board), depth)
        if isinstance(node, Chance):
            weighted, landings, end_probability = [], [], 0.0
            for edge in node.children:
                child_value, child_end_probability, child_landings = self.node(
                    state, board, edge.node, depth - 1)
                weighted.append((edge.probability, child_value))
                landings.extend((edge.probability * probability, landing_state,
                                 landing_board, ended)
                                for probability, landing_state, landing_board, ended
                                in child_landings)
                end_probability += edge.probability * child_end_probability
            return (_expected_valuation(weighted, self.ctx), end_probability,
                    tuple(landings))
        if isinstance(node, Refresh):
            valuation, gaps, outcomes = refresh_outcomes(
                _payload(state), board, node.card_id, node.draws, node.opponent_shuffles,
                lambda synthetic: evaluate(synthetic, self.ctx), self.ctx.compute)
            self.gaps.extend(gaps)
            landings = tuple((probability, _refresh_state(state, synthetic, index),
                              successor, False)
                             for index, (probability, successor, synthetic)
                             in enumerate(outcomes))
            return valuation, 0.0, landings
        if isinstance(node, RevealChoice):
            priced = {edge.label: self.node(state, board, edge.node, depth - 1)
                      for edge in node.choices}
            weighted, landings, end_probability = [], [], 0.0
            for outcome in node.outcomes:
                _label, (best_value, best_end_probability, best_landings) = self._choose(
                    ((label, priced[label]) for label in outcome.choices), node.actor,
                    salt=f"reveal:{depth}")
                weighted.append((outcome.probability, best_value))
                landings.extend((outcome.probability * probability, landing_state,
                                 landing_board, ended)
                                for probability, landing_state, landing_board, ended
                                in best_landings)
                end_probability += outcome.probability * best_end_probability
            return (_expected_valuation(weighted, self.ctx), end_probability,
                    tuple(landings))
        if isinstance(node, Choice):
            _label, result = self._choose(
                ((edge.label, self.node(state, board, edge.node, depth - 1))
                 for edge in node.children), node.actor, salt=f"choice:{depth}")
            return result
        if isinstance(node, Unknown):
            self.gaps.append(f"unpriceable: {node.reason} ({node.missing_fact})")
            return evaluate(board, self.ctx), 0.0, ((1.0, state, board, False),)
        self.gaps.append(f"unpriceable: undeclared node {type(node).__name__}")
        return evaluate(board, self.ctx), 0.0, ((1.0, state, board, False),)

    def deterministic(self, state, board: ObservationState, depth: int):
        context_value = None if board.select is None else board.select.context
        context = _MAIN if context_value is None else int(context_value)
        if context == _MAIN:
            return evaluate(board, self.ctx), 0.0, ((1.0, state, board, False),)
        actions = self.provider.actions(state)
        if not actions:
            self.gaps.append("forced menu offered no actions; scored mid-effect board")
            return evaluate(board, self.ctx), 0.0, ((1.0, state, board, False),)
        actor = self.provider.actor(state)
        _identity, result = self._choose((
            (action.identity, self.node(
                state, board, self.provider.transition(state, action), depth - 1))
            for action in actions), actor, salt=f"menu:{depth}")
        return result

    def _choose(self, entries, actor: Actor, *, salt: str):
        entries = tuple(entries)
        values = tuple(result[0].total for _key, result in entries)
        best = (max(values) if actor is Actor.OURS else min(values))
        tolerance = self.ctx.compute.noise_tolerance
        tied = tuple(entry for entry in entries
                     if abs(entry[1][0].total - best) <= tolerance)

        indexed = tuple(enumerate(tied))

        def lottery(indexed_entry):
            index, _entry = indexed_entry
            payload = f"{self.ctx.compute.tie_seed}:{salt}:{index}".encode("utf-8")
            return hashlib.blake2b(payload, digest_size=8).digest()

        return min(indexed, key=lottery)[1]

    def _typed(self, state, parent: ObservationState) -> ObservationState:
        found = getattr(state, "observation", None)
        if isinstance(found, ObservationState):
            return found
        return ObservationStateBuilder(parent.decklist).advance(parent, _payload(state))[0]


def _root_footprint(board: ObservationState, provider, state, landings, gaps) -> _RawFootprint:
    if not landings:
        return _RawFootprint()

    def zones(value):
        return {
            "hand": value.me.hand_count,
            "deck": value.me.deck_count,
            "discard": len(value.me.discard),
            "in_play": len(value.me.bodies),
            "attached_energy": sum(len(body.energies) for body in value.me.bodies),
        }

    labels = {name: set() for name in (
        "zones_created", "zones_replaced", "allowances_consumed",
        "immediately_usable_outputs", "opportunities_created",
        "opportunities_preserved", "opportunities_consumed")}
    activations = {feature: 0.0 for feature in (
        "continuation.zone_created", "continuation.zone_replaced",
        "continuation.allowance_consumed", "continuation.usable_output",
        "continuation.opportunity_created", "continuation.opportunity_preserved",
        "continuation.opportunity_consumed")}
    before = zones(board)
    before_actions = _legal_inventory(provider, state, gaps)
    allowances = ("supporter_played", "stadium_played", "energy_attached", "retreated")
    for probability, landing_state, successor, ended in landings:
        after = zones(successor)
        branch_created = {name for name in before if before[name] == 0 < after[name]}
        branch_replaced = {name for name in before
                           if before[name] and before[name] != after[name]}
        branch_allowances = {name for name in allowances
                             if not getattr(board.turn, name)
                             and getattr(successor.turn, name)}
        branch_outputs = {name for name in before if after[name] > before[name]}
        after_actions = Counter() if ended else _legal_inventory(provider, landing_state, gaps)
        branch_opportunities = ((Counter(), Counter(), Counter()) if ended else (
            after_actions - before_actions, after_actions & before_actions,
            before_actions - after_actions))
        branch_groups = (branch_created, branch_replaced, branch_allowances, branch_outputs,
                         *branch_opportunities)
        for label, feature, items in zip(labels, activations, branch_groups):
            labels[label].update(items)
            units = sum(items.values()) if isinstance(items, Counter) else len(items)
            activations[feature] += probability * units
    return _RawFootprint(
        *(tuple(sorted(labels[name])) for name in labels),
        tuple((feature, value) for feature, value in activations.items() if value))


def _action_key(action) -> str:
    return str(action.identity.kind)


def _refresh_state(state, observation, index):
    from .seam import PreviewState
    if isinstance(state, PreviewState):
        successor = ObservationStateBuilder(state.observation.decklist).advance(
            state.observation, observation)[0]
        return PreviewState(
            observation, successor, f"refresh:{index}", deck=state.deck,
            deck_counts=successor.deck_counts or (), prize_counts=state.prize_counts)
    with_observation = getattr(state, "with_observation", None)
    if with_observation is None:
        raise TypeError(f"cannot bind refresh successor for {type(state).__name__}")
    return with_observation(observation)


def _payload(state):
    found = getattr(state, "_provider_payload", None)
    if found is not None:
        return found
    found = getattr(state, "obs", None)
    return found if found is not None else state.observation


def _legal_inventory(provider, state, gaps) -> Counter[str]:
    try:
        return Counter(_action_key(action) for action in provider.actions(state))
    except (KeyError, LookupError) as exc:
        gaps.append(f"continuation action inventory unavailable: {type(exc).__name__}")
        return Counter()


def _footprint_contributions(values, ctx):
    contributions = []
    for feature, activation in values.activations:
        coefficient = ctx.configuration[feature]
        contributions.append(FeatureContribution(
            feature, activation, coefficient, activation * coefficient,
            ("continuation.footprint",)))
    return tuple(contributions)


def _state_contributions(baseline, successor, ctx):
    contributions = []
    before = {item.feature: item.value for item in baseline.activations}
    after = {item.feature: item.value for item in successor.activations}
    for feature in sorted(set(before) | set(after)):
        activation = after.get(feature, 0.0) - before.get(feature, 0.0)
        if not activation:
            continue
        coefficient = ctx.configuration[feature]
        value = activation * coefficient
        contributions.append(FeatureContribution(
            feature, activation, coefficient, value, ("continuation.state",)))
    return tuple(contributions)


def _expected_valuation(weighted, ctx) -> Valuation:
    values = {}
    provenance = {}
    gaps = []
    prize_maps = set()
    for probability, valuation in weighted:
        gaps.extend(valuation.gaps)
        prize_maps.add(valuation.prize_map)
        for item in valuation.activations:
            values[item.feature] = values.get(item.feature, 0.0) + probability * item.value
            provenance.setdefault(item.feature, set()).update(item.provenance)
    activations = tuple(FeatureActivation(
        feature, value, tuple(sorted(provenance[feature])))
        for feature, value in sorted(values.items()) if value)
    contributions = tuple(FeatureContribution(
        item.feature, item.value, ctx.configuration[item.feature],
        item.value * ctx.configuration[item.feature], item.provenance)
        for item in activations)
    prize_map = next(iter(prize_maps)) if len(prize_maps) == 1 else None
    return Valuation(sum(item.value for item in contributions), (), tuple(gaps),
                     activations, contributions, prize_map)


__all__ = ("ContinuationFootprint", "OptionPrice", "price_actions")
