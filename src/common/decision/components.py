from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Protocol, cast, runtime_checkable
from collections.abc import Mapping

from common.observation import ObservationDelta, ObservationState

from .identity import ActionChoiceIdentity
from .identity import WireValue
from .outcomes import DecisionFailure, SearchOutcome, SearchOutcomeStatus
from .results import CandidateResult, CandidateRoster, SearchEvidence, SearchResult
from .statistics import DecisionDeltaStatistic, DecisionStatistic, StatisticIdentity
from .values import EvaluationStatus, StateValuation, ValueScale


class EvaluationModel(Protocol):
    @property
    def identity(self) -> str: ...


class IdentifiedConfiguration(Protocol):
    @property
    def identity(self) -> str: ...


class ExecutionGuard(Protocol):
    def check(self) -> None: ...


class EvaluationReuse(Protocol):
    @property
    def identity(self) -> str: ...


class FailSafeContext(Protocol):
    @property
    def provider_payload(self) -> Mapping[str, WireValue]: ...


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    state: ObservationState
    evaluation_model: EvaluationModel
    parent_valuation: StateValuation | None = None
    observation_delta: ObservationDelta | None = None
    reuse: EvaluationReuse | None = None
    execution_guard: ExecutionGuard | None = None
    baseline_identity: str | None = None
    root_perspective: int | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, ObservationState):
            raise TypeError("evaluation request requires an Observation State")
        if not self.evaluation_model.identity:
            raise ValueError("evaluation request requires an Evaluation Model identity")
        if self.root_perspective is None:
            object.__setattr__(self, "root_perspective", self.state.seat)


class CollaboratorKind(str, Enum):
    POLICY_MODEL = "policy_model"
    PROVIDER = "provider"


class SearchProvider(Protocol):
    @property
    def identity(self) -> str: ...


@dataclass(frozen=True, order=True, slots=True)
class EvidenceIdentity:
    owner: str
    schema_version: int

    def __post_init__(self) -> None:
        if not self.owner or self.schema_version <= 0:
            raise ValueError("evidence identity requires owner and positive schema")


@dataclass(frozen=True, slots=True)
class ReuseProvenance:
    behavior_identity: str
    provider_identity: str
    evaluator_identity: str
    policy_model_identity: str
    evaluation_model_identity: str
    value_scale_identity: str
    root_decision_key: str
    configuration_identity: str
    horizon_identity: str

    def __post_init__(self) -> None:
        if not all((self.behavior_identity, self.provider_identity,
                    self.evaluator_identity, self.policy_model_identity,
                    self.evaluation_model_identity,
                    self.value_scale_identity, self.root_decision_key,
                    self.configuration_identity, self.horizon_identity)):
            raise ValueError("reuse provenance requires every semantic identity")


class ReuseVerdict(str, Enum):
    VERIFIED = "verified"
    FRESH_REQUIRED = "fresh_required"


class RetainedSearchState(Protocol):
    owner: str


class SearchLifecycle(Protocol):
    def close(self) -> None: ...


class SearchSnapshot(Protocol):
    def snapshot(self) -> RetainedSearchState: ...


class SearchReuse(Protocol):
    def reuse(
            self,
            state: RetainedSearchState,
            provenance: ReuseProvenance,
    ) -> ReuseVerdict: ...


@dataclass(frozen=True, slots=True)
class ComponentContract:
    identity: str
    configuration_identity: str
    required_statistics: frozenset[StatisticIdentity] = frozenset()
    produced_statistics: frozenset[StatisticIdentity] = frozenset()
    required_collaborators: frozenset[CollaboratorKind] = frozenset()
    optional_collaborators: frozenset[CollaboratorKind] = frozenset()
    required_evidence: frozenset[EvidenceIdentity] = frozenset()
    produced_evidence: frozenset[EvidenceIdentity] = frozenset()
    accepted_outcomes: frozenset[SearchOutcomeStatus] = frozenset()
    accepted_evidence: frozenset[EvidenceIdentity | None] = frozenset()

    def __post_init__(self) -> None:
        if not self.identity or not self.configuration_identity:
            raise ValueError("component contract requires stable identities")
        if self.required_collaborators & self.optional_collaborators:
            raise ValueError("component collaborator cannot be required and optional")


@dataclass(frozen=True, slots=True)
class DecisionRequirements:
    statistics: tuple[StatisticIdentity, ...] = ()

    def __post_init__(self) -> None:
        if len(set(self.statistics)) != len(self.statistics):
            raise ValueError("decision requirements contain duplicate statistics")


def _validate_candidate_view(
        roster: CandidateRoster,
        candidates: tuple[CandidateResult, ...],
        statistics: tuple[DecisionStatistic, ...],
) -> dict[StatisticIdentity, frozenset[ActionChoiceIdentity]]:
    if tuple(candidate.choice for candidate in candidates) != roster.identities:
        raise ValueError("candidates do not match Candidate Roster")
    choices = set(roster.identities)
    keyed: set[tuple[StatisticIdentity, ActionChoiceIdentity]] = set()
    supplied: dict[StatisticIdentity, set[ActionChoiceIdentity]] = {}
    for statistic in statistics:
        if statistic.choice not in choices:
            raise ValueError("decision statistic choice is outside Candidate Roster")
        key = (statistic.identity, statistic.choice)
        if key in keyed:
            raise ValueError("duplicate decision statistic for choice")
        keyed.add(key)
        supplied.setdefault(statistic.identity, set()).add(statistic.choice)
    return {identity: frozenset(values) for identity, values in supplied.items()}


@dataclass(frozen=True, slots=True)
class PolicyModelRequest:
    observation: ObservationState
    roster: CandidateRoster
    candidates: tuple[CandidateResult, ...]
    statistics: tuple[DecisionStatistic, ...]
    source: PolicySourceIdentity
    requirements: DecisionRequirements = DecisionRequirements()

    def __post_init__(self) -> None:
        if not isinstance(self.observation, ObservationState):
            raise TypeError("policy model request requires an Observation State")
        if self.roster.decision_key != self.observation.decision_key:
            raise ValueError("policy model roster is not proven for Observation State")
        legal = tuple(ActionChoiceIdentity.from_action(action)
                      for action in self.observation.legal_actions)
        if self.roster.identities != legal:
            raise ValueError("policy model roster differs from Observation State legal actions")
        supplied = _validate_candidate_view(
            self.roster, self.candidates, self.statistics)
        for statistic in self.statistics:
            if isinstance(statistic, DecisionDeltaStatistic) and statistic.value is not None:
                if (statistic.value.scale.identity != self.source.value_scale_identity
                        or statistic.value.perspective != self.observation.seat):
                    raise ValueError(
                        "policy model candidate Value Scale or perspective differs from "
                        "source Value Scale or observation perspective")
        for required in self.requirements.statistics:
            if supplied.get(required, frozenset()) != frozenset(self.roster.identities):
                raise ValueError("policy model required statistic is not supplied for roster")


@dataclass(frozen=True, slots=True)
class PolicySourceIdentity:
    baseline_identity: str | None
    evaluator_identity: str
    evaluation_model_identity: str
    value_scale_identity: str

    def __post_init__(self) -> None:
        if not all((self.evaluator_identity, self.evaluation_model_identity,
                    self.value_scale_identity)):
            raise ValueError("policy source identities are required")

    def as_dict(self) -> dict[str, str | None]:
        return {
            "baseline_identity": self.baseline_identity,
            "evaluator_identity": self.evaluator_identity,
            "evaluation_model_identity": self.evaluation_model_identity,
            "value_scale_identity": self.value_scale_identity,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, WireValue]) -> PolicySourceIdentity:
        expected = {"baseline_identity", "evaluator_identity",
                    "evaluation_model_identity", "value_scale_identity"}
        if set(value) != expected:
            raise ValueError("invalid policy source identity fields")
        baseline = value["baseline_identity"]
        fields = tuple(value[name] for name in (
            "evaluator_identity", "evaluation_model_identity", "value_scale_identity"))
        if ((baseline is not None and not isinstance(baseline, str))
                or any(not isinstance(item, str) for item in fields)):
            raise ValueError("invalid policy source identity")
        return cls(
            baseline,
            cast(str, fields[0]),
            cast(str, fields[1]),
            cast(str, fields[2]),
        )


class PolicyFallbackReason(str, Enum):
    REQUESTED_UNIFORM = "requested_uniform"
    UNAVAILABLE_CANDIDATE = "unavailable_candidate"
    UNACCEPTED_STATUS = "unaccepted_status"


@dataclass(frozen=True, slots=True)
class PolicyActionEvidence:
    choice: ActionChoiceIdentity
    raw_delta: float | None
    normalized_score: float
    final_prior: float
    source_status: EvaluationStatus
    fallback_reason: PolicyFallbackReason | None = None

    def __post_init__(self) -> None:
        if self.raw_delta is not None and not math.isfinite(self.raw_delta):
            raise ValueError("policy raw delta must be finite")
        if (not math.isfinite(self.normalized_score)
                or self.normalized_score < 0.0):
            raise ValueError("policy score must be finite and nonnegative")
        if not math.isfinite(self.final_prior) or self.final_prior <= 0.0:
            raise ValueError("policy prior must be finite and positive")

    @property
    def action_identity(self) -> ActionChoiceIdentity:
        return self.choice

    def as_dict(self) -> dict[str, WireValue]:
        return {
            "action": self.choice.as_dict(),
            "raw_delta": self.raw_delta,
            "normalized_score": self.normalized_score,
            "final_prior": self.final_prior,
            "source_status": self.source_status.value,
            "fallback_reason": (None if self.fallback_reason is None
                                else self.fallback_reason.value),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, WireValue]) -> PolicyActionEvidence:
        expected = {"action", "raw_delta", "normalized_score", "final_prior",
                    "source_status", "fallback_reason"}
        if set(value) != expected:
            raise ValueError("invalid policy action evidence fields")
        action = value["action"]
        if not isinstance(action, dict):
            raise ValueError("invalid policy action evidence")
        raw = value["raw_delta"]
        fallback = value["fallback_reason"]
        return cls(
            ActionChoiceIdentity.from_dict(action),
            None if raw is None else float(cast(float | int, raw)),
            float(cast(float | int, value["normalized_score"])),
            float(cast(float | int, value["final_prior"])),
            EvaluationStatus(cast(str, value["source_status"])),
            None if fallback is None else PolicyFallbackReason(cast(str, fallback)),
        )


@dataclass(frozen=True, slots=True)
class PolicyDistribution:
    model_identity: str
    configuration_identity: str
    source: PolicySourceIdentity
    actions: tuple[PolicyActionEvidence, ...]
    temperature: float | None
    uniform_mix: float
    actual_floor: float
    fallback_reason: PolicyFallbackReason | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.model_identity or not self.configuration_identity or self.schema_version <= 0:
            raise ValueError("policy distribution identities are required")
        identities = tuple(item.choice for item in self.actions)
        if len(set(identities)) != len(identities):
            raise ValueError("policy distribution contains duplicate choices")
        scores = tuple(item.normalized_score for item in self.actions)
        priors = tuple(item.final_prior for item in self.actions)
        if not math.isclose(math.fsum(scores), 1.0, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("policy scores must form a normalized distribution")
        if not math.isclose(math.fsum(priors), 1.0, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("policy priors must form a normalized distribution")
        if not math.isclose(self.actual_floor, min(priors), rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("policy floor must equal the smallest prior")
        if (self.temperature is not None
                and (not math.isfinite(self.temperature) or self.temperature <= 0.0)):
            raise ValueError("policy temperature must be positive and finite")
        if not math.isfinite(self.uniform_mix) or not 0.0 <= self.uniform_mix <= 1.0:
            raise ValueError("policy uniform mix must be between zero and one")

    def priors_for(self, roster: CandidateRoster) -> tuple[float, ...]:
        by_choice = {item.choice: item.final_prior for item in self.actions}
        if set(by_choice) != set(roster.identities):
            raise ValueError("policy distribution does not match Candidate Roster")
        return tuple(by_choice[choice] for choice in roster.identities)

    def as_dict(self) -> dict[str, WireValue]:
        return {
            "schema_version": self.schema_version,
            "model_identity": self.model_identity,
            "configuration_identity": self.configuration_identity,
            "source": cast(WireValue, self.source.as_dict()),
            "temperature": self.temperature,
            "uniform_mix": self.uniform_mix,
            "actual_floor": self.actual_floor,
            "fallback_reason": (None if self.fallback_reason is None
                                else self.fallback_reason.value),
            "actions": [item.as_dict() for item in self.actions],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, WireValue]) -> PolicyDistribution:
        expected = {"schema_version", "model_identity", "configuration_identity",
                    "source", "temperature", "uniform_mix", "actual_floor",
                    "fallback_reason", "actions"}
        if set(value) != expected:
            raise ValueError("invalid policy distribution fields")
        source = value["source"]
        actions = value["actions"]
        fallback = value["fallback_reason"]
        temperature = value["temperature"]
        if not isinstance(source, dict) or not isinstance(actions, list):
            raise ValueError("invalid policy distribution")
        return cls(
            cast(str, value["model_identity"]),
            cast(str, value["configuration_identity"]),
            PolicySourceIdentity.from_dict(source),
            tuple(PolicyActionEvidence.from_dict(cast(dict[str, WireValue], item))
                  for item in actions),
            None if temperature is None else float(cast(float | int, temperature)),
            float(cast(float | int, value["uniform_mix"])),
            float(cast(float | int, value["actual_floor"])),
            None if fallback is None else PolicyFallbackReason(cast(str, fallback)),
            int(cast(int, value["schema_version"])),
        )


def validate_policy_distribution(
        request: PolicyModelRequest,
        model: PolicyModel,
        distribution: PolicyDistribution,
) -> None:
    if not isinstance(distribution, PolicyDistribution):
        raise TypeError("policy model must return a Policy Distribution")
    expected = (
        model.identity,
        model.contract.configuration_identity,
        request.source,
        set(request.roster.identities),
    )
    actual = (
        distribution.model_identity,
        distribution.configuration_identity,
        distribution.source,
        {item.choice for item in distribution.actions},
    )
    if actual != expected:
        raise ValueError("policy distribution does not prove Policy Model Request semantics")


@dataclass(frozen=True, slots=True)
class DecisionPolicyRequest:
    roster: CandidateRoster
    candidates: tuple[CandidateResult, ...]
    outcome: SearchOutcome
    statistics: tuple[DecisionStatistic, ...]
    evidence: SearchEvidence | None
    configuration: IdentifiedConfiguration | str
    requirements: DecisionRequirements = DecisionRequirements()

    def __post_init__(self) -> None:
        if not self.outcome.permits_action:
            raise ValueError("normal decision policy requires a permitting Search Outcome")
        supplied = _validate_candidate_view(
            self.roster, self.candidates, self.statistics)
        for required in self.requirements.statistics:
            covered = self.outcome.coverage.choices_for(required)
            if not covered or not covered.issubset(supplied.get(required, frozenset())):
                raise ValueError("decision policy required statistic is not covered")


@dataclass(frozen=True, slots=True)
class FailSafePolicyRequest:
    observation: ObservationState
    roster: CandidateRoster
    candidates: tuple[CandidateResult, ...]
    outcome: SearchOutcome
    original_search_outcome: SearchOutcome
    evidence: SearchEvidence | None
    failure: DecisionFailure
    configuration: IdentifiedConfiguration | str
    context: FailSafeContext | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.observation, ObservationState):
            raise TypeError("fail-safe request requires an Observation State")
        if self.outcome.permits_action:
            raise ValueError("fail-safe policy requires a non-permitting outcome")
        if self.roster.decision_key != self.observation.decision_key:
            raise ValueError("fail-safe roster is not proven for Observation State")
        legal = tuple(ActionChoiceIdentity.from_action(action)
                      for action in self.observation.legal_actions)
        if self.roster.identities != legal:
            raise ValueError("fail-safe roster differs from Observation State legal actions")
        _validate_candidate_view(self.roster, self.candidates, ())
        if (self.outcome.status is SearchOutcomeStatus.HARD_FAILURE
                and self.outcome.failure != self.failure):
            raise ValueError("fail-safe outcome differs from Decision Failure")


@runtime_checkable
class ValueEvaluator(Protocol):
    @property
    def identity(self) -> str: ...

    @property
    def value_scale(self) -> ValueScale: ...

    @property
    def accepted_model_identity(self) -> str: ...

    @property
    def contract(self) -> ComponentContract: ...

    def evaluate(self, request: EvaluationRequest) -> StateValuation: ...


def validate_state_valuation(
        request: EvaluationRequest,
        state: ObservationState,
        evaluator: ValueEvaluator,
        valuation: StateValuation,
) -> None:
    expected = (
        state.position_key,
        request.root_perspective,
        evaluator.identity,
        request.evaluation_model.identity,
        evaluator.value_scale,
    )
    actual = (
        valuation.state_key,
        valuation.perspective,
        valuation.evaluator_identity,
        valuation.evaluation_model_identity,
        valuation.scale,
    )
    if actual != expected:
        raise ValueError("State Valuation does not prove Evaluation Request semantics")


class PolicyModel(Protocol):
    @property
    def identity(self) -> str: ...

    @property
    def contract(self) -> ComponentContract: ...

    def priors(self, request: PolicyModelRequest) -> PolicyDistribution: ...


class SearchAlgorithm(Protocol):
    @property
    def identity(self) -> str: ...

    @property
    def required_collaborators(self) -> tuple[CollaboratorKind, ...]: ...

    @property
    def optional_collaborators(self) -> tuple[CollaboratorKind, ...]: ...

    @property
    def contract(self) -> ComponentContract: ...


class SearchWithoutCollaborators(SearchAlgorithm, Protocol):
    def search(
            self,
            request: EvaluationRequest,
            evaluator: ValueEvaluator,
            configuration: IdentifiedConfiguration | str,
    ) -> SearchResult: ...


class SearchWithPolicyModel(SearchAlgorithm, Protocol):
    def search(
            self,
            request: EvaluationRequest,
            evaluator: ValueEvaluator,
            configuration: IdentifiedConfiguration | str,
            *,
            policy_model: PolicyModel,
    ) -> SearchResult: ...


class SearchWithProvider(SearchAlgorithm, Protocol):
    def search(
            self,
            request: EvaluationRequest,
            evaluator: ValueEvaluator,
            configuration: IdentifiedConfiguration | str,
            *,
            provider: SearchProvider,
    ) -> SearchResult: ...


class SearchWithPolicyModelAndProvider(SearchAlgorithm, Protocol):
    def search(
            self,
            request: EvaluationRequest,
            evaluator: ValueEvaluator,
            configuration: IdentifiedConfiguration | str,
            *,
            policy_model: PolicyModel,
            provider: SearchProvider,
    ) -> SearchResult: ...


class DecisionPolicy(Protocol):
    @property
    def identity(self) -> str: ...

    @property
    def required_statistics(self) -> tuple[StatisticIdentity, ...]: ...

    @property
    def contract(self) -> ComponentContract: ...

    def choose(self, request: DecisionPolicyRequest) -> ActionChoiceIdentity: ...


class FailSafePolicy(Protocol):
    @property
    def identity(self) -> str: ...

    @property
    def contract(self) -> ComponentContract: ...

    def choose(self, request: FailSafePolicyRequest) -> ActionChoiceIdentity: ...


__all__ = (
    "CollaboratorKind", "ComponentContract", "DecisionPolicy", "DecisionPolicyRequest",
    "DecisionRequirements", "EvaluationModel", "EvaluationRequest", "FailSafePolicy",
    "EvidenceIdentity", "FailSafeContext", "FailSafePolicyRequest", "IdentifiedConfiguration",
    "PolicyActionEvidence",
    "PolicyDistribution", "PolicyFallbackReason", "PolicyModel", "PolicyModelRequest",
    "PolicySourceIdentity",
    "RetainedSearchState", "ReuseProvenance", "ReuseVerdict", "SearchAlgorithm",
    "SearchLifecycle", "SearchProvider", "SearchReuse", "SearchSnapshot",
    "SearchWithPolicyModel", "SearchWithPolicyModelAndProvider", "SearchWithProvider",
    "SearchWithoutCollaborators", "ValueEvaluator",
    "validate_policy_distribution", "validate_state_valuation",
)
