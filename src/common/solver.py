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
from .api import PlanStep, RootDecision
from .budget_prototype import FairBudgetPrototype
from .commutativity import ActionFootprint, independent
from .options import LegalAction
from .needs import StrategyBeamBuilder, semantic_action_key
from .pilot_profile import DEFAULT_PILOT_PROFILE, PilotProfile
from .state import DecisionState
from .strategy.context import _DISCARD
from .value import ValueOracle


REFERENCE_MAX_NODES = 100_000
PRODUCTION_MAX_NODES = int(DEFAULT_PILOT_PROFILE.get("search.max_nodes"))
PRODUCTION_CHANCE_MAX_NODES = int(DEFAULT_PILOT_PROFILE.get("search.chance_max_nodes"))
PRODUCTION_REVEAL_MAX_NODES = int(DEFAULT_PILOT_PROFILE.get("search.reveal_max_nodes"))
UNCERTAINTY_REFINEMENT_VALUE_MARGIN = DEFAULT_PILOT_PROFILE.get("search.uncertainty_margin")
ROOT_PROBE_TIME_SHARE = 0.4
PRODUCTION_MAX_SECONDS = DEFAULT_PILOT_PROFILE.get("clock.remaining_200_seconds")
PRODUCTION_BEAM_WIDTH = int(DEFAULT_PILOT_PROFILE.get("search.beam_width"))
DEFAULT_ROOT_BEAM_WIDTH = int(DEFAULT_PILOT_PROFILE.get("search.root_beam_width"))
DEFAULT_EFFECT_CHOICE_WIDTH = int(DEFAULT_PILOT_PROFILE.get("search.effect_choice_width"))
DEFAULT_ROOT_PROBE_NODES = int(DEFAULT_PILOT_PROFILE.get("search.shallow_nodes"))
DEFAULT_ROOT_REFINEMENT_WIDTH = int(DEFAULT_PILOT_PROFILE.get("search.refinement_width"))
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
    continuation: tuple[PlanStep, ...] = ()


@dataclass(frozen=True)
class StateEvaluation:
    value: float
    action: LegalAction | None
    evaluation: Evaluation
    alternatives: tuple[tuple[LegalAction, Evaluation], ...]


@dataclass(frozen=True)
class SleepEvent:
    """An action suppressed on a reverse-order path by a structural proof."""

    event: tuple[str, ...]
    footprint: ActionFootprint
    persistent: bool = False
    proof_type: str = "commutativity"


def _combine(base: Ledger, continuation: float, extra: Ledger = Ledger()) -> Ledger:
    return Ledger(base.benefits + extra.benefits, base.costs + extra.costs,
                  base.continuation + extra.immediate + float(continuation))


def _ordered_evaluation(result: Evaluation, actor: Actor) -> tuple[float, bool, float]:
    """Bellman utility first; on an exact tie, prefer the shorter continuation.

    This is a lexicographic objective, not a small magic penalty that can overturn real utility.
    Both actors avoid redundant decisions after optimizing their opposing primary utilities.
    """
    value = (round(result.value, VALUE_TIE_DECIMALS)
             if math.isfinite(result.value) else result.value)
    decision_order = 0.0
    if result.complete:
        decision_order = -float(result.decisions) if actor is Actor.OURS else float(result.decisions)
    return value, bool(result.complete), decision_order


def _select_our_action(finite, context: int):
    if context == _DISCARD and any(not result.complete for _action, result in finite):
        immediate = max(result.ledger.immediate for _action, result in finite)
        leaders = tuple(
            pair for pair in finite
            if round(pair[1].ledger.immediate, VALUE_TIE_DECIMALS)
            == round(immediate, VALUE_TIE_DECIMALS)
        )
        return min(leaders, key=lambda pair: str(pair[0].identity))
    return max(finite, key=lambda pair: _ordered_evaluation(pair[1], Actor.OURS))


def _commutative_order(action: LegalAction):
    priority = {"evolve": 0, "attach": 1}
    return priority.get(action.identity.kind, 2), action.identity


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
        self._transitions = {}
        self.nodes = 0
        self.cache_hits = 0

    def decide(self, state: DecisionState) -> RootDecision:
        self._memo.clear()
        self._active.clear()
        self._transitions.clear()
        self.nodes = self.cache_hits = 0
        self._root_key = state.semantic_key
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
            plan_suffix=solved.evaluation.continuation,
        )

    def _continuation_steps(self, before: DecisionState, action: LegalAction,
                            after: DecisionState,
                            continuation: StateEvaluation) -> tuple[PlanStep, ...]:
        return ()

    def _reveal_choices(self, before: DecisionState, node: RevealChoice):
        return node.choices

    def _models(self, before: DecisionState, after: DecisionState):
        if self.model_factory is None:
            return None, None
        return self.model_factory(before), self.model_factory(after)

    def _ledger(self, before: DecisionState, after: DecisionState, action: LegalAction) -> Ledger:
        left, right = self._models(before, after)
        return self.oracle.transition_ledger(before, after, action.identity,
                                             before_model=left, after_model=right)

    def _provider_transition(self, state: DecisionState, action: LegalAction):
        key = state.semantic_key, action.identity
        if key not in self._transitions:
            self._transitions[key] = self.provider.transition(state, action)
        return self._transitions[key]

    def _state(self, state: DecisionState, sleep: tuple[SleepEvent, ...] = ()) -> StateEvaluation:
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
        return self._transition(state, action, self._provider_transition(state, action), sleep)

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
            if continuation.action is None and not continuation.evaluation.complete:
                return Evaluation(-math.inf, base, False, continuation.evaluation.reason)
            ledger = _combine(base, continuation.value)
            steps = self._continuation_steps(before, action, node.state, continuation)
            return Evaluation(ledger.total, ledger, continuation.evaluation.complete,
                              continuation.evaluation.reason, decisions=(
                                  1.0 + continuation.evaluation.decisions), continuation=steps)
        if isinstance(node, Terminal):
            base = self._ledger(before, node.state, action)
            ledger = _combine(base, 0.0, node.ledger)
            return Evaluation(ledger.total, ledger, True, node.result, decisions=1.0)
        if isinstance(node, Choice):
            branches = [(edge, self._transition(before, action, edge.node, sleep))
                        for edge in node.children]
            finite = [(edge, result) for edge, result in branches if math.isfinite(result.value)]
            if (not finite
                    or (node.actor is Actor.OPPONENT and len(finite) != len(branches))):
                return Evaluation(-math.inf, Ledger(), False, "incomplete choice branch",
                                  tuple({"label": edge.label, "complete": result.complete,
                                         "value": result.value, "reason": result.reason}
                                        for edge, result in branches))
            chooser = max if node.actor is Actor.OURS else min
            edge, result = chooser(
                finite, key=lambda pair: _ordered_evaluation(pair[1], node.actor))
            proven = (len(finite) == len(branches)
                      and all(evaluated.complete for _child, evaluated in branches))
            return Evaluation(result.value, result.ledger, proven,
                              (result.reason if result.reason == TERMINAL_WIN_REASON
                               else f"{node.actor.value} chose {edge.label}"),
                              tuple({"label": child.label, "value": evaluated.value,
                                     "complete": evaluated.complete}
                                    for child, evaluated in branches), result.decisions)
        if isinstance(node, RevealChoice):
            evaluated = {edge.label: self._transition(before, action, edge.node, ())
                         for edge in self._reveal_choices(before, node)}
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
                ledger, diagnostics = self.oracle.refresh_ledger(
                    before, node, include_next_turn=before.semantic_key == self._root_key)
            except (TypeError, ValueError) as exc:
                return Evaluation(-math.inf, Ledger(), False,
                                  f"refresh valuation unavailable: {exc}")
            continuation = self._guaranteed_refresh_continuation(before)
            combined = _combine(ledger, continuation.value)
            return Evaluation(combined.total, combined, True, "analytic refresh gamble",
                              diagnostics, decisions=1.0 + continuation.decisions)
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

    def _guaranteed_refresh_continuation(self, state: DecisionState) -> Evaluation:
        candidates = []
        for action in self.provider.actions(state):
            if (action.identity.kind != "attack"
                    or not self.oracle.refresh_attack_independent(state, action)):
                continue
            result = self._end_transition(state, action, self._provider_transition(state, action))
            if result.complete and math.isfinite(result.value):
                candidates.append(result)
        return max(candidates, key=lambda result: _ordered_evaluation(result, Actor.OURS),
                   default=Evaluation(0.0, Ledger(), True, "no guaranteed attack"))


class ProductionSolver(ReferenceSolver):
    """Bounded search over the reference transition/value contracts.

    There is no depth horizon and no second action policy. Width/state capacity are explicit. At a
    capped state where End is legal, exact-zero End is a valid lower bound. Every root receives an
    equal probe; the strongest few incomplete roots receive the expensive refinement pass.
    """

    def __init__(self, provider: TransitionProvider, oracle: ValueOracle, *, model_factory=None,
                 limits: ProductionLimits = ProductionLimits(),
                 profile: PilotProfile = DEFAULT_PILOT_PROFILE, needs_snapshot=None):
        super().__init__(provider, oracle, model_factory=model_factory,
                         limits=SearchLimits(limits.max_nodes))
        self.production_limits = limits
        self.profile = profile
        self.needs_snapshot = needs_snapshot
        self._root_key = ""
        self._root_branch_nodes: list[int] = []
        self._root_branch_capped: list[bool] = []
        self._deadline = math.inf
        self._hard_deadline = math.inf
        self._budget = FairBudgetPrototype(limits.max_seconds)
        self._por_memo: dict[tuple[str, tuple[tuple[str, ...], ...]], StateEvaluation] = {}
        self._diamond_cache: dict[tuple[str, tuple[str, ...], tuple[str, ...]], bool] = {}
        self.por_pruned = 0
        self.information_pruned = 0
        self._structural_prunes: list[dict] = []
        self._need_builder = None
        self._need_beams = {}
        self._need_waves = {}
        self._need_focus_ranks = {}
        self._need_later_wave = {}
        self._need_clock_scale = 1.0
        self._completed_rounds = 0
        self._bound_prunes: list[dict] = []
        self._action_bounds: dict[object, dict] = {}
        self._deadline_hit = False

    def decide(self, state: DecisionState) -> RootDecision:
        self._root_key = state.semantic_key
        self._root_branch_nodes = []
        self._root_branch_capped = []
        self._por_memo.clear()
        self._diamond_cache.clear()
        self.por_pruned = 0
        self.information_pruned = 0
        self._structural_prunes.clear()
        self._need_beams.clear()
        self._need_waves.clear()
        self._need_focus_ranks.clear()
        self._need_later_wave.clear()
        self._need_clock_scale = 1.0
        self._need_builder = None
        if (self.needs_snapshot is not None
                and self.profile.get("needs.focus_enabled") >= 0.5):
            self._need_builder = StrategyBeamBuilder(
                self.needs_snapshot, effects=self.oracle.effects, stats=self.oracle.stats,
                width=self.profile.get("needs.focus_width"))
        self._completed_rounds = 0
        self._bound_prunes.clear()
        self._action_bounds.clear()
        self._deadline_hit = False
        self._hard_deadline = self._budget.hard_deadline(monotonic())
        self._deadline = self._hard_deadline
        decision = super().decide(state)
        self._complete_root_bounds(state, decision)
        if self._need_builder is not None and self._root_key not in self._need_beams:
            root_actions = tuple(sorted(self.provider.actions(state), key=lambda row: row.identity))
            self._need_beams[self._root_key] = self._need_builder.build(state, root_actions)
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
            "deadline_hit": self._deadline_hit,
            "lower_bound": not decision.complete,
            "commutative_permutations_pruned": self.por_pruned,
            "information_first_permutations_pruned": self.information_pruned,
            "structural_prunes": tuple(self._structural_prunes),
            "profile_hash": self.profile.hash,
            "completed_rounds": self._completed_rounds,
            "needs_later_wave": len(self._need_later_wave.get(self._root_key, ())),
            "needs_clock_scale": self._need_clock_scale,
            "family_candidates": (),
            "bound_prunes": tuple(self._bound_prunes),
            "action_bounds": tuple(self._action_bounds.values()),
        }
        if self._root_key in self._need_beams:
            diagnostics["needs"] = self._need_beams[self._root_key]
        if self.needs_snapshot is not None:
            diagnostics["needs_snapshot"] = self.needs_snapshot
        diagnostics["odds"] = {
            "enabled": True,
            "marginal_access": (dict(getattr(self._need_builder, "last_odds", {}))
                                if self._need_builder is not None else {}),
        }
        return RootDecision(decision.chosen, decision.action, decision.value,
                            decision.complete, diagnostics, decision.plan_suffix)

    def _continuation_steps(self, before: DecisionState, action: LegalAction,
                            after: DecisionState,
                            continuation: StateEvaluation) -> tuple[PlanStep, ...]:
        if (continuation.action is None or not math.isfinite(continuation.value)
                or self.provider.actor(after) is not Actor.OURS):
            return ()
        before_current = before.obs.get("current") or {}
        after_current = after.obs.get("current") or {}
        if int(before_current.get("turn", 0)) != int(after_current.get("turn", 0)):
            return ()
        footprint = self._footprint(before, action)
        if footprint is not None and footprint.barrier:
            return ()
        step = PlanStep(
            after.plan_key, after.legal_menu_digest, continuation.action.selection,
            continuation.action.identity, self.profile.hash,
            int(after_current.get("turn", 0)), int(after_current.get("yourIndex", 0)),
            continuation.value,
        )
        return (step,) + continuation.evaluation.continuation

    def _reveal_choices(self, before: DecisionState, node: RevealChoice):
        def priority(edge):
            child = edge.node
            state = child.state if isinstance(child, (Deterministic, Terminal)) else None
            need = (self.oracle.reveal_choice_priority(before, state)
                    if state is not None else 0.0)
            return edge.label != "decline", -need, edge.label

        return tuple(sorted(node.choices, key=priority))

    def _footprint(self, state: DecisionState, action: LegalAction) -> ActionFootprint | None:
        footprint = getattr(self.provider, "footprint", None)
        return footprint(state, action) if footprint is not None else None

    def _information_priority(self, state: DecisionState, action: LegalAction) -> float:
        if self._need_builder is not None:
            return self._need_builder.action_priority(state, action)
        node = self._provider_transition(state, action)
        return self.oracle.reveal_node_priority(state, node) if isinstance(node, RevealChoice) else 0.0

    def _immediate_order_value(self, state: DecisionState, action: LegalAction) -> float:
        node = self._provider_transition(state, action)
        if isinstance(node, Deterministic):
            return self._ledger(state, node.state, action).immediate
        if isinstance(node, Terminal):
            return _combine(self._ledger(state, node.state, action), 0.0,
                            node.ledger).immediate
        return -math.inf

    @staticmethod
    def _sleep_key(sleep: tuple[SleepEvent, ...]) -> tuple[tuple[str, ...], ...]:
        return tuple(sorted((("persistent" if event.persistent else "commutative", *event.event)
                             for event in sleep)))

    def _action_with_event(self, state: DecisionState, event: tuple[str, ...]):
        for action in self.provider.actions(state):
            footprint = self._footprint(state, action)
            if footprint is not None and footprint.event == event:
                return action, footprint
        return None, None

    def _diamond_commutes(self, state: DecisionState, left: LegalAction,
                          right: LegalAction, left_footprint: ActionFootprint,
                          right_footprint: ActionFootprint) -> bool:
        events = tuple(sorted((left_footprint.event, right_footprint.event)))
        key = (state.semantic_key, *events)
        if key in self._diamond_cache:
            return self._diamond_cache[key]
        answer = False
        left_node = self._provider_transition(state, left)
        right_node = self._provider_transition(state, right)
        if isinstance(left_node, Deterministic) and isinstance(right_node, Deterministic):
            right_after_left, _ = self._action_with_event(
                left_node.state, right_footprint.event)
            left_after_right, _ = self._action_with_event(
                right_node.state, left_footprint.event)
            if right_after_left is not None and left_after_right is not None:
                left_then_right = self._provider_transition(left_node.state, right_after_left)
                right_then_left = self._provider_transition(right_node.state, left_after_right)
                if isinstance(left_then_right, Deterministic) and isinstance(
                        right_then_left, Deterministic):
                    x, y = left_then_right.state, right_then_left.state
                    answer = (
                        x.semantic_key == y.semantic_key
                        and x.legal_menu_digest == y.legal_menu_digest
                        and self.provider.actor(x) is self.provider.actor(y)
                    )
        self._diamond_cache[key] = answer
        return answer

    def _commutes(self, state: DecisionState, left: LegalAction, right: LegalAction,
                  left_footprint: ActionFootprint,
                  right_footprint: ActionFootprint) -> tuple[bool, str]:
        if independent(left_footprint, right_footprint):
            return True, "commutativity"
        if left.identity.kind == "end" or right.identity.kind == "end":
            return False, ""
        if left_footprint.event == right_footprint.event:
            return False, ""
        if self._diamond_commutes(state, left, right, left_footprint, right_footprint):
            return True, "diamond_commutativity"
        return False, ""

    def _successor_sleep(self, state: DecisionState, sleep: tuple[SleepEvent, ...],
                         earlier: list[tuple[LegalAction, ActionFootprint]],
                         current_action: LegalAction,
                         current: ActionFootprint | None) -> tuple[SleepEvent, ...]:
        if current is None:
            return ()
        retained = []
        for event in sleep:
            sleeping_action, sleeping_footprint = self._action_with_event(state, event.event)
            if sleeping_action is None:
                continue
            commutes, proof_type = self._commutes(
                state, sleeping_action, current_action, sleeping_footprint, current)
            if commutes:
                retained.append(SleepEvent(
                    event.event, sleeping_footprint, event.persistent,
                    proof_type or event.proof_type))
        for action, footprint in earlier:
            commutes, proof_type = self._commutes(
                state, action, current_action, footprint, current)
            if commutes:
                retained.append(SleepEvent(footprint.event, footprint, False, proof_type))
        by_event = {event.event: event for event in retained}
        return tuple(by_event[event] for event in sorted(by_event))

    def _end_lower_bound(self, state: DecisionState, actions, reason: str) -> StateEvaluation:
        end = next((action for action in actions if action.identity.kind == "end"), None)
        if end is None:
            incomplete = Evaluation(-math.inf, Ledger(), False, reason)
            return StateEvaluation(-math.inf, None, incomplete, ())
        exact = self._action(state, end)
        if not math.isfinite(exact.value):
            return StateEvaluation(-math.inf, None, exact, ((end, exact),))
        lower = Evaluation(
            exact.value, exact.ledger, False, reason, exact.branches,
            exact.decisions, exact.continuation)
        return StateEvaluation(lower.value, end, lower, ((end, lower),))

    def _node_upper_bound(self, before: DecisionState, action: LegalAction, node) -> tuple[float, dict]:
        if isinstance(node, Unknown):
            return math.inf, {"unknown": node.missing_fact}
        if isinstance(node, Refresh):
            return math.inf, {"unknown": "analytic refresh"}
        if isinstance(node, Terminal):
            ledger = _combine(self._ledger(before, node.state, action), 0.0, node.ledger)
            return ledger.total, {"delta_v_upper": ledger.total, "continuation": 0.0,
                                  "reachable_upper": 0.0}
        if isinstance(node, Deterministic):
            delta = self._ledger(before, node.state, action).total
            continuation = self.oracle.continuation_upper_bound(node.state)
            value = delta + continuation
            return value, {"delta_v_upper": delta, "continuation": continuation,
                           "reachable_upper": continuation}
        if isinstance(node, Chance):
            rows = tuple((edge.probability, *self._node_upper_bound(before, action, edge.node))
                         for edge in node.children if edge.probability > 0.0)
            if not rows or any(not math.isfinite(value) for _probability, value, _terms in rows):
                return math.inf, {"unknown": "chance child bound"}
            return sum(probability * value for probability, value, _terms in rows), {
                "chance": tuple({"probability": probability, "upper": value}
                                for probability, value, _terms in rows)}
        if isinstance(node, Choice):
            rows = tuple(self._node_upper_bound(before, action, edge.node)
                         for edge in node.children)
            if not rows or any(not math.isfinite(value) for value, _terms in rows):
                return math.inf, {"unknown": "choice child bound"}
            return max(value for value, _terms in rows), {
                "choice": tuple(value for value, _terms in rows)}
        if isinstance(node, RevealChoice):
            by_label = {edge.label: self._node_upper_bound(before, action, edge.node)
                        for edge in node.choices}
            if any(not math.isfinite(value) for value, _terms in by_label.values()):
                return math.inf, {"unknown": "reveal child bound"}
            value = sum(outcome.probability * max(by_label[label][0]
                                                  for label in outcome.choices)
                        for outcome in node.outcomes)
            return value, {"reveal": tuple(
                {"probability": outcome.probability,
                 "upper": max(by_label[label][0] for label in outcome.choices)}
                for outcome in node.outcomes)}
        return math.inf, {"unknown": "undeclared transition"}

    def _root_upper_bound(self, state: DecisionState, action: LegalAction) -> tuple[float, dict]:
        value, terms = self._node_upper_bound(state, action, self._provider_transition(state, action))
        diagnostic = {"state": state.semantic_key, "action": str(action.identity),
                      "q_upper": value, **terms}
        bound_key = (state.semantic_key, action.identity)
        self._action_bounds[bound_key] = diagnostic
        if state.semantic_key == self._root_key:
            self._action_bounds[action.identity] = self._action_bounds.pop(bound_key)
        return value, diagnostic

    def _complete_root_bounds(self, state: DecisionState, decision: RootDecision) -> None:
        root = decision.diagnostics["root"]
        evaluated = {row.action_key: row for row in root.alternatives}
        actions = tuple(sorted(self.provider.actions(state), key=lambda row: row.identity))
        for action in actions:
            key = str(action.identity)
            row = self._action_bounds.get(action.identity, {
                "state": state.semantic_key, "action": key})
            if key == root.chosen_key:
                q_lower = decision.value
                complete = decision.complete
            elif key in evaluated:
                q_lower = evaluated[key].ledger.total
                complete = evaluated[key].complete
            else:
                q_lower = -math.inf
                complete = False
            if "q_upper" not in row:
                if complete:
                    row["q_upper"] = q_lower
                    row.update({"delta_v_upper": q_lower, "continuation": 0.0,
                                "reachable_upper": 0.0})
                else:
                    _upper, row = self._root_upper_bound(state, action)
            row.update({
                "q_lower": q_lower,
                "complete": complete,
                "search_wave": self._need_waves.get(state.semantic_key, {}).get(action, 0),
            })
            self._action_bounds[action.identity] = row

    def _state(self, state: DecisionState,
               sleep: tuple[SleepEvent, ...] = ()) -> StateEvaluation:
        now = monotonic()
        if self.nodes >= self.limits.max_nodes or now >= self._deadline:
            self._deadline_hit = self._deadline_hit or now >= self._deadline
            actions = tuple(sorted(self.provider.actions(state), key=lambda action: action.identity))
            return self._end_lower_bound(state, actions, "production cap: exact End lower bound")

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

        self.nodes += 1
        self._active.add(memo_key)
        actions = tuple(sorted(self.provider.actions(state), key=lambda action: action.identity))
        actor = self.provider.actor(state)
        context = int(((state.obs.get("select") or {}).get("context", -1)))
        if actor is Actor.OURS and context == _DISCARD:
            actions = tuple(sorted(
                actions,
                key=lambda action: (-self._immediate_order_value(state, action), action.identity),
            ))
        footprints: dict[object, ActionFootprint | None] = {}
        if actor is Actor.OURS and context == MAIN_DECISION_CONTEXT:
            footprints = {action.identity: self._footprint(state, action) for action in actions}
            asleep = {event.event: event for event in sleep}
            filtered = tuple(action for action in actions
                             if footprints[action.identity] is None
                             or footprints[action.identity].event not in asleep)
            for action in actions:
                footprint = footprints[action.identity]
                if footprint is not None and footprint.event in asleep:
                    sleeping = asleep[footprint.event]
                    proof_type = sleeping.proof_type
                    self._structural_prunes.append({
                        "proof_type": proof_type,
                        "pruned": str(action.identity),
                        "retained_event": sleeping.event,
                    })
                    if sleeping.persistent:
                        self.information_pruned += 1
                    else:
                        self.por_pruned += 1
            actions = filtered
            needs_focus = (key == self._root_key and self._need_builder is not None
                           and self.profile.get("needs.focus_enabled") >= 0.5)
            if needs_focus:
                beam = self._need_builder.build(state, actions)
                self._need_beams[key] = beam
                retained = {row.action_key for row in (*beam.focused, *beam.safety)}
                retained.update(row.action_key for row in beam.unknown)
                self._need_later_wave[key] = tuple(
                    action for action in actions
                    if semantic_action_key(action) not in retained)
                self._need_waves[key] = {
                    action: (0 if semantic_action_key(action) in retained
                             else 1)
                    for action in actions
                }
                self._need_focus_ranks[key] = {
                    row.action_key: index for index, row in enumerate(beam.focused)
                }
                original = {action: index for index, action in enumerate(actions)}
                focus_order = {
                    row.action_key: index for index, row in enumerate(beam.focused)
                }
                information_order = {
                    action: 0
                    for action in actions
                    if footprints[action.identity] is not None
                    and footprints[action.identity].information_first
                    and self._information_priority(state, action) > 0.0
                }
                actions = tuple(sorted(actions, key=lambda action: (
                    information_order.get(action, 1),
                    self._need_waves[key][action],
                    focus_order.get(semantic_action_key(action), len(actions)),
                    original[action],
                )))
        if self.provider.actor(state) is Actor.OURS:
            width = (self.production_limits.root_beam_width if key == self._root_key
                     else self.production_limits.beam_width if context == MAIN_DECISION_CONTEXT
                     else self.production_limits.effect_choice_width)
            non_end_count = sum(action.identity.kind != "end" for action in actions)
            if non_end_count > width:
                end = next((action for action in actions if action.identity.kind == "end"), None)
                if end is not None:
                    self._active.remove(memo_key)
                    return self._end_lower_bound(
                        state, actions, "production width cap: exact End lower bound")
                # A forced effect selection has no legal End action.  Applying the optional-menu
                # beam here would manufacture an illegal "no decision" outcome.  Evaluate its
                # declared actions with the same Bellman backup; the node cap still bounds work.

        actor = self.provider.actor(state)
        child_sleeps: dict[object, tuple[SleepEvent, ...]] = {}
        if actor is Actor.OURS and context == MAIN_DECISION_CONTEXT:
            earlier = []
            for action in sorted(actions, key=_commutative_order):
                footprint = footprints.get(action.identity)
                child_sleeps[action.identity] = self._successor_sleep(
                    state, sleep, earlier, action, footprint)
                if footprint is not None:
                    earlier.append((action, footprint))
        else:
            child_sleeps = {action.identity: sleep for action in actions}
        if key == self._root_key:
            action_waves = self._need_waves.get(key, {})
            results_list = []
            branch_nodes = []
            branch_capped = []
            original_limits = self.limits
            probe_started = monotonic()
            probe_hard_deadline = probe_started + max(
                0.0, self._hard_deadline - probe_started) * ROOT_PROBE_TIME_SHARE
            for index, action in enumerate(actions):
                wave = action_waves.get(action, 0)
                widening = wave > 0
                probe_nodes = min(
                    self.production_limits.max_nodes,
                    max(1, self.production_limits.root_probe_nodes if not widening else 1),
                )
                self.limits = SearchLimits(probe_nodes)
                self._deadline = self._budget.root_deadline(
                    monotonic(), probe_hard_deadline, len(actions) - index)
                self.nodes = 1
                result = self._action(state, action, child_sleeps[action.identity])
                branch_nodes.append(self.nodes)
                branch_capped.append(not result.complete and (
                    self.nodes >= probe_nodes or monotonic() >= self._deadline))
                results_list.append((action, result))
            if results_list:
                self._completed_rounds = 1
            self._deadline = self._hard_deadline

            # Bellman probe values order bounded widening rounds; exact results need no more work.
            incomplete = [
                (index, action, result)
                for index, (action, result) in enumerate(results_list)
                if not result.complete
            ]
            incomplete.sort(
                key=lambda row: _ordered_evaluation(row[2], actor),
                reverse=actor is Actor.OURS,
            )
            if actor is Actor.OURS:
                finite_results = tuple(
                    (action, result) for action, result in results_list
                    if math.isfinite(result.value))
                incumbent = (_select_our_action(finite_results, context)
                             if finite_results else None)
                bounded = []
                for row in incomplete:
                    index, action, _probe = row
                    q_upper, terms = self._root_upper_bound(state, action)
                    if incumbent is None or not math.isfinite(q_upper):
                        bounded.append(row)
                        continue
                    incumbent_action, incumbent_result = incumbent
                    upper_value = round(q_upper, VALUE_TIE_DECIMALS)
                    lower_value = round(incumbent_result.value, VALUE_TIE_DECIMALS)
                    optimistic_decisions = 1.0
                    tie_loses = (
                        optimistic_decisions > incumbent_result.decisions
                        or (optimistic_decisions == incumbent_result.decisions
                            and str(action.identity) >= str(incumbent_action.identity)))
                    if upper_value < lower_value or (upper_value == lower_value and tie_loses):
                        self._bound_prunes.append({
                            "action": str(action.identity), "q_upper": q_upper,
                            "optimistic_decisions": optimistic_decisions,
                            "incumbent": str(incumbent_action.identity),
                            "q_lower": incumbent_result.value,
                            "incumbent_decisions": incumbent_result.decisions,
                            "terms": terms,
                        })
                        branch_capped[index] = False
                        continue
                    bounded.append(row)
                incomplete = bounded
            refinement_width = (len(actions)
                                if (self.production_limits.root_refinement_width
                                    == DEFAULT_ROOT_REFINEMENT_WIDTH
                                    and len(actions) <= SMALL_ROOT_FULL_REFINEMENT_ACTIONS)
                                else self.production_limits.root_refinement_width)
            refinement_width = max(0, refinement_width)
            selected = []
            focus_ranks = self._need_focus_ranks.get(key, {})
            refinement_candidates = sorted(
                incomplete,
                key=lambda row: (
                    action_waves.get(row[1], 0),
                    focus_ranks.get(semantic_action_key(row[1]), len(actions)),
                    tuple(-value if isinstance(value, (int, float)) else value
                          for value in _ordered_evaluation(row[2], actor)),
                    str(row[1].identity),
                ),
            )
            selected.extend(sorted(
                (row for row in refinement_candidates
                 if row not in selected and semantic_action_key(row[1]) in focus_ranks),
                key=lambda row: focus_ranks[semantic_action_key(row[1])],
            ))
            selected.extend(row for row in refinement_candidates if row not in selected)
            selected = selected[:refinement_width]
            for uncertainty_type in (Chance, RevealChoice):
                if (selected
                        and not any(isinstance(self._provider_transition(state, row[1]),
                                               uncertainty_type)
                                    for row in selected)):
                    uncertainty_candidate = next(
                        (row for row in refinement_candidates
                         if (isinstance(self._provider_transition(state, row[1]), uncertainty_type)
                             and abs(float(row[2].value) - float(incomplete[0][2].value))
                             <= UNCERTAINTY_REFINEMENT_VALUE_MARGIN)),
                        None,
                    )
                    if uncertainty_candidate is not None:
                        replacement = next(
                            (position for position in range(len(selected) - 1, -1, -1)
                             if not isinstance(self._provider_transition(
                                 state, selected[position][1]), (Chance, RevealChoice))),
                            None,
                        )
                        if replacement is not None:
                            selected[replacement] = uncertainty_candidate
            ordered_refinements = selected + [
                row for row in refinement_candidates if row not in selected
            ] if refinement_width else []
            for refinement_index, (index, action, probe) in enumerate(ordered_refinements):
                if monotonic() >= self._hard_deadline:
                    break
                self._completed_rounds = max(
                    self._completed_rounds,
                    2 + refinement_index // max(1, refinement_width),
                )
                transition = self._provider_transition(state, action)
                if isinstance(transition, RevealChoice):
                    refinement_nodes = self.production_limits.reveal_max_nodes
                elif isinstance(transition, Chance):
                    refinement_nodes = self.production_limits.chance_max_nodes
                elif semantic_action_key(action) in focus_ranks:
                    refinement_nodes = self.production_limits.reveal_max_nodes
                elif (actor is Actor.OURS and context != MAIN_DECISION_CONTEXT):
                    refinement_nodes = self.production_limits.reveal_max_nodes
                elif (footprints.get(action.identity) is not None
                      and footprints[action.identity].information_first
                      and self._information_priority(state, action) > 0.0):
                    refinement_nodes = self.production_limits.reveal_max_nodes
                else:
                    refinement_nodes = self.production_limits.max_nodes
                self.limits = SearchLimits(refinement_nodes)
                self._deadline = self._budget.root_deadline(
                    monotonic(), self._hard_deadline,
                    len(ordered_refinements) - refinement_index,
                )
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
            self._deadline = self._hard_deadline
            self.nodes = 1 + sum(max(0, count - 1) for count in branch_nodes)
            results = tuple(results_list)
        else:
            results_list = []
            ordered_actions = actions
            if actor is Actor.OURS:
                ordered_actions = tuple(sorted(
                    actions, key=lambda row: (row.identity.kind != "end", row.identity)))
            incumbent = None
            for action in ordered_actions:
                if actor is Actor.OURS and incumbent is not None \
                        and action.identity.kind != "end":
                    q_upper, terms = self._root_upper_bound(state, action)
                    incumbent_action, incumbent_result = incumbent
                    upper_value = round(q_upper, VALUE_TIE_DECIMALS)
                    lower_value = round(incumbent_result.value, VALUE_TIE_DECIMALS)
                    tie_loses = (1.0 > incumbent_result.decisions or (
                        1.0 == incumbent_result.decisions
                        and str(action.identity) >= str(incumbent_action.identity)))
                    if math.isfinite(q_upper) and (
                            upper_value < lower_value
                            or (upper_value == lower_value and tie_loses)):
                        self._bound_prunes.append({
                            "state": state.semantic_key,
                            "action": str(action.identity),
                            "q_upper": q_upper,
                            "optimistic_decisions": 1.0,
                            "incumbent": str(incumbent_action.identity),
                            "q_lower": incumbent_result.value,
                            "incumbent_decisions": incumbent_result.decisions,
                            "terms": terms,
                        })
                        bound = self._action_bounds[(state.semantic_key, action.identity)]
                        bound.update({"q_lower": -math.inf, "complete": False,
                                      "search_wave": 0, "pruned": True})
                        continue
                result = self._action(state, action, child_sleeps[action.identity])
                results_list.append((action, result))
                bound_key = (state.semantic_key, action.identity)
                bound = self._action_bounds.get(bound_key, {
                    "state": state.semantic_key, "action": str(action.identity)})
                if "q_upper" not in bound:
                    if result.complete:
                        bound["q_upper"] = result.value
                    else:
                        _upper, bound = self._root_upper_bound(state, action)
                bound.update({"q_lower": result.value, "complete": result.complete,
                              "search_wave": 0, "pruned": False})
                self._action_bounds[bound_key] = bound
                if actor is Actor.OURS and math.isfinite(result.value):
                    finite_results = tuple(
                        (candidate, evaluated) for candidate, evaluated in results_list
                        if math.isfinite(evaluated.value))
                    incumbent = _select_our_action(finite_results, context)
            results = tuple(results_list)
        self._active.remove(memo_key)
        finite = [(action, result) for action, result in results if math.isfinite(result.value)]
        if not finite or (actor is Actor.OPPONENT and len(finite) != len(results)):
            answer = StateEvaluation(-math.inf, None,
                                     Evaluation(-math.inf, Ledger(), False,
                                                "one or more legal actions incomplete"), results)
        else:
            if actor is Actor.OURS:
                action, result = _select_our_action(finite, context)
            else:
                action, result = min(
                    finite, key=lambda pair: _ordered_evaluation(pair[1], actor))
            proven = result.complete and len(finite) == len(results) and all(
                evaluated.complete for _candidate, evaluated in results)
            evaluation = Evaluation(result.value, result.ledger, proven, result.reason,
                                     result.branches, result.decisions, result.continuation)
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
