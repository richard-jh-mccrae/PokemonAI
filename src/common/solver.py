"""Deterministic exhaustive Bellman reference solver."""
from __future__ import annotations

from dataclasses import dataclass
import math
from time import monotonic
from typing import Protocol

from .algebra import (
    ActionDiagnostic, Actor, Chance, Choice, Deterministic, Ledger, Refresh, RevealChoice,
    RootDiagnostics, Terminal, Unknown,
)
from .api import RootDecision
from .commutativity import ActionFootprint, independent
from .options import LegalAction
from .state import DecisionState
from .value import ValueOracle


REFERENCE_MAX_NODES = 100_000
PRODUCTION_MAX_NODES = 4_000
PRODUCTION_CHANCE_MAX_NODES = 600
PRODUCTION_REVEAL_MAX_NODES = 1_300
UNCERTAINTY_REFINEMENT_VALUE_MARGIN = 0.10
PRODUCTION_MAX_SECONDS = 15.0
PRODUCTION_BEAM_WIDTH = 16
DEFAULT_ROOT_BEAM_WIDTH = 16
DEFAULT_EFFECT_CHOICE_WIDTH = 64
DEFAULT_ROOT_PROBE_NODES = 96
DEFAULT_ROOT_REFINEMENT_WIDTH = 2
SMALL_ROOT_FULL_REFINEMENT_ACTIONS = 3
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
    root_probe_nodes: int = DEFAULT_ROOT_PROBE_NODES
    root_refinement_width: int = DEFAULT_ROOT_REFINEMENT_WIDTH
    chance_max_nodes: int = PRODUCTION_CHANCE_MAX_NODES
    reveal_max_nodes: int = PRODUCTION_REVEAL_MAX_NODES
    max_seconds: float = PRODUCTION_MAX_SECONDS


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


@dataclass(frozen=True)
class SleepEvent:
    """An earlier enabled action suppressed only on its commutative reverse-order path."""

    event: tuple[str, ...]
    footprint: ActionFootprint


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

    def _state(self, state: DecisionState, sleep: tuple[SleepEvent, ...] = ()) -> StateEvaluation:
        key = state.semantic_key
        if key in self._memo:
            self.cache_hits += 1
            return self._memo[key]
        if key in self._active:
            incomplete = Evaluation(-math.inf, Ledger(), False, "semantic cycle")
            return StateEvaluation(-math.inf, None, incomplete, ())
        actions = tuple(sorted(self.provider.actions(state), key=lambda action: action.identity))
        if len(actions) == 1:
            action = actions[0]
            self._active.add(key)
            result = self._action(state, action)
            self._active.remove(key)
            answer = StateEvaluation(result.value, action, result, ((action, result),))
            if result.complete:
                self._memo[key] = answer
            return answer
        if self.nodes >= self.limits.max_nodes:
            incomplete = Evaluation(-math.inf, Ledger(), False, "reference cap")
            return StateEvaluation(-math.inf, None, incomplete, ())
        self.nodes += 1
        self._active.add(key)
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

    def _action(self, state: DecisionState, action: LegalAction,
                sleep: tuple[SleepEvent, ...] = ()) -> Evaluation:
        if action.identity.kind == "end":
            resolve_end = getattr(self.provider, "resolve_end", None)
            if resolve_end is None:
                return Evaluation(0.0, Ledger(), True, "End exact zero")
            node = resolve_end(state, action)
            if node is None:
                return Evaluation(0.0, Ledger(), True, "End exact zero")
            return self._end_transition(state, action, node)
        return self._transition(state, action, self.provider.transition(state, action), sleep)

    def _end_transition(self, before: DecisionState, action: LegalAction, node) -> Evaluation:
        """Value only the forced turn-boundary outcome, without planning the opponent's turn."""
        if isinstance(node, Unknown):
            return Evaluation(-math.inf, Ledger(), False,
                              f"{node.reason}: {node.missing_fact}")
        if isinstance(node, Deterministic):
            ledger = self._ledger(before, node.state, action)
            return Evaluation(ledger.total, ledger, True, "End resolved", decisions=1.0)
        if isinstance(node, Terminal):
            ledger = _combine(self._ledger(before, node.state, action), 0.0, node.ledger)
            return Evaluation(ledger.total, ledger, True, node.result, decisions=1.0)
        if isinstance(node, Chance):
            branches = [(edge, self._end_transition(before, action, edge.node))
                        for edge in node.children]
            if any(not result.complete for _edge, result in branches):
                return Evaluation(-math.inf, Ledger(), False, "incomplete End chance branch")
            return _expected_evaluation(
                ((edge.probability, result) for edge, result in branches),
                reason="expected End value",
                branches=tuple({"label": edge.label, "probability": edge.probability,
                                "value": result.value} for edge, result in branches),
            )
        return Evaluation(-math.inf, Ledger(), False, "End transition unavailable")

    def _transition(self, before: DecisionState, action: LegalAction, node,
                    sleep: tuple[SleepEvent, ...] = ()) -> Evaluation:
        if isinstance(node, Unknown):
            return Evaluation(-math.inf, Ledger(), False,
                              f"{node.reason}: {node.missing_fact}")
        if isinstance(node, Deterministic):
            base = self._ledger(before, node.state, action)
            continuation = self._state(node.state, sleep)
            if not math.isfinite(continuation.value):
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
            branches = [(edge, self._transition(before, action, edge.node, sleep))
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
            evaluated = {edge.label: self._transition(before, action, edge.node, ())
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
        if isinstance(node, Refresh):
            try:
                ledger, diagnostics = self.oracle.refresh_ledger(before, node)
            except (TypeError, ValueError) as exc:
                return Evaluation(-math.inf, Ledger(), False,
                                  f"refresh valuation unavailable: {exc}")
            return Evaluation(ledger.total, ledger, True, "analytic refresh gamble",
                              diagnostics, decisions=1.0)
        if isinstance(node, Chance):
            branches = [(edge, self._transition(before, action, edge.node, ()))
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

    There is no depth horizon and no second action policy. Width/state capacity are explicit. At a
    capped state where End is legal, exact-zero End is a valid lower bound. Every root receives an
    equal probe; the strongest few incomplete roots receive the expensive refinement pass.
    """

    def __init__(self, provider: TransitionProvider, oracle: ValueOracle, *, model_factory=None,
                 limits: ProductionLimits = ProductionLimits()):
        super().__init__(provider, oracle, model_factory=model_factory,
                         limits=SearchLimits(limits.max_nodes))
        self.production_limits = limits
        self._root_key = ""
        self._root_branch_nodes: list[int] = []
        self._root_branch_capped: list[bool] = []
        self._deadline = math.inf
        self._root_probe_active = False
        self._por_memo: dict[tuple[str, tuple[tuple[str, ...], ...]], StateEvaluation] = {}
        self.por_pruned = 0

    def decide(self, state: DecisionState) -> RootDecision:
        self._root_key = state.semantic_key
        self._root_branch_nodes = []
        self._root_branch_capped = []
        self._por_memo.clear()
        self.por_pruned = 0
        self._deadline = monotonic() + max(0.0, self.production_limits.max_seconds)
        decision = super().decide(state)
        diagnostics = dict(decision.diagnostics)
        diagnostics["production"] = {
            "beam_width": self.production_limits.beam_width,
            "root_beam_width": self.production_limits.root_beam_width,
            "effect_choice_width": self.production_limits.effect_choice_width,
            "root_probe_nodes": self.production_limits.root_probe_nodes,
            "root_refinement_width": self.production_limits.root_refinement_width,
            "max_nodes": self.production_limits.max_nodes,
            "chance_max_nodes": self.production_limits.chance_max_nodes,
            "reveal_max_nodes": self.production_limits.reveal_max_nodes,
            "max_seconds": self.production_limits.max_seconds,
            "max_nodes_per_refined_root_action": (
                self.production_limits.root_probe_nodes
                + self.production_limits.max_nodes - 1),
            "root_branch_nodes": tuple(self._root_branch_nodes),
            "root_branch_capped": tuple(self._root_branch_capped),
            "cap_reached": any(self._root_branch_capped),
            "lower_bound": not decision.complete,
            "commutative_permutations_pruned": self.por_pruned,
        }
        return RootDecision(decision.chosen, decision.action, decision.value,
                            decision.complete, diagnostics)

    def _footprint(self, state: DecisionState, action: LegalAction) -> ActionFootprint | None:
        footprint = getattr(self.provider, "footprint", None)
        return footprint(state, action) if footprint is not None else None

    @staticmethod
    def _sleep_key(sleep: tuple[SleepEvent, ...]) -> tuple[tuple[str, ...], ...]:
        return tuple(sorted((event.event for event in sleep)))

    def _successor_sleep(self, sleep: tuple[SleepEvent, ...], earlier: list[ActionFootprint],
                         current: ActionFootprint | None) -> tuple[SleepEvent, ...]:
        if current is None or current.barrier:
            return ()
        retained = [event for event in sleep if independent(event.footprint, current)]
        retained.extend(SleepEvent(footprint.event, footprint)
                        for footprint in earlier if independent(footprint, current))
        by_event = {event.event: event for event in retained}
        return tuple(by_event[event] for event in sorted(by_event))

    def _state(self, state: DecisionState,
               sleep: tuple[SleepEvent, ...] = ()) -> StateEvaluation:
        key = state.semantic_key
        sleep_key = self._sleep_key(sleep)
        memo_key = (key, sleep_key)
        memo = self._por_memo if sleep else self._memo
        lookup_key = memo_key if sleep else key
        if lookup_key in memo:
            self.cache_hits += 1
            return memo[lookup_key]
        if memo_key in self._active:
            incomplete = Evaluation(-math.inf, Ledger(), False, "semantic cycle")
            return StateEvaluation(-math.inf, None, incomplete, ())

        actions = tuple(sorted(self.provider.actions(state), key=lambda action: action.identity))
        if len(actions) == 1:
            action = actions[0]
            self._active.add(memo_key)
            result = self._action(state, action, sleep)
            self._active.remove(memo_key)
            answer = StateEvaluation(result.value, action, result, ((action, result),))
            if result.complete:
                memo[lookup_key] = answer
            return answer

        if (self.nodes >= self.limits.max_nodes
                or (not self._root_probe_active and monotonic() >= self._deadline)):
            end = next((action for action in actions if action.identity.kind == "end"), None)
            if end is not None:
                lower = Evaluation(0.0, Ledger(), False, "production cap: End lower bound")
                return StateEvaluation(0.0, end, lower, ((end, lower),))
            incomplete = Evaluation(-math.inf, Ledger(), False, "production state cap")
            return StateEvaluation(-math.inf, None, incomplete, ())

        self.nodes += 1
        self._active.add(memo_key)
        actor = self.provider.actor(state)
        context = int(((state.obs.get("select") or {}).get("context", -1)))
        footprints: dict[object, ActionFootprint | None] = {}
        if actor is Actor.OURS and context == MAIN_DECISION_CONTEXT:
            footprints = {action.identity: self._footprint(state, action) for action in actions}
            asleep = {event.event for event in sleep}
            filtered = tuple(action for action in actions
                             if footprints[action.identity] is None
                             or footprints[action.identity].event not in asleep)
            self.por_pruned += len(actions) - len(filtered)
            actions = filtered
        if actor is Actor.OURS:
            width = (self.production_limits.root_beam_width if key == self._root_key
                     else self.production_limits.beam_width if context == MAIN_DECISION_CONTEXT
                     else self.production_limits.effect_choice_width)
            non_end_count = sum(action.identity.kind != "end" for action in actions)
            if non_end_count > width:
                end = next((action for action in actions if action.identity.kind == "end"), None)
                if end is not None:
                    self._active.remove(memo_key)
                    lower = Evaluation(0.0, Ledger(), False,
                                       "production width cap: End lower bound")
                    return StateEvaluation(0.0, end, lower, ((end, lower),))
                # A forced effect selection has no legal End action.  Applying the optional-menu
                # beam here would manufacture an illegal "no decision" outcome.  Evaluate its
                # declared actions with the same Bellman backup; the node cap still bounds work.

        actor = self.provider.actor(state)
        child_sleeps: dict[object, tuple[SleepEvent, ...]] = {}
        if actor is Actor.OURS and context == MAIN_DECISION_CONTEXT:
            earlier = []
            for action in actions:
                footprint = footprints.get(action.identity)
                child_sleeps[action.identity] = self._successor_sleep(sleep, earlier, footprint)
                if footprint is not None and not footprint.barrier:
                    earlier.append(footprint)
        else:
            child_sleeps = {action.identity: sleep for action in actions}
        if key == self._root_key:
            results_list = []
            branch_nodes = []
            branch_capped = []
            original_limits = self.limits
            probe_nodes = min(
                self.production_limits.max_nodes,
                max(1, self.production_limits.root_probe_nodes),
            )
            self.limits = SearchLimits(probe_nodes)
            self._root_probe_active = True
            for action in actions:
                self.nodes = 1
                result = self._action(state, action, child_sleeps[action.identity])
                branch_nodes.append(self.nodes)
                branch_capped.append(not result.complete and self.nodes >= probe_nodes)
                results_list.append((action, result))
            self._root_probe_active = False
            self._deadline = monotonic() + max(0.0, self.production_limits.max_seconds)

            # Successive halving allocates the expensive pass by observed Bellman continuation
            # value.  Every legal choice receives the same probe, while exact probe results need no
            # further work.  This shapes width, never turn depth or action semantics.
            incomplete = [
                (index, action, result)
                for index, (action, result) in enumerate(results_list)
                if not result.complete
            ]
            incomplete.sort(
                key=lambda row: _ordered_evaluation(row[2], actor),
                reverse=actor is Actor.OURS,
            )
            refinement_width = (len(actions)
                                if (self.production_limits.root_refinement_width
                                    == DEFAULT_ROOT_REFINEMENT_WIDTH
                                    and len(actions) <= SMALL_ROOT_FULL_REFINEMENT_ACTIONS)
                                else self.production_limits.root_refinement_width)
            selected = incomplete[:max(0, refinement_width)]
            for uncertainty_type in (Chance, RevealChoice):
                if (selected
                        and not any(isinstance(self.provider.transition(state, row[1]),
                                               uncertainty_type)
                                    for row in selected)):
                    uncertainty_candidate = next(
                        (row for row in incomplete
                         if (isinstance(self.provider.transition(state, row[1]), uncertainty_type)
                             and abs(float(row[2].value) - float(incomplete[0][2].value))
                             <= UNCERTAINTY_REFINEMENT_VALUE_MARGIN)),
                        None,
                    )
                    if uncertainty_candidate is not None:
                        replacement = next(
                            (position for position in range(len(selected) - 1, -1, -1)
                             if not isinstance(self.provider.transition(
                                 state, selected[position][1]), (Chance, RevealChoice))),
                            None,
                        )
                        if replacement is not None:
                            selected[replacement] = uncertainty_candidate
            for index, action, probe in selected:
                transition = self.provider.transition(state, action)
                if isinstance(transition, RevealChoice):
                    refinement_nodes = self.production_limits.reveal_max_nodes
                elif isinstance(transition, Chance):
                    refinement_nodes = self.production_limits.chance_max_nodes
                else:
                    refinement_nodes = self.production_limits.max_nodes
                self.limits = SearchLimits(refinement_nodes)
                self.nodes = 1
                refined = self._action(state, action, child_sleeps[action.identity])
                branch_nodes[index] += max(0, self.nodes - 1)
                branch_capped[index] = (
                    not refined.complete and self.nodes >= refinement_nodes)
                if (math.isfinite(refined.value)
                        and ((actor is Actor.OURS and _ordered_evaluation(refined, actor)
                              >= _ordered_evaluation(probe, actor))
                             or (actor is Actor.OPPONENT and _ordered_evaluation(refined, actor)
                                 <= _ordered_evaluation(probe, actor)))):
                    results_list[index] = (action, refined)

            self._root_branch_nodes.extend(branch_nodes)
            self._root_branch_capped.extend(branch_capped)
            self.limits = original_limits
            self.nodes = 1 + sum(max(0, count - 1) for count in branch_nodes)
            results = tuple(results_list)
        else:
            results_list = []
            for action in actions:
                result = self._action(state, action, child_sleeps[action.identity])
                results_list.append((action, result))
            results = tuple(results_list)
        self._active.remove(memo_key)
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
            memo[lookup_key] = answer
        return answer


__all__ = (
    "Evaluation", "ProductionLimits", "ProductionSolver", "ReferenceSolver", "SearchLimits",
    "StateEvaluation", "TransitionProvider",
)
