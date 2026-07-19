"""Eval harness (tools/sim/eval_report, ADR-0053 WP2): the verdict rule, the checkpoint regression
tripwire, pure checkpoint-pool resolution, and the C3 report assembler — all engine-free. This is
the contract G2 reads (C3 in docs/plans/ml/ml-training-contracts.md), so the field set and the
pass/fail/inconclusive logic are pinned here."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


def _pair(cand_w, base_w, n):
    """One paired matchup cell in C3 shape (candidate and baseline each play n games vs the opp)."""
    return {"opponent": "o", "seat": 0, "n": n, "candidate_wins": cand_w,
            "baseline_wins": base_w, "draws": 0}


# ---- verdict rule (step 2) -------------------------------------------------------------------

@pytest.mark.req("REQ-SIM-0019")
def test_verdict_pass_when_flips_on_and_no_regression():
    """pass = the grilled flips_on bar (delta >= 0, CI lower bound >= -1%, zero candidate crashes)
    with no checkpoint regression. A clean, powered win ships."""
    from sim.eval_report import build_report
    matchups = [_pair(1100, 1000, 2000), _pair(1150, 1000, 2000)]
    rep = build_report(baseline={"agent": "b"}, candidate={"agent": "c"}, matchups=matchups)
    assert rep["paired_delta"]["win_delta"] > 0 and rep["paired_delta"]["ci_low"] > -0.01
    assert rep["verdict"] == "pass"


@pytest.mark.req("REQ-SIM-0019")
def test_verdict_fail_when_ci_upper_below_zero():
    """fail = the candidate is provably worse overall (CI upper bound < 0)."""
    from sim.eval_report import build_report
    matchups = [_pair(900, 1000, 2000), _pair(880, 1000, 2000)]
    rep = build_report(baseline={"agent": "b"}, candidate={"agent": "c"}, matchups=matchups)
    assert rep["paired_delta"]["ci_high"] < 0
    assert rep["verdict"] == "fail"


@pytest.mark.req("REQ-SIM-0019")
def test_verdict_inconclusive_on_crash_and_on_wide_ci():
    """A candidate crash blocks a pass (never ship on a crash); a straddling CI at low N is
    inconclusive, not a pass — the flip needs the interval, not just the point estimate."""
    from sim.eval_report import build_report
    strong = [_pair(1100, 1000, 2000), _pair(1150, 1000, 2000)]
    crashed = build_report(baseline={}, candidate={}, matchups=strong, candidate_crashes=1)
    assert crashed["verdict"] == "inconclusive"          # positive delta, but a crash -> not pass, not fail

    noisy = build_report(baseline={}, candidate={}, matchups=[_pair(55, 50, 100)])
    assert noisy["paired_delta"]["ci_low"] < -0.01 < noisy["paired_delta"]["ci_high"]
    assert noisy["verdict"] == "inconclusive"


# ---- checkpoint tripwire (step 3) ------------------------------------------------------------

def _ck(build_id, cand_w, base_w, n):
    return {"build_id": build_id, "candidate_wins": cand_w, "candidate_n": n,
            "baseline_wins": base_w, "baseline_n": n}


@pytest.mark.req("REQ-SIM-0019")
def test_checkpoint_regression_caps_a_clean_pass_to_inconclusive():
    """A candidate that would otherwise pass, but regresses against a frozen checkpoint by more
    than the cell CI, is capped at inconclusive with the culprit named — non-transitivity drift a
    raw gauntlet would hide. Checkpoints never enter the paired delta."""
    from sim.eval_report import build_report
    matchups = [_pair(1100, 1000, 2000), _pair(1150, 1000, 2000)]     # clean pass on live opponents
    checkpoints = [_ck(7, 600, 1000, 2000)]                          # candidate 30% vs baseline 50% -> big drop
    rep = build_report(baseline={}, candidate={}, matchups=matchups, checkpoints=checkpoints)
    assert rep["verdict"] == "inconclusive"
    assert [r["build_id"] for r in rep["regressions"]] == [7]
    assert rep["checkpoints"][0]["regression"] is True
    assert rep["paired_delta"]["win_delta"] > 0                       # delta unaffected by the checkpoint


@pytest.mark.req("REQ-SIM-0019")
def test_checkpoint_within_noise_does_not_trip():
    """A checkpoint result within the cell's CI margin is not a regression — noise doesn't cap the
    verdict, and a checkpoint can never MAKE a candidate pass (it's not in the delta)."""
    from sim.eval_report import build_report, checkpoint_regressions
    checkpoints = [_ck(7, 1010, 1000, 2000)]                         # ~equal vs baseline -> no trip
    assert checkpoint_regressions(checkpoints) == []
    matchups = [_pair(1100, 1000, 2000), _pair(1150, 1000, 2000)]
    rep = build_report(baseline={}, candidate={}, matchups=matchups, checkpoints=checkpoints)
    assert rep["verdict"] == "pass"
    assert rep["checkpoints"][0]["regression"] is False


@pytest.mark.req("REQ-SIM-0019")
def test_checkpoint_pool_resolves_submitted_builds_and_warns_on_missing():
    """Pool = submitted builds (agent_history rows) whose zip is on disk; a submitted build with no
    local zip is skipped with a named warning; --checkpoints ids restrict to a pinned subset."""
    from sim.eval_report import checkpoint_pool
    history = [{"submission_id": 3, "agent": "ms", "artifact": "ms-3"},
               {"submission_id": 5, "agent": "ml", "artifact": "ml-5"}]
    pool, warnings = checkpoint_pool(history, available_artifacts={"ms-3"})
    assert [p["submission_id"] for p in pool] == [3]                 # only the one with a zip
    assert any("#5" in w and "missing" in w for w in warnings)

    pinned, warns2 = checkpoint_pool(history, available_artifacts={"ms-3", "ml-5"}, extra_ids=[5])
    assert [p["submission_id"] for p in pinned] == [5]              # pin restricts to #5
    unknown_pool, warns3 = checkpoint_pool(history, available_artifacts=set(), extra_ids=[9])
    assert unknown_pool == [] and any("#9" in w for w in warns3)


# ---- C3 emitter (step 4) ---------------------------------------------------------------------

@pytest.mark.req("REQ-SIM-0019")
def test_report_carries_the_full_c3_field_set():
    """The frozen C3 shape G2 reads: version, provenance, paired_delta in C3 names, matchups,
    strata, checkpoints, aivat (null in v1), verdict. Missing a field breaks the gate's consumer."""
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
    """A matchup or checkpoint cell with zero games (an odd per-cell that samples only one seat, or
    a fully-crashed cell) must not divide-by-zero — it's simply excluded from the aggregate."""
    from sim.eval_report import build_report, checkpoint_regressions
    matchups = [_pair(1050, 1000, 2000), {"opponent": "o", "seat": 1, "n": 0,
                                          "candidate_wins": 0, "baseline_wins": 0, "draws": 0}]
    rep = build_report(baseline={}, candidate={}, matchups=matchups,
                       checkpoints=[_ck(9, 0, 0, 0)])
    assert rep["paired_delta"]["win_delta"] > 0                    # computed off the one real cell
    assert checkpoint_regressions([_ck(9, 0, 0, 0)]) == []        # empty checkpoint can't regress


@pytest.mark.req("REQ-SIM-0019")
def test_h2h_is_reported_but_never_enters_the_delta_or_verdict():
    """The head-to-head block is emitted for context (tagged informational) but excluded from the
    paired delta — a lopsided H2H can't flip the verdict, the protocol the research says not to
    trust alone."""
    from sim.eval_report import build_report
    neutral = [_pair(1000, 1000, 2000)]                             # dead-even live matchups
    h2h = [{"opponent": "h2h", "seat": 0, "n": 200, "candidate_wins": 200, "baseline_wins": 0,
            "draws": 0}]                                            # candidate crushes baseline head-to-head
    rep = build_report(baseline={}, candidate={}, matchups=neutral, h2h=h2h)
    assert abs(rep["paired_delta"]["win_delta"]) < 1e-9            # H2H did not move the delta
    assert rep["verdict"] != "pass"                                # ...so the crush can't ship it
    tagged = [m for m in rep["matchups"] if m.get("informational")]
    assert len(tagged) == 1 and tagged[0]["opponent"] == "h2h"    # but it IS in the report for the human
