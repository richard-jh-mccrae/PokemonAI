"""Every shipped agent's main.py IS the shared runtime (ADR-0055) — nothing else.

Deployment config is DATA (``common.runtime.PROFILE``), so a main.py must carry NO local wiring:
one ``make_agent`` call, no ``Pilot(...)``, no per-file flag literals.
"""
import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

AGENT_MAINS = sorted((REPO / "src" / "agents").glob("*/main.py"))
FIXTURE_MAIN = REPO / "tests" / "fixtures" / "agents" / "mega_starmie" / "main.py"
ALL_MAINS = AGENT_MAINS + [FIXTURE_MAIN]
_IDS = [p.parent.name for p in AGENT_MAINS] + ["fixture_mega_starmie"]


@pytest.mark.req("REQ-WIRE-0001")
@pytest.mark.parametrize("main_py", ALL_MAINS, ids=_IDS)
def test_main_is_only_the_shared_runtime(main_py):
    tree = ast.parse(main_py.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert sum(c.func.id == "make_agent" for c in calls) == 1, (
        f"{main_py}: expected exactly one make_agent(...) call — the shared runtime builds "
        f"the agent (common/runtime.py).")
    assert not any(c.func.id == "Pilot" for c in calls), (
        f"{main_py}: local Pilot(...) build — deployment wiring lives in common.runtime, "
        f"never per-agent (the pre-0055 dark-layer drift class).")
    assert "_params.get(" not in main_py.read_text(encoding="utf-8"), (
        f"{main_py}: per-file kill-switch literal — the shipped value belongs in "
        f"common.runtime.PROFILE (one decision, every agent).")
    bound = [t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
             for t in n.targets if isinstance(t, ast.Name)]
    assert "agent" in bound, (
        f"{main_py}: no module-level `agent` binding — every harness (grader, arena worker, "
        f"check_agent, battle server) loads main.py and calls module.agent(obs).")


@pytest.mark.req("REQ-WIRE-0001")
def test_fixture_main_is_a_byte_copy_of_the_shipped_agent():
    """The packaged-bundle system tests exercise the fixture, so drift here tests a DIFFERENT
    deployable."""
    src = (REPO / "src" / "agents" / "mega_starmie" / "main.py").read_bytes()
    assert FIXTURE_MAIN.read_bytes() == src
