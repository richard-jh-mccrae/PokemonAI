"""Paired-delta A/B analysis for the Tier-5 cross-deck gauntlet.

Per directed matchup: ``winrate(D@on vs O) − winrate(D@off vs O)`` against a FIXED opponent O, then
aggregated — which subtracts out the raw deck matchup so only the switch's effect remains.
"""
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


@pytest.mark.req("REQ-SIM-0016")
def test_paired_delta_aggregates_and_flips_only_when_safe():
    """Flip needs delta >= 0, a CI ruling out a real (>=1%) regression, AND zero crashes."""
    from sim.paired_ab import paired_delta, flips_on

    strong = paired_delta([(1100, 2000, 1000, 2000), (1150, 2000, 1000, 2000)])
    assert strong["delta"] > 0 and strong["ci_lo"] > -0.01
    assert flips_on(strong, crashes=0) is True
    assert flips_on(strong, crashes=1) is False        # any crash blocks the flip

    weak = paired_delta([(900, 2000, 1000, 2000), (880, 2000, 1000, 2000)])
    assert weak["delta"] < 0 and weak["ci_lo"] < -0.01
    assert flips_on(weak, crashes=0) is False


@pytest.mark.req("REQ-SIM-0016")
def test_paired_delta_ci_tightens_with_n():
    """The flip rule needs the CI, not just the point estimate."""
    from sim.paired_ab import paired_delta
    small = paired_delta([(55, 100, 50, 100)])
    big = paired_delta([(5500, 10000, 5000, 10000)])
    assert (small["ci_hi"] - small["ci_lo"]) > (big["ci_hi"] - big["ci_lo"])


# --- the mid-build Tripwire (ADR-0072 decision 1, Issue #167) -------------------------------------

@pytest.mark.req("REQ-SIM-0031")
def test_mid_build_verdict_passes_a_negative_delta_that_flips_on_refuses():
    """A mid-build decider swap is not trying to raise win rate, so the Tripwire drops `delta >= 0`
    and asks only that no CATASTROPHE is consistent with the data."""
    from sim.paired_ab import flips_on, mid_build_verdict

    b1 = {"delta": -0.0117, "ci_lo": -0.0459, "ci_hi": 0.0225, "n_matchups": 6}
    assert flips_on(b1, crashes=0) is False
    assert mid_build_verdict(b1, crashes=0) is True


@pytest.mark.req("REQ-SIM-0031")
def test_mid_build_verdict_still_hard_fails_on_any_crash():
    """A hard zero, never traded against precision."""
    from sim.paired_ab import mid_build_verdict
    neutral = {"delta": 0.0, "ci_lo": -0.02, "ci_hi": 0.02, "n_matchups": 6}
    assert mid_build_verdict(neutral, crashes=0) is True
    assert mid_build_verdict(neutral, crashes=1) is False


@pytest.mark.req("REQ-SIM-0031")
def test_mid_build_verdict_fails_a_catastrophe_below_the_bound():
    """−5 pp is the one win-rate fact the standing n=200/arm/matchup run can resolve."""
    from sim.paired_ab import mid_build_verdict
    bad = {"delta": -0.06, "ci_lo": -0.091, "ci_hi": -0.029, "n_matchups": 6}
    assert mid_build_verdict(bad, crashes=0) is False


@pytest.mark.req("REQ-SIM-0031")
def test_mid_build_bound_is_looser_than_the_post_composition_one():
    """Each bound is calibrated to what its instrument can adjudicate at its own game count."""
    from sim.paired_ab import _REG_TOL, MID_BUILD_REG_TOL, flips_on, mid_build_verdict
    assert MID_BUILD_REG_TOL > _REG_TOL
    between = {"delta": 0.001, "ci_lo": -0.03, "ci_hi": 0.032, "n_matchups": 6}
    assert flips_on(between, crashes=0) is False        # post-composition: not precise enough
    assert mid_build_verdict(between, crashes=0) is True  # mid-build: no catastrophe, that's the ask
