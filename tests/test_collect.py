"""collect: turn a match's replay + log into a performance sample (ADR-0019).

System test — runs a real `cabt` match and verifies `collect` recovers EVERYTHING we expect
from the actual replay + log (result, matchup via the existing classifier, per-decision
timing, and the stderr Decision Telemetry), not an imagined shape.
"""
import json
from datetime import datetime
from pathlib import Path

import pytest

from conftest import require_kaggle_environments

REPO = Path(__file__).resolve().parents[1]
FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"


@pytest.mark.req("REQ-SUB-0007")
def test_collect_extracts_result_matchup_timing_and_telemetry_from_a_real_match():
    require_kaggle_environments()
    from sim.check_agent import _run_match
    from submit.collect import parse_match

    statuses, env = _run_match(FIXTURE_AGENTS / "mega_starmie", [REPO / "src"])
    assert all(s == "DONE" for s in statuses), statuses

    m = parse_match(env.toJSON(), env.logs, seat=0)

    assert m["result"] in {"win", "loss", "draw"}             # decided from the replay rewards
    assert m["opponent_archetype"]                            # classified from the opponent's deck
    assert m["decision_ms"]["count"] > 0                      # per-decision timing from the log
    assert m["telemetry"]["decisions"] > 0                    # @T telemetry parsed out of stderr
    assert set(m["telemetry"]["tier_mix"]) == {"0"}           # this agent runs Tier-0 closed-form


@pytest.mark.req("REQ-SUB-0007")
def test_aggregate_matches_builds_record_and_per_archetype_matchups():
    from submit.collect import aggregate_matches

    def match(result, arch, count, median_ms, max_ms):
        return {"result": result, "opponent_archetype": arch,
                "decision_ms": {"count": count, "median_ms": median_ms, "max_ms": max_ms},
                "telemetry": {"decisions": count, "tier_mix": {"0": count}}}

    sample = aggregate_matches([
        match("win", "Mega Lucario ex", 3, 2.0, 9.0),
        match("loss", "Mega Lucario ex", 2, 3.0, 12.0),
        match("win", "Dragapult ex", 4, 1.0, 5.0),
    ])

    assert sample["record"] == {"wins": 2, "losses": 1, "draws": 0}
    matchups = {m["archetype"]: (m["wins"], m["losses"]) for m in sample["matchups"]}
    assert matchups == {"Mega Lucario ex": (1, 1), "Dragapult ex": (1, 0)}   # the dropdown
    assert sample["efficiency"]["matches"] == 3
    assert sample["efficiency"]["max_ms"] == 12.0
    assert sample["telemetry"]["decisions"] == 9


@pytest.mark.req("REQ-SUB-0011")
def test_record_sample_appends_performance_keyed_by_submission(tmp_path):
    from submit.collect import record_sample

    perf = tmp_path / "performance.jsonl"
    matches = [{"result": "win", "opponent_archetype": "A",
                "decision_ms": {"count": 3, "median_ms": 2.0, "max_ms": 9.0},
                "telemetry": {"decisions": 3, "tier_mix": {"0": 3}}}]

    sample = record_sample(7, matches, public_score=1234.5, rank=42, kaggle_ref="me/x/123",
                           perf_path=perf, when=datetime(2026, 6, 25, 8, 0, 0))

    assert sample["submission_id"] == 7 and sample["public_score"] == 1234.5 and sample["rank"] == 42
    assert sample["record"]["wins"] == 1
    rows = [json.loads(ln) for ln in perf.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(rows) == 1 and rows[0]["kaggle_ref"] == "me/x/123"


@pytest.mark.req("REQ-SUB-0011")
def test_collect_orchestrates_score_fetch_parse_and_record(tmp_path):
    from submit.collect import collect

    perf = tmp_path / "performance.jsonl"
    won = {"result": "win", "opponent_archetype": "Dragapult ex",
           "decision_ms": {"count": 2, "median_ms": 1.0, "max_ms": 3.0},
           "telemetry": {"decisions": 2, "tier_mix": {"0": 2}}}

    sample = collect(7, perf_path=perf,
                     score_fn=lambda sid: {"kaggle_ref": "me/x/9", "public_score": 1200.0, "rank": 5},
                     fetch_fn=lambda ref: [("R1", "L1"), ("R2", "L2")],   # two matches
                     parse_fn=lambda r, l, seat=0, cards=None: won)

    assert sample["submission_id"] == 7 and sample["public_score"] == 1200.0
    assert sample["kaggle_ref"] == "me/x/9"
    assert sample["record"]["wins"] == 2                      # both fetched matches parsed + recorded


@pytest.mark.req("REQ-SUB-0011")
def test_collect_submission_defaults_to_latest_submitted_into_artifact_dir(tmp_path):
    from submit.collect import collect_submission
    from submit.history import append_history

    history = tmp_path / "agent_history.jsonl"
    for r in [{"submission_id": 1, "artifact": "a1", "submitted_at": "t1"},
              {"submission_id": 2, "artifact": "a2", "submitted_at": "t2"}]:
        append_history(history, r)
    canned = {"result": "win", "opponent_archetype": "A",
              "decision_ms": {"count": 2, "median_ms": 1.0, "max_ms": 3.0},
              "telemetry": {"decisions": 2, "tier_mix": {"0": 2}}}
    seen = {}

    def dl(row, dest, n, kaggle_ref=None):
        seen.update(artifact=row["artifact"], dest=str(dest), n=n, ref=kaggle_ref)
        return [("R", "L", 0), ("R", "L", 1)]                # (replay, log, seat) per episode

    sample = collect_submission(history=history, replays_root=tmp_path / "replays",
                                perf_path=tmp_path / "p.jsonl", max_replays=7, download_fn=dl,
                                parse_fn=lambda r, l, seat=0, cards=None: canned,
                                score_fn=lambda sid: {"kaggle_ref": "12345", "public_score": 900.0, "rank": 1})

    assert sample["submission_id"] == 2                       # latest submitted, by default
    assert seen["artifact"] == "a2" and seen["dest"].endswith("a2")   # data/replays/<artifact stem>
    assert seen["n"] == 7 and seen["ref"] == "12345"         # --max-replays + Kaggle id plumbed through
    assert sample["record"]["wins"] == 2 and sample["public_score"] == 900.0


@pytest.mark.req("REQ-SUB-0011")
def test_collect_submission_can_target_an_explicit_id(tmp_path):
    from submit.collect import collect_submission
    from submit.history import append_history

    history = tmp_path / "h.jsonl"
    for r in [{"submission_id": 1, "artifact": "a1", "submitted_at": "t1"},
              {"submission_id": 2, "artifact": "a2", "submitted_at": "t2"}]:
        append_history(history, r)
    seen = {}

    sample = collect_submission(1, history=history, replays_root=tmp_path, perf_path=tmp_path / "p.jsonl",
                                download_fn=lambda row, dest, n, kaggle_ref=None: seen.update(a=row["artifact"]) or [],
                                score_fn=lambda sid: {"kaggle_ref": None, "public_score": None, "rank": None})
    assert sample["submission_id"] == 1 and seen["a"] == "a1"   # honored the explicit id


@pytest.mark.req("REQ-SUB-0011")
def test_cli_collect_dispatches_with_supported_kwargs_only(monkeypatch, tmp_path):
    import submit.collect as collectmod

    captured = {}

    def fake(submission_id=None, **kw):
        captured.update(submission_id=submission_id, **kw)
        return {"submission_id": submission_id or 1, "record": {}, "public_score": None}

    monkeypatch.setattr(collectmod, "collect_submission", fake)
    from submit_agent import main

    rc = main(["collect", "5", "--max-replays", "9", "--history", str(tmp_path / "h.jsonl")])
    assert rc == 0
    assert captured["submission_id"] == 5 and captured["max_replays"] == 9
    assert "seat" not in captured                        # regression: CLI must not pass a per-episode seat


@pytest.mark.req("REQ-SUB-0011")
def test_kaggle_score_fails_cleanly_with_an_auth_hint(monkeypatch):
    """An unauthenticated Kaggle CLI must yield an actionable message, not a raw traceback."""
    import subprocess

    import submit.collect as collectmod

    class _Proc:
        returncode, stdout = 1, ""
        stderr = "Authentication required to call the Kaggle API."

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc())
    with pytest.raises(SystemExit) as ei:
        collectmod.kaggle_score(1)
    msg = str(ei.value)
    assert "authenticated" in msg.lower() and "KAGGLE_API_TOKEN" in msg   # tells you how to fix it


@pytest.mark.req("REQ-SUB-0011")
def test_run_kaggle_surfaces_the_cli_error_on_other_failures(monkeypatch):
    import subprocess

    import submit.collect as collectmod

    class _Proc:
        returncode, stdout = 2, ""
        stderr = "404 - competition not found: typo-comp"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc())
    with pytest.raises(SystemExit) as ei:
        collectmod._run_kaggle(["competitions", "submissions", "typo-comp", "--csv"])
    assert "competition not found" in str(ei.value)      # the real cause, surfaced not swallowed


class _FakeApi:
    """A stand-in Kaggle API that records which episodes it was asked to download."""

    def __init__(self, ep_ids):
        self._ep_ids = ep_ids
        self.replay_calls: list = []
        self.log_calls: list = []

    def competition_list_episodes(self, submission_id=None):
        return [type("Ep", (), {"id": i})() for i in self._ep_ids]   # no agents -> seat 0

    def competition_episode_replay(self, episode_id=None, path=None):
        self.replay_calls.append(episode_id)
        (Path(path) / f"episode-{episode_id}-replay.json").write_text(
            json.dumps({"r": episode_id}), encoding="utf-8")

    def competition_episode_agent_logs(self, episode_id=None, agent_index=None, path=None):
        self.log_calls.append((episode_id, agent_index))
        (Path(path) / f"episode-{episode_id}-agent-{agent_index}-logs.json").write_text(
            json.dumps([]), encoding="utf-8")


@pytest.mark.req("REQ-SUB-0011")
def test_kaggle_download_skips_episodes_already_on_disk(tmp_path):
    """Re-running `collect` must reuse already-downloaded episodes and fetch only the new ones."""
    from submit.collect import _kaggle_download

    dest = tmp_path / "replays"
    dest.mkdir()
    # episode 100 was collected on a prior run — both its files are already present
    (dest / "episode-100-replay.json").write_text(json.dumps({"r": 100}), encoding="utf-8")
    (dest / "episode-100-agent-0-logs.json").write_text(json.dumps([]), encoding="utf-8")

    api = _FakeApi([100, 200])      # 100 cached, 200 is new
    triples = _kaggle_download({"artifact": "x"}, dest, 20, kaggle_ref="42",
                               api=api, sleep=lambda _s: None)

    assert api.replay_calls == [200]            # only the new episode hit the network
    assert api.log_calls == [(200, 0)]
    assert len(triples) == 2                     # both episodes returned (cached + freshly fetched)
    assert {t[0]["r"] for t in triples} == {100, 200}
