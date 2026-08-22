from dataclasses import dataclass

from common.decision import (
    CandidateDisposition,
    CandidateRoster,
    DecisionCoordinator,
    DecisionDelta,
    EvaluationStatus,
    SearchResult,
    StateValuation,
    ValueScale,
    ValuedCandidate,
)


SCALE = ValueScale("ledger-worth", 1)


@dataclass(frozen=True)
class Action:
    name: str


class FakeEvaluator:
    identity = "fake-evaluator"

    def __init__(self, valuation=None):
        self.valuation = valuation
        self.calls = []

    def evaluate(self, request):
        self.calls.append(request)
        return self.valuation


class FakePolicyModel:
    identity = "fake-policy-model"

    def __init__(self):
        self.calls = []

    def priors(self, state, actions):
        self.calls.append((state, actions))
        probability = 0.0 if not actions else 1.0 / len(actions)
        return tuple(probability for _action in actions)


class FakeSearch:
    identity = "fake-search"

    def __init__(self, result):
        self.result = result
        self.calls = []

    def search(self, request, evaluator, policy_model, provider, configuration):
        self.calls.append((request, evaluator, policy_model, provider, configuration))
        evaluator.evaluate(request)
        policy_model.priors(
            request.state, tuple(candidate.action for candidate in self.result.roster.candidates))
        return self.result


class FakeDecisionPolicy:
    identity = "fake-decision-policy"

    def __init__(self, chosen):
        self.chosen = chosen
        self.calls = []

    def choose(self, roster, configuration):
        self.calls.append((roster, configuration))
        return self.chosen


def test_coordinator_keeps_search_evaluation_and_policy_contracts_separate():
    attach, end = Action("attach"), Action("end")
    baseline = StateValuation("root", 2.0, SCALE, 0, "fake-evaluator")
    candidates = (
        ValuedCandidate(
            attach,
            DecisionDelta(0.5, SCALE),
            CandidateDisposition.CONTINUES_TURN,
            EvaluationStatus.COMPLETE,
        ),
        ValuedCandidate(
            end,
            DecisionDelta(0.0, SCALE),
            CandidateDisposition.ENDS_TURN,
            EvaluationStatus.COMPLETE,
        ),
    )
    search_result = SearchResult(baseline, CandidateRoster(candidates))
    search = FakeSearch(search_result)
    decision_policy = FakeDecisionPolicy(attach)
    evaluator = FakeEvaluator(baseline)
    policy_model = FakePolicyModel()
    coordinator = DecisionCoordinator(
        evaluator=evaluator,
        evaluation_model="evaluation-model",
        search=search,
        search_configuration="search-configuration",
        policy_model=policy_model,
        decision_policy=decision_policy,
        policy_configuration="policy-configuration",
    )

    result = coordinator.decide("state", provider="provider")

    assert result.chosen is attach
    assert result.baseline is baseline
    assert result.roster.candidates == candidates
    assert result.trace.chosen_action is attach
    assert result.policy_reason == "fake-decision-policy"
    request, passed_evaluator, passed_model, provider, search_config = search.calls[0]
    assert request.state == "state"
    assert request.evaluation_model == "evaluation-model"
    assert passed_evaluator is evaluator
    assert passed_model is policy_model
    assert provider == "provider"
    assert search_config == "search-configuration"
    assert decision_policy.calls == [(search_result.roster, "policy-configuration")]
    assert evaluator.calls == [request]
    assert policy_model.calls == [("state", (attach, end))]


def test_roster_rejects_duplicate_action_identity_without_dropping_candidates():
    action = Action("same")
    candidate = ValuedCandidate(
        action,
        None,
        CandidateDisposition.FORCED,
        EvaluationStatus.UNAVAILABLE,
    )

    try:
        CandidateRoster((candidate, candidate))
    except ValueError as exc:
        assert "duplicate candidate action" in str(exc)
    else:
        raise AssertionError("duplicate candidate accepted")
