"""The cross-deck gauntlet corpus generator (tools/sim/gauntlet): our agents against each other, so
the value model trains on states where favorability VARIES — a mirror-only corpus never does."""
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"
SRC = [REPO / "src"]
WHEN = datetime(2026, 7, 5, 12, 0, 0)


@pytest.mark.req("REQ-SIM-0014")
def test_pairings_covers_the_cross_pairs_and_mirrors():
    """Cross carries the favorability signal; mirrors keep the model calibrated on symmetric boards."""
    from sim.gauntlet import pairings
    full = pairings(["ms", "ml", "dp"])
    assert set(full) == {("ms", "ms"), ("ms", "ml"), ("ms", "dp"),
                         ("ml", "ml"), ("ml", "dp"), ("dp", "dp")}   # 3 cross + 3 mirror
    cross = pairings(["ms", "ml", "dp"], include_mirror=False)
    assert set(cross) == {("ms", "ml"), ("ms", "dp"), ("ml", "dp")}  # mirrors dropped
    assert len(full) == 6 and len(cross) == 3


@pytest.mark.req("REQ-SIM-0015")
def test_generate_gauntlet_writes_mineable_films(tmp_path):
    """Mineable = the value extractor needs no new reader; `train.py --replays <out>/gauntlet` works."""
    from sim.gauntlet import generate_gauntlet
    from train.value.extract import rows_from_replay
    from meta_tracker.parse import load_replay
    from train.tune import _build_pilot

    run_root = generate_gauntlet(["mega_starmie"], 2, agents_root=FIXTURE_AGENTS, out_root=tmp_path,
                                 when=WHEN, sha="abc1234", extra_syspath=SRC)
    files = sorted(run_root.rglob("*.json"))
    assert len(files) == 2
    pilot, _ = _build_pilot("mega_starmie")
    rows = list(rows_from_replay(pilot, load_replay(files[0])))
    assert len(rows) > 10
