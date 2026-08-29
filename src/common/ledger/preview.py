"""Price one option: the engine plays it, ObservationState digests the reprint, the Ledger differences.

Every transition node the providers emit is priced here. A forced follow-up chain is resolved
inside the preview and its best sub-menu choices are cached for the matching live prompts.
A capped or unpriceable chain scores
the last board it could see and logs the gap; it never deletes the root option (the end-chain
lesson: a cap must not veto the action carrying the turn's value)."""
from __future__ import annotations

import math
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, replace

from common.algebra import (Actor, Chance, Choice, Deterministic, Refresh, RevealChoice,
                            Terminal, Unknown)
from common.cards import card_clauses
from common.cards.card_facts import SUPPORTER, PokemonCard, TrainerCard
from common.decision import EvaluationStatus, SearchConfiguration, SuccessorResult
from common.observation import ObservationState, ObservationStateBuilder, TransitionTrace
from common.strategy.context import (_ACTIVE, _BENCH, _DAMAGE_COUNTER_ANY, _DISCARD,
                                     _EVOLVE, _MAIN, _PLAY, _ATTACH_FROM, _TO_BENCH, _TO_HAND)

from .activation import ActivationCompiler, ActivationEnvironment
from .capabilities import DAMAGE_COUNTER_HP, DAMAGE_UNIT_HP
from .chance import RefreshSummary, refresh_outcomes
from .decision import state_valuation_from_ledger
from .evaluate import (_active_doomed, FeatureActivation, FeatureContribution,
                       Valuation, evaluate)
from .prizes import PrizeMap
from .worth import EvaluationModel

LOTTERY_DIGEST_BYTES = 8
PRIZE_PHASE_PIVOT = 4
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
    chance_summaries: tuple[RefreshSummary, ...] = ()
    continuation_policy: tuple[tuple[tuple[object, ...], object], ...] = ()


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
    end_action = next((action for action in original_actions
                       if action.identity.kind == "end"), None)
    end_valuation = baseline_valuation
    end_board = board
    end_gaps: list[str] = []
    end_unavailable = False
    if end_action is not None:
        end_walk = _Walk(provider, ctx, board.decklist, compute, budget, valuation_fn)
        try:
            end_node = provider.transition(state, end_action)
            end_valuation, _end_probability, end_landings = end_walk.node(
                state, board, end_node, compute.depth_budget)
            end_landings = _coalesce_landings(end_landings)
            if len(end_landings) == 1:
                _probability, _state, end_board, _ended, _path = end_landings[0]
            else:
                end_gaps.append("end counterfactual has multiple successors")
                end_unavailable = True
        except (KeyError, LookupError) as exc:
            end_gaps.append(
                f"end counterfactual unavailable: {type(exc).__name__}")
            end_unavailable = True
        end_gaps.extend(end_walk.gaps)
        end_unavailable = end_unavailable or end_walk.unavailable
    action_order = {_action_roster_key(action): index
                    for index, action in enumerate(original_actions)}
    actions = tuple(sorted(
        original_actions,
        key=lambda action: bool(_local_action_events(board, action))))
    for action in actions:
        if action.identity.kind == "end":
            state_delta = end_valuation.total - baseline_valuation.total
            state_contributions = _state_contributions(
                baseline_valuation, end_valuation, ctx)
            activations = tuple(FeatureActivation(
                item.feature, item.activation, item.provenance)
                for item in state_contributions)
            footprint = ContinuationFootprint(
                state_delta, 0.0, False,
                activations=activations, contributions=state_contributions)
            successors = (() if end_unavailable else (_successor_result(
                1.0, end_board, True, valuation_fn, state_valuation_fn,
                board.position_key, (action.identity,),
                precomputed_valuation=end_valuation),))
            prices.append(OptionPrice(
                action, state_delta, True, tuple(end_gaps), footprint,
                status=(EvaluationStatus.UNAVAILABLE if end_unavailable else
                        EvaluationStatus.ESTIMATED if end_gaps
                        else EvaluationStatus.COMPLETE),
                successors=successors, prize_map=end_valuation.prize_map))
            continue
        local_action_contribution = _event_contributions(
            "action", _local_action_events(board, action, ctx), ctx, "action")
        local_action_value = sum(item.value for item in local_action_contribution)
        if (budget is not None
                and (budget.stop_reason != "complete"
                     or (hasattr(budget, "check") and budget.check()))):
            budget.frontier.append(action.identity)
            footprint = ContinuationFootprint(
                0.0, local_action_value, False,
                activations=(), contributions=())
            prices.append(OptionPrice(
                action, 0.0, False,
                (f"search stopped: {budget.stop_reason}",), footprint,
                status=EvaluationStatus.ESTIMATED,
                prize_map=baseline_valuation.prize_map))
            continue
        walk = _Walk(
            provider, ctx, board.decklist, compute, budget, valuation_fn)
        node = provider.transition(state, action)
        information_value, information_capped = _immediate_information_value(
            node, compute.path_node_budget)
        if information_capped:
            walk.gaps.append("information branches capped")
        successor, end_probability, landings = walk.node(
            state, board, node, compute.depth_budget)
        landings = _coalesce_landings(landings)
        ends_turn = end_probability >= 1.0
        state_delta = successor.total - baseline_valuation.total
        activation = -(1.0 - end_probability)
        action_events = [("continued_action", activation)]
        action_contribution = _event_contributions(
            "continuation", action_events, ctx, "continuation")
        opportunity_cost = sum(item.value for item in action_contribution)
        opportunity_cost += sum(item.value for item in local_action_contribution)
        state_contributions = _state_contributions(
            baseline_valuation, successor, ctx)
        realization_contributions = _realized_portfolio_contributions(
            baseline_valuation, board, action)
        discard_contributions = _discard_spend_contributions(
            baseline_valuation, board, action, ctx)
        knockout_contributions = _prize_transition_contributions(board, landings, ctx)
        track_opportunities = not isinstance(node, (Chance, Refresh, RevealChoice))
        footprint_landings = landings
        footprint_values = _root_footprint(
            board, provider, state, action, footprint_landings, walk.gaps,
            track_opportunities=track_opportunities)
        if isinstance(node, Refresh):
            facts = ctx.facts(node.card_id)
            allowances = (("supporter_played",)
                          if isinstance(facts, TrainerCard) and facts.kind == SUPPORTER
                          else ())
            footprint_values = replace(
                footprint_values,
                zones_replaced=tuple(sorted(set(
                    (*footprint_values.zones_replaced, "deck", "hand")))),
                allowances_consumed=tuple(sorted(set(
                    (*footprint_values.allowances_consumed, *allowances)))),
                immediately_usable_outputs=tuple(sorted(set((
                    *footprint_values.immediately_usable_outputs, "hand")))),
                opportunities_consumed=tuple(sorted(set((
                    *footprint_values.opportunities_consumed, "play")))))
        footprint_values = _with_portfolio_opportunity_losses(
            footprint_values, state_contributions, original_actions)
        footprint_contributions = _footprint_contributions(footprint_values, ctx)
        information_contributions = _event_contributions(
            "continuation", (("information_value", information_value),),
            ctx, "continuation.information")
        opportunity_cost += sum(item.value for item in footprint_contributions)
        opportunity_cost += sum(item.value for item in information_contributions)
        opportunity_cost += sum(item.value for item in realization_contributions)
        opportunity_cost += sum(item.value for item in discard_contributions)
        opportunity_cost += sum(item.value for item in knockout_contributions)
        contributions = state_contributions
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
        swing = footprint.state_delta
        if not math.isfinite(swing):
            # Belt behind configuration validation: a NaN/inf swing would make every price
            # unrankable. Score neutral, SAY SO — a visible gap, never a silent absorb.
            walk.gaps.append(f"non-finite price for {action.identity}; unavailable")
            walk.unavailable = True
            swing = 0.0
        comparison_gaps = ()
        status = (EvaluationStatus.UNAVAILABLE if walk.unavailable else
                  EvaluationStatus.ESTIMATED if walk.gaps or successor.gaps
                  or comparison_gaps else
                  EvaluationStatus.COMPLETE)
        explicit_successors = (() if walk.unavailable else tuple(_successor_result(
            probability, landing_board, ended, valuation_fn, state_valuation_fn,
            board.position_key, (action.identity, *path))
            for probability, _landing_state, landing_board, ended, path in landings))
        prices.append(OptionPrice(
            action, swing, ends_turn, (*walk.gaps, *comparison_gaps), footprint, status,
            explicit_successors, successor.prize_map, tuple(walk.chance_summaries),
            tuple(walk.continuation_policy.items())))
    return tuple(sorted(
        prices, key=lambda price: action_order[_action_roster_key(price.action)]))


class _Walk:
    """One root option's preview: a node budget, a gap log, and the recursion over nodes."""

    def __init__(self, provider, ctx: EvaluationModel, decklist, compute, budget,
                 valuation_fn):
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
        self.chance_summaries = []
        self.continuation_policy = {}

    def node(self, state, board: ObservationState, node, depth: int):
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
                node.state, self._typed(node.state, board), depth)
        if isinstance(node, Chance):
            weighted, landings, end_probability = [], [], 0.0
            processed_probability = 0.0
            for index, edge in enumerate(node.children):
                child_value, child_end_probability, child_landings = self.node(
                    state, board, edge.node, depth - 1)
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
            valuation, gaps, summary = refresh_outcomes(
                _payload(state), board, node.card_id, node.draws, node.opponent_shuffles,
                self.valuation, self.compute, self.ctx)
            self.gaps.extend(gaps)
            self.chance_summaries.append(summary)
            if not summary.sample_count and summary.method == "sampled":
                self.unavailable = True
            return valuation, 0.0, ()
        if isinstance(node, RevealChoice):
            priced = {}
            for edge in node.choices:
                if self._budget_stopped():
                    break
                priced[edge.label] = self.node(
                    state, board, edge.node, depth - 1)
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
                self.continuation_policy[tuple(outcome.choices)] = label
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
                    state, board, edge.node, depth - 1)))
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

    def deterministic(self, state, board: ObservationState, depth: int):
        context_value = None if board.select is None else board.select.context
        context = _MAIN if context_value is None else int(context_value)
        if context == _DAMAGE_COUNTER_ANY:
            return self.damage_counter_rollout(state, board, depth)
        if context == _MAIN:
            ended = self.provider.actor(state) is Actor.OPPONENT
            return (self.valuation(board), float(ended),
                    ((1.0, state, board, ended, ()),))
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
            result = self.node(
                state, board, self.provider.transition(state, action), depth - 1)
            local = sum(item.value for item in _event_contributions(
                "action", _local_action_events(board, action, self.ctx),
                self.ctx, "action"))
            valuation, end_probability, landings = result
            scored = (replace(valuation, total=valuation.total + local),
                      end_probability, landings)
            entries.append((action.identity, result, scored))
        if not entries:
            return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
        identity, _scored = self._choose(
            ((identity, scored) for identity, _result, scored in entries),
            actor, salt=f"menu:{depth}")
        result = next(result for candidate, result, _scored in entries
                      if candidate == identity)
        self.continuation_policy[tuple(action.identity for action in actions)] = identity
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
                if self.budget is not None and not self.budget.visit(action.identity):
                    self.gaps.append(f"search stopped: {self.budget.stop_reason}")
                    self.path_stopped = True
                    return (self.valuation(board), 0.0,
                            ((1.0, state, board, False, tuple(path)),))
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
            self.continuation_policy[
                tuple(action.identity for action in actions)] = identity
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
        valuation, end_probability, landings = self.deterministic(state, board, depth)
        return valuation, end_probability, tuple(
            (probability, landing_state, landing_board, ended,
             (*path, *suffix))
            for probability, landing_state, landing_board, ended, suffix in landings)

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


def _local_action_events(board, action, ctx=None):
    dead_discard = _dead_discard(board, action, ctx)
    if dead_discard:
        return (("dead_discard", dead_discard),)
    dead_play = _dead_play(board, action, ctx)
    if dead_play:
        return (("dead_play", dead_play),)
    draw_before_refresh = _draw_before_refresh(board, action, ctx)
    if draw_before_refresh:
        return (("draw_before_refresh", draw_before_refresh),)
    play_before_refresh = _play_before_refresh(board, action, ctx)
    if play_before_refresh:
        return (("play_before_refresh", play_before_refresh),)
    if ctx is not None and _body_ability_ready(board, action, ctx):
        return (("body_ability_ready", 1.0),)
    if ctx is not None and (overflow := _body_copy_overflow(board, action, ctx)):
        return (("body_copy_overflow", overflow),)
    if ctx is not None and _retreats_doomed_denial(board, action, ctx):
        return (("retreat_doomed_denial", 1.0),)
    select = board.select
    if ctx is not None and select is not None and select.context == _ATTACH_FROM:
        return _acceleration_phase_events(board, action, ctx)
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


def _dead_discard(board, action, ctx):
    if ctx is None or board.select is None or board.select.context != _DISCARD:
        return 0.0
    from .worth import Demand, DemandState, _liveness

    demand = Demand.read(board.me, ctx, board.turn)
    return float(sum(
        _liveness(card_id, ctx.facts(card_id), demand, ctx, board.deck_counts)[0]
        is DemandState.DEAD
        for _serial, card_id in _selected_cards(board, action)
        if card_id is not None))


def _dead_play(board, action, ctx):
    if ctx is None or action.identity.kind != "play":
        return 0.0
    from .worth import Demand, DemandState, _liveness

    demand = Demand.read(board.me, ctx, board.turn)
    return float(sum(
        _liveness(card_id, ctx.facts(card_id), demand, ctx, board.deck_counts)[0]
        is DemandState.DEAD
        for _serial, card_id in _selected_cards(board, action)
        if card_id is not None))


def _retreats_doomed_denial(board, action, ctx):
    if action.identity.kind != "retreat" or board.me.active is None:
        return False
    facts = ctx.facts(board.me.active.card.card_id)
    denial = any(clause.kind in {"attack_lock", "item_lock", "no_retreat", "retreat_lock"}
                 for clause in card_clauses(facts))
    return denial and _active_doomed(board.them, board.me, ctx)


def _body_copy_overflow(board, action, ctx):
    from .worth import pokemon_copy_capacity

    if board.select is None or board.select.context not in {_TO_BENCH, _TO_HAND}:
        return 0
    selectable = {_option_card_id(board, option) for option in board.select.options}
    selectable.discard(None)
    if board.select.max_count == 1 and len(selectable) <= 1:
        return 0
    selected = Counter(card_id for _serial, card_id in _selected_cards(board, action)
                       if card_id is not None
                       and pokemon_copy_capacity(ctx.facts(card_id)) != 1)
    owned = Counter(body.card.card_id for body in board.me.bodies)
    owned.update(card.card_id for card in board.me.hand)
    overflow = 0
    owned_names = Counter(ctx.facts(card_id).name for card_id in owned.elements())
    for card_id, count in selected.items():
        facts = ctx.facts(card_id)
        capacity = pokemon_copy_capacity(facts)
        if capacity is None:
            continue
        if (isinstance(facts, PokemonCard) and facts.evolves_from
                and not owned_names[facts.evolves_from]):
            capacity = min(capacity, 1)
        overflow += max(0, owned[card_id] + count - capacity)
    return overflow


def _option_card_id(board, option):
    if option.cardId is not None:
        return option.cardId
    if option.serial is not None or not isinstance(option.index, int):
        return None
    if board.select.deck and 0 <= option.index < len(board.select.deck):
        return board.select.deck[option.index].card_id
    if 0 <= option.index < len(board.me.hand):
        return tuple(board.me.hand)[option.index].card_id
    return None


def _body_ability_ready(board, action, ctx):
    if board.select is None:
        return False
    selected = tuple(ctx.facts(card_id)
                     for _serial, card_id in _selected_cards(board, action)
                     if card_id is not None)
    triggered_evolutions = tuple(
        facts for facts in selected if isinstance(facts, PokemonCard)
        and facts.evolves_from
        and any(clause.trigger == "on_evolve" for clause in card_clauses(facts)))
    if any(
            ctx.facts(body.card.card_id).name == facts.evolves_from
            and not body.appeared_this_turn
            for facts in triggered_evolutions for body in board.me.bodies):
        return True
    if action.identity.kind != "evolve":
        return False
    if not any(any(clause.allowance == "body" for clause in card_clauses(facts))
               for facts in selected):
        return False
    selected_names = {facts.name for facts in selected}
    return not any(getattr(ctx.facts(body.card.card_id), "evolves_from", None)
                   in selected_names for body in board.me.bodies)


def _acceleration_phase_events(board, action, ctx):
    from .worth import _forward_lines

    values = []
    for selection in action.selection:
        if not 0 <= selection < len(board.select.options):
            continue
        option = board.select.options[selection]
        if option.area != _BENCH or not isinstance(option.index, int):
            continue
        side = board.me if option.playerIndex == board.seat else board.them
        if not 0 <= option.index < len(side.bench):
            continue
        facts = ctx.facts(side.bench[option.index].card.card_id)
        line = (facts, *(ctx.facts(card_id)
                         for card_id in _forward_lines().get(facts.name, ())))
        route_prizes = max((int(getattr(card, "prize_value", 1) or 1)
                            for card in line if card is not None), default=1)
        damage_per_energy = max((
            float(attack.damage or attack.damage_fix or attack.damage_max or 0)
            / DAMAGE_UNIT_HP / max(1, len(attack.cost))
            for card in line if card is not None for attack in card.attacks), default=0.0)
        matches = ((route_prizes > 1) == (side is board.me
                    and board.them.prize_count <= PRIZE_PHASE_PIVOT))
        values.append((1.0 if matches else -1.0) * damage_per_energy)
    return (("acceleration_phase_fit", sum(values)),) if values else ()


def _draw_before_refresh(board, action, ctx):
    if ctx is None or action.identity.kind != "ability" or board.select is None \
            or board.turn.supporter_played:
        return 0.0
    refresh_available = any(
        isinstance(facts := ctx.facts(card.card_id), TrainerCard)
        and facts.kind == SUPPORTER
        and any(clause.kind == "draw" and clause.rider == "shuffle_own_hand_in"
                for clause in card_clauses(facts))
        for card in tuple(board.me.hand))
    if not refresh_available or len(action.selection) != 1:
        return 0.0
    selected = action.selection[0]
    if not 0 <= selected < len(board.select.options):
        return 0.0
    option = board.select.options[selected]
    area = option.inPlayArea if option.inPlayArea is not None else option.area
    index = option.inPlayIndex if option.inPlayIndex is not None else option.index
    if area == _BENCH and isinstance(index, int) and 0 <= index < len(board.me.bench):
        body = board.me.bench[index]
    elif area == _ACTIVE and board.me.active is not None:
        body = board.me.active
    else:
        return 0.0
    facts = ctx.facts(body.card.card_id)
    return max((float(clause.amount or 1)
                for ability in getattr(facts, "abilities", ())
                for clause in ability.clauses if clause.kind == "draw"), default=0.0)


def _play_before_refresh(board, action, ctx):
    if ctx is None or action.identity.kind != "play" or board.select is None:
        return 0.0
    selected = tuple(ctx.facts(card_id) for _serial, card_id in
                     _selected_cards(board, action) if card_id is not None)
    refresh = any(
        isinstance(facts, TrainerCard) and facts.kind == SUPPORTER
        and any(clause.kind == "draw" and clause.rider == "shuffle_own_hand_in"
                for clause in card_clauses(facts))
        for facts in selected)
    if not refresh:
        return 0.0
    playable = 0
    hand = tuple(board.me.hand)
    for option in board.select.options:
        if option.type != _PLAY or not isinstance(option.index, int) \
                or not 0 <= option.index < len(hand):
            continue
        facts = ctx.facts(hand[option.index].card_id)
        if isinstance(facts, TrainerCard) and facts.kind != SUPPORTER:
            playable += 1
    return float(playable)


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


def _with_portfolio_opportunity_losses(values, contributions, root_actions):
    contracts = {"option.energy": "attach"}
    root_kinds = {_action_key(action) for action in root_actions}
    consumed = set(values.opportunities_consumed)
    for feature, kind in contracts.items():
        if kind in root_kinds and sum(
                item.activation for item in contributions if item.feature == feature) < 0:
            consumed.add(kind)
    added = len(consumed) - len(values.opportunities_consumed)
    if not added:
        return values
    activations = dict(values.activations)
    activations["opportunity_consumed"] = (
        activations.get("opportunity_consumed", 0.0) + added)
    return replace(
        values, opportunities_consumed=tuple(sorted(consumed)),
        activations=tuple(sorted(activations.items())))


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


def _prize_transition_contributions(board, landings, ctx):
    realized = sum(
        probability * (
            max(0, board.me.prize_count - successor.me.prize_count)
            - max(0, board.them.prize_count - successor.them.prize_count))
        for probability, _state, successor, _ended, _path in landings)
    return (_event_contributions(
        "observation", (("realized_knockout", realized),), ctx,
        "continuation.prize_transition") if realized else ())


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


def _selected_cards(board, action):
    if board.select is None:
        return ()
    options = board.select.options
    resolved = []
    for index in action.selection:
        if not isinstance(index, int) or not 0 <= index < len(options):
            continue
        option = options[index]
        card = None
        if option.serial is None and option.cardId is None and isinstance(option.index, int):
            if board.select.deck and 0 <= option.index < len(board.select.deck):
                card = board.select.deck[option.index]
            elif 0 <= option.index < len(board.me.hand):
                card = tuple(board.me.hand)[option.index]
        resolved.append((
            option.serial if option.serial is not None else getattr(card, "serial", None),
            option.cardId if option.cardId is not None else getattr(card, "card_id", None)))
    if any(card_id is None for _serial, card_id in resolved):
        identity_ids = iter(int(value) for value in re.findall(
            r'"id":(\d+)', "".join(map(str, action.identity.parts))))
        resolved = [(serial, card_id if card_id is not None else next(identity_ids, None))
                    for serial, card_id in resolved]
    return tuple(resolved)


def _portfolio_tokens(board, action):
    return tuple(token for token, _serial, _card_id in _portfolio_sources(board, action))


def _portfolio_sources(board, action):
    sources = []
    for serial, card_id in _selected_cards(board, action):
        if serial is None and card_id is None:
            continue
        token = (f"feasible_option_portfolio:serial:{serial}"
                 if serial is not None else f"feasible_option_portfolio:card:{card_id}")
        sources.append((token, serial, card_id))
    return tuple(sources)


def _realized_portfolio_contributions(baseline, board, action):
    if action.identity.kind not in {"play", "attach", "evolve"} or board.select is None:
        return ()
    tokens = _portfolio_tokens(board, action)
    if len(tokens) != 1:
        return ()
    token = tokens[0]
    realized = tuple(FeatureContribution(
        item.feature, item.activation, item.coefficient, item.value,
        ("action.realized_portfolio", *item.provenance))
        for item in baseline.contributions if token in item.provenance)
    return realized


def _discard_spend_contributions(baseline, board, action, ctx=None):
    if (action.identity.kind != "card" or board.select is None
            or board.select.context != _DISCARD):
        return ()
    selected = _selected_cards(board, action)
    remaining = Counter(card.card_id for card in tuple(board.me.hand))
    for _serial, card_id in selected:
        if card_id is not None:
            remaining[card_id] -= 1
    sources = _portfolio_sources(board, action)
    tokens = {
        token for token, _serial, card_id in sources
        if card_id is None or remaining[card_id] <= 0}
    dead_tokens = set()
    if ctx is not None:
        from .worth import Demand, DemandState, _liveness

        demand = Demand.read(board.me, ctx, board.turn)
        dead_tokens = {
            token for token, _serial, card_id in sources
            if card_id is not None
            and _liveness(
                card_id, ctx.facts(card_id), demand, ctx, board.deck_counts)[0]
            is DemandState.DEAD}
    contributions = list(FeatureContribution(
        item.feature, -item.activation, item.coefficient, -item.value,
        ("action.discard_spend", *item.provenance))
        for item in baseline.contributions
        if item.value > 0 and tokens.intersection(item.provenance)
        and not dead_tokens.intersection(item.provenance))
    if ctx is not None:
        from .capabilities import card_option_units

        for token, _serial, card_id in sources:
            if token not in tokens or token in dead_tokens or card_id is None:
                continue
            units = card_option_units(
                ctx.facts(card_id), board.me, board.them, board, ctx)
            owned_features = {
                item.feature for item in baseline.contributions
                if token in item.provenance and item.feature.startswith("option.")}
            if owned_features:
                continue
            for feature, activation in units.activations():
                if not activation or feature == "option.cost":
                    continue
                coefficient = ctx.configuration[feature]
                spent_activation = -activation
                value = spent_activation * coefficient
                if value < 0:
                    contributions.append(FeatureContribution(
                        feature, spent_activation, coefficient, value,
                        ("action.discard_spend", token)))
    return tuple(contributions)


def _expected_valuation(weighted, ctx) -> Valuation:
    provenance = {}
    owned = {}
    gaps = []
    prize_maps = set()
    for probability, valuation in weighted:
        gaps.extend(valuation.gaps)
        prize_maps.add(valuation.prize_map)
        for item in valuation.activations:
            provenance.setdefault(item.feature, set()).update(item.provenance)
        for item in valuation.contributions:
            key = (item.feature, item.provenance)
            owned.setdefault(key, []).append(probability * item.activation)
    contributions = tuple(FeatureContribution(
        feature, activation, ctx.configuration[feature],
        activation * ctx.configuration[feature], owner)
        for (feature, owner), owner_values in sorted(owned.items())
        if (activation := math.fsum(owner_values)))
    activation_values = {}
    for item in contributions:
        activation_values.setdefault(item.feature, []).append(item.activation)
    activations = tuple(FeatureActivation(
        feature, math.fsum(feature_values), tuple(sorted(provenance[feature])))
        for feature, feature_values in sorted(activation_values.items())
        if math.fsum(feature_values))
    prize_map = next(iter(prize_maps)) if len(prize_maps) == 1 else None
    return Valuation(sum(item.value for item in contributions), (), tuple(gaps),
                     activations, contributions, prize_map)


def _successor_result(probability, board, ended, valuation_fn,
                      state_valuation_fn, start_position_key, path, *,
                      precomputed_valuation=None) -> SuccessorResult:
    valuation = (state_valuation_from_ledger(
        board, valuation_fn(board) if precomputed_valuation is None
        else precomputed_valuation)
                 if state_valuation_fn is None else state_valuation_fn(board))
    trace = TransitionTrace(1, start_position_key, tuple(path), board.position_key)
    return SuccessorResult(
        probability, valuation, ended, board, trace, tuple(path), valuation.status,
        "; ".join(valuation.gaps) if valuation.status is EvaluationStatus.UNAVAILABLE else None,
    )


__all__ = ("ContinuationFootprint", "OptionPrice", "price_actions")
