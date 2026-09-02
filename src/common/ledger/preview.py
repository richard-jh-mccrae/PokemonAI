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
from common.cards.card_facts import SUPPORTER, EnergyCard, PokemonCard, TrainerCard
from common.decision import (ContinuationOpportunity, EvaluationStatus, OpportunityRef,
                             RealizedOutcome, SearchConfiguration, SuccessorResult)
from common.observation import ObservationState, ObservationStateBuilder, TransitionTrace
from common.strategy.context import (_ACTIVE, _BENCH, _DAMAGE, _DAMAGE_COUNTER_ANY, _DECK,
                                     _DISCARD, _EVOLVE, _HAND, _LOOKING, _MAIN, _PLAY,
                                     _ATTACH_FROM, _ATTACH_TO, _TO_BENCH, _TO_HAND)

from .activation import ActivationCompiler, ActivationEnvironment
from .capabilities import (DAMAGE_COUNTER_HP, DAMAGE_UNIT_HP, attack_damage,
                           best_energy_marginal, body_capability,
                           creates_lethal_damage_boost,
                           hand_dependency_reach_units, knockout_exposure_units)
from .chance import RefreshSummary, refresh_outcomes
from .decision import state_valuation_from_ledger
from .evaluate import (_active_doomed, FeatureActivation, FeatureContribution,
                       Valuation, evaluate)
from .prizes import PrizeMap
from .worth import EvaluationModel, any_attack_payable

LOTTERY_DIGEST_BYTES = 8
PRIZE_AREA = 6
FORCED_FOOTPRINT_SLOT = 3
CONSUMED_OPPORTUNITY_INDEX = 2
BODY_SOURCE_PREFIX_GROUP = 1
EVOLUTION_SOURCE_CARD_GROUP = 2
OPPORTUNITY_SOURCE_KIND_GROUP = 2
OPPORTUNITY_SOURCE_CARD_GROUP = 3


@dataclass(frozen=True)
class ContinuationFootprint:
    state_delta: float
    action_opportunity: float
    continues_turn: bool
    zones_created: tuple[str, ...] = ()
    zones_replaced: tuple[str, ...] = ()
    allowances_consumed: tuple[str, ...] = ()
    immediately_usable_outputs: tuple[str, ...] = ()
    opportunities_created: tuple[OpportunityRef, ...] = ()
    opportunities_preserved: tuple[OpportunityRef, ...] = ()
    opportunities_consumed: tuple[OpportunityRef, ...] = ()
    activations: tuple[FeatureActivation, ...] = ()
    contributions: tuple[FeatureContribution, ...] = ()
    policy_contributions: tuple[FeatureContribution, ...] = ()
    realized_outcomes: tuple[RealizedOutcome, ...] = ()
    executed_opportunity: OpportunityRef | None = None


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
    opportunities_created: tuple[OpportunityRef, ...] = ()
    opportunities_preserved: tuple[OpportunityRef, ...] = ()
    opportunities_consumed: tuple[OpportunityRef, ...] = ()
    activations: tuple[tuple[str, float], ...] = ()
    executed_opportunity: OpportunityRef | None = None


def price_actions(state, board: ObservationState, baseline: float, provider,
                  ctx: EvaluationModel, compute=None, budget=None,
                  valuation_fn=None, state_valuation_fn=None) -> tuple[OptionPrice, ...]:
    compute = SearchConfiguration() if compute is None else getattr(compute, "search", compute)
    valuation_fn = ((lambda value: evaluate(value, ctx))
                    if valuation_fn is None else valuation_fn)
    prices = []
    baseline_valuation = valuation_fn(board)
    original_actions = tuple(provider.actions(state))
    if (budget is not None
            and (budget.stop_reason != "complete"
                 or (hasattr(budget, "check") and budget.check()))):
        for action in original_actions:
            budget.frontier.append(action.identity)
            prices.append(OptionPrice(
                action, 0.0, False,
                (f"search stopped: {budget.stop_reason}",),
                ContinuationFootprint(0.0, 0.0, False),
                status=EvaluationStatus.UNAVAILABLE,
                prize_map=baseline_valuation.prize_map))
        return tuple(prices)
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
                activations=activations, contributions=state_contributions,
                realized_outcomes=(RealizedOutcome.EXPLICIT_TURN_END,))
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
                status=EvaluationStatus.UNAVAILABLE,
                prize_map=baseline_valuation.prize_map))
            continue
        walk = _Walk(
            provider, ctx, board.decklist, compute, budget, valuation_fn)
        node = provider.transition(state, action)
        _information_value, information_capped = _immediate_information_value(
            node, compute.path_node_budget)
        if information_capped:
            walk.gaps.append("information branches capped")
        successor, end_probability, landings = walk.node(
            state, board, node, compute.depth_budget)
        landings = _coalesce_landings(landings)
        local_action_contribution = _event_contributions(
            "action", _local_action_events(board, action, ctx, landings),
            ctx, "action")
        ends_turn = end_probability >= 1.0
        state_delta = successor.total - baseline_valuation.total
        activation = -(1.0 - end_probability)
        action_events = [("continued_action", activation)]
        action_contribution = _event_contributions(
            "continuation", action_events, ctx, "continuation")
        state_contributions = _state_contributions(
            baseline_valuation, successor, ctx)
        realization_contributions = _realized_portfolio_contributions(
            baseline_valuation, board, action, ctx)
        discard_contributions = (
            *_discard_spend_contributions(
                baseline_valuation, board, action, ctx, valuation_fn),
            *_compound_discard_spend_contributions(
                baseline_valuation, board, action, landings, ctx, valuation_fn),
            *_refresh_spend_contributions(
                baseline_valuation, board, action, node),
        )
        track_opportunities = not isinstance(node, (Chance, Refresh, RevealChoice))
        footprint_landings = landings
        footprint_values = _root_footprint(
            board, provider, state, action, footprint_landings, walk.gaps, ctx,
            track_opportunities=track_opportunities)
        footprint_values = _with_hand_evolution_opportunity(
            footprint_values, board, action, ctx)
        footprint_values = _with_lethal_attack_opportunity(
            footprint_values, board, action, ctx, landings)
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
                    *footprint_values.opportunities_consumed,
                    OpportunityRef("play"))), key=_opportunity_sort_key)))
        footprint_values = _with_portfolio_opportunity_losses(
            footprint_values, state_contributions, original_actions)
        footprint_contributions = _footprint_contributions(footprint_values, ctx)
        dependency_contributions = _dependency_reach_contributions(
            board, action, landings, ctx)
        if sum(item.value for item in dependency_contributions) > 0.0:
            footprint_values = replace(
                footprint_values,
                opportunities_created=tuple(sorted(set((
                    *footprint_values.opportunities_created,
                    OpportunityRef(ContinuationOpportunity.DEPENDENCY_REACH))),
                    key=_opportunity_sort_key)))
        policy_contributions = (
            *action_contribution, *local_action_contribution,
            *footprint_contributions,
            *realization_contributions, *discard_contributions,
            *dependency_contributions)
        opportunity_cost = sum(item.value for item in policy_contributions)
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
            footprint_values.opportunities_consumed, activations, contributions,
            executed_opportunity=footprint_values.executed_opportunity)
        footprint = replace(
            footprint,
            policy_contributions=policy_contributions,
            realized_outcomes=_realized_outcomes(
                board, action, landings, ctx, ends_turn=ends_turn))
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
            valuation, gaps, summary, landings = refresh_outcomes(
                _payload(state), board, node.card_id, node.draws, node.opponent_shuffles,
                self.valuation, self.compute, self.ctx)
            self.gaps.extend(gaps)
            self.chance_summaries.append(summary)
            if not summary.sample_count and summary.method == "sampled":
                self.unavailable = True
            return valuation, 0.0, landings
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
        if (board.select is not None and board.select.context == _TO_HAND
                and board.select.options
                and all(option.area == PRIZE_AREA for option in board.select.options)):
            actions = actions[:1]
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
            valuation, end_probability, landings = result
            local = sum(item.value for item in _event_contributions(
                "action", _local_action_events(
                    board, action, self.ctx, landings),
                self.ctx, "action"))
            footprint = _root_footprint(
                board, self.provider, state, action, landings, self.gaps,
                self.ctx,
                track_opportunities=True)
            opportunity = sum(item.value for item in _footprint_contributions(
                footprint, self.ctx))
            scored = (replace(
                valuation, total=valuation.total + local + opportunity),
                      end_probability, landings)
            entries.append((action.identity, result, scored, footprint))
        if not entries:
            return self.valuation(board), 0.0, ((1.0, state, board, False, ()),)
        purposeful = tuple(
            entry for entry in entries
            if entry[0].kind != "decline"
            and ("in_play" in entry[FORCED_FOOTPRINT_SLOT].immediately_usable_outputs
                 or bool(entry[FORCED_FOOTPRINT_SLOT].opportunities_created)))
        has_decline = any(entry[0].kind == "decline" for entry in entries)
        choice_entries = (purposeful if actor is Actor.OURS and has_decline and purposeful
                          else entries)
        identity, _scored = self._choose(
            ((identity, scored) for identity, _result, scored, _footprint in choice_entries),
            actor, salt=f"menu:{depth}")
        result = next(result for candidate, result, _scored, _footprint in entries
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


def _root_footprint(board: ObservationState, provider, state, action, landings, gaps, ctx,
                    *, track_opportunities: bool) -> _RawFootprint:
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

    def development_outputs(before_state, after_state):
        outputs = set()
        for before_body, after_body in zip(
                before_state.me.bodies, after_state.me.bodies):
            evolved = (
                before_body.card.card_id != after_body.card.card_id
                and any(card.card_id == before_body.card.card_id
                        for card in after_body.pre_evolution))
            if not evolved:
                continue
            outputs.add("in_play")
            if any_attack_payable(ctx.facts(after_body.card.card_id), after_body.energies):
                outputs.add("ready_attacker")
        return outputs

    labels = {name: set() for name in (
        "zones_created", "zones_replaced", "allowances_consumed",
        "immediately_usable_outputs", "opportunities_created",
        "opportunities_preserved", "opportunities_consumed")}
    activations = {claim: 0.0 for claim in (
        "zone_created", "zone_replaced", "allowance_consumed", "usable_output",
        "opportunity_created", "opportunity_preserved", "opportunity_consumed")}
    before = zones(board)
    before_actions = (_legal_inventory(provider, state, board, gaps)
                      if track_opportunities else Counter())
    executed_kind = _action_opportunity(action, board)
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
        branch_outputs.update(development_outputs(board, successor))
        after_actions = (Counter() if ended or not track_opportunities
                         else _legal_inventory(
                             provider, landing_state, successor, gaps,
                             report_missing=False))
        after_actions = _remap_body_sources(
            after_actions, board, successor)
        after_actions = _remap_evolution_sources(
            before_actions, after_actions, executed_kind, board, successor)
        branch_opportunities = ((Counter(), Counter(), Counter())
                                if ended or not track_opportunities or not after_actions else (
                                    after_actions - before_actions,
                                    after_actions & before_actions,
                                    before_actions - after_actions))
        if (not ended and track_opportunities
                and str(executed_kind) == "ability"):
            branch_opportunities[CONSUMED_OPPORTUNITY_INDEX][executed_kind] += 1
        branch_groups = (branch_created, branch_replaced, branch_allowances, branch_outputs,
                         *branch_opportunities)
        for label, feature, items in zip(labels, activations, branch_groups):
            labels[label].update(items)
            units = sum(items.values()) if isinstance(items, Counter) else len(items)
            activations[feature] += probability * units
    return _RawFootprint(
        *(tuple(sorted(labels[name], key=_opportunity_sort_key)) for name in labels),
        tuple((feature, value) for feature, value in activations.items() if value),
        executed_kind)


def _action_key(action) -> str:
    return str(action.identity.kind)


def _opportunity_sort_key(value):
    return str(value), getattr(value, "source", None) or ""


def _action_opportunity(action, board) -> OpportunityRef:
    source = None
    if board.select is not None:
        for index in action.selection:
            if not isinstance(index, int) or not 0 <= index < len(board.select.options):
                continue
            option = board.select.options[index]
            area = option.inPlayArea if option.inPlayArea is not None else option.area
            position = option.inPlayIndex if option.inPlayIndex is not None else option.index
            seat = board.seat if option.playerIndex in {None, board.seat} else 1 - board.seat
            if area in {_ACTIVE, _BENCH}:
                source = _body_opportunity_source(
                    board, seat, area, position, _action_key(action))
            if source is not None:
                break
    return OpportunityRef(_action_key(action), source)


def _body_opportunity_source(board, seat, area, position, kind):
    side = board.me if seat == board.seat else board.them
    target = (side.active if area == _ACTIVE else
              side.bench[position] if isinstance(position, int)
              and 0 <= position < len(side.bench) else None)
    if target is None:
        return None
    prefix = _body_source_prefix(side, seat, target)
    return f"{prefix}:{kind}:{target.card.card_id}"


def _remap_body_sources(after, board, successor):
    prefixes = {}
    for before_side, after_side, seat in (
            (board.me, successor.me, board.seat),
            (board.them, successor.them, 1 - board.seat)):
        before_by_serial = {
            body.card.serial: _body_source_prefix(before_side, seat, body)
            for body in before_side.bodies if body.card.serial is not None}
        for body in after_side.bodies:
            serial = body.card.serial
            if serial is None or serial not in before_by_serial:
                continue
            prefixes[_body_source_prefix(after_side, seat, body)] = before_by_serial[serial]
    remapped = Counter()
    for opportunity, count in after.items():
        match = re.fullmatch(
            r"(seat:\d+:body:\d+:\d+):([^:]+):(\d+)",
            opportunity.source or "")
        if match is None or match.group(BODY_SOURCE_PREFIX_GROUP) not in prefixes:
            remapped[opportunity] += count
            continue
        prefix = prefixes[match.group(BODY_SOURCE_PREFIX_GROUP)]
        kind = match.group(OPPORTUNITY_SOURCE_KIND_GROUP)
        card_id = match.group(OPPORTUNITY_SOURCE_CARD_GROUP)
        remapped[OpportunityRef(kind, f"{prefix}:{kind}:{card_id}")] += count
    return remapped


def _body_source_prefix(side, seat, target):
    card_id = target.card.card_id
    peers = [body for body in side.bodies if body.card.card_id == card_id]
    ordinal = next(index for index, body in enumerate(peers) if body is target)
    return f"seat:{seat}:body:{card_id}:{ordinal}"


def _remap_evolution_sources(before, after, executed, board, successor):
    if str(executed) != "evolve" or executed.source is None:
        return after
    match = re.fullmatch(
        r"(seat:\d+:body:(\d+):\d+):evolve:\d+", executed.source)
    if match is None:
        return after
    selected_prefix = match.group(BODY_SOURCE_PREFIX_GROUP)
    old_card_id = int(match.group(EVOLUTION_SOURCE_CARD_GROUP))
    before_counts = Counter(body.card.card_id for body in board.me.bodies)
    after_counts = Counter(body.card.card_id for body in successor.me.bodies)
    evolved_ids = {
        card_id for card_id, count in (after_counts - before_counts).items()
        if count > 0}
    available = {}
    for opportunity in sorted(before, key=_opportunity_sort_key):
        source_match = re.fullmatch(
            r"(seat:\d+:body:\d+:\d+):([^:]+):(\d+)",
            opportunity.source or "")
        if (source_match is None
                or int(source_match.group(OPPORTUNITY_SOURCE_CARD_GROUP)) != old_card_id
                or source_match.group(BODY_SOURCE_PREFIX_GROUP) == selected_prefix):
            continue
        available.setdefault(str(opportunity), []).extend(
            [source_match.group(BODY_SOURCE_PREFIX_GROUP)] * before[opportunity])
    remapped = Counter()
    for opportunity, count in sorted(after.items(), key=lambda item: _opportunity_sort_key(item[0])):
        source_match = re.fullmatch(
            r"(seat:\d+:body:\d+:\d+):([^:]+):(\d+)",
            opportunity.source or "")
        if source_match is None:
            remapped[opportunity] += count
            continue
        kind = source_match.group(OPPORTUNITY_SOURCE_KIND_GROUP)
        card_id = int(source_match.group(OPPORTUNITY_SOURCE_CARD_GROUP))
        for _copy in range(count):
            if card_id in evolved_ids:
                prefix = selected_prefix
            elif card_id == old_card_id and available.get(str(opportunity)):
                prefix = available[str(opportunity)].pop(0)
            else:
                remapped[opportunity] += 1
                continue
            remapped[OpportunityRef(kind, f"{prefix}:{kind}:{card_id}")] += 1
    return remapped


def _action_roster_key(action):
    return action.identity, tuple(action.selection)


def _with_hand_evolution_opportunity(footprint, board, action, ctx):
    if action.identity.kind != "play":
        return footprint
    selected = tuple(card_id for _serial, card_id in _selected_cards(board, action)
                     if card_id is not None)
    parent_names = {
        facts.name for card_id in selected
        if isinstance((facts := ctx.facts(card_id)), PokemonCard)
    }
    if not parent_names:
        return footprint
    held_child = any(
        isinstance((facts := ctx.facts(card.card_id)), PokemonCard)
        and facts.evolves_from in parent_names
        for card in board.me.hand
    )
    if not held_child or "future_evolve" in footprint.opportunities_created:
        return footprint
    activations = Counter(dict(footprint.activations))
    activations["opportunity_created"] += 1.0
    return replace(
        footprint,
        opportunities_created=tuple(sorted((
            *footprint.opportunities_created, OpportunityRef("future_evolve")),
            key=_opportunity_sort_key)),
        activations=tuple(activations.items()))


def _with_lethal_attack_opportunity(footprint, board, action, ctx, landings=()):
    attack_available = "attack" in {
        *footprint.opportunities_created, *footprint.opportunities_preserved}
    successor_winning = (
        attack_available
        and not _active_doomed(board.me, board.them, ctx, board)
        and bool(landings)
        and all(not ended and _attack_wins_game(successor, ctx)
                for _probability, _state, successor, ended, _path in landings))
    selected = tuple(
        ctx.facts(card_id) for _serial, card_id in _selected_cards(board, action)
        if card_id is not None)
    damage_boost_lethal = (
        action.identity.kind == "play"
        and "attack" in footprint.opportunities_preserved
        and any(creates_lethal_damage_boost(
            facts, board.me, board.them, board, ctx) for facts in selected))
    if not successor_winning and not damage_boost_lethal:
        return footprint
    opportunities = set(footprint.opportunities_created)
    if damage_boost_lethal:
        opportunities.add(OpportunityRef(ContinuationOpportunity.LETHAL_ATTACK))
    if successor_winning:
        opportunities.add(OpportunityRef(ContinuationOpportunity.WINNING_ATTACK))
    activations = Counter(dict(footprint.activations))
    activations["opportunity_created"] += (
        len(opportunities) - len(footprint.opportunities_created))
    return replace(
        footprint,
        opportunities_created=tuple(sorted(
            opportunities, key=_opportunity_sort_key)),
        activations=tuple(activations.items()))


def _attack_wins_game(board, ctx):
    if board.them.active is None or not _active_doomed(
            board.me, board.them, ctx, board):
        return False
    prizes = getattr(ctx.facts(board.them.active.card.card_id), "prize_value", 1)
    return prizes >= board.them.prize_count or not board.them.bench


def _local_action_events(board, action, ctx=None, landings=()):
    dead_discard = _dead_discard(board, action, ctx, landings)
    if dead_discard:
        return (("dead_discard", dead_discard),)
    dead_play = _dead_play(board, action, ctx)
    if dead_play:
        return (("dead_play", dead_play),)
    play_before_refresh = _play_before_refresh(board, action, ctx)
    if play_before_refresh:
        return (("play_before_refresh", play_before_refresh),)
    if ctx is not None and _spends_gust(board, action, ctx):
        return (("gust_spend", 1.0),)
    if ctx is not None and (opportunity := _ability_rider_energy_opportunity(
            board, action, ctx)):
        return (("rider_energy_opportunity", opportunity),)
    if ctx is not None and (exposure := _survival_tool_target(
            board, action, ctx)):
        return (("survival_tool_target", exposure),)
    if ctx is not None and (fit := _manual_attachment_target_fit(
            board, action, ctx)):
        return (("attachment_target_fit", fit),)
    if ctx is not None and _body_ability_bonus_applies(board, action, ctx):
        commitment = _evolution_target_commitment(board, action)
        if commitment:
            return (("body_ability_ready", 1.0),
                    ("evolution_target_commitment", commitment))
        return (("body_ability_ready", 1.0),)
    if commitment := _evolution_target_commitment(board, action):
        return (("evolution_target_commitment", commitment),)
    if ctx is not None and _duplicate_body_deployment(board, action, ctx):
        return (("duplicate_body_deployment", 1.0),)
    if ctx is not None and (overflow := _body_copy_overflow(board, action, ctx)):
        return (("body_copy_overflow", overflow),)
    if ctx is not None and _retreats_doomed_denial(board, action, ctx):
        return (("retreat_doomed_denial", 1.0),)
    select = board.select
    if ctx is not None and select is not None and select.context == _ATTACH_TO:
        selected_energy = sum(
            isinstance(ctx.facts(card_id), EnergyCard)
            for _serial, card_id in _selected_cards(board, action)
            if card_id is not None)
        if selected_energy:
            return (("acceleration_phase_fit",
                     selected_energy * ctx.configuration["option.acceleration"]),)
    if ctx is not None and select is not None and select.context == _ATTACH_FROM:
        return _acceleration_phase_events(board, action, ctx)
    if select is None or select.context not in {_DAMAGE, _DAMAGE_COUNTER_ANY}:
        return ()
    for selection in action.selection:
        if not 0 <= selection < len(select.options):
            continue
        option = select.options[selection]
        side = board.me if option.playerIndex in {None, board.seat} else board.them
        target = _option_body(board, option)
        if target is None:
            continue
        if target.hp <= 0:
            return (("overkill_counter", 1.0),)
        if ctx is not None:
            facts = ctx.facts(target.card.card_id)
            if (option.area == _BENCH and select.context == _DAMAGE
                    and getattr(facts, "tera", False)):
                return ()
            prize_value = int(getattr(facts, "prize_value", 1) or 1)
            opponent = board.them if side is board.me else board.me
            capability = body_capability(
                target, side, opponent, board, ctx,
                include_hand_attach=False)
            threat = max(capability.attack_now, capability.line_potential)
            progress = (min(DAMAGE_COUNTER_HP, target.hp)
                        / DAMAGE_COUNTER_HP
                        * math.sqrt(prize_value) * (1.0 + threat))
            return (("damage_counter_progress", progress),)
    return ()


def _duplicate_body_deployment(board, action, ctx):
    if action.identity.kind != "play":
        return False
    selected = _selected_cards(board, action)
    return len(selected) == 1 and any(
        card_id is not None
        and isinstance(ctx.facts(card_id), PokemonCard)
        and body.card.card_id == card_id
        for _serial, card_id in selected
        for body in board.me.bodies)


def _spends_gust(board, action, ctx):
    return action.identity.kind == "play" and any(
        clause.kind == "gust"
        for _serial, card_id in _selected_cards(board, action)
        if card_id is not None
        for clause in card_clauses(ctx.facts(card_id)))


def _ability_rider_energy_opportunity(board, action, ctx):
    if action.identity.kind != "ability":
        return 0.0
    body = _selected_body(board, action)
    if body is None:
        return 0.0
    facts = ctx.facts(body.card.card_id)
    energy_types = {
        clause.rider_energy_type
        for ability in getattr(facts, "abilities", ())
        for clause in ability.clauses
        if str(clause.rider or "").startswith("discard_basic_")
    }
    candidates = tuple(
        energy
        for card in board.me.hand
        if isinstance((energy := ctx.facts(card.card_id)), EnergyCard)
        and (None in energy_types or energy.provides in energy_types))
    return max((best_energy_marginal(
        energy, board.me, board.them, board, ctx) for energy in candidates), default=0.0)


def _survival_tool_target(board, action, ctx):
    if action.identity.kind != "attach":
        return 0.0
    if not any(
            clause.kind == "hp_bonus"
            for _serial, card_id in _selected_cards(board, action)
            if card_id is not None
            for clause in card_clauses(ctx.facts(card_id))):
        return 0.0
    target = _selected_body(board, action)
    if target is None or target is not board.me.active:
        return 0.0
    return knockout_exposure_units(target, ctx)


def _evolution_target_commitment(board, action):
    if action.identity.kind != "evolve":
        return 0.0
    target = _selected_body(board, action)
    return 0.0 if target is None else float(len(target.energies) + len(target.tools))


def _selected_body(board, action):
    if board.select is None or len(action.selection) != 1:
        return None
    selection = action.selection[0]
    if not 0 <= selection < len(board.select.options):
        return None
    return _option_body(board, board.select.options[selection])


def _option_body(board, option):
    area = option.inPlayArea if option.inPlayArea is not None else option.area
    index = option.inPlayIndex if option.inPlayIndex is not None else option.index
    side = board.me if option.playerIndex in {None, board.seat} else board.them
    if area == _ACTIVE:
        return side.active
    if area == _BENCH and isinstance(index, int) and 0 <= index < len(side.bench):
        return side.bench[index]
    return None


def _dead_discard(board, action, ctx, landings=()):
    if ctx is None or board.select is None or board.select.context != _DISCARD:
        return 0.0
    from .worth import Demand, DemandState, _liveness

    expendability = {
        DemandState.DEAD: 1.0,
        DemandState.COLORLESS_ONLY: 1.0,
    }
    cards = tuple(card_id for _serial, card_id in _selected_cards(board, action)
                  if card_id is not None)
    states = ((1.0, board),) if not landings else tuple(
        (probability, successor)
        for probability, _state, successor, _ended, _path in landings)
    return float(sum(
        probability * sum(
            expendability.get(_liveness(
                card_id, ctx.facts(card_id),
                Demand.read(successor.me, ctx, successor.turn), ctx,
                successor.deck_counts)[0], 0.0)
            for card_id in cards)
        for probability, successor in states))


def _dead_play(board, action, ctx):
    if ctx is None or action.identity.kind != "play":
        return 0.0
    from .worth import Demand, DemandState, _liveness

    demand = Demand.read(board.me, ctx, board.turn)
    dead = 0
    for _serial, card_id in _selected_cards(board, action):
        if card_id is None:
            continue
        facts = ctx.facts(card_id)
        state, _capacity = _liveness(
            card_id, facts, demand, ctx, board.deck_counts)
        dead += state is DemandState.DEAD or (
            isinstance(facts, TrainerCard) and facts.kind == SUPPORTER
            and state is not DemandState.LIVE)
    return float(dead)


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
                       if card_id is not None)
    owned = Counter(body.card.card_id for body in board.me.bodies)
    owned.update(card.card_id for card in board.me.hand)
    overflow = 0
    owned_names = Counter(
        facts.name for card_id in owned.elements()
        if (facts := ctx.facts(card_id)) is not None)
    in_play_names = Counter(
        facts.name for body in board.me.bodies
        if (facts := ctx.facts(body.card.card_id)) is not None)
    for card_id, count in selected.items():
        facts = ctx.facts(card_id)
        capacity = pokemon_copy_capacity(facts)
        if capacity is None:
            continue
        if (isinstance(facts, PokemonCard) and facts.evolves_from
                and not owned_names[facts.evolves_from]):
            capacity = min(capacity, 1)
        if (isinstance(facts, PokemonCard) and in_play_names[facts.name]
                and any(in_play_names[name] for name in facts.synergy)):
            capacity = min(capacity, in_play_names[facts.name])
        overflow += max(0, owned[card_id] + count - capacity)
    return overflow


def _option_card_id(board, option):
    if option.cardId is not None:
        return option.cardId
    card = _option_card(board, option)
    return None if card is None else card.card_id


def _option_card(board, option):
    if option.serial is not None or not isinstance(option.index, int):
        return None
    sources = {
        _DECK: board.select.deck,
        _HAND: tuple(board.me.hand),
        _LOOKING: None if board.looking is None else board.looking.cards,
        None: tuple(board.me.hand),
    }
    cards = sources.get(option.area)
    if cards is not None and 0 <= option.index < len(cards):
        return cards[option.index]
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


def _body_ability_bonus_applies(board, action, ctx):
    if not _body_ability_ready(board, action, ctx):
        return False
    active = board.me.active
    if active is None or action.identity.kind != "card":
        return True
    prize_value = int(getattr(ctx.facts(active.card.card_id), "prize_value", 1) or 1)
    return not (
        board.them.prize_count - prize_value <= 1
        and _active_doomed(board.them, board.me, ctx, board))


def _acceleration_phase_events(board, action, ctx):
    context_card = board.select.context_card
    energy = None if context_card is None else ctx.facts(context_card.card_id)
    if not isinstance(energy, EnergyCard):
        return ()
    reach = _attachment_line_reach(board, ctx)
    values = []
    for selection in action.selection:
        if not 0 <= selection < len(board.select.options):
            continue
        option = board.select.options[selection]
        body = _option_body(board, option)
        if body is None:
            continue
        side = board.me if option.playerIndex in {None, board.seat} else board.them
        opponent = board.them if side is board.me else board.me
        values.append(_attachment_target_fit(
            board, body, energy, side, opponent, ctx, reach))
    return (("acceleration_phase_fit", sum(values)),) if values else ()


def _manual_attachment_target_fit(board, action, ctx):
    if action.identity.kind != "attach":
        return 0.0
    target = _selected_body(board, action)
    energy = next((
        facts for _serial, card_id in _selected_cards(board, action)
        if card_id is not None
        and isinstance((facts := ctx.facts(card_id)), EnergyCard)), None)
    if target is None or energy is None:
        return 0.0
    reach = _attachment_line_reach(board, ctx)
    selected = _attachment_target_fit(
        board, target, energy, board.me, board.them, ctx, reach)
    best = max(
        _attachment_target_fit(
            board, body, energy, board.me, board.them, ctx, reach)
        for body in board.me.bodies)
    return selected - best


def _attachment_line_reach(board, ctx):
    from .worth import line_reach

    hand_names = Counter(
        facts.name for card in tuple(board.me.hand)
        if (facts := ctx.facts(card.card_id)) is not None)
    return line_reach(
        hand_names, board.deck_counts, ctx, hand=board.me.hand, turn=board.turn)


def _attachment_target_fit(board, body, energy, side, opponent, ctx, reach):
    from .capabilities import energy_marginal
    from .worth import Reach, legal_line_reach

    facts = ctx.facts(body.card.card_id)
    body_reach = legal_line_reach(
        body, reach, ctx, board.me.hand, board.turn)
    line = (facts, *(ctx.facts(card_id) for card_id, status in body_reach.items()
                     if status is not Reach.ABSENT))
    route_prizes = max((int(getattr(card, "prize_value", 1) or 1)
                        for card in line if card is not None), default=1)
    damage_per_energy = max((
        float(attack.damage or attack.damage_fix or attack.damage_max or 0)
        / DAMAGE_UNIT_HP / max(1, len(attack.cost))
        for card in line if card is not None for attack in card.attacks), default=0.0)
    typed_route = any(
        energy.provides in attack.cost
        for card in line if card is not None for attack in card.attacks)
    route_fit = damage_per_energy if typed_route else 0.0
    marginal = energy_marginal(
        body, energy, side, opponent, board, ctx, reach=body_reach)
    return route_prizes * marginal + route_fit


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


def _legal_inventory(provider, state, board, gaps, *, report_missing=True) -> Counter:
    try:
        return Counter(
            _action_opportunity(action, board) for action in provider.actions(state))
    except (KeyError, LookupError) as exc:
        if report_missing:
            gaps.append(f"continuation action inventory unavailable: {type(exc).__name__}")
        return Counter()


def _footprint_contributions(values, ctx):
    return _event_contributions(
        "continuation", values.activations, ctx, "continuation.footprint")


def _dependency_reach_contributions(board, action, landings, ctx):
    delta = Counter()
    root_sources = _portfolio_sources(board, action)
    for probability, _state, successor, _ended, _path in landings:
        committed = _without_hand_sources(board, (
            *root_sources, *_forced_hand_discard_sources(
                board, action, successor)))
        before = dict(hand_dependency_reach_units(
            committed.me, committed.them, committed, ctx).activations())
        after = dict(hand_dependency_reach_units(
            successor.me, successor.them, successor, ctx)
                     .activations())
        for feature in set(before) | set(after):
            delta[feature] += probability * (
                after.get(feature, 0.0) - before.get(feature, 0.0))
    contributions = []
    for feature, activation in sorted(delta.items()):
        if not activation:
            continue
        coefficient = ctx.configuration[feature]
        contributions.append(FeatureContribution(
            feature, activation, coefficient, activation * coefficient,
            ("continuation.dependency_reach",)))
    return (tuple(contributions)
            if sum(item.value for item in contributions) > 0.0 else ())


def _selected_attack_is_lethal(board, action, ctx):
    if (action.identity.kind != "attack" or len(action.selection) != 1
            or board.select is None or board.me.active is None
            or board.them.active is None):
        return False
    selection = action.selection[0]
    if not 0 <= selection < len(board.select.options):
        return False
    attack_id = board.select.options[selection].attackId
    attacker_facts = ctx.facts(board.me.active.card.card_id)
    defender_facts = ctx.facts(board.them.active.card.card_id)
    if not isinstance(attacker_facts, PokemonCard):
        return False
    attack = next((candidate for candidate in attacker_facts.attacks
                   if candidate.attack_id == attack_id), None)
    if attack is None:
        return False
    return attack_damage(
        attack, attacker_facts, defender_facts, board.me.active,
        board.me, board.them, ctx, board,
        include_held_modifiers=False) >= board.them.active.hp


def _realized_outcomes(board, action, landings, ctx, *, ends_turn=False):
    active = board.them.active
    if active is None:
        return ()
    active_serial = active.card.serial
    lethal_without_serial = (
        active_serial is None and _selected_attack_is_lethal(board, action, ctx))
    knockout_probability = 0.0
    body_knockout_probability = 0.0
    win_probability = 0.0
    original_serials = {
        body.card.serial for body in (board.them.active, *board.them.bench)
        if body is not None and body.card.serial is not None}
    for probability, _state, successor, _ended, _path in landings:
        result = successor.turn.result
        if (isinstance(result, int) and not isinstance(result, bool)
                and result >= 0 and result == board.seat):
            win_probability += probability
        if successor.me.prize_count >= board.me.prize_count:
            continue
        bodies = tuple(body for body in (successor.them.active, *successor.them.bench)
                       if body is not None)
        surviving_serials = {
            body.card.serial for body in bodies
            if body.card.serial is not None and body.hp > 0}
        if active_serial is None:
            if lethal_without_serial:
                knockout_probability += probability
            elif original_serials - surviving_serials:
                body_knockout_probability += probability
            continue
        original = next((body for body in bodies
                         if body.card.serial == active_serial), None)
        if original is None or original.hp <= 0:
            knockout_probability += probability
        elif original_serials - surviving_serials:
            body_knockout_probability += probability
    outcomes = (() if not math.isclose(knockout_probability, 1.0) else
                (RealizedOutcome.OPPONENT_ACTIVE_KNOCKOUT,))
    if not outcomes and math.isclose(body_knockout_probability, 1.0):
        outcomes = (RealizedOutcome.OPPONENT_BODY_KNOCKOUT,)
    if math.isclose(win_probability, 1.0):
        outcomes = (*outcomes, RealizedOutcome.GAME_WIN)
    if ends_turn:
        outcomes = (*outcomes, RealizedOutcome.ACTION_ENDED_TURN)
    return outcomes


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
        values, opportunities_consumed=tuple(sorted(
            consumed, key=_opportunity_sort_key)),
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
        card = _option_card(board, option)
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


def _realized_portfolio_contributions(baseline, board, action, ctx=None):
    if action.identity.kind not in {"play", "attach", "evolve"} or board.select is None:
        return ()
    tokens = _portfolio_tokens(board, action)
    if len(tokens) != 1:
        return ()
    token = tokens[0]
    selected = tuple(card_id for _serial, card_id in _selected_cards(board, action)
                     if card_id is not None)
    recovery = bool(ctx is not None and len(selected) == 1 and any(
        clause.kind in {"fetch", "energy_recur"}
        and (clause.zone or clause.source) == "discard"
        for clause in card_clauses(ctx.facts(selected[0]))))
    marker = (("action.recovery",) if recovery else ())
    realized = tuple(FeatureContribution(
        item.feature, item.activation, item.coefficient, item.value,
        ("action.realized_portfolio", *marker, *item.provenance))
        for item in baseline.contributions if token in item.provenance)
    if realized or ctx is None:
        return realized
    from .capabilities import card_option_units

    if len(selected) != 1:
        return ()
    selected_facts = ctx.facts(selected[0])
    if not any(clause.cost for clause in card_clauses(selected_facts)):
        return ()
    units = card_option_units(
        selected_facts, board.me, board.them, board, ctx)
    return tuple(
        FeatureContribution(
            feature, activation, ctx.configuration[feature],
            activation * ctx.configuration[feature],
            ("action.realized_portfolio", *marker, token))
        for feature, activation in units.activations()
        if activation and activation * ctx.configuration[feature] > 0)


def _discard_spend_contributions(
        baseline, board, action, ctx=None, valuation_fn=None):
    if (action.identity.kind != "card" or board.select is None
            or board.select.context != _DISCARD):
        return ()
    sources = _portfolio_sources(board, action)
    return _discard_source_contributions(
        baseline, board, sources, ctx, valuation_fn)


def _discard_source_contributions(
        baseline, board, sources, ctx=None, valuation_fn=None):
    if ctx is None:
        return ()

    counterfactual = _without_hand_sources(board, sources)
    value = (evaluate(counterfactual, ctx)
             if valuation_fn is None else valuation_fn(counterfactual))
    exact = tuple(replace(
        item, provenance=("action.discard_spend",))
        for item in _state_contributions(baseline, value, ctx)
        if item.feature.startswith("option.") and item.value < 0.0)
    return exact


def _without_hand_sources(board, sources):
    from common.observation.nodes import card_bag

    serials = Counter(
        serial for _token, serial, _card_id in sources if serial is not None)
    card_ids = Counter(
        card_id for _token, serial, card_id in sources
        if serial is None and card_id is not None)
    remaining = []
    for card in tuple(board.me.hand):
        if card.serial is not None and serials[card.serial] > 0:
            serials[card.serial] -= 1
            continue
        if card_ids[card.card_id] > 0:
            card_ids[card.card_id] -= 1
            continue
        remaining.append(card)
    hand = replace(board.me.hand, bag=card_bag({
        "id": card.card_id, "serial": card.serial, "playerIndex": card.owner,
    } for card in remaining))
    return replace(
        board,
        me=replace(board.me, hand=hand, hand_count=len(remaining)),
    )


def _compound_discard_spend_contributions(
        baseline, board, action, landings, ctx, valuation_fn=None):
    committed = _without_hand_sources(board, _portfolio_sources(board, action))
    committed_value = (evaluate(committed, ctx)
                       if valuation_fn is None else valuation_fn(committed))
    contributions = []
    for probability, _state, successor, _ended, _path in landings:
        sources = _forced_hand_discard_sources(board, action, successor)
        for item in _discard_source_contributions(
                committed_value, committed, tuple(sources), ctx, valuation_fn):
            contributions.append(replace(
                item,
                activation=probability * item.activation,
                value=probability * item.value,
                provenance=("action.compound_discard_spend", *item.provenance),
            ))
    return tuple(contributions)


def _forced_hand_discard_sources(board, action, successor):
    before_discard = Counter(
        _card_instance_key(card.serial, card.card_id) for card in board.me.discard)
    root_spend = Counter(
        _card_instance_key(serial, card_id)
        for serial, card_id in _selected_cards(board, action)
        if serial is not None or card_id is not None)
    newly_discarded = Counter(
        _card_instance_key(card.serial, card.card_id)
        for card in successor.me.discard) - before_discard
    newly_discarded.subtract(root_spend)
    hand = {}
    for card in board.me.hand:
        hand.setdefault(_card_instance_key(card.serial, card.card_id), []).append(card)
    sources = []
    for key, count in newly_discarded.items():
        if count <= 0:
            continue
        for card in hand.get(key, ())[:count]:
            token = (f"feasible_option_portfolio:serial:{card.serial}"
                     if card.serial is not None
                     else f"feasible_option_portfolio:card:{card.card_id}")
            sources.append((token, card.serial, card.card_id))
    return tuple(sources)


def _refresh_spend_contributions(baseline, board, action, node):
    if not isinstance(node, Refresh):
        return ()
    played = set(_portfolio_tokens(board, action))
    shuffled = {
        (f"feasible_option_portfolio:serial:{card.serial}"
         if card.serial is not None
         else f"feasible_option_portfolio:card:{card.card_id}")
        for card in tuple(board.me.hand)
    } - played
    return tuple(FeatureContribution(
        item.feature, -item.activation, item.coefficient, -item.value,
        ("action.refresh_spend", *item.provenance))
        for item in baseline.contributions
        if item.value > 0 and shuffled.intersection(item.provenance))


def _card_instance_key(serial, card_id):
    return ("serial", serial) if serial is not None else ("card", card_id)


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
            provenance.setdefault(item.feature, set()).update(item.provenance)
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
