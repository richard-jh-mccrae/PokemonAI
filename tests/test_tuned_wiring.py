"""The shipped tuned.json is wired into the agent and its keys actually take effect.

ADR-0018: main.py loads tuned.json as ``Pilot(overrides=...)`` and ``Pilot._weight`` resolves
every Hypothesis weight through it by id (0 disables). A key matching no Hypothesis id is
silently ignored -> a no-op override. These tests guard that every shipped override is real
(so it is *actually used*) and pin the silent-drop failure mode the guard exists for.
"""
import importlib.util
import json
from pathlib import Path

from common.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.strategy import Hypothesis, Strategy

REPO = Path(__file__).resolve().parents[1]


def _deck_hypotheses(agent: str):
    path = REPO / "src" / "agents" / agent / "strategy.py"
    spec = importlib.util.spec_from_file_location(f"{agent}_strategy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.STRATEGY.hypotheses


def _hypothesis_ids(agent: str) -> set[str]:
    return {h.id for h in (*GENERAL_STRATEGY.hypotheses, *_deck_hypotheses(agent))}


def test_shipped_tuned_keys_are_real_hypotheses():
    """REQ-TUNER-0011: every key in a shipped tuned.json matches a Hypothesis id; otherwise
    _weight ignores it (a silent no-op) and the override is never actually used."""
    for tuned in sorted((REPO / "src" / "agents").glob("*/tuned.json")):
        agent = tuned.parent.name
        keys = set(json.loads(tuned.read_text(encoding="utf-8")))
        unknown = keys - _hypothesis_ids(agent)
        assert not unknown, f"{tuned}: overrides for unknown hypotheses {sorted(unknown)}"


def test_unknown_override_key_is_silently_ignored():
    """REQ-TUNER-0011: pins why keys must be validated — an override whose id matches no
    Hypothesis never reaches a weight, so it changes nothing."""
    h = Hypothesis("real", "", when=lambda c: c.card_id == 222, weight=0)
    pilot = Pilot(Strategy(hypotheses=[h]), deck=[1] * 60, overrides={"ghost": 99.0})
    assert pilot._weight(h) == 0          # 'ghost' never applied; the real Hypothesis keeps its default
