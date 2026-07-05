"""Paired-delta A/B analysis for the Tier-5 cross-deck gauntlet (grilled 2026-07-05).

You can't overlay-on-vs-off on ONE deck cross-deck (that's the useless mirror). So for each directed
matchup we measure ``winrate(D@value-on vs O) − winrate(D@value-off vs O)`` against a FIXED baseline
opponent O, and aggregate — subtracting out the raw deck matchup so only the switch's effect remains.
"""
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


@pytest.mark.req("REQ-SIM-0016")
def test_paired_delta_aggregates_and_flips_only_when_safe():
    """The aggregate delta + 95% CI combine the per-matchup on−off differences; the grilled flip rule
    ships value_model ON only when the delta is non-negative, its CI rules out a real (≥1%) regression,
    AND zero games crashed — else the model parks OFF."""
    from sim.paired_ab import paired_delta, flips_on

    # value-on beats value-off across two matchups at big N → positive delta, CI clear of −1%
    strong = paired_delta([(1100, 2000, 1000, 2000), (1150, 2000, 1000, 2000)])
    assert strong["delta"] > 0 and strong["ci_lo"] > -0.01
    assert flips_on(strong, crashes=0) is True
    assert flips_on(strong, crashes=1) is False        # any crash blocks the flip (never on a green suite alone)

    # a real regression (on << off) → negative delta below the tolerance → park
    weak = paired_delta([(900, 2000, 1000, 2000), (880, 2000, 1000, 2000)])
    assert weak["delta"] < 0 and weak["ci_lo"] < -0.01
    assert flips_on(weak, crashes=0) is False


@pytest.mark.req("REQ-SIM-0016")
def test_paired_delta_ci_tightens_with_n():
    """The honesty interval narrows as games grow — a neutral result at small N is inconclusive, not a
    pass; the flip rule needs the CI, not just the point estimate."""
    from sim.paired_ab import paired_delta
    small = paired_delta([(55, 100, 50, 100)])
    big = paired_delta([(5500, 10000, 5000, 10000)])
    assert (small["ci_hi"] - small["ci_lo"]) > (big["ci_hi"] - big["ci_lo"])
