"""Deterministic exhaustive Bellman reference solver."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import math
import sys
from time import monotonic
from typing import Protocol

from .algebra import (
    ActionDiagnostic, Actor, Chance, Choice, Deterministic, Ledger, Refresh, RevealChoice,
    RootDiagnostics, Terminal, Unknown,
)
from .api import PlanStep, RootDecision
from .budget_prototype import FairBudgetPrototype
from .commutativity import ActionFootprint, independent
from .fetch import DEADNESS, WINDOW, fetch_target_matches
from .options import LegalAction
from .option_equivalence import option_source_card
from .demand import StrategyBeamBuilder, outcome_identity, semantic_action_key
from .refresh import played_card_id
from .pilot_profile import DEFAULT_PILOT_PROFILE, PilotProfile
from .state import DecisionState
from .strategy.context import _DAMAGE, _DAMAGE_COUNTER, _DAMAGE_COUNTER_ANY, _DISCARD
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
_UNSET = object()
MAIN_DECISION_CONTEXT = 0
VALUE_TIE_DECIMALS = 12
TERMINAL_WIN_REASON = "win"
#: The forced continuation after End is expected to be a few plies of checkup menus; these caps
#: keep a pathological or cyclic forced chain from exhausting the interpreter stack.  Both are
#: spent per chain: a capped chain reports -inf/incomplete, which deletes the End line carrying
#: a cut sequence's remaining EV, so a decision-wide budget retired whole root actions once a
#: busy decision had valued enough unrelated forced menus.
END_CHAIN_DEPTH_CAP = 32
END_CHAIN_NODE_CAP = 512
#: Board commitments a free peek weakly dominates (ADR-0140 amendment clause 3).  Trainer plays
#: are excluded: the Supporter allowance makes them non-neutral, and an urgent play outranks a peek.
DOMINATED_COMMITMENT_KINDS = frozenset({"attach", "evolve", "retreat"})


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
    execution_complete: bool = False


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


@dataclass
class _CompletedCandidateBank:
    live: dict[object, Evaluation] = field(default_factory=dict)
    checkpoint: dict[object, Evaluation] = field(default_factory=dict)
    live_tiers: dict[object, str] = field(default_factory=dict)
    checkpoint_tiers: dict[object, str] = field(default_factory=dict)

    def offer(self, action: LegalAction, result: Evaluation, tier: str | None = None) -> None:
        if not math.isfinite(result.value):
            return
        tier = tier or ("full" if result.execution_complete else "recoverable")
        ranks = {"safety": 0, "recoverable": 1, "full": 2}
        incumbent = self.live.get(action.identity)
        incumbent_tier = self.live_tiers.get(action.identity, "safety")
        if (incumbent is None or (ranks[tier], _ordered_evaluation(result, Actor.OURS))
                > (ranks[incumbent_tier], _ordered_evaluation(incumbent, Actor.OURS))):
            self.live[action.identity] = result
            self.live_tiers[action.identity] = tier

    def publish(self) -> None:
        self.checkpoint = dict(self.live)
        self.checkpoint_tiers = dict(self.live_tiers)


def _select_our_action(finite, context: int):
    if context == _DISCARD:
        immediate = max(result.ledger.immediate for _action, result in finite)
        leaders = tuple(
            pair for pair in finite
            if round(pair[1].ledger.immediate, VALUE_TIE_DECIMALS)
            == round(immediate, VALUE_TIE_DECIMALS)
        )
        return min(leaders, key=lambda pair: str(pair[0].identity))
    selected = max(finite, key=lambda pair: _ordered_evaluation(pair[1], Actor.OURS))
    if not selected[1].complete or context not in {
            _DAMAGE, _DAMAGE_COUNTER, _DAMAGE_COUNTER_ANY}:
        return selected
    leaders = tuple(
        pair for pair in finite
        if _ordered_evaluation(pair[1], Actor.OURS)
        == _ordered_evaluation(selected[1], Actor.OURS)
    )
    return min(leaders, key=lambda pair: (pair[0].selection, str(pair[0].identity)))


def _commutative_order(action: LegalAction):
    priority = {"evolve": 0, "attach": 1}
    return priority.get(action.identity.kind, 2), action.identity


def _expected_evaluation(weighted, *, reason: str, branches=(), complete: bool = True) -> Evaluation:
    weighted = tuple(weighted)
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
    return Evaluation(ledger.total, ledger, complete, reason, tuple(branches), decisions,
                      execution_complete=all(
                          result.execution_complete for _probability, result in weighted))


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
        self._end_chain_nodes = 0

    def decide(self, state: DecisionState) -> RootDecision:
        self._memo.clear()
        self._active.clear()
        self._transitions.clear()
        self.nodes = self.cache_hits = 0
        self._end_chain_nodes = 0
        self._root_key = state.semantic_key
        solved = self._state(state)
        if solved.action is None:
            solved = self._root_salvage(state, solved)
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

    def _root_salvage(self, state: DecisionState, solved: StateEvaluation) -> StateEvaluation:
        """A planning dead end still submits something legal (End, else the first action) —
        incomplete and naming the dead end, never a fabricated value. A raise is a forfeit."""
        actions = tuple(sorted(self.provider.actions(state), key=lambda action: action.identity))
        if not actions:
            return solved
        action = next((candidate for candidate in actions
                       if candidate.identity.kind == "end"), actions[0])
        reason = f"root salvage: {solved.evaluation.reason or 'no complete legal action'}"
        return StateEvaluation(
            0.0, action, Evaluation(0.0, Ledger(), False, reason), solved.alternatives)

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
                return Evaluation(
                    0.0, Ledger(), True, "End exact zero", execution_complete=True)
            node = resolve_end(state, action)
            if node is None:
                return Evaluation(
                    0.0, Ledger(), True, "End exact zero", execution_complete=True)
            return self._end_transition(state, action, node)
        return self._transition(state, action, self._provider_transition(state, action), sleep)

    def _end_transition(self, before: DecisionState, action: LegalAction, node,
                        depth: int = END_CHAIN_DEPTH_CAP) -> Evaluation:
        """Value only the forced turn-boundary outcome, without planning the opponent's turn.
        Carries structural depth/node caps so a cyclic forced menu degrades to incomplete rather
        than a RecursionError.  Structural and never a clock: stopping this chain on wall time
        decides the turn by machine load."""
        if depth == END_CHAIN_DEPTH_CAP:             # the top of one chain
            self._end_chain_nodes = 0
        self._end_chain_nodes += 1
        if depth <= 0 or self._end_chain_nodes > END_CHAIN_NODE_CAP:
            return Evaluation(-math.inf, Ledger(), False, "End continuation capped")
        if isinstance(node, Unknown):
            return Evaluation(-math.inf, Ledger(), False,
                              f"{node.reason}: {node.missing_fact}")
        if isinstance(node, Deterministic):
            ledger = self._ledger(before, node.state, action)
            select = node.state.obs.get("select") or {}
            if int(select.get("context", MAIN_DECISION_CONTEXT)) != MAIN_DECISION_CONTEXT:
                actor = self.provider.actor(node.state)
                forced = tuple(
                    (candidate, self._end_transition(
                        node.state, candidate,
                        self._provider_transition(node.state, candidate), depth - 1))
                    for candidate in self.provider.actions(node.state)
                )
                if (not forced or any(not result.complete or not math.isfinite(result.value)
                                      for _candidate, result in forced)):
                    return Evaluation(-math.inf, ledger, False,
                                      "forced End continuation incomplete")
                chooser = max if actor is Actor.OURS else min
                _candidate, continuation = chooser(
                    forced, key=lambda row: _ordered_evaluation(row[1], actor))
                combined = _combine(ledger, continuation.value)
                return Evaluation(
                    combined.total, combined, True, "End forced continuation resolved",
                    decisions=1.0 + continuation.decisions,
                    execution_complete=continuation.execution_complete)
            return Evaluation(ledger.total, ledger, True, "End resolved", decisions=1.0,
                              execution_complete=True)
        if isinstance(node, Terminal):
            ledger = _combine(self._ledger(before, node.state, action), 0.0, node.ledger)
            return Evaluation(ledger.total, ledger, True, node.result, decisions=1.0,
                              execution_complete=True)
        if isinstance(node, Chance):
            branches = [(edge, self._end_transition(before, action, edge.node, depth - 1))
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
                                  1.0 + continuation.evaluation.decisions), continuation=steps,
                              execution_complete=continuation.evaluation.execution_complete)
        if isinstance(node, Terminal):
            base = self._ledger(before, node.state, action)
            ledger = _combine(base, 0.0, node.ledger)
            return Evaluation(ledger.total, ledger, True, node.result, decisions=1.0,
                              execution_complete=True)
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
                                    for child, evaluated in branches), result.decisions,
                              execution_complete=(
                                  result.execution_complete if node.actor is Actor.OURS else
                                  all(evaluated.execution_complete
                                      for _child, evaluated in branches)))
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
            except Exception as exc:  # noqa: BLE001 - a KeyError here was process death (forfeit)
                print(f"refresh valuation unavailable ({type(exc).__name__}: {exc}); "
                      "the refresh card is unplayable this decision", file=sys.stderr, flush=True)
                return Evaluation(-math.inf, Ledger(), False,
                                  f"refresh valuation unavailable: {exc}")
            continuation = self._guaranteed_refresh_continuation(before)
            combined = _combine(ledger, continuation.value)
            return Evaluation(combined.total, combined, True, "analytic refresh gamble",
                              diagnostics, decisions=1.0 + continuation.decisions,
                              execution_complete=True)
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
                                    for edge, result in branches), decisions,
                              execution_complete=all(
                                  result.execution_complete for _edge, result in branches))
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

    Strategy paths first produce executable candidates; Bellman then probes every unresolved root
    and refines the strongest incomplete branches. There is no depth horizon or second action policy.
    Width/state capacity are explicit; a capped state may retain an exact End lower bound.
    """

    def __init__(self, provider: TransitionProvider, oracle: ValueOracle, *, model_factory=None,
                 limits: ProductionLimits = ProductionLimits(),
                 profile: PilotProfile = DEFAULT_PILOT_PROFILE, strategy_snapshot=None):
        super().__init__(provider, oracle, model_factory=model_factory,
                         limits=SearchLimits(limits.max_nodes))
        self.production_limits = limits
        self.profile = profile
        self.strategy_snapshot = strategy_snapshot
        self._root_key = ""
        self._root_branch_nodes: list[int] = []
        self._root_branch_capped: list[bool] = []
        self._deadline = math.inf
        self._hard_deadline = math.inf
        self._budget = FairBudgetPrototype(limits.max_seconds)
        self._por_memo: dict[tuple[str, tuple[tuple[str, ...], ...]], StateEvaluation] = {}
        self._diamond_cache: dict[tuple[str, tuple[str, ...], tuple[str, ...]], bool] = {}
        # Printed card text, so the clauses are decision-invariant and outlive the state cache.
        self._dead_fetch_clauses: dict[int, tuple[dict, ...] | None] = {}
        self.por_pruned = 0
        self.information_pruned = 0
        self._structural_prunes: list[dict] = []
        self._strategy_builder = None
        self._strategy_beams = {}
        self._strategy_waves = {}
        self._strategy_focus_ranks = {}
        self._strategy_later_wave = {}
        self._strategy_clock_scale = 1.0
        self._completed_rounds = 0
        self._bound_prunes: list[dict] = []
        self._action_bounds: dict[object, dict] = {}
        self._deadline_hit = False
        self._search_started = 0.0
        self._incumbent_timeline: list[dict] = []
        self._harvesting_candidates = False
        self._candidate_harvest: dict = {}
        self._candidate_bank = _CompletedCandidateBank()
        self._harvest_prefix: list[object] = []
        self._harvest_coverage: list[tuple[str, ...]] = []
        self._harvest_exclusions: set[tuple[object, ...]] = set()
        self._candidate_timeout_fallback = False
        self._phase_budgets = {}
        self._protected_bundle_diagnostics = {}
        self._challenger_diagnostics = {}
        self._stability_stop = False
        self._stability_history = None

    def decide(self, state: DecisionState) -> RootDecision:
        self._search_started = monotonic()
        self._incumbent_timeline = []
        self._root_key = state.semantic_key
        self._root_branch_nodes = []
        self._root_branch_capped = []
        self._por_memo.clear()
        self._diamond_cache.clear()
        self.por_pruned = 0
        self.information_pruned = 0
        self._structural_prunes.clear()
        self._strategy_beams.clear()
        self._strategy_waves.clear()
        self._strategy_focus_ranks.clear()
        self._strategy_later_wave.clear()
        self._strategy_clock_scale = 1.0
        self._strategy_builder = None
        if (self.strategy_snapshot is not None
                and self.profile.get("strategy.focus_enabled") >= 0.5):
            self._strategy_builder = StrategyBeamBuilder(
                self.strategy_snapshot, effects=self.oracle.effects, stats=self.oracle.stats,
                registry=self.oracle.registry,
                width=self.profile.get("strategy.focus_width"),
                sequence_coverage=(
                    self.profile.get("strategy.sequence_coverage_enabled") >= 0.5))
        self._completed_rounds = 0
        self._bound_prunes.clear()
        self._action_bounds.clear()
        self._deadline_hit = False
        self._harvesting_candidates = False
        self._harvest_coverage = []
        self._candidate_harvest = {
            "target": int(self.profile.get("search.completed_candidate_target")),
            "time_share": self.profile.get("search.completed_candidate_time_share"),
            "elapsed_seconds": 0.0,
            "attempted_count": 0,
            "completed_count": 0,
            "completed": (),
        }
        self._candidate_bank = _CompletedCandidateBank()
        self._harvest_prefix = []
        self._harvest_exclusions = set()
        self._candidate_timeout_fallback = False
        self._stability_stop = False
        self._stability_history = None
        self._hard_deadline = self._budget.hard_deadline(monotonic())
        self._deadline = self._hard_deadline
        decision = super().decide(state)
        search_seconds = monotonic() - self._search_started
        incumbent_summary = self._incumbent_summary(decision, search_seconds)
        self._complete_root_bounds(state, decision)
        if self._strategy_builder is not None and self._root_key not in self._strategy_beams:
            root_actions = tuple(sorted(self.provider.actions(state), key=lambda row: row.identity))
            self._sync_prefix_outcomes()
            self._strategy_beams[self._root_key] = self._strategy_builder.build(state, root_actions)
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
            "candidate_harvest": self._candidate_harvest,
            "candidate_timeout_fallback": self._candidate_timeout_fallback,
            "execution_tier": self._candidate_bank.checkpoint_tiers.get(
                decision.action,
                "full" if decision.complete else "recoverable"),
            "phase_budgets": dict(self._phase_budgets),
            "protected_bundles": dict(self._protected_bundle_diagnostics),
            "challengers": dict(self._challenger_diagnostics),
            "stability_stop": self._stability_stop,
            "lower_bound": not decision.complete,
            "commutative_permutations_pruned": self.por_pruned,
            "information_first_permutations_pruned": self.information_pruned,
            "structural_prunes": tuple(self._structural_prunes),
            "profile_hash": self.profile.hash,
            "completed_rounds": self._completed_rounds,
            "strategy_later_wave": len(self._strategy_later_wave.get(self._root_key, ())),
            "strategy_clock_scale": self._strategy_clock_scale,
            "family_candidates": (),
            "bound_prunes": tuple(self._bound_prunes),
            "action_bounds": tuple(self._action_bounds.values()),
            "incumbent_timeline": tuple(self._incumbent_timeline),
            "final_incumbent": incumbent_summary,
        }
        if self._root_key in self._strategy_beams:
            diagnostics["strategy_beam"] = self._strategy_beams[self._root_key]
        if self.strategy_snapshot is not None:
            diagnostics["strategy_snapshot"] = self.strategy_snapshot
        diagnostics["odds"] = {
            "enabled": True,
            "marginal_access": (dict(getattr(self._strategy_builder, "last_odds", {}))
                                if self._strategy_builder is not None else {}),
        }
        return RootDecision(decision.chosen, decision.action, decision.value,
                            decision.complete, diagnostics, decision.plan_suffix)

    @staticmethod
    def _sequence_signature(action, result) -> tuple[str, ...]:
        return (str(action.identity), *(str(step.action) for step in result.continuation))

    @staticmethod
    def _sequence_identities(action, result) -> tuple[object, ...]:
        return (action.identity, *(step.action for step in result.continuation))

    @staticmethod
    def _is_executable_candidate(action, result) -> bool:
        del action
        return math.isfinite(result.value) and result.execution_complete

    def _candidate_order(self, actions) -> tuple[LegalAction, ...]:
        if self._strategy_builder is None:
            return ()
        focus_ranks = self._strategy_focus_ranks.get(self._root_key, {})
        focused = sorted(
            (action for action in actions if semantic_action_key(action) in focus_ranks),
            key=lambda action: focus_ranks[semantic_action_key(action)],
        )
        target = int(self.profile.get("search.completed_candidate_target"))
        ordered = focused[:target]
        ordered.extend(action for action in focused if action not in ordered)
        ordered.extend(action for action in self._safety_candidates(actions)
                       if action not in ordered)
        return tuple(ordered)

    def _protected_bundles(self, state) -> tuple[str, ...]:
        if self._strategy_builder is None or not hasattr(
                self._strategy_builder, "outcome_statuses"):
            return ()
        rows = self._strategy_builder.outcome_statuses(state)
        grouped = {}
        for row in rows:
            if (row["urgency"] != "high" or row["conviction"] != "high"
                    or row["status"] in {"satisfied", "impossible"}):
                continue
            bundle = str(row["bundle_id"] or row["strategy_id"])
            grouped.setdefault(bundle, []).append(row)
        reachability = {"unknown": 0, "probabilistic": 1, "guaranteed": 2}

        def outcome(row):
            return outcome_identity(
                row.get("kind"), row.get("recipient_serial"), row.get("recipient_card_id"),
                tuple(row.get("target_card_ids") or ()), int(row.get("waypoint", 0)),
            )

        ranked = []
        for bundle, members in grouped.items():
            outcomes = tuple(sorted({outcome(row) for row in members}, key=repr))
            score = (
                max(reachability.get(str(row["status"]), 0) for row in members),
                len(outcomes),
            )
            ranked.append((bundle, score, outcomes))
        ranked.sort(key=lambda item: (
            -item[1][0], -item[1][1], repr(item[2]),
        ))
        bundle_ids = tuple(bundle for bundle, _score, _outcomes in ranked)
        limit = int(self.profile.get("search.protected_bundle_count"))
        protected = tuple(bundle_ids[:limit])
        self._protected_bundle_diagnostics = {
            "eligible": tuple(bundle_ids), "protected": protected,
            "overflow": tuple(bundle_ids[limit:]),
            "ranked": tuple({
                "bundle_id": bundle,
                "reachability": score[0],
                "distinct_outcomes": score[1],
            } for bundle, score, _outcomes in ranked),
        }
        return protected

    def _action_bundles(self, action) -> tuple[str, ...]:
        beam = self._strategy_beams.get(self._root_key)
        if (beam is None or self.strategy_snapshot is None
                or not hasattr(self.strategy_snapshot, "hints")):
            return ()
        focus = next((row for row in beam.focused
                      if row.action_key == semantic_action_key(action)), None)
        if focus is None:
            return ()
        by_id = {hint.strategy_id: str(hint.bundle_id or hint.strategy_id)
                 for hint in self.strategy_snapshot.hints}
        return tuple(dict.fromkeys(by_id[strategy_id] for strategy_id in focus.path_ids
                                   if strategy_id in by_id))

    def _credible_challengers(self, state, actions, indices, finite, context):
        if context != MAIN_DECISION_CONTEXT:
            selected = tuple(indices)
            self._challenger_diagnostics = {
                "selected": tuple(str(actions[index].identity) for index in selected),
                "rejected_by_bound": (), "limit": len(selected),
            }
            return selected
        focus = self._strategy_focus_ranks.get(self._root_key, {})
        incumbent = self._select_our_action(state, finite, context) if finite else None
        rows = []
        rejected = []
        for index in indices:
            action = actions[index]
            if (semantic_action_key(action) in focus
                    or action.identity.kind in {"attack", "end"}):
                continue
            q_upper, _terms = self._root_upper_bound(state, action)
            if incumbent is not None and math.isfinite(q_upper):
                _incumbent_action, incumbent_result = incumbent
                if round(q_upper, VALUE_TIE_DECIMALS) < round(
                        incumbent_result.value, VALUE_TIE_DECIMALS):
                    rejected.append(str(action.identity))
                    continue
            rows.append((index, q_upper))
        rows.sort(key=lambda row: (
            -row[1] if math.isfinite(row[1]) else -math.inf,
            str(actions[row[0]].identity)))
        limit = int(self.profile.get("search.challenger_count"))
        selected = tuple(index for index, _bound in rows[:limit])
        self._challenger_diagnostics = {
            "selected": tuple(str(actions[index].identity) for index in selected),
            "rejected_by_bound": tuple(rejected), "limit": limit,
        }
        return selected

    def _stable_checkpoint(self, state, actions, context: int, *, now=None) -> bool:
        now = monotonic() if now is None else float(now)
        full = tuple(
            (action, self._candidate_bank.checkpoint[action.identity])
            for action in actions
            if self._candidate_bank.checkpoint_tiers.get(action.identity) == "full")
        if not full:
            self._stability_history = None
            return False
        incumbent_action, incumbent = self._select_our_action(state, full, context)
        identity = self._sequence_signature(incumbent_action, incumbent)
        if self._stability_history is None or self._stability_history[0] != identity:
            self._stability_history = (identity, now, 1)
            return False
        first_seen, count = self._stability_history[1], self._stability_history[2] + 1
        self._stability_history = (identity, first_seen, count)
        patience = min(
            self.profile.get("search.stability_patience_max_seconds"),
            max(self.profile.get("search.stability_patience_min_seconds"),
                self.production_limits.max_seconds
                * self.profile.get("search.stability_patience_share")))
        if (count < int(self.profile.get("search.stability_checkpoints"))
                or now - first_seen < patience):
            return False
        for action in actions:
            if action.identity == incumbent_action.identity:
                continue
            bound = self._action_bounds.get(action.identity)
            if bound is None:
                candidate = self._candidate_bank.checkpoint.get(action.identity)
                if (candidate is None or self._candidate_bank.checkpoint_tiers.get(
                        action.identity) != "full"):
                    return False
                upper = candidate.value
            else:
                upper = float(bound.get("q_upper", math.inf))
            if round(upper, VALUE_TIE_DECIMALS) >= round(
                    incumbent.value, VALUE_TIE_DECIMALS):
                return False
        return True

    @staticmethod
    def _safety_candidates(actions, *, allow_fallback=False) -> tuple[LegalAction, ...]:
        safety = tuple(action for kind in ("attack", "end") for action in actions
                       if action.identity.kind == kind)
        if safety:
            return safety
        fallback = next((action for action in actions if action.selection), None) \
            if allow_fallback else None
        return (fallback,) if fallback is not None else ()

    def _bank_candidate(self, action: LegalAction, result: Evaluation,
                        tier: str | None = None) -> None:
        self._candidate_bank.offer(action, result, tier)

    def _select_timeout_candidate(self, finite, context: int):
        if context == _DISCARD:
            return _select_our_action(finite, context)
        ranks = {"safety": 0, "recoverable": 1, "full": 2}

        def score(pair):
            return (
                ranks[self._candidate_bank.checkpoint_tiers.get(
                    pair[0].identity,
                    "full" if pair[1].execution_complete else "recoverable")],
                _ordered_evaluation(pair[1], Actor.OURS),
            )
        best = max(score(pair) for pair in finite)
        return min((pair for pair in finite if score(pair) == best),
                   key=lambda pair: str(pair[0].identity))

    def _prefer_unresolved_strategy(self, state, finite, selected, context: int):
        action, result = selected
        focus = self._strategy_focus_ranks.get(self._root_key, {})
        if (context != MAIN_DECISION_CONTEXT or result.complete
                or semantic_action_key(action) in focus or not focus):
            return selected
        protected = set(self._protected_bundle_diagnostics.get("protected", ()))
        focused = tuple(
            pair for pair in finite
            if (semantic_action_key(pair[0]) in focus
                and protected.intersection(self._action_bundles(pair[0])))
        )
        if not focused:
            return selected
        preferred = min(
            focused,
            key=lambda pair: (focus[semantic_action_key(pair[0])], str(pair[0].identity)),
        )
        bound = self._action_bounds.get(preferred[0].identity)
        upper = float(bound.get("q_upper", math.inf)) if bound else math.inf
        return selected if round(result.value, VALUE_TIE_DECIMALS) > round(
            upper, VALUE_TIE_DECIMALS) else preferred

    def _action_coverage(self, state, action) -> tuple[str, ...]:
        beam = self._strategy_beams.get(state.semantic_key)
        if beam is None:
            return ()
        key = semantic_action_key(action)
        row = next((row for row in beam.focused if row.action_key == key), None)
        return tuple(getattr(row, "coverage", ()) or ()) if row is not None else ()

    def _sync_prefix_outcomes(self) -> None:
        """Hand the beam the outcomes the searched prefix already advanced, so a sequence
        counts each distinct outcome once (traversal order only — never value or bounds)."""
        if self._strategy_builder is not None:
            self._strategy_builder.prefix_outcomes = tuple(dict.fromkeys(
                key for keys in self._harvest_coverage for key in keys))

    def _search_action(self, state, action, sleep) -> Evaluation:
        if not self._harvesting_candidates:
            return self._action(state, action, sleep)
        self._harvest_prefix.append(action.identity)
        self._harvest_coverage.append(self._action_coverage(state, action))
        try:
            return self._action(state, action, sleep)
        finally:
            self._harvest_prefix.pop()
            self._harvest_coverage.pop()

    def _record_incumbent(self, state, finite, context, phase) -> None:
        if not finite:
            return
        action, result = self._select_our_action(state, finite, context)
        key = semantic_action_key(action)
        focus_ranks = self._strategy_focus_ranks.get(self._root_key, {})
        event = {
            "elapsed_seconds": monotonic() - self._search_started,
            "sequence": self._sequence_signature(action, result),
            "value": result.value,
            "complete": result.complete,
            "execution_tier": (
                "full" if result.execution_complete else "recoverable"),
            "phase": phase,
            "strategy_wave": ("first" if self._strategy_waves.get(
                self._root_key, {}).get(action, 0) == 0 else "widening"),
            "strategy_focus_position": (
                focus_ranks[key] + 1 if key in focus_ranks else None),
            "strategy_focus_count": len(focus_ranks),
        }
        identity = (event["sequence"], event["value"], event["complete"],
                    event["execution_tier"])
        if not self._incumbent_timeline or identity != tuple(
                self._incumbent_timeline[-1][name]
                for name in ("sequence", "value", "complete", "execution_tier")):
            self._incumbent_timeline.append(event)

    def _incumbent_summary(self, decision, search_seconds) -> dict:
        final_sequence = (
            str(decision.action), *(str(step.action) for step in decision.plan_suffix))
        matches = [index for index, event in enumerate(self._incumbent_timeline)
                   if tuple(event["sequence"]) == final_sequence]
        if not matches:
            return {"search_seconds": search_seconds, "found": False}
        complete_matches = [index for index in matches
                            if self._incumbent_timeline[index]["complete"]]
        recoverable_matches = [index for index in matches
                               if self._incumbent_timeline[index].get("execution_tier", "full")
                               in {"recoverable", "full"}]
        full_matches = [index for index in matches
                        if self._incumbent_timeline[index].get(
                            "execution_tier", "full") == "full"]
        first_index = (complete_matches[0] if complete_matches else matches[0])
        last_other = max(
            (index for index, event in enumerate(self._incumbent_timeline)
             if tuple(event["sequence"]) != final_sequence), default=-1)
        stable_index = next((index for index in matches
                             if index >= first_index and index > last_other), None)
        first = self._incumbent_timeline[first_index]
        stable = self._incumbent_timeline[stable_index if stable_index is not None else matches[-1]]
        return {
            "search_seconds": search_seconds,
            "found": True,
            "first_found_seconds": first["elapsed_seconds"],
            "first_recoverable_seconds": (
                self._incumbent_timeline[recoverable_matches[0]]["elapsed_seconds"]
                if recoverable_matches else None),
            "first_full_seconds": (
                self._incumbent_timeline[full_matches[0]]["elapsed_seconds"]
                if full_matches else None),
            "stabilized_seconds": (
                stable["elapsed_seconds"] if stable_index is not None else search_seconds),
            "strategy_wave": stable["strategy_wave"],
            "strategy_focus_position": stable["strategy_focus_position"],
            "strategy_focus_count": stable["strategy_focus_count"],
            "complete": decision.complete,
        }

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

    def _peek_is_look_class(self, state: DecisionState, action: LegalAction) -> bool:
        """Whether this peek only looks at a bounded slice of the deck (a printed ``dig``).  A
        whole-deck tutor certainly spends itself for a known card, so playing it is a commitment."""
        effects = self.oracle.effects
        if effects is None:
            return True
        card_id = played_card_id(state, action)
        if card_id is None:
            return True
        fetches = tuple(clause for clause in effects.clauses(card_id)
                        if clause.get("kind") == "fetch")
        return bool(fetches) and all(clause.get("dig") for clause in fetches)

    def _peek_is_live(self, state: DecisionState, action: LegalAction) -> bool:
        """Whether this peek can still reveal anything: a fetch window with zero live targets in
        the remaining deck carries zero information, so it must not order anyone (ADR-0140)."""
        effects, stats = self.oracle.effects, self.oracle.stats
        if effects is None or stats is None:
            return True
        card_id = played_card_id(state, action)
        if card_id is None:
            return True
        fetches = tuple(clause for clause in effects.clauses(card_id)
                        if clause.get("kind") == "fetch")
        if not fetches:
            return True
        return any(
            count > 0 and any(fetch_target_matches(clause, stats.get(target_id), reading=WINDOW)
                              for clause in fetches)
            for target_id, count in state.deck_counts)

    def _zone_counts(self, state: DecisionState, zone: str):
        """The card ids still reachable in one fetch zone, as ``(card_id, count)`` pairs.  Constant
        per state and asked once per candidate play, so it lives on the scratch that dies with it."""
        if zone == "deck":
            return state.deck_counts
        scratch = state.action_scratch
        key = ("zone_counts", zone)
        if key not in scratch:
            players = (state.obs.get("current") or {}).get("players") or ()
            player = players[state.root_seat] if state.root_seat < len(players) else {}
            held = Counter(int(card["id"]) for card in (player.get(zone) or ())
                           if card and card.get("id") is not None)
            scratch[key] = tuple(held.items())
        return scratch[key]

    def _dead_fetch_cards(self, card_id: int) -> tuple[dict, ...] | None:
        """The fetch clauses of a Trainer whose whole printed effect is an unconditional fetch.
        Playing a Pokemon benches a body, so its play changes the board whatever the fetch finds."""
        cached = self._dead_fetch_clauses.get(card_id, _UNSET)
        if cached is not _UNSET:
            return cached
        stat = self.oracle.stats.get(card_id)
        clauses = tuple(self.oracle.effects.clauses(card_id))
        usable = (bool(clauses)
                  and stat is not None and not getattr(stat, "is_pokemon", False)
                  and all(clause.get("kind") == "fetch" for clause in clauses)
                  and not any(clause.get("cost") or clause.get("cost_required")
                              or clause.get("rider") or clause.get("trigger")
                              for clause in clauses))
        self._dead_fetch_clauses[card_id] = result = clauses if usable else None
        return result

    def _fetch_is_dead(self, state: DecisionState, action: LegalAction) -> bool:
        """Whether this play is entirely a fetch reaching nothing in its named zones.  Only the card
        itself moves, so skipping it keeps every continuation and a strictly larger hand."""
        stats = self.oracle.stats
        if self.oracle.effects is None or stats is None or action.identity.kind != "play":
            return False
        card_id = played_card_id(state, action)
        if card_id is None:
            return False
        clauses = self._dead_fetch_cards(card_id)
        if clauses is None:
            return False
        return not any(
            count > 0 and fetch_target_matches(clause, stats.get(target_id), reading=DEADNESS)
            for clause in clauses
            for target_id, count in self._zone_counts(state, str(clause.get("zone", "deck"))))

    def _hand_size_sensitive_play(self, state: DecisionState, actions) -> bool:
        """Whether any legal play reads or moves the whole hand (draw-to-hand-size, shuffle-hand).
        Against one, a smaller hand can be better, so the dead-fetch proof does not hold here."""
        effects = self.oracle.effects
        if effects is None:
            return False
        for action in actions:
            if action.identity.kind != "play":
                continue
            card_id = played_card_id(state, action)
            if card_id is None:
                continue
            for clause in effects.clauses(card_id):
                if clause.get("to_hand_size") is not None:
                    return True
                if "hand" in str(clause.get("rider", "")) or "hand" in str(clause.get("cost", "")):
                    return True
                conditional = clause.get("amount_if") or {}
                if "hand" in str(conditional.get("condition", "")) or "to_hand_size" in conditional:
                    return True
        return False

    def _dead_fetch_filter(self, state, actions):
        """Drop plays that provably fetch nothing: they spend a card and change nothing else."""
        if self._hand_size_sensitive_play(state, actions):
            return actions
        retained = []
        for action in actions:
            if action.identity.kind == "play" and self._fetch_is_dead(state, action):
                self._structural_prunes.append({
                    "proof_type": "dead_fetch",
                    "pruned": str(action.identity),
                    "retained_event": ("hold_the_card",),
                })
                continue
            retained.append(action)
        return tuple(retained) if retained else actions

    def _hand_payment_available(self, state: DecisionState, actions) -> bool:
        """Whether any legal play this turn pays a discard-from-hand cost (Ultra Ball class).

        When one does, the peek may be worth more as payment than as a peek, and only the value
        calculation can weigh that — the gate stands down (ADR-0140).
        """
        effects = self.oracle.effects
        if effects is None:
            return False
        for action in actions:
            if action.identity.kind != "play":
                continue
            card_id = played_card_id(state, action)
            if card_id is None:
                continue
            if any(clause.get("cost") or clause.get("cost_required")
                   for clause in effects.clauses(card_id)):
                return True
        return False

    def _information_dominance_filter(self, state, actions, footprints):
        """Order a live look-class peek before the board commitments it leaves exactly as playable,
        pruning those orderings.  Barriers, attack and End stay; ADR-0140 records every exemption."""
        peek_available = any(
            footprints.get(action.identity) is not None
            and footprints[action.identity].information_first
            and self._peek_is_look_class(state, action)
            and self._peek_is_live(state, action)
            for action in actions)
        if not peek_available:
            return actions
        if self._hand_payment_available(state, actions):
            return actions
        protected_keys = set()
        protected_bundles = set(self._protected_bundles(state))
        if protected_bundles and self._strategy_builder is not None:
            self._sync_prefix_outcomes()
            # A dominance proof must not depend on beam width or sort order: build unbounded so
            # the protected set is the full match set, whatever coverage put in the top slots.
            width = self._strategy_builder.width
            self._strategy_builder.width = max(width, len(actions))
            try:
                beam = self._strategy_builder.build(state, actions)
            finally:
                self._strategy_builder.width = width
            by_id = {
                hint.strategy_id: str(hint.bundle_id or hint.strategy_id)
                for hint in self.strategy_snapshot.hints
                if hint.deadline == "immediate"
            }
            protected_keys = {
                row.action_key for row in beam.focused
                if any(by_id.get(strategy_id) in protected_bundles
                       for strategy_id in row.path_ids)
            }
        retained = []
        for action in actions:
            footprint = footprints.get(action.identity)
            options = tuple((state.obs.get("select") or {}).get("option") or ())
            index = action.selection[0] if len(action.selection) == 1 else -1
            option = options[index] if 0 <= index < len(options) else None
            source = option_source_card(option, state.obs)
            source_id = int(source["id"]) if source and source.get("id") is not None else None
            source_stat = self.oracle.stats.get(source_id) \
                if source_id is not None and self.oracle.stats is not None else None
            if (footprint is not None and footprint.commitment and not footprint.barrier
                    and action.identity.kind in DOMINATED_COMMITMENT_KINDS
                    and not bool(getattr(source_stat, "is_tool", False))
                    and semantic_action_key(action) not in protected_keys):
                self.information_pruned += 1
                self._structural_prunes.append({
                    "proof_type": "information_dominance",
                    "pruned": str(action.identity),
                    "retained_event": ("free_peek_first",),
                })
                continue
            retained.append(action)
        return tuple(retained)

    def _footprint(self, state: DecisionState, action: LegalAction) -> ActionFootprint | None:
        footprint = getattr(self.provider, "footprint", None)
        if footprint is None:
            return None
        # Pure per (state, action); the sleep-set machinery asks for the same footprints once per
        # sleeping event per state.  The scratch lives on the exact state object: semantically
        # equal states can differ in the physical serials footprint events mention, so equal
        # semantic keys must not share footprints — and the cache must not outlive the state.
        scratch = state.action_scratch
        key = ("footprint", action.identity)
        if key not in scratch:
            scratch[key] = footprint(state, action)
        return scratch[key]

    def _information_priority(self, state: DecisionState, action: LegalAction) -> float:
        if self._strategy_builder is not None:
            return self._strategy_builder.action_priority(state, action)
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
        def leaves(node, weight=1.0, seen=frozenset()):
            if isinstance(node, Deterministic):
                context = int((node.state.obs.get("select") or {}).get("context", -1))
                if context != MAIN_DECISION_CONTEXT:
                    if node.state.semantic_key in seen:
                        return None
                    forced = self.provider.actions(node.state)
                    if len(forced) != 1:
                        return None
                    return leaves(
                        self._provider_transition(node.state, forced[0]), weight,
                        seen | {node.state.semantic_key})
                return ((weight, node.state),)
            if isinstance(node, Chance):
                result = []
                for edge in node.children:
                    branch = leaves(edge.node, weight * edge.probability, seen)
                    if branch is None:
                        return None
                    result.extend(branch)
                return tuple(result)
            return None

        def sequence(node, event):
            first = leaves(node)
            if first is None:
                return None
            outcomes = {}
            for probability, child in first:
                action, _footprint = self._action_with_event(child, event)
                if action is None:
                    return None
                second = leaves(self._provider_transition(child, action), probability)
                if second is None:
                    return None
                for branch_probability, final in second:
                    signature = (
                        final.semantic_key, final.legal_menu_digest, self.provider.actor(final))
                    outcomes[signature] = outcomes.get(signature, 0.0) + branch_probability
            return tuple(sorted((signature, round(probability, VALUE_TIE_DECIMALS))
                                for signature, probability in outcomes.items()))

        left_node = self._provider_transition(state, left)
        right_node = self._provider_transition(state, right)
        left_then_right = sequence(left_node, right_footprint.event)
        right_then_left = sequence(right_node, left_footprint.event)
        answer = left_then_right is not None and left_then_right == right_then_left
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

    def _select_our_action(self, state: DecisionState, finite, context: int):
        selected = _select_our_action(finite, context)
        selected_action, selected_result = selected
        if not selected_result.complete:
            return selected
        leaders = tuple(
            pair for pair in finite
            if pair[1].complete
            and round(pair[1].value, VALUE_TIE_DECIMALS) == round(
                selected_result.value, VALUE_TIE_DECIMALS)
        )
        selected_footprint = self._footprint(state, selected_action)
        if selected_footprint is None:
            return selected
        for candidate in sorted(leaders, key=lambda pair: _commutative_order(pair[0])):
            action, result = candidate
            if action == selected_action:
                return selected
            footprint = self._footprint(state, action)
            if footprint is not None and self._commutes(
                    state, action, selected_action, footprint, selected_footprint)[0]:
                return action, result
        return selected

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
            exact.decisions, exact.continuation, exact.execution_complete)
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
                "search_wave": self._strategy_waves.get(state.semantic_key, {}).get(action, 0),
            })
            self._action_bounds[action.identity] = row

    def _state(self, state: DecisionState,
               sleep: tuple[SleepEvent, ...] = ()) -> StateEvaluation:
        now = monotonic()
        if self.nodes >= self.limits.max_nodes or now >= self._deadline:
            self._deadline_hit = self._deadline_hit or now >= self._hard_deadline
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
            ))[:1]
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
            if self.profile.get("search.dead_fetch_pruning_enabled") >= 0.5:
                actions = self._dead_fetch_filter(state, actions)
            if self.profile.get("search.information_dominance_enabled") >= 0.5:
                actions = self._information_dominance_filter(state, actions, footprints)
        deep_strategy = bool(
            self.strategy_snapshot is not None
            and hasattr(self.strategy_snapshot, "hints")
            and any(hint.waypoint > 0 for hint in self.strategy_snapshot.hints)
        )
        strategy_focus = (actor is Actor.OURS
                          and self._strategy_builder is not None
                          and self.profile.get("strategy.focus_enabled") >= 0.5
                          and (key == self._root_key or self._harvesting_candidates
                               or deep_strategy))
        if strategy_focus:
            self._sync_prefix_outcomes()
            beam = self._strategy_builder.build(state, actions)
            self._strategy_beams[key] = beam
            retained = {row.action_key for row in (*beam.focused, *beam.safety)}
            retained.update(row.action_key for row in beam.unknown)
            self._strategy_later_wave[key] = tuple(
                action for action in actions
                if semantic_action_key(action) not in retained)
            self._strategy_waves[key] = {
                action: (0 if semantic_action_key(action) in retained else 1)
                for action in actions
            }
            self._strategy_focus_ranks[key] = {
                row.action_key: index for index, row in enumerate(beam.focused)
            }
            original = {action: index for index, action in enumerate(actions)}
            focus_order = {
                row.action_key: index for index, row in enumerate(beam.focused)
            }
            information_order = {
                action: 0
                for action in actions
                if footprints.get(action.identity) is not None
                and footprints[action.identity].information_first
                and self._information_priority(state, action) > 0.0
            }
            actions = tuple(sorted(actions, key=lambda action: (
                information_order.get(action, 1),
                self._strategy_waves[key][action],
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
        harvest_short_circuit = False
        if key == self._root_key:
            action_waves = self._strategy_waves.get(key, {})
            results_list: list[tuple[LegalAction, Evaluation] | None] = [None] * len(actions)
            branch_nodes = [0] * len(actions)
            branch_capped = [False] * len(actions)
            original_limits = self.limits

            harvest_started = monotonic()
            harvest_target = int(self.profile.get("search.completed_candidate_target"))
            harvest_goal = harvest_target
            protected_bundles = self._protected_bundles(state)
            harvest_share = (self.profile.get("search.protected_bundle_exploration_share")
                             if protected_bundles else
                             self.profile.get("search.completed_candidate_time_share"))
            harvest_deadline = harvest_started + max(
                0.0, self._hard_deadline - harvest_started) * harvest_share
            harvest_order = self._candidate_order(actions)
            completed = []
            seen_sequences = set()
            self._harvesting_candidates = True
            self.limits = SearchLimits(self.production_limits.max_nodes)
            for position, action in enumerate(harvest_order):
                if len(completed) >= harvest_goal or monotonic() >= harvest_deadline:
                    break
                index = actions.index(action)
                while len(completed) < harvest_goal and monotonic() < harvest_deadline:
                    self._deadline = self._budget.root_deadline(
                        monotonic(), harvest_deadline, len(harvest_order) - position)
                    self.nodes = 1
                    result = self._search_action(state, action, child_sleeps[action.identity])
                    incumbent = results_list[index]
                    if (incumbent is None
                            or _ordered_evaluation(result, Actor.OURS)
                            > _ordered_evaluation(incumbent[1], Actor.OURS)):
                        results_list[index] = (action, result)
                    self._bank_candidate(action, result)
                    if (position == 0 and result.execution_complete
                            and semantic_action_key(action) in self._strategy_focus_ranks.get(
                                self._root_key, {})):
                        harvest_goal = min(3, harvest_target + 1)
                    if (set(self._action_bundles(action)).intersection(protected_bundles)
                            and math.isfinite(result.value)
                            and self._candidate_bank.live_tiers.get(action.identity)
                            in {"recoverable", "full"}):
                        harvest_share = self.profile.get("search.protected_bundle_time_share")
                        harvest_deadline = max(
                            harvest_deadline,
                            harvest_started + max(
                                0.0, self._hard_deadline - harvest_started) * harvest_share)
                    branch_nodes[index] += max(1, self.nodes)
                    branch_capped[index] = not result.complete and (
                        self.nodes >= self.production_limits.max_nodes
                        or monotonic() >= self._deadline)
                    sequence = self._sequence_signature(action, result)
                    identities = self._sequence_identities(action, result)
                    if (not self._is_executable_candidate(action, result)
                            or sequence in seen_sequences):
                        break
                    seen_sequences.add(sequence)
                    self._harvest_exclusions.add(identities)
                    self._bank_candidate(action, result)
                    completed.append({
                        "root_action": str(action.identity),
                        "sequence": sequence,
                        "value": result.value,
                        "bellman_complete": result.complete,
                    })
                    break
                finite_results = tuple(
                    pair for pair in results_list
                    if pair is not None and math.isfinite(pair[1].value))
                self._record_incumbent(state, finite_results, context, "candidate_harvest")
            while (self._strategy_builder is not None
                   and len(completed) < harvest_goal
                   and monotonic() < harvest_deadline):
                progress = False
                for action in harvest_order:
                    if len(completed) >= harvest_goal or monotonic() >= harvest_deadline:
                        break
                    index = actions.index(action)
                    self._deadline = harvest_deadline
                    self.nodes = 1
                    result = self._search_action(state, action, child_sleeps[action.identity])
                    branch_nodes[index] += max(1, self.nodes)
                    self._bank_candidate(action, result)
                    sequence = self._sequence_signature(action, result)
                    identities = self._sequence_identities(action, result)
                    if (not self._is_executable_candidate(action, result)
                            or sequence in seen_sequences):
                        continue
                    seen_sequences.add(sequence)
                    self._harvest_exclusions.add(identities)
                    self._bank_candidate(action, result, "safety")
                    completed.append({
                        "root_action": str(action.identity), "sequence": sequence,
                        "value": result.value, "bellman_complete": result.complete,
                    })
                    progress = True
                if not progress:
                    break
            for action in self._safety_candidates(
                    actions, allow_fallback=context != MAIN_DECISION_CONTEXT):
                if action.identity in self._candidate_bank.live:
                    break
                index = actions.index(action)
                self.nodes = 1
                result = self._search_action(state, action, child_sleeps[action.identity])
                results_list[index] = (action, result)
                branch_nodes[index] = max(branch_nodes[index], self.nodes)
                sequence = self._sequence_signature(action, result)
                if self._is_executable_candidate(action, result) and sequence not in seen_sequences:
                    seen_sequences.add(sequence)
                    self._bank_candidate(action, result)
                    completed.append({
                        "root_action": str(action.identity), "sequence": sequence,
                        "value": result.value, "bellman_complete": result.complete,
                    })
                    break
            self._harvesting_candidates = False
            self._candidate_harvest = {
                "target": harvest_target,
                "expanded_target": harvest_goal,
                "time_share": harvest_share,
                "elapsed_seconds": monotonic() - harvest_started,
                "attempted_count": sum(pair is not None for pair in results_list),
                "completed_count": len(completed),
                "completed": tuple(completed),
                "protected_bundles": protected_bundles,
            }
            self._candidate_bank.publish()
            self._stable_checkpoint(state, actions, context)
            self._phase_budgets["candidate_harvest"] = {
                "share": harvest_share,
                "elapsed_seconds": monotonic() - harvest_started,
            }

            probe_started = monotonic()
            challenger_enabled = self.profile.get("search.challenger_enabled") >= 0.5
            probe_share = (self.profile.get("search.challenger_time_share")
                           if challenger_enabled else 0.4)
            probe_hard_deadline = min(
                self._hard_deadline,
                probe_started + max(
                    0.0, self._hard_deadline - self._search_started) * probe_share)
            remaining = [index for index, pair in enumerate(results_list) if pair is None]
            finite_before_probe = tuple(
                pair for pair in results_list
                if pair is not None and math.isfinite(pair[1].value))
            challenger_indices = (set(self._credible_challengers(
                state, actions, remaining, finite_before_probe, context))
                if challenger_enabled else set(remaining))
            for position, index in enumerate(remaining):
                action = actions[index]
                if index not in challenger_indices:
                    if action.identity.kind == "end":
                        result = self._search_action(
                            state, action, child_sleeps[action.identity])
                        results_list[index] = (action, result)
                        self._bank_candidate(action, result, "safety")
                    else:
                        self.limits = SearchLimits(1)
                        self._deadline = probe_hard_deadline
                        self.nodes = 1
                        result = self._search_action(
                            state, action, child_sleeps[action.identity])
                        results_list[index] = (action, result)
                        self._bank_candidate(action, result)
                        branch_nodes[index] = self.nodes
                        branch_capped[index] = not result.complete
                    continue
                wave = action_waves.get(action, 0)
                widening = wave > 0
                probe_nodes = min(
                    self.production_limits.max_nodes,
                    max(1, self.production_limits.root_probe_nodes if not widening else 1),
                )
                self.limits = SearchLimits(probe_nodes)
                self._deadline = self._budget.root_deadline(
                    monotonic(), probe_hard_deadline, len(remaining) - position)
                self.nodes = 1
                result = self._search_action(state, action, child_sleeps[action.identity])
                self._bank_candidate(action, result)
                branch_nodes[index] = self.nodes
                branch_capped[index] = not result.complete and (
                    self.nodes >= probe_nodes or monotonic() >= self._deadline)
                results_list[index] = (action, result)
                self._record_incumbent(
                    state,
                    tuple(pair for pair in results_list
                          if pair is not None and math.isfinite(pair[1].value)),
                    context, "probe")
            self._phase_budgets["challenger"] = {
                "share": probe_share,
                "elapsed_seconds": monotonic() - probe_started,
            }
            results_list = [pair for pair in results_list if pair is not None]
            if len(results_list) == len(actions):
                self._completed_rounds = 1
                self._candidate_bank.publish()
                self._stability_stop = self._stable_checkpoint(
                    state, actions, context)
            self._deadline = self._hard_deadline

            # Bellman probe values order bounded widening rounds; exact results need no more work.
            incomplete = [
                (index, action, result)
                for index, (action, result) in enumerate(results_list)
                if not result.complete
            ]
            if self._stability_stop:
                incomplete = []
            incomplete.sort(
                key=lambda row: _ordered_evaluation(row[2], actor),
                reverse=actor is Actor.OURS,
            )
            if actor is Actor.OURS:
                finite_results = tuple(
                    (action, result) for action, result in results_list
                    if math.isfinite(result.value))
                incumbent = (self._select_our_action(state, finite_results, context)
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
            focus_ranks = self._strategy_focus_ranks.get(key, {})
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
                 if semantic_action_key(row[1]) in focus_ranks),
                key=lambda row: focus_ranks[semantic_action_key(row[1])],
            ))
            selected.extend(row for row in refinement_candidates
                            if row not in selected and row[1].identity.kind == "attack")
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
            reserved_refinements = len(selected)
            refinement_interrupted = False
            for refinement_index, (index, action, probe) in enumerate(ordered_refinements):
                if monotonic() >= self._hard_deadline:
                    self._deadline_hit = True
                    refinement_interrupted = True
                    break
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
                    (reserved_refinements - refinement_index
                     if refinement_index < reserved_refinements
                     else len(ordered_refinements) - refinement_index),
                )
                self.nodes = 1
                refined = self._search_action(state, action, child_sleeps[action.identity])
                branch_nodes[index] += max(0, self.nodes - 1)
                branch_capped[index] = (
                    not refined.complete and self.nodes >= refinement_nodes)
                if (math.isfinite(refined.value)
                        and ((actor is Actor.OURS and _ordered_evaluation(refined, actor)
                              >= _ordered_evaluation(probe, actor))
                             or (actor is Actor.OPPONENT and _ordered_evaluation(refined, actor)
                                 <= _ordered_evaluation(probe, actor)))):
                    results_list[index] = (action, refined)
                    self._bank_candidate(action, refined)
                self._record_incumbent(
                    state,
                    tuple((candidate, evaluated) for candidate, evaluated in results_list
                          if math.isfinite(evaluated.value)),
                    context, "refinement")
                if refinement_width and (refinement_index + 1) % refinement_width == 0:
                    self._candidate_bank.publish()
                    self._completed_rounds = max(
                        self._completed_rounds, 2 + refinement_index // refinement_width)
                    if self._stable_checkpoint(state, actions, context):
                        self._stability_stop = True
                        break
            if (ordered_refinements and not refinement_interrupted and refinement_width
                    and len(ordered_refinements) % refinement_width):
                self._candidate_bank.publish()
                self._completed_rounds = max(
                    self._completed_rounds,
                    2 + (len(ordered_refinements) - 1) // refinement_width)
                self._stability_stop = self._stable_checkpoint(
                    state, actions, context)

            self._root_branch_nodes.extend(branch_nodes)
            self._root_branch_capped.extend(branch_capped)
            self.limits = original_limits
            self._deadline = self._hard_deadline
            self.nodes = 1 + sum(max(0, count - 1) for count in branch_nodes)
            results = tuple(results_list)
        else:
            results_list = []
            ordered_actions = actions
            if actor is Actor.OURS and not self._harvesting_candidates:
                ordered_actions = tuple(sorted(
                    actions, key=lambda row: (row.identity.kind != "end", row.identity)))
            if self._harvesting_candidates and self._harvest_exclusions:
                ordered_actions = tuple(
                    action for action in ordered_actions
                    if (*self._harvest_prefix, action.identity) not in self._harvest_exclusions)
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
                result = self._search_action(state, action, child_sleeps[action.identity])
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
                    incumbent = self._select_our_action(state, finite_results, context)
                    if self._harvesting_candidates and result.execution_complete:
                        harvest_short_circuit = True
                        break
            results = tuple(results_list)
        self._deadline_hit = self._deadline_hit or monotonic() >= self._hard_deadline
        self._active.remove(memo_key)
        finite = [(action, result) for action, result in results if math.isfinite(result.value)]
        if not finite or (actor is Actor.OPPONENT and len(finite) != len(results)):
            answer = StateEvaluation(-math.inf, None,
                                     Evaluation(-math.inf, Ledger(), False,
                                                "one or more legal actions incomplete"), results)
        else:
            if actor is Actor.OURS:
                candidate_finite = tuple(
                    (candidate, self._candidate_bank.checkpoint[candidate.identity])
                    for candidate, _evaluated in finite
                    if candidate.identity in self._candidate_bank.checkpoint)
                if key == self._root_key and self._deadline_hit and candidate_finite:
                    action, result = self._select_timeout_candidate(candidate_finite, context)
                    self._candidate_timeout_fallback = True
                else:
                    action, result = self._select_our_action(state, finite, context)
                    if key == self._root_key:
                        action, result = self._prefer_unresolved_strategy(
                            state, finite, (action, result), context)
            else:
                action, result = min(
                    finite, key=lambda pair: _ordered_evaluation(pair[1], actor))
            proven = (not harvest_short_circuit
                      and result.complete and len(finite) == len(results) and all(
                evaluated.complete for _candidate, evaluated in results)
            )
            evaluation = Evaluation(result.value, result.ledger, proven, result.reason,
                                     result.branches, result.decisions, result.continuation,
                                     (result.execution_complete if actor is Actor.OURS else
                                      all(evaluated.execution_complete
                                          for _candidate, evaluated in results)))
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
