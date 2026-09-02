import json

import pytest

from common.decision import EvaluationStatus
from common.ledger import LedgerPolicyConfiguration
from common.ledger.policy import normalize_ledger_priors
from train.policy_calibrate import _loss, _priors


def row(deck="dragapult_ex"):
    return {
        "deck": deck,
        "graded": True,
        "chosen": [0],
        "acceptable": [[0]],
        "candidates": [
            {"selection": [0], "equivalent_selections": [],
             "status": "complete", "decision_delta": 2.0},
            {"selection": [1], "equivalent_selections": [],
             "status": "complete", "decision_delta": 0.0},
        ],
    }


def test_policy_calibration_scores_the_acceptable_action():
    assert _loss((row(),), 1.0, 0.1) < _loss((row(),), 4.0, 0.5)


def test_policy_calibration_smoke_falls_back_for_estimated_evidence():
    sample = json.loads(json.dumps(row()))
    sample["candidates"][1]["status"] = "estimated"

    assert _priors(sample, 1.0, 0.1) == (0.5, 0.5)


def test_policy_calibration_uses_runtime_normalization_semantics():
    configuration = LedgerPolicyConfiguration(1.0, 0.1)

    runtime = normalize_ledger_priors(
        (2.0, 0.0),
        (EvaluationStatus.COMPLETE, EvaluationStatus.COMPLETE),
        configuration,
    )

    assert _priors(row(), 1.0, 0.1) == runtime.priors


@pytest.mark.parametrize(("temperature", "mix"), ((0.25, 0.01), (16.0, 0.5)))
def test_policy_calibration_priors_remain_normalized(temperature, mix):
    priors = _priors(row(), temperature, mix)

    assert sum(priors) == pytest.approx(1.0)
    assert all(prior > 0.0 for prior in priors)
