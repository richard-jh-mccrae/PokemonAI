"""Eval harness (tools/sim/eval_run, ADR-0053 WP2): the live matrix runner end-to-end, on a fixture
mirror. Cross-deck process isolation is covered by test_battle."""
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
    return {"label": "mega_starmie", "dir": MEGA, "deck": read_deck(MEGA), "overlay": None,
            "agent": "mega_starmie",
            "descriptor": {"agent": "mega_starmie", "label": "working-tree", "config": None}}


@pytest.mark.req("REQ-SIM-0022")
def test_run_eval_end_to_end_writes_manifest_films_and_c3_report(tmp_path):
    from sim.eval_run import run_eval
    cand = base = _mega()
    report = run_eval(run_id="e1", created_at="2026-07-19T00:00:00", git_rev="abc1234",
                      candidate=cand, baseline=base, opponents={"mega_starmie": _mega()},
                      out_root=tmp_path, per_cell=2, extra_syspath=SRC, preset="default")

    run_dir = tmp_path / "eval" / "e1"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete" and manifest["manifest_version"] == 1
    assert manifest["totals"]["games"] == 2 * 2                    # arms x per_cell

    films = list(run_dir.rglob("*.json.gz"))
    assert len(films) == 4 and all(f.suffix == ".gz" for f in films)

    saved = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert saved == report
    for field in ("report_version", "matchups", "paired_delta", "strata", "checkpoints",
                  "aivat", "verdict", "status", "coverage"):
        assert field in report
    assert report["verdict"] in ("pass", "fail", "inconclusive")
    assert report["status"] == "complete"
    assert report["candidate"]["agent"] == "mega_starmie" and "config" in report["candidate"]
    assert report["aivat"] is None
    assert len(report["matchups"]) == 2                           # one opponent, both seats
    assert report["strata"] and {c["name"] for c in report["strata"]} == {"high-swing", "low-swing"}


@pytest.mark.req("REQ-SIM-0022")
def test_capped_run_cannot_pass(tmp_path):
    """G2 must not adopt on a fraction of the powered matrix."""
    from sim.eval_run import run_eval
    report = run_eval(run_id="e4", created_at="2026-07-19T00:00:00", git_rev="abc1234",
                      candidate=_mega(), baseline=_mega(),
                      opponents={"a": _mega(), "b": _mega(), "c": _mega()}, out_root=tmp_path,
                      per_cell=2, caps={"max_games": 2}, extra_syspath=SRC)
    assert report["status"] == "capped"
    assert report["verdict"] == "inconclusive"


@pytest.mark.req("REQ-SIM-0022")
def test_run_eval_resume_writes_nothing_new(tmp_path):
    from sim.eval_run import run_eval
    kw = dict(run_id="e2", created_at="2026-07-19T00:00:00", git_rev="abc1234",
              candidate=_mega(), baseline=_mega(), opponents={"mega_starmie": _mega()},
              out_root=tmp_path, per_cell=2, extra_syspath=SRC)
    first = run_eval(**kw)
    films_after_first = sorted((tmp_path / "eval" / "e2").rglob("*.json.gz"))
    second = run_eval(resume=True, **kw)
    films_after_second = sorted((tmp_path / "eval" / "e2").rglob("*.json.gz"))
    assert films_after_second == films_after_first
    assert second["matchups"] == first["matchups"]                # completed cells reused


@pytest.mark.req("REQ-SIM-0022")
def test_run_eval_cap_halts_the_run(tmp_path):
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
    from sim.eval_run import run_cell
    from sim.eval_report import build_report
    from sim.battle import read_deck
    crasher = FIXTURE_AGENTS / "crasher"
    deck = read_deck(MEGA)
    result = run_cell(crasher, MEGA, deck, deck, 2, extra_syspath=SRC)
    assert result["crashes"] == 2
    # a positive paired delta carrying candidate crashes must not pass
    rep = build_report(baseline={}, candidate={},
                       matchups=[{"opponent": "o", "seat": 0, "n": 2000,
                                  "candidate_wins": 1100, "baseline_wins": 1000, "draws": 0}],
                       candidate_crashes=result["crashes"])
    assert rep["verdict"] == "inconclusive"
