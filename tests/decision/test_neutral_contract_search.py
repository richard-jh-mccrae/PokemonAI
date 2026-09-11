from dataclasses import dataclass, replace

import pytest

from common.api import ActionIdentity
from common.decision import (
    ActionChoiceIdentity,
    CandidateDisposition,
    CandidateResult,
    CandidateRoster,
    ComponentContract,
    DecisionCoordinator,
    DecisionDelta,
    DecisionPolicyRequest,
    EvaluationRequest,
    EvaluationStatus,
    PolicySelection,
    SearchCoverage,
    SearchOutcome,
    SearchOutcomeStatus,
    SearchResult,
    SearchTermination,
    StateValuation,
    StatisticIdentity,
    ValueScale,
    ValueEvaluator,
)
from common.decision.components import IdentifiedConfiguration
from common.options import LegalAction
from common.observation import ObservationStateBuilder
from ledger_helpers import DARK_E, DRAGAPULT, body, player, printout


SCALE = ValueScale("contract", 1)
ACTION = LegalAction(ActionIdentity("end"), (0,), ((0,),), ())
OBSERVATION = replace(
    ObservationStateBuilder((DRAGAPULT, DARK_E) * 30).root(
        printout(me=player(active=body(DRAGAPULT, 1)))),
    legal_actions=(ACTION,),
)
DELTA = StatisticIdentity("common", "decision-delta", 1)


@dataclass(frozen=True)
class Model:
    identity: str = "contract-model-v1"


class Evaluator:
    identity = "contract-evaluator-v1"
    value_scale = SCALE
    accepted_model_identity = Model.identity

    def evaluate(self, request: EvaluationRequest) -> StateValuation:
        return StateValuation(
            request.state.position_key,
            0.0,
            SCALE,
            request.root_perspective,
            self.identity,
            evaluation_model_identity=request.evaluation_model.identity,
        )


class ContractSearch:
    identity = "contract-search-v1"
    required_collaborators = ()
    optional_collaborators = ()

    def search(
            self,
            request: EvaluationRequest,
            evaluator: ValueEvaluator,
            configuration: IdentifiedConfiguration | str,
    ) -> SearchResult:
        baseline = evaluator.evaluate(request)
        roster = CandidateRoster.from_request(request)
        choice = roster.identities[0]
        candidates = (
            CandidateResult(
                choice,
                CandidateDisposition.FORCED,
                delta=DecisionDelta(0.0, SCALE),
                delta_status=EvaluationStatus.COMPLETE,
            ),
        )
        coverage = SearchCoverage.covered(DELTA, roster.identities)
        return SearchResult(
            baseline,
            roster,
            candidates,
            SearchOutcome(
                SearchOutcomeStatus.COMPLETE,
                coverage,
                SearchTermination("contract-search", "complete", 1),
            ),
        )


class Policy:
    identity = "contract-policy-v1"
    required_statistics = (DELTA,)

    def choose(self, request: DecisionPolicyRequest) -> ActionChoiceIdentity:
        return request.roster.identities[0]


def test_independent_search_runs_through_the_coordinator_without_puct_collaborators() -> None:
    coordinator = DecisionCoordinator(
        evaluator=Evaluator(),
        evaluation_model=Model(),
        search=ContractSearch(),
        search_configuration="contract-search-config-v1",
        decision_policy=Policy(),
        policy_configuration="contract-policy-config-v1",
    )

    result = coordinator.decide(OBSERVATION)

    assert isinstance(result.resolution, PolicySelection)
    assert result.resolution.choice == ActionChoiceIdentity.from_action(ACTION)
    assert result.chosen is ACTION
    assert result.search.outcome.status is SearchOutcomeStatus.COMPLETE


def test_choice_identity_keeps_semantically_equal_menu_selections_distinct() -> None:
    identity = ActionIdentity("card", ("same-card",))

    assert ActionChoiceIdentity(identity, (1,)) != ActionChoiceIdentity(identity, (2,))


def test_non_permitting_outcome_produces_no_selection() -> None:
    class IncompleteSearch(ContractSearch):
        def search(
                self,
                request: EvaluationRequest,
                evaluator: ValueEvaluator,
                configuration: IdentifiedConfiguration | str,
        ) -> SearchResult:
            result = super().search(request, evaluator, configuration)
            return replace(
                result,
                outcome=SearchOutcome(
                    SearchOutcomeStatus.INSUFFICIENT_INITIALIZATION,
                    SearchCoverage(),
                    SearchTermination("contract-search", "no-sample", 1),
                ),
            )

    result = DecisionCoordinator(
        evaluator=Evaluator(),
        evaluation_model=Model(),
        search=IncompleteSearch(),
        search_configuration="contract-search-config-v1",
        decision_policy=Policy(),
        policy_configuration="contract-policy-config-v1",
    ).decide(OBSERVATION)

    assert result.chosen is None
    assert result.resolution.outcome is SearchOutcomeStatus.INSUFFICIENT_INITIALIZATION


def test_coordinator_rejects_an_evaluator_for_another_model() -> None:
    class WrongEvaluator(Evaluator):
        accepted_model_identity = "different-model-v1"

    with pytest.raises(ValueError, match="does not accept"):
        DecisionCoordinator(
            evaluator=WrongEvaluator(),
            evaluation_model=Model(),
            search=ContractSearch(),
            search_configuration="contract-search-config-v1",
            decision_policy=Policy(),
            policy_configuration="contract-policy-config-v1",
        )


def test_coordinator_rejects_a_component_configuration_mismatch() -> None:
    class ContractedSearch(ContractSearch):
        contract = ComponentContract(ContractSearch.identity, "different-config-v1")

    with pytest.raises(ValueError, match="rejects its injected configuration"):
        DecisionCoordinator(
            evaluator=Evaluator(),
            evaluation_model=Model(),
            search=ContractedSearch(),
            search_configuration="contract-search-config-v1",
            decision_policy=Policy(),
            policy_configuration="contract-policy-config-v1",
        )
