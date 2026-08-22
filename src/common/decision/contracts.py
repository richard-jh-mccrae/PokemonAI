from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from common.observation import ObservationState, TransitionTrace


class EvaluationStatus(str, Enum):
    COMPLETE = "complete"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class CandidateDisposition(str, Enum):
    CONTINUES_TURN = "continues_turn"
    ENDS_TURN = "ends_turn"
    FORCED = "forced"


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
    opportunities_created: tuple[str, ...] = ()
    opportunities_preserved: tuple[str, ...] = ()
    opportunities_consumed: tuple[str, ...] = ()


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

    def __post_init__(self):
        identities = tuple(getattr(candidate.action, "identity", candidate.action)
                           for candidate in self.candidates)
        if any(identity in identities[:index]
               for index, identity in enumerate(identities)):
            raise ValueError("duplicate candidate action")


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    state: object
    evaluation_model: object
    parent_valuation: StateValuation | None = None
    observation_delta: object | None = None


class ValuationCache:
    def __init__(self):
        self._values: dict[tuple[str, str, str], StateValuation] = {}

    def evaluate(self, request: EvaluationRequest, evaluator) -> StateValuation:
        state = getattr(request.state, "observation", request.state)
        state_key = getattr(state, "position_key", str(id(state)))
        model_key = getattr(request.evaluation_model, "identity", "anonymous-model")
        key = (evaluator.identity, model_key, state_key)
        if key not in self._values:
            self._values[key] = evaluator.evaluate(request)
        return self._values[key]


@dataclass(frozen=True, slots=True)
class SearchResult:
    baseline: StateValuation
    roster: CandidateRoster
    nodes_visited: int = 0
    stop_reason: str = "complete"
    frontier: tuple[object, ...] = ()


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
    policy_reason: str = ""
    behavior_identity: object | None = None


@dataclass(frozen=True, slots=True)
class DecisionChoice:
    action: object
    reason: str


class ValueEvaluator(Protocol):
    identity: str

    def evaluate(self, request: EvaluationRequest) -> StateValuation: ...


class PolicyModel(Protocol):
    identity: str

    def priors(self, state, actions: tuple[object, ...]) -> tuple[float, ...]: ...


class SearchAlgorithm(Protocol):
    identity: str

    def search(self, request, evaluator, policy_model, provider, configuration) -> SearchResult: ...


class DecisionPolicy(Protocol):
    identity: str

    def choose(self, roster: CandidateRoster, configuration) -> object: ...


__all__ = (
    "CandidateDisposition", "CandidateRoster", "ContinuationResult", "DecisionChoice",
    "DecisionDelta",
    "DecisionPolicy",
    "DecisionResult", "EvaluationRequest", "EvaluationStatus", "PolicyModel",
    "SearchAlgorithm", "SearchResult", "SearchTrace", "SearchValue", "StateValuation",
    "SuccessorResult",
    "ValuationCache", "ValueComponent", "ValueEvaluator", "ValueScale",
    "ValuedCandidate",
)
