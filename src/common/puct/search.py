from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field, replace
from pathlib import Path

from common.decision import (
    CandidateDisposition, CandidateRoster, DecisionDelta, DecisionFailure, DecisionFailureStage,
    EvaluationStatus, PolicyRequest, PolicySourceIdentity, SearchResult, SearchValue, StateValuation, ValuedCandidate,
)
from common.decision.puct import (
    PuctChanceStatistics, PuctConvergence, PuctEdgeStatistics, PuctEvidence, PuctOutcome, PuctPathStep, PuctPathStop,
    PuctPriorEvidence,
)
from common.decision.turn import (ChancePlan, NodeKind, ProviderCompletion, SearchContractError,
                                  SearchNode, TurnAction, DirectTurnSearchProvider,
                                  WorkerTurnSearchProvider)
from common.decision.action_policy import admissible_actions
from common.ledger.policy import LedgerPolicyModel
from common.ledger.search import UniformPolicyModel
from common.ledger.decision import evaluator_semantics_identity
from .budget import PreparationExhausted, SearchBudget, SearchBudgetExhausted, SearchCancelled
from .priors import prepare_ledger_candidates
from .workers import BoundedWorkers, WorkItem, WorkResult


class _WorkFailure(RuntimeError):
    def __init__(self, category, result):
        super().__init__(result.error or result.error_type)
        self.failure = DecisionFailure(
            DecisionFailureStage.EVALUATION if category == "evaluations" else DecisionFailureStage.PROVIDER,
            result.error_type, result.error or result.error_type)


@dataclass(slots=True)
class _Edge:
    action: TurnAction
    prior: float
    visits: int = 0
    total: float = 0.0
    child: _Node | None = None
    exclusion: str | None = None
    pending: int = 0
    inherited_visits: int = 0


@dataclass(frozen=True)
class _Operation:
    category: str
    function: object
    arguments: tuple
    states: int = 0
    capacity: int = 1
    affinity: str | None = None


@dataclass(slots=True)
class _Node:
    state: SearchNode
    valuation: StateValuation | None = None
    edges: list[_Edge] = field(default_factory=list)
    chance_plan: ChancePlan | None = None
    samples: dict[int, _Node] = field(default_factory=dict)
    sample_visits: dict[int, int] = field(default_factory=dict)
    selections: int = 0
    distribution: object | None = None
    preparation_limited: bool = False

    @property
    def value(self) -> StateValuation:
        if self.valuation is None:
            raise SearchContractError("search node has no valid leaf evaluation")
        return self.valuation


def _tie(seed, node, edge):
    return hashlib.sha256(
        f"{seed}:{node.state.observation.decision_key}:{edge.action.identity}:{edge.action.selection}".encode()
    ).hexdigest()


class PuctSearch:
    identity = "bounded-puct-v1:" + evaluator_semantics_identity(tuple(
        Path(__file__).with_name(name) for name in ("search.py", "budget.py", "priors.py", "workers.py")))

    def __init__(self):
        self.previous = None

    def close(self):
        if self.previous is not None:
            self.previous.provider.close()
            self.previous = None

    reset = close

    def search(self, request, evaluator, policy_model, provider, configuration):
        if isinstance(provider, WorkerTurnSearchProvider):
            worker_backed = True
        elif isinstance(provider, DirectTurnSearchProvider):
            worker_backed = False
        else:
            raise TypeError("PUCT provider does not satisfy a supported provider contract")
        session = _Session(request, evaluator, policy_model, provider, configuration)
        session.worker_backed = worker_backed
        previous = self.previous
        self.previous = None
        if configuration.reuse_tree:
            session.reuse_reason = "no_retained_tree"
            if previous is not None:
                session.inherit(previous)
        if previous is not None:
            previous.provider.close()
        result = session.run()
        if configuration.reuse_tree and result.puct.outcome.permits_action:
            self.previous = session
        else:
            try:
                provider.close()
            except Exception as exc:
                result = replace(result, failure=DecisionFailure.capture(DecisionFailureStage.PROVIDER, exc),
                                 stop_reason="cleanup_failure",
                                 puct=replace(result.puct, outcome=PuctOutcome.HARD_FAILURE))
        return replace(result, puct=replace(result.puct, timing=session.budget.timing()))


class _Session:
    def __init__(self, request, evaluator, policy_model, provider, configuration):
        self.request, self.evaluator, self.policy_model = request, evaluator, policy_model
        self.provider, self.configuration = provider, configuration
        self.budget = SearchBudget(configuration, execution_guard=request.execution_guard)
        self.nodes = {}
        self.values, self.transitions, self.samples = {}, {}, {}
        self.completed = 0
        self.stage = DecisionFailureStage.SEARCH
        self.root = _Node(provider.root)
        self.workers = BoundedWorkers(configuration.worker_count, outstanding_limit=configuration.outstanding_limit,
                                      message_limit=configuration.ipc_message_bytes)
        self.next_task = 0
        self.batches = self.peak_pending = 0
        self.reuse_reason = "fresh_requested"
        self.convergence = []
        self.worker_backed = False

    def inherit(self, previous):
        compatibility = lambda session: (
            replace(session.configuration, remaining_match_seconds=None).identity,
            session.evaluator.identity, session.policy_model.identity, session.request.evaluation_model.identity,
            session.request.baseline_identity, session.root.state.root_turn, session.root.state.perspective_seat)
        if compatibility(self) != compatibility(previous):
            self.reuse_reason = "configuration_or_horizon_changed"
            return
        candidates = [node for node in previous.nodes.values()
                      if node.state.observation.decision_key == self.root.state.observation.decision_key
                      and node.state.kind == self.root.state.kind]
        if len(candidates) != 1:
            self.reuse_reason = "state_not_retained"
            return
        candidate = candidates[0]
        if not self.provider.reuse_from(previous.provider, candidate.state):
            self.reuse_reason = "ownership_or_state_unverified"
            return
        self.root, self.nodes = candidate, previous.nodes
        self.values, self.transitions, self.samples = previous.values, previous.transitions, previous.samples
        self.budget.counts["states"] = previous.budget.counts["states"]
        self.budget.cache_entries = previous.budget.cache_entries
        for node in self.nodes.values():
            for edge in node.edges:
                edge.inherited_visits = edge.visits
        self.reuse_reason = "verified_subtree"

    def run(self):
        failure = None
        outcome = PuctOutcome.SEARCHED
        stop_reason = "simulation_limit"
        try:
            self.stage = DecisionFailureStage.PROVIDER
            actions = tuple(self.provider.legal_actions(self.root.state))
            if self.reuse_reason != "verified_subtree":
                self.root.edges = [_Edge(action, 1 / len(actions)) for action in actions]
            if len(actions) == 1:
                outcome, stop_reason = PuctOutcome.FORCED, "single_legal_action"
            else:
                if self.reuse_reason != "verified_subtree":
                    self.budget.retain()
                with self.budget.phase("search"):
                    self.initialize(self.root.state, existing=self.root)
                    for offset in range(0, self.configuration.simulation_limit, self.configuration.batch_size):
                        self.budget.check()
                        if self.budget.admission_closed is not None:
                            raise SearchBudgetExhausted(self.budget.admission_closed)
                        if not self.root.edges:
                            break
                        self.batch(min(self.configuration.batch_size, self.configuration.simulation_limit - offset))
                        if (self.completed // self.configuration.convergence_interval > len(self.convergence)
                                and len(self.convergence) < self.configuration.convergence_limit):
                            self.convergence.append(PuctConvergence(
                                self.completed, tuple(edge.visits for edge in self.root.edges),
                                tuple(edge.total / edge.visits if edge.visits else None for edge in self.root.edges)))
        except SearchBudgetExhausted as exc:
            stop_reason = exc.reason
        except SearchCancelled:
            outcome, stop_reason = PuctOutcome.CANCELLED, "cancelled"
        except Exception as exc:
            failure = getattr(exc, "failure", None) or DecisionFailure.capture(self.stage, exc)
            outcome, stop_reason = PuctOutcome.HARD_FAILURE, "hard_failure"
        finally:
            try:
                self.workers.close()
                if self.worker_backed:
                    self.budget.release(self.provider.release_worker_states())
            except Exception as exc:
                failure = DecisionFailure.capture(DecisionFailureStage.PROVIDER, exc)
                outcome, stop_reason = PuctOutcome.HARD_FAILURE, "cleanup_failure"
        if outcome is PuctOutcome.SEARCHED and not any(edge.visits for edge in self.root.edges):
            outcome = PuctOutcome.INITIALIZATION_DEGRADED
        return self.result(stop_reason, outcome, failure)

    def initialize(self, state, *, existing=None):
        self.stage = DecisionFailureStage.PROVIDER
        if state.kind is NodeKind.UNAVAILABLE or state.failure:
            raise SearchContractError(state.failure or "provider returned an unavailable node")
        if state.perspective_seat != self.root.state.perspective_seat:
            raise SearchContractError("provider changed the search perspective")
        if state.kind in (NodeKind.PLAYER_DECISION, NodeKind.FORCED_DECISION) and (
                state.actor_seat != self.root.state.perspective_seat
                or state.root_turn != self.root.state.root_turn):
            raise SearchContractError("provider returned a decision beyond the current-turn horizon")
        plan = (self.provider.chance_plan(state, self.configuration.chance_samples)
                if state.kind is NodeKind.CHANCE else None)
        key = (state.kind, state.observation.decision_key, state.boundary_reason,
               None if plan is None else plan.identity)
        if key in self.nodes:
            return self.nodes[key]
        node = existing or _Node(state)
        if len(self.nodes) >= self.configuration.node_limit:
            raise SearchBudgetExhausted("node_limit")
        node.chance_plan = plan
        self.nodes[key] = node
        if plan is not None:
            return node
        valuation = self.evaluate(state.observation)
        node.valuation = valuation
        self.stage = DecisionFailureStage.PROVIDER
        actions = tuple(self.provider.legal_actions(state))
        if actions:
            node.edges = [_Edge(action, 1 / len(actions)) for action in actions]
            allowed = admissible_actions(state.observation, actions, self.configuration.action_policy)
            for edge in node.edges:
                if edge.action not in allowed:
                    edge.exclusion = self.configuration.action_policy
            candidates = tuple(ValuedCandidate(
                action, None, CandidateDisposition.CONTINUES_TURN, EvaluationStatus.UNAVAILABLE)
                for action in actions)
            with self.budget.phase("prior"), self.budget.preparation():
                if (len(actions) > 1 and isinstance(self.policy_model, LedgerPolicyModel)
                        and self.budget.admission_closed is None):
                    try:
                        candidates = prepare_ledger_candidates(self, node, actions)
                    except PreparationExhausted:
                        node.preparation_limited = True
                    except SearchBudgetExhausted as exc:
                        self.budget.stop_admission(exc.reason)
                        node.preparation_limited = True
                roster = CandidateRoster.from_legal_actions(actions, candidates)
                self.stage = DecisionFailureStage.POLICY
                request = PolicyRequest(
                    state.observation, roster, PolicySourceIdentity(
                        self.request.baseline_identity, self.evaluator.identity,
                        self.request.evaluation_model.identity, valuation.scale.identity))
                try:
                    self.budget.prepare(len(actions))
                    distribution = self.policy_model.priors(request)
                except PreparationExhausted:
                    node.preparation_limited = True
                    distribution = UniformPolicyModel().priors(request)
            node.distribution = distribution
            for edge, prior in zip(node.edges, distribution.priors_for(roster)):
                edge.prior = prior
        return node

    def evaluate(self, observation):
        key = observation.valuation_key
        if key in self.values:
            return self.values[key]
        self.budget.check()
        self.budget.cache()
        self.stage = DecisionFailureStage.EVALUATION
        valuation = self.budget.call("evaluations", lambda: self.perform(
            self.evaluator.evaluate, (replace(self.request, state=observation, parent_valuation=None,
                                             observation_delta=None, reuse=None, execution_guard=None),)))
        return self.accept_valuation(observation, valuation)

    def accept_valuation(self, observation, valuation):
        self.stage = DecisionFailureStage.EVALUATION
        if (valuation.perspective != self.root.state.perspective_seat
                or valuation.evaluator_identity != self.evaluator.identity
                or valuation.scale != self.evaluator.value_scale
                or valuation.status is EvaluationStatus.UNAVAILABLE):
            raise SearchContractError("leaf valuation is unavailable or incompatible")
        if isinstance(self.policy_model, LedgerPolicyModel):
            self.policy_model.validate_source(PolicySourceIdentity(
                valuation.baseline_identity, valuation.evaluator_identity,
                valuation.evaluation_model_identity, valuation.scale.identity))
        self.values[observation.valuation_key] = valuation
        return valuation

    def transition(self, node, action):
        key = (node.observation.decision_key, action.identity, tuple(action.selection))
        if key not in self.transitions:
            self.budget.check()
            self.budget.cache()
            self.stage = DecisionFailureStage.PROVIDER
            requested = action if self.worker_backed else action.identity
            self.transitions[key] = self.provider_call("transitions", node, "transition", (requested,))
        return self.transitions[key]

    def sample(self, node, slot):
        plan = self.provider.chance_plan(node, self.configuration.chance_samples)
        key = (plan.identity, slot)
        if key not in self.samples:
            self.budget.check()
            self.budget.cache()
            self.stage = DecisionFailureStage.PROVIDER
            self.samples[key] = self.provider_call("chances", node, "sample_for_search", (self.configuration.seed, slot))
        return self.samples[key]

    def provider_call(self, category, node, operation, arguments):
        item = self.provider_operation(category, node, operation, arguments)
        result = self.budget.call(category, lambda: self.perform(
            item.function, item.arguments, item.affinity),
                                  creates_state=item.states, units=item.capacity)
        return self.provider.accept_work(result) if self.worker_backed else result.node

    def provider_operation(self, category, node, operation, arguments):
        if self.worker_backed:
            item = self.provider.work_item(node, operation, arguments)
            return _Operation(
                category, item.function, item.arguments, item.state_capacity,
                item.operation_capacity, item.affinity)
        return _Operation(
            category, getattr(self.provider, operation), (node, *arguments), 1)

    def perform(self, function, arguments, affinity=None):
        item = WorkItem(self.next_task, function, arguments, affinity)
        self.next_task += 1
        phase = self.budget.phase_name
        result: tuple[WorkResult, ...] = ()
        grant = self.budget.active_grant
        completion = None
        try:
            with self.budget.phase("overhead"):
                result = self.workers.run_batch(
                    (item,), deadline=self.budget.deadline,
                    cancelled=self.budget.cancellation_requested)
        finally:
            self.budget.worker_timing(result, phase)
            if grant is not None:
                if result and result[0].error_type is None and isinstance(result[0].value, ProviderCompletion):
                    completion = result[0].value
                    if self.worker_backed:
                        self.provider.observe_completion(completion, item.affinity)
                self.budget.settle(
                    grant, started=item.task_id in self.workers.started_tasks,
                    completed=bool(result) and result[0].error_type is None,
                    dispatched=item.task_id in self.workers.dispatched_tasks,
                    used_units=None if completion is None else completion.operation_units,
                    used_states=None if completion is None else completion.state_capacity)
        if not result:
            if self.workers.interrupted:
                raise SearchCancelled()
            raise SearchBudgetExhausted("time_limit")
        if result[0].error_type is not None:
            raise _WorkFailure("worker" if grant is None else grant.category, result[0])
        return completion.value if completion is not None else result[0].value

    def async_initialize(self, state):
        if state.kind not in (NodeKind.CHANCE, NodeKind.UNAVAILABLE) and state.observation.valuation_key not in self.values:
            self.budget.cache()
            valuation = yield _Operation("evaluations", self.evaluator.evaluate, (replace(
                self.request, state=state.observation, parent_valuation=None, observation_delta=None,
                reuse=None, execution_guard=None),))
            self.accept_valuation(state.observation, valuation)
        return self.initialize(state)

    def async_provider(self, category, node, operation, arguments):
        result = yield self.provider_operation(category, node, operation, arguments)
        return self.provider.accept_work(result) if self.worker_backed else result.node

    def async_transition(self, node, action):
        key = (node.observation.decision_key, action.identity, tuple(action.selection))
        if key not in self.transitions:
            self.budget.cache()
            requested = action if self.worker_backed else action.identity
            self.transitions[key] = yield from self.async_provider(
                "transitions", node, "transition", (requested,))
        return self.transitions[key]

    def async_sample(self, node, slot):
        plan = self.provider.chance_plan(node, self.configuration.chance_samples)
        key = (plan.identity, slot)
        if key not in self.samples:
            self.budget.cache()
            self.samples[key] = yield from self.async_provider(
                "chances", node, "sample_for_search", (self.configuration.seed, slot))
        return self.samples[key]

    def batch(self, size):
        paths: list[list[_Edge]] = [[] for _ in range(size)]
        chance_paths: list[list[tuple[_Node, int]]] = [[] for _ in range(size)]
        generators = [self.simulate(paths[index], chance_paths[index]) for index in range(size)]
        active = dict.fromkeys(range(size))
        proofs = {}
        self.batches += 1
        self.peak_pending = max(self.peak_pending, size)
        try:
            while active:
                operations, error = {}, None
                for index, value in active.items():
                    try:
                        operations[index] = generators[index].send(value)
                    except StopIteration as complete:
                        proofs[index] = complete.value
                    except Exception as exc:
                        error = error or exc
                if error:
                    raise error
                jobs, indices, grants, affinities = [], {}, {}, {}
                for index, operation in operations.items():
                    try:
                        grant = self.budget.reserve(operation.category, creates_state=operation.states,
                                                    units=operation.capacity)
                    except Exception as exc:
                        error = exc
                        break
                    job = WorkItem(
                        self.next_task, operation.function, operation.arguments,
                        operation.affinity)
                    self.next_task += 1
                    jobs.append(job)
                    indices[job.task_id] = index
                    grants[job.task_id] = grant
                    affinities[job.task_id] = job.affinity
                results: tuple[WorkResult, ...] = ()
                try:
                    with self.budget.phase("overhead"):
                        results = self.workers.run_batch(
                            tuple(jobs), deadline=self.budget.deadline,
                            cancelled=self.budget.cancellation_requested)
                finally:
                    self.budget.worker_timing(results, "search")
                    successful = {result.task_id for result in results if result.error_type is None}
                    completions = {result.task_id: result.value for result in results
                                   if result.error_type is None and isinstance(result.value, ProviderCompletion)}
                    for task_id, grant in grants.items():
                        self.budget.settle(
                            grant, started=task_id in self.workers.started_tasks, completed=task_id in successful,
                            dispatched=task_id in self.workers.dispatched_tasks,
                            used_units=(completions[task_id].operation_units
                                        if task_id in completions else None),
                            used_states=(completions[task_id].state_capacity
                                         if task_id in completions else None))
                active = {}
                for result in results:
                    if result.error_type:
                        error = error or _WorkFailure(grants[result.task_id].category, result)
                    else:
                        value = result.value
                        if isinstance(value, ProviderCompletion) and self.worker_backed:
                            self.provider.observe_completion(
                                value, affinities[result.task_id])
                        active[indices[result.task_id]] = value.value if isinstance(value, ProviderCompletion) else value
                if len(results) != len(jobs):
                    error = error or (SearchCancelled() if self.workers.interrupted
                                      else SearchBudgetExhausted("time_limit"))
                if error:
                    self.budget.stop_admission(getattr(error, "reason", "hard_failure"))
                    for index, value in active.items():
                        try:
                            generators[index].send(value)
                        except StopIteration as complete:
                            proofs[index] = complete.value
                        except Exception:
                            pass
                    raise error
        finally:
            for index in sorted(proofs):
                value = proofs[index]
                for edge in paths[index]:
                    edge.visits += 1
                    edge.total += value
                for node, slot in chance_paths[index]:
                    node.sample_visits[slot] = node.sample_visits.get(slot, 0) + 1
                if paths[index]:
                    self.completed += 1
            for generator, path in zip(generators, paths):
                generator.close()
                for edge in path:
                    edge.pending -= 1

    def simulate(self, path, chance_path):
        node = self.root
        seen = set()
        while id(node) not in seen:
            self.budget.check()
            seen.add(id(node))
            if node.chance_plan is not None:
                plan = node.chance_plan
                rng = random.Random(hashlib.sha256(
                    f"{self.configuration.seed}:{plan.identity}:{node.selections}".encode()).digest())
                slot = rng.choices(range(len(plan.probabilities)), weights=plan.probabilities, k=1)[0]
                node.selections += 1
                chance_path.append((node, slot))
                fresh = slot not in node.samples
                if fresh:
                    successor = yield from self.async_sample(node.state, slot)
                    node.samples[slot] = yield from self.async_initialize(successor)
                node = node.samples[slot]
                if fresh and node.chance_plan is None:
                    break
                continue
            if not node.edges:
                break
            parent_count = sum(edge.visits + edge.pending for edge in node.edges)

            def priority(edge):
                reference = edge.total / edge.visits if edge.visits else node.value.total
                score = reference + self.configuration.exploration * edge.prior * math.sqrt(
                    parent_count + 1) / (1 + edge.visits + edge.pending)
                return score, _tie(self.configuration.seed, node, edge)

            edge = max((item for item in node.edges if item.exclusion is None), key=priority)
            path.append(edge)
            edge.pending += 1
            if edge.child is None:
                successor = yield from self.async_transition(node.state, edge.action)
                if successor.kind is NodeKind.UNAVAILABLE or successor.failure:
                    edge.exclusion = successor.failure or "provider returned an unavailable node"
                    edge.pending -= 1
                    path.pop()
                    if any(item.exclusion is None for item in node.edges):
                        seen.discard(id(node))
                        continue
                    break
                edge.child = yield from self.async_initialize(successor)
                node = edge.child
                if node.chance_plan is None:
                    break
                continue
            node = edge.child
        self.stage = DecisionFailureStage.SEARCH
        if node.valuation is None:
            raise SearchContractError("simulation cannot terminate in unresolved chance")
        return node.value.total

    def result(self, stop_reason, outcome, failure):
        candidates = []
        for edge in self.root.edges:
            value = edge.total / edge.visits if edge.visits else None
            candidates.append(ValuedCandidate(
                edge.action,
                None if value is None else DecisionDelta(value - self.root.value.total, self.root.value.scale),
                CandidateDisposition.FORCED if outcome is PuctOutcome.FORCED else CandidateDisposition.CONTINUES_TURN,
                EvaluationStatus.UNAVAILABLE if value is None else EvaluationStatus.ESTIMATED,
                search_value=None if value is None else SearchValue(value, self.root.value.scale),
                prior=edge.prior, puct=PuctEdgeStatistics(
                    edge.visits, edge.total, inherited_visits=edge.inherited_visits, exclusion=edge.exclusion,
                    tie_break=_tie(self.configuration.seed, self.root, edge))))
        roster = CandidateRoster.from_legal_actions(
            tuple(edge.action for edge in self.root.edges), tuple(candidates), forced=outcome is PuctOutcome.FORCED)
        chances = tuple(PuctChanceStatistics(
            node.chance_plan.identity, node.chance_plan.method, node.chance_plan.estimated,
            len(node.chance_plan.probabilities), len(node.samples), len({id(child) for child in node.samples.values()}),
            sum(node.sample_visits.values())) for node in self.nodes.values() if node.chance_plan is not None)
        variation, variation_stop = self.variation()
        return SearchResult(
            self.root.valuation, roster, self.completed, stop_reason, failure=failure,
            puct=PuctEvidence(self.completed, variation, self.configuration.identity,
                              self.budget.snapshot(), chances, outcome=outcome,
                              batches=self.batches, peak_pending=self.peak_pending,
                              reuse_reason=self.reuse_reason,
                              inherited_visits=sum(edge.inherited_visits for edge in self.root.edges),
                              resources=self.budget.resources(),
                              convergence=tuple(self.convergence), tree_nodes=len(self.nodes),
                              cache_entries=len(self.values) + len(self.transitions) + len(self.samples),
                              cache_capacity_charged=self.budget.cache_entries,
                              retained_engine_states=self.provider.retained_states,
                              peak_retained_engine_states=(
                                  self.provider.peak_retained_states
                                  if self.worker_backed else self.provider.retained_states),
                              principal_variation_stop_reason=variation_stop,
                              reproduction_input=self.provider.reproduction_input(),
                              prior_distributions=tuple(PuctPriorEvidence(
                                  node.state.observation.decision_key, node.distribution,
                                  node.preparation_limited) for node in self.nodes.values()
                                  if node.distribution is not None)))

    def variation(self):
        variation, seen = [], set()
        node: _Node | None = self.root
        stop = PuctPathStop.UNEVALUATED_SUCCESSOR
        while node is not None and id(node) not in seen:
            seen.add(id(node))
            if node.chance_plan is not None:
                if not node.sample_visits:
                    stop = PuctPathStop.UNRESOLVED_CHANCE
                    break
                visits = node.sample_visits
                slot = max(visits, key=lambda key: (visits[key], -key))
                variation.append(PuctPathStep(
                    None, node.state.observation.decision_key, slot, node.chance_plan.probabilities[slot]))
                node = node.samples[slot]
                continue
            if not node.edges:
                stop = {NodeKind.TURN_BOUNDARY: PuctPathStop.TURN_BOUNDARY,
                        NodeKind.INFORMATION_BOUNDARY: PuctPathStop.INFORMATION_BOUNDARY,
                        NodeKind.TERMINAL: PuctPathStop.TERMINAL}.get(
                            node.state.kind, PuctPathStop.NO_COMPLETED_EDGE)
                break
            edge = max(node.edges, key=lambda item: (item.visits, _tie(self.configuration.seed, node, item)))
            if not edge.visits:
                stop = PuctPathStop.NO_COMPLETED_EDGE
                break
            variation.append(PuctPathStep(edge.action.identity, node.state.observation.decision_key))
            node = edge.child
        else:
            if node is not None:
                stop = PuctPathStop.CYCLE
        return tuple(variation), stop
