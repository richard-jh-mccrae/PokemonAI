from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
import json
from pathlib import Path

import pytest

from common.api import ActionIdentity
from common.decision import (
    CandidateDisposition,
    CandidateRoster,
    DecisionDelta,
    EvaluationStatus,
    PolicyFallbackReason,
    PolicyRequest,
    PolicyDistribution,
    PolicySourceIdentity,
    ValueScale,
    ValuedCandidate,
)
from common.ledger import (
    LedgerPolicyBaseline,
    LedgerPolicyConfiguration,
    LedgerPolicyModel,
    UniformPolicyModel,
)
from common.observation import ObservationStateBuilder
from ledger_helpers import DARK_E, DRAGAPULT, body, player, printout


SCALE = ValueScale("ledger-worth", 1)
SOURCE = PolicySourceIdentity("frozen-v1", "evaluator-v1", "model-v1", SCALE.identity)
BASELINE = LedgerPolicyBaseline(
    "frozen-v1", "evaluator-v1", ("model-v1",), SCALE.identity)
DECK = (DRAGAPULT, DARK_E) * 30
OBSERVATION = ObservationStateBuilder(DECK).root(
    printout(me=player(active=body(DRAGAPULT, 1))))


@dataclass(frozen=True)
class Action:
    identity: ActionIdentity
    selection: tuple[int, ...]


def roster(*deltas: float) -> CandidateRoster:
    actions = tuple(Action(ActionIdentity("action", (str(index),)), (index,))
                    for index in range(len(deltas)))
    candidates = tuple(ValuedCandidate(
        action,
        DecisionDelta(delta, SCALE),
        CandidateDisposition.CONTINUES_TURN,
        EvaluationStatus.COMPLETE,
    ) for action, delta in zip(actions, deltas))
    return CandidateRoster.from_legal_actions(actions, candidates)


def mixed_roster(*items, forced=False) -> CandidateRoster:
    actions = tuple(Action(ActionIdentity("action", (str(index),)), (index,))
                    for index in range(len(items)))
    candidates = tuple(ValuedCandidate(
        action,
        None if delta is None else DecisionDelta(delta, SCALE),
        CandidateDisposition.FORCED if forced else CandidateDisposition.CONTINUES_TURN,
        status,
    ) for action, (delta, status) in zip(actions, items))
    return CandidateRoster.from_legal_actions(actions, candidates, forced=forced)


def test_ledger_policy_softens_canonical_deltas_without_excluding_actions():
    candidates = roster(2.0, 0.0)
    model = LedgerPolicyModel(
        LedgerPolicyConfiguration(temperature=1.0, uniform_mix=0.2),
        BASELINE,
    )

    distribution = model.priors(PolicyRequest(OBSERVATION, candidates, SOURCE))

    assert tuple(item.raw_delta for item in distribution.actions) == (2.0, 0.0)
    assert tuple(item.normalized_score for item in distribution.actions) == pytest.approx(
        (0.8807970779778823, 0.11920292202211755))
    assert tuple(item.final_prior for item in distribution.actions) == pytest.approx(
        (0.8046376623823059, 0.19536233761769405))
    assert distribution.actual_floor == pytest.approx(0.19536233761769405)
    assert distribution.source == SOURCE


def test_uniform_policy_uses_the_same_evidenced_distribution_contract():
    candidates = roster(-4.0, 9.0)

    distribution = UniformPolicyModel().priors(PolicyRequest(OBSERVATION, candidates, SOURCE))

    assert tuple(item.raw_delta for item in distribution.actions) == (-4.0, 9.0)
    assert tuple(item.final_prior for item in distribution.actions) == (0.5, 0.5)
    assert distribution.fallback_reason.value == "requested_uniform"
    assert distribution.temperature is None
    assert distribution.uniform_mix == 1.0


def test_policy_distribution_round_trips_hidden_safe_evidence():
    candidates = roster(2.0, -1.0)
    model = LedgerPolicyModel(
        LedgerPolicyConfiguration(temperature=2.0, uniform_mix=0.1),
        BASELINE,
    )
    distribution = model.priors(PolicyRequest(OBSERVATION, candidates, SOURCE))

    restored = PolicyDistribution.from_dict(
        json.loads(json.dumps(distribution.as_dict(), sort_keys=True)))

    assert restored == distribution
    assert restored.priors_for(candidates) == pytest.approx(
        tuple(item.final_prior for item in distribution.actions))


def test_ledger_policy_is_repeatable_across_thread_workers():
    candidates = roster(2.0, -1.0)
    request = PolicyRequest(OBSERVATION, candidates, SOURCE)
    model = LedgerPolicyModel(
        LedgerPolicyConfiguration(temperature=2.0, uniform_mix=0.1), BASELINE)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = tuple(workers.map(model.priors, (request, request)))

    assert results[0] == results[1] == model.priors(request)


@pytest.mark.parametrize(("deltas", "expected"), (
    ((-7.0, -7.0), (0.5, 0.5)),
    ((10_000.0, -10_000.0), (0.95, 0.05)),
))
def test_ledger_policy_is_stable_for_ties_negative_values_and_wide_ranges(
        deltas, expected):
    distribution = LedgerPolicyModel(
        LedgerPolicyConfiguration(temperature=1.0, uniform_mix=0.1), BASELINE,
    ).priors(PolicyRequest(OBSERVATION, roster(*deltas), SOURCE))

    assert tuple(item.final_prior for item in distribution.actions) == pytest.approx(expected)


def test_forced_unpriced_action_receives_probability_one():
    candidates = mixed_roster((None, EvaluationStatus.UNAVAILABLE), forced=True)

    distribution = LedgerPolicyModel(
        LedgerPolicyConfiguration(temperature=1.0, uniform_mix=0.1), BASELINE,
    ).priors(PolicyRequest(OBSERVATION, candidates, SOURCE))

    assert distribution.actions[0].final_prior == 1.0
    assert distribution.actions[0].raw_delta is None
    assert distribution.fallback_reason is None


@pytest.mark.parametrize(("items", "accepted", "reason"), (
    (((1.0, EvaluationStatus.COMPLETE), (None, EvaluationStatus.UNAVAILABLE)),
     (EvaluationStatus.COMPLETE, EvaluationStatus.ESTIMATED), "unavailable_candidate"),
    (((1.0, EvaluationStatus.COMPLETE), (0.5, EvaluationStatus.ESTIMATED)),
     (EvaluationStatus.COMPLETE,), "unaccepted_status"),
))
def test_non_comparable_candidate_falls_back_the_entire_roster(
        items, accepted, reason):
    candidates = mixed_roster(*items)
    configuration = LedgerPolicyConfiguration(
        temperature=1.0, uniform_mix=0.1, accepted_statuses=accepted)

    distribution = LedgerPolicyModel(configuration, BASELINE).priors(
        PolicyRequest(OBSERVATION, candidates, SOURCE))

    assert tuple(item.final_prior for item in distribution.actions) == (0.5, 0.5)
    assert distribution.fallback_reason.value == reason
    assert {item.fallback_reason.value for item in distribution.actions} == {reason}


@pytest.mark.parametrize(("temperature", "uniform_mix"), (
    (0.0, 0.1),
    (-1.0, 0.1),
    (float("nan"), 0.1),
    (float("inf"), 0.1),
    (1.0, 0.0),
    (1.0, 1.0),
    (1.0, float("nan")),
))
def test_ledger_policy_configuration_rejects_invalid_normalization(
        temperature, uniform_mix):
    with pytest.raises(ValueError):
        LedgerPolicyConfiguration(temperature=temperature, uniform_mix=uniform_mix)


def test_ledger_policy_configuration_identity_ignores_status_order():
    first = LedgerPolicyConfiguration(
        temperature=1.0, uniform_mix=0.1,
        accepted_statuses=(EvaluationStatus.COMPLETE, EvaluationStatus.ESTIMATED))
    second = LedgerPolicyConfiguration(
        temperature=1.0, uniform_mix=0.1,
        accepted_statuses=(EvaluationStatus.ESTIMATED, EvaluationStatus.COMPLETE))

    assert first == second
    assert first.identity == second.identity


def test_estimated_candidate_requires_explicit_opt_in():
    candidates = mixed_roster(
        (1.0, EvaluationStatus.COMPLETE),
        (0.5, EvaluationStatus.ESTIMATED),
    )

    default = LedgerPolicyModel(
        LedgerPolicyConfiguration(temperature=1.0, uniform_mix=0.1), BASELINE,
    ).priors(PolicyRequest(OBSERVATION, candidates, SOURCE))
    opted_in = LedgerPolicyModel(
        LedgerPolicyConfiguration(
            temperature=1.0,
            uniform_mix=0.1,
            accepted_statuses=(EvaluationStatus.COMPLETE, EvaluationStatus.ESTIMATED),
        ),
        BASELINE,
    ).priors(PolicyRequest(OBSERVATION, candidates, SOURCE))

    assert default.fallback_reason is PolicyFallbackReason.UNACCEPTED_STATUS
    assert opted_in.fallback_reason is None
    assert opted_in.actions[0].final_prior > opted_in.actions[1].final_prior


@pytest.mark.parametrize(("field", "value", "message"), (
    ("baseline_identity", "other", "baseline"),
    ("evaluator_identity", "other", "evaluator"),
    ("evaluation_model_identity", "other", "Evaluation Model"),
    ("value_scale_identity", "other", "Value Scale"),
))
def test_ledger_policy_rejects_p0_v0_identity_mismatch(field, value, message):
    model = LedgerPolicyModel(
        LedgerPolicyConfiguration(temperature=1.0, uniform_mix=0.1), BASELINE)

    with pytest.raises(ValueError, match=message):
        model.priors(PolicyRequest(
            OBSERVATION, roster(1.0, 0.0), replace(SOURCE, **{field: value})))


def test_policy_request_requires_a_nonempty_proven_roster():
    candidates = roster(1.0).candidates

    with pytest.raises(ValueError, match="proven legal"):
        PolicyRequest(OBSERVATION, CandidateRoster(candidates), SOURCE)
    with pytest.raises(ValueError, match="requires a candidate"):
        PolicyRequest(OBSERVATION, CandidateRoster((), legal_actions_proven=True), SOURCE)


def test_ledger_policy_loads_the_committed_frozen_baseline():
    repository = Path(__file__).resolve().parents[2]
    manifests = tuple((repository / "data" / "ledger-baselines").glob("*/manifest.json"))

    assert len(manifests) == 1
    baseline = LedgerPolicyBaseline.load(manifests[0].parent.name, manifests[0])
    assert baseline.baseline_identity == manifests[0].parent.name
    assert baseline.evaluator_identity
    assert baseline.evaluation_model_identities


def test_committed_calibration_matches_the_frozen_baseline_without_heldout_data():
    repository = Path(__file__).resolve().parents[2]
    baseline_identity = next(
        (repository / "data" / "ledger-baselines").iterdir()).name
    path = (repository / "data" / "ledger-policy-calibrations"
            / f"{baseline_identity}.json")

    configuration = LedgerPolicyConfiguration.load_calibrated(baseline_identity, path)
    artifact = json.loads(path.read_text(encoding="utf-8"))

    assert configuration.identity == "6f822dc74c2655c5"
    assert configuration.accepted_statuses == (EvaluationStatus.COMPLETE,)
    assert artifact["heldout"] == {"consumed": False, "paths": []}
    assert set(artifact["deck_smoke"]) == {
        "dragapult_ex", "mega_lucario", "mega_starmie"}
    assert all(result["all_priors_finite_normalized_nonzero"]
               for result in artifact["deck_smoke"].values())
    assert sum(result["live_greedy_disagreements"]
               for result in artifact["deck_smoke"].values()) > 0


def test_policy_distribution_decoder_rejects_unknown_fields():
    candidates = roster(1.0, 0.0)
    distribution = UniformPolicyModel().priors(
        PolicyRequest(OBSERVATION, candidates, SOURCE)).as_dict()
    distribution["invented"] = True

    with pytest.raises(ValueError, match="invalid policy distribution fields"):
        PolicyDistribution.from_dict(distribution)


def test_policy_request_rejects_non_observation_state():
    with pytest.raises(TypeError, match="Observation State"):
        PolicyRequest(object(), roster(1.0), SOURCE)


def test_ledger_policy_rejects_candidate_value_scale_mismatch():
    action = Action(ActionIdentity("action"), (0,))
    candidate = ValuedCandidate(
        action,
        DecisionDelta(1.0, ValueScale("other", 1)),
        CandidateDisposition.CONTINUES_TURN,
        EvaluationStatus.COMPLETE,
    )
    candidates = CandidateRoster.from_legal_actions((action,), (candidate,))
    model = LedgerPolicyModel(
        LedgerPolicyConfiguration(temperature=1.0, uniform_mix=0.1), BASELINE)

    with pytest.raises(ValueError, match="candidate Value Scale"):
        model.priors(PolicyRequest(OBSERVATION, candidates, SOURCE))
