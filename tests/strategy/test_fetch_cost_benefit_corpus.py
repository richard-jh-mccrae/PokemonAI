"""Issue #507 Pattern 2: generic fetch targets and fetch plays have cost-benefit value."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]

STARYU, MEGA_STARMIE, WATER = 1030, 1031, 3
NIGHT_STRETCHER, MEGA_SIGNAL, SALVATORE, HILDA = 1097, 1145, 1189, 1225


def _record(case: str):
    from corpus_helpers import corpus_record
    episode, frame = case.split("-")
    return corpus_record(episode, int(frame))


def _pilot():
    spec = importlib.util.spec_from_file_location(
        "tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot("mega_starmie")[0]


@pytest.mark.parametrize(("case", "target"), [
    ("81903490-8", MEGA_STARMIE),
    ("81903490-93", WATER),
    ("82228640-9", STARYU),
    ("82749656-21", STARYU),
    ("82753102-17", STARYU),
])
def test_fetch_target_uses_marginal_need_value(case, target):
    rec = _record(case)
    decision = _pilot().explain(rec.obs)

    assert decision.options[rec.correct[0]].card_id == target
    assert decision.options[rec.correct[0]].score > 0.0
    assert decision.chosen == rec.correct


@pytest.mark.parametrize(("case", "card_id", "sign"), [
    ("81904451-15", HILDA, 1),
    ("82749168-21", SALVATORE, -1),
    ("83038055-40", MEGA_SIGNAL, -1),
    ("83665798-12", MEGA_SIGNAL, -1),
    ("83667237-120", NIGHT_STRETCHER, 1),
    ("83667237-87", NIGHT_STRETCHER, 1),
])
def test_fetch_play_nets_delivered_need_against_card_cost(case, card_id, sign):
    rec = _record(case)
    decision = _pilot().explain(rec.obs)
    trace = next(option for option in decision.options if option.card_id == card_id)

    assert trace.tactical * sign > 0.0


@pytest.mark.parametrize("case", [
    "81904451-15",
    "83038055-40",
    "83667237-120",
    "83667237-87",
])
def test_fetch_cost_benefit_survives_main_sequence_planning(case):
    rec = _record(case)

    assert _pilot().explain(rec.obs).chosen == rec.correct
