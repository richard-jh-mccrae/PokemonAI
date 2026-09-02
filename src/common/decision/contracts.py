from __future__ import annotations

import math
import traceback
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol

from common.api import ActionIdentity
from common.observation import ObservationState, TransitionTrace


class EvaluationStatus(str, Enum):
    COMPLETE = "complete"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class CandidateDisposition(str, Enum):
    CONTINUES_TURN = "continues_turn"
    ENDS_TURN = "ends_turn"
    FORCED = "forced"


class ContinuationOpportunity(str, Enum):
    DEPENDENCY_REACH = "dependency_reach"
    LETHAL_ATTACK = "lethal_attack"
    WINNING_ATTACK = "winning_attack"


class OpportunityRef(str):
    def __new__(cls, kind, source=None):
        value = str(getattr(kind, "value", kind))
        instance = super().__new__(cls, value)
        instance.source = None if source is None else str(source)
        return instance

    def __eq__(self, other):
        if isinstance(other, OpportunityRef):
            return str(self) == str(other) and self.source == other.source
        return str(self) == str(getattr(other, "value", other))

    __hash__ = str.__hash__

    @classmethod
    def decode(cls, value):
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            return cls(value)
        if isinstance(value, dict) and set(value) == {"kind", "source"}:
            return cls(value["kind"], value["source"])
        raise TypeError(f"invalid opportunity reference {value!r}")

    def wire(self):
        return {"kind": str(self), "source": self.source}


class RealizedOutcome(str, Enum):
    ACTION_ENDED_TURN = "action_ended_turn"
    EXPLICIT_TURN_END = "explicit_turn_end"
    GAME_WIN = "game_win"
    OPPONENT_ACTIVE_KNOCKOUT = "opponent_active_knockout"
    OPPONENT_BODY_KNOCKOUT = "opponent_body_knockout"


class DecisionFailureStage(str, Enum):
    EVALUATION = "evaluation"
    PROVIDER = "provider"
    SEARCH = "search"
    POLICY = "policy"
    PRESENTATION = "presentation"
    RUNTIME = "runtime"


class DecisionReason(str, Enum):
    POLICY = "policy"
    FORCED = "forced"
    BEST_DELTA = "best_delta"
    POSITIVE_CONTINUATION = "positive_continuation"
    BEST_TURN_ENDER = "best_turn_ender"
    FAIL_SAFE_EVALUATION_FAILURE = "fail_safe_evaluation_failure"
    FAIL_SAFE_PROVIDER_FAILURE = "fail_safe_provider_failure"
    FAIL_SAFE_SEARCH_FAILURE = "fail_safe_search_failure"
    FAIL_SAFE_POLICY_FAILURE = "fail_safe_policy_failure"
    FAIL_SAFE_PRESENTATION_FAILURE = "fail_safe_presentation_failure"
    FAIL_SAFE_RUNTIME_FAILURE = "fail_safe_runtime_failure"
    EMPTY_ROSTER = "empty_roster"


class PolicyFallbackReason(str, Enum):
    REQUESTED_UNIFORM = "requested_uniform"
    UNAVAILABLE_CANDIDATE = "unavailable_candidate"
    UNACCEPTED_STATUS = "unaccepted_status"


@dataclass(frozen=True, slots=True)
class DecisionFailure:
    stage: DecisionFailureStage
    error_type: str
    message: str
    traceback_tail: str = ""

    @classmethod
    def capture(cls, stage: DecisionFailureStage, exc: Exception) -> "DecisionFailure":
        return cls(stage, type(exc).__name__, str(exc)[:500], traceback.format_exc()[-2000:])


@dataclass(frozen=True, slots=True)
class FailSafeRequest:
    observation: dict
    legal_actions: tuple
    seat: int
    state_key: str
    decision_key: str
    context: int | None


@dataclass(frozen=True, slots=True)
class ValueScale:
    name: str
    schema_version: int
    lower_bound: float | None = None
    upper_bound: float | None = None

    def __post_init__(self):
        if not self.name:
            raise ValueError("value scale name is required")
        if self.schema_version <= 0:
            raise ValueError("value scale schema version must be positive")
        if (self.lower_bound is not None and self.upper_bound is not None
                and self.lower_bound >= self.upper_bound):
            raise ValueError("value scale bounds must increase")

    @property
    def identity(self) -> str:
        return f"{self.name}:v{self.schema_version}"


@dataclass(frozen=True, slots=True)
class ValueComponent:
    key: str
    activation: float
    coefficient: float
    value: float
    provenance: tuple[str, ...] = ()

    def __post_init__(self):
        if not all(math.isfinite(value) for value in (
                self.activation, self.coefficient, self.value)):
            raise ValueError("value component must be finite")


@dataclass(frozen=True, slots=True)
class StateValuation:
    state_key: str
    total: float
    scale: ValueScale
    perspective: int | str
    evaluator_identity: str
    components: tuple[ValueComponent, ...] = ()
    status: EvaluationStatus = EvaluationStatus.COMPLETE
    gaps: tuple[str, ...] = ()
    evidence: object | None = None
    cache_key: str | None = None
    baseline_identity: str | None = None
    evaluation_model_identity: str | None = None

    def __post_init__(self):
        if not math.isfinite(self.total):
            raise ValueError("state valuation must be finite")
        if self.scale.lower_bound is not None and self.total < self.scale.lower_bound:
            raise ValueError("state valuation is below its scale")
        if self.scale.upper_bound is not None and self.total > self.scale.upper_bound:
            raise ValueError("state valuation is above its scale")


@dataclass(frozen=True, slots=True)
class DecisionDelta:
    total: float
    scale: ValueScale
    components: tuple[ValueComponent, ...] = ()

    def __post_init__(self):
        if not math.isfinite(self.total):
            raise ValueError("decision delta must be finite")


@dataclass(frozen=True, slots=True)
class SearchValue:
    total: float
    scale: ValueScale

    def __post_init__(self):
        if not math.isfinite(self.total):
            raise ValueError("search value must be finite")


@dataclass(frozen=True, slots=True)
class SuccessorResult:
    probability: float
    valuation: StateValuation
    ended: bool
    state: ObservationState
    trace: TransitionTrace
    action_path: tuple[object, ...] = ()
    status: EvaluationStatus = EvaluationStatus.COMPLETE
    failure: str | None = None

    def __post_init__(self):
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("successor probability must be between zero and one")
        if self.status is not self.valuation.status:
            raise ValueError("successor and valuation statuses must match")


@dataclass(frozen=True, slots=True)
class ContinuationResult:
    state_delta: float
    action_opportunity: float
    continues_turn: bool
    zones_created: tuple[str, ...] = ()
    zones_replaced: tuple[str, ...] = ()
    allowances_consumed: tuple[str, ...] = ()
    immediately_usable_outputs: tuple[str, ...] = ()
    opportunities_created: tuple[OpportunityRef, ...] = ()
    opportunities_preserved: tuple[OpportunityRef, ...] = ()
    opportunities_consumed: tuple[OpportunityRef, ...] = ()
    policy_components: tuple[ValueComponent, ...] = ()
    realized_outcomes: tuple[RealizedOutcome, ...] = ()
    executed_opportunity: OpportunityRef | None = None

    def __post_init__(self):
        for field in (
                "opportunities_created", "opportunities_preserved",
                "opportunities_consumed"):
            object.__setattr__(self, field, tuple(
                OpportunityRef.decode(value) for value in getattr(self, field)))
        if self.executed_opportunity is not None:
            object.__setattr__(
                self, "executed_opportunity",
                OpportunityRef.decode(self.executed_opportunity))


@dataclass(frozen=True, slots=True)
class ValuedCandidate:
    action: object
    delta: DecisionDelta | None
    disposition: CandidateDisposition
    status: EvaluationStatus
    successors: tuple[SuccessorResult, ...] = ()
    gaps: tuple[str, ...] = ()
    continuation: ContinuationResult | None = None
    search_value: SearchValue | None = None
    prior: float | None = None
    policy_tie_break: tuple[object, ...] = ()
    policy_evidence: object | None = None

    def __post_init__(self):
        if self.status is EvaluationStatus.UNAVAILABLE and self.delta is not None:
            raise ValueError("unavailable candidate cannot carry a decision delta")
        if self.status is not EvaluationStatus.UNAVAILABLE and self.delta is None:
            raise ValueError("priced candidate requires a decision delta")
        if self.prior is not None and not 0.0 <= self.prior <= 1.0:
            raise ValueError("candidate prior must be between zero and one")


@dataclass(frozen=True, slots=True)
class CandidateRoster:
    candidates: tuple[ValuedCandidate, ...]
    forced: bool = False
    legal_action_identities: tuple[object, ...] = ()
    legal_actions_proven: bool = False

    def __post_init__(self):
        identities = tuple(_roster_action_id(candidate.action)
                           for candidate in self.candidates)
        if _has_duplicates(identities):
            raise ValueError("duplicate candidate action")
        legal = tuple(self.legal_action_identities)
        if _has_duplicates(legal):
            raise ValueError("duplicate legal action")
        if self.legal_actions_proven and identities != legal:
            raise ValueError("candidate roster does not match ordered legal actions")
        object.__setattr__(self, "legal_action_identities", legal)

    @classmethod
    def from_legal_actions(cls, legal_actions, candidates, *, forced=False):
        legal = tuple(_roster_action_id(action) for action in legal_actions)
        candidates = tuple(candidates)
        actual = tuple(_roster_action_id(candidate.action) for candidate in candidates)
        if len(actual) < len(legal):
            raise ValueError("candidate roster has a missing legal action")
        if len(actual) > len(legal):
            raise ValueError("candidate roster has an extra candidate action")
        if actual != legal:
            raise ValueError("candidate roster order differs from legal actions")
        return cls(candidates, forced, legal, True)

    @property
    def policy_action_identities(self) -> tuple["PolicyActionIdentity", ...]:
        return tuple(PolicyActionIdentity.from_action(candidate.action)
                     for candidate in self.candidates)

    def with_priors(self, priors) -> "CandidateRoster":
        priors = tuple(priors)
        if len(priors) != len(self.candidates):
            raise ValueError("candidate prior count does not match roster")
        return replace(self, candidates=tuple(
            replace(candidate, prior=prior)
            for candidate, prior in zip(self.candidates, priors)))


def _roster_action_id(action):
    selection = getattr(action, "selection", None)
    identity = getattr(action, "identity", action)
    return ((identity, tuple(selection)) if selection is not None else identity)


def _has_duplicates(values) -> bool:
    try:
        return len(set(values)) != len(values)
    except TypeError:
        return any(value in values[:index] for index, value in enumerate(values))


@dataclass(frozen=True, slots=True)
class PolicyActionIdentity:
    identity: object
    selection: tuple[object, ...] = ()

    @classmethod
    def from_action(cls, action) -> "PolicyActionIdentity":
        return cls(getattr(action, "identity", action),
                   tuple(getattr(action, "selection", ())))

    def as_dict(self) -> dict:
        identity = self.identity
        wire = ({"kind": str(identity.kind), "parts": _wire_value(identity.parts)}
                if hasattr(identity, "kind") and hasattr(identity, "parts")
                else _wire_value(identity))
        return {"identity": wire, "selection": list(self.selection)}

    @classmethod
    def from_dict(cls, value: dict) -> "PolicyActionIdentity":
        _exact_policy_fields(value, {"identity", "selection"}, "policy action identity")
        identity = value["identity"]
        if isinstance(identity, dict) and set(identity) == {"kind", "parts"}:
            identity = ActionIdentity(str(identity["kind"]), _unwire_value(identity["parts"]))
        return cls(identity, tuple(_unwire_value(value["selection"])))


def _wire_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_wire_value(item) for item in value]
    if isinstance(value, list):
        return [_wire_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _wire_value(item) for key, item in value.items()}
    return value


def _unwire_value(value):
    if isinstance(value, list):
        return tuple(_unwire_value(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _unwire_value(item) for key, item in value.items()}
    return value


def _exact_policy_fields(value, expected, label):
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"invalid {label} fields")


@dataclass(frozen=True, slots=True)
class PolicySourceIdentity:
    baseline_identity: str | None
    evaluator_identity: str
    evaluation_model_identity: str
    value_scale_identity: str

    def __post_init__(self):
        for name in ("evaluator_identity", "evaluation_model_identity",
                     "value_scale_identity"):
            if not getattr(self, name):
                raise ValueError(f"policy source {name} is required")

    def as_dict(self) -> dict:
        return {
            "baseline_identity": self.baseline_identity,
            "evaluator_identity": self.evaluator_identity,
            "evaluation_model_identity": self.evaluation_model_identity,
            "value_scale_identity": self.value_scale_identity,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "PolicySourceIdentity":
        expected = {"baseline_identity", "evaluator_identity",
                    "evaluation_model_identity", "value_scale_identity"}
        _exact_policy_fields(value, expected, "policy source identity")
        return cls(
            value["baseline_identity"],
            str(value["evaluator_identity"]),
            str(value["evaluation_model_identity"]),
            str(value["value_scale_identity"]),
        )


@dataclass(frozen=True, slots=True)
class PolicyRequest:
    observation: ObservationState
    roster: CandidateRoster
    source: PolicySourceIdentity

    def __post_init__(self):
        if not isinstance(self.observation, ObservationState):
            raise TypeError("policy request requires an Observation State")
        if not self.roster.candidates:
            raise ValueError("policy request requires a candidate")
        if not self.roster.legal_actions_proven:
            raise ValueError("policy request requires a proven legal Candidate Roster")


@dataclass(frozen=True, slots=True)
class PolicyActionEvidence:
    action_identity: PolicyActionIdentity
    raw_delta: float | None
    normalized_score: float
    final_prior: float
    source_status: EvaluationStatus
    fallback_reason: PolicyFallbackReason | None = None

    def __post_init__(self):
        if self.raw_delta is not None and not math.isfinite(self.raw_delta):
            raise ValueError("policy raw delta must be finite")
        if not math.isfinite(self.normalized_score) or self.normalized_score < 0.0:
            raise ValueError("policy normalized score must be finite and nonnegative")
        if not math.isfinite(self.final_prior) or self.final_prior <= 0.0:
            raise ValueError("policy prior must be finite and positive")

    def as_dict(self) -> dict:
        return {
            "action": self.action_identity.as_dict(),
            "raw_delta": self.raw_delta,
            "normalized_score": self.normalized_score,
            "final_prior": self.final_prior,
            "source_status": self.source_status.value,
            "fallback_reason": (None if self.fallback_reason is None
                                else self.fallback_reason.value),
        }

    @classmethod
    def from_dict(cls, value: dict) -> "PolicyActionEvidence":
        expected = {"action", "raw_delta", "normalized_score", "final_prior",
                    "source_status", "fallback_reason"}
        _exact_policy_fields(value, expected, "policy action evidence")
        reason = value["fallback_reason"]
        return cls(
            PolicyActionIdentity.from_dict(value["action"]),
            None if value["raw_delta"] is None else float(value["raw_delta"]),
            float(value["normalized_score"]),
            float(value["final_prior"]),
            EvaluationStatus(value["source_status"]),
            None if reason is None else PolicyFallbackReason(reason),
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

    def __post_init__(self):
        if self.schema_version != 1:
            raise ValueError("unsupported policy distribution schema version")
        if not self.model_identity or not self.configuration_identity or not self.actions:
            raise ValueError("policy distribution identity and actions are required")
        identities = tuple(item.action_identity for item in self.actions)
        if _has_duplicates(identities):
            raise ValueError("policy distribution contains duplicate actions")
        priors = tuple(item.final_prior for item in self.actions)
        normalized = tuple(item.normalized_score for item in self.actions)
        if not math.isclose(math.fsum(priors), 1.0, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("policy priors must form a normalized distribution")
        if not math.isclose(math.fsum(normalized), 1.0, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("policy scores must form a normalized distribution")
        if not math.isclose(self.actual_floor, min(priors), rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("policy floor must equal the smallest prior")
        if (self.temperature is not None
                and (not math.isfinite(self.temperature) or self.temperature <= 0.0)):
            raise ValueError("policy temperature must be positive and finite")
        if not math.isfinite(self.uniform_mix) or not 0.0 <= self.uniform_mix <= 1.0:
            raise ValueError("policy uniform mix must be between zero and one")

    @property
    def action_identities(self) -> tuple[PolicyActionIdentity, ...]:
        return tuple(item.action_identity for item in self.actions)

    def priors_for(self, roster: CandidateRoster) -> tuple[float, ...]:
        if self.action_identities != roster.policy_action_identities:
            raise ValueError("policy distribution does not match Candidate Roster")
        return tuple(item.final_prior for item in self.actions)

    def as_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "model_identity": self.model_identity,
            "configuration_identity": self.configuration_identity,
            "source": self.source.as_dict(),
            "temperature": self.temperature,
            "uniform_mix": self.uniform_mix,
            "actual_floor": self.actual_floor,
            "fallback_reason": (None if self.fallback_reason is None
                                else self.fallback_reason.value),
            "actions": [item.as_dict() for item in self.actions],
        }

    @classmethod
    def from_dict(cls, value: dict) -> "PolicyDistribution":
        expected = {"schema_version", "model_identity", "configuration_identity",
                    "source", "temperature", "uniform_mix", "actual_floor",
                    "fallback_reason", "actions"}
        _exact_policy_fields(value, expected, "policy distribution")
        reason = value["fallback_reason"]
        temperature = value["temperature"]
        return cls(
            str(value["model_identity"]),
            str(value["configuration_identity"]),
            PolicySourceIdentity.from_dict(value["source"]),
            tuple(PolicyActionEvidence.from_dict(item) for item in value["actions"]),
            None if temperature is None else float(temperature),
            float(value["uniform_mix"]),
            float(value["actual_floor"]),
            None if reason is None else PolicyFallbackReason(reason),
            int(value["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    state: object
    evaluation_model: object
    parent_valuation: StateValuation | None = None
    observation_delta: object | None = None
    reuse: object | None = None
    execution_guard: object | None = None
    baseline_identity: str | None = None


@dataclass(frozen=True, slots=True)
class SearchResult:
    baseline: StateValuation
    roster: CandidateRoster
    nodes_visited: int = 0
    stop_reason: str = "complete"
    frontier: tuple[object, ...] = ()
    failure: DecisionFailure | None = None


@dataclass(frozen=True, slots=True)
class SearchTrace:
    nodes_visited: int
    stop_reason: str
    frontier: tuple[object, ...]
    chosen_action: object | None = None
    action_paths: tuple[tuple[object, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionResult:
    chosen: object
    baseline: StateValuation
    roster: CandidateRoster
    search: SearchResult
    trace: SearchTrace | None = None
    policy_reason: DecisionReason = DecisionReason.POLICY
    behavior_identity: object | None = None

    def __post_init__(self):
        if self.search.roster != self.roster:
            raise ValueError("decision and search candidate rosters differ")
        if self.chosen is None:
            if self.roster.candidates:
                raise ValueError("non-empty candidate roster requires a chosen action")
            return
        chosen_identity = getattr(self.chosen, "identity", self.chosen)
        matches = tuple(candidate for candidate in self.roster.candidates
                        if getattr(candidate.action, "identity", candidate.action)
                        == chosen_identity)
        if len(matches) != 1:
            raise ValueError("chosen action is not in candidate roster")

    @property
    def chosen_candidate(self) -> ValuedCandidate | None:
        if self.chosen is None:
            return None
        chosen_identity = getattr(self.chosen, "identity", self.chosen)
        return next(candidate for candidate in self.roster.candidates
                    if getattr(candidate.action, "identity", candidate.action)
                    == chosen_identity)


@dataclass(frozen=True, slots=True)
class DecisionChoice:
    action: object
    reason: DecisionReason


class ValueEvaluator(Protocol):
    identity: str

    def evaluate(self, request: EvaluationRequest) -> StateValuation: ...


class PolicyModel(Protocol):
    identity: str

    def priors(self, request: PolicyRequest) -> PolicyDistribution: ...


class SearchAlgorithm(Protocol):
    identity: str

    def search(self, request, evaluator, policy_model, provider, configuration) -> SearchResult: ...


class DecisionPolicy(Protocol):
    identity: str

    def choose(self, roster: CandidateRoster, configuration) -> object: ...


__all__ = (
    "CandidateDisposition", "CandidateRoster", "ContinuationOpportunity", "OpportunityRef",
    "ContinuationResult", "DecisionChoice",
    "DecisionDelta", "DecisionFailure", "DecisionFailureStage", "DecisionReason",
    "FailSafeRequest", "PolicyActionEvidence", "PolicyActionIdentity",
    "PolicyDistribution", "PolicyFallbackReason", "PolicyRequest", "PolicySourceIdentity",
    "DecisionPolicy",
    "DecisionResult", "EvaluationRequest", "EvaluationStatus", "PolicyModel",
    "RealizedOutcome", "SearchAlgorithm", "SearchResult", "SearchTrace", "SearchValue",
    "StateValuation",
    "SuccessorResult", "ValueComponent", "ValueEvaluator", "ValueScale",
    "ValuedCandidate",
)
