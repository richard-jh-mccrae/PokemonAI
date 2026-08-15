from __future__ import annotations

import hashlib
import zipfile

import pytest

from sim import mirror_gate
from sim.mirror_gate import MirrorGateFailure, assert_within_limit, run_mirror, summarize, worker_count


def _artifact(path):
    with zipfile.ZipFile(path, "w") as zipped:
        zipped.writestr("main.py", "def agent(obs): return 0\n")
    return path


def _outcome(index, status="passed", seconds=None):
    return {
        "index": index, "status": status, "seconds": float(seconds or index),
        "error": None if status == "passed" else f"synthetic {status}",
        "result": ({"crashed": [], "callback_seconds": [0.1 * index]}
                   if status == "passed" else None),
    }


def test_mirror_summary_reports_total_average_minimum_and_maximum():
    assert summarize([1.0, 2.0, 6.0]) == {
        "total": 9.0, "avg": 3.0, "min": 1.0, "max": 6.0,
    }


def test_mirror_gate_rejects_the_slowest_match_not_the_average():
    with pytest.raises(RuntimeError, match="max match time 301.0s exceeds 300.0s"):
        assert_within_limit([1.0, 2.0, 301.0], 300.0)


def test_mirror_gate_rejects_nonpositive_worker_counts(tmp_path):
    with pytest.raises(ValueError, match="workers must be positive"):
        run_mirror("missing", games=1, max_match_seconds=1, agents_root=tmp_path, workers=0)


def test_worker_count_never_exceeds_the_five_match_gate_limit():
    assert worker_count(10, 10) == 5
    assert worker_count(3, 10) == 3
    assert worker_count(10, 2) == 2


def test_posix_timeout_kills_the_entire_match_process_group(monkeypatch):
    calls = []

    class Process:
        pid = 123

        @staticmethod
        def is_alive():
            return True

        @staticmethod
        def join(_timeout=None):
            return None

        @staticmethod
        def terminate():
            raise AssertionError("POSIX must kill the session, not only the wrapper")

        @staticmethod
        def kill():
            return None

    monkeypatch.setattr(mirror_gate, "_is_windows", lambda: False)
    monkeypatch.setattr(mirror_gate.os, "killpg", lambda pid, sig: calls.append((pid, sig)),
                        raising=False)

    mirror_gate._terminate_process(Process())

    assert calls == [(123, mirror_gate.POSIX_KILL_SIGNAL)]


def test_parallel_report_contract_preserves_all_results_and_exact_artifact_identity(
        tmp_path, monkeypatch, capsys):
    artifact = _artifact(tmp_path / "agent.zip")
    monkeypatch.setattr(mirror_gate, "_timed_archive_match",
                        lambda task: _outcome(task[0]))
    ticks = iter((10.0, 12.0))

    report = run_mirror(
        "agent", games=5, workers=1, max_match_seconds=600,
        artifact=artifact, clock=lambda: next(ticks))

    expected_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert len(report["results"]) == 5
    assert report["artifact_sha256"] == expected_sha
    assert report["match"] == {"total": 15.0, "avg": 3.0, "min": 1.0, "max": 5.0}
    assert report["batch_wall"] == 2.0
    rendered = capsys.readouterr().out
    assert "match 5: PASSED 5.000s" in rendered
    assert "total: 15.000s" in rendered
    assert "batch wall: 2.000s" in rendered


def test_failure_and_timeout_do_not_suppress_other_results_or_aggregate(
        tmp_path, monkeypatch, capsys):
    artifact = _artifact(tmp_path / "agent.zip")
    statuses = {2: "failed", 4: "timeout"}
    monkeypatch.setattr(
        mirror_gate, "_timed_archive_match",
        lambda task: _outcome(task[0], statuses.get(task[0], "passed")),
    )
    ticks = iter((20.0, 25.0))

    with pytest.raises(MirrorGateFailure) as raised:
        run_mirror("agent", games=5, workers=1, max_match_seconds=600,
                   artifact=artifact, clock=lambda: next(ticks))

    assert [row["status"] for row in raised.value.report["results"]] == [
        "passed", "failed", "passed", "timeout", "passed",
    ]
    assert raised.value.report["match"]["total"] == 15.0
    rendered = capsys.readouterr().out
    assert "match 2: FAILED" in rendered
    assert "match 4: TIMEOUT" in rendered
    assert "avg: 3.000s" in rendered


def test_each_match_extraction_is_removed_after_worker_completion(tmp_path, monkeypatch):
    artifact = _artifact(tmp_path / "agent.zip")
    seen = []

    def fake_match(bundle, *, a_seat, timeout):
        seen.append(bundle)
        assert (bundle / "main.py").is_file()
        return {"crashed": [], "callback_seconds": [0.1]}

    monkeypatch.setattr(mirror_gate, "_one_match_with_deadline", fake_match)

    result = mirror_gate._timed_archive_match((1, artifact, 0, 600.0))

    assert result["status"] == "passed"
    assert len(seen) == 1
    assert not seen[0].exists()


def test_exact_artifact_with_offline_engine_name_is_rejected(tmp_path):
    artifact = tmp_path / "agent.zip"
    with zipfile.ZipFile(artifact, "w") as zipped:
        zipped.writestr("main.py", "import cgpy\n")

    with pytest.raises(RuntimeError, match="offline-only cgpy"):
        run_mirror("agent", games=1, workers=1, artifact=artifact)


def test_mirror_agent_accepts_battle_callback_timeout(tmp_path, monkeypatch):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "main.py").write_text("def agent(obs): return 0\n")

    class AgentServer:
        def __init__(self, _bundle):
            self.proc = None

        def act(self, _obs, timeout=None):
            return timeout

        def close(self):
            pass

    def play(left, _right, _left_deck, _right_deck, _seat):
        assert left.act({"step": 1, "current": {"turn": 1}}, timeout=7.0) == 7.0
        return type("Result", (), {"winner": 0, "crashed": ()})()

    monkeypatch.setattr("sim.battle.AgentServer", AgentServer)
    monkeypatch.setattr("sim.battle._play_seated", play)
    monkeypatch.setattr("sim.battle.read_deck", lambda _bundle: ())

    result = mirror_gate._one_match(bundle, a_seat=0)

    assert result["crashed"] == []
