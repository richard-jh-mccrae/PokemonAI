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
