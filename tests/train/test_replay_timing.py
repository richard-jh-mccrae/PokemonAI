import gzip
import json
import pytest

from sim.record import MatchRecorder
from sim.selfplay import _save_telemetry
from train.replay_timing import analyze_directory, format_report


def _obs(seat, value):
    return {
        "current": {"yourIndex": seat, "turn": 2},
        "select": {"context": 0, "option": [{"type": 14, "value": value}]},
    }


def test_replay_timing_aggregates_explicit_samples_and_attributes_limit_hits(tmp_path):
    recorder = MatchRecorder()
    recorder.step(_obs(0, "a"), [0])
    recorder.step(_obs(1, "b"), [0])
    recorder.finish({"current": {"result": 0}, "select": None}, winner=0)
    replay = recorder.replay(episode_id=42, team_names=["a", "b"])
    replay["info"]["MatchWallSeconds"] = 3.0
    (tmp_path / "42.json").write_text(json.dumps(replay), encoding="utf-8")
    _save_telemetry(tmp_path, 42, [
        {"bellman": True, "chosen": [0], "seat": 0, "decision_seconds": 0.2,
         "decision_limit_seconds": 0.15, "deadline_hit": True},
        {"bellman": True, "chosen": [0], "seat": 1, "decision_seconds": 0.1,
         "decision_limit_seconds": 0.15, "deadline_hit": False},
    ])

    report = analyze_directory(tmp_path)

    assert report["match_time"] == {
        "count": 1, "missing": 0, "min": 3.0, "max": 3.0, "avg": 3.0}
    assert report["decision_time"]["avg"] == pytest.approx(0.15)
    assert report["decision_limit_hits"] == 1
    assert report["limit_hits"] == [{
        "match_id": "42", "frame_id": 0, "seat": 0,
        "decision_seconds": 0.2, "decision_limit_seconds": 0.15,
    }]
    text = format_report(report)
    assert "match time: 3.000s, 3.000s, 3.000s" in text
    assert "decision time limits hit: 1" in text
    assert "42-0" in text


def test_replay_timing_preserves_missing_match_and_decision_samples(tmp_path):
    recorder = MatchRecorder()
    recorder.step(_obs(0, "a"), [0])
    recorder.finish({"current": {"result": 0}, "select": None}, winner=0)
    replay = recorder.replay(episode_id=7, team_names=["a", "b"])
    (tmp_path / "7.json").write_text(json.dumps(replay), encoding="utf-8")

    report = analyze_directory(tmp_path)

    assert report["match_count"] == 1
    assert report["match_time"]["count"] == 0
    assert report["match_time"]["missing"] == 1
    assert report["decision_count"] == 1
    assert report["decision_time"]["missing"] == 1


def test_gz_replay_uses_double_suffix_timing_sidecar(tmp_path):
    recorder = MatchRecorder()
    recorder.finish({"current": {"result": 0}, "select": None}, winner=0)
    replay = recorder.replay(episode_id=None, team_names=["a", "b"])
    replay["info"].pop("EpisodeId", None)
    (tmp_path / "game.json.gz").write_bytes(gzip.compress(json.dumps(replay).encode()))
    (tmp_path / "game-timing.json").write_text(
        json.dumps({"match_wall_seconds": 2.5}), encoding="utf-8")
    assert analyze_directory(tmp_path)["match_time"]["avg"] == 2.5
