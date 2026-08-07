"""Blunder round 2026-07-09 (mega_starmie) — REFUTED-CRITICAL regression gates (/blunder-buster).

Two corrections this round carried the uppercase CRITICAL marker at the SAME turn (ep83966968 T10)
and BOTH were refuted: they rest on KOing the opponent's benched Mega Starmie ex line, which our
Active cannot reach this turn. Our Active (Mega Starmie ex, 1 Energy attached) has Jetting Blow
(cost 1, 120 dmg — the only affordable attack) and Nebula Beam (cost 3, 210 dmg — unaffordable: 1
attached + 1 attach/turn = 2). The benched Mega Starmie ex is at 230/330 HP: 120 < 230 and even a
fully-powered 210 < 230, so it is UN-KO-able. The only KO on the board is the benched Cinderace
(Fire, weak ×2 → Jetting Blow 120×2 = 240 ≥ 110). Prizes: we had 6 remaining (behind; opp 4), so no
"skip the small KO to win directly" shortcut applied either. The agent's line — Boss's Orders → gust
Cinderace → KO for 1 prize + strip their energy accelerator — is correct. Human ack 2026-07-09.

These tests pin that the SHIPPED Pilot keeps making the correct call, so a future gust/snipe change
can't silently regress into forgoing the only KO for an unreachable target. See
tests/fixtures/corrections/ms0705_*.json and [[forgo-ko-corrections-are-refuted]].
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
    """REFUTED CRITICAL ('KOing a Cinderace does not help us … KO the Mega Starmie instead'): at the
    Boss's-Orders SWITCH select the agent drags up Cinderace (the ONLY KO-able target: 120×2 weakness
    = 240 ≥ 110) rather than the benched Mega Starmie ex (230/330 HP, un-KO-able — max 210 < 230).
    Gusting the Mega would forgo the only prize for a 120 chip they retreat away."""
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
    """REFUTED CRITICAL ('evolve our benched Staryu … play Harlequin'): with the Cinderace gust-KO the
    only KO on the board (f79), Boss's Orders is the correct Supporter. Harlequin (shuffle + coin-flip
    dig for an evolution piece we don't hold) would forgo that guaranteed 1-prize KO. The shipped Pilot
    keeps Boss's Orders — a positional/dig rule must never override a KO."""
    fx = _fixture("ms0705_bosss_over_harlequin_f78")
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["agent_choice"]          # play Boss's Orders [12], NOT Harlequin [2]
    assert dec.chosen != fx["human_wanted"]
