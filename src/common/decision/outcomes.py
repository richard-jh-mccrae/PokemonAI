from __future__ import annotations

import traceback
from dataclasses import dataclass
from enum import Enum

from .identity import ActionChoiceIdentity
from .statistics import StatisticIdentity


class DecisionFailureStage(str, Enum):
    EVALUATION = "evaluation"
    PROVIDER = "provider"
    SEARCH = "search"
    POLICY = "policy"
    PRESENTATION = "presentation"
    RUNTIME = "runtime"


@dataclass(frozen=True, slots=True)
class DecisionFailure:
    stage: DecisionFailureStage
    error_type: str
    message: str
    traceback_tail: str = ""

    @classmethod
    def capture(cls, stage: DecisionFailureStage, exc: Exception) -> DecisionFailure:
        return cls(stage, type(exc).__name__, str(exc)[:500], traceback.format_exc()[-2000:])


class SearchOutcomeStatus(str, Enum):
    COMPLETE = "complete"
    BUDGET_LIMITED = "budget_limited"
    INSUFFICIENT_INITIALIZATION = "insufficient_initialization"
    CANCELLED = "cancelled"
    HARD_FAILURE = "hard_failure"

    @property
    def permits_action(self) -> bool:
        return self in (self.COMPLETE, self.BUDGET_LIMITED)


@dataclass(frozen=True, slots=True)
class SearchTermination:
    owner: str
    code: str
    schema_version: int

    def __post_init__(self) -> None:
        if not self.owner or not self.code or self.schema_version <= 0:
            raise ValueError("search termination requires owner, code, and positive schema")


@dataclass(frozen=True, slots=True)
class StatisticCoverage:
    statistic: StatisticIdentity
    choices: frozenset[ActionChoiceIdentity]


@dataclass(frozen=True, slots=True)
class SearchCoverage:
    statistics: tuple[StatisticCoverage, ...] = ()

    def __post_init__(self) -> None:
        identities = tuple(item.statistic for item in self.statistics)
        if len(set(identities)) != len(identities):
            raise ValueError("search coverage contains duplicate statistic identities")

    @classmethod
    def covered(
            cls,
            statistic: StatisticIdentity,
            choices: tuple[ActionChoiceIdentity, ...],
    ) -> SearchCoverage:
        return cls((StatisticCoverage(statistic, frozenset(choices)),))

    def choices_for(self, statistic: StatisticIdentity) -> frozenset[ActionChoiceIdentity]:
        return next((item.choices for item in self.statistics
                     if item.statistic == statistic), frozenset())

    def covers(
            self,
            statistic: StatisticIdentity,
            choices: tuple[ActionChoiceIdentity, ...],
    ) -> bool:
        return frozenset(choices).issubset(self.choices_for(statistic))


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    status: SearchOutcomeStatus
    coverage: SearchCoverage
    termination: SearchTermination
    failure: DecisionFailure | None = None

    def __post_init__(self) -> None:
        if self.status is SearchOutcomeStatus.HARD_FAILURE and self.failure is None:
            raise ValueError("hard failure outcome requires a Decision Failure")
        if self.status is not SearchOutcomeStatus.HARD_FAILURE and self.failure is not None:
            raise ValueError("only hard failure outcome carries a Decision Failure")

    @property
    def permits_action(self) -> bool:
        return self.status.permits_action


__all__ = (
    "DecisionFailure", "DecisionFailureStage", "SearchCoverage", "SearchOutcome",
    "SearchOutcomeStatus", "SearchTermination", "StatisticCoverage",
)
