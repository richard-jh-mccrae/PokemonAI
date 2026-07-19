"""Eval harness (tools/sim/eval_run, ADR-0053 WP2): the power math + cell plan — pure functions,
no engine. The live matrix runner is exercised in test_eval_run; the statistics that decide how
many games a G2 run buys are pinned here."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


@pytest.mark.req("REQ-SIM-0018")
def test_per_arm_games_matches_the_power_table():
    """n = 0.5·(z/d)² at 95%/80% — the presets a standard run is powered for. Finer deltas cost
    quadratically more games (halving the detectable delta ~quadruples the games)."""
    from sim.eval_run import per_arm_games
    assert per_arm_games(0.05) == 1568          # --quick
    assert per_arm_games(0.03) == 4356          # default
    assert per_arm_games(0.02) == 9800          # --fine
    assert per_arm_games(0.02) > 4 * per_arm_games(0.05) - 100   # ~quadratic in 1/d


@pytest.mark.req("REQ-SIM-0018")
def test_per_arm_games_rejects_nonpositive_delta():
    """A zero/negative detectable delta is nonsense (infinite games) — fail loud, not silently."""
    from sim.eval_run import per_arm_games
    for bad in (0.0, -0.03):
        with pytest.raises(ValueError):
            per_arm_games(bad)


@pytest.mark.req("REQ-SIM-0018")
def test_preset_delta_resolves_named_presets():
    """The three CLI presets map to their detectable deltas; an unknown name fails loud."""
    from sim.eval_run import preset_delta, PRESETS, DEFAULT_PRESET
    assert preset_delta("quick") == 0.05
    assert preset_delta("default") == 0.03
    assert preset_delta("fine") == 0.02
    assert DEFAULT_PRESET in PRESETS
    with pytest.raises(ValueError):
        preset_delta("turbo")


@pytest.mark.req("REQ-SIM-0018")
def test_games_per_matchup_spreads_the_per_arm_total():
    """The per-arm total is spread evenly across the opponent field (ceil, floored at 1) so every
    cell gets games and matchup coverage stays balanced; no opponents -> nothing to run."""
    from sim.eval_run import games_per_matchup
    assert games_per_matchup(4356, 3) == 1452       # even spread across 3 opponents
    assert games_per_matchup(10, 3) == 4            # ceil, not floor (never under-buys)
    assert games_per_matchup(1, 3) == 1             # floored at 1, never 0
    assert games_per_matchup(4356, 0) == 0          # no field -> nothing


@pytest.mark.req("REQ-SIM-0018")
def test_matchup_cells_are_per_opponent_per_seat_and_exclude_h2h():
    """Cells enumerate (opponent, seat); the candidate's own deck in the field is the mirror cell.
    The direct candidate-vs-baseline head-to-head is never a paired cell (it's informational-only,
    assembled separately by the report) — so 'baseline' as a bare name is not implied here."""
    from sim.eval_run import matchup_cells
    cells = matchup_cells(["ms", "ml", "dp"])
    assert len(cells) == 6                          # 3 opponents x 2 seats
    assert {(c["opponent"], c["seat"]) for c in cells} == {
        (o, s) for o in ("ms", "ml", "dp") for s in (0, 1)}
    mirror = matchup_cells(["ms"])                  # candidate deck vs itself = the mirror
    assert [c["opponent"] for c in mirror] == ["ms", "ms"]
