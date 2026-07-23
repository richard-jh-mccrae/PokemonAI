"""Eval harness (tools/sim/eval_aivat, ADR-0053 WP2 design D5): the AIVAT seam. v1 is the null
implementation — the signature is frozen so WP1's value net plugs in with no harness rework; the
report must carry ``aivat: null`` until then."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


@pytest.mark.req("REQ-SIM-0020")
def test_aivat_null_seam_returns_none_regardless_of_inputs():
    """v1 returns None for any (films, value_fn) — and never raises — so an eval run is complete
    with or without the correction. WP1 fills exactly this function."""
    from sim.eval_aivat import aivat
    assert aivat([], None) is None
    assert aivat([{"steps": []}], lambda obs: 0.5) is None


@pytest.mark.req("REQ-SIM-0020")
def test_report_maps_null_aivat_to_json_null():
    """The frozen wiring: the report's ``aivat`` field is the seam's return, so v1 emits null (not
    a stub object G2 would misread as a real correction)."""
    from sim.eval_aivat import aivat
    from sim.eval_report import build_report
    rep = build_report(baseline={}, candidate={},
                       matchups=[{"opponent": "o", "seat": 0, "n": 100,
                                  "candidate_wins": 50, "baseline_wins": 50, "draws": 0}],
                       aivat=aivat([], None))
    assert rep["aivat"] is None
