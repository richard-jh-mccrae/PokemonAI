from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from common.decision.components import PolicyDistribution
from common.decision.identity import ActionChoiceIdentity

from .prizes import PrizeMap


class LedgerDecisionReason(str, Enum):
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


@dataclass(frozen=True, slots=True)
class LedgerCandidateEvidence:
    choice: ActionChoiceIdentity
    policy_tie_break: tuple[int | float | str, ...] = ()
    prize_map: PrizeMap | None = None


@dataclass(frozen=True, slots=True)
class LedgerEvidence:
    owner: ClassVar[str] = "ledger"
    schema_version: int
    nodes_visited: int
    frontier: tuple[str, ...]
    policy_distribution: PolicyDistribution | None
    candidates: tuple[LedgerCandidateEvidence, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1 or self.nodes_visited < 0:
            raise ValueError("invalid Ledger evidence")
        choices = tuple(candidate.choice for candidate in self.candidates)
        if len(set(choices)) != len(choices):
            raise ValueError("Ledger evidence contains duplicate choices")


@dataclass(frozen=True, slots=True)
class LedgerPolicyDecisionEvidence:
    owner: ClassVar[str] = "ledger"
    schema_version: int
    choice: ActionChoiceIdentity
    reason: str


LedgerFailSafeDecisionEvidence = LedgerPolicyDecisionEvidence


__all__ = (
    "LedgerCandidateEvidence", "LedgerDecisionReason", "LedgerEvidence",
    "LedgerFailSafeDecisionEvidence",
    "LedgerPolicyDecisionEvidence",
)
