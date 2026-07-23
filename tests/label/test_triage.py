"""triage — consecutive-decision Φ-deltas that RANK but never emit (S3a design §D2).

A drop across a seat's own MAIN decisions folds in the opponent's reply and coin luck, so triage is
a prefilter (fork-budget ranking + the played-well-lost full-coverage screen), never a Correction.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]


def _rec(seat, frame, v, context=0, agent="ms", episode_id=1, turn=1):
    return {"episode_id": episode_id, "frame": frame, "seat": seat, "turn": turn,
            "agent": agent, "v": v, "context": context}


@pytest.mark.req("REQ-LABEL-0002")
def test_drops_are_per_seat_consecutive_over_main_decisions():
    from train.label.triage import triage_drops

    # seat 0 MAIN decisions at frames 0,4,8 with V 0.6→0.5→0.2; seat 1 interleaved and irrelevant.
    recs = [_rec(0, 0, 0.6), _rec(1, 2, 0.9), _rec(0, 4, 0.5), _rec(1, 6, 0.1), _rec(0, 8, 0.2)]
    drops = triage_drops(recs)
    s0 = [d for d in drops if d["seat"] == 0]
    assert [d["frame"] for d in s0] == [0, 4]                    # last decision has no successor
    assert s0[0]["drop"] == pytest.approx(0.1)                   # 0.6 → 0.5
    assert s0[1]["drop"] == pytest.approx(0.3)                   # 0.5 → 0.2 (skips seat-1 frames)
    assert s0[0]["frame_next"] == 4 and s0[1]["frame_next"] == 8


@pytest.mark.req("REQ-LABEL-0002")
def test_non_main_contexts_are_excluded():
    from train.label.triage import triage_drops

    recs = [_rec(0, 0, 0.8), _rec(0, 2, 0.7, context=3), _rec(0, 4, 0.4)]  # frame 2 is a SWITCH
    drops = triage_drops(recs)
    assert [d["frame"] for d in drops] == [0]                    # 0.8 → 0.4 across the two MAINs
    assert drops[0]["drop"] == pytest.approx(0.4)


@pytest.mark.req("REQ-LABEL-0002")
def test_rank_by_drop_thresholds_and_orders():
    from train.label.triage import rank_by_drop

    drops = [{"drop": 0.02}, {"drop": 0.30}, {"drop": 0.11}, {"drop": -0.05}]
    ranked = rank_by_drop(drops, theta_triage=0.10)
    assert [d["drop"] for d in ranked] == [0.30, 0.11]           # ≥ θ, descending; gains dropped


@pytest.mark.req("REQ-LABEL-0002")
def test_triage_over_a_real_film_is_outcome_blind(ms_pilot, one_replay, seed_model):
    """Runs end-to-end off vread records; both seats (both ours) produce drops regardless of who won."""
    from train.label.triage import triage_drops
    from train.label.vread import iter_values

    recs = list(iter_values(ms_pilot, one_replay, seed_model))
    drops = triage_drops(recs)
    assert drops                                                 # a real game yields consecutive MAINs
    assert {d["seat"] for d in drops} <= {0, 1}
    for d in drops:
        assert d["drop"] == pytest.approx(d["v"] - d["v_next"])
