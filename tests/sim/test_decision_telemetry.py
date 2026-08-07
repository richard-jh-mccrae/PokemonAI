"""Decision Telemetry: the agent emits its per-decision trace to stderr (ADR-0019).

System test — a real `cabt` match, read back off the episode agent log, so the shape verified is
the one Kaggle actually collects.
"""
from pathlib import Path

import pytest

from conftest import require_kaggle_environments

REPO = Path(__file__).resolve().parents[2]
FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"


def _stderr_telemetry(env) -> list[dict]:
    """`parse_records`, not a hand-rolled `@T` parser: `kaggle_environments` truncates stderr at
    `maxLogLength`, so a big decision can cut an `@T` line mid-JSON (Issue #180)."""
    from train.blunder.telemetry_log import parse_records

    return parse_records(env.logs or [])


@pytest.mark.req("REQ-SUB-0006")
def test_agent_emits_decision_telemetry_to_stderr_in_a_real_match():
    require_kaggle_environments()
    from sim.check_agent import _run_match

    statuses, env = _run_match(FIXTURE_AGENTS / "mega_starmie", [REPO / "src"])
    assert all(s == "DONE" for s in statuses), statuses

    recs = _stderr_telemetry(env)
    assert recs, "agent must emit @T decision telemetry to stderr"
    rec = recs[0]
    assert "chosen" in rec and "opts" in rec
    assert all("score" in o for o in rec["opts"])
    assert any(o.get("fired") for o in recs[-1]["opts"]) or any(
        o.get("fired") for r in recs for o in r["opts"])

    postures = [r["posture"] for r in recs if "posture" in r]
    assert postures, "agent must emit its opponent posture to stderr (ADR-0041)"
    assert all({"cands", "gamma", "brief"} <= set(p) for p in postures)
