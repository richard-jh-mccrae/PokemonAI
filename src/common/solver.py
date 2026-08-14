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
from .commutativity import ActionFootprint, independent, information_precedes
from .options import LegalAction
from .family_ranking import FAMILIES, FamilyRanking, apply_family_ordering, rank_actions
from .pilot_profile import DEFAULT_PILOT_PROFILE, PilotProfile
from .state import DecisionState
from .strategy.context import _DISCARD
from .value import ValueOracle


REFERENCE_MAX_NODES = 100_000
PRODUCTION_MAX_NODES = int(DEFAULT_PILOT_PROFILE.get("search.max_nodes"))
PRODUCTION_CHANCE_MAX_NODES = int(DEFAULT_PILOT_PROFILE.get("search.chance_max_nodes"))
PRODUCTION_REVEAL_MAX_NODES = int(DEFAULT_PILOT_PROFILE.get("search.reveal_max_nodes"))
UNCERTAINTY_REFINEMENT_VALUE_MARGIN = DEFAULT_PILOT_PROFILE.get("search.uncertainty_margin")
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


def _select_our_action(finite, context: int):
    if context == _DISCARD and all(not result.complete for _action, result in finite):
        immediate = max(result.ledger.immediate for _action, result in finite)
        leaders = tuple(
            pair for pair in finite
            if round(pair[1].ledger.immediate, VALUE_TIE_DECIMALS)
            == round(immediate, VALUE_TIE_DECIMALS)
        )
        return min(leaders, key=lambda pair: str(pair[0].identity))
    return max(finite, key=lambda pair: _ordered_evaluation(pair[1], Actor.OURS))


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
                 limits: ProductionLimits = ProductionLimits(),
                 profile: PilotProfile = DEFAULT_PILOT_PROFILE):
        super().__init__(provider, oracle, model_factory=model_factory,
                         limits=SearchLimits(limits.max_nodes))
        self.production_limits = limits
        self.profile = profile
        self._root_key = ""
        self._root_branch_nodes: list[int] = []
        self._root_branch_capped: list[bool] = []
        self._deadline = math.inf
        self._hard_deadline = math.inf
        self._budget = FairBudgetPrototype(limits.max_seconds)
        self._por_memo: dict[tuple[str, tuple[tuple[str, ...], ...]], StateEvaluation] = {}
        self.por_pruned = 0
        self.information_pruned = 0
        self._structural_prunes: list[dict] = []
        self._family_rankings: dict[str, FamilyRanking] = {}
        self._completed_rounds = 0

    def decide(self, state: DecisionState) -> RootDecision:
        self._root_key = state.semantic_key
        self._root_branch_nodes = []
        self._root_branch_capped = []
        self._por_memo.clear()
        self.por_pruned = 0
        self.information_pruned = 0
        self._structural_prunes.clear()
        self._family_rankings.clear()
        self._completed_rounds = 0
        self._hard_deadline = self._budget.hard_deadline(monotonic())
        self._deadline = self._hard_deadline
        decision = super().decide(state)
        if self._root_key not in self._family_rankings:
            root_actions = tuple(sorted(self.provider.actions(state), key=lambda row: row.identity))
            self._family_rankings[self._root_key] = rank_actions(
                state, root_actions, self.provider, self.oracle, self.profile)
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
            "information_first_permutations_pruned": self.information_pruned,
            "structural_prunes": tuple(self._structural_prunes),
            "profile_hash": self.profile.hash,
            "completed_rounds": self._completed_rounds,
            "family_candidates": tuple(
                candidate.diagnostic()
                for candidate in self._family_rankings.get(self._root_key, FamilyRanking((), (), ())).candidates
            ),
        }
        return RootDecision(decision.chosen, decision.action, decision.value,
                            decision.complete, diagnostics, decision.plan_suffix)

    def _continuation_steps(self, before: DecisionState, action: LegalAction,
                            after: DecisionState,
                            continuation: StateEvaluation) -> tuple[PlanStep, ...]:
        if continuation.action is None or self.provider.actor(after) is not Actor.OURS:
            return ()
        before_current = before.obs.get("current") or {}
        after_current = after.obs.get("current") or {}
        if int(before_current.get("turn", 0)) != int(after_current.get("turn", 0)):
            return ()
        footprint = self._footprint(before, action)
        if footprint is not None and footprint.barrier:
            return ()
        step = PlanStep(
            after.semantic_key, after.legal_menu_digest, continuation.action.selection,
            continuation.action.identity, self.profile.hash,
            int(after_current.get("turn", 0)), int(after_current.get("yourIndex", 0)),
        )
        return (step,) + continuation.evaluation.continuation

    def _reveal_choices(self, before: DecisionState, node: RevealChoice):
        def priority(edge):
            child = edge.node
            state = child.state if isinstance(child, (Deterministic, Terminal)) else None
            need = (self.oracle.reveal_choice_priority(before, state)
                    if state is not None else 0.0)
            return -need, edge.label

        return tuple(sorted(node.choices, key=priority))

    def _footprint(self, state: DecisionState, action: LegalAction) -> ActionFootprint | None:
        footprint = getattr(self.provider, "footprint", None)
        return footprint(state, action) if footprint is not None else None

    def _information_priority(self, state: DecisionState, action: LegalAction) -> float:
        node = self.provider.transition(state, action)
        reveal = self.oracle.reveal_node_priority(state, node)
        if isinstance(node, RevealChoice):
            minimum = self.profile.get("search.reveal_information_min_need")
            return reveal if reveal >= minimum else 0.0
        return self.oracle.need_coverage_value(state, action)

    @staticmethod
    def _sleep_key(sleep: tuple[SleepEvent, ...]) -> tuple[tuple[str, ...], ...]:
        return tuple(sorted((("persistent" if event.persistent else "commutative", *event.event)
                             for event in sleep)))

    def _successor_sleep(self, sleep: tuple[SleepEvent, ...], earlier: list[ActionFootprint],
                         current: ActionFootprint | None,
                         information: tuple[ActionFootprint, ...]) -> tuple[SleepEvent, ...]:
        if current is None or current.barrier:
            return ()
        retained = [event for event in sleep
                    if event.persistent or independent(event.footprint, current)]
        retained.extend(SleepEvent(footprint.event, footprint)
                        for footprint in earlier if independent(footprint, current))
        retained.extend(SleepEvent(footprint.event, footprint, True)
                        for footprint in information if information_precedes(footprint, current))
        by_event = {event.event: event for event in retained}
        return tuple(by_event[event] for event in sorted(by_event))

    def _state(self, state: DecisionState,
               sleep: tuple[SleepEvent, ...] = ()) -> StateEvaluation:
        if self.nodes >= self.limits.max_nodes or monotonic() >= self._deadline:
            actions = tuple(sorted(self.provider.actions(state), key=lambda action: action.identity))
            end = next((action for action in actions if action.identity.kind == "end"), None)
            if end is not None:
                lower = Evaluation(0.0, Ledger(), False, "production cap: End lower bound")
                return StateEvaluation(0.0, end, lower, ((end, lower),))
            incomplete = Evaluation(-math.inf, Ledger(), False, "production state cap")
            return StateEvaluation(-math.inf, None, incomplete, ())

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
                    proof_type = ("information_before_commitment" if sleeping.persistent
                                  else "commutativity")
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
            deterministic_need = any(
                not footprints[action.identity].information_first
                and self.oracle.need_coverage_value(state, action) > 0.0
                for action in actions if footprints[action.identity] is not None
            )
            if deterministic_need:
                retained = []
                minimum = self.profile.get("search.reveal_information_min_need")
                for action in actions:
                    footprint = footprints[action.identity]
                    node = (self.provider.transition(state, action)
                            if footprint is not None and footprint.information_first else None)
                    reveal = (self.oracle.reveal_node_priority(state, node)
                              if isinstance(node, RevealChoice) else minimum)
                    if reveal >= minimum:
                        retained.append(action)
                        continue
                    self._structural_prunes.append({
                        "proof_type": "weak_reveal_vs_deterministic_need",
                        "pruned": str(action.identity),
                    })
                actions = tuple(retained)
            retained = []
            for action in actions:
                heal = self.oracle.heal_need_value(state, action)
                if heal is None or heal >= self.profile.get("needs.heal_min_gain"):
                    retained.append(action)
                    continue
                self._structural_prunes.append({
                    "proof_type": "heal_below_minimum_gain",
                    "pruned": str(action.identity),
                    "gain": heal,
                })
            actions = tuple(retained)
            energy_heals = tuple(
                action for action in actions
                if self.oracle.heal_repositions_energy(state, action)
                and self.oracle.heal_need_value(state, action) >= self.profile.get(
                    "needs.heal_min_gain")
            )
            if energy_heals:
                urgent = max(self.oracle.heal_need_value(state, action)
                             for action in energy_heals) >= self.profile.get(
                                 "needs.heal_urgent_gain")
                retained = []
                for action in actions:
                    footprint = footprints[action.identity]
                    transition = (self.provider.transition(state, action)
                                  if footprint is not None and footprint.commitment else None)
                    useful_information = bool(
                        footprint is not None and footprint.information_first
                        and self._information_priority(state, action) > 0.0)
                    useful_recovery = self.oracle.recovery_need_value(state, action) > 0.0
                    if (action in energy_heals or action.identity.kind == "end"
                            or useful_information
                            or useful_recovery
                            or (not urgent and (footprint is None or not footprint.commitment))
                            or (isinstance(transition, Terminal)
                                and transition.result == TERMINAL_WIN_REASON)):
                        retained.append(action)
                        continue
                    self._structural_prunes.append({
                        "proof_type": "heal_before_commitment",
                        "pruned": str(action.identity),
                        "retained_event": footprints[energy_heals[0].identity].event,
                    })
                actions = tuple(retained)
            information_actions = tuple(
                action for action in actions
                if footprints[action.identity] is not None
                and footprints[action.identity].information_first
                and footprints[action.identity].event not in asleep
                and self._information_priority(state, action) > 0.0
            )
            information = tuple(footprints[action.identity] for action in information_actions)
            if information:
                retained = []
                for action in actions:
                    footprint = footprints[action.identity]
                    transition = (self.provider.transition(state, action)
                                  if footprint is not None and footprint.commitment else None)
                    if (footprint is None or not footprint.commitment
                            or action.identity.kind == "evolve"
                            or self.oracle.need_coverage_value(state, action) > 0.0
                            or (isinstance(transition, Terminal)
                                and transition.result == TERMINAL_WIN_REASON)):
                        retained.append(action)
                        continue
                    self._structural_prunes.append({
                        "proof_type": "information_before_commitment",
                        "pruned": str(action.identity),
                        "retained_event": information[0].event,
                    })
                    self.information_pruned += 1
                actions = tuple(retained)
            if self.profile.get("search.needs_before_commitment") >= 0.5:
                preparations = tuple(
                    action for action in actions
                    if footprints[action.identity] is not None
                    and not footprints[action.identity].commitment
                    and hasattr(self.oracle, "need_coverage_ledger")
                    and self.oracle.need_coverage_ledger(state, action) is not None
                )
                if preparations:
                    retained = []
                    for action in actions:
                        footprint = footprints[action.identity]
                        if footprint is None or not footprint.commitment:
                            retained.append(action)
                            continue
                        self._structural_prunes.append({
                            "proof_type": "needs_before_commitment",
                            "pruned": str(action.identity),
                            "retained_event": footprints[preparations[0].identity].event,
                        })
                    actions = tuple(retained)
            ordering = any(self.profile.get(f"family.{family}_ordering") >= 0.5
                           for family in FAMILIES)
            widening = any(self.profile.get(f"family.{family}_widening") >= 0.5
                           for family in FAMILIES)
            if ordering or widening:
                ranking = rank_actions(state, actions, self.provider, self.oracle, self.profile)
                self._family_rankings[key] = ranking
            if ordering:
                actions = apply_family_ordering(actions, ranking, self.profile)
        if self.provider.actor(state) is Actor.OURS:
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
            information = tuple(
                footprints[action.identity] for action in actions
                if footprints[action.identity] is not None
                and footprints[action.identity].information_first
                and self._information_priority(state, action) > 0.0
            )
            for action in actions:
                footprint = footprints.get(action.identity)
                child_sleeps[action.identity] = self._successor_sleep(
                    sleep, earlier, footprint, information)
                if footprint is not None and not footprint.barrier:
                    earlier.append(footprint)
        else:
            child_sleeps = {action.identity: sleep for action in actions}
        if key == self._root_key:
            ranking = self._family_rankings.get(key)
            action_waves = ({
                candidate.action: (candidate.wave if candidate.family in FAMILIES and
                                   self.profile.get(
                                       f"family.{candidate.family}_widening") >= 0.5 else 0)
                for candidate in ranking.candidates
            } if ranking is not None else {})
            results_list = []
            branch_nodes = []
            branch_capped = []
            original_limits = self.limits
            for index, action in enumerate(actions):
                wave = action_waves.get(action, 0)
                widening = wave > 0
                probe_nodes = min(
                    self.production_limits.max_nodes,
                    max(1, self.production_limits.root_probe_nodes
                        if wave <= 1 or not widening else 1),
                )
                self.limits = SearchLimits(probe_nodes)
                self._deadline = self._budget.root_deadline(
                    monotonic(), self._hard_deadline, len(actions) - index)
                self.nodes = 1
                result = self._action(state, action, child_sleeps[action.identity])
                branch_nodes.append(self.nodes)
                branch_capped.append(not result.complete and (
                    self.nodes >= probe_nodes or monotonic() >= self._deadline))
                results_list.append((action, result))
            if results_list:
                self._completed_rounds = 1 + max(action_waves.values(), default=0)
            self._deadline = self._hard_deadline

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
