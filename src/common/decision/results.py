from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from common.options import LegalAction

from .identity import ActionChoiceIdentity
from .outcomes import DecisionFailure, DecisionFailureStage, SearchOutcome, SearchOutcomeStatus
from .statistics import DecisionStatistic
from .values import (
    ContinuationResult,
    DecisionDelta,
    EvaluationStatus,
    StateValuation,
    SuccessorResult,
)


class CandidateDisposition(str, Enum):
    CONTINUES_TURN = "continues_turn"
    ENDS_TURN = "ends_turn"
    FORCED = "forced"


class SearchEvidence(Protocol):
    owner: str
    schema_version: int


class DecisionEvidence(Protocol):
    owner: str
    schema_version: int
    choice: ActionChoiceIdentity


@dataclass(frozen=True, slots=True)
class BehaviorIdentity:
    evaluator: str
    evaluation_model: str
    search: str
    policy_model: str
    decision_policy: str
    fail_safe_policy: str
    provider: str
    compute: str
    prize_plan: str = ""

    def __post_init__(self) -> None:
        if not all((self.evaluator, self.evaluation_model, self.search,
                    self.policy_model, self.decision_policy,
                    self.fail_safe_policy, self.provider, self.compute)):
            raise ValueError("Behavior Identity requires every resolved component")


@dataclass(frozen=True, slots=True)
class CandidateRoster:
    actions: tuple[LegalAction, ...]
    decision_key: str
    forced: bool = False

    def __post_init__(self) -> None:
        identities = tuple(ActionChoiceIdentity.from_action(action) for action in self.actions)
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate candidate action")
        if self.forced and not self.actions:
            raise ValueError("forced roster requires an action")

    @classmethod
    def from_request(cls, request: EvaluationRequestLike, *, forced: bool = False) -> CandidateRoster:
        return cls(tuple(request.state.legal_actions), request.state.decision_key, forced)

    @property
    def identities(self) -> tuple[ActionChoiceIdentity, ...]:
        return tuple(ActionChoiceIdentity.from_action(action) for action in self.actions)

    def action_for(self, choice: ActionChoiceIdentity) -> LegalAction:
        try:
            return self.actions[self.identities.index(choice)]
        except ValueError:
            raise ValueError("choice is not in Candidate Roster") from None


class EvaluationRequestLike(Protocol):
    state: ObservationStateLike


class ObservationStateLike(Protocol):
    decision_key: str
    legal_actions: tuple[LegalAction, ...]


@dataclass(frozen=True, slots=True)
class CandidateResult:
    choice: ActionChoiceIdentity
    disposition: CandidateDisposition
    delta: DecisionDelta | None = None
    delta_status: EvaluationStatus = EvaluationStatus.UNAVAILABLE
    delta_gaps: tuple[str, ...] = ()
    successors: tuple[SuccessorResult, ...] = ()
    continuation: ContinuationResult | None = None
    continuation_status: EvaluationStatus = EvaluationStatus.UNAVAILABLE
    continuation_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.delta_status is EvaluationStatus.UNAVAILABLE and self.delta is not None:
            raise ValueError("unavailable decision delta cannot carry a value")
        if self.delta_status is not EvaluationStatus.UNAVAILABLE and self.delta is None:
            raise ValueError("available decision delta requires a value")
        if (self.continuation_status is EvaluationStatus.UNAVAILABLE
                and self.continuation is not None):
            raise ValueError("unavailable continuation cannot carry a value")
        if (self.continuation_status is not EvaluationStatus.UNAVAILABLE
                and self.continuation is None):
            raise ValueError("available continuation requires a value")


@dataclass(frozen=True, slots=True)
class SearchResult:
    baseline: StateValuation | None
    roster: CandidateRoster
    candidates: tuple[CandidateResult, ...]
    outcome: SearchOutcome
    statistics: tuple[DecisionStatistic, ...] = ()
    evidence: SearchEvidence | None = None

    def __post_init__(self) -> None:
        choices = tuple(candidate.choice for candidate in self.candidates)
        if choices != self.roster.identities:
            raise ValueError("Search Result requires one ordered Candidate Result per roster member")
        roster_choices = set(self.roster.identities)
        for covered in self.outcome.coverage.statistics:
            if not covered.choices.issubset(roster_choices):
                raise ValueError("search coverage contains a choice outside Candidate Roster")

    def candidate_for(self, choice: ActionChoiceIdentity) -> CandidateResult:
        try:
            return self.candidates[self.roster.identities.index(choice)]
        except ValueError:
            raise ValueError("choice is not in Search Result") from None


@dataclass(frozen=True, slots=True)
class PolicySelection:
    choice: ActionChoiceIdentity
    evidence: DecisionEvidence | None = None


@dataclass(frozen=True, slots=True)
class ForcedSelection:
    choice: ActionChoiceIdentity
    evidence: DecisionEvidence | None = None


@dataclass(frozen=True, slots=True)
class FailSafeSelection:
    choice: ActionChoiceIdentity
    failure: DecisionFailure
    evidence: DecisionEvidence | None = None

    @property
    def failure_stage(self) -> DecisionFailureStage:
        return self.failure.stage


@dataclass(frozen=True, slots=True)
class NoSelection:
    outcome: SearchOutcomeStatus


DecisionResolution = PolicySelection | ForcedSelection | FailSafeSelection | NoSelection


@dataclass(frozen=True, slots=True)
class DecisionResult:
    search: SearchResult
    resolution: DecisionResolution
    behavior_identity: BehaviorIdentity | None = None

    def __post_init__(self) -> None:
        if isinstance(self.resolution, NoSelection):
            if self.search.roster.actions and self.search.outcome.permits_action:
                raise ValueError("permitting non-empty search requires a selection")
            return
        if self.resolution.choice not in self.search.roster.identities:
            raise ValueError("selected choice is not in Candidate Roster")
        if (isinstance(self.resolution, (PolicySelection, ForcedSelection))
                and not self.search.outcome.permits_action):
            raise ValueError("normal selection requires a permitting Search Outcome")
        if isinstance(self.resolution, ForcedSelection) and not self.search.roster.forced:
            raise ValueError("forced selection requires a forced Candidate Roster")

    @property
    def chosen(self) -> LegalAction | None:
        if isinstance(self.resolution, NoSelection):
            return None
        return self.search.roster.action_for(self.resolution.choice)

    @property
    def chosen_candidate(self) -> CandidateResult | None:
        if isinstance(self.resolution, NoSelection):
            return None
        return self.search.candidate_for(self.resolution.choice)

    @property
    def baseline(self) -> StateValuation | None:
        return self.search.baseline

    @property
    def roster(self) -> CandidateRoster:
        return self.search.roster


__all__ = (
    "BehaviorIdentity", "CandidateDisposition", "CandidateResult", "CandidateRoster",
    "DecisionEvidence",
    "DecisionResolution", "DecisionResult", "FailSafeSelection", "ForcedSelection",
    "NoSelection", "PolicySelection", "SearchEvidence", "SearchResult",
)
