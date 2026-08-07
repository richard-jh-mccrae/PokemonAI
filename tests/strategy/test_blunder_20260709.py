"""Blunder round 2026-07-09 (mega_starmie) — REFUTED-CRITICAL regression gates.

Both corrections were REFUTED (human ack 2026-07-09): they ask for a KO on an un-KO-able target while
the agent's line takes the board's only real KO. A gust/snipe change must not regress into forgoing
it. See `tests/fixtures/corrections/ms0705_*.json`.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot():
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_starmie")
    return pilot


def _fixture(name):
    p = REPO / "tests" / "fixtures" / "corrections" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.mark.req("REQ-GEN-0068")
def test_critical_f79_gust_the_only_ko_not_the_unreachable_mega():
    """Cinderace is the ONLY KO-able target (120x2 weakness = 240 >= 110); the benched Mega at 230/330
    is out of reach even fully powered (210 < 230)."""
    fx = _fixture("ms0705_gust_cinderace_only_ko_f79")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["agent_choice"]          # gust Cinderace [0], NOT the Mega Starmie ex [1]
    assert dec.chosen != fx["human_wanted"]


@pytest.mark.req("REQ-GEN-0068")
@pytest.mark.xfail(strict=True, reason=(
    "POC-T4/5 flip (Issue #386) on a REFUTED correction, which is why it is inline rather than "
    "a `poc_t4_flips.FLIPS` row: this fixture carries `agent_choice`/`human_wanted` and no "
    "`correct`, so the table's ruling guard has nothing to resolve. The refutation is the "
    "ruling — the agent's Boss’s Orders line [12] was judged CORRECT and the human's Harlequin "
    "[2] wrong. The composer now plays [5], which is neither. A frame the agent had RIGHT and "
    "no longer does, so it is the sharpest kind of regression this table holds"))
def test_critical_f78_take_the_gust_ko_over_a_speculative_refresh():
    """A positional/dig rule must never override a KO."""
    fx = _fixture("ms0705_bosss_over_harlequin_f78")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["agent_choice"]          # play Boss's Orders [12], NOT Harlequin [2]
    assert dec.chosen != fx["human_wanted"]
