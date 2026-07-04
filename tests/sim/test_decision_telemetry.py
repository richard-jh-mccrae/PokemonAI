"""Decision Telemetry: the agent emits its per-decision trace to stderr (ADR-0019).

System test — runs the fixture agent in a real `cabt` match and reads the telemetry back off
the episode's agent log (the same `{duration, stdout, stderr}` structure you download from
Kaggle), so we verify the *collected* data end-to-end, not an imagined shape.
"""
import json
from pathlib import Path

import pytest

from conftest import require_kaggle_environments

REPO = Path(__file__).resolve().parents[2]
FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"


def _stderr_telemetry(env) -> list[dict]:
    """Every `@T` telemetry record our agent wrote to stderr across the match."""
    recs = []
    for step in (env.logs or []):
        for seat in step:
            for line in (seat or {}).get("stderr", "").splitlines():
                if line.startswith("@T"):
                    recs.append(json.loads(line[2:].strip()))
    return recs


@pytest.mark.req("REQ-SUB-0006")
def test_agent_emits_decision_telemetry_to_stderr_in_a_real_match():
    require_kaggle_environments()
    from sim.check_agent import _run_match

    statuses, env = _run_match(FIXTURE_AGENTS / "mega_starmie", [REPO / "src"])
    assert all(s == "DONE" for s in statuses), statuses

    recs = _stderr_telemetry(env)
    assert recs, "agent must emit @T decision telemetry to stderr"
    rec = recs[0]
    assert "chosen" in rec and "opts" in rec                 # choice + every legal option
    assert all("score" in o for o in rec["opts"])            # each option carries its score
    assert any(o.get("fired") for o in recs[-1]["opts"]) or any(  # hypotheses fired somewhere
        o.get("fired") for r in recs for o in r["opts"])

    # ADR-0041: the shipped agent wires a Scout, so each decision's @T record carries its opponent
    # POSTURE (who it thinks it faces) -> every Correction's live_trace records the matchup.
    postures = [r["posture"] for r in recs if "posture" in r]
    assert postures, "agent must emit its opponent posture to stderr (ADR-0041)"
    assert all({"cands", "gamma", "brief"} <= set(p) for p in postures)
