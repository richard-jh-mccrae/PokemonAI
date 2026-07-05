"""The cross-deck gauntlet corpus generator (tools/sim/gauntlet): our real agents played against each
other via the process-isolated battle loop + MatchRecorder, so the Automatic Value Model trains on states
where favorability actually VARIES (grilled 2026-07-05 — the seed's mirror-only corpus never did)."""
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
    """The gauntlet's deck pairings: every unordered cross pair PLUS each mirror (the grilled corpus
    mix — cross carries the favorability signal, mirrors keep the model calibrated on symmetric boards).
    `include_mirror=False` drops the mirrors."""
    from sim.gauntlet import pairings
    full = pairings(["ms", "ml", "dp"])
    assert set(full) == {("ms", "ms"), ("ms", "ml"), ("ms", "dp"),
                         ("ml", "ml"), ("ml", "dp"), ("dp", "dp")}   # 3 cross + 3 mirror
    cross = pairings(["ms", "ml", "dp"], include_mirror=False)
    assert set(cross) == {("ms", "ml"), ("ms", "dp"), ("ml", "dp")}  # mirrors dropped
    assert len(full) == 6 and len(cross) == 3


@pytest.mark.req("REQ-SIM-0015")
def test_generate_gauntlet_writes_mineable_films(tmp_path):
    """Each pairing's games run through play_match + recorder and land as tagged replays under
    ``<out>/gauntlet/<stem>/`` — a corpus the value extractor mines with no new reader (so
    ``train.py --replays <out>/gauntlet`` just works). Mirror fixture here; the real run is cross-deck
    (its process isolation is covered by test_battle's mega_starmie×crasher)."""
    from sim.gauntlet import generate_gauntlet
    from train.value.extract import rows_from_replay
    from meta_tracker.parse import load_replay
    from train.tune import _build_pilot

    run_root = generate_gauntlet(["mega_starmie"], 2, agents_root=FIXTURE_AGENTS, out_root=tmp_path,
                                 when=WHEN, sha="abc1234", extra_syspath=SRC)
    files = sorted(run_root.rglob("*.json"))
    assert len(files) == 2                          # both clean mirror games written
    pilot, _ = _build_pilot("mega_starmie")
    rows = list(rows_from_replay(pilot, load_replay(files[0])))
    assert len(rows) > 10                           # a real game → many mineable labelled states
