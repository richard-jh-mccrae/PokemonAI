from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

import pytest

from common.api import ActionIdentity
from common.decision.components import (
    CollaboratorKind, ComponentContract, DecisionPolicyRequest, EvidenceIdentity,
    EvaluationRequest, FailSafePolicyRequest, IdentifiedConfiguration, ValueEvaluator,
    SearchAlgorithm, SearchProvider, SearchWithPolicyModelAndProvider,
)
from common.decision.coordinator import DecisionCoordinator
from common.decision.identity import ActionChoiceIdentity
from common.decision.outcomes import (
    DecisionFailureStage, SearchCoverage, SearchOutcome, SearchOutcomeStatus,
    SearchTermination,
)
from common.decision.results import (
    BehaviorIdentity, CandidateDisposition, CandidateResult, CandidateRoster,
    FailSafeSelection, NO_FAIL_SAFE_POLICY_IDENTITY, NO_POLICY_MODEL_IDENTITY,
    NO_PRIZE_PLAN_IDENTITY, NO_PROVIDER_IDENTITY, NoSelection, PolicySelection,
    SearchResult,
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


def behavior_identity(
        fail_safe_policy: str = NO_FAIL_SAFE_POLICY_IDENTITY,
        provider: str = NO_PROVIDER_IDENTITY,
) -> BehaviorIdentity:
    return BehaviorIdentity(
        Evaluator.identity, Model.identity, ContractSearch.identity,
        NO_POLICY_MODEL_IDENTITY, Policy.identity, fail_safe_policy,
        provider, "contract-compute-v1", NO_PRIZE_PLAN_IDENTITY,
    )

if TYPE_CHECKING:
    from common.ledger.search import LedgerOnePlySearch
    from common.puct.search import PuctSearch

    ledger_adapter: SearchWithPolicyModelAndProvider = LedgerOnePlySearch()
    puct_adapter: SearchWithPolicyModelAndProvider = PuctSearch()


@dataclass(frozen=True)
class Model:
    identity: str = "contract-model-v1"


class Evaluator:
    identity = "contract-evaluator-v1"
    value_scale = SCALE
    accepted_model_identity = Model.identity
    contract = ComponentContract(identity, "Model")

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
    contract = ComponentContract(
        identity, "contract-search-config-v1",
        produced_statistics=frozenset((DELTA,)))

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
                choice, candidates[0].delta, EvaluationStatus.COMPLETE),),
        )


class Policy:
    identity = "contract-policy-v1"
    required_statistics = (DELTA,)
    contract = ComponentContract(
        identity, "contract-policy-config-v1",
        required_statistics=frozenset(required_statistics))

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
        behavior_identity=behavior_identity(),
        compute_identity="contract-compute-v1",
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
        behavior_identity=behavior_identity(),
        compute_identity="contract-compute-v1",
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
            behavior_identity=behavior_identity(),
            compute_identity="contract-compute-v1",
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
            behavior_identity=behavior_identity(),
            compute_identity="contract-compute-v1",
        )


def test_optional_provider_identity_matches_each_runtime_injection() -> None:
    class OptionalProviderSearch(ContractSearch):
        optional_collaborators = (CollaboratorKind.PROVIDER,)
        contract = replace(
            ContractSearch.contract,
            optional_collaborators=frozenset(optional_collaborators))

    without_provider = DecisionCoordinator(
        evaluator=Evaluator(), evaluation_model=Model(), search=OptionalProviderSearch(),
        search_configuration="contract-search-config-v1", decision_policy=Policy(),
        policy_configuration="contract-policy-config-v1",
        behavior_identity=behavior_identity(), compute_identity="contract-compute-v1")
    with pytest.raises(ValueError, match="injected provider"):
        without_provider.decide(
            OBSERVATION, provider=cast(SearchProvider, Model("provider-v1")))

    with_provider = DecisionCoordinator(
        evaluator=Evaluator(), evaluation_model=Model(), search=OptionalProviderSearch(),
        search_configuration="contract-search-config-v1", decision_policy=Policy(),
        policy_configuration="contract-policy-config-v1",
        behavior_identity=behavior_identity(provider="provider-v1"),
        compute_identity="contract-compute-v1")
    with pytest.raises(ValueError, match="injected provider"):
        with_provider.decide(OBSERVATION)


def test_coordinator_requires_every_core_component_contract() -> None:
    class UncontractedSearch:
        identity = ContractSearch.identity
        required_collaborators = ContractSearch.required_collaborators
        optional_collaborators = ContractSearch.optional_collaborators
        search = ContractSearch.search

    with pytest.raises(ValueError, match="Component Contract"):
        DecisionCoordinator(
            evaluator=Evaluator(), evaluation_model=Model(),
            search=cast(SearchAlgorithm, UncontractedSearch()),
            search_configuration="contract-search-config-v1",
            decision_policy=Policy(), policy_configuration="contract-policy-config-v1",
            behavior_identity=behavior_identity(), compute_identity="contract-compute-v1")


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
            policy_configuration="contract-policy-config-v1",
            behavior_identity=behavior_identity(), compute_identity="contract-compute-v1")


def test_coordinator_rejects_static_evidence_incompatibility() -> None:
    class EvidencePolicy(Policy):
        contract = ComponentContract(
            Policy.identity, "contract-policy-config-v1",
            required_statistics=frozenset((DELTA,)),
            required_evidence=frozenset((EvidenceIdentity("ledger", 1),)),
        )

    with pytest.raises(ValueError, match="required evidence"):
        DecisionCoordinator(
            evaluator=Evaluator(), evaluation_model=Model(), search=ContractSearch(),
            search_configuration="contract-search-config-v1",
            decision_policy=EvidencePolicy(), policy_configuration="contract-policy-config-v1",
            behavior_identity=behavior_identity(), compute_identity="contract-compute-v1")


def test_policy_failure_reaches_fail_safe_as_non_permitting_outcome() -> None:
    class RaisingPolicy(Policy):
        def choose(self, request: DecisionPolicyRequest) -> ActionChoiceIdentity:
            raise RuntimeError("policy failed")

    class FailSafe:
        identity = "contract-fail-safe-v1"
        contract = ComponentContract(
            identity, "contract-policy-config-v1",
            accepted_outcomes=frozenset((SearchOutcomeStatus.HARD_FAILURE,)),
            accepted_evidence=frozenset((None,)))

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
        behavior_identity=behavior_identity(FailSafe.identity),
        compute_identity="contract-compute-v1",
    ).decide(OBSERVATION)

    assert isinstance(result.resolution, FailSafeSelection)
    assert result.search.outcome.status is SearchOutcomeStatus.COMPLETE


def test_fail_safe_declines_undeclared_search_evidence() -> None:
    @dataclass(frozen=True)
    class Evidence:
        owner: str = "other"
        schema_version: int = 1

    class RaisingPolicy(Policy):
        def choose(self, request: DecisionPolicyRequest) -> ActionChoiceIdentity:
            raise RuntimeError("policy failed")

    class FailSafe:
        identity = "contract-fail-safe-v1"
        contract = ComponentContract(
            identity, "contract-policy-config-v1",
            accepted_outcomes=frozenset((SearchOutcomeStatus.HARD_FAILURE,)),
            accepted_evidence=frozenset((EvidenceIdentity("ledger", 1),)))

        def choose(self, request: FailSafePolicyRequest) -> ActionChoiceIdentity:
            raise AssertionError("incompatible recovery must not run")

    class ForeignEvidenceSearch(ContractSearch):
        contract = ComponentContract(
            ContractSearch.identity, "contract-search-config-v1",
            produced_statistics=frozenset((DELTA,)),
            produced_evidence=frozenset((EvidenceIdentity("other", 1),)),
        )

        def search(
                self,
                request: EvaluationRequest,
                evaluator: ValueEvaluator,
                configuration: IdentifiedConfiguration | str,
        ) -> SearchResult:
            return replace(super().search(request, evaluator, configuration), evidence=Evidence())

    result = DecisionCoordinator(
        evaluator=Evaluator(), evaluation_model=Model(), search=ForeignEvidenceSearch(),
        search_configuration="contract-search-config-v1",
        decision_policy=RaisingPolicy(), policy_configuration="contract-policy-config-v1",
        fail_safe_policy=FailSafe(),
        behavior_identity=behavior_identity(FailSafe.identity),
        compute_identity="contract-compute-v1",
    ).decide(OBSERVATION)

    assert isinstance(result.resolution, NoSelection)
    assert result.resolution.failure is not None
    assert result.resolution.failure.stage is DecisionFailureStage.POLICY
    assert result.resolution.original_outcome is result.search.outcome
    assert result.resolution.recovery_termination is not None
    assert result.resolution.recovery_termination.code == "incompatible_evidence"
