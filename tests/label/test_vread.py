"""vread — the shared per-decision P(win) reader (S3a design §D5; the S2b/AIVAT coordination point).

One record per own decision frame, computed on the aligned obs via the same ``pilot._board`` path
``value.extract`` uses (zero train/serve skew). The frozen record shape is a cross-track contract;
a null model must fail LOUD offline (the inverse of the fail-open runtime).
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

# The frozen shape S2b's AIVAT stub consumes (S3a design §D5). Additive fields (e.g. `context`) are
# non-breaking; these six are the contract.
FROZEN_KEYS = {"episode_id", "frame", "seat", "turn", "agent", "v"}


@pytest.mark.req("REQ-LABEL-0001")
def test_iter_values_yields_frozen_shape_over_own_decisions(ms_pilot, one_replay, seed_model):
    from train.label.vread import iter_values

    records = list(iter_values(ms_pilot, one_replay, seed_model))
    assert records, "a real game has many own decision frames"
    for r in records:
        assert FROZEN_KEYS <= set(r), f"record missing frozen keys: {FROZEN_KEYS - set(r)}"
        assert isinstance(r["frame"], int) and isinstance(r["seat"], int)
        assert 0.0 <= r["v"] <= 1.0
        assert r["agent"] == "mega_starmie"           # bare name parsed from corpus TeamNames
        assert r["episode_id"] == (one_replay.get("info") or {}).get("EpisodeId")
    frames = [r["frame"] for r in records]
    assert frames == sorted(frames)                    # film order


@pytest.mark.req("REQ-LABEL-0001")
def test_values_match_extract_path_exactly(ms_pilot, one_replay, seed_model):
    """vread must compute V on the SAME board/obs value.extract trains on — identical features →
    identical predictions, or training and labeling silently diverge."""
    from common.value.features import features_from_board
    from train.label.vread import iter_values
    from train.value.extract import rows_from_replay

    extract_feats = [f for f, _ in rows_from_replay(ms_pilot, one_replay)]
    vread_v = [r["v"] for r in iter_values(ms_pilot, one_replay, seed_model)]
    assert len(extract_feats) == len(vread_v)          # same decision-frame set
    expected = [seed_model.predict(f) for f in extract_feats]
    assert vread_v == pytest.approx(expected)


@pytest.mark.req("REQ-LABEL-0001")
def test_null_model_fails_loud_offline(ms_pilot, one_replay):
    """Runtime is fail-open (null → 0.5); offline a null model would emit v=0.5 everywhere — zero
    signal dressed as data. vread raises instead."""
    from common.value.model import ValueModel
    from train.label.vread import iter_values

    null = ValueModel.load(REPO / "does_not_exist_xyz.json")
    assert null.present is False
    with pytest.raises(ValueError):
        list(iter_values(ms_pilot, one_replay, null))


@pytest.mark.req("REQ-LABEL-0001")
def test_agent_name_parses_corpus_and_ladder_teamnames():
    from train.label.vread import agent_name_for_seat

    corpus = {"info": {"TeamNames": ["ms__ml#0-ms", "ms__ml#1-mega_lucario"]}}
    assert agent_name_for_seat(corpus, 0) == "ms"
    assert agent_name_for_seat(corpus, 1) == "mega_lucario"   # underscores in the bare name survive
    ladder = {"info": {"TeamNames": ["SkiChu", "Pablo"]}}      # real ladder: plain names, no '#'
    assert agent_name_for_seat(ladder, 0) == "SkiChu"
    assert agent_name_for_seat(ladder, 9) is None             # out-of-range seat → None, never crash
