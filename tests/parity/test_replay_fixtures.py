"""THE parity gate: every committed trace replays through cgpy divergence-free (ADR-0059).

DLL-free by construction — the trace IS the native side — so this runs on any platform,
which is what pins cgpy to the binary's behavior in CI. A failure prints the first-divergence
report (frame, JSON path, native vs cgpy values). REQ-CGPY-0002.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from cgpy.verify.replayer import replay
from cgpy.verify.trace import Trace

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "parity"
TRACES = sorted(FIXTURES.glob("*.trace.json.gz"))


@pytest.mark.parametrize("path", TRACES, ids=lambda p: p.name.replace(".trace.json.gz", ""))
def test_trace_replays_clean(path):
    report = replay(Trace.load(path))
    assert report.clean, f"\n{report}"


def test_fixture_corpus_present():
    assert len(TRACES) >= 10, "the committed parity corpus should not shrink"
