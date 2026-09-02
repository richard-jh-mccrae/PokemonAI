import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO = Path(__file__).resolve().parents[2]


def test_teacher_review_plan_is_seeded_balanced_and_repeatable():
    from sim.teacher_review_run import plan_teacher_review_run

    first = plan_teacher_review_run(
        focal="mega_starmie", opponents=("dragapult_ex", "mega_lucario"),
        matches=5, seed=654, run_identity="run")
    second = plan_teacher_review_run(
        focal="mega_starmie", opponents=("dragapult_ex", "mega_lucario"),
        matches=5, seed=654, run_identity="run")

    assert first == second
    assert {slot.opponent for slot in first} == {"dragapult_ex", "mega_lucario"}
    assert abs(sum(slot.focal_seat == 0 for slot in first)
               - sum(slot.focal_seat == 1 for slot in first)) <= 1
    assert len({slot.episode_id for slot in first}) == 5
    assert len({slot.teacher_seed for slot in first}) == 5


@pytest.mark.parametrize("opponents", [(), ("dragapult_ex", "dragapult_ex")])
def test_teacher_review_plan_rejects_an_invalid_opponent_pool(opponents):
    from sim.teacher_review_run import plan_teacher_review_run

    with pytest.raises(ValueError):
        plan_teacher_review_run(
            focal="mega_starmie", opponents=opponents, matches=1,
            seed=1, run_identity="run")


def test_teacher_review_jobs_leave_two_cores_but_never_exceed_eight(monkeypatch):
    from sim.teacher_review_run import default_jobs

    monkeypatch.setattr(os, "cpu_count", lambda: 10)
    assert default_jobs() == 8
    monkeypatch.setattr(os, "cpu_count", lambda: 32)
    assert default_jobs() == 8
    monkeypatch.setattr(os, "cpu_count", lambda: 2)
    assert default_jobs() == 1


def test_teacher_review_manifest_persists_full_plan_before_play(tmp_path):
    from cgpy.experiment import TeacherSearchConfiguration
    from sim.teacher_review_run import ReviewExecutionConfiguration, create_teacher_review_run

    run_dir = create_teacher_review_run(
        output_root=tmp_path, run_id="teacher-run", created_at="2026-09-02T00:00:00+00:00",
        focal="mega_starmie", opponents=("dragapult_ex",), matches=2,
        seed=654, jobs=8, source_identity={"commit": "abc", "dirty": False},
        contestant_identities={
            "mega_starmie": {"deck_sha256": "focal"},
            "dragapult_ex": {"deck_sha256": "opponent"},
        },
        baseline={"path": "baseline/manifest.json", "baseline_id": "frozen"},
        teacher={
            "identity": "teacher-v1", "evaluator_identity": "ledger-v1",
            "evaluation_model_identity": "model-v1",
        },
        search=TeacherSearchConfiguration(time_cap_seconds=2.0),
        execution=ReviewExecutionConfiguration(
            root_timeout_seconds=3.0, opponent_timeout_seconds=1.0,
            match_timeout_seconds=10.0, max_bytes=1000, agents_root=tmp_path),
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "teacher.review-run"
    assert manifest["status"] == "planned"
    assert manifest["jobs"] == {
        "requested": 8, "effective": 8, "maximum": 8, "scope": "root_actions"}
    assert manifest["teacher"]["search"]["time_cap_seconds"] == 2.0
    assert manifest["execution"]["root_timeout_seconds"] == 3.0
    assert [slot["status"] for slot in manifest["slots"]] == ["planned", "planned"]


def test_teacher_review_execution_is_transactional_and_resumable(tmp_path):
    from cgpy.experiment import TeacherSearchConfiguration
    from sim.teacher_review_run import (
        ReviewExecutionConfiguration, create_teacher_review_run, execute_teacher_review_run,
    )

    run_dir = create_teacher_review_run(
        output_root=tmp_path, run_id="teacher-run", created_at="now", focal="mega_starmie",
        opponents=("dragapult_ex",), matches=2, seed=1, jobs=2,
        source_identity={"commit": "abc", "dirty": False},
        contestant_identities={
            "mega_starmie": {"deck_sha256": "focal"},
            "dragapult_ex": {"deck_sha256": "opponent"},
        },
        baseline={"path": "baseline/manifest.json", "baseline_id": "frozen"},
        teacher={"identity": "teacher", "evaluator_identity": "ledger",
                 "evaluation_model_identity": "model"},
        search=TeacherSearchConfiguration(time_cap_seconds=2.0),
        execution=ReviewExecutionConfiguration(3.0, 1.0, 10.0, 1000, tmp_path),
    )
    calls = []

    def complete(slot):
        calls.append(slot["index"])
        return {
            "index": slot["index"], "status": "complete", "bytes": 10,
            "replay_path": f"episodes/{slot['episode_id']}/replay.json.gz",
            "search_count": 2,
        }

    manifest = execute_teacher_review_run(
        run_dir=run_dir, verify_inputs=False, slot_worker=complete)
    assert manifest["status"] == "complete"
    assert manifest["totals"] == {"planned": 2, "complete": 2, "failed": 0, "bytes": 20}
    assert calls == [0, 1]
    assert len(list((run_dir / "results").glob("*.json"))) == 2

    resumed = execute_teacher_review_run(
        run_dir=run_dir, verify_inputs=False,
        slot_worker=lambda _slot: pytest.fail("completed slot reran"))
    assert resumed == manifest


def test_teacher_review_retries_failed_slots_but_not_completed_slots(tmp_path):
    from cgpy.experiment import TeacherSearchConfiguration
    from sim.teacher_review_run import (
        ReviewExecutionConfiguration, create_teacher_review_run, execute_teacher_review_run,
    )

    run_dir = create_teacher_review_run(
        output_root=tmp_path, run_id="teacher-run", created_at="now",
        focal="mega_starmie", opponents=("dragapult_ex",), matches=2,
        seed=1, jobs=2, source_identity={"commit": "abc", "dirty": False},
        contestant_identities={"mega_starmie": {}, "dragapult_ex": {}},
        baseline={"path": "baseline/manifest.json", "baseline_id": "frozen"},
        teacher={"identity": "teacher", "evaluator_identity": "ledger",
                 "evaluation_model_identity": "model"},
        search=TeacherSearchConfiguration(time_cap_seconds=2.0),
        execution=ReviewExecutionConfiguration(3.0, 1.0, 10.0, 1000, tmp_path),
    )

    first = execute_teacher_review_run(
        run_dir=run_dir, verify_inputs=False,
        slot_worker=lambda slot: {
            "index": slot["index"],
            "status": "failed" if slot["index"] == 0 else "complete",
            "bytes": 0 if slot["index"] == 0 else 10,
            "replay_path": f"episodes/{slot['episode_id']}/replay.json.gz",
            "search_count": 1,
        })
    rerun = []

    second = execute_teacher_review_run(
        run_dir=run_dir, verify_inputs=False,
        slot_worker=lambda slot: (
            rerun.append(slot["index"]) or {
                "index": slot["index"], "status": "complete", "bytes": 10,
                "replay_path": f"episodes/{slot['episode_id']}/replay.json.gz",
                "search_count": 1,
            }))

    assert first["status"] == "failed"
    assert rerun == [0]
    assert second["status"] == "complete"


def test_teacher_review_storage_cap_stops_starting_new_slots(tmp_path):
    from cgpy.experiment import TeacherSearchConfiguration
    from sim.teacher_review_run import (
        ReviewExecutionConfiguration, create_teacher_review_run, execute_teacher_review_run,
    )

    run_dir = create_teacher_review_run(
        output_root=tmp_path, run_id="teacher-run", created_at="now",
        focal="mega_starmie", opponents=("dragapult_ex",), matches=2,
        seed=1, jobs=1, source_identity={"commit": "abc", "dirty": False},
        contestant_identities={"mega_starmie": {}, "dragapult_ex": {}},
        baseline={"path": "baseline/manifest.json", "baseline_id": "frozen"},
        teacher={"identity": "teacher", "evaluator_identity": "ledger",
                 "evaluation_model_identity": "model"},
        search=TeacherSearchConfiguration(time_cap_seconds=2.0),
        execution=ReviewExecutionConfiguration(3.0, 1.0, 10.0, 10, tmp_path),
    )
    calls = []

    manifest = execute_teacher_review_run(
        run_dir=run_dir, verify_inputs=False,
        slot_worker=lambda slot: (
            calls.append(slot["index"]) or {
                "index": slot["index"], "status": "complete", "bytes": 10,
                "replay_path": f"episodes/{slot['episode_id']}/replay.json.gz",
                "search_count": 1,
            }))

    assert calls == [0]
    assert manifest["status"] == "capped"
    assert manifest["totals"] == {
        "planned": 2, "complete": 1, "failed": 0, "bytes": 10,
    }


def test_teacher_review_directory_is_directly_accepted_by_blunder_viewer(tmp_path):
    from sim.record import MatchRecorder
    from train.blunder.batch import discover_replays, load_game_summary
    from train.corpus.io import write_gzip_jsonl

    episode = tmp_path / "episodes" / "42"
    episode.mkdir(parents=True)
    obs = {"current": {"yourIndex": 1, "turn": 1},
           "select": {"context": 0, "option": [{"type": 14}]}}
    recorder = MatchRecorder()
    recorder.step(obs, [0])
    recorder.finish({"current": {"result": 1}, "select": None}, 1)
    replay = recorder.replay(episode_id=42, team_names=["opponent", "mega_starmie"])
    replay_path = episode / "replay.json.gz"
    write_gzip_jsonl(replay_path, [replay])
    (tmp_path / "manifest.json").write_text(json.dumps({
        "schema": "teacher.review-run", "run_id": "run-1", "created_at": "now",
        "focal": "mega_starmie", "source_identity": {"commit": "abc"},
        "slots": [{"index": 0, "episode_id": 42, "focal_seat": 1,
                   "status": "complete", "replay_path": "episodes/42/replay.json.gz"}],
    }), encoding="utf-8")

    assert discover_replays(tmp_path) == [replay_path]
    summary = load_game_summary(replay_path)
    assert summary["live_seat"] == 1
    assert summary["agent"] == "mega_starmie"
    assert summary["agent_build"] == "run-1"
    assert summary["agent_version"] == "abc"


def test_teacher_review_cli_exposes_the_bounded_search_contract():
    completed = subprocess.run(
        [sys.executable, str(REPO / "tools" / "sim" / "teacher_review_run.py"), "--help"],
        cwd=REPO, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stderr
    for option in (
            "--jobs", "--opponents", "--teacher-time-cap", "--teacher-root-timeout",
            "--teacher-node-cap", "--teacher-path-node-cap",
            "--teacher-chance-branch-cap", "--teacher-exact-outcome-limit",
            "--teacher-chance-samples", "--opponent-decision-timeout", "--match-timeout"):
        assert option in completed.stdout


def test_teacher_review_cli_runs_a_match_and_feeds_the_blunder_viewer(tmp_path):
    from train.blunder.batch import discover_replays, load_game_summary

    baseline = next((REPO / "data" / "ledger-baselines").glob("*/manifest.json"))
    agents = REPO / "tests" / "fixtures" / "teacher_review_agents"
    completed = subprocess.run([
        sys.executable, str(REPO / "tools" / "sim" / "teacher_review_run.py"),
        "mega_starmie", "-n", "1", "--jobs", "2", "--opponents", "quick_opponent",
        "--seed", "654", "--agents-root", str(agents), "--out", str(tmp_path),
        "--ledger-baseline", str(baseline), "--teacher-time-cap", "30",
        "--teacher-root-timeout", "40", "--teacher-node-cap", "2000",
        "--teacher-path-node-cap", "64", "--teacher-chance-branch-cap", "2000",
        "--teacher-chance-samples", "3", "--opponent-decision-timeout", "20",
        "--match-timeout", "120", "--allow-dirty",
    ], cwd=REPO, text=True, capture_output=True, timeout=150, check=False)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    run_dir, = tuple(path for path in tmp_path.iterdir() if path.is_dir())
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert manifest["jobs"] == {
        "requested": 2, "effective": 2, "maximum": 8, "scope": "root_actions"}
    replay, = discover_replays(run_dir)
    summary = load_game_summary(replay)
    assert summary["agent"] == "mega_starmie"
    assert summary["live_seat"] == manifest["slots"][0]["focal_seat"]


def test_teacher_identity_gate_accepts_only_the_frozen_evaluator_and_model():
    from sim.teacher_review_run import require_teacher_identities

    identities = SimpleNamespace(
        baseline="frozen", evaluator="ledger-v1", evaluation_models=("model-a", "model-b"))
    require_teacher_identities(identities, evaluator="ledger-v1", evaluation_model="model-a")
    with pytest.raises(ValueError, match="evaluator"):
        require_teacher_identities(
            identities, evaluator="other", evaluation_model="model-a")
    with pytest.raises(ValueError, match="Evaluation Model"):
        require_teacher_identities(
            identities, evaluator="ledger-v1", evaluation_model="other")
