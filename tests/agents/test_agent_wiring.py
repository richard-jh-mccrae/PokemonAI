"""Every shipped agent's main.py wires the full deployment config into its Pilot.

The Pilot ctor defaults the Posture / Lethal-Solver / Turn-Planner kill-switches to ``False``
(``pilot.py`` __init__): the ctor is the *raw-scoring* layer, and the validated-best deployment
config (all A/B-cleared ON: ADR-0026/0030/0031/0037) is opted into at the AGENT (main.py) level.

A new deck built from an incomplete main.py template can silently ship with those layers DARK —
no engine-ranked planner, no unified lethal family, no key-threat rung — and play far below the
tuned agent (this is exactly how mega_lucario + dragapult_ex first shipped, 2026-07-03). This test
pins the invariant so the omission fails CI instead of the grader: every ``Pilot(...)`` in every
``src/agents/<deck>/main.py`` must pass each switch as ``_params.get("<key>", True)`` — ON by
default, still overlay-controllable for local A/B (ADR-0021).
"""
import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# The deployment kill-switches every shipped agent must opt into (default ON, overlay-off capable).
REQUIRED_SWITCHES = (
    "posture",              # ADR-0026 Read/Posture
    "lethal_verify",        # ADR-0030 engine-confirm direct lethal locks
    "planner_engine_rank",  # ADR-0031 engine-sim ranks the planner's candidate lines
    "planner_key_threat",   # ADR-0031 KO-the-key-threat Goal-Ladder rung
    "lethal_family",        # ADR-0037 the ONE win-generator family + verify-every-lock
    "lethal_veto",          # ADR-0037 replay the verified cascade
    "matchup_targeting",    # ADR-0051 MatchupPlan target-priority spine (superseded ADR-0038 levers)
)

# Wired-but-ARMED-OFF switches: present + overlay-controllable, default False — deliberately dark
# until an evidence gate clears (then a switch moves into REQUIRED_SWITCHES). Currently none: the
# ADR-0038 brief_engine lever was retired into the ADR-0051 MatchupPlan spine.
ARMED_OFF_SWITCHES = ()

AGENT_MAINS = sorted((REPO / "src" / "agents").glob("*/main.py"))


def _pilot_call(main_py: Path) -> ast.Call:
    """The single ``Pilot(...)`` call node in an agent's main.py."""
    tree = ast.parse(main_py.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Pilot"]
    assert len(calls) == 1, f"{main_py}: expected exactly one Pilot(...) call, found {len(calls)}"
    return calls[0]


def _is_params_get(node: ast.AST, key: str, default: bool) -> bool:
    """True iff ``node`` is exactly ``_params.get("<key>", <default>)`` (overlay-controllable)."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get" and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "_params"):
        return False
    if len(node.args) != 2:
        return False
    key_arg, default_arg = node.args
    return (isinstance(key_arg, ast.Constant) and key_arg.value == key
            and isinstance(default_arg, ast.Constant) and default_arg.value is default)


@pytest.mark.parametrize("main_py", AGENT_MAINS, ids=[p.parent.name for p in AGENT_MAINS])
def test_agent_wires_deployment_switches_on(main_py):
    """REQ-WIRE-0001: no shipped agent runs the Posture/Lethal/Planner layers dark — each switch is
    ``_params.get("<key>", True)`` (default ON, overlay can force off for A/B)."""
    call = _pilot_call(main_py)
    kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg}
    for switch in REQUIRED_SWITCHES:
        assert switch in kwargs, (
            f"{main_py}: Pilot(...) is missing `{switch}=` — the agent would run that layer at the "
            f"ctor default (OFF). Wire it as {switch}=_params.get(\"{switch}\", True).")
        assert _is_params_get(kwargs[switch], switch, True), (
            f"{main_py}: `{switch}=` must be _params.get(\"{switch}\", True) (default ON, "
            f"overlay-controllable), not {ast.dump(kwargs[switch])}.")


@pytest.mark.parametrize("main_py", AGENT_MAINS, ids=[p.parent.name for p in AGENT_MAINS])
def test_agent_wires_armed_off_switches(main_py):
    """REQ-WIRE-0001: an armed-off switch is WIRED (present, overlay-controllable) but defaults
    False — deliberately dark until its evidence gate clears (see ARMED_OFF_SWITCHES notes)."""
    call = _pilot_call(main_py)
    kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg}
    for switch in ARMED_OFF_SWITCHES:
        assert switch in kwargs, (
            f"{main_py}: Pilot(...) is missing `{switch}=` — wire it as "
            f"{switch}=_params.get(\"{switch}\", False) (armed-off, overlay can force on).")
        assert _is_params_get(kwargs[switch], switch, False), (
            f"{main_py}: `{switch}=` must be _params.get(\"{switch}\", False) (armed-off; its "
            f"evidence gate has NOT cleared), not {ast.dump(kwargs[switch])}.")


@pytest.mark.parametrize("main_py", AGENT_MAINS, ids=[p.parent.name for p in AGENT_MAINS])
def test_agent_wires_scout_and_briefs(main_py):
    """REQ-WIRE-0002: every shipped agent passes ``scout=`` and ``briefs=`` into its Pilot — an
    agent that omits ``briefs=`` silently gets ZERO Matchup Briefs (ctor default None → []), so a
    recognized opponent's counterplay never reaches the Board (the ADR-0038 levers run dark)."""
    call = _pilot_call(main_py)
    kwargs = {kw.arg for kw in call.keywords if kw.arg}
    for required in ("scout", "briefs"):
        assert required in kwargs, (
            f"{main_py}: Pilot(...) is missing `{required}=` — recognition/Brief routing would be "
            f"silently OFF for this agent.")
