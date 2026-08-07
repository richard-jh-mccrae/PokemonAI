"""Correction pins for the deferred-proposal clean-up round (2026-07-14).

The strategy-ingest / blunder deferrals that turned out to be BUILDABLE (opponent-model infra had
landed) or ALREADY-COVERED are drained here. These two are the correction-backed ones — they must flip
(or hold) a real fixture, so each re-derives the tagged decision through the REAL engine-backed Pilot and
asserts the human's `correct` option is chosen (the same harness as tests/strategy/test_blunder_*.py).

The opponent-model-driven cluster (disrupt-the-tailored-hand, unfair-stamp-comeback-posture,
play-safe-when-ahead-on-prizes, dont-spend-unneeded-supporter, and the planner opponent-read consumers)
ships weight-0 / kill-switched-OFF pending ladder validation — those are trigger-tested in
tests/strategy/test_deferred_{disruption,posture,planner}_cluster.py, not scored here.
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
    """ms 85164605 f6: turn-1 Mega Signal tutors a Mega Starmie ex with NO Staryu base anywhere (and it
    cannot fetch one), so the fetched wincon sits dead — attach the {W} to the Cinderace accelerator
    instead. The new `dont-tutor-the-baseless-wincon-turn-one` (-55) cancels the +53 free-dig stack,
    driving Mega Signal to score <=0 so `_finish_turn_last` drops it to tier 4 (behind the tier-2 attach)
    — merely beating the attach on score is not enough (a free PLAY at score>0 stays tier 0)."""
    fx = _fixture("ms_premature_wincon_tutor_no_base_f6")
    d = starmie.explain(fx["obs"])
    assert d.chosen == fx["correct"]
    assert d.options[fx["chosen"][0]].score <= 0, "the baseless tutor must be driven <=0 (tier 4)"


# POC-T4/5: this frame FLIPPED BACK, and it is the most interesting of the three. It was a
# REFUSAL row — the seam cannot prove Lunar Cycle deterministic — and it resolved with NO
# widening of the seam at all. The refused option was never the problem; the composer
# committing a line it had no view on was (`planner._tied_first_steps`).
def test_lunar_cycle_beats_the_inert_bench_attach_f16(lucario):
    """ml 85058574 f16 (deferred `lunar-cycle-beats-an-inert-bench-attach`, now COVERED): the lone {F}
    was being spent on a benched Solrock (`attach-solrock-over-line-base`) that will not attack this turn,
    while the weak-preevo Riolu Active makes Lunar Cycle (draw 3) the better spend. Already satisfied by
    the applied `lunar-cycle-the-weak-preevo-last-f` (+30) — pinned here so the coverage cannot regress."""
    fx = _fixture("ml_lunar_cycle_over_inert_bench_attach_f16")
    d = lucario.explain(fx["obs"])
    assert d.chosen == fx["correct"]
