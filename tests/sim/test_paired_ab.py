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


# --- the mid-build Tripwire (ADR-0071 decision 1, #167) -------------------------------------------

@pytest.mark.req("REQ-SIM-0031")
def test_mid_build_verdict_passes_a_negative_delta_that_flips_on_refuses():
    """THE re-scope, in one assertion. A mid-build decider swap is not trying to raise win rate — it
    makes one axis correct so #165/#145 can compose the axes — so the Tripwire drops `delta >= 0` and
    asks only that no CATASTROPHE is consistent with the data. Phase 1b's real numbers (−1.17 pp,
    CI [−4.59, +2.25]) are the case: `flips_on` says no, the Tripwire says yes."""
    from sim.paired_ab import flips_on, mid_build_verdict

    b1 = {"delta": -0.0117, "ci_lo": -0.0459, "ci_hi": 0.0225, "n_matchups": 6}
    assert flips_on(b1, crashes=0) is False           # the rule that forced a user override
    assert mid_build_verdict(b1, crashes=0) is True   # the rule that grades what 1b was actually doing


@pytest.mark.req("REQ-SIM-0031")
def test_mid_build_verdict_still_hard_fails_on_any_crash():
    """The crash gate is the clause that WAS working (4800 games, zero crashes) and it survives the
    re-scope unchanged — a hard zero, never traded against precision."""
    from sim.paired_ab import mid_build_verdict
    neutral = {"delta": 0.0, "ci_lo": -0.02, "ci_hi": 0.02, "n_matchups": 6}
    assert mid_build_verdict(neutral, crashes=0) is True
    assert mid_build_verdict(neutral, crashes=1) is False


@pytest.mark.req("REQ-SIM-0031")
def test_mid_build_verdict_fails_a_catastrophe_below_the_bound():
    """It excludes catastrophes and claims nothing more: a CI lower bound worse than −5 pp is the one
    win-rate fact the standing n=200/arm/matchup run CAN resolve, so it is the one it gates on."""
    from sim.paired_ab import mid_build_verdict
    bad = {"delta": -0.06, "ci_lo": -0.091, "ci_hi": -0.029, "n_matchups": 6}
    assert mid_build_verdict(bad, crashes=0) is False


@pytest.mark.req("REQ-SIM-0031")
def test_mid_build_bound_is_looser_than_the_post_composition_one():
    """The two stages are calibrated to what their instrument can adjudicate: a −1 pp bound needs
    ~28,000 games near a zero delta, a −5 pp bound is decidable at the standing 2400. A swap sitting
    between the two bounds is exactly the band the split exists to separate."""
    from sim.paired_ab import _REG_TOL, MID_BUILD_REG_TOL, flips_on, mid_build_verdict
    assert MID_BUILD_REG_TOL > _REG_TOL
    between = {"delta": 0.001, "ci_lo": -0.03, "ci_hi": 0.032, "n_matchups": 6}
    assert flips_on(between, crashes=0) is False        # post-composition: not precise enough
    assert mid_build_verdict(between, crashes=0) is True  # mid-build: no catastrophe, that's the ask
