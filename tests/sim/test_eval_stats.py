"""Eval harness (tools/sim/eval_run, ADR-0053 WP2): the power math + cell plan, pure functions."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


@pytest.mark.req("REQ-SIM-0018")
def test_per_arm_games_matches_the_power_table():
    """n = 0.5·(z/d)² at 95%/80%."""
    from sim.eval_run import per_arm_games
    assert per_arm_games(0.05) == 1568          # --quick
    assert per_arm_games(0.03) == 4356          # default
    assert per_arm_games(0.02) == 9800          # --fine
    assert per_arm_games(0.02) > 4 * per_arm_games(0.05) - 100   # ~quadratic in 1/d


@pytest.mark.req("REQ-SIM-0018")
def test_per_arm_games_rejects_nonpositive_delta():
    from sim.eval_run import per_arm_games
    for bad in (0.0, -0.03):
        with pytest.raises(ValueError):
            per_arm_games(bad)


@pytest.mark.req("REQ-SIM-0018")
def test_preset_delta_resolves_named_presets():
    from sim.eval_run import preset_delta, PRESETS, DEFAULT_PRESET
    assert preset_delta("quick") == 0.05
    assert preset_delta("default") == 0.03
    assert preset_delta("fine") == 0.02
    assert DEFAULT_PRESET in PRESETS
    with pytest.raises(ValueError):
        preset_delta("turbo")


@pytest.mark.req("REQ-SIM-0018")
def test_games_per_matchup_spreads_the_per_arm_total():
    from sim.eval_run import games_per_matchup
    assert games_per_matchup(4356, 3) == 1452
    assert games_per_matchup(10, 3) == 4            # ceil, not floor (never under-buys)
    assert games_per_matchup(1, 3) == 1             # floored at 1, never 0
    assert games_per_matchup(4356, 0) == 0


@pytest.mark.req("REQ-SIM-0018")
def test_matchup_cells_are_per_opponent_per_seat_and_exclude_h2h():
    """The candidate-vs-baseline head-to-head is informational-only, assembled by the report."""
    from sim.eval_run import matchup_cells
    cells = matchup_cells(["ms", "ml", "dp"])
    assert len(cells) == 6                          # 3 opponents x 2 seats
    assert {(c["opponent"], c["seat"]) for c in cells} == {
        (o, s) for o in ("ms", "ml", "dp") for s in (0, 1)}
    mirror = matchup_cells(["ms"])                  # candidate deck vs itself = the mirror
    assert [c["opponent"] for c in mirror] == ["ms", "ms"]
