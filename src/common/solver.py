"""Deterministic exhaustive Bellman reference solver."""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol

from .algebra import (
    ActionDiagnostic, Actor, Chance, Choice, Deterministic, Ledger, RevealChoice, RootDiagnostics,
    Terminal, Unknown,
)
from .api import RootDecision
from .options import LegalAction
from .state import DecisionState
from .value import ValueOracle


REFERENCE_MAX_NODES = 100_000
PRODUCTION_MAX_NODES = 4_000
PRODUCTION_BEAM_WIDTH = 16
DEFAULT_ROOT_BEAM_WIDTH = 16
DEFAULT_EFFECT_CHOICE_WIDTH = 64
MAIN_DECISION_CONTEXT = 0
VALUE_TIE_DECIMALS = 12
TERMINAL_WIN_REASON = "win"


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
    root_beam_width: int = DEFAULT_ROOT_BEAM_WIDTH
    effect_choice_width: int = DEFAULT_EFFECT_CHOICE_WIDTH


@dataclass(frozen=True)
class Evaluation:
    value: float
    ledger: Ledger
    complete: bool
    reason: str = ""
    branches: tuple[dict, ...] = ()
    decisions: float = 0.0


@dataclass(frozen=True)
class StateEvaluation:
    value: float
    action: LegalAction | None
    evaluation: Evaluation
    alternatives: tuple[tuple[LegalAction, Evaluation], ...]


def _combine(base: Ledger, continuation: float, extra: Ledger = Ledger()) -> Ledger:
    return Ledger(base.benefits + extra.benefits, base.costs + extra.costs,
                  base.continuation + extra.immediate + float(continuation))


def _ordered_evaluation(result: Evaluation, actor: Actor) -> tuple[float, float]:
    """Bellman utility first; on an exact tie, prefer the shorter continuation.

    This is a lexicographic objective, not a small magic penalty that can overturn real utility.
    Both actors avoid redundant decisions after optimizing their opposing primary utilities.
    """
    value = (round(result.value, VALUE_TIE_DECIMALS)
             if math.isfinite(result.value) else result.value)
    decision_order = -float(result.decisions) if actor is Actor.OURS else float(result.decisions)
    return value, decision_order


def _expected_evaluation(weighted, *, reason: str, branches=(), complete: bool = True) -> Evaluation:
    benefits: dict[str, float] = {}
    costs: dict[str, float] = {}
    continuation = 0.0
    decisions = 0.0
    for probability, result in weighted:
        for key, amount in result.ledger.benefits:
            benefits[key] = benefits.get(key, 0.0) + probability * amount
        for key, amount in result.ledger.costs:
            costs[key] = costs.get(key, 0.0) + probability * amount
        continuation += probability * result.ledger.continuation
        decisions += probability * result.decisions
    ledger = Ledger(tuple(sorted(benefits.items())), tuple(sorted(costs.items())), continuation)
    return Evaluation(ledger.total, ledger, complete, reason, tuple(branches), decisions)


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
                             result.branches, result.decisions)
            for action, result in solved.alternatives if action != solved.action)
        diagnostics = RootDiagnostics(
            chosen_key=str(solved.action.identity),
            end=ActionDiagnostic("end", end_eval.ledger, end_eval.complete, end_eval.reason,
                                 end_eval.branches, end_eval.decisions),
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
        actor = (self.provider.actor(state) if hasattr(self.provider, "actor") else Actor.OURS)
        results_list = []
        for action in actions:
            result = self._action(state, action)
            results_list.append((action, result))
        results = tuple(results_list)
        self._active.remove(key)
        complete = [(action, result) for action, result in results if result.complete]
        if len(complete) != len(results) or not complete:
            answer = StateEvaluation(-math.inf, None,
                                     Evaluation(-math.inf, Ledger(), False,
                                                "one or more legal actions incomplete"), results)
        else:
            chooser = max if actor is Actor.OURS else min
            action, result = chooser(
                complete, key=lambda pair: _ordered_evaluation(pair[1], actor))
            answer = StateEvaluation(result.value, action, result, results)
        if answer.evaluation.complete:
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
                              continuation.evaluation.reason, decisions=(
                                  1.0 + continuation.evaluation.decisions))
        if isinstance(node, Terminal):
            base = self._ledger(before, node.state, action)
            ledger = _combine(base, 0.0, node.ledger)
            return Evaluation(ledger.total, ledger, True, node.result, decisions=1.0)
        if isinstance(node, Choice):
            branches = [(edge, self._transition(before, action, edge.node))
                        for edge in node.children]
            finite = [(edge, result) for edge, result in branches if math.isfinite(result.value)]
            if len(finite) != len(branches) or not finite:
                return Evaluation(-math.inf, Ledger(), False, "incomplete choice branch",
                                  tuple({"label": edge.label, "complete": result.complete,
                                         "value": result.value, "reason": result.reason}
                                        for edge, result in branches))
            chooser = max if node.actor is Actor.OURS else min
            edge, result = chooser(
                finite, key=lambda pair: _ordered_evaluation(pair[1], node.actor))
            proven = all(evaluated.complete for _child, evaluated in branches)
            return Evaluation(result.value, result.ledger, proven,
                              (result.reason if result.reason == TERMINAL_WIN_REASON
                               else f"{node.actor.value} chose {edge.label}"),
                              tuple({"label": child.label, "value": evaluated.value,
                                     "complete": evaluated.complete}
                                    for child, evaluated in branches), result.decisions)
        if isinstance(node, RevealChoice):
            evaluated = {edge.label: self._transition(before, action, edge.node)
                         for edge in node.choices}
            if any(not math.isfinite(result.value) for result in evaluated.values()):
                return Evaluation(-math.inf, Ledger(), False, "incomplete reveal choice")
            chooser = max if node.actor is Actor.OURS else min
            weighted = []
            diagnostics = []
            for outcome in node.outcomes:
                label = chooser(
                    outcome.choices,
                    key=lambda choice: _ordered_evaluation(evaluated[choice], node.actor))
                weighted.append((outcome.probability, evaluated[label]))
                diagnostics.append({"choices": outcome.choices, "chosen": label,
                                    "probability": outcome.probability,
                                    "value": evaluated[label].value})
            return _expected_evaluation(
                weighted, reason="expected value after revealed choice", branches=diagnostics,
                complete=all(result.complete for result in evaluated.values()))
        if isinstance(node, Chance):
            branches = [(edge, self._transition(before, action, edge.node))
                        for edge in node.children]
            if any(not math.isfinite(result.value) for _edge, result in branches):
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
            decisions = sum(edge.probability * result.decisions for edge, result in branches)
            return Evaluation(value, ledger, all(result.complete for _edge, result in branches),
                              "expected value",
                              tuple({"label": edge.label, "probability": edge.probability,
                                     "value": result.value}
                                    for edge, result in branches), decisions)
        return Evaluation(-math.inf, Ledger(), False, "undeclared transition result")


class ProductionSolver(ReferenceSolver):
    """Bounded search over the reference transition/value contracts.

    There is no depth horizon and no second policy. Width/state capacity are explicit. At a capped
    state where End is legal, exact-zero End is a valid lower bound. A mandatory selection is not
    an optional action menu, so its legal choices are never discarded solely by the width bound.
    """

    def __init__(self, provider: TransitionProvider, oracle: ValueOracle, *, model_factory=None,
                 limits: ProductionLimits = ProductionLimits()):
        super().__init__(provider, oracle, model_factory=model_factory,
                         limits=SearchLimits(limits.max_nodes))
        self.production_limits = limits
        self._root_key = ""
        self._root_branch_nodes: list[int] = []

    def decide(self, state: DecisionState) -> RootDecision:
        self._root_key = state.semantic_key
        self._root_branch_nodes = []
        decision = super().decide(state)
        diagnostics = dict(decision.diagnostics)
        diagnostics["production"] = {
            "beam_width": self.production_limits.beam_width,
            "root_beam_width": self.production_limits.root_beam_width,
            "effect_choice_width": self.production_limits.effect_choice_width,
            "max_nodes": self.production_limits.max_nodes,
            "max_nodes_per_root_action": self.production_limits.max_nodes,
            "root_branch_nodes": tuple(self._root_branch_nodes),
            "cap_reached": any(nodes >= self.production_limits.max_nodes
                               for nodes in self._root_branch_nodes),
            "lower_bound": not decision.complete,
        }
        return RootDecision(decision.chosen, decision.action, decision.value,
                            decision.complete, diagnostics)

    def _state(self, state: DecisionState) -> StateEvaluation:
        if self.nodes >= self.limits.max_nodes:
            actions = tuple(sorted(self.provider.actions(state), key=lambda action: action.identity))
            end = next((action for action in actions if action.identity.kind == "end"), None)
            if end is not None:
                lower = Evaluation(0.0, Ledger(), False, "production cap: End lower bound")
                return StateEvaluation(0.0, end, lower, ((end, lower),))
            incomplete = Evaluation(-math.inf, Ledger(), False, "production state cap")
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
        if self.provider.actor(state) is Actor.OURS:
            context = int(((state.obs.get("select") or {}).get("context", -1)))
            width = (self.production_limits.root_beam_width if key == self._root_key
                     else self.production_limits.beam_width if context == MAIN_DECISION_CONTEXT
                     else self.production_limits.effect_choice_width)
            non_end_count = sum(action.identity.kind != "end" for action in actions)
            if non_end_count > width:
                end = next((action for action in actions if action.identity.kind == "end"), None)
                if end is not None:
                    self._active.remove(key)
                    lower = Evaluation(0.0, Ledger(), False,
                                       "production width cap: End lower bound")
                    return StateEvaluation(0.0, end, lower, ((end, lower),))
                # A forced effect selection has no legal End action.  Applying the optional-menu
                # beam here would manufacture an illegal "no decision" outcome.  Evaluate its
                # declared actions with the same Bellman backup; the node cap still bounds work.

        actor = self.provider.actor(state)
        if key == self._root_key:
            results_list = []
            total_nodes = self.nodes
            original_limits = self.limits
            # Every root alternative receives the same full budget. Dividing a
            # fixed pool by the number of legal choices makes a card worse merely
            # because other cards are playable, and therefore is itself a hidden
            # action-count policy rather than a Bellman comparison.
            self.limits = SearchLimits(self.production_limits.max_nodes)
            for action in actions:
                self.nodes = 1
                result = self._action(state, action)
                self._root_branch_nodes.append(self.nodes)
                total_nodes += max(0, self.nodes - 1)
                results_list.append((action, result))
            self.limits = original_limits
            self.nodes = total_nodes
            results = tuple(results_list)
        else:
            results_list = []
            for action in actions:
                result = self._action(state, action)
                results_list.append((action, result))
            results = tuple(results_list)
        self._active.remove(key)
        finite = [(action, result) for action, result in results if math.isfinite(result.value)]
        if not finite or (actor is Actor.OPPONENT and len(finite) != len(results)):
            answer = StateEvaluation(-math.inf, None,
                                     Evaluation(-math.inf, Ledger(), False,
                                                "one or more legal actions incomplete"), results)
        else:
            if actor is Actor.OURS:
                action, result = max(
                    finite, key=lambda pair: _ordered_evaluation(pair[1], actor))
            else:
                action, result = min(
                    finite, key=lambda pair: _ordered_evaluation(pair[1], actor))
            proven = result.complete and len(finite) == len(results) and all(
                evaluated.complete for _candidate, evaluated in results)
            evaluation = Evaluation(result.value, result.ledger, proven, result.reason,
                                    result.branches, result.decisions)
            answer = StateEvaluation(result.value, action, evaluation, results)
        # A bounded lower bound depends on the budget remaining when it was
        # reached.  Reusing it from another branch would turn traversal order
        # into policy.  Only exact Bellman backups are transposition-safe.
        if answer.evaluation.complete:
            self._memo[key] = answer
        return answer


__all__ = (
    "Evaluation", "ProductionLimits", "ProductionSolver", "ReferenceSolver", "SearchLimits",
    "StateEvaluation", "TransitionProvider",
)
