"""Blunder round 2026-07-09 (dragapult_ex) — spend Boss's Orders on the KO, not on setup.

Proposal `spend-boss-orders-on-the-ko-not-setup` (data/strategy/proposals/blunder-20260709-dragapult_ex.md).
`gust-for-the-ko` (+50) fires ONLY when the gust-KO takes MORE prizes than any menu attack
(`gust_best_ko_prizes > active_ko_prizes`), yet `_finish_turn_last` tiered a KO-enabling gust behind
tier-0/1 setup plays — a bench-fill Poffin (f79) and an accel Crispin (f81) — forfeiting the premium gust.
Fix: a PLAY that fired `gust-for-the-ko` rides tier 0, so the agent takes the gust-setup first, then KOs
the dragged-up body. Sound because the rung's own gate proves the gust-KO out-values every menu attack
(the ep83456015 f38 concern — a bigger menu KO — never triggers `gust-for-the-ko`, so an ordinary gust
still sits at tier 4).

f10 (the inverse — a valueless setup stall-gust) and the Poffin-whiff guard are SPLIT OUT to their own
proposal (distinct mechanisms, tangled with the famine-gust tiering / the whiff-guard infra).
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
    """CRITICAL f79: with Dragapult ex online, `gust-for-the-ko` (+50) on Boss's Orders now rides tier 0,
    beating the tier-0 Buddy-Buddy Poffin bench-fill (35) — gust the KO instead of a setup Item."""
    fx = _fixture("dragapult_poffin_whiff_take_gust_ko_f79")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [4] Play Boss's Orders
    assert "gust-for-the-ko" in _fired_ids(dec.options[fx["correct"][0]])


@pytest.mark.req("REQ-GUST-0001")
@pytest.mark.xfail(strict=True, reason=marks("dragapult_gust_ko_over_accel_f81")[0].kwargs["reason"])
def test_f81_take_the_gust_ko_over_a_setup_accelerator():
    """f81: Boss's Orders (`gust-for-the-ko` +50) rides tier 0 ahead of the tier-1 accel Supporter Crispin
    (+45), which would otherwise spend the one-Supporter-per-turn slot and forfeit the 2-prize gust line."""
    fx = _fixture("dragapult_gust_ko_over_accel_f81")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                         # [2] Play Boss's Orders
    assert "gust-for-the-ko" in _fired_ids(dec.options[fx["correct"][0]])
