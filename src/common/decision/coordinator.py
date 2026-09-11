from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Protocol, cast

from common.observation import ObservationDelta, ObservationState

from .components import (
    CollaboratorKind, DecisionPolicy, DecisionPolicyRequest, DecisionRequirements,
    EvaluationModel,
    EvaluationRequest, FailSafeContext, FailSafePolicy, FailSafePolicyRequest,
    IdentifiedConfiguration,
    PolicyModel, SearchAlgorithm, ValueEvaluator,
)
from .configuration import DecisionDeadlineExceeded
from .identity import ActionChoiceIdentity
from .outcomes import (
    DecisionFailure, DecisionFailureStage, SearchOutcome, SearchOutcomeStatus,
    SearchTermination,
)
from .results import (
    BehaviorIdentity, DecisionEvidence, DecisionResult, FailSafeSelection, ForcedSelection,
    NoSelection, PolicySelection, SearchResult,
)
from .values import StateValuation


LOTTERY_DIGEST_BYTES = 8


class SearchProvider(Protocol):
    @property
    def identity(self) -> str: ...


class ExecutionGuard(Protocol):
    def check(self) -> None: ...


SearchConfiguration = IdentifiedConfiguration | str
PolicyConfiguration = IdentifiedConfiguration | str
FailureHandler = Callable[[EvaluationRequest, DecisionFailure], SearchResult]


class SearchWithPolicyModel(Protocol):
    def search(self, request: EvaluationRequest, evaluator: ValueEvaluator,
               configuration: SearchConfiguration, *,
               policy_model: PolicyModel) -> SearchResult: ...


class SearchWithProvider(Protocol):
    def search(self, request: EvaluationRequest, evaluator: ValueEvaluator,
               configuration: SearchConfiguration, *,
               provider: SearchProvider) -> SearchResult: ...


class SearchWithPolicyModelAndProvider(Protocol):
    def search(self, request: EvaluationRequest, evaluator: ValueEvaluator,
               configuration: SearchConfiguration, *, policy_model: PolicyModel,
               provider: SearchProvider) -> SearchResult: ...


class DecisionPolicyWithEvidence(Protocol):
    def choose_with_evidence(self, request: DecisionPolicyRequest) -> DecisionEvidence: ...


class FailSafePolicyWithEvidence(Protocol):
    def choose_with_evidence(self, request: FailSafePolicyRequest) -> DecisionEvidence: ...


def neutral_lottery_choice(candidates: tuple[ActionChoiceIdentity, ...],
                           configuration: PolicyConfiguration) -> ActionChoiceIdentity:
    if not candidates:
        raise ValueError("neutral lottery requires a candidate")
    seed = int(getattr(configuration, "tie_seed", 0))
    return min(enumerate(candidates), key=lambda item: hashlib.blake2b(
        f"{seed}:{item[0]}".encode("utf-8"),
        digest_size=LOTTERY_DIGEST_BYTES).digest())[1]


@dataclass(frozen=True, slots=True)
class DecisionCoordinator:
    evaluator: ValueEvaluator
    evaluation_model: EvaluationModel
    search: SearchAlgorithm
    search_configuration: SearchConfiguration
    decision_policy: DecisionPolicy
    policy_configuration: PolicyConfiguration
    policy_model: PolicyModel | None = None
    behavior_identity: BehaviorIdentity | None = None
    fail_safe_policy: FailSafePolicy | None = None
    failure_handler: FailureHandler | None = None
    ledger_baseline_identity: str | None = None

    def __post_init__(self) -> None:
        bindings = (
            (self.evaluator, self.evaluation_model),
            (self.search, self.search_configuration),
            (self.decision_policy, self.policy_configuration),
            (self.policy_model, None),
            (self.fail_safe_policy, self.policy_configuration),
        )
        for component, configuration in bindings:
            if component is None:
                continue
            contract = getattr(component, "contract", None)
            if contract is None:
                continue
            if contract.identity != component.identity:
                raise ValueError("component identity differs from its Component Contract")
            if configuration is not None:
                configuration_identities = {
                    type(configuration).__name__,
                    str(getattr(configuration, "identity", configuration)),
                }
                if contract.configuration_identity not in configuration_identities:
                    raise ValueError("component rejects its injected configuration")
        search_contract = getattr(self.search, "contract", None)
        if search_contract is not None:
            if (search_contract.required_collaborators
                    != frozenset(self.search.required_collaborators)
                    or search_contract.optional_collaborators
                    != frozenset(self.search.optional_collaborators)):
                raise ValueError("search collaborator declarations differ from its contract")
        policy_contract = getattr(self.decision_policy, "contract", None)
        if search_contract is not None and policy_contract is not None:
            declared_required = frozenset(self.decision_policy.required_statistics)
            if policy_contract.required_statistics != declared_required:
                raise ValueError("decision-policy statistic declarations differ from its contract")
            if not declared_required.issubset(search_contract.produced_statistics):
                raise ValueError("search cannot produce decision-policy required statistics")
        accepted_model = getattr(self.evaluator, "accepted_model_identity", None)
        if accepted_model not in (None, "*", self.evaluation_model.identity):
            raise ValueError("evaluator does not accept the Evaluation Model")
        required = tuple(getattr(self.search, "required_collaborators", ()))
        if (CollaboratorKind.POLICY_MODEL in required
                and self.policy_model is None):
            raise ValueError("search requires a policy model")
        identity = self.behavior_identity
        if identity is None:
            return
        actual = (
            self.evaluator.identity,
            self.evaluation_model.identity,
            self.search.identity,
            "" if self.policy_model is None else self.policy_model.identity,
            self.decision_policy.identity,
        )
        declared = (
            identity.evaluator,
            identity.evaluation_model,
            identity.search,
            identity.policy_model,
            identity.decision_policy,
        )
        if actual != declared:
            raise ValueError("Behavior Identity does not match injected components")

    def decide(
            self,
            state: ObservationState,
            *,
            provider: SearchProvider | None = None,
            parent_valuation: StateValuation | None = None,
            observation_delta: ObservationDelta | None = None,
            execution_guard: ExecutionGuard | None = None,
            strict: bool = False,
            failure: DecisionFailure | None = None,
            recovery_context: FailSafeContext | None = None,
    ) -> DecisionResult:
        request = EvaluationRequest(
            state=state,
            evaluation_model=self.evaluation_model,
            root_perspective=state.seat,
            parent_valuation=parent_valuation,
            observation_delta=observation_delta,
            execution_guard=execution_guard,
            baseline_identity=self.ledger_baseline_identity,
        )
        if failure is not None:
            if self.failure_handler is None:
                raise ValueError("decision failure requires a failure handler")
            result = self.failure_handler(request, failure)
        else:
            try:
                result = self._search(request, provider)
            except DecisionDeadlineExceeded:
                raise
            except Exception as exc:
                if strict or self.failure_handler is None:
                    raise
                captured = getattr(exc, "failure", None) or DecisionFailure.capture(
                    DecisionFailureStage.SEARCH, exc)
                result = self.failure_handler(request, captured)
        self._validate_search_result(request, result)
        if not result.roster.actions:
            return DecisionResult(result, NoSelection(result.outcome.status), self.behavior_identity)
        if result.outcome.status is SearchOutcomeStatus.HARD_FAILURE:
            if self.fail_safe_policy is None:
                return DecisionResult(
                    result, NoSelection(result.outcome.status), self.behavior_identity)
            return self._recover(state, result, recovery_context)
        if not result.outcome.permits_action:
            if (result.outcome.status is SearchOutcomeStatus.INSUFFICIENT_INITIALIZATION
                    and self.fail_safe_policy is not None):
                return self._recover(state, result, recovery_context)
            return DecisionResult(result, NoSelection(result.outcome.status), self.behavior_identity)
        if result.roster.forced and len(result.roster.actions) == 1:
            return DecisionResult(
                result, ForcedSelection(result.roster.identities[0]), self.behavior_identity)
        required = tuple(getattr(self.decision_policy, "required_statistics", ()))
        missing = tuple(statistic for statistic in required
                        if not result.outcome.coverage.choices_for(statistic))
        if missing:
            raise ValueError(f"decision policy requirements are not covered: {missing!r}")
        policy_request = DecisionPolicyRequest(
            result.roster, result.candidates, result.outcome,
            result.statistics, result.evidence, self.policy_configuration,
            DecisionRequirements(required))
        try:
            choose_with_evidence = getattr(
                self.decision_policy, "choose_with_evidence", None)
            if choose_with_evidence is None:
                choice = self.decision_policy.choose(policy_request)
                evidence = None
            else:
                evidence = cast(
                    DecisionPolicyWithEvidence, self.decision_policy,
                ).choose_with_evidence(policy_request)
                choice = evidence.choice
            resolution = (ForcedSelection(choice, evidence) if result.roster.forced
                          else PolicySelection(choice, evidence))
            return DecisionResult(result, resolution, self.behavior_identity)
        except Exception as exc:
            if strict or self.fail_safe_policy is None:
                raise
            return self.recover(
                state, result,
                DecisionFailure.capture(DecisionFailureStage.POLICY, exc),
                recovery_context)

    def _search(
            self,
            request: EvaluationRequest,
            provider: SearchProvider | None,
    ) -> SearchResult:
        required = tuple(getattr(self.search, "required_collaborators", ()))
        needs_policy = CollaboratorKind.POLICY_MODEL in required
        needs_provider = CollaboratorKind.PROVIDER in required
        policy_model = self.policy_model
        provider_value = provider
        if needs_policy and policy_model is None:
            raise ValueError("search requires a policy model")
        if needs_provider and provider_value is None:
            raise ValueError("search requires a provider")
        if needs_policy and needs_provider:
            assert policy_model is not None and provider_value is not None
            combined = cast(SearchWithPolicyModelAndProvider, self.search)
            return combined.search(
                request, self.evaluator, self.search_configuration,
                policy_model=policy_model, provider=provider_value)
        if needs_policy:
            assert policy_model is not None
            policy_search = cast(SearchWithPolicyModel, self.search)
            return policy_search.search(
                request, self.evaluator, self.search_configuration,
                policy_model=policy_model)
        if needs_provider:
            assert provider_value is not None
            provider_search = cast(SearchWithProvider, self.search)
            return provider_search.search(
                request, self.evaluator, self.search_configuration,
                provider=provider_value)
        return self.search.search(request, self.evaluator, self.search_configuration)

    def _recover(
            self,
            state: ObservationState,
            result: SearchResult,
            context: FailSafeContext | None = None,
            failure: DecisionFailure | None = None,
    ) -> DecisionResult:
        if self.fail_safe_policy is None:
            raise ValueError("failed search result requires a fail-safe policy")
        failure = failure or result.outcome.failure or DecisionFailure(
            DecisionFailureStage.SEARCH,
            "InsufficientInitialization",
            "search produced no comparable candidate",
        )
        recovery_outcome = result.outcome
        if recovery_outcome.permits_action or recovery_outcome.failure != failure:
            recovery_outcome = SearchOutcome(
                SearchOutcomeStatus.HARD_FAILURE,
                result.outcome.coverage,
                SearchTermination("coordinator", failure.stage.value, 1),
                failure,
            )
        request = FailSafePolicyRequest(
            state, result.roster, result.candidates, recovery_outcome,
            result.outcome, result.evidence, failure,
            self.policy_configuration, context)
        choose_with_evidence = getattr(self.fail_safe_policy, "choose_with_evidence", None)
        if choose_with_evidence is None:
            choice = self.fail_safe_policy.choose(request)
            evidence = None
        else:
            evidence = cast(
                FailSafePolicyWithEvidence, self.fail_safe_policy,
            ).choose_with_evidence(request)
            choice = evidence.choice
        return DecisionResult(
            result, FailSafeSelection(choice, failure, evidence), self.behavior_identity)

    def recover(
            self,
            state: ObservationState,
            result: SearchResult,
            failure: DecisionFailure,
            context: FailSafeContext | None = None,
    ) -> DecisionResult:
        return self._recover(state, result, context, failure)

    def _validate_search_result(
            self,
            request: EvaluationRequest,
            result: SearchResult,
    ) -> None:
        if result.roster.decision_key != request.state.decision_key:
            raise ValueError("search roster is not proven for Evaluation Request")
        request_choices = tuple(ActionChoiceIdentity.from_action(action)
                                for action in request.state.legal_actions)
        if result.roster.identities != request_choices:
            raise ValueError("search roster differs from ordered legal actions")
        baseline = result.baseline
        if baseline is None:
            return
        expected = (
            request.state.position_key, request.root_perspective,
            self.evaluator.identity, request.evaluation_model.identity,
            self.evaluator.value_scale,
        )
        actual = (
            baseline.state_key, baseline.perspective, baseline.evaluator_identity,
            baseline.evaluation_model_identity, baseline.scale,
        )
        if actual != expected:
            raise ValueError(
                "search baseline does not prove Evaluation Request semantics: "
                f"expected {expected!r}, got {actual!r}")


__all__ = ("DecisionCoordinator", "neutral_lottery_choice")
