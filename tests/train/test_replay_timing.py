import gzip
import json
from pathlib import Path
import subprocess
import sys
import pytest

from sim.record import MatchRecorder
from sim.artifacts import save_legacy_telemetry
from train import replay_timing
from train.replay_timing import analyze_directory, format_report


REPO = Path(__file__).resolve().parents[2]


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
    save_legacy_telemetry(tmp_path, 42, [
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


def test_replay_timing_builds_each_replays_decision_index_once(tmp_path, monkeypatch):
    recorder = MatchRecorder()
    for frame in range(8):
        recorder.step(_obs(frame % 2, str(frame)), [0])
    recorder.finish({"current": {"result": 0}, "select": None}, winner=0)
    replay = recorder.replay(episode_id=99, team_names=["a", "b"])
    (tmp_path / "99.json").write_text(json.dumps(replay), encoding="utf-8")
    original = replay_timing.iter_decisions
    calls = 0

    def counted(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(replay_timing, "iter_decisions", counted)

    assert analyze_directory(tmp_path)["decision_count"] == 8
    assert calls == 1


def test_blunder_correction_direct_cli_has_no_deprecated_runtime_dependency():
    completed = subprocess.run(
        [sys.executable, str(REPO / "tools" / "train" / "blunder_correction.py"), "--help"],
        cwd=REPO, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stderr
    assert "replay" in completed.stdout
