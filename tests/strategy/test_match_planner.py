"""S2 — the Match Planner (ADR-0045): `plan_match` produces the Game Plan (route + mode + confidence +
directed Turn Goal), computed first each turn and emitted for the blunder-buster.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot(agent="mega_starmie"):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot(agent)
    return pilot


@pytest.mark.req("REQ-MATCH-0001")
def test_plan_enum_grows_to_the_six_modes():
    from common.strategy.strategy import Plan
    assert {p.name for p in Plan} == {"SETUP", "RACE", "STALL", "STABILIZE", "SACRIFICE", "CLOSE"}


def _obs(me, opp, turn=6):
    return {"current": {"yourIndex": 0, "turn": turn, "players": [me, opp]}}


def _E(n):
    """``n`` attached Energy as the engine gives them: bare card ids. A dict shape survives only
    while every reader takes ``len()``; a typed read finds an unhashable dict."""
    return [1] * n


@pytest.mark.req("REQ-MATCH-0002")
def test_plan_match_returns_a_game_plan_with_a_mode_and_bounded_confidence():
    from common.strategy.strategy import GamePlan, Plan
    pilot = _shipped_pilot()
    me = {"active": [{"id": 1031, "hp": 330, "energies": _E(3)}], "bench": [], "hand": [], "prize": [None] * 6}
    opp = {"active": [{"id": 676, "hp": 110, "energies": []}], "bench": [], "prize": [None] * 6, "hand": []}
    board = pilot._board(_obs(me, opp))
    gp = pilot.plan_match(_obs(me, opp), board)
    assert isinstance(gp, GamePlan)
    assert isinstance(gp.mode, Plan)
    assert 0.0 <= gp.confidence <= 1.0


@pytest.mark.req("REQ-MATCH-0003")
def test_plan_confidence_rises_with_race_margin_and_survival_and_clamps():
    from common.strategy.objectives import plan_confidence
    assert plan_confidence(0, 1) == pytest.approx(0.5)
    assert plan_confidence(2, 1) > plan_confidence(0, 1)        # ahead in the race → more confident
    assert plan_confidence(0, 5) > plan_confidence(0, 1)        # survives longer → more confident
    assert plan_confidence(-3, 1) < 0.5                         # behind → less confident
    assert 0.0 <= plan_confidence(-99, None) <= 1.0
    assert 0.0 <= plan_confidence(99, 99) <= 1.0


@pytest.mark.req("REQ-MATCH-0004")
def test_derive_mode_sacrifice_when_doomed_with_a_ready_backup():
    from common.pilot import Board
    from common.strategy.strategy import Plan
    pilot = _shipped_pilot()
    assert pilot._derive_mode(Board(phase=Plan.STABILIZE, bench_wincon_ready=True,
                                    race_ahead=0.0)) is Plan.SACRIFICE
    assert pilot._derive_mode(Board(phase=Plan.STABILIZE, bench_wincon_ready=False,
                                    race_ahead=0.0)) is Plan.STABILIZE


@pytest.mark.req("REQ-MATCH-0005")
def test_derive_mode_stall_when_clearly_ahead_and_wincon_offline():
    from common.pilot import Board
    from common.strategy.strategy import Plan
    pilot = _shipped_pilot()
    assert pilot._derive_mode(Board(phase=Plan.RACE, line_ready=False, race_ahead=3.0)) is Plan.STALL
    assert pilot._derive_mode(Board(phase=Plan.RACE, line_ready=True, race_ahead=3.0)) is Plan.RACE


@pytest.mark.req("REQ-MATCH-0006")
def test_directed_goal_maps_from_mode_and_is_withheld_on_low_confidence():
    """Withheld, the Pilot defers to the Turn Planner + weights."""
    from common.pilot import Board
    from common.strategy.objectives import _MATCH_CONFIDENCE_MIN
    from common.strategy.strategy import Plan
    pilot = _shipped_pilot()
    me = {"active": [{"id": 1031, "hp": 330, "energies": _E(3)}], "bench": [], "hand": [], "prize": [None] * 6}
    opp = {"active": [{"id": 676, "hp": 110, "energies": []}], "bench": [], "prize": [None] * 6, "hand": []}
    obs = _obs(me, opp)
    behind = pilot.plan_match(obs, Board(phase=Plan.RACE, race_ahead=-5.0, my_path_turns=9.0))
    assert behind.confidence < _MATCH_CONFIDENCE_MIN and behind.directed_goal is None
    ahead = pilot.plan_match(obs, Board(phase=Plan.RACE, race_ahead=5.0, my_path_turns=3.0, line_ready=True))
    assert ahead.confidence >= _MATCH_CONFIDENCE_MIN and ahead.directed_goal == "ko_on_path"


@pytest.mark.req("REQ-MATCH-0007")
def test_board_carries_the_game_plan():
    pilot = _shipped_pilot()
    me = {"active": [{"id": 1031, "hp": 330, "energies": _E(3)}], "bench": [], "hand": [], "prize": [None] * 6}
    opp = {"active": [{"id": 676, "hp": 110, "energies": []}], "bench": [], "prize": [None] * 6, "hand": []}
    board = pilot._board(_obs(me, opp))
    assert board.game_plan is not None and board.game_plan.mode is not None


@pytest.mark.req("REQ-MATCH-0007")
def test_game_plan_rides_the_decision_and_telemetry_blunder_buster_parseable():
    """`/blunder-buster` parses this out of a ladder correction's live_trace."""
    import json

    from common.telemetry import to_record
    fx = json.loads((REPO / "tests" / "fixtures" / "corrections" / "planner_a21472.json")
                    .read_text(encoding="utf-8"))
    pilot = _shipped_pilot()
    decision = pilot.explain(fx["obs"])
    assert decision.game_plan is not None
    assert {"mode", "conf", "goal"} <= set(decision.game_plan)
    rec = to_record(decision, tier=0)
    assert rec["game_plan"] == decision.game_plan


# --------------------------------------------------------------- S3: the directed-goal seam (planner)

@pytest.mark.req("REQ-MATCH-0008")
def test_gameplan_goal_bonus_is_confidence_scaled_and_switch_gated():
    """`match_planner_steer` defaults OFF. `survive` was DROPPED from `_GOAL_LINE`, not left mapping
    to the empty set — mapped to nothing, this test passes while asserting a bump nothing can pay."""
    from common.pilot import Board
    from common.strategy.strategy import GamePlan, Plan
    pilot = _shipped_pilot()
    board = Board(game_plan=GamePlan(mode=Plan.RACE, confidence=0.8, directed_goal="ko_on_path"))
    pilot.match_planner_steer = True
    hi = pilot._gameplan_goal_bonus("ko_for_prizes", board)
    assert hi > 0                                                    # this line serves the directed goal
    assert pilot._gameplan_goal_bonus("compose", board) == 0         # unrelated line → no bump
    lo = Board(game_plan=GamePlan(mode=Plan.RACE, confidence=0.4, directed_goal="ko_on_path"))
    assert pilot._gameplan_goal_bonus("ko_for_prizes", lo) < hi       # confidence-scaled
    pilot.match_planner_steer = False
    assert pilot._gameplan_goal_bonus("ko_for_prizes", board) == 0    # kill-switch → silent


# ── S4: the forgo-KO gate — DELETED (POC-T4/5, Issue #386); a gate above the composer is what
# ADR-0092 eliminates. The FACT survives at DECISION level in `test_blunder_20260710.py`.
