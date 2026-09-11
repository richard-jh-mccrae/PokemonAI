from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable, Protocol, cast

from common.observation import ObservationDelta, ObservationState

from .components import (
    CollaboratorKind, DecisionPolicy, DecisionPolicyRequest, DecisionRequirements,
    EvidenceIdentity, EvaluationModel,
    EvaluationRequest, FailSafeContext, FailSafePolicy, FailSafePolicyRequest,
    IdentifiedConfiguration,
    PolicyModel, SearchAlgorithm, SearchProvider, SearchWithPolicyModel,
    SearchWithPolicyModelAndProvider, SearchWithProvider, SearchWithoutCollaborators,
    ValueEvaluator,
)
from .configuration import DecisionDeadlineExceeded
from .identity import ActionChoiceIdentity
from .outcomes import (
    DecisionFailure, DecisionFailureStage, SearchOutcome, SearchOutcomeStatus,
    SearchTermination,
)
from .results import (
    BehaviorIdentity, DecisionEvidence, DecisionResult, FailSafeSelection, ForcedSelection,
    NO_FAIL_SAFE_POLICY_IDENTITY, NO_POLICY_MODEL_IDENTITY, NO_PRIZE_PLAN_IDENTITY,
    NO_PROVIDER_IDENTITY, NoSelection, PolicySelection, SearchResult,
)
from .values import StateValuation


LOTTERY_DIGEST_BYTES = 8


class ExecutionGuard(Protocol):
    def check(self) -> None: ...


SearchConfiguration = IdentifiedConfiguration | str
PolicyConfiguration = IdentifiedConfiguration | str
FailureHandler = Callable[[EvaluationRequest, DecisionFailure], SearchResult]


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
    behavior_identity: BehaviorIdentity
    policy_model: PolicyModel | None = None
    fail_safe_policy: FailSafePolicy | None = None
    failure_handler: FailureHandler | None = None
    ledger_baseline_identity: str | None = None
    compute_identity: str | None = None

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
                raise ValueError("core component requires a Component Contract")
            if contract.identity != component.identity:
                raise ValueError("component identity differs from its Component Contract")
            if configuration is not None:
                configuration_identities = {
                    type(configuration).__name__,
                    str(getattr(configuration, "identity", configuration)),
                }
                if contract.configuration_identity not in configuration_identities:
                    raise ValueError("component rejects its injected configuration")
        search_contract = self.search.contract
        if (search_contract.required_collaborators
                != frozenset(self.search.required_collaborators)
                or search_contract.optional_collaborators
                != frozenset(self.search.optional_collaborators)):
            raise ValueError("search collaborator declarations differ from its contract")
        policy_contract = self.decision_policy.contract
        declared_required = frozenset(self.decision_policy.required_statistics)
        if policy_contract.required_statistics != declared_required:
            raise ValueError("decision-policy statistic declarations differ from its contract")
        if not declared_required.issubset(search_contract.produced_statistics):
            raise ValueError("search cannot produce decision-policy required statistics")
        if not policy_contract.required_evidence.issubset(
                search_contract.produced_evidence):
            raise ValueError("search cannot produce decision-policy required evidence")
        if (self.policy_model is not None
                and not self.policy_model.contract.required_statistics.issubset(
                    search_contract.produced_statistics)):
            raise ValueError("search cannot produce policy-model required statistics")
        if self.fail_safe_policy is not None:
            fail_safe_contract = self.fail_safe_policy.contract
            if (not fail_safe_contract.accepted_outcomes
                    or any(status.permits_action
                           for status in fail_safe_contract.accepted_outcomes)):
                raise ValueError("fail-safe policy must declare non-permitting outcomes")
            if not fail_safe_contract.accepted_evidence:
                raise ValueError("fail-safe policy must declare accepted evidence")
        accepted_model = self.evaluator.accepted_model_identity
        if accepted_model not in ("*", self.evaluation_model.identity):
            raise ValueError("evaluator does not accept the Evaluation Model")
        required = self.search.required_collaborators
        optional = self.search.optional_collaborators
        if (CollaboratorKind.POLICY_MODEL in required
                and self.policy_model is None):
            raise ValueError("search requires a policy model")
        if (self.policy_model is not None
                and CollaboratorKind.POLICY_MODEL not in (*required, *optional)):
            raise ValueError("search does not accept a policy model")
        identity = self.behavior_identity
        if self.compute_identity is None:
            raise ValueError("Behavior Identity requires a verified compute identity")
        requires_provider = CollaboratorKind.PROVIDER in required
        accepts_provider = requires_provider or CollaboratorKind.PROVIDER in optional
        if ((requires_provider and identity.provider == NO_PROVIDER_IDENTITY)
                or (not accepts_provider
                    and identity.provider != NO_PROVIDER_IDENTITY)):
            raise ValueError("Behavior Identity does not match provider capability")
        actual = (
            self.evaluator.identity,
            self.evaluation_model.identity,
            self.search.identity,
            (NO_POLICY_MODEL_IDENTITY if self.policy_model is None
             else self.policy_model.identity),
            self.decision_policy.identity,
            (NO_FAIL_SAFE_POLICY_IDENTITY if self.fail_safe_policy is None
             else self.fail_safe_policy.identity),
            self.compute_identity,
            str(getattr(getattr(self.evaluation_model, "prize_plan", None), "identity",
                        NO_PRIZE_PLAN_IDENTITY)),
        )
        declared = (
            identity.evaluator,
            identity.evaluation_model,
            identity.search,
            identity.policy_model,
            identity.decision_policy,
            identity.fail_safe_policy,
            identity.compute,
            identity.prize_plan,
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
        collaborators = (
            *self.search.required_collaborators,
            *self.search.optional_collaborators,
        )
        if provider is not None and CollaboratorKind.PROVIDER not in collaborators:
            raise ValueError("search does not accept a provider")
        if ((provider is not None
             and provider.identity != self.behavior_identity.provider)
                or (provider is None and failure is None
                    and self.behavior_identity.provider != NO_PROVIDER_IDENTITY)):
            raise ValueError("Behavior Identity does not match injected provider")
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
        required = self.decision_policy.required_statistics
        missing = tuple(statistic for statistic in required
                        if not result.outcome.coverage.choices_for(statistic))
        if missing:
            raise ValueError(f"decision policy requirements are not covered: {missing!r}")
        policy_request = DecisionPolicyRequest(
            result.roster, result.candidates, result.outcome,
            result.statistics, result.evidence, self.policy_configuration,
            DecisionRequirements(required))
        supplied_evidence = (None if result.evidence is None else EvidenceIdentity(
            result.evidence.owner, result.evidence.schema_version))
        policy_contract = self.decision_policy.contract
        if (policy_contract.required_evidence
                and supplied_evidence not in policy_contract.required_evidence):
            raise ValueError("decision policy required evidence is not supplied")
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
        required = self.search.required_collaborators
        optional = self.search.optional_collaborators
        policy_model = self.policy_model
        provider_value = provider
        if CollaboratorKind.POLICY_MODEL in required and policy_model is None:
            raise ValueError("search requires a policy model")
        if CollaboratorKind.PROVIDER in required and provider_value is None:
            raise ValueError("search requires a provider")
        needs_policy = (CollaboratorKind.POLICY_MODEL in required
                        or (CollaboratorKind.POLICY_MODEL in optional
                            and policy_model is not None))
        needs_provider = (CollaboratorKind.PROVIDER in required
                          or (CollaboratorKind.PROVIDER in optional
                              and provider_value is not None))
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
        return cast(SearchWithoutCollaborators, self.search).search(
            request, self.evaluator, self.search_configuration)

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
        contract = self.fail_safe_policy.contract
        evidence_identity = (None if result.evidence is None else EvidenceIdentity(
            result.evidence.owner, result.evidence.schema_version))
        if (recovery_outcome.status not in contract.accepted_outcomes
                or evidence_identity not in contract.accepted_evidence):
            reason = ("unsupported_outcome"
                      if recovery_outcome.status not in contract.accepted_outcomes
                      else "incompatible_evidence")
            return DecisionResult(
                result,
                NoSelection(
                    recovery_outcome.status,
                    failure,
                    SearchTermination("coordinator", reason, 1),
                    result.outcome,
                ),
                self.behavior_identity,
            )
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
        if result.evidence is not None:
            evidence_identity = EvidenceIdentity(
                result.evidence.owner, result.evidence.schema_version)
            if evidence_identity not in self.search.contract.produced_evidence:
                raise ValueError("search returned undeclared evidence")
        baseline = result.baseline
        if baseline is None:
            forced_without_comparison = result.roster.forced and len(result.roster.actions) == 1
            if result.outcome.permits_action and not forced_without_comparison:
                raise ValueError("permitting search result requires a semantic baseline")
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
