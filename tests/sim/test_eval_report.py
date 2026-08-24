"""Engine-free eval harness contract consumed by the G2 adoption gate (ADR-0053 WP2)."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


def _pair(cand_w, base_w, n):
    """One paired matchup cell in C3 shape; each arm plays n games vs the opponent."""
    return {"opponent": "o", "seat": 0, "n": n, "candidate_wins": cand_w,
            "baseline_wins": base_w, "draws": 0}


@pytest.mark.req("REQ-SIM-0019")
def test_verdict_pass_when_flips_on_and_no_regression():
    """pass = delta >= 0, CI lower bound >= -1%, zero crashes, no checkpoint regression."""
    from sim.eval_report import build_report
    matchups = [_pair(1100, 1000, 2000), _pair(1150, 1000, 2000)]
    rep = build_report(baseline={"agent": "b"}, candidate={"agent": "c"}, matchups=matchups)
    assert rep["paired_delta"]["win_delta"] > 0 and rep["paired_delta"]["ci_low"] > -0.01
    assert rep["verdict"] == "pass"


@pytest.mark.req("REQ-SIM-0019")
def test_verdict_fail_when_ci_upper_below_zero():
    from sim.eval_report import build_report
    matchups = [_pair(900, 1000, 2000), _pair(880, 1000, 2000)]
    rep = build_report(baseline={"agent": "b"}, candidate={"agent": "c"}, matchups=matchups)
    assert rep["paired_delta"]["ci_high"] < 0
    assert rep["verdict"] == "fail"


@pytest.mark.req("REQ-SIM-0019")
def test_verdict_inconclusive_on_zero_pairs_and_on_capped_run():
    """Both cap at inconclusive, so G2 cannot adopt on a fraction of the matrix."""
    from sim.eval_report import build_report
    empty = build_report(baseline={}, candidate={}, matchups=[])
    assert empty["paired_delta"]["win_delta"] == 0.0
    assert empty["verdict"] == "inconclusive"                     # measured nothing -> not a pass

    strong = [_pair(1100, 1000, 2000), _pair(1150, 1000, 2000)]
    capped = build_report(baseline={}, candidate={}, matchups=strong, status="capped")
    assert capped["verdict"] == "inconclusive"                    # partial matrix -> not a pass


@pytest.mark.req("REQ-SIM-0019")
def test_per_arm_n_keeps_the_delta_sane_on_mismatched_sizes():
    """A resume can leave the arms different sizes; a shared min-n would give p>1 and a garbage CI."""
    from sim.eval_report import build_report
    row = {"opponent": "o", "seat": 0, "n": 5, "candidate_wins": 40, "candidate_n": 50,
           "baseline_wins": 3, "baseline_n": 5, "draws": 0}                # arms differ: 50 vs 5
    rep = build_report(baseline={}, candidate={}, matchups=[row])
    pd = rep["paired_delta"]
    assert -1.0 <= pd["win_delta"] <= 1.0                         # 40/50=0.8 vs 3/5=0.6, not 40/5=8
    assert pd["ci_low"] <= pd["win_delta"] <= pd["ci_high"]


@pytest.mark.req("REQ-SIM-0019")
def test_verdict_inconclusive_on_crash_and_on_wide_ci():
    """The flip needs the interval, not just the point estimate."""
    from sim.eval_report import build_report
    strong = [_pair(1100, 1000, 2000), _pair(1150, 1000, 2000)]
    crashed = build_report(baseline={}, candidate={}, matchups=strong, candidate_crashes=1)
    assert crashed["verdict"] == "inconclusive"          # positive delta, but a crash: not pass, not fail

    noisy = build_report(baseline={}, candidate={}, matchups=[_pair(55, 50, 100)])
    assert noisy["paired_delta"]["ci_low"] < -0.01 < noisy["paired_delta"]["ci_high"]
    assert noisy["verdict"] == "inconclusive"


def _ck(build_id, cand_w, base_w, n):
    return {"build_id": build_id, "candidate_wins": cand_w, "candidate_n": n,
            "baseline_wins": base_w, "baseline_n": n}


@pytest.mark.req("REQ-SIM-0019")
def test_checkpoint_regression_caps_a_clean_pass_to_inconclusive():
    """Catches non-transitivity drift a raw gauntlet hides. Checkpoints never enter the delta."""
    from sim.eval_report import build_report
    matchups = [_pair(1100, 1000, 2000), _pair(1150, 1000, 2000)]     # clean pass on live opponents
    checkpoints = [_ck(7, 600, 1000, 2000)]                          # 30% vs 50% -> big drop
    rep = build_report(baseline={}, candidate={}, matchups=matchups, checkpoints=checkpoints)
    assert rep["verdict"] == "inconclusive"
    assert [r["build_id"] for r in rep["regressions"]] == [7]
    assert rep["checkpoints"][0]["regression"] is True
    assert rep["paired_delta"]["win_delta"] > 0                       # delta unaffected by the checkpoint


@pytest.mark.req("REQ-SIM-0019")
def test_checkpoint_within_noise_does_not_trip():
    """A checkpoint can never MAKE a candidate pass either — it is not in the delta."""
    from sim.eval_report import build_report, checkpoint_regressions
    checkpoints = [_ck(7, 1010, 1000, 2000)]                         # ~equal vs baseline -> no trip
    assert checkpoint_regressions(checkpoints) == []
    matchups = [_pair(1100, 1000, 2000), _pair(1150, 1000, 2000)]
    rep = build_report(baseline={}, candidate={}, matchups=matchups, checkpoints=checkpoints)
    assert rep["verdict"] == "pass"
    assert rep["checkpoints"][0]["regression"] is False


@pytest.mark.req("REQ-SIM-0019")
def test_checkpoint_pool_is_additive_and_warns_on_missing():
    """Pool = every agent_history build whose zip is on disk; `--checkpoints` ids ADD, never restrict."""
    from sim.eval_report import checkpoint_pool
    history = [{"submission_id": 3, "agent": "ms", "artifact": "ms-3"},
               {"submission_id": 5, "agent": "ml", "artifact": "ml-5"}]
    pool, warnings = checkpoint_pool(history, available_artifacts={"ms-3"})
    assert [p["submission_id"] for p in pool] == [3]                 # only the one with a zip
    assert any("#5" in w and "missing" in w for w in warnings)

    both, _ = checkpoint_pool(history, available_artifacts={"ms-3", "ml-5"}, extra_ids=[3])
    assert [p["submission_id"] for p in both] == [3, 5]            # additive, no restriction
    unknown_pool, warns3 = checkpoint_pool(history, available_artifacts=set(), extra_ids=[9])
    assert unknown_pool == [] and any("#9" in w for w in warns3)


@pytest.mark.req("REQ-SIM-0019")
def test_report_carries_the_full_c3_field_set():
    """Missing a field breaks the gate's consumer."""
    from sim.eval_report import build_report, REPORT_VERSION
    from sim.eval_aivat import aivat
    rep = build_report(
        baseline={"agent": "b", "label": "hand-tuned"}, candidate={"agent": "c", "label": "learned"},
        matchups=[_pair(1050, 1000, 2000)], checkpoints=[_ck(3, 250, 250, 500)],
        strata=[{"name": "high-swing", "n": 10, "win_delta": 0.04, "ci_low": 0.0, "ci_high": 0.08}],
        aivat=aivat([], None), git_rev="abc1234", generated_at="2026-07-19T00:00:00",
        preset="default", per_cell_n=1452)
    for field in ("report_version", "generated_at", "git_rev", "baseline", "candidate", "n_games",
                  "matchups", "paired_delta", "strata", "checkpoints", "aivat", "verdict"):
        assert field in rep, f"C3 missing {field}"
    assert rep["report_version"] == REPORT_VERSION
    assert set(rep["paired_delta"]) == {"win_delta", "ci_low", "ci_high", "method"}
    assert rep["aivat"] is None                                     # v1 null seam
    assert rep["n_games"] == 2000 * 2 + (500 + 500)                # both arms per cell + checkpoint arms


@pytest.mark.req("REQ-SIM-0019")
def test_empty_cells_are_excluded_from_the_delta():
    """Excluded, not a divide-by-zero: an odd per-cell samples one seat, and cells can fully crash."""
    from sim.eval_report import build_report, checkpoint_regressions
    matchups = [_pair(1050, 1000, 2000), {"opponent": "o", "seat": 1, "n": 0,
                                          "candidate_wins": 0, "baseline_wins": 0, "draws": 0}]
    rep = build_report(baseline={}, candidate={}, matchups=matchups,
                       checkpoints=[_ck(9, 0, 0, 0)])
    assert rep["paired_delta"]["win_delta"] > 0                    # computed off the one real cell
    assert checkpoint_regressions([_ck(9, 0, 0, 0)]) == []        # empty checkpoint can't regress


@pytest.mark.req("REQ-SIM-0019")
def test_h2h_is_reported_but_never_enters_the_delta_or_verdict():
    """H2H is emitted tagged informational; a lopsided one must not flip the verdict."""
    from sim.eval_report import build_report
    neutral = [_pair(1000, 1000, 2000)]
    h2h = [{"opponent": "h2h", "seat": 0, "n": 200, "candidate_wins": 200, "baseline_wins": 0,
            "draws": 0}]                                            # candidate crushes baseline
    rep = build_report(baseline={}, candidate={}, matchups=neutral, h2h=h2h)
    assert abs(rep["paired_delta"]["win_delta"]) < 1e-9
    assert rep["verdict"] != "pass"
    tagged = [m for m in rep["matchups"] if m.get("informational")]
    assert len(tagged) == 1 and tagged[0]["opponent"] == "h2h"
