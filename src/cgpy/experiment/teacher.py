"""Current-contract exhaustive within-turn teacher (ADR-0198)."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from enum import Enum
from time import monotonic

from common.api import ActionIdentity
from common.decision import EvaluationRequest, EvaluationStatus
from common.ledger import LedgerValueEvaluator

from .action_policy import admissible_teacher_actions
from .contracts import ChanceExpansionRequest, ChanceExpansionStatus, NodeKind
from .environment import TurnSearchEnvironment
from .teacher_contracts import (
    TeacherCoverage,
    TeacherLeaf,
    TeacherPathStep,
    TeacherPolicyEntry,
    TeacherRootAction,
    TeacherSearchConfiguration,
    TeacherSearchResult,
    TeacherSearchStatistics,
    TeacherStopReason,
)


@dataclass(frozen=True, slots=True)
class _ActionOutcome:
    action: ActionIdentity
    child: "_NodeEvaluation"


@dataclass(frozen=True, slots=True)
class _NodeEvaluation:
    coverage: TeacherCoverage
    quality: EvaluationStatus
    value: float | None
    stop_reason: TeacherStopReason
    policy: tuple[TeacherPolicyEntry, ...] = ()
    leaves: tuple[TeacherLeaf, ...] = ()
    principal_variation: tuple[TeacherPathStep, ...] = ()
    sequence: tuple[ActionIdentity, ...] | None = None
    alternatives: tuple[_ActionOutcome, ...] = ()
    indifference_set: tuple[ActionIdentity, ...] = ()
    failure: str | None = None


@dataclass(slots=True)
class _MutableStatistics:
    nodes_visited: int = 0
    leaf_evaluations: int = 0
    chance_nodes: int = 0
    chance_branches: int = 0
    cache_hits: int = 0
    transpositions: int = 0
    memo_entries: int = 0
    cycles: int = 0

    def freeze(self, elapsed_seconds: float) -> TeacherSearchStatistics:
        return TeacherSearchStatistics(
            self.nodes_visited, self.leaf_evaluations, self.chance_nodes,
            self.chance_branches, self.cache_hits, self.transpositions,
            self.memo_entries, self.cycles, elapsed_seconds)


@dataclass(slots=True)
class _SearchRun:
    configuration: TeacherSearchConfiguration
    started: float
    statistics: _MutableStatistics
    active: set[str] = field(default_factory=set)
    memo: dict[str, _NodeEvaluation] = field(default_factory=dict)


class _FramePhase(str, Enum):
    ENTER = "enter"
    DECISION = "decision"
    CHANCE = "chance"


@dataclass(slots=True)
class _Frame:
    node: object
    depth: int
    key: str = ""
    kind: NodeKind | None = None
    phase: _FramePhase = _FramePhase.ENTER
    active: bool = False
    actions: tuple[ActionIdentity, ...] = ()
    expansion: object | None = None
    children: list[_NodeEvaluation] = field(default_factory=list)


def _quality(values) -> EvaluationStatus:
    values = tuple(values)
    if any(value is EvaluationStatus.UNAVAILABLE for value in values):
        return EvaluationStatus.UNAVAILABLE
    if any(value is EvaluationStatus.ESTIMATED for value in values):
        return EvaluationStatus.ESTIMATED
    return EvaluationStatus.COMPLETE


def _neutral_choice(tied: tuple[int, ...], seed: int) -> int:
    return min(tied, key=lambda index: hashlib.blake2b(
        f"{seed}:{index}".encode(), digest_size=8).digest())


def _merge_policy(evaluations) -> tuple[TeacherPolicyEntry, ...]:
    merged = {}
    for evaluation in evaluations:
        for entry in evaluation.policy:
            previous = merged.setdefault(entry.state_key, entry)
            if previous != entry:
                raise ValueError("one Search State Key produced conflicting teacher actions")
    return tuple(merged.values())


def merge_root_action_results(
        results, configuration: TeacherSearchConfiguration, *,
        elapsed_seconds: float | None = None) -> TeacherSearchResult:
    results = tuple(results)
    if not results:
        raise ValueError("root-action merge requires at least one Teacher result")
    first = results[0]
    metadata = (
        first.root_state_key, first.snapshot_id, first.experiment_seed,
        first.configuration_identity, first.evaluator_identity,
        first.evaluation_model_identity, first.baseline_identity,
        first.baseline_value, first.baseline_quality,
    )
    for result in results:
        candidate = (
            result.root_state_key, result.snapshot_id, result.experiment_seed,
            result.configuration_identity, result.evaluator_identity,
            result.evaluation_model_identity, result.baseline_identity,
            result.baseline_value, result.baseline_quality,
        )
        if candidate != metadata or result.configuration_identity != configuration.identity:
            raise ValueError("root-action Teacher results use different search contracts")
        if len(result.root_actions) != 1:
            raise ValueError("each root-action Teacher result must contain one action")
    root_actions = tuple(result.root_actions[0] for result in results)
    statistics = TeacherSearchStatistics(
        nodes_visited=sum(result.statistics.nodes_visited for result in results),
        leaf_evaluations=sum(result.statistics.leaf_evaluations for result in results),
        chance_nodes=sum(result.statistics.chance_nodes for result in results),
        chance_branches=sum(result.statistics.chance_branches for result in results),
        cache_hits=sum(result.statistics.cache_hits for result in results),
        transpositions=sum(result.statistics.transpositions for result in results),
        memo_entries=sum(result.statistics.memo_entries for result in results),
        cycles=sum(result.statistics.cycles for result in results),
        elapsed_seconds=(
            max(result.statistics.elapsed_seconds for result in results)
            if elapsed_seconds is None else max(0.0, float(elapsed_seconds))),
    )
    incomplete = tuple(action for action in root_actions
                       if action.coverage is not TeacherCoverage.COMPLETE)
    if incomplete:
        failed = incomplete[0]
        coverage = (TeacherCoverage.UNAVAILABLE
                    if all(action.coverage is TeacherCoverage.UNAVAILABLE
                           for action in root_actions)
                    else TeacherCoverage.INCOMPLETE)
        return TeacherSearchResult(
            *metadata[:8], first.baseline_quality, root_actions,
            None, (), (), (), (), None, coverage,
            _quality((first.baseline_quality,
                      *(action.value_quality for action in root_actions))),
            failed.stop_reason, statistics, False,
            failed.failure or first.failure)
    best = max(action.expected_value for action in root_actions)
    tied = tuple(index for index, action in enumerate(root_actions)
                 if best - action.expected_value <= configuration.noise_tolerance)
    selected_index = _neutral_choice(tied, configuration.tie_seed)
    selected_action = root_actions[selected_index]
    selected_result = results[selected_index]
    indifference = tuple(root_actions[index].action for index in tied)
    decision_quality = _quality(action.value_quality for action in root_actions)
    root_entry = TeacherPolicyEntry(
        first.root_state_key, selected_action.action, selected_action.expected_value,
        decision_quality, indifference)
    selected_policy = (root_entry,) + tuple(
        entry for entry in selected_result.selected_policy
        if entry.state_key != first.root_state_key)
    return TeacherSearchResult(
        *metadata[:8], first.baseline_quality, root_actions,
        selected_action.action, indifference, selected_policy,
        selected_result.leaves, selected_result.principal_variation,
        selected_result.best_full_sequence, TeacherCoverage.COMPLETE,
        _quality((first.baseline_quality, decision_quality)),
        TeacherStopReason.COMPLETE, statistics, False, selected_result.failure)


class WithinHorizonTeacher:
    identity = "cgpy-within-horizon-teacher-v2"

    def __init__(self, evaluator=None, *, clock=monotonic):
        self.evaluator = evaluator or LedgerValueEvaluator()
        self.clock = clock

    def search(self, snapshot, *, evaluation_model, experiment_seed: int,
               configuration: TeacherSearchConfiguration = TeacherSearchConfiguration(),
               baseline_identity: str | None = None) -> TeacherSearchResult:
        return self.search_environment(
            TurnSearchEnvironment.from_snapshot(snapshot),
            evaluation_model=evaluation_model, experiment_seed=experiment_seed,
            configuration=configuration, baseline_identity=baseline_identity,
            snapshot_id=snapshot.snapshot_id)

    def search_environment(
            self, environment, *, evaluation_model, experiment_seed: int,
            configuration: TeacherSearchConfiguration = TeacherSearchConfiguration(),
            baseline_identity: str | None = None,
            snapshot_id: str | None = None) -> TeacherSearchResult:
        started = self.clock()
        statistics = _MutableStatistics()
        root = environment.root
        baseline_value = None
        baseline_quality = EvaluationStatus.UNAVAILABLE
        baseline_failure = None
        try:
            baseline = self.evaluator.evaluate(EvaluationRequest(root, evaluation_model))
            baseline_quality = baseline.status
            if baseline.status is not EvaluationStatus.UNAVAILABLE:
                baseline_value = baseline.total
            else:
                baseline_failure = "root Ledger evaluation unavailable"
        except Exception as exc:
            baseline_failure = f"{type(exc).__name__}: {exc}"
        run = _SearchRun(configuration, started, statistics)
        root_evaluation = self._evaluate(
            environment, root, evaluation_model, int(experiment_seed),
            run)
        root_actions = tuple(self._root_action(
            root, outcome, baseline_value)
                             for outcome in root_evaluation.alternatives)
        preferred = (root_evaluation.policy[0].action
                     if root_evaluation.coverage is TeacherCoverage.COMPLETE
                     and root_evaluation.policy else None)
        elapsed = max(0.0, self.clock() - started)
        benchmark_ready = False
        return TeacherSearchResult(
            environment.state_key(root).digest, snapshot_id, int(experiment_seed),
            configuration.identity, self.evaluator.identity, evaluation_model.identity,
            baseline_identity, baseline_value, baseline_quality, root_actions,
            preferred, root_evaluation.indifference_set, root_evaluation.policy,
            root_evaluation.leaves, root_evaluation.principal_variation,
            root_evaluation.sequence, root_evaluation.coverage,
            _quality((baseline_quality, root_evaluation.quality)),
            root_evaluation.stop_reason, statistics.freeze(elapsed),
            benchmark_ready, root_evaluation.failure or baseline_failure)

    def _evaluate(self, environment, node, evaluation_model, experiment_seed,
                  run: _SearchRun, depth: int = 0) -> _NodeEvaluation:
        configuration = run.configuration
        statistics = run.statistics
        stack = [_Frame(node, depth)]
        answer = None

        def finish(result: _NodeEvaluation) -> None:
            nonlocal answer
            frame = stack.pop()
            if frame.active:
                run.active.remove(frame.key)
                if result.coverage is TeacherCoverage.COMPLETE:
                    run.memo[frame.key] = result
                    statistics.memo_entries = len(run.memo)
            if stack:
                stack[-1].children.append(result)
            else:
                answer = result

        while stack:
            frame = stack[-1]
            if frame.phase is _FramePhase.ENTER:
                frame.key = environment.state_key(frame.node).digest
                memoized = run.memo.get(frame.key)
                if memoized is not None:
                    statistics.cache_hits += 1
                    statistics.transpositions += 1
                    finish(memoized)
                    continue
                if frame.key in run.active:
                    statistics.cycles += 1
                    finish(_NodeEvaluation(
                        TeacherCoverage.INCOMPLETE, EvaluationStatus.UNAVAILABLE, None,
                        TeacherStopReason.CYCLE,
                        failure="active-path Search State Key cycle"))
                    continue
                if statistics.nodes_visited >= configuration.node_cap:
                    finish(_NodeEvaluation(
                        TeacherCoverage.INCOMPLETE, EvaluationStatus.UNAVAILABLE, None,
                        TeacherStopReason.NODE_CAP, failure="teacher node cap reached"))
                    continue
                if frame.depth >= configuration.path_node_cap:
                    finish(_NodeEvaluation(
                        TeacherCoverage.INCOMPLETE, EvaluationStatus.UNAVAILABLE, None,
                        TeacherStopReason.PATH_CAP,
                        failure="teacher path-node cap reached"))
                    continue
                if self.clock() - run.started >= configuration.time_cap_seconds:
                    finish(_NodeEvaluation(
                        TeacherCoverage.INCOMPLETE, EvaluationStatus.UNAVAILABLE, None,
                        TeacherStopReason.TIME_CAP, failure="teacher time cap reached"))
                    continue
                run.active.add(frame.key)
                frame.active = True
                statistics.nodes_visited += 1
                frame.kind = environment.node_kind(frame.node)
                if frame.kind in (
                        NodeKind.TERMINAL, NodeKind.TURN_BOUNDARY,
                        NodeKind.INFORMATION_BOUNDARY):
                    statistics.leaf_evaluations += 1
                    try:
                        valuation = self.evaluator.evaluate(EvaluationRequest(
                            frame.node, evaluation_model))
                    except Exception as exc:
                        finish(_NodeEvaluation(
                            TeacherCoverage.UNAVAILABLE, EvaluationStatus.UNAVAILABLE, None,
                            TeacherStopReason.EVALUATION_UNAVAILABLE,
                            failure=f"{type(exc).__name__}: {exc}"))
                        continue
                    if valuation.status is EvaluationStatus.UNAVAILABLE:
                        finish(_NodeEvaluation(
                            TeacherCoverage.UNAVAILABLE, valuation.status, None,
                            TeacherStopReason.EVALUATION_UNAVAILABLE,
                            failure="Ledger leaf evaluation unavailable"))
                        continue
                    leaf = TeacherLeaf(
                        frame.key, frame.kind, 1.0, valuation.total, valuation.status)
                    finish(_NodeEvaluation(
                        TeacherCoverage.COMPLETE, valuation.status, valuation.total,
                        TeacherStopReason.COMPLETE, leaves=(leaf,), sequence=()))
                    continue
                if frame.kind is NodeKind.CHANCE:
                    statistics.chance_nodes += 1
                    remaining = configuration.chance_branch_cap - statistics.chance_branches
                    if remaining <= 0:
                        finish(_NodeEvaluation(
                            TeacherCoverage.INCOMPLETE, EvaluationStatus.UNAVAILABLE, None,
                            TeacherStopReason.CHANCE_CAP,
                            failure="teacher chance-branch cap reached"))
                        continue
                    try:
                        frame.expansion = environment.expand(
                            frame.node, ChanceExpansionRequest(
                                experiment_seed,
                                min(configuration.exact_outcome_limit, remaining),
                                min(configuration.chance_sample_count, remaining)))
                    except Exception as exc:
                        finish(_NodeEvaluation(
                            TeacherCoverage.UNAVAILABLE, EvaluationStatus.UNAVAILABLE, None,
                            TeacherStopReason.CHANCE_INCOMPLETE,
                            failure=f"{type(exc).__name__}: {exc}"))
                        continue
                    expansion = frame.expansion
                    statistics.chance_branches += min(expansion.requested_count, remaining)
                    reduced = min(configuration.chance_sample_count, remaining) \
                        < configuration.chance_sample_count
                    if (expansion.requested_count > remaining
                            or (reduced and expansion.status is ChanceExpansionStatus.ESTIMATED)):
                        finish(_NodeEvaluation(
                            TeacherCoverage.INCOMPLETE, EvaluationStatus.UNAVAILABLE, None,
                            TeacherStopReason.CHANCE_CAP,
                            failure="teacher chance-branch cap cannot fund the expansion"))
                        continue
                    if expansion.status in (
                            ChanceExpansionStatus.INCOMPLETE,
                            ChanceExpansionStatus.UNAVAILABLE):
                        coverage = (TeacherCoverage.INCOMPLETE
                                    if expansion.status is ChanceExpansionStatus.INCOMPLETE else
                                    TeacherCoverage.UNAVAILABLE)
                        finish(_NodeEvaluation(
                            coverage, EvaluationStatus.UNAVAILABLE, None,
                            TeacherStopReason.CHANCE_INCOMPLETE,
                            failure=expansion.failure or expansion.status.value))
                        continue
                    frame.phase = _FramePhase.CHANCE
                    continue
                if frame.kind in (NodeKind.PLAYER_DECISION, NodeKind.FORCED_DECISION):
                    legal = admissible_teacher_actions(
                        frame.node.observation,
                        environment.legal_actions(frame.node),
                        configuration.action_policy)
                    frame.actions = tuple(action.identity for action in legal)
                    if not frame.actions:
                        finish(_NodeEvaluation(
                            TeacherCoverage.UNAVAILABLE, EvaluationStatus.UNAVAILABLE, None,
                            TeacherStopReason.EMPTY_DECISION,
                            failure="decision has no legal actions"))
                        continue
                    frame.phase = _FramePhase.DECISION
                    continue
                finish(_NodeEvaluation(
                    TeacherCoverage.UNAVAILABLE, EvaluationStatus.UNAVAILABLE, None,
                    TeacherStopReason.UNAVAILABLE,
                    failure=f"unsupported Search Node kind {frame.kind.value}"))
                continue

            if frame.phase is _FramePhase.DECISION:
                if len(frame.children) < len(frame.actions):
                    action = frame.actions[len(frame.children)]
                    try:
                        transition = environment.transition(frame.node, action)
                    except Exception as exc:
                        frame.children.append(_NodeEvaluation(
                            TeacherCoverage.UNAVAILABLE, EvaluationStatus.UNAVAILABLE, None,
                            TeacherStopReason.TRANSITION_FAILURE,
                            failure=f"{type(exc).__name__}: {exc}"))
                        continue
                    if transition.node is None:
                        frame.children.append(_NodeEvaluation(
                            TeacherCoverage.UNAVAILABLE, EvaluationStatus.UNAVAILABLE, None,
                            TeacherStopReason.TRANSITION_FAILURE,
                            failure=transition.failure))
                        continue
                    stack.append(_Frame(transition.node, frame.depth + 1))
                    continue
                finish(self._decision_result(
                    frame.key, frame.kind, frame.actions,
                    tuple(frame.children), configuration))
                continue

            expansion = frame.expansion
            if len(frame.children) < len(expansion.successors):
                successor = expansion.successors[len(frame.children)]
                stack.append(_Frame(successor.node, frame.depth + 1))
                continue
            finish(self._chance_result(
                frame.key, expansion, tuple(frame.children)))

        return answer

    @staticmethod
    def _decision_result(state_key, kind, actions, children,
                         configuration) -> _NodeEvaluation:
        outcomes = tuple(_ActionOutcome(action, child)
                         for action, child in zip(actions, children))
        if any(child.coverage is not TeacherCoverage.COMPLETE for child in children):
            failure = next(child for child in children
                           if child.coverage is not TeacherCoverage.COMPLETE)
            coverage = (TeacherCoverage.UNAVAILABLE
                        if all(child.coverage is TeacherCoverage.UNAVAILABLE
                               for child in children) else TeacherCoverage.INCOMPLETE)
            return _NodeEvaluation(
                coverage, _quality(child.quality for child in children), None,
                failure.stop_reason, alternatives=outcomes, failure=failure.failure)
        best = max(child.value for child in children)
        tied = tuple(index for index, child in enumerate(children)
                     if best - child.value <= configuration.noise_tolerance)
        selected_index = _neutral_choice(tied, configuration.tie_seed)
        selected = outcomes[selected_index]
        indifference = tuple(actions[index] for index in tied)
        quality = _quality(child.quality for child in children)
        entry = TeacherPolicyEntry(
            state_key, selected.action, selected.child.value, quality, indifference)
        step = TeacherPathStep(state_key, kind, action=selected.action)
        sequence = (None if selected.child.sequence is None else
                    (selected.action,) + selected.child.sequence)
        return _NodeEvaluation(
            TeacherCoverage.COMPLETE, quality, selected.child.value,
            TeacherStopReason.COMPLETE, (entry,) + selected.child.policy,
            selected.child.leaves, (step,) + selected.child.principal_variation,
            sequence, outcomes, indifference)

    @staticmethod
    def _chance_result(state_key, expansion, children) -> _NodeEvaluation:
        if any(child.coverage is not TeacherCoverage.COMPLETE for child in children):
            failed = next(child for child in children
                          if child.coverage is not TeacherCoverage.COMPLETE)
            coverage = (TeacherCoverage.UNAVAILABLE
                        if all(child.coverage is TeacherCoverage.UNAVAILABLE
                               for child in children) else TeacherCoverage.INCOMPLETE)
            return _NodeEvaluation(
                coverage, _quality(child.quality for child in children), None,
                failed.stop_reason, failure=failed.failure)
        value = math.fsum(successor.probability * child.value
                          for successor, child in zip(expansion.successors, children))
        quality = _quality(child.quality for child in children)
        if expansion.status is ChanceExpansionStatus.ESTIMATED:
            quality = EvaluationStatus.ESTIMATED
        leaves = tuple(TeacherLeaf(
            leaf.state_key, leaf.kind, successor.probability * leaf.probability,
            leaf.value, leaf.value_quality)
                       for successor, child in zip(expansion.successors, children)
                       for leaf in child.leaves)
        pv_index = max(range(len(expansion.successors)),
                       key=lambda index: expansion.successors[index].probability)
        successor = expansion.successors[pv_index]
        chance_step = TeacherPathStep(
            state_key, NodeKind.CHANCE,
            branch_keys=tuple(branch.digest for branch in successor.branch_keys),
            probability=successor.probability)
        sequence = children[0].sequence if len(children) == 1 else None
        return _NodeEvaluation(
            TeacherCoverage.COMPLETE, quality, value, TeacherStopReason.COMPLETE,
            _merge_policy(children), leaves,
            (chance_step,) + children[pv_index].principal_variation,
            sequence)

    @staticmethod
    def _root_action(root, outcome: _ActionOutcome,
                     baseline: float | None) -> TeacherRootAction:
        child = outcome.child
        value = child.value if child.coverage is TeacherCoverage.COMPLETE else None
        state_key = root.state_key.digest
        policy = child.policy
        principal = child.principal_variation
        sequence = child.sequence
        if value is not None:
            entry = TeacherPolicyEntry(
                state_key, outcome.action, value, child.quality, (outcome.action,))
            policy = (entry,) + policy
            principal = (TeacherPathStep(
                state_key, root.kind, action=outcome.action),) + principal
            sequence = None if sequence is None else (outcome.action,) + sequence
        return TeacherRootAction(
            outcome.action, child.coverage, child.quality, value,
            None if value is None or baseline is None else value - baseline,
            child.stop_reason,
            policy, child.leaves, principal, sequence, child.failure)


__all__ = ("WithinHorizonTeacher", "merge_root_action_results")
