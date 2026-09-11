from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from common.decision import ActionChoiceIdentity, PolicyDistribution

from .prizes import PrizeMap


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
    "LedgerCandidateEvidence", "LedgerEvidence", "LedgerFailSafeDecisionEvidence",
    "LedgerPolicyDecisionEvidence",
)
