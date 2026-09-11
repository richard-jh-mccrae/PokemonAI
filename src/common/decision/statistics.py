from __future__ import annotations

from dataclasses import dataclass
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
    identity: StatisticIdentity = DECISION_DELTA


@dataclass(frozen=True, slots=True)
class SampledMeanStatistic:
    choice: ActionChoiceIdentity
    value: SampledMean | None
    status: EvaluationStatus
    identity: StatisticIdentity = SAMPLED_MEAN


@dataclass(frozen=True, slots=True)
class ExpectedContinuationStatistic:
    choice: ActionChoiceIdentity
    value: ExpectedContinuation | None
    status: EvaluationStatus
    identity: StatisticIdentity = EXPECTED_CONTINUATION


@dataclass(frozen=True, slots=True)
class BestContinuationStatistic:
    choice: ActionChoiceIdentity
    value: BestContinuation | None
    status: EvaluationStatus
    identity: StatisticIdentity = BEST_CONTINUATION


__all__ = (
    "BEST_CONTINUATION", "DECISION_DELTA", "EXPECTED_CONTINUATION", "SAMPLED_MEAN",
    "BestContinuationStatistic", "DecisionDeltaStatistic", "DecisionStatistic",
    "ExpectedContinuationStatistic", "SampledMeanStatistic", "StatisticIdentity",
)
