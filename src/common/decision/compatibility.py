from __future__ import annotations

from common.observation import ObservationState

from .components import (
    DecisionPolicyRequest, EvaluationRequest, PolicyModelRequest, PolicySourceIdentity,
)
from .compatibility_contracts import CandidateRoster as LegacyCandidateRoster
from .compatibility_contracts import SearchResult as LegacySearchResult
from .compatibility_contracts import (
    CandidateDisposition as LegacyCandidateDisposition,
    ValuedCandidate as LegacyValuedCandidate,
)
from .outcomes import (
    SearchCoverage, SearchOutcome, SearchOutcomeStatus, SearchTermination, StatisticCoverage,
)
from .results import (
    CandidateDisposition, CandidateResult, CandidateRoster, SearchEvidence, SearchResult,
)
from .statistics import DECISION_DELTA, DecisionStatistic


DECISION_DELTA_STATISTIC = DECISION_DELTA


def search_result_from_legacy(
        request: EvaluationRequest,
        result: LegacySearchResult,
        owner: str,
        evidence: SearchEvidence,
        *,
        status: SearchOutcomeStatus | None = None,
        statistics: tuple[DecisionStatistic, ...] = (),
        statistic_coverage: tuple[StatisticCoverage, ...] = (),
) -> SearchResult:
    actions = tuple(request.state.legal_actions)
    roster = CandidateRoster(actions, request.state.decision_key, result.roster.forced)
    legacy_choices = tuple(
        roster_choice(candidate.action) for candidate in result.roster.candidates)
    if legacy_choices != roster.identities:
        raise ValueError(
            "legacy search roster differs from Evaluation Request: "
            f"{legacy_choices!r} != {roster.identities!r}")
    candidates = candidate_results_from_legacy(roster, result.roster)
    covered = tuple(candidate.choice for candidate in candidates
                    if candidate.delta_status.value != "unavailable")
    delta_coverage = (() if not covered else (
        StatisticCoverage(DECISION_DELTA_STATISTIC, frozenset(covered)),))
    coverage = SearchCoverage((*delta_coverage, *statistic_coverage))
    status = _outcome_status(result) if status is None else status
    outcome = SearchOutcome(
        status,
        coverage,
        SearchTermination(owner, result.stop_reason or status.value, 1),
        result.failure if status is SearchOutcomeStatus.HARD_FAILURE else None,
    )
    return SearchResult(
        result.baseline,
        roster,
        candidates,
        outcome,
        statistics=statistics,
        evidence=evidence,
    )


def candidate_results_from_legacy(
        roster: CandidateRoster,
        legacy_roster: LegacyCandidateRoster,
) -> tuple[CandidateResult, ...]:
    return tuple(CandidateResult(
        choice,
        CandidateDisposition(legacy.disposition.value),
        legacy.delta,
        legacy.status,
        legacy.gaps,
        legacy.successors,
        (legacy.continuation
         if legacy.status.value != "unavailable" else None),
        (legacy.status if legacy.continuation is not None
         and legacy.status.value != "unavailable"
         else type(legacy.status).UNAVAILABLE),
        (legacy.gaps if legacy.continuation is not None
         and legacy.status.value != "unavailable" else ()),
    ) for choice, legacy in zip(roster.identities, legacy_roster.candidates))


def policy_model_request_from_legacy(
        observation: ObservationState,
        legacy_roster: LegacyCandidateRoster,
        source: PolicySourceIdentity,
) -> PolicyModelRequest:
    roster = CandidateRoster(
        tuple(observation.legal_actions), observation.decision_key,
        legacy_roster.forced)
    legacy_choices = tuple(
        roster_choice(candidate.action) for candidate in legacy_roster.candidates)
    if legacy_choices != roster.identities:
        raise ValueError("policy candidates differ from Observation State legal actions")
    return PolicyModelRequest(
        observation,
        roster,
        candidate_results_from_legacy(roster, legacy_roster),
        (),
        source,
    )


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
        LegacyCandidateDisposition(result.disposition.value),
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


def _outcome_status(result: LegacySearchResult) -> SearchOutcomeStatus:
    if result.failure is not None:
        return SearchOutcomeStatus.HARD_FAILURE
    if result.stop_reason in {"node_budget", "time_budget"}:
        covered = any(candidate.delta is not None for candidate in result.roster.candidates)
        return (SearchOutcomeStatus.BUDGET_LIMITED if covered
                else SearchOutcomeStatus.INSUFFICIENT_INITIALIZATION)
    if (not result.roster.forced
            and not any(candidate.delta is not None
                        for candidate in result.roster.candidates)):
        return SearchOutcomeStatus.INSUFFICIENT_INITIALIZATION
    return SearchOutcomeStatus.COMPLETE


def roster_choice(action) -> object:
    from .identity import ActionChoiceIdentity

    return ActionChoiceIdentity.from_action(action)


__all__ = (
    "DECISION_DELTA_STATISTIC", "legacy_roster_from_policy_request",
    "policy_model_request_from_legacy", "search_result_from_legacy",
)
