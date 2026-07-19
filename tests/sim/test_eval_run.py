"""Eval harness (tools/sim/eval_run, ADR-0053 WP2): the live matrix runner end-to-end. A tiny
mega_starmie run produces reports/eval/<run_id>/ with a corpus-style manifest, gzip films, and a
valid C3 report.json; resume writes nothing new; caps halt the run; a crashing arm is recorded and
blocks a pass. Fixture mirror here (cross-deck process isolation is covered by test_battle)."""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"
SRC = [REPO / "src"]
MEGA = FIXTURE_AGENTS / "mega_starmie"


def _mega():
    from sim.battle import read_deck
    return {"label": "mega_starmie", "dir": MEGA, "deck": read_deck(MEGA)}


@pytest.mark.req("REQ-SIM-0022")
def test_run_eval_end_to_end_writes_manifest_films_and_c3_report(tmp_path):
    """A default-shape run (candidate=baseline=mega_starmie, one opponent=mega_starmie) emits a
    valid C3 report with a verdict and a populated strata block, plus a manifest header and gzip
    films under <out>/eval/<run_id>/."""
    from sim.eval_run import run_eval
    cand = base = _mega()
    report = run_eval(run_id="e1", created_at="2026-07-19T00:00:00", git_rev="abc1234",
                      candidate=cand, baseline=base, opponents={"mega_starmie": _mega()},
                      out_root=tmp_path, per_cell=2, extra_syspath=SRC, strata_agent="mega_starmie",
                      preset="default")

    run_dir = tmp_path / "eval" / "e1"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete" and manifest["manifest_version"] == 1
    assert manifest["totals"]["games"] == 2 * 2                    # 2 arms x per_cell=2

    films = list(run_dir.rglob("*.json.gz"))
    assert len(films) == 4 and all(f.suffix == ".gz" for f in films)

    saved = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert saved == report                                        # returned == written
    for field in ("report_version", "matchups", "paired_delta", "strata", "checkpoints",
                  "aivat", "verdict"):
        assert field in report
    assert report["verdict"] in ("pass", "fail", "inconclusive")
    assert report["aivat"] is None
    assert len(report["matchups"]) == 2                           # one opponent x 2 seats
    assert report["strata"] and {c["name"] for c in report["strata"]} == {"high-swing", "low-swing"}


@pytest.mark.req("REQ-SIM-0022")
def test_run_eval_resume_writes_nothing_new(tmp_path):
    """A second call with the same run_id and resume=True reuses each completed cell's tally from
    the manifest — no new films, identical report (disk/manifest are authoritative)."""
    from sim.eval_run import run_eval
    kw = dict(run_id="e2", created_at="2026-07-19T00:00:00", git_rev="abc1234",
              candidate=_mega(), baseline=_mega(), opponents={"mega_starmie": _mega()},
              out_root=tmp_path, per_cell=2, extra_syspath=SRC)
    first = run_eval(**kw)
    films_after_first = sorted((tmp_path / "eval" / "e2").rglob("*.json.gz"))
    second = run_eval(resume=True, **kw)
    films_after_second = sorted((tmp_path / "eval" / "e2").rglob("*.json.gz"))
    assert films_after_second == films_after_first                # resume added nothing
    assert second["matchups"] == first["matchups"]                # same tallies reused


@pytest.mark.req("REQ-SIM-0022")
def test_run_eval_cap_halts_the_run(tmp_path):
    """A max_games cap stops the run mid-matrix and marks the manifest capped (the disk safety
    valve, same intent as corpus)."""
    from sim.eval_run import run_eval
    run_eval(run_id="e3", created_at="2026-07-19T00:00:00", git_rev="abc1234",
             candidate=_mega(), baseline=_mega(),
             opponents={"a": _mega(), "b": _mega(), "c": _mega()}, out_root=tmp_path,
             per_cell=2, caps={"max_games": 2}, extra_syspath=SRC)
    manifest = json.loads((tmp_path / "eval" / "e3" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "capped"
    assert manifest["totals"]["games"] < 3 * 2 * 2                # halted before the full matrix


@pytest.mark.req("REQ-SIM-0022")
def test_run_cell_records_arm_crash(tmp_path):
    """A crashing arm (the crasher fixture, borrowing mega's deck as test_battle does) is counted
    and flagged — feeding candidate_crashes, which blocks a verdict pass."""
    from sim.eval_run import run_cell
    from sim.eval_report import build_report
    from sim.battle import read_deck
    crasher = FIXTURE_AGENTS / "crasher"
    deck = read_deck(MEGA)
    result = run_cell(crasher, MEGA, deck, deck, 2, extra_syspath=SRC)
    assert result["crashes"] == 2                                 # every game: the arm crashed
    # a positive paired delta that nonetheless carries candidate crashes must not pass
    rep = build_report(baseline={}, candidate={},
                       matchups=[{"opponent": "o", "seat": 0, "n": 2000,
                                  "candidate_wins": 1100, "baseline_wins": 1000, "draws": 0}],
                       candidate_crashes=result["crashes"])
    assert rep["verdict"] == "inconclusive"
