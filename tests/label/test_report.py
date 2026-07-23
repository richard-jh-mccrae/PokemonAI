"""played-well-lost — the report view over lost games (S3a design §D6). A REPORT, never Corrections."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


@pytest.mark.req("REQ-LABEL-0006")
def test_assess_only_the_losing_seat_over_a_real_game(ms_pilot, one_replay, seed_model):
    from meta_tracker.parse import winner_index
    from train.label.report import assess_replay

    winner = winner_index(one_replay)
    assert winner is not None, "the fixture game is decisive"
    recs = assess_replay(ms_pilot, one_replay, seed_model, theta=0.15, theta_triage=0.03)
    assert len(recs) == 1                                        # exactly the losing seat
    r = recs[0]
    assert r["seat"] == (1 - winner)
    assert r["agent"] == "mega_starmie" and r["opponent"] == "mega_starmie"   # mirror corpus
    assert r["n_decisions"] > 0
    assert r["verdict"] in {"clean", "blundered"}
    assert r["n_confirmed"] <= r["n_triage_hits"]               # confirmation is a subset of hits


@pytest.mark.req("REQ-LABEL-0006")
def test_draw_carries_no_loss(ms_pilot, seed_model, monkeypatch):
    from train.label import report

    monkeypatch.setattr(report, "winner_index", lambda _r: None)   # simulate a draw
    assert report.assess_replay(ms_pilot, {"info": {}}, seed_model, theta=0.1, theta_triage=0.03) == []


@pytest.mark.req("REQ-LABEL-0006")
def test_aggregate_clean_loss_rate():
    from train.label.report import aggregate

    a = [
        {"agent": "ms", "opponent": "ml", "verdict": "clean"},
        {"agent": "ms", "opponent": "ml", "verdict": "blundered"},
        {"agent": "ms", "opponent": "ml", "verdict": "clean"},
        {"agent": "ms", "opponent": "dp", "verdict": "blundered"},
    ]
    agg = aggregate(a)
    assert agg["ms vs ml"] == {"losses": 3, "clean": 2, "clean_loss_rate": pytest.approx(2 / 3)}
    assert agg["ms vs dp"]["clean_loss_rate"] == 0.0


@pytest.mark.req("REQ-LABEL-0006")
def test_clean_verdict_when_no_triage_hits(ms_pilot, one_replay, seed_model):
    """A huge theta_triage → no hits to confirm → every loss reads clean (played-well-lost). Proves
    the screen, not the outcome, drives the verdict."""
    from train.label.report import assess_replay

    recs = assess_replay(ms_pilot, one_replay, seed_model, theta=0.15, theta_triage=99.0)
    assert recs and all(r["verdict"] == "clean" and r["n_triage_hits"] == 0 for r in recs)
