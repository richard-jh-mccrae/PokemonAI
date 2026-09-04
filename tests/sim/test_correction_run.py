from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[2]


def test_correction_run_plan_is_reproducible_balanced_and_focal_owned():
    from sim.correction_run import plan_correction_run

    opponents = ("mega_starmie", "mega_lucario", "dragapult_ex")
    first = plan_correction_run(
        focal="mega_starmie", opponents=opponents, episodes=8, seed=73, heldout=2,
        run_identity="run-a")
    second = plan_correction_run(
        focal="mega_starmie", opponents=opponents, episodes=8, seed=73, heldout=2,
        run_identity="run-a")

    assert first == second
    assert all(slot.focal == "mega_starmie" for slot in first)
    assert len({slot.episode_id for slot in first}) == 8
    assert len({slot.engine_seed for slot in first}) == 8
    assert Counter(slot.partition for slot in first) == {"tuning": 6, "heldout": 2}

    opponent_counts = Counter(slot.opponent for slot in first)
    seat_counts = Counter(slot.focal_seat for slot in first)
    assert max(opponent_counts.values()) - min(opponent_counts.values()) <= 1
    assert max(seat_counts.values()) - min(seat_counts.values()) <= 1
    other = plan_correction_run(
        focal="mega_starmie", opponents=opponents, episodes=8, seed=73, heldout=2,
        run_identity="run-b")
    assert {slot.episode_id for slot in first}.isdisjoint(
        slot.episode_id for slot in other)


def test_correction_run_manifest_randomizes_a_single_opponent_from_the_pool(tmp_path):
    from sim.correction_run import create_correction_run

    run_dir = create_correction_run(
        output_root=tmp_path, run_id="random-opponent",
        created_at="2026-09-01T00:00:00+00:00", focal="mega_starmie",
        opponents=("dragapult_ex", "mega_lucario"), episodes=1, seed=1,
        heldout=0, jobs=1, engine="native",
        source_identity={"commit": "abc", "dirty": False},
        contestant_identities={
            "mega_starmie": {"deck_sha256": "starmie"},
            "dragapult_ex": {"deck_sha256": "dragapult"},
            "mega_lucario": {"deck_sha256": "lucario"},
        },
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["slots"][0]["opponent"] == "mega_lucario"


def test_correction_run_default_opponent_pool_excludes_the_focal_agent(tmp_path):
    from sim.correction_run import discover_opponents

    for name in ("dragapult_ex", "mega_lucario", "mega_starmie"):
        agent = tmp_path / name
        agent.mkdir()
        (agent / "main.py").touch()
        (agent / "deck.csv").touch()

    assert discover_opponents(tmp_path, "mega_starmie") == (
        "dragapult_ex", "mega_lucario")


def test_correction_run_plan_rejects_an_invalid_request():
    from sim.correction_run import plan_correction_run

    with pytest.raises(ValueError, match="episodes must be positive"):
        plan_correction_run(
            focal="ms", opponents=("ms",), episodes=0, seed=1, run_identity="run")
    with pytest.raises(ValueError, match="opponent pool is empty"):
        plan_correction_run(focal="ms", opponents=(), episodes=1, seed=1, run_identity="run")
    with pytest.raises(ValueError, match="heldout"):
        plan_correction_run(
            focal="ms", opponents=("ms",), episodes=1, seed=1, heldout=2,
            run_identity="run")


def test_correction_run_manifest_persists_the_complete_plan_before_play(tmp_path):
    from sim.correction_run import ExecutionConfig, create_correction_run

    run_dir = create_correction_run(
        output_root=tmp_path,
        run_id="run-1",
        created_at="2026-08-25T00:00:00+00:00",
        focal="mega_starmie",
        opponents=("mega_starmie", "mega_lucario", "dragapult_ex"),
        episodes=5,
        seed=91,
        heldout=1,
        jobs=3,
        engine="cgpy",
        source_identity={"commit": "abc", "dirty": False},
        contestant_identities={
            "mega_starmie": {"deck_sha256": "deck"},
            "mega_lucario": {"deck_sha256": "lucario"},
            "dragapult_ex": {"deck_sha256": "dragapult"},
        },
        execution=ExecutionConfig(120.0, 1800.0, 1024, tmp_path / "agents"),
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "ledger.correction-run"
    assert manifest["status"] == "planned"
    assert manifest["focal"] == "mega_starmie"
    assert manifest["opponents"] == ["mega_starmie", "mega_lucario", "dragapult_ex"]
    assert manifest["engine"] == {"kind": "cgpy", "seeded": True}
    assert manifest["ledger"]["feature_schema_version"] > 0
    assert len(manifest["ledger"]["global_configuration_sha256"]) == 64
    assert len(manifest["ledger"]["ledger_source_sha256"]) == 64
    assert manifest["source_identity"] == {"commit": "abc", "dirty": False}
    assert manifest["contestants"]["mega_starmie"] == {"deck_sha256": "deck"}
    assert manifest["execution"] == {
        "decision_timeout": 120.0, "episode_timeout": 1800.0, "max_bytes": 1024,
        "agents_root": str(tmp_path / "agents"),
    }
    assert len(manifest["slots"]) == 5
    assert sum(slot["partition"] == "heldout" for slot in manifest["slots"]) == 1
    assert all(slot["status"] == "planned" for slot in manifest["slots"])


def test_correction_run_audit_accepts_declared_pregame_and_complete_ledger_records():
    from sim.correction_run import audit_correction_records

    records = [
        {"record_type": "decision", "record_id": "pre", "decision": {
            "variant": "declarative_pregame", "turn": 0}},
        {"record_type": "decision", "record_id": "ledger", "decision": {
            "variant": "ledger", "turn": 1, "policy_reason": "positive_continuation",
            "chosen_action_id": "a"}, "completeness": "complete",
         "candidates": [{"action_id": "a", "gaps": []}],
         "behavior_identity": {"evaluator": "ledger-linear-v1"},
         "search": {"failure": None}},
        {"record_type": "outcome", "record_id": "outcome"},
    ]

    summary = audit_correction_records(records)

    assert summary["ledger_decisions"] == 1
    assert summary["pregame_decisions"] == 1
    assert summary["selected_chain_caps"] == []
    assert summary["incomplete_decisions"] == []
    assert len(summary["behavior_identities"]) == 1


def test_correction_run_audit_accepts_a_forced_unpriced_singleton():
    from sim.correction_run import audit_correction_records

    record = {"record_type": "decision", "record_id": "forced", "decision": {
        "variant": "ledger", "turn": 1, "policy_reason": "forced",
        "chosen_action_id": "a"}, "completeness": "unavailable",
        "candidates": [{"action_id": "a", "status": "unavailable", "gaps": []}],
        "behavior_identity": {"evaluator": "ledger-linear-v1"},
        "search": {"failure": None}}

    summary = audit_correction_records([record])

    assert summary["ledger_decisions"] == 1
    assert summary["forced_unpriced_decisions"] == ["forced"]
    assert summary["incomplete_decisions"] == []


@pytest.mark.parametrize("policy_reason", ("best_delta", "forced"))
def test_correction_run_audit_rejects_a_private_alternative_even_when_the_chosen_action_is_priced(policy_reason):
    from sim.correction_run import audit_correction_records

    record = {"record_type": "decision", "record_id": "private-alternative", "decision": {
        "variant": "ledger", "turn": 1, "policy_reason": policy_reason, "chosen_action_id": "end"},
        "completeness": "unavailable", "search": {"failure": None},
        "candidates": [{"action_id": "end", "status": "complete", "gaps": []},
                       {"action_id": "attack", "status": "unavailable", "successors": [], "gaps": [
                           "unpriceable: private opponent selection unavailable (focal information boundary)"]}],
        "behavior_identity": {"evaluator": "ledger-linear-v1"}}

    with pytest.raises(ValueError, match="^unavailable Ledger decision entered Correction Run: unavailable$"):
        audit_correction_records([record])


def test_correction_run_audit_requires_one_decision_record_per_replay_choice():
    from sim.correction_run import audit_correction_records
    from sim.record import MatchRecorder

    recorder = MatchRecorder()
    recorder.step({"current": {"yourIndex": 0, "turn": 1},
                   "select": {"context": 0, "option": [{"type": 14}]}}, [0])
    recorder.finish({"current": {"result": 0}, "select": None}, 0)
    replay = recorder.replay(episode_id=1, team_names=["a", "b"])
    with pytest.raises(ValueError, match="telemetry does not cover every replay choice"):
        audit_correction_records([], replay=replay)


def test_correction_run_audit_rejects_declarative_policy_after_setup():
    from sim.correction_run import audit_correction_records

    with pytest.raises(ValueError, match="after setup"):
        audit_correction_records([{"record_type": "decision", "decision": {
            "variant": "declarative_pregame", "turn": 1}}])


def test_correction_run_audit_couples_each_replay_choice_exactly():
    from sim.correction_run import audit_correction_records
    from sim.record import MatchRecorder

    recorder = MatchRecorder()
    recorder.step({"current": {"yourIndex": 0, "turn": 1},
                   "select": {"context": 0, "option": [{"type": 14}, {"type": 14}]}}, [1])
    recorder.finish({"current": {"result": 0}, "select": None}, 0)
    replay = recorder.replay(episode_id=1, team_names=["a", "b"])
    record = {"record_type": "decision", "record_id": "ledger", "decision": {
        "variant": "ledger", "seat": 0, "turn": 1, "selection": [0],
        "policy_reason": "best_delta", "chosen_action_id": "a"},
        "observation": {"select_context": 0}, "completeness": "complete",
        "candidates": [{"action_id": "a", "gaps": []}],
        "behavior_identity": {"evaluator": "ledger-v1"}, "search": {"failure": None}}

    with pytest.raises(ValueError, match="selection"):
        audit_correction_records([record], replay=replay)


def test_correction_run_audit_keeps_numeric_context_from_the_legal_observation():
    from sim.correction_run import audit_correction_records
    from sim.record import MatchRecorder

    obs = {"current": {"yourIndex": 0, "turn": 1},
           "select": {"context": 0, "option": [{"type": 14}, {"type": 14}]}}
    recorder = MatchRecorder()
    recorder.step(obs, [1])
    recorder.finish({"current": {"result": 0}, "select": None}, 0, visualizer=[
        {"current": {"turn": 1},
         "select": {"context": "Main", "option": [{"type": 14}, {"type": 14}]}},
        {"current": {"result": 0}},
    ])
    replay = recorder.replay(episode_id=1, team_names=["a", "b"])
    record = {"record_type": "decision", "record_id": "ledger", "decision": {
        "variant": "ledger", "seat": 0, "turn": 1, "selection": [1],
        "policy_reason": "best_delta", "chosen_action_id": "a"},
        "observation": {"select_context": 0}, "completeness": "complete",
        "candidates": [{"action_id": "a", "gaps": []}],
        "behavior_identity": {"evaluator": "ledger-v1"}, "search": {"failure": None}}

    summary = audit_correction_records([record], replay=replay)

    assert summary["ledger_decisions"] == 1


@pytest.mark.parametrize("record, message", [
    ({"record_type": "decision", "decision": {"variant": "legacy"}},
     "unknown decision variant"),
    ({"record_type": "decision", "decision": {
        "variant": "ledger", "policy_reason": "fail_safe_provider_failure",
        "chosen_action_id": "a"}, "completeness": "complete", "candidates": [],
      "behavior_identity": {}, "search": {"failure": None}}, "fail-safe"),
    ({"record_type": "decision", "decision": {
        "variant": "ledger", "policy_reason": "best_delta", "chosen_action_id": "a"},
      "completeness": "unavailable", "candidates": [], "behavior_identity": {},
      "search": {"failure": {"stage": "provider"}}}, "unavailable"),
])
def test_correction_run_audit_rejects_unsafe_decision_evidence(record, message):
    from sim.correction_run import audit_correction_records

    with pytest.raises(ValueError, match=message):
        audit_correction_records([record])


def test_correction_run_execution_reconciles_slot_results_transactionally(tmp_path):
    from sim.correction_run import ExecutionConfig, create_correction_run, execute_correction_run

    run_dir = create_correction_run(
        output_root=tmp_path, run_id="run-2", created_at="2026-08-25T00:00:00+00:00",
        focal="mega_starmie", opponents=("mega_starmie", "mega_lucario"),
        episodes=3, seed=3, heldout=1, jobs=2, engine="native",
        source_identity={"commit": "abc", "dirty": False},
        contestant_identities={"mega_starmie": {"deck_sha256": "deck"},
                               "mega_lucario": {"deck_sha256": "other"}},
        execution=ExecutionConfig(10.0, 20.0, 1000, tmp_path))

    def complete(slot):
        return {
            "index": slot["index"], "status": "complete",
            "bundle_id": f"bundle-{slot['index']}", "bytes": 100 + slot["index"],
            "winner": slot["focal_seat"], "audit": {"ledger_decisions": 4},
        }

    manifest = execute_correction_run(
        run_dir=run_dir, agents_root=tmp_path, extra_syspath=(),
        decision_timeout=10.0, episode_timeout=20.0, max_bytes=1000,
        verify_inputs=False,
        slot_worker=complete)

    assert manifest["status"] == "complete"
    assert manifest["totals"] == {
        "planned": 3, "complete": 3, "failed": 0, "bytes": 303}
    assert [slot["bundle_id"] for slot in manifest["slots"]] == [
        "bundle-0", "bundle-1", "bundle-2"]
    assert len(list((run_dir / "results").glob("*.json"))) == 3

    resumed = execute_correction_run(
        run_dir=run_dir, agents_root=tmp_path, extra_syspath=(),
        decision_timeout=10.0, episode_timeout=20.0, max_bytes=1000,
        verify_inputs=False,
        slot_worker=lambda _slot: pytest.fail("completed slot reran"))
    assert resumed == manifest


def test_correction_run_direct_cli_exposes_the_focal_parallel_contract():
    completed = subprocess.run(
        [sys.executable, str(REPO / "tools" / "sim" / "correction_run.py"), "--help"],
        cwd=REPO, text=True, capture_output=True, check=False)

    assert completed.returncode == 0, completed.stderr
    assert "focal" in completed.stdout
    assert "--jobs" in completed.stdout
    assert "--opponents" in completed.stdout
    assert "--heldout" in completed.stdout
    assert "--episodes" in completed.stdout


def test_correction_run_cli_generates_a_fresh_default_seed_per_run(tmp_path, monkeypatch):
    import sim.correction_run as correction_run

    seeds = iter((17, 29))

    class Entropy:
        def getrandbits(self, _bits):
            return next(seeds)

    manifests = []

    def complete_without_playing(*, run_dir, **_kwargs):
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        manifests.append(manifest)
        manifest["status"] = "complete"
        manifest["totals"]["complete"] = manifest["totals"]["planned"]
        return manifest

    monkeypatch.setattr(correction_run.random, "SystemRandom", Entropy)
    monkeypatch.setattr(
        correction_run, "_git_source_identity",
        lambda *_args, **_kwargs: {"commit": "abc", "dirty": False})
    monkeypatch.setattr(correction_run, "execute_correction_run", complete_without_playing)

    for output in (tmp_path / "one", tmp_path / "two"):
        assert correction_run.main([
            "mega_starmie", "-n", "1", "--jobs", "1", "--out", str(output),
        ]) == 0

    assert [manifest["seed"] for manifest in manifests] == [17, 29]


def test_correction_run_completion_reports_focal_decision_timing():
    from sim.correction_run import _focal_decision_timing, _log_completion

    timing = _focal_decision_timing([
        {"record_type": "decision", "engine_seat": 1, "round_trip_seconds": 0.4},
        {"record_type": "decision", "engine_seat": 0, "round_trip_seconds": 9.9},
        {"record_type": "decision", "engine_seat": 1, "round_trip_seconds": 0.2},
    ], 1)
    assert timing == {"count": 2, "avg": pytest.approx(0.3), "min": 0.2, "max": 0.4}

    lines = []
    _log_completion(
        lines.append, 0.0,
        {"index": 1, "opponent": "mega_lucario"},
        {"status": "complete", "focal_result": "win", "match_seconds": 12.34,
         "focal_decision_seconds": timing},
        running=3, finished=2, planned=5)
    assert "running 3 | finished 2/5" in lines[0]
    assert "match 2 vs mega_lucario: focal win, 12.34s" in lines[0]
    assert "decision avg/min/max 0.300/0.200/0.400s (n=2)" in lines[0]


def test_agent_identity_hashes_exact_deck_strategy_and_agent_tree(tmp_path):
    from sim.correction_run import _agent_identity

    agent = tmp_path / "mega_starmie"
    agent.mkdir()
    (agent / "deck.csv").write_text("3\n" * 60, encoding="utf-8")
    (agent / "strategy.py").write_text("VALUE = 1\n", encoding="utf-8")
    (agent / "main.py").write_text("import strategy\n", encoding="utf-8")

    first = _agent_identity(tmp_path, "mega_starmie")
    (agent / "strategy.py").write_text("VALUE = 2\n", encoding="utf-8")
    second = _agent_identity(tmp_path, "mega_starmie")

    assert first["deck_sha256"] == second["deck_sha256"]
    assert first["strategy_sha256"] != second["strategy_sha256"]
    assert first["agent_tree_sha256"] != second["agent_tree_sha256"]


def test_dirty_source_identity_hashes_untracked_contents(tmp_path):
    from sim.correction_run import _git_source_identity

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    untracked = tmp_path / "untracked.txt"
    untracked.write_text("one\n", encoding="utf-8")
    first = _git_source_identity(tmp_path, allow_dirty=True)
    untracked.write_text("two\n", encoding="utf-8")
    second = _git_source_identity(tmp_path, allow_dirty=True)

    assert first["dirty"] is True
    assert first["dirty_sha256"] != second["dirty_sha256"]


def test_source_identity_ignores_the_artifact_root(tmp_path):
    from sim.correction_run import _git_source_identity

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "one.bin").write_bytes(b"one")
    first = _git_source_identity(tmp_path, allow_dirty=True, exclude_paths=(artifacts,))
    (artifacts / "one.bin").write_bytes(b"two")
    second = _git_source_identity(tmp_path, allow_dirty=True, exclude_paths=(artifacts,))

    assert first == second == {"commit": first["commit"], "dirty": False}


def test_source_identity_refuses_a_broad_tracked_exclusion(tmp_path):
    from sim.correction_run import _git_source_identity

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                   cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "src"
    source.mkdir()
    (source / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "src/tracked.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)

    with pytest.raises(ValueError, match="repository"):
        _git_source_identity(tmp_path, allow_dirty=True, exclude_paths=(tmp_path,))
    with pytest.raises(ValueError, match="tracked source"):
        _git_source_identity(tmp_path, allow_dirty=True, exclude_paths=(source,))


def test_correction_run_cli_warns_when_source_identity_is_refused(tmp_path, monkeypatch, capsys):
    import sim.correction_run as correction_run

    monkeypatch.setattr(correction_run, "_discover_agents", lambda _root: ("dragapult_ex",))
    monkeypatch.setattr(
        correction_run, "_git_source_identity",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("working tree is dirty; commit changes or pass --allow-dirty")),
    )

    exit_code = correction_run.main([
        "dragapult_ex", "-n", "1", "--jobs", "1", "--out", str(tmp_path),
    ])

    assert exit_code == 2
    assert capsys.readouterr().err == (
        "warning: correction run not started: working tree is dirty; "
        "commit changes or pass --allow-dirty\n"
    )


def test_resume_refuses_changed_contestant_identity(tmp_path):
    from sim.correction_run import _agent_identity, verify_correction_run_inputs

    agents = tmp_path / "agents"
    agent = agents / "focal"
    agent.mkdir(parents=True)
    (agent / "deck.csv").write_text("3\n" * 60, encoding="utf-8")
    (agent / "main.py").write_text("pass\n", encoding="utf-8")
    manifest = {
        "source_identity": {"commit": "ignored", "dirty": False},
        "contestants": {"focal": _agent_identity(agents, "focal")},
    }
    (agent / "deck.csv").write_text("4\n" * 60, encoding="utf-8")

    with pytest.raises(ValueError, match="contestant identity mismatch"):
        verify_correction_run_inputs(
            manifest, agents, source_reader=lambda: manifest["source_identity"])


def test_resume_at_byte_cap_starts_no_episode(tmp_path):
    from sim.correction_run import ExecutionConfig, create_correction_run, execute_correction_run

    run_dir = create_correction_run(
        output_root=tmp_path, run_id="run-cap", created_at="2026-08-25T00:00:00+00:00",
        focal="focal", opponents=("focal",), episodes=1, seed=1, heldout=0,
        jobs=1, engine="native", source_identity={"commit": "abc", "dirty": False},
        contestant_identities={"focal": {"deck_sha256": "deck"}},
        execution=ExecutionConfig(1, 1, 10, tmp_path))
    results = run_dir / "results"
    results.mkdir()
    (results / "000000.json").write_text(json.dumps({
        "index": 0, "status": "failed", "bytes": 10}), encoding="utf-8")
    result = execute_correction_run(
        run_dir=run_dir, agents_root=tmp_path, extra_syspath=(), decision_timeout=1,
        episode_timeout=1, max_bytes=10, verify_inputs=False,
        slot_worker=lambda _slot: pytest.fail("episode started past cap"))

    assert result["status"] == "capped"


def test_resume_cap_counts_superseded_quarantines(tmp_path):
    from sim.correction_run import ExecutionConfig, create_correction_run, execute_correction_run

    run_dir = create_correction_run(
        output_root=tmp_path, run_id="run-quarantine-cap",
        created_at="2026-08-25T00:00:00+00:00", focal="focal",
        opponents=("focal",), episodes=1, seed=1, heldout=0, jobs=1,
        engine="native", source_identity={"commit": "abc", "dirty": False},
        contestant_identities={"focal": {"deck_sha256": "deck"}},
        execution=ExecutionConfig(1, 1, 15, tmp_path))
    first = run_dir / "quarantine" / "000000-first"
    latest = run_dir / "quarantine" / "000000-latest"
    first.mkdir(parents=True)
    latest.mkdir()
    (first / "evidence").write_bytes(b"a" * 10)
    (latest / "evidence").write_bytes(b"b" * 10)
    results = run_dir / "results"
    results.mkdir()
    (results / "000000.json").write_text(json.dumps({
        "index": 0, "status": "failed", "bytes": 10,
        "quarantine_path": "quarantine/000000-latest",
    }), encoding="utf-8")

    result = execute_correction_run(
        run_dir=run_dir, agents_root=tmp_path, extra_syspath=(), decision_timeout=1,
        episode_timeout=1, max_bytes=15, verify_inputs=False)

    assert result["status"] == "capped"
    assert result["totals"]["bytes"] == 20


def test_resume_persists_complete_after_the_last_result_was_already_written(tmp_path):
    from sim.correction_run import ExecutionConfig, create_correction_run, execute_correction_run

    run_dir = create_correction_run(
        output_root=tmp_path, run_id="run-recover", created_at="2026-08-25T00:00:00+00:00",
        focal="focal", opponents=("focal",), episodes=1, seed=1, heldout=0,
        jobs=1, engine="native", source_identity={"commit": "abc", "dirty": False},
        contestant_identities={"focal": {"deck_sha256": "deck"}},
        execution=ExecutionConfig(1, 1, 0, tmp_path))
    execute_correction_run(
        run_dir=run_dir, agents_root=tmp_path, extra_syspath=(), decision_timeout=1,
        episode_timeout=1, max_bytes=0, verify_inputs=False,
        slot_worker=lambda slot: {"index": slot["index"], "status": "complete",
                                  "bundle_id": "bundle", "bytes": 1})
    manifest_path = run_dir / "manifest.json"
    stale = json.loads(manifest_path.read_text(encoding="utf-8"))
    stale["status"] = "running"
    manifest_path.write_text(json.dumps(stale), encoding="utf-8")

    recovered = execute_correction_run(
        run_dir=run_dir, agents_root=tmp_path, extra_syspath=(), decision_timeout=1,
        episode_timeout=1, max_bytes=0, verify_inputs=False,
        slot_worker=lambda _slot: pytest.fail("complete Episode reran"))

    assert recovered["status"] == "complete"
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["status"] == "complete"


def test_reconcile_rejects_a_missing_completed_bundle(tmp_path):
    from sim.correction_run import ExecutionConfig, create_correction_run, execute_correction_run

    run_dir = create_correction_run(
        output_root=tmp_path, run_id="run-corrupt", created_at="2026-08-25T00:00:00+00:00",
        focal="focal", opponents=("focal",), episodes=1, seed=1, heldout=0,
        jobs=1, engine="native", source_identity={"commit": "abc", "dirty": False},
        contestant_identities={"focal": {"deck_sha256": "deck"}},
        execution=ExecutionConfig(1, 1, 0, tmp_path))
    results = run_dir / "results"
    results.mkdir()
    (results / "000000.json").write_text(json.dumps({
        "index": 0, "status": "complete", "bytes": 1, "bundle_id": "missing",
        "bundle_path": "bundles/tuning/missing"}), encoding="utf-8")

    with pytest.raises(ValueError, match="bundle"):
        execute_correction_run(
            run_dir=run_dir, agents_root=tmp_path, extra_syspath=(), decision_timeout=1,
            episode_timeout=1, max_bytes=0)


def test_correction_worker_passes_its_decision_limit_to_the_agent(monkeypatch, tmp_path):
    import sim.battle as battle
    import sim.correction_run as correction_run

    calls = []

    class Server:
        def __init__(self, *_args, **kwargs):
            calls.append(kwargs)

        def alive(self):
            return True

        def close(self):
            pass

    monkeypatch.setattr(battle, "AgentServer", Server)
    monkeypatch.setattr(battle, "read_deck", lambda _directory: [1] * 60)
    monkeypatch.setattr(correction_run, "_WORKER_STATE", {
        "config": {
            "agents_root": str(tmp_path), "extra_syspath": (),
            "source_identity": {"commit": "abc", "dirty": False},
            "contestants": {"agent": {"deck_sha256": "deck"}},
            "run_id": "run", "decision_timeout": 20.0,
        },
        "servers": {}, "decks": {},
    })

    correction_run._worker_agent("focal", "agent")

    assert calls[0]["decision_seconds"] == 20.0


def test_correction_run_process_worker_quarantines_unrecoverable_focal_views(tmp_path):
    from sim.correction_run import (
        ExecutionConfig, _agent_identity, _git_source_identity, create_correction_run,
        execute_correction_run,
    )
    from train.corpus.bundle import _strict_records

    agent = "mega_starmie"
    agents = REPO / "src" / "agents"
    source = _git_source_identity(REPO, allow_dirty=True, exclude_paths=(tmp_path,))
    contestants = {agent: _agent_identity(agents, agent)}
    assert len(contestants[agent]["ledger_overlay_sha256"]) == 64
    run_dir = create_correction_run(
        output_root=tmp_path, run_id=f"process-worker-{agent}",
        created_at="2026-08-25T00:00:00+00:00",
        focal=agent, opponents=(agent,), episodes=1, seed=601,
        heldout=0, jobs=1, engine="cgpy", source_identity=source,
        contestant_identities=contestants,
        execution=ExecutionConfig(20.0, 600.0, 1024 ** 3, agents))

    manifest = execute_correction_run(
        run_dir=run_dir, agents_root=agents, extra_syspath=(REPO / "src",),
        decision_timeout=20.0, episode_timeout=600.0, max_bytes=1024 ** 3)

    assert manifest["status"] == "failed"
    slot = manifest["slots"][0]
    assert slot["status"] == "failed" and "bundle_path" not in slot
    assert slot["error"]["message"] == "unavailable Ledger decision entered Correction Run: unavailable"
    quarantine = run_dir / slot["quarantine_path"]
    records = _strict_records((quarantine / "telemetry.jsonl").read_text().splitlines())
    unavailable = [candidate for record in records for candidate in record.get("candidates", ())
                   if candidate["status"] == "unavailable"]
    assert unavailable and all(not candidate["successors"] for candidate in unavailable)
    assert any("focal hand update is hidden from the source viewer" in gap
               for candidate in unavailable for gap in candidate["gaps"])
