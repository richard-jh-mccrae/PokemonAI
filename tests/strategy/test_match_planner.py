"""S2 — the Match Planner (ADR-0045): `plan_match` produces the Game Plan (route + mode + confidence +
directed Turn Goal), computed first each turn and emitted for the blunder-buster. COMPUTE-ONLY: zero
decisions change until the seam (S3) wires the directed goal into the Turn Planner.
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
    """The Plan enum (the Game Plan's mode axis) grows from four to six — +STALL (build while declining
    giant-waking KOs) +SACRIFICE (trade the Active, race on prize math)."""
    from common.strategy.strategy import Plan
    assert {p.name for p in Plan} == {"SETUP", "RACE", "STALL", "STABILIZE", "SACRIFICE", "CLOSE"}


def _obs(me, opp, turn=6):
    return {"current": {"yourIndex": 0, "turn": turn, "players": [me, opp]}}


def _E(n):
    """``n`` attached Energy, as the engine gives them: bare card ids. (Verified against the
    recorded corrections — e.g. `dp_attach_the_recipients_color_f86.json` carries ``[2]``. The
    earlier dict shape survived only because every reader took ``len()``; a typed read of the same
    field goes looking for a CardStat and finds an unhashable dict.)"""
    return [1] * n


@pytest.mark.req("REQ-MATCH-0002")
def test_plan_match_returns_a_game_plan_with_a_mode_and_bounded_confidence():
    """`plan_match` returns a Game Plan carrying a mode (a Plan), a confidence in [0,1], and the route
    (my Prize-Path target ids) — the object the blunder-buster parses and the seam later steers by."""
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
    """Confidence is a closed-form feasibility score: neutral 0.5, up with the race margin (turns ahead)
    and my Active's survival window, down when behind — always clamped to [0,1]."""
    from common.strategy.objectives import plan_confidence
    assert plan_confidence(0, 1) == pytest.approx(0.5)
    assert plan_confidence(2, 1) > plan_confidence(0, 1)        # ahead in the race → more confident
    assert plan_confidence(0, 5) > plan_confidence(0, 1)        # survives longer → more confident
    assert plan_confidence(-3, 1) < 0.5                         # behind → less confident
    assert 0.0 <= plan_confidence(-99, None) <= 1.0
    assert 0.0 <= plan_confidence(99, 99) <= 1.0


@pytest.mark.req("REQ-MATCH-0004")
def test_derive_mode_sacrifice_when_doomed_with_a_ready_backup():
    """STABILIZE grows to SACRIFICE when a ready bench backup lets me trade the Active and race (the b4649
    delay-wall); with no backup it stays STABILIZE (save the Active)."""
    from common.pilot import Board
    from common.strategy.strategy import Plan
    pilot = _shipped_pilot()
    assert pilot._derive_mode(Board(phase=Plan.STABILIZE, bench_wincon_ready=True,
                                    race_ahead=0.0)) is Plan.SACRIFICE
    assert pilot._derive_mode(Board(phase=Plan.STABILIZE, bench_wincon_ready=False,
                                    race_ahead=0.0)) is Plan.STABILIZE


@pytest.mark.req("REQ-MATCH-0005")
def test_derive_mode_stall_when_clearly_ahead_and_wincon_offline():
    """SETUP/RACE grow to STALL when I am clearly ahead in the race yet my win-condition is not online —
    build rather than over-press; once the wincon is online it stays RACE."""
    from common.pilot import Board
    from common.strategy.strategy import Plan
    pilot = _shipped_pilot()
    assert pilot._derive_mode(Board(phase=Plan.RACE, line_ready=False, race_ahead=3.0)) is Plan.STALL
    assert pilot._derive_mode(Board(phase=Plan.RACE, line_ready=True, race_ahead=3.0)) is Plan.RACE


@pytest.mark.req("REQ-MATCH-0006")
def test_directed_goal_maps_from_mode_and_is_withheld_on_low_confidence():
    """The directed goal maps from the mode when confidence clears the bar (RACE → take the on-path KO),
    and is WITHHELD (None) when confidence is low — the Pilot then defers to the Turn Planner + weights."""
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
    """`_board` runs the Match Planner first each turn and hangs the Game Plan on the Board."""
    pilot = _shipped_pilot()
    me = {"active": [{"id": 1031, "hp": 330, "energies": _E(3)}], "bench": [], "hand": [], "prize": [None] * 6}
    opp = {"active": [{"id": 676, "hp": 110, "energies": []}], "bench": [], "prize": [None] * 6, "hand": []}
    board = pilot._board(_obs(me, opp))
    assert board.game_plan is not None and board.game_plan.mode is not None


@pytest.mark.req("REQ-MATCH-0007")
def test_game_plan_rides_the_decision_and_telemetry_blunder_buster_parseable():
    """The Game Plan rides the Decision and the telemetry record (mode + confidence + directed goal), so
    `/blunder-buster` can parse it from a ladder correction's live_trace."""
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
    """The seam (ADR-0045): a Turn-Planner candidate line SERVING the Game Plan's directed goal gets a
    confidence-scaled sub-prize bump, so the Game Plan steers the ranking; an unrelated line gets none,
    and the `match_planner_steer` kill-switch silences it (default OFF → byte-identical).

    Exercised on `ko_on_path`/`ko_for_prizes` since POC-T4/5. The pairing this used to use —
    `survive` → `stabilize_then_ko` — is gone: the composer scores heal-then-attack sequences by
    construction, so that line no longer exists and `survive` was DROPPED from `_GOAL_LINE` rather
    than left mapping to the empty set. Left mapping to nothing, this test would still have passed
    while asserting a bump that could never be paid."""
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


# ── S4: the forgo-KO gate — DELETED (POC-T4/5, Issue #386) ───────────────────────────────────────
#
# `_forgo_ko_gate`, `_forgo_ko_line` and the `reactivity == "solitaire"` opt-out are gone, and with
# them the three tests that lived here (`REQ-MATCH-0009/0010/0011`). Under 1-ply differencing,
# "decline this KO because it wakes a scarier body" is not a gate above the decider — it is one
# sequence out-scoring another, and a gate above the composer is what ADR-0092 exists to eliminate.
#
# The FACT is not deleted with the mechanism. "Don't wake the giant" is asserted at DECISION level,
# on real captured boards rather than the synthetic `_giant_waking_scenario` these tests built, by
# `tests/strategy/test_blunder_20260710.py::test_dont_wake_the_giant_takes_the_lock_free_attack`
# over `ml_dont_wake_the_giant_with_the_locking_ko_f88` (a CRITICAL) and
# `ml_dont_wake_the_giant_boost_ko_f48`. That is the test that survives a swap; these three pinned
# which rung fired, so they could not.
