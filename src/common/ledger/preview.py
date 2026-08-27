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
from dataclasses import dataclass, replace

from common.algebra import (Actor, Chance, Choice, Deterministic, Refresh, RevealChoice,
                            Terminal, Unknown)
from common.decision import EvaluationStatus, SearchConfiguration, SuccessorResult
from common.observation import ObservationState, ObservationStateBuilder, TransitionTrace
from common.strategy.context import _BENCH, _DAMAGE_COUNTER_ANY, _DISCARD, _EVOLVE, _MAIN

from .activation import ActivationCompiler, ActivationEnvironment
from .capabilities import DAMAGE_COUNTER_HP
from .chance import refresh_outcomes
from .decision import state_valuation_from_ledger
from .evaluate import FeatureActivation, FeatureContribution, Valuation, evaluate
from .prizes import PrizeMap
from .worth import EvaluationModel

LOTTERY_DIGEST_BYTES = 8
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
    status: EvaluationStatus = EvaluationStatus.COMPLETE
    successors: tuple[SuccessorResult, ...] = ()
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
                  ctx: EvaluationModel, compute=None, budget=None,
                  valuation_fn=None, state_valuation_fn=None) -> tuple[OptionPrice, ...]:
    compute = SearchConfiguration() if compute is None else getattr(compute, "search", compute)
    valuation_fn = ((lambda value: evaluate(value, ctx))
                    if valuation_fn is None else valuation_fn)
    prices = []
    baseline_valuation = valuation_fn(board)
    original_actions = tuple(provider.actions(state))
    action_order = {_action_roster_key(action): index
                    for index, action in enumerate(original_actions)}
    actions = tuple(sorted(
        original_actions,
        key=lambda action: bool(_local_action_events(board, action))))
    for action in actions:
        if action.identity.kind == "end":
            # The one free action: ending the turn is the zero every other option must beat.
            successor = _successor_result(
                1.0, board, True, valuation_fn, state_valuation_fn,
                board.position_key, (action.identity,))
            prices.append(OptionPrice(
                action, 0.0, True, (), ContinuationFootprint(0.0, 0.0, False),
                successors=(successor,), prize_map=baseline_valuation.prize_map))
            continue
        local_action_contribution = _event_contributions(
            "action", _local_action_events(board, action, ctx), ctx, "action")
        local_action_value = sum(item.value for item in local_action_contribution)
        if budget is not None and budget.stop_reason != "complete":
            budget.frontier.append(action.identity)
            activations = tuple(FeatureActivation(
                item.feature, item.activation, item.provenance)
                for item in local_action_contribution)
            footprint = ContinuationFootprint(
                0.0, local_action_value, False,
                activations=activations,
                contributions=local_action_contribution)
            prices.append(OptionPrice(
                action, local_action_value, False,
                (f"search stopped: {budget.stop_reason}",), footprint,
                status=EvaluationStatus.ESTIMATED,
                prize_map=baseline_valuation.prize_map))
            continue
        forced_counter = (board.select is not None
                          and board.select.context == _DAMAGE_COUNTER_ANY)
        walk = _Walk(
            provider, ctx, board.decklist, compute, budget, valuation_fn,
            stop_at_damage_counter=forced_counter)
        node = provider.transition(state, action)
        information_value, information_capped = _immediate_information_value(
            node, compute.path_node_budget)
        main_depth = _main_depth(
            board, action, original_actions, node, compute.main_depth_budget)
        if information_capped:
            walk.gaps.append("information branches capped")
        successor, end_probability, landings = walk.node(
            state, board, node, compute.depth_budget, main_depth)
        landings = _coalesce_landings(landings)
        ends_turn = end_probability >= 1.0
        state_delta = successor.total - baseline
        activation = -(1.0 - end_probability)
        action_events = [("continued_action", activation)]
        action_contribution = _event_contributions(
            "continuation", action_events, ctx, "continuation")
        opportunity_cost = sum(item.value for item in action_contribution)
        opportunity_cost += sum(item.value for item in local_action_contribution)
        state_contributions = _state_contributions(baseline_valuation, successor, ctx)
        track_opportunities = not isinstance(node, (Chance, Refresh, RevealChoice))
        footprint_landings = landings
        if track_opportunities and main_depth > 0:
            footprint_walk = _Walk(
                provider, ctx, board.decklist, compute, None, valuation_fn,
                stop_at_damage_counter=forced_counter)
            _value, _ended, footprint_landings = footprint_walk.node(
                state, board, node, compute.depth_budget, 0)
            footprint_landings = _coalesce_landings(footprint_landings)
            walk.gaps.extend(footprint_walk.gaps)
            walk.unavailable = walk.unavailable or footprint_walk.unavailable
        footprint_values = _root_footprint(
            board, provider, state, action, footprint_landings, walk.gaps,
            track_opportunities=track_opportunities)
        footprint_contributions = _footprint_contributions(footprint_values, ctx)
        information_contributions = _event_contributions(
            "continuation", (("information_value", information_value),),
            ctx, "continuation.information")
        opportunity_cost += sum(item.value for item in footprint_contributions)
        opportunity_cost += sum(item.value for item in information_contributions)
        contributions = (*state_contributions, *action_contribution,
                         *local_action_contribution,
                         *footprint_contributions, *information_contributions)
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
            walk.gaps.append(f"non-finite price for {action.identity}; unavailable")
            walk.unavailable = True
            swing = 0.0
        status = (EvaluationStatus.UNAVAILABLE if walk.unavailable else
                  EvaluationStatus.ESTIMATED if walk.gaps or successor.gaps else
                  EvaluationStatus.COMPLETE)
        explicit_successors = (() if walk.unavailable else tuple(_successor_result(
            probability, landing_board, ended, valuation_fn, state_valuation_fn,
            board.position_key, (action.identity, *path))
            for probability, _landing_state, landing_board, ended, path in landings))
        prices.append(OptionPrice(
            action, swing, ends_turn, tuple(walk.gaps), footprint, status,
            explicit_successors, successor.prize_map))
    return tuple(sorted(
        prices, key=lambda price: action_order[_action_roster_key(price.action)]))


class _Walk:
    """One root option's preview: a node budget, a gap log, and the recursion over nodes."""

    def __init__(self, provider, ctx: EvaluationModel, decklist, compute, budget,
                 valuation_fn, *, stop_at_damage_counter=False):
        self.provider = provider
        self.ctx = ctx
        self.decklist = decklist
        self.compute = compute
        self.budget = budget
        self.valuation = valuation_fn
        self.gaps: list[str] = []
        self.nodes = 0
        self.path_stopped = False
        self.unavailable = False
        self.stop_at_damage_counter = bool(stop_at_damage_counter)

    def node(self, state, board: ObservationState, node, depth: int, main_depth=None):
        main_depth = (self.compute.main_depth_budget if main_depth is None else main_depth)
        if self.budget is not None and not self.budget.visit(getattr(state, "semantic_key", None)):
            self.gaps.append(f"search stopped: {self.budget.stop_reason}")
            self.path_stopped = True
            return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
        self.nodes += 1
        if isinstance(node, Terminal):
            successor = self._typed(node.state, board)
            return self.valuation(successor), 1.0, ((1.0, node.state, successor, True, ()),)
        # The budget binds EVERY recursive node type, not just forced-menu walks: a wide or
        # nested chance tree must also land on the cap instead of running past it.
        if depth <= 0 or self.nodes >= self.compute.path_node_budget:
            if isinstance(node, Deterministic):
                board = self._typed(node.state, board)
            self.gaps.append("chain capped; scored mid-effect board")
            self.path_stopped = True
            landing_state = node.state if isinstance(node, Deterministic) else state
            return self.valuation(board), 0.0, ((1.0, landing_state, board, False, ()),)
        if isinstance(node, Deterministic):
            return self.deterministic(
                node.state, self._typed(node.state, board), depth, main_depth)
        if isinstance(node, Chance):
            weighted, landings, end_probability = [], [], 0.0
            processed_probability = 0.0
            for index, edge in enumerate(node.children):
                child_value, child_end_probability, child_landings = self.node(
                    state, board, edge.node, depth - 1, main_depth)
                if self._budget_stopped():
                    residual = max(0.0, 1.0 - processed_probability)
                    weighted.append((residual, self.valuation(board)))
                    landings.append((residual, state, board, False, ()))
                    if index + 1 < len(node.children):
                        self.gaps.append(
                            "chance branches capped; remaining mass scored at parent")
                    break
                weighted.append((edge.probability, child_value))
                landings.extend((edge.probability * probability, landing_state,
                                 landing_board, ended, path)
                                for probability, landing_state, landing_board, ended, path
                                in child_landings)
                end_probability += edge.probability * child_end_probability
                processed_probability += edge.probability
            return (_expected_valuation(weighted, self.ctx), end_probability,
                    tuple(landings))
        if isinstance(node, Refresh):
            valuation, gaps, outcomes = refresh_outcomes(
                _payload(state), board, node.card_id, node.draws, node.opponent_shuffles,
                self.valuation, self.compute)
            self.gaps.extend(gaps)
            if not outcomes:
                self.unavailable = True
            if main_depth <= 0:
                landings = []
                for index, (probability, successor, synthetic) in enumerate(outcomes):
                    landing_state = _refresh_state(state, synthetic, index)
                    landings.append((probability, landing_state, successor, False, ()))
                return valuation, 0.0, tuple(landings)
            weighted, landings, end_probability = [], [], 0.0
            processed_probability = 0.0
            for index, (probability, successor, synthetic) in enumerate(outcomes):
                if self._budget_stopped():
                    residual = max(0.0, 1.0 - processed_probability)
                    weighted.append((residual, self.valuation(board)))
                    landings.append((residual, state, board, False, ()))
                    self.gaps.append(
                        "refresh branches capped; remaining mass scored at parent")
                    break
                landing_state = _refresh_state(state, synthetic, index)
                child_value, child_end, child_landings = self.deterministic(
                    landing_state, successor, depth - 1, main_depth)
                weighted.append((probability, child_value))
                landings.extend((probability * child_probability, child_state,
                                 child_board, ended, path)
                                for child_probability, child_state, child_board, ended, path
                                in child_landings)
                end_probability += probability * child_end
                processed_probability += probability
            return (_expected_valuation(weighted, self.ctx), end_probability,
                    tuple(landings))
        if isinstance(node, RevealChoice):
            priced = {}
            for edge in node.choices:
                if self._budget_stopped():
                    break
                priced[edge.label] = self.node(
                    state, board, edge.node, depth - 1, main_depth)
            if self._budget_stopped():
                self.gaps.append(
                    "reveal branches capped; remaining outcomes scored at parent")
                return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
            weighted, landings, end_probability = [], [], 0.0
            processed_probability = 0.0
            for index, outcome in enumerate(node.outcomes):
                if self.budget is not None and not self.budget.visit(
                        f"reveal-outcome:{index}"):
                    self.gaps.append(f"search stopped: {self.budget.stop_reason}")
                    self.gaps.append(
                        "reveal outcomes capped; remaining mass scored at parent")
                    residual = max(0.0, 1.0 - processed_probability)
                    weighted.append((residual, self.valuation(board)))
                    landings.append((residual, state, board, False, ()))
                    break
                label, result = self._choose(
                    ((label, priced[label]) for label in outcome.choices), node.actor,
                    salt=f"reveal:{depth}")
                best_value, best_end_probability, best_landings = _with_path(result, label)
                weighted.append((outcome.probability, best_value))
                landings.extend((outcome.probability * probability, landing_state,
                                 landing_board, ended, path)
                                for probability, landing_state, landing_board, ended, path
                                in best_landings)
                end_probability += outcome.probability * best_end_probability
                processed_probability += outcome.probability
            return (_expected_valuation(weighted, self.ctx), end_probability,
                    tuple(landings))
        if isinstance(node, Choice):
            entries = []
            for edge in node.children:
                if self._budget_stopped():
                    break
                entries.append((edge.label, self.node(
                    state, board, edge.node, depth - 1, main_depth)))
            if not entries:
                return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
            label, result = self._choose(entries, node.actor, salt=f"choice:{depth}")
            return _with_path(result, label)
        if isinstance(node, Unknown):
            self.gaps.append(f"unpriceable: {node.reason} ({node.missing_fact})")
            self.unavailable = True
            return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
        self.gaps.append(f"unpriceable: undeclared node {type(node).__name__}")
        self.unavailable = True
        return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)

    def deterministic(self, state, board: ObservationState, depth: int, main_depth: int):
        context_value = None if board.select is None else board.select.context
        context = _MAIN if context_value is None else int(context_value)
        if context == _DAMAGE_COUNTER_ANY:
            if self.stop_at_damage_counter:
                return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
            return self.damage_counter_rollout(state, board, depth)
        if context == _MAIN:
            if main_depth <= 0:
                return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
            try:
                actions = tuple(self.provider.actions(state))
            except (KeyError, LookupError):
                return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
            if not actions:
                return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
            actor = self.provider.actor(state)
            entries = []
            for action in actions:
                if self._budget_stopped():
                    break
                if action.identity.kind == "end":
                    result = (self.valuation(board), 1.0,
                              ((1.0, state, board, True, ()),))
                else:
                    try:
                        successor = self.provider.transition(state, action)
                    except (KeyError, LookupError):
                        result = (self.valuation(board), 0.0,
                                  ((1.0, state, board, False, ()),))
                    else:
                        result = self.node(
                            state, board, successor, depth - 1, main_depth - 1)
                        valuation, end_probability, landings = result
                        result = (_expected_valuation((
                            (1.0 - self.compute.main_continuation_discount,
                             self.valuation(board)),
                            (self.compute.main_continuation_discount, valuation),
                        ), self.ctx), end_probability, landings)
                entries.append((action.identity, result))
            if not entries:
                return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
            identity, result = self._choose(entries, actor, salt=f"main:{depth}")
            valuation, _planned_end_probability, landings = _with_path(result, identity)
            return valuation, 0.0, landings
        actions = self.provider.actions(state)
        if not actions:
            self.gaps.append("forced menu offered no actions; unavailable")
            self.unavailable = True
            return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
        if board.select is not None and board.select.context == _DAMAGE_COUNTER_ANY:
            live = tuple(action for action in actions
                         if not _local_action_events(board, action))
            if live:
                actions = live
        actor = self.provider.actor(state)
        entries = []
        for action in actions:
            if self._budget_stopped():
                break
            entries.append((action.identity, self.node(
                state, board, self.provider.transition(state, action), depth - 1, main_depth)))
        if not entries:
            return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
        identity, result = self._choose(entries, actor, salt=f"menu:{depth}")
        return _with_path(result, identity)

    def damage_counter_rollout(self, state, board, depth):
        path = []
        while (depth > 0 and board.select is not None
               and board.select.context == _DAMAGE_COUNTER_ANY):
            actions = tuple(self.provider.actions(state))
            live = tuple(action for action in actions
                         if not _local_action_events(board, action))
            actions = live or actions
            candidates = []
            for action in actions:
                if self.nodes >= self.compute.path_node_budget:
                    self.gaps.append("damage-counter rollout capped")
                    self.path_stopped = True
                    return (self.valuation(board), 0.0,
                            ((1.0, state, board, False, tuple(path)),))
                self.nodes += 1
                node = self.provider.transition(state, action)
                if not isinstance(node, (Deterministic, Terminal)):
                    self.gaps.append(
                        f"unpriceable damage-counter node {type(node).__name__}")
                    self.unavailable = True
                    continue
                successor = self._typed(node.state, board)
                valuation = self.valuation(successor)
                local = sum(item.value for item in _event_contributions(
                    "action", _local_action_events(board, action, self.ctx),
                    self.ctx, "action"))
                candidates.append((
                    action, node, successor, valuation,
                    replace(valuation, total=valuation.total + local)))
            if not candidates:
                return (self.valuation(board), 0.0,
                        ((1.0, state, board, False, tuple(path)),))
            actor = self.provider.actor(state)
            identity, _result = self._choose((
                (action.identity, (scored, 0.0, ()))
                for action, _node, _successor, _valuation, scored in candidates
            ), actor, salt=f"damage-counter:{depth}")
            action, node, board, valuation, _scored = next(
                row for row in candidates if row[0].identity == identity)
            state = node.state
            path.append(action.identity)
            depth -= 1
            if isinstance(node, Terminal):
                return valuation, 1.0, ((1.0, state, board, True, tuple(path)),)
        if depth <= 0 and board.select is not None \
                and board.select.context == _DAMAGE_COUNTER_ANY:
            self.gaps.append("damage-counter rollout depth capped")
            self.path_stopped = True
        return (self.valuation(board), 0.0,
                ((1.0, state, board, False, tuple(path)),))

    def _budget_stopped(self):
        return self.path_stopped or (
            self.budget is not None and self.budget.stop_reason != "complete")

    def _choose(self, entries, actor: Actor, *, salt: str):
        entries = tuple(entries)
        values = tuple(result[0].total for _key, result in entries)
        best = (max(values) if actor is Actor.OURS else min(values))
        tolerance = self.compute.noise_tolerance
        tied = tuple(entry for entry in entries
                     if abs(entry[1][0].total - best) <= tolerance)

        indexed = tuple(enumerate(tied))

        def lottery(indexed_entry):
            index, _entry = indexed_entry
            payload = f"{self.compute.tie_seed}:{salt}:{index}".encode("utf-8")
            return hashlib.blake2b(payload, digest_size=LOTTERY_DIGEST_BYTES).digest()

        return min(indexed, key=lottery)[1]

    def _typed(self, state, parent: ObservationState) -> ObservationState:
        found = getattr(state, "observation", None)
        if isinstance(found, ObservationState):
            return found
        return ObservationStateBuilder(parent.decklist).advance(parent, _payload(state))[0]


def _with_path(result, step):
    valuation, end_probability, landings = result
    return valuation, end_probability, tuple(
        (probability, state, board, ended, (step, *path))
        for probability, state, board, ended, path in landings)


def _coalesce_landings(landings):
    combined = {}
    for probability, state, board, ended, path in landings:
        key = (board.valuation_key, bool(ended), tuple(path))
        if key in combined:
            previous = combined[key]
            combined[key] = (min(1.0, math.fsum((previous[0], probability))),
                             *previous[1:])
        else:
            combined[key] = (probability, state, board, ended, path)
    return tuple(combined.values())


def _immediate_information_value(node, branch_budget: int) -> tuple[float, bool]:
    pending = [(1.0, node)]
    value = 0.0
    visited = 0
    capped = False
    while pending and visited < branch_budget:
        probability, current = pending.pop()
        visited += 1
        if isinstance(current, RevealChoice):
            for outcome in current.outcomes:
                if visited >= branch_budget:
                    return value, True
                visited += 1
                value += (probability * outcome.probability
                          * math.log2(max(1, len(outcome.choices))))
        elif isinstance(current, Chance):
            remaining = max(0, branch_budget - visited - len(pending))
            children = current.children[:remaining]
            capped = capped or len(current.children) > len(children)
            pending.extend((probability * edge.probability, edge.node)
                           for edge in reversed(children))
    return value, capped or bool(pending)


def _root_footprint(board: ObservationState, provider, state, action, landings, gaps, *,
                    track_opportunities: bool) -> _RawFootprint:
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
    activations = {claim: 0.0 for claim in (
        "zone_created", "zone_replaced", "allowance_consumed", "usable_output",
        "opportunity_created", "opportunity_preserved", "opportunity_consumed")}
    before = zones(board)
    before_actions = (_legal_inventory(provider, state, gaps)
                      if track_opportunities else Counter())
    executed_kind = _action_key(action)
    if before_actions[executed_kind] > 0:
        before_actions[executed_kind] -= 1
        if before_actions[executed_kind] == 0:
            del before_actions[executed_kind]
    allowances = ("supporter_played", "stadium_played", "energy_attached", "retreated")
    for probability, landing_state, successor, ended, _path in landings:
        after = zones(successor)
        branch_created = {name for name in before if before[name] == 0 < after[name]}
        branch_replaced = {name for name in before
                           if before[name] and before[name] != after[name]}
        branch_allowances = {name for name in allowances
                             if not getattr(board.turn, name)
                             and getattr(successor.turn, name)}
        branch_outputs = {name for name in before if after[name] > before[name]}
        after_actions = (Counter() if ended or not track_opportunities
                         else _legal_inventory(
                             provider, landing_state, gaps, report_missing=False))
        branch_opportunities = ((Counter(), Counter(), Counter())
                                if ended or not track_opportunities or not after_actions else (
                                    after_actions - before_actions,
                                    after_actions & before_actions,
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


def _action_roster_key(action):
    return action.identity, tuple(action.selection)


def _main_depth(board, action, actions, node, configured):
    if board.select is not None and board.select.context == _DAMAGE_COUNTER_ANY:
        return 0
    if isinstance(node, (Chance, Refresh, RevealChoice)):
        return 0
    configured = int(configured)
    if configured <= 0:
        return 0
    if board.select is not None and board.select.context == _DISCARD:
        return 1
    if action.identity.kind in {"attach", "retreat"}:
        return 1
    if action.identity.kind not in {"ability", "skill"}:
        return 0
    options = () if board.select is None else board.select.options
    if len(action.selection) != 1 or not 0 <= action.selection[0] < len(options):
        return 1
    source = options[action.selection[0]]
    source_location = (source.area, source.index)
    for candidate in actions:
        if candidate.identity.kind != "evolve" or len(candidate.selection) != 1:
            continue
        index = candidate.selection[0]
        if not 0 <= index < len(options):
            continue
        target = options[index]
        if target.type == _EVOLVE \
                and (target.inPlayArea, target.inPlayIndex) == source_location:
            return configured
    return 0


def _local_action_events(board, action, ctx=None):
    select = board.select
    if select is None or select.context != _DAMAGE_COUNTER_ANY:
        return ()
    for selection in action.selection:
        if not 0 <= selection < len(select.options):
            continue
        option = select.options[selection]
        if option.area != _BENCH or not isinstance(option.index, int):
            continue
        side = board.me if option.playerIndex == board.seat else board.them
        if not 0 <= option.index < len(side.bench):
            continue
        target = side.bench[option.index]
        if target.hp <= 0:
            return (("overkill_counter", 1.0),)
        if ctx is not None:
            facts = ctx.facts(target.card.card_id)
            prize_value = int(getattr(facts, "prize_value", 1) or 1)
            progress = (min(DAMAGE_COUNTER_HP, target.hp)
                        / max(DAMAGE_COUNTER_HP, target.hp) * prize_value)
            return (("damage_counter_progress", progress),)
    return ()


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


def _legal_inventory(provider, state, gaps, *, report_missing=True) -> Counter[str]:
    try:
        return Counter(_action_key(action) for action in provider.actions(state))
    except (KeyError, LookupError) as exc:
        if report_missing:
            gaps.append(f"continuation action inventory unavailable: {type(exc).__name__}")
        return Counter()


def _footprint_contributions(values, ctx):
    return _event_contributions(
        "continuation", values.activations, ctx, "continuation.footprint")


def _event_contributions(source, events, ctx, provenance):
    contributions = []
    compiler = ActivationCompiler()
    for claim, value in events:
        if not compiler.catalog.has_activation_rules(source, (claim,)):
            raise KeyError(f"Feature Catalog has no {source!r} rule for {claim!r}")
        for activation in compiler.compile(
                source, (claim,), ActivationEnvironment(scale=value)):
            coefficient = ctx.configuration[activation.feature]
            contributions.append(FeatureContribution(
                activation.feature, activation.value, coefficient,
                activation.value * coefficient, (provenance,)))
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


def _successor_result(probability, board, ended, valuation_fn,
                      state_valuation_fn, start_position_key, path) -> SuccessorResult:
    valuation = (state_valuation_from_ledger(board, valuation_fn(board))
                 if state_valuation_fn is None else state_valuation_fn(board))
    trace = TransitionTrace(1, start_position_key, tuple(path), board.position_key)
    return SuccessorResult(
        probability, valuation, ended, board, trace, tuple(path), valuation.status,
        "; ".join(valuation.gaps) if valuation.status is EvaluationStatus.UNAVAILABLE else None,
    )


__all__ = ("ContinuationFootprint", "OptionPrice", "price_actions")
