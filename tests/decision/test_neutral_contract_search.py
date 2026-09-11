from dataclasses import dataclass, replace

import pytest

from common.api import ActionIdentity
from common.decision.components import (
    CollaboratorKind, ComponentContract, DecisionPolicyRequest, EvaluationRequest,
    FailSafePolicyRequest, IdentifiedConfiguration, ValueEvaluator,
)
from common.decision.coordinator import DecisionCoordinator
from common.decision.identity import ActionChoiceIdentity
from common.decision.outcomes import (
    DecisionFailureStage, SearchCoverage, SearchOutcome, SearchOutcomeStatus,
    SearchTermination,
)
from common.decision.results import (
    CandidateDisposition, CandidateResult, CandidateRoster, FailSafeSelection,
    NoSelection, PolicySelection, SearchResult,
)
from common.decision.statistics import DecisionDeltaStatistic, StatisticIdentity
from common.decision.values import DecisionDelta, EvaluationStatus, StateValuation, ValueScale
from common.options import LegalAction
from common.observation import ObservationStateBuilder
from ledger_helpers import DARK_E, DRAGAPULT, body, player, printout


SCALE = ValueScale("contract", 1)
ACTION = LegalAction(ActionIdentity("end"), (0,), ((0,),), ())
OBSERVATION = replace(
    ObservationStateBuilder((DRAGAPULT, DARK_E) * 30).root(  # type: ignore[no-untyped-call]
        printout(me=player(active=body(DRAGAPULT, 1)))),  # type: ignore[no-untyped-call]
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
            request.state.seat,
            self.identity,
            evaluation_model_identity=request.evaluation_model.identity,
        )


class ContractSearch:
    identity = "contract-search-v1"
    required_collaborators: tuple[CollaboratorKind, ...] = ()
    optional_collaborators: tuple[CollaboratorKind, ...] = ()

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
                delta=DecisionDelta(0.0, SCALE, perspective=request.state.seat),
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
            statistics=(DecisionDeltaStatistic(
                choice, candidates[0].delta, EvaluationStatus.COMPLETE, DELTA),),
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
                statistics=(),
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
    assert isinstance(result.resolution, NoSelection)
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


def test_coordinator_rejects_static_statistic_incompatibility() -> None:
    class ContractedSearch(ContractSearch):
        contract = ComponentContract(
            ContractSearch.identity, "contract-search-config-v1")

    class ContractedPolicy(Policy):
        contract = ComponentContract(
            Policy.identity, "contract-policy-config-v1",
            required_statistics=frozenset((DELTA,)))

    with pytest.raises(ValueError, match="cannot produce"):
        DecisionCoordinator(
            evaluator=Evaluator(), evaluation_model=Model(), search=ContractedSearch(),
            search_configuration="contract-search-config-v1",
            decision_policy=ContractedPolicy(),
            policy_configuration="contract-policy-config-v1")


def test_policy_failure_reaches_fail_safe_as_non_permitting_outcome() -> None:
    class RaisingPolicy(Policy):
        def choose(self, request: DecisionPolicyRequest) -> ActionChoiceIdentity:
            raise RuntimeError("policy failed")

    class FailSafe:
        identity = "contract-fail-safe-v1"

        def choose(self, request: FailSafePolicyRequest) -> ActionChoiceIdentity:
            assert request.outcome.status is SearchOutcomeStatus.HARD_FAILURE
            assert not request.outcome.permits_action
            assert request.original_search_outcome.status is SearchOutcomeStatus.COMPLETE
            assert request.failure.stage is DecisionFailureStage.POLICY
            return request.roster.identities[0]

    result = DecisionCoordinator(
        evaluator=Evaluator(), evaluation_model=Model(), search=ContractSearch(),
        search_configuration="contract-search-config-v1",
        decision_policy=RaisingPolicy(),
        policy_configuration="contract-policy-config-v1",
        fail_safe_policy=FailSafe(),
    ).decide(OBSERVATION)

    assert isinstance(result.resolution, FailSafeSelection)
    assert result.search.outcome.status is SearchOutcomeStatus.COMPLETE
