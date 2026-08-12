"""Deterministic exhaustive Bellman reference solver."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

from .algebra import (
    ActionDiagnostic, Actor, Chance, Choice, Deterministic, Ledger, RootDiagnostics, Terminal, Unknown,
)
from .api import ActionIdentity, RootDecision
from .options import LegalAction
from .state import DecisionState
from .value import ValueOracle


REFERENCE_MAX_NODES = 100_000
PRODUCTION_MAX_NODES = 4_000
PRODUCTION_BEAM_WIDTH = 4
PRODUCTION_PREVIEW_CAP_PER_ACTION = 300
VALUE_TIE_DECIMALS = 12
IMMEDIATE_VALUE_BEAM_SLOTS = 1
RANKED_ACTION_SLOT = 2


class TransitionProvider(Protocol):
    def actions(self, state: DecisionState) -> tuple[LegalAction, ...]:
        ...

    def transition(self, state: DecisionState, action: LegalAction):
        ...

    def actor(self, state: DecisionState) -> Actor:
        ...


@dataclass(frozen=True)
class SearchLimits:
    max_nodes: int = REFERENCE_MAX_NODES


@dataclass(frozen=True)
class ProductionLimits:
    max_nodes: int = PRODUCTION_MAX_NODES
    beam_width: int = PRODUCTION_BEAM_WIDTH
    max_preview_per_action: int = PRODUCTION_PREVIEW_CAP_PER_ACTION


@dataclass(frozen=True)
class Evaluation:
    value: float
    ledger: Ledger
    complete: bool
    reason: str = ""
    branches: tuple[dict, ...] = ()


@dataclass(frozen=True)
class StateEvaluation:
    value: float
    action: LegalAction | None
    evaluation: Evaluation
    alternatives: tuple[tuple[LegalAction, Evaluation], ...]


def _combine(base: Ledger, continuation: float, extra: Ledger = Ledger()) -> Ledger:
    return Ledger(base.benefits + extra.benefits, base.costs + extra.costs,
                  base.continuation + extra.immediate + float(continuation))


def _ordered_value(value: float) -> float:
    """Suppress floating-association noise before deterministic stable-order tie breaking."""
    return round(value, VALUE_TIE_DECIMALS) if math.isfinite(value) else value


class ReferenceSolver:
    """Exact within explicit caps; unknown/cap/cycle states are incomplete, never fabricated zeroes."""

    def __init__(self, provider: TransitionProvider, oracle: ValueOracle,
                 *, model_factory=None, limits: SearchLimits = SearchLimits()):
        self.provider = provider
        self.oracle = oracle
        self.model_factory = model_factory
        self.limits = limits
        self._memo: dict[str, StateEvaluation] = {}
        self._active: set[str] = set()
        self.nodes = 0
        self.cache_hits = 0

    def decide(self, state: DecisionState) -> RootDecision:
        self._memo.clear()
        self._active.clear()
        self.nodes = self.cache_hits = 0
        solved = self._state(state)
        if solved.action is None:
            raise RuntimeError(f"Bellman root has no complete legal action: {solved.evaluation.reason}")
        end_pair = next(((action, result) for action, result in solved.alternatives
                         if action.identity.kind == "end"), None)
        if solved.action.identity.kind == "end":
            end_eval = solved.evaluation
        elif end_pair is not None:
            end_eval = end_pair[1]
        else:
            end_eval = Evaluation(0.0, Ledger(), True)
        alternatives = tuple(
            ActionDiagnostic(str(action.identity), result.ledger, result.complete, result.reason,
                             result.branches)
            for action, result in solved.alternatives if action != solved.action)
        diagnostics = RootDiagnostics(
            chosen_key=str(solved.action.identity),
            end=ActionDiagnostic("end", end_eval.ledger, end_eval.complete, end_eval.reason,
                                 end_eval.branches),
            alternatives=alternatives, nodes=self.nodes, cache_hits=self.cache_hits,
            stopped_reason=solved.evaluation.reason or "optimal_complete_line",
        )
        return RootDecision(
            chosen=solved.action.selection, action=solved.action.identity,
            value=solved.value, complete=solved.evaluation.complete,
            diagnostics={"root": diagnostics, "ledger": solved.evaluation.ledger.as_dict()},
        )

    def _models(self, before: DecisionState, after: DecisionState):
        if self.model_factory is None:
            return None, None
        return self.model_factory(before), self.model_factory(after)

    def _ledger(self, before: DecisionState, after: DecisionState, action: LegalAction) -> Ledger:
        left, right = self._models(before, after)
        return self.oracle.transition_ledger(before, after, action.identity,
                                             before_model=left, after_model=right)

    def _state(self, state: DecisionState) -> StateEvaluation:
        key = state.semantic_key
        if key in self._memo:
            self.cache_hits += 1
            return self._memo[key]
        if key in self._active:
            incomplete = Evaluation(-math.inf, Ledger(), False, "semantic cycle")
            return StateEvaluation(-math.inf, None, incomplete, ())
        if self.nodes >= self.limits.max_nodes:
            incomplete = Evaluation(-math.inf, Ledger(), False, "reference cap")
            return StateEvaluation(-math.inf, None, incomplete, ())
        self.nodes += 1
        self._active.add(key)
        actions = tuple(sorted(self.provider.actions(state), key=lambda action: action.identity))
        results = tuple((action, self._action(state, action)) for action in actions)
        self._active.remove(key)
        complete = [(action, result) for action, result in results if result.complete]
        if not complete:
            answer = StateEvaluation(-math.inf, None,
                                     Evaluation(-math.inf, Ledger(), False,
                                                "all legal actions incomplete"), results)
        else:
            actor = (self.provider.actor(state) if hasattr(self.provider, "actor") else Actor.OURS)
            chooser = max if actor is Actor.OURS else min
            action, result = chooser(complete, key=lambda pair: _ordered_value(pair[1].value))
            answer = StateEvaluation(result.value, action, result, results)
        self._memo[key] = answer
        return answer

    def _action(self, state: DecisionState, action: LegalAction) -> Evaluation:
        if action.identity.kind == "end":
            return Evaluation(0.0, Ledger(), True, "End exact zero")
        return self._transition(state, action, self.provider.transition(state, action))

    def _transition(self, before: DecisionState, action: LegalAction, node) -> Evaluation:
        if isinstance(node, Unknown):
            return Evaluation(-math.inf, Ledger(), False,
                              f"{node.reason}: {node.missing_fact}")
        if isinstance(node, Deterministic):
            base = self._ledger(before, node.state, action)
            continuation = self._state(node.state)
            if continuation.action is None and not continuation.evaluation.complete:
                return Evaluation(-math.inf, base, False, continuation.evaluation.reason)
            ledger = _combine(base, continuation.value)
            return Evaluation(ledger.total, ledger, continuation.evaluation.complete,
                              continuation.evaluation.reason)
        if isinstance(node, Terminal):
            base = self._ledger(before, node.state, action)
            ledger = _combine(base, 0.0, node.ledger)
            return Evaluation(ledger.total, ledger, True, node.result)
        if isinstance(node, Choice):
            branches = [(edge, self._transition(before, action, edge.node))
                        for edge in node.children]
            complete = [(edge, result) for edge, result in branches if result.complete]
            if len(complete) != len(branches) or not complete:
                return Evaluation(-math.inf, Ledger(), False, "incomplete choice branch",
                                  tuple({"label": edge.label, "complete": result.complete,
                                         "value": result.value, "reason": result.reason}
                                        for edge, result in branches))
            chooser = max if node.actor is Actor.OURS else min
            edge, result = chooser(complete, key=lambda pair: _ordered_value(pair[1].value))
            return Evaluation(result.value, result.ledger, True,
                              f"{node.actor.value} chose {edge.label}",
                              tuple({"label": child.label, "value": evaluated.value,
                                     "complete": evaluated.complete}
                                    for child, evaluated in branches))
        if isinstance(node, Chance):
            branches = [(edge, self._transition(before, action, edge.node))
                        for edge in node.children]
            if any(not result.complete for _edge, result in branches):
                return Evaluation(-math.inf, Ledger(), False, "incomplete chance branch")
            value = sum(edge.probability * result.value for edge, result in branches)
            benefits: dict[str, float] = {}
            costs: dict[str, float] = {}
            continuation = 0.0
            for edge, result in branches:
                for key, amount in result.ledger.benefits:
                    benefits[key] = benefits.get(key, 0.0) + edge.probability * amount
                for key, amount in result.ledger.costs:
                    costs[key] = costs.get(key, 0.0) + edge.probability * amount
                continuation += edge.probability * result.ledger.continuation
            ledger = Ledger(tuple(sorted(benefits.items())), tuple(sorted(costs.items())), continuation)
            return Evaluation(value, ledger, True, "expected value",
                              tuple({"label": edge.label, "probability": edge.probability,
                                     "value": result.value}
                                    for edge, result in branches))
        return Evaluation(-math.inf, Ledger(), False, "undeclared transition result")


class ProductionSolver(ReferenceSolver):
    """Bounded search over the reference transition/value contracts.

    Preview recursion has no depth horizon.  Width and expanded-state budgets are the only search
    bounds.  A cap is a real End choice when End is reachable; a mandatory nested menu remains
    incomplete and can never inherit fabricated zero value.
    """

    def __init__(self, provider: TransitionProvider, oracle: ValueOracle, *, model_factory=None,
                 limits: ProductionLimits = ProductionLimits()):
        super().__init__(provider, oracle, model_factory=model_factory,
                         limits=SearchLimits(limits.max_nodes))
        self.production_limits = limits
        self.previewed = 0
        self.pruned = 0
        self._preview_cache: dict[tuple[str, str], float] = {}
        self._root_previews: dict[str, float] = {}
        self._preview_remaining = limits.max_preview_per_action
        self.preview_caps = 0
        self._root_key = ""

    def decide(self, state: DecisionState) -> RootDecision:
        self.previewed = self.pruned = self.preview_caps = 0
        self._root_key = state.semantic_key
        self._preview_cache.clear()
        self._root_previews.clear()
        decision = super().decide(state)
        diagnostics = dict(decision.diagnostics)
        diagnostics["production"] = {
            "beam_width": self.production_limits.beam_width,
            "max_nodes": self.production_limits.max_nodes,
            "max_preview_per_action": self.production_limits.max_preview_per_action,
            "previewed": self.previewed,
            "pruned": self.pruned,
            "cap_reached": self.nodes >= self.production_limits.max_nodes,
            "root_previews": dict(sorted(self._root_previews.items())),
            "preview_caps": self.preview_caps,
        }
        return RootDecision(decision.chosen, decision.action, decision.value,
                            decision.complete, diagnostics)

    def _preview_state(self, state: DecisionState, *, seen: frozenset[str]) -> float:
        if state.semantic_key in seen:
            return -math.inf
        actions = tuple(sorted(self.provider.actions(state), key=lambda action: action.identity))
        if self.provider.actor(state) is Actor.OURS and len(actions) > 1:
            ranked = []
            for action in actions:
                if action.identity.kind == "end":
                    ranked.append((0.0, action, None))
                    continue
                node = self.provider.transition(state, action)
                ranked.append((self._immediate_transition(state, action, node), action, node))
            end = [row for row in ranked if row[1].identity.kind == "end"]
            non_end = sorted(
                (row for row in ranked if row[1].identity.kind != "end"),
                key=lambda row: _ordered_value(row[0]), reverse=True)
            kept = (*non_end[:self.production_limits.beam_width], *end)
            values = [self._preview_node_action(
                state, action, node, seen=seen | {state.semantic_key})
                for _value, action, node in kept]
        else:
            values = [self._preview_action(state, action, seen=seen | {state.semantic_key})
                      for action in actions]
        finite = [value for value in values if math.isfinite(value)]
        if not finite:
            return -math.inf
        actor = self.provider.actor(state)
        if actor is Actor.OPPONENT and len(finite) != len(values):
            return -math.inf
        return (max if actor is Actor.OURS else min)(finite)

    def _preview_action(self, state: DecisionState, action: LegalAction,
                        *, seen: frozenset[str]) -> float:
        if action.identity.kind == "end":
            return 0.0
        return self._preview_node_action(
            state, action, self.provider.transition(state, action), seen=seen)

    def _preview_node_action(self, state: DecisionState, action: LegalAction, node,
                             *, seen: frozenset[str]) -> float:
        if action.identity.kind == "end":
            return 0.0
        key = (state.semantic_key, str(action.identity))
        if key in self._preview_cache:
            return self._preview_cache[key]
        if self._preview_remaining <= 0:
            self.preview_caps += 1
            return -math.inf
        self._preview_remaining -= 1
        self.previewed += 1
        value = self._preview_transition(state, action, node, seen=seen)
        if math.isfinite(value):
            self._preview_cache[key] = value
        return value

    def _preview_transition(self, before: DecisionState, action: LegalAction, node,
                            *, seen: frozenset[str]) -> float:
        if isinstance(node, Unknown):
            return -math.inf
        if isinstance(node, Terminal):
            return _combine(self._ledger(before, node.state, action), 0.0, node.ledger).total
        if isinstance(node, Deterministic):
            base = self._ledger(before, node.state, action).immediate
            continuation = self._preview_state(node.state, seen=seen)
            return base + continuation if math.isfinite(continuation) else -math.inf
        if isinstance(node, Choice):
            values = [self._preview_transition(before, action, edge.node, seen=seen)
                      for edge in node.children]
            finite = [value for value in values if math.isfinite(value)]
            if not finite or (node.actor is Actor.OPPONENT and len(finite) != len(values)):
                return -math.inf
            return (max if node.actor is Actor.OURS else min)(finite)
        if isinstance(node, Chance):
            values = [self._preview_transition(before, action, edge.node, seen=seen)
                      for edge in node.children]
            if any(not math.isfinite(value) for value in values):
                return -math.inf
            return sum(edge.probability * value for edge, value in zip(node.children, values))
        return -math.inf

    def _immediate_transition(self, before: DecisionState, action: LegalAction, node) -> float:
        """One-transition ledger value used only to break equal no-horizon previews."""
        if isinstance(node, Unknown):
            return -math.inf
        if isinstance(node, Terminal):
            return _combine(self._ledger(before, node.state, action), 0.0, node.ledger).total
        if isinstance(node, Deterministic):
            return self._ledger(before, node.state, action).immediate
        if isinstance(node, Choice):
            values = [self._immediate_transition(before, action, edge.node)
                      for edge in node.children]
            finite = [value for value in values if math.isfinite(value)]
            if not finite or (node.actor is Actor.OPPONENT and len(finite) != len(values)):
                return -math.inf
            return (max if node.actor is Actor.OURS else min)(finite)
        if isinstance(node, Chance):
            values = [self._immediate_transition(before, action, edge.node)
                      for edge in node.children]
            if any(not math.isfinite(value) for value in values):
                return -math.inf
            return sum(edge.probability * value for edge, value in zip(node.children, values))
        return -math.inf

    def _chance_policy(self, before, action, node) -> Evaluation:
        if isinstance(node, Unknown):
            return Evaluation(-math.inf, Ledger(), False, node.reason)
        if isinstance(node, Terminal):
            ledger = _combine(self._ledger(before, node.state, action), 0.0, node.ledger)
            return Evaluation(ledger.total, ledger, True, node.result)
        if isinstance(node, Deterministic):
            base = self._ledger(before, node.state, action)
            continuation = self._preview_state(
                node.state, seen=frozenset({before.semantic_key}))
            if not math.isfinite(continuation):
                return Evaluation(-math.inf, base, False, "chance policy incomplete")
            ledger = _combine(base, continuation)
            return Evaluation(ledger.total, ledger, True, "replan preview")
        if isinstance(node, Choice):
            branches = [(edge, self._chance_policy(before, action, edge.node))
                        for edge in node.children]
            if any(not result.complete for _edge, result in branches):
                return Evaluation(-math.inf, Ledger(), False, "chance choice incomplete")
            chooser = max if node.actor is Actor.OURS else min
            _edge, result = chooser(
                branches, key=lambda pair: _ordered_value(pair[1].value))
            return result
        if isinstance(node, Chance):
            branches = [(edge, self._chance_policy(before, action, edge.node))
                        for edge in node.children]
            if any(not result.complete for _edge, result in branches):
                return Evaluation(-math.inf, Ledger(), False, "nested chance incomplete")
            benefits, costs, continuation = {}, {}, 0.0
            for edge, result in branches:
                for key, amount in result.ledger.benefits:
                    benefits[key] = benefits.get(key, 0.0) + edge.probability * amount
                for key, amount in result.ledger.costs:
                    costs[key] = costs.get(key, 0.0) + edge.probability * amount
                continuation += edge.probability * result.ledger.continuation
            ledger = Ledger(tuple(sorted(benefits.items())), tuple(sorted(costs.items())),
                            continuation)
            return Evaluation(ledger.total, ledger, True, "nested expected replan preview")
        return Evaluation(-math.inf, Ledger(), False, "undeclared chance policy node")

    def _transition(self, before: DecisionState, action: LegalAction, node) -> Evaluation:
        if isinstance(node, Choice) and node.actor is Actor.OURS:
            budget = self.production_limits.max_preview_per_action
            if hasattr(self.provider, "preview_node_budget"):
                budget = self.provider.preview_node_budget(before, action, budget)
            self._preview_remaining = budget
            previews = [(edge, self._preview_transition(
                before, action, edge.node, seen=frozenset({before.semantic_key})))
                for edge in node.children]
            finite = [(edge, value) for edge, value in previews if math.isfinite(value)]
            if not finite:
                return Evaluation(-math.inf, Ledger(), False, "our choice preview incomplete")
            edge, _value = max(finite, key=lambda pair: _ordered_value(pair[1]))
            result = self._transition(before, action, edge.node)
            return Evaluation(result.value, result.ledger, result.complete,
                              f"ours chose {edge.label}",
                              tuple({"label": child.label, "value": value,
                                     "complete": math.isfinite(value)}
                                    for child, value in previews))
        if isinstance(node, Deterministic):
            base = self._ledger(before, node.state, action)
            continuation = self._state(node.state)
            if continuation.action is None and not continuation.evaluation.complete:
                return Evaluation(-math.inf, base, False, continuation.evaluation.reason)
            ledger = _combine(base, continuation.value)
            return Evaluation(ledger.total, ledger, continuation.evaluation.complete,
                              continuation.evaluation.reason)
        if not isinstance(node, Chance):
            return super()._transition(before, action, node)
        branches = []
        for edge in node.children:
            self._preview_remaining = self.production_limits.max_preview_per_action
            branches.append((edge, self._chance_policy(before, action, edge.node)))
        if any(not result.complete for _edge, result in branches):
            return Evaluation(-math.inf, Ledger(), False, "incomplete production chance branch")
        benefits, costs, continuation = {}, {}, 0.0
        for edge, result in branches:
            for key, amount in result.ledger.benefits:
                benefits[key] = benefits.get(key, 0.0) + edge.probability * amount
            for key, amount in result.ledger.costs:
                costs[key] = costs.get(key, 0.0) + edge.probability * amount
            continuation += edge.probability * result.ledger.continuation
        ledger = Ledger(tuple(sorted(benefits.items())), tuple(sorted(costs.items())), continuation)
        return Evaluation(ledger.total, ledger, True, "expected actual-state replan",
                          tuple({"label": edge.label, "probability": edge.probability,
                                 "value": result.value}
                                for edge, result in branches))

    def _state(self, state: DecisionState) -> StateEvaluation:
        if self.nodes >= self.limits.max_nodes:
            end = next((action for action in self.provider.actions(state)
                        if action.identity.kind == "end"), None)
            if end is not None:
                stopped = Evaluation(0.0, Ledger(), True, "bounded End")
                return StateEvaluation(0.0, end, stopped, ((end, stopped),))
            incomplete = Evaluation(-math.inf, Ledger(), False,
                                    "production cap at mandatory choice")
            return StateEvaluation(-math.inf, None, incomplete, ())

        key = state.semantic_key
        if key in self._memo:
            self.cache_hits += 1
            return self._memo[key]
        if key in self._active:
            incomplete = Evaluation(-math.inf, Ledger(), False, "semantic cycle")
            return StateEvaluation(-math.inf, None, incomplete, ())

        self.nodes += 1
        self._active.add(key)
        actions = tuple(sorted(self.provider.actions(state), key=lambda action: action.identity))
        immediate_values: dict[ActionIdentity, float] = {}
        if self.provider.actor(state) is Actor.OURS:
            ranked = []
            for action in actions:
                budget = self.production_limits.max_preview_per_action
                if hasattr(self.provider, "preview_node_budget"):
                    budget = self.provider.preview_node_budget(state, action, budget)
                self._preview_remaining = budget
                checkpoint = (self.provider.preview_checkpoint()
                              if hasattr(self.provider, "preview_checkpoint") else None)
                try:
                    if action.identity.kind == "end":
                        value = immediate = 0.0
                    else:
                        node = self.provider.transition(state, action)
                        value = self._preview_node_action(
                            state, action, node, seen=frozenset({key}))
                        immediate = self._immediate_transition(state, action, node)
                finally:
                    if checkpoint is not None:
                        self.provider.preview_restore(checkpoint)
                immediate_values[action.identity] = immediate
                ranked.append((value, immediate, action))
            if key == self._root_key:
                self._root_previews = {str(action.identity): value
                                       for value, _immediate, action in ranked}
            end = [pair for pair in ranked if pair[RANKED_ACTION_SLOT].identity.kind == "end"]
            non_end = sorted((pair for pair in ranked
                              if pair[RANKED_ACTION_SLOT].identity.kind != "end"),
                             key=lambda pair: (_ordered_value(pair[0]),
                                               _ordered_value(pair[1])), reverse=True)
            kept = non_end[:self.production_limits.beam_width]
            if self.production_limits.beam_width > IMMEDIATE_VALUE_BEAM_SLOTS and non_end:
                immediate = sorted(
                    non_end, key=lambda pair: (_ordered_value(pair[1]),
                                               _ordered_value(pair[0])), reverse=True)
                diverse = [*non_end[:self.production_limits.beam_width
                                    - IMMEDIATE_VALUE_BEAM_SLOTS]]
                diverse.extend(row for row in immediate if row not in diverse)
                kept = tuple(diverse[:self.production_limits.beam_width])
            chosen_set = {action.identity for _value, _immediate, action in (*kept, *end)}
            self.pruned += len(actions) - len(chosen_set)
            actions = tuple(action for _value, _immediate, action in (*kept, *end))

        results = tuple((action, self._action(state, action)) for action in actions)
        self._active.remove(key)
        complete = [(action, result) for action, result in results if result.complete]
        if not complete:
            answer = StateEvaluation(-math.inf, None,
                                     Evaluation(-math.inf, Ledger(), False,
                                                "all legal actions incomplete"), results)
        else:
            actor = self.provider.actor(state)
            if actor is Actor.OURS:
                action, result = max(complete, key=lambda pair: (
                    _ordered_value(pair[1].value),
                    _ordered_value(immediate_values.get(pair[0].identity, -math.inf))))
            else:
                action, result = min(
                    complete, key=lambda pair: _ordered_value(pair[1].value))
            answer = StateEvaluation(result.value, action, result, results)
        self._memo[key] = answer
        return answer


__all__ = (
    "Evaluation", "ProductionLimits", "ProductionSolver", "ReferenceSolver", "SearchLimits",
    "StateEvaluation", "TransitionProvider",
)
