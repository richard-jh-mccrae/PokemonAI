"""Blunder round 2026-07-09 (dragapult_ex) — play-energy-denial: threat- and KO-aware gating.

Two gates separate a worthwhile strip from a wasted Item: `opp_active_can_damage_us`, and a KO
stand-down keyed on `active_can_ko` (BEST affordable attack) rather than the cheapest.
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


@pytest.mark.req("REQ-GEN-0031")
@pytest.mark.xfail(strict=True, reason=marks("dragapult_hammer_no_threat_f6")[0].kwargs["reason"])
def test_f6_hold_the_hammer_vs_a_harmless_conditional_attacker():
    """The opponent's only affordable attack scales off an EMPTY discard, so it computes to 0 damage
    and `opp_active_can_damage_us` is False."""
    fx = _fixture("dragapult_hammer_no_threat_f6")
    dec = _pilot("dragapult_ex").explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # [2] Poké Pad, not [1] Crushing Hammer
    assert "play-energy-denial" not in _fired_ids(dec.options[1])   # the Hammer no longer endorsed
