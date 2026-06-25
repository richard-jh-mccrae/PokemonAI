"""Append-only JSONL store for Corrections."""
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.correction import build_correction
from train.blunder.decisions import iter_decisions
from train.blunder.store import append_correction, delete_correction, load_corrections

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def _corr(category="missed_win", correct=(4,)):
    d = next(x for x in iter_decisions(load_replay(FIXTURE)) if x.select_context == "Main")
    return build_correction(d, source="own", agent="mega_starmie",
                            correct=list(correct), category=category, rationale="r")


def test_append_then_load_roundtrips(tmp_path):
    """REQ-BLUNDER-0006: a Correction appended to the log loads back equal."""
    path = tmp_path / "corrections.jsonl"
    c1 = _corr("missed_win")
    append_correction(c1, path)
    loaded = load_corrections(path)
    assert len(loaded) == 1 and loaded[0] == c1


def test_append_grows_log_without_clobbering(tmp_path):
    """REQ-BLUNDER-0006: each append adds a line; the log accumulates in order."""
    path = tmp_path / "corrections.jsonl"
    append_correction(_corr("missed_win"), path)
    append_correction(_corr("overextension"), path)
    assert [c.category for c in load_corrections(path)] == ["missed_win", "overextension"]


def test_load_missing_file_is_empty(tmp_path):
    """REQ-BLUNDER-0006: loading a non-existent log yields an empty list, not an error."""
    assert load_corrections(tmp_path / "nope.jsonl") == []


def test_delete_correction_removes_by_id(tmp_path):
    """REQ-BLUNDER-0013: a logged Correction can be removed by id (review list edit/remove)."""
    path = tmp_path / "corrections.jsonl"
    a, b = _corr("missed_win"), _corr("overextension")
    append_correction(a, path)
    append_correction(b, path)
    removed = delete_correction(a.id, path)
    left = load_corrections(path)
    assert removed == 1 and [c.category for c in left] == ["overextension"]
