"""A brain crash must be catchable after the fact, never silently absorbed.

The fallback shell still saves the match, but the crash itself has to surface: the full
traceback on stderr under a greppable LEDGER-CRASH marker, and a bounded report inside the
decision's diagnostics so telemetry, replays, and the corpus dashboard all carry it. Offline
harnesses can refuse the parachute entirely with AGENT_BRAIN_STRICT=1."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from ledger_helpers import DRAGAPULT, FIRE_E, body, player, printout

from common.api import ActionIdentity, RootDecision
from common.runtime import build_runtime
from common.strategy.context import _END

REPO = Path(__file__).resolve().parents[2]


def _runtime():
    path = REPO / "src" / "agents" / "mega_starmie" / "strategy.py"
    spec = importlib.util.spec_from_file_location("_crash_test_strategy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    deck = [int(value) for value in
            (REPO / "src" / "agents" / "mega_starmie" / "deck.csv").read_text().split()[:60]]
    return build_runtime(module.STRATEGY, deck, stats=None, functions=None, scout=None,
                         briefs=[])


def _observation():
    select = {"type": 1, "context": 0, "minCount": 1, "maxCount": 1,
              "option": [{"type": 3, "index": 0}, {"type": _END}],   # two options: not forced
              "deck": None, "contextCard": None, "effect": None,
              "remainDamageCounter": 0, "remainEnergyCost": 0}
    return printout(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]),
                    them=player(own=False, active=body(DRAGAPULT, 2)), select=select)


def test_a_brain_crash_logs_the_traceback_and_reports_in_diagnostics(capsys):
    runtime = _runtime()

    def dead(_obs):
        raise ValueError("boom: the exact bug text")

    runtime.ledger.decide = dead
    decision = runtime.decide(_observation())

    assert decision.diagnostics["backend"] == "strategy-fallback"
    fallback = decision.diagnostics["fallback"]
    assert fallback["cause"] == "exception:ValueError"
    assert fallback["error"]["type"] == "ValueError"
    assert "boom: the exact bug text" in fallback["error"]["message"]
    assert "boom: the exact bug text" in fallback["error"]["traceback_tail"]

    stderr = capsys.readouterr().err
    assert "LEDGER-CRASH" in stderr
    assert "ValueError: boom: the exact bug text" in stderr
    assert "in dead" in stderr                   # the traceback names the crashing frame


def test_strict_mode_refuses_the_parachute(monkeypatch):
    """Offline harnesses set AGENT_BRAIN_STRICT=1 so a bug fails loudly instead of being
    played through — better to fix bugs than to hide them."""
    monkeypatch.setenv("AGENT_BRAIN_STRICT", "1")
    runtime = _runtime()

    def dead(_obs):
        raise ValueError("boom")

    runtime.ledger.decide = dead
    with pytest.raises(ValueError):
        runtime.decide(_observation())


def test_a_healthy_decision_logs_no_crash_marker(capsys):
    runtime = _runtime()
    runtime.ledger.decide = lambda _obs: RootDecision(
        (0,), ActionIdentity("end", (0,)), 0.0, True, {"backend": "ledger"})
    decision = runtime.decide(_observation())
    assert decision.diagnostics["backend"] == "ledger"
    assert "LEDGER-CRASH" not in capsys.readouterr().err
