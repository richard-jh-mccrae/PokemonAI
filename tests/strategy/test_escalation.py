"""Tier 6 — Escalation Search (ADR-0043): the budgeted depth-2 tree for the opponent-CHOICE residue.

The trigger (`_close_attack_tie`) and the gating are pure and unit-tested here; the two-ply engine
sim is exercised end-to-end by the engine-backed planner suite (it shares `_simulate_line`).
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


def _shipped_pilot(agent="mega_starmie"):
    from train.tune import _build_pilot
    pilot, _ = _build_pilot(agent)
    return pilot


class _Trace:
    def __init__(self, tactical):
        self.tactical = tactical


@pytest.mark.req("REQ-ESCALATE-0001")
def test_close_attack_tie_detects_only_genuine_ties():
    """Two attacks within _ESCALATE_EPS are a tie to break; a clear leader, a lone attack, and a
    KO-on-the-menu (KO_SCORE-class — nothing to escalate) all yield no tie."""
    from common.strategy.context import _ATTACK, _PLAY, KO_SCORE
    pilot = _shipped_pilot()
    opts = [{"type": _ATTACK}, {"type": _ATTACK}, {"type": _PLAY}]
    # within ε → both attacks tied
    assert set(pilot._close_attack_tie(opts, [_Trace(200), _Trace(190), _Trace(0)])) == {0, 1}
    # clear leader (> ε apart) → no tie
    assert pilot._close_attack_tie(opts, [_Trace(200), _Trace(120), _Trace(0)]) == []
    # a KO on the menu → dominates, nothing to escalate
    assert pilot._close_attack_tie(opts, [_Trace(KO_SCORE + 2), _Trace(KO_SCORE), _Trace(0)]) == []
    # a single attack → no tie
    assert pilot._close_attack_tie([{"type": _ATTACK}, {"type": _PLAY}], [_Trace(200), _Trace(9)]) == []


@pytest.mark.req("REQ-ESCALATE-0002")
def test_escalation_defers_when_off_or_no_budget():
    """The escalation stands down (returns None) when the switch is off, when no search budget is
    set, or when the observation carries no search input — the tuned scoring owns the decision."""
    pilot = _shipped_pilot()
    obs = {"current": {"players": []}}                   # no search_begin_input
    board = object()
    # switch off (default) → None even with a budget
    pilot.search_budget = 50
    assert pilot._escalate(obs, {}, board, [], []) is None
    # switch on but no search input on obs → None
    pilot.escalation = True
    assert pilot._escalate(obs, {}, board, [], []) is None
    # switch on, has input, but budget 0 → None
    pilot.search_budget = 0
    assert pilot._escalate({"search_begin_input": {}}, {}, board, [], []) is None


@pytest.mark.req("REQ-ESCALATE-0003")
def test_escalation_off_by_default_on_the_shipped_pilot():
    """The shipped Pilot ships with escalation OFF and no search budget — a Tier-6 seam gates on its
    own ladder A/B before shipping (like the value model), so the default agent never pays the tree."""
    pilot = _shipped_pilot()
    assert pilot.escalation is False and pilot.search_budget == 0
