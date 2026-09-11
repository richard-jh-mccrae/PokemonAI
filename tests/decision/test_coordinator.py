from dataclasses import dataclass, replace

import pytest

from common.api import ActionIdentity
from common.decision import (
    ActionChoiceIdentity,
    CandidateDisposition,
    CandidateResult,
    CandidateRoster,
    DecisionDeadlineExceeded,
    DecisionDelta,
    DecisionDeltaStatistic,
    DecisionResult,
    EvaluationStatus,
    NoSelection,
    PolicyConfiguration,
    PolicySelection,
    SearchCoverage,
    SearchOutcome,
    SearchOutcomeStatus,
    SearchResult,
    SearchTermination,
    StateValuation,
    ValueScale,
    neutral_lottery_choice,
)
from common.options import LegalAction
from common.observation import ObservationStateBuilder
from ledger_helpers import DARK_E, DRAGAPULT, body, player, printout


SCALE = ValueScale("fixture", 1)
BASE = ObservationStateBuilder((DRAGAPULT, DARK_E) * 30).root(
    printout(me=player(active=body(DRAGAPULT, 1))))


def action(kind: str, index: int) -> LegalAction:
    selection = (index,)
    return LegalAction(ActionIdentity(kind), selection, (selection,), ())


def result_for(actions: tuple[LegalAction, ...]) -> SearchResult:
    state = replace(BASE, legal_actions=actions)
    roster = CandidateRoster(actions, state.decision_key)
    candidates = tuple(CandidateResult(
        choice,
        CandidateDisposition.CONTINUES_TURN,
        DecisionDelta(float(index), SCALE, perspective=state.seat),
        EvaluationStatus.COMPLETE,
    ) for index, choice in enumerate(roster.identities))
    return SearchResult(
        StateValuation(
            state.position_key, 0.0, SCALE, state.seat, "fixture-evaluator",
            evaluation_model_identity="fixture-model"),
        roster,
        candidates,
        SearchOutcome(
            SearchOutcomeStatus.COMPLETE,
            SearchCoverage(),
            SearchTermination("fixture", "complete", 1),
        ),
    )


def test_neutral_lottery_is_seeded_without_favoring_the_first_candidate():
    choices = (
        ActionChoiceIdentity(ActionIdentity("first"), (0,)),
        ActionChoiceIdentity(ActionIdentity("second"), (1,)),
    )

    assert neutral_lottery_choice(choices, PolicyConfiguration()) == choices[1]
    assert neutral_lottery_choice(choices, PolicyConfiguration()) == choices[1]


def test_deadline_is_not_converted_to_partial_search_evidence():
    with pytest.raises(DecisionDeadlineExceeded, match="expired"):
        raise DecisionDeadlineExceeded("expired")


def test_roster_rejects_duplicate_exact_choice_identity():
    duplicate = action("same", 0)

    with pytest.raises(ValueError, match="duplicate candidate action"):
        CandidateRoster((duplicate, duplicate), "fixture")


def test_decision_result_joins_selection_by_exact_choice_identity():
    actions = (action("same", 0), action("same", 1))
    search = result_for(actions)

    result = DecisionResult(search, PolicySelection(search.roster.identities[1]))

    assert result.chosen is actions[1]
    with pytest.raises(ValueError, match="not in Candidate Roster"):
        DecisionResult(
            search,
            PolicySelection(ActionChoiceIdentity(ActionIdentity("same"), (2,))),
        )


def test_decision_result_rejects_evidence_for_another_choice():
    @dataclass(frozen=True)
    class Evidence:
        choice: ActionChoiceIdentity
        owner: str = "fixture"
        schema_version: int = 1

    search = result_for((action("same", 0), action("same", 1)))

    with pytest.raises(ValueError, match="evidence differs"):
        DecisionResult(
            search,
            PolicySelection(search.roster.identities[0], Evidence(
                search.roster.identities[1])),
        )


def test_search_result_rejects_statistic_perspective_and_missing_coverage():
    search = result_for((action("end", 0),))
    choice = search.roster.identities[0]
    statistic = DecisionDeltaStatistic(
        choice, DecisionDelta(1.0, SCALE, perspective=1), EvaluationStatus.COMPLETE)

    with pytest.raises(ValueError, match="perspective"):
        replace(
            search,
            outcome=replace(
                search.outcome,
                coverage=SearchCoverage.covered(statistic.identity, (choice,))),
            statistics=(statistic,),
        )

    valid = replace(
        statistic,
        value=DecisionDelta(1.0, SCALE, perspective=search.baseline.perspective),
    )
    with pytest.raises(ValueError, match="absent from search coverage"):
        replace(search, statistics=(valid,))


def test_no_selection_rejects_a_permitting_nonempty_search():
    search = result_for((action("end", 0),))

    with pytest.raises(ValueError, match="requires a selection"):
        DecisionResult(search, NoSelection(SearchOutcomeStatus.COMPLETE))
