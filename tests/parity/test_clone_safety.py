"""M3 clone-safety gate (ADR-0059): fork mid-cascade at every select of every committed
trace; the fork and the original must replay the recorded choice identically (god frame,
outboxes, pending select). This is the property the verification API's clone-per-step
sessions — and every future search consumer — stand on.
"""
from pathlib import Path

import pytest

from cgpy.verify.replayer import replay
from cgpy.verify.trace import Trace

FIXDIR = Path(__file__).resolve().parents[1] / "fixtures" / "parity"
TRACES = sorted(FIXDIR.glob("*.trace.json.gz"))


@pytest.mark.req("REQ-CGPY-M3-0011")
@pytest.mark.parametrize("path", TRACES, ids=lambda p: p.name.split(".")[0])
def test_fork_at_every_select_replays_identically(path):
    report = replay(Trace.load(path), fork_check=True)
    assert report.clean, f"{path.name}: {report}"
