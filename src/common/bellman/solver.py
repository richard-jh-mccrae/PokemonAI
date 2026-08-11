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
from common.strategy.context import _MAIN, _SKILL, _TO_ACTIVE
from .value import ValueOracle


REFERENCE_MAX_DEPTH = 20
REFERENCE_MAX_NODES = 100_000
PRODUCTION_MAX_DEPTH = 12
PRODUCTION_MAX_NODES = 4_000
PRODUCTION_BEAM_WIDTH = 4
PRODUCTION_PREVIEW_MAIN_STEPS = 1
PRODUCTION_PREVIEW_CAP_PER_ACTION = 300
FORCED_RESOLUTION_DEPTH_LIMIT = 24
MULTI_PRIZE_GAIN_THRESHOLD = 2


class TransitionProvider(Protocol):
    def actions(self, state: DecisionState) -> tuple[LegalAction, ...]:
        ...

    def transition(self, state: DecisionState, action: LegalAction):
        ...

    def actor(self, state: DecisionState) -> Actor:
        ...


@dataclass(frozen=True)
class SearchLimits:
    max_depth: int = REFERENCE_MAX_DEPTH
    max_nodes: int = REFERENCE_MAX_NODES


@dataclass(frozen=True)
class ProductionLimits:
    max_depth: int = PRODUCTION_MAX_DEPTH
    max_nodes: int = PRODUCTION_MAX_NODES
    beam_width: int = PRODUCTION_BEAM_WIDTH
    preview_main_steps: int = PRODUCTION_PREVIEW_MAIN_STEPS
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
        solved = self._state(state, depth=0)
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

    def _state(self, state: DecisionState, *, depth: int) -> StateEvaluation:
        key = state.semantic_key
        if key in self._memo:
            self.cache_hits += 1
            return self._memo[key]
        if key in self._active:
            incomplete = Evaluation(-math.inf, Ledger(), False, "semantic cycle")
            return StateEvaluation(-math.inf, None, incomplete, ())
        if depth > self.limits.max_depth or self.nodes >= self.limits.max_nodes:
            incomplete = Evaluation(-math.inf, Ledger(), False, "reference cap")
            return StateEvaluation(-math.inf, None, incomplete, ())
        self.nodes += 1
        self._active.add(key)
        actions = tuple(sorted(self.provider.actions(state), key=lambda action: action.identity))
        results = tuple((action, self._action(state, action, depth=depth)) for action in actions)
        self._active.remove(key)
        complete = [(action, result) for action, result in results if result.complete]
        if not complete:
            answer = StateEvaluation(-math.inf, None,
                                     Evaluation(-math.inf, Ledger(), False,
                                                "all legal actions incomplete"), results)
        else:
            actor = (self.provider.actor(state) if hasattr(self.provider, "actor") else Actor.OURS)
            chooser = max if actor is Actor.OURS else min
            action, result = chooser(complete, key=lambda pair: (pair[1].value,
                                                                  tuple(pair[0].identity.parts),
                                                                  pair[0].identity.kind))
            answer = StateEvaluation(result.value, action, result, results)
        self._memo[key] = answer
        return answer

    def _action(self, state: DecisionState, action: LegalAction, *, depth: int) -> Evaluation:
        if action.identity.kind == "end":
            return Evaluation(0.0, Ledger(), True, "End exact zero")
        return self._transition(state, action, self.provider.transition(state, action), depth=depth)

    def _transition(self, before: DecisionState, action: LegalAction, node, *, depth: int) -> Evaluation:
        if isinstance(node, Unknown):
            return Evaluation(-math.inf, Ledger(), False,
                              f"{node.reason}: {node.missing_fact}")
        if isinstance(node, Deterministic):
            base = self._ledger(before, node.state, action)
            continuation = self._state(node.state, depth=depth + 1)
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
            branches = [(edge, self._transition(before, action, edge.node, depth=depth))
                        for edge in node.children]
            complete = [(edge, result) for edge, result in branches if result.complete]
            if len(complete) != len(branches) or not complete:
                return Evaluation(-math.inf, Ledger(), False, "incomplete choice branch",
                                  tuple({"label": edge.label, "complete": result.complete,
                                         "value": result.value, "reason": result.reason}
                                        for edge, result in branches))
            chooser = max if node.actor is Actor.OURS else min
            edge, result = chooser(complete, key=lambda pair: (pair[1].value, pair[0].label))
            return Evaluation(result.value, result.ledger, True,
                              f"{node.actor.value} chose {edge.label}",
                              tuple({"label": child.label, "value": evaluated.value,
                                     "complete": evaluated.complete}
                                    for child, evaluated in branches))
        if isinstance(node, Chance):
            branches = [(edge, self._transition(before, action, edge.node, depth=depth))
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

    Every root option is simulated through its nested effect to the next MAIN menu.  Only then does
    the beam remove dominated continuations.  A cap is a real End choice when End is reachable; a
    mandatory nested menu remains incomplete and can never inherit fabricated zero value.
    """

    def __init__(self, provider: TransitionProvider, oracle: ValueOracle, *, model_factory=None,
                 limits: ProductionLimits = ProductionLimits()):
        super().__init__(provider, oracle, model_factory=model_factory,
                         limits=SearchLimits(limits.max_depth, limits.max_nodes))
        self.production_limits = limits
        self.previewed = 0
        self.pruned = 0
        self._preview_cache: dict[tuple[str, str, int], float] = {}
        self._root_previews: dict[str, float] = {}
        self._preview_remaining = limits.max_preview_per_action
        self.preview_caps = 0

    def _forced_win(self, node, *, seen: frozenset[str], depth: int = 0) -> bool:
        """Resolve only mandatory post-attack menus to prove an immediate game win."""
        if depth > FORCED_RESOLUTION_DEPTH_LIMIT or isinstance(node, Unknown):
            return False
        if isinstance(node, Terminal):
            return node.result == "win"
        if isinstance(node, Choice):
            rows = [self._forced_win(edge.node, seen=seen, depth=depth + 1)
                    for edge in node.children]
            return (any(rows) if node.actor is Actor.OURS else bool(rows) and all(rows))
        if isinstance(node, Chance):
            return bool(node.children) and all(
                self._forced_win(edge.node, seen=seen, depth=depth + 1)
                for edge in node.children)
        if not isinstance(node, Deterministic):
            return False
        state = node.state
        if state.semantic_key in seen or self._main(state):
            return False
        actions = self.provider.actions(state)
        if not actions:
            return False
        rows = [self._forced_win(
            self.provider.transition(state, action),
            seen=seen | {state.semantic_key}, depth=depth + 1)
                for action in actions]
        actor = self.provider.actor(state)
        return any(rows) if actor is Actor.OURS else all(rows)

    def _immediate_winning_attacks(self, state, actions):
        winners = []
        for action in actions:
            if action.identity.kind != "attack":
                continue
            checkpoint = (self.provider.preview_checkpoint()
                          if hasattr(self.provider, "preview_checkpoint") else None)
            try:
                if self._forced_win(
                        self.provider.transition(state, action),
                        seen=frozenset({state.semantic_key})):
                    winners.append(action)
            finally:
                if checkpoint is not None:
                    self.provider.preview_restore(checkpoint)
        return tuple(winners)

    def _prize_gain(self, node, *, root_count: int, seen: frozenset[str], depth: int = 0):
        if depth > FORCED_RESOLUTION_DEPTH_LIMIT or isinstance(node, Unknown):
            return None
        if isinstance(node, Terminal):
            players = (node.state.obs.get("current") or {}).get("players") or ()
            mine = players[node.state.root_seat] if len(players) > node.state.root_seat else {}
            return max(0, root_count - len(mine.get("prize") or ()))
        if isinstance(node, (Choice, Chance)):
            rows = [self._prize_gain(edge.node, root_count=root_count, seen=seen,
                                     depth=depth + 1) for edge in node.children]
            if not rows or any(value is None for value in rows):
                return None
            if isinstance(node, Chance) or node.actor is Actor.OPPONENT:
                return min(rows)
            return max(rows)
        if not isinstance(node, Deterministic):
            return None
        state = node.state
        if state.semantic_key in seen or self._main(state):
            return None
        actions = self.provider.actions(state)
        rows = [self._prize_gain(
            self.provider.transition(state, action), root_count=root_count,
            seen=seen | {state.semantic_key}, depth=depth + 1) for action in actions]
        if not rows or any(value is None for value in rows):
            return None
        return max(rows) if self.provider.actor(state) is Actor.OURS else min(rows)

    def _immediate_prize_attacks(self, state, actions):
        players = (state.obs.get("current") or {}).get("players") or ()
        mine = players[state.root_seat] if len(players) > state.root_seat else {}
        root_count = len(mine.get("prize") or ())
        rows = []
        for action in actions:
            if action.identity.kind != "attack":
                continue
            checkpoint = (self.provider.preview_checkpoint()
                          if hasattr(self.provider, "preview_checkpoint") else None)
            try:
                gain = self._prize_gain(
                    self.provider.transition(state, action), root_count=root_count,
                    seen=frozenset({state.semantic_key}))
            finally:
                if checkpoint is not None:
                    self.provider.preview_restore(checkpoint)
            if gain is not None:
                rows.append((gain, action))
        best = max((gain for gain, _action in rows), default=0)
        return (tuple(action for gain, action in rows if gain == best)
                if best >= MULTI_PRIZE_GAIN_THRESHOLD else ())

    def _immediate_prize_choices(self, state, actions):
        players = (state.obs.get("current") or {}).get("players") or ()
        mine = players[state.root_seat] if len(players) > state.root_seat else {}
        root_count = len(mine.get("prize") or ())
        rows = []
        for action in actions:
            checkpoint = (self.provider.preview_checkpoint()
                          if hasattr(self.provider, "preview_checkpoint") else None)
            try:
                gain = self._prize_gain(
                    self.provider.transition(state, action), root_count=root_count,
                    seen=frozenset({state.semantic_key}))
            finally:
                if checkpoint is not None:
                    self.provider.preview_restore(checkpoint)
            if gain is not None:
                rows.append((gain, action))
        best = max((gain for gain, _action in rows), default=0)
        return tuple(action for gain, action in rows if gain == best) if best > 0 else ()

    @staticmethod
    def _main(state: DecisionState) -> bool:
        return int(((state.obs.get("select") or {}).get("context", -1))) == _MAIN

    def decide(self, state: DecisionState) -> RootDecision:
        self.previewed = self.pruned = self.preview_caps = 0
        self._preview_cache.clear()
        self._root_previews.clear()
        decision = super().decide(state)
        diagnostics = dict(decision.diagnostics)
        diagnostics["production"] = {
            "beam_width": self.production_limits.beam_width,
            "preview_main_steps": self.production_limits.preview_main_steps,
            "max_depth": self.production_limits.max_depth,
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

    def _preview_state(self, state: DecisionState, *, seen: frozenset[str],
                       main_steps: int) -> float:
        if state.semantic_key in seen:
            return -math.inf
        actions = self.provider.actions(state)
        if hasattr(self.provider, "preview_actions"):
            actions = self.provider.preview_actions(
                state, actions, main_steps=main_steps)
        values = [self._preview_action(state, action, seen=seen | {state.semantic_key},
                                       main_steps=main_steps)
                  for action in actions]
        finite = [value for value in values if math.isfinite(value)]
        if not finite:
            return -math.inf
        actor = self.provider.actor(state)
        return (max if actor is Actor.OURS else min)(finite)

    def _preview_action(self, state: DecisionState, action: LegalAction,
                        *, seen: frozenset[str], main_steps: int) -> float:
        if action.identity.kind == "end":
            return 0.0
        key = (state.semantic_key, str(action.identity), int(main_steps))
        if key in self._preview_cache:
            return self._preview_cache[key]
        if self._preview_remaining <= 0:
            self.preview_caps += 1
            return -math.inf
        self._preview_remaining -= 1
        self.previewed += 1
        value = self._preview_transition(
            state, action, self.provider.transition(state, action), seen=seen,
            main_steps=main_steps)
        self._preview_cache[key] = value
        return value

    def _preview_transition(self, before: DecisionState, action: LegalAction, node,
                            *, seen: frozenset[str], main_steps: int) -> float:
        if isinstance(node, Unknown):
            return -math.inf
        if isinstance(node, Terminal):
            return _combine(self._ledger(before, node.state, action), 0.0, node.ledger).total
        if isinstance(node, Deterministic):
            base = self._ledger(before, node.state, action).immediate
            if self._main(node.state):
                if main_steps <= 0:
                    return base
                continuation = self._preview_state(
                    node.state, seen=seen, main_steps=main_steps - 1)
                return base + continuation if math.isfinite(continuation) else -math.inf
            continuation = self._preview_state(node.state, seen=seen,
                                               main_steps=main_steps)
            return base + continuation if math.isfinite(continuation) else -math.inf
        if isinstance(node, Choice):
            values = [self._preview_transition(before, action, edge.node, seen=seen,
                                               main_steps=main_steps)
                      for edge in node.children]
            if any(not math.isfinite(value) for value in values):
                return -math.inf
            return (max if node.actor is Actor.OURS else min)(values)
        if isinstance(node, Chance):
            chance_steps = main_steps
            if hasattr(self.provider, "chance_replan_steps"):
                chance_steps = self.provider.chance_replan_steps(
                    before, action, chance_steps)
            values = [self._preview_transition(before, action, edge.node, seen=seen,
                                               main_steps=chance_steps)
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
            chance_steps = self.production_limits.preview_main_steps
            if hasattr(self.provider, "chance_replan_steps"):
                chance_steps = self.provider.chance_replan_steps(
                    before, action, chance_steps)
            continuation = self._preview_state(
                node.state, seen=frozenset({before.semantic_key}),
                main_steps=chance_steps)
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
            _edge, result = chooser(branches, key=lambda pair: (pair[1].value, pair[0].label))
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

    def _transition(self, before: DecisionState, action: LegalAction, node,
                    *, depth: int) -> Evaluation:
        if isinstance(node, Choice) and node.actor is Actor.OURS:
            budget = self.production_limits.max_preview_per_action
            if hasattr(self.provider, "preview_budget"):
                budget = self.provider.preview_budget(before, action, budget)
            self._preview_remaining = budget
            steps = self.production_limits.preview_main_steps
            if hasattr(self.provider, "preview_main_steps"):
                steps = self.provider.preview_main_steps(before, action, steps)
            previews = [(edge, self._preview_transition(
                before, action, edge.node, seen=frozenset({before.semantic_key}),
                main_steps=steps)) for edge in node.children]
            finite = [(edge, value) for edge, value in previews if math.isfinite(value)]
            if not finite:
                return Evaluation(-math.inf, Ledger(), False, "our choice preview incomplete")
            edge, _value = max(finite, key=lambda pair: (pair[1], pair[0].label))
            result = self._transition(before, action, edge.node, depth=depth)
            return Evaluation(result.value, result.ledger, result.complete,
                              f"ours chose {edge.label}",
                              tuple({"label": child.label, "value": value,
                                     "complete": math.isfinite(value)}
                                    for child, value in previews))
        if isinstance(node, Deterministic):
            base = self._ledger(before, node.state, action)
            continuation = self._state(
                node.state, depth=depth + (1 if self._main(node.state) else 0))
            if continuation.action is None and not continuation.evaluation.complete:
                return Evaluation(-math.inf, base, False, continuation.evaluation.reason)
            ledger = _combine(base, continuation.value)
            return Evaluation(ledger.total, ledger, continuation.evaluation.complete,
                              continuation.evaluation.reason)
        if not isinstance(node, Chance):
            return super()._transition(before, action, node, depth=depth)
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

    def _state(self, state: DecisionState, *, depth: int) -> StateEvaluation:
        if depth > self.limits.max_depth or self.nodes >= self.limits.max_nodes:
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
        if (int(((state.obs.get("select") or {}).get("context", -1))) == _SKILL
                and self.provider.actor(state) is Actor.OURS):
            immediate_prizes = self._immediate_prize_choices(state, actions)
            if immediate_prizes:
                actions = immediate_prizes
        context = int(((state.obs.get("select") or {}).get("context", -1)))
        # Forced promotion determines the attacker's entire next turn.  Retain every promotion
        # candidate for its full board-value evaluation; broader nested menus retain the bounded
        # preview policy below.
        exact_nested_context = context == _TO_ACTIVE
        if (not exact_nested_context and not self._main(state)
                and self.provider.actor(state) is Actor.OURS and len(actions) > 1):
            ranked_nested = []
            for action in actions:
                budget = self.production_limits.max_preview_per_action
                if hasattr(self.provider, "preview_budget"):
                    budget = self.provider.preview_budget(state, action, budget)
                self._preview_remaining = budget
                steps = self.production_limits.preview_main_steps
                if hasattr(self.provider, "preview_main_steps"):
                    steps = self.provider.preview_main_steps(state, action, steps)
                checkpoint = (self.provider.preview_checkpoint()
                              if hasattr(self.provider, "preview_checkpoint") else None)
                try:
                    value = self._preview_action(
                        state, action, seen=frozenset({key}), main_steps=steps)
                finally:
                    if checkpoint is not None:
                        self.provider.preview_restore(checkpoint)
                ranked_nested.append((value, action))
            finite_nested = [pair for pair in ranked_nested if math.isfinite(pair[0])]
            if finite_nested:
                _value, best_nested = max(
                    finite_nested, key=lambda pair: (pair[0], pair[1].identity))
                self.pruned += len(actions) - 1
                actions = (best_nested,)
        if self._main(state) and self.provider.actor(state) is Actor.OURS:
            immediate_wins = self._immediate_winning_attacks(state, actions)
            if immediate_wins:
                actions = immediate_wins
            else:
                immediate_prizes = self._immediate_prize_attacks(state, actions)
                if immediate_prizes:
                    # Keep the best resolving attack(s), but do not erase setup that can precede
                    # that same KO (heal, attach, information). Only a game-winning attack is
                    # terminally dominant over every other root action.
                    actions = tuple(action for action in actions
                                    if action.identity.kind != "attack") + immediate_prizes
            ranked = []
            for action in actions:
                budget = self.production_limits.max_preview_per_action
                if hasattr(self.provider, "preview_budget"):
                    budget = self.provider.preview_budget(state, action, budget)
                self._preview_remaining = budget
                steps = self.production_limits.preview_main_steps
                if hasattr(self.provider, "preview_main_steps"):
                    steps = self.provider.preview_main_steps(state, action, steps)
                checkpoint = (self.provider.preview_checkpoint()
                              if hasattr(self.provider, "preview_checkpoint") else None)
                try:
                    value = self._preview_action(
                        state, action, seen=frozenset({key}), main_steps=steps)
                finally:
                    if checkpoint is not None:
                        self.provider.preview_restore(checkpoint)
                ranked.append((value, action))
            if depth == 0:
                self._root_previews = {str(action.identity): value for value, action in ranked}
            end = [pair for pair in ranked if pair[1].identity.kind == "end"]
            non_end = sorted((pair for pair in ranked if pair[1].identity.kind != "end"),
                             key=lambda pair: (pair[0], pair[1].identity), reverse=True)
            kept = non_end[:self.production_limits.beam_width]
            chosen_set = {action.identity for _value, action in (*kept, *end)}
            self.pruned += len(actions) - len(chosen_set)
            actions = tuple(action for action in actions if action.identity in chosen_set)

        results = tuple((action, self._action(state, action, depth=depth)) for action in actions)
        self._active.remove(key)
        complete = [(action, result) for action, result in results if result.complete]
        if not complete:
            answer = StateEvaluation(-math.inf, None,
                                     Evaluation(-math.inf, Ledger(), False,
                                                "all legal actions incomplete"), results)
        else:
            actor = self.provider.actor(state)
            chooser = max if actor is Actor.OURS else min
            action, result = chooser(complete, key=lambda pair: (
                pair[1].value, tuple(pair[0].identity.parts), pair[0].identity.kind))
            answer = StateEvaluation(result.value, action, result, results)
        self._memo[key] = answer
        return answer


__all__ = (
    "Evaluation", "ProductionLimits", "ProductionSolver", "ReferenceSolver", "SearchLimits",
    "StateEvaluation", "TransitionProvider",
)
