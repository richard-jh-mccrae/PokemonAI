"""Blunder round 2026-07-09 (dragapult_ex) — spend Boss's Orders on the KO, not on setup.

A PLAY that fired `gust-for-the-ko` rides tier 0. Sound because that rung's own gate proves the
gust-KO out-values every menu attack; an ordinary gust never fires it and stays at tier 4.
"""
import json
import sys
from pathlib import Path

import pytest

from poc_t4_flips import marks

REPO = Path(__file__).resolve().parents[2]


def _pilot(deck):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(deck)[0]


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json").read_text(encoding="utf-8"))


def _fired_ids(option):
    return {h.id for h, _w in option.fired}


@pytest.mark.req("REQ-GUST-0001")
@pytest.mark.xfail(strict=True, reason=marks("dragapult_poffin_whiff_take_gust_ko_f79")[0].kwargs["reason"])
def test_f79_take_the_gust_ko_over_a_whiffing_bench_fill():
    fx = _fixture("dragapult_poffin_whiff_take_gust_ko_f79")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [4] Play Boss's Orders
    # The rung-id assertion here is DELETED with its rung (Issue #386): it gave this strict xfail a
    # SECOND cause, and the recorded reason is a seam-coverage gap. One xfail, one cause.


@pytest.mark.req("REQ-GUST-0001")
@pytest.mark.xfail(strict=True, reason=marks("dragapult_gust_ko_over_accel_f81")[0].kwargs["reason"])
def test_f81_take_the_gust_ko_over_a_setup_accelerator():
    """The accel Supporter would spend the one-per-turn Supporter slot and forfeit the gust line."""
    fx = _fixture("dragapult_gust_ko_over_accel_f81")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [2] Play Boss's Orders
    # The rung-id assertion here is DELETED with its rung (Issue #386): it gave this strict xfail a
    # SECOND cause, and the recorded reason is a seam-coverage gap. One xfail, one cause.
