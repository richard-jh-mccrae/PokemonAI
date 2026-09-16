from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .identity import ActionChoiceIdentity
from .values import (
    BestContinuation, DecisionDelta, EvaluationStatus, ExpectedContinuation, SampledMean,
)


@dataclass(frozen=True, order=True, slots=True)
class StatisticIdentity:
    owner: str
    name: str
    schema_version: int

    def __post_init__(self) -> None:
        if not self.owner or not self.name or self.schema_version <= 0:
            raise ValueError("statistic identity requires owner, name, and positive schema")


class DecisionStatistic(Protocol):
    @property
    def identity(self) -> StatisticIdentity: ...

    @property
    def choice(self) -> ActionChoiceIdentity: ...


DECISION_DELTA = StatisticIdentity("common", "decision-delta", 1)
SAMPLED_MEAN = StatisticIdentity("common", "sampled-mean", 1)
EXPECTED_CONTINUATION = StatisticIdentity("common", "expected-continuation", 1)
BEST_CONTINUATION = StatisticIdentity("common", "best-continuation", 1)


@dataclass(frozen=True, slots=True)
class DecisionDeltaStatistic:
    choice: ActionChoiceIdentity
    value: DecisionDelta | None
    status: EvaluationStatus
    identity: StatisticIdentity = field(default=DECISION_DELTA, init=False)

    def __post_init__(self) -> None:
        _validate_availability(self.status, self.value, "decision delta")


@dataclass(frozen=True, slots=True)
class SampledMeanStatistic:
    choice: ActionChoiceIdentity
    value: SampledMean | None
    status: EvaluationStatus
    identity: StatisticIdentity = field(default=SAMPLED_MEAN, init=False)

    def __post_init__(self) -> None:
        _validate_availability(self.status, self.value, "sampled mean")


@dataclass(frozen=True, slots=True)
class ExpectedContinuationStatistic:
    choice: ActionChoiceIdentity
    value: ExpectedContinuation | None
    status: EvaluationStatus
    identity: StatisticIdentity = field(default=EXPECTED_CONTINUATION, init=False)

    def __post_init__(self) -> None:
        _validate_availability(self.status, self.value, "expected continuation")


@dataclass(frozen=True, slots=True)
class BestContinuationStatistic:
    choice: ActionChoiceIdentity
    value: BestContinuation | None
    status: EvaluationStatus
    identity: StatisticIdentity = field(default=BEST_CONTINUATION, init=False)

    def __post_init__(self) -> None:
        _validate_availability(self.status, self.value, "best continuation")


def _validate_availability(status: EvaluationStatus, value: object | None,
                           label: str) -> None:
    if status is EvaluationStatus.UNAVAILABLE and value is not None:
        raise ValueError(f"unavailable {label} cannot carry a value")
    if status is not EvaluationStatus.UNAVAILABLE and value is None:
        raise ValueError(f"available {label} requires a value")


__all__ = (
    "BEST_CONTINUATION", "DECISION_DELTA", "EXPECTED_CONTINUATION", "SAMPLED_MEAN",
    "BestContinuationStatistic", "DecisionDeltaStatistic", "DecisionStatistic",
    "ExpectedContinuationStatistic", "SampledMeanStatistic", "StatisticIdentity",
)
