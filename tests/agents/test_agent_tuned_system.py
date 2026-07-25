"""System test (ISTQB system level): the shipped agent bundle actually *applies* tuned.json.

The package test proves tuned.json is *shipped*; the io test proves the Pilot *can* apply
overrides. Neither proves the deployable wiring — that ``main.py`` loads the file from the
bundle and feeds it to the Pilot. This runs the real, packaged agent in a clean subprocess
(cwd = the bundle, like the Kaggle grader) and asserts a weight override in tuned.json reaches
``Pilot._weight``. Skips if the real agent dir is absent (the package tests use a fixture so they
survive its deletion; this one is specifically about the deployable, so it targets src/agents).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from submit.package import package  # noqa: E402

AGENT = "mega_starmie"
TARGET = "use-acceleration"    # real General Strategy Hypothesis id (general_strategy.py). NB it must
                               # be a rung that still EXISTS: this asserts the tuned.json plumbing, and
                               # `power-up-attacker` — the old choice — was deleted with the attach swap.
AUTHORED = 25.0               # authored seed weight

pytestmark = pytest.mark.skipif(
    not (REPO / "src" / "agents" / AGENT / "main.py").exists(),
    reason="real agent src/agents/mega_starmie not present",
)

_PROBE = (
    "import json, main\n"
    "pilot = main.agent.pilot\n"    # the runtime exposes the built Pilot on the callable (ADR-0055)
    "hs = (*pilot.general.hypotheses, *pilot.strategy.hypotheses)\n"
    f"h = next(h for h in hs if h.id == {TARGET!r})\n"
    "print('RESULT' + json.dumps({'overrides': pilot.overrides, "
    "'w': pilot._weight(h)}))\n"
)


def _run_bundle(bundle: Path, env_extra: dict | None = None) -> dict:
    """Import the bundled agent in a clean subprocess (cwd = bundle) and read back the probe."""
    env = {**os.environ, "PYTHONPATH": str(bundle), **(env_extra or {})}   # resolve from bundle only
    proc = subprocess.run([sys.executable, "-c", _PROBE], cwd=bundle, env=env,
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, f"bundle import failed:\n{proc.stderr}"
    line = next(ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT"))
    return json.loads(line[len("RESULT"):])


def test_packaged_agent_applies_tuned_weight_override(tmp_path):
    """REQ-TUNER-0011: the deployable agent loads tuned.json and its weights reach _weight —
    an override changes the effective weight; an empty file falls back to the authored seed."""
    package(AGENT, tmp_path)            # stages exact shipped bundle at tmp_path/<agent>
    bundle = tmp_path / AGENT

    (bundle / "tuned.json").write_text("{}", encoding="utf-8")
    base = _run_bundle(bundle)
    assert base["overrides"] == {}
    assert base["w"] == AUTHORED        # no override -> authored default

    (bundle / "tuned.json").write_text(json.dumps({TARGET: 999.0}), encoding="utf-8")
    tuned = _run_bundle(bundle)
    assert tuned["overrides"] == {TARGET: 999.0}
    assert tuned["w"] == 999.0          # shipped agent actually applies the diff


def test_packaged_agent_applies_experiment_overlay(tmp_path):
    """REQ-SIM-0008: the agent honors an AGENT_OVERLAY experiment overlay layered over tuned.json
    — the offline A/B injection path (ADR-0021). Inert (falls back to tuned.json) when unset."""
    package(AGENT, tmp_path)
    bundle = tmp_path / AGENT
    (bundle / "tuned.json").write_text("{}", encoding="utf-8")

    overlay = tmp_path / "exp.json"
    overlay.write_text(json.dumps({"overrides": {TARGET: 7.0}}), encoding="utf-8")
    out = _run_bundle(bundle, env_extra={"AGENT_OVERLAY": str(overlay)})
    assert out["w"] == 7.0              # overlay weight reached _weight, over empty tuned.json
