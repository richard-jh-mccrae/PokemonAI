from __future__ import annotations

from .components import DecisionPolicyRequest
from .compatibility_contracts import CandidateRoster as LegacyCandidateRoster
from .compatibility_contracts import ValuedCandidate as LegacyValuedCandidate
from .statistics import DECISION_DELTA


DECISION_DELTA_STATISTIC = DECISION_DELTA


def legacy_roster_from_policy_request(request: DecisionPolicyRequest) -> LegacyCandidateRoster:
    from common.ledger.evidence import LedgerEvidence

    evidence = request.evidence
    if not isinstance(evidence, LedgerEvidence):
        raise TypeError("Ledger policy requires Ledger evidence")
    evidence_by_choice = {item.choice: item for item in evidence.candidates}
    priors = (() if evidence.policy_distribution is None
              else evidence.policy_distribution.priors_for(request.roster))
    candidates = tuple(LegacyValuedCandidate(
        action,
        result.delta,
        result.disposition,
        result.delta_status,
        result.successors,
        result.delta_gaps,
        result.continuation,
        prior=(None if not priors else priors[index]),
        policy_tie_break=evidence_by_choice[result.choice].policy_tie_break,
        policy_evidence=evidence_by_choice[result.choice].prize_map,
    ) for index, (action, result) in enumerate(zip(
        request.roster.actions, request.candidates)))
    return LegacyCandidateRoster.from_legal_actions(
        request.roster.actions, candidates, forced=request.roster.forced)


__all__ = (
    "DECISION_DELTA_STATISTIC", "legacy_roster_from_policy_request",
)
