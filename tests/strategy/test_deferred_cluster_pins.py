"""Correction pins for the deferred-proposal clean-up round.

The two correction-backed deferrals: each re-derives its tagged decision through the REAL
engine-backed Pilot and asserts the human's `correct` option is chosen. The opponent-model-driven
cluster ships weight-0 / kill-switched-OFF and is trigger-tested in
`test_deferred_{disruption,posture,planner}_cluster.py` instead.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from poc_t4_flips import marks

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def starmie():
    return _pilot("mega_starmie")


@pytest.fixture(scope="module")
def lucario():
    return _pilot("mega_lucario")


def test_dont_tutor_the_baseless_wincon_turn_one_f6(starmie):
    """The tutored wincon has no base anywhere, so it sits dead. Beating the attach on score is not
    enough — a free PLAY at score > 0 stays tier 0, so the tutor must be driven <= 0."""
    fx = _fixture("ms_premature_wincon_tutor_no_base_f6")
    d = starmie.explain(fx["obs"])
    assert d.chosen == fx["correct"]
    assert d.options[fx["chosen"][0]].score <= 0, "the baseless tutor must be driven <=0 (tier 4)"


def test_lunar_cycle_beats_the_inert_bench_attach_f16(lucario):
    """Immutable human ruling retained for adjudication: the closed-form route is now scored, but
    the composer still prefers the attach. This is inherited from Issue #468, not a direct rung test."""
    fx = _fixture("ml_lunar_cycle_over_inert_bench_attach_f16")
    assert lucario.explain(fx["obs"]).chosen == fx["correct"]
