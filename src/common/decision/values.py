from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from common.api import ActionIdentity
from common.observation import ObservationState, TransitionTrace


class EvaluationStatus(str, Enum):
    COMPLETE = "complete"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class EvaluationEvidence(Protocol):
    owner: str
    schema_version: int


class ContinuationOpportunity(str, Enum):
    DEPENDENCY_REACH = "dependency_reach"
    LETHAL_ATTACK = "lethal_attack"
    WINNING_ATTACK = "winning_attack"


class RealizedOutcome(str, Enum):
    ACTION_ENDED_TURN = "action_ended_turn"
    EXPLICIT_TURN_END = "explicit_turn_end"
    GAME_WIN = "game_win"
    OPPONENT_ACTIVE_KNOCKOUT = "opponent_active_knockout"
    OPPONENT_BODY_KNOCKOUT = "opponent_body_knockout"


@dataclass(frozen=True, slots=True, eq=False)
class OpportunityRef:
    kind: str
    source: str | None = None

    @classmethod
    def decode(cls, value: OpportunityRef | ContinuationOpportunity | str) -> OpportunityRef:
        if isinstance(value, cls):
            return value
        return cls(str(getattr(value, "value", value)))

    def wire(self) -> dict[str, str | None]:
        return {"kind": self.kind, "source": self.source}

    def __str__(self) -> str:
        return self.kind

    def __eq__(self, other: object) -> bool:
        if isinstance(other, OpportunityRef):
            return self.kind == other.kind and self.source == other.source
        if isinstance(other, (str, ContinuationOpportunity)):
            return self.kind == str(getattr(other, "value", other))
        return False

    def __hash__(self) -> int:
        return hash(self.kind)


@dataclass(frozen=True, slots=True)
class ValueScale:
    name: str
    schema_version: int
    lower_bound: float | None = None
    upper_bound: float | None = None

    def __post_init__(self) -> None:
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

    def __post_init__(self) -> None:
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
    evidence: EvaluationEvidence | None = None
    cache_key: str | None = None
    baseline_identity: str | None = None
    evaluation_model_identity: str | None = None

    def __post_init__(self) -> None:
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
    perspective: int | str = field(kw_only=True)

    def __post_init__(self) -> None:
        if not math.isfinite(self.total):
            raise ValueError("decision delta must be finite")


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

    def __post_init__(self) -> None:
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
class SampledMean:
    total: float
    scale: ValueScale
    samples: int
    perspective: int | str = field(kw_only=True)

    def __post_init__(self) -> None:
        if not math.isfinite(self.total) or self.samples <= 0:
            raise ValueError("sampled mean requires finite completed samples")


@dataclass(frozen=True, slots=True)
class ExpectedContinuation:
    total: float
    scale: ValueScale
    perspective: int | str = field(kw_only=True)

    def __post_init__(self) -> None:
        if not math.isfinite(self.total):
            raise ValueError("expected continuation must be finite")


@dataclass(frozen=True, slots=True)
class BestContinuation:
    total: float
    scale: ValueScale
    perspective: int | str = field(kw_only=True)

    def __post_init__(self) -> None:
        if not math.isfinite(self.total):
            raise ValueError("best continuation must be finite")


@dataclass(frozen=True, slots=True)
class SuccessorResult:
    probability: float
    valuation: StateValuation
    ended: bool
    state: ObservationState
    trace: TransitionTrace
    action_path: tuple[ActionIdentity, ...] = ()
    status: EvaluationStatus = EvaluationStatus.COMPLETE
    failure: str | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("successor probability must be between zero and one")
        if self.status is not self.valuation.status:
            raise ValueError("successor and valuation statuses must match")


__all__ = (
    "BestContinuation", "ContinuationOpportunity", "ContinuationResult", "DecisionDelta",
    "EvaluationEvidence", "EvaluationStatus", "ExpectedContinuation", "OpportunityRef",
    "RealizedOutcome",
    "SampledMean", "StateValuation", "SuccessorResult", "ValueComponent",
    "ValueScale",
)
