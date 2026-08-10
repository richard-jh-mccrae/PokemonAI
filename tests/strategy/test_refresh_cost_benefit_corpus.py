"""Issue #507 Pattern 3: a hand refresh must beat its consumed-hand cost."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
LILLIE, HARLEQUIN = 1227, 1223


def _pilot():
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot("mega_starmie")[0]


def _record(case: str):
    from corpus_helpers import corpus_record
    episode, frame = case.split("-")
    return corpus_record(episode, int(frame))


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.parametrize("case", ["85164605-64", "83969481-55"])
def test_cost_negative_lillie_loses_to_the_existing_attack(case):
    record = _record(case)
    decision = _pilot().explain(record.obs)
    lillie = next(option for option in decision.options if option.card_id == LILLIE)

    assert lillie.score < 0.0
    assert decision.chosen == record.correct


@pytest.mark.req("REQ-CORPUS-0001")
def test_positive_refresh_still_wins_when_its_expected_benefit_exceeds_cost():
    record = _record("83457493-31")
    decision = _pilot().explain(record.obs)
    harlequin = next(option for option in decision.options if option.card_id == HARLEQUIN)

    assert harlequin.score > 0.0
    assert decision.chosen == record.correct
