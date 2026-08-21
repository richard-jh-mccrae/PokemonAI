"""Teacher-runtime shell behavior: planner construction and epoch failure cleanup."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from deprecated.bellman import build_teacher_runtime
from observation_helpers import engine_opt


REPO = Path(__file__).resolve().parents[3]


def _strategy(name: str = "mega_starmie"):
    path = REPO / "src" / "agents" / name / "strategy.py"
    spec = importlib.util.spec_from_file_location(f"_teacher_{name}_strategy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STRATEGY


def _teacher():
    strategy = _strategy()
    deck = [int(value) for value in
            (REPO / "src" / "agents" / "mega_starmie" / "deck.csv").read_text().splitlines()
            if value.strip()]
    return build_teacher_runtime(
        strategy, deck, stats=None, functions=None, scout=None, briefs=[])


def _menu(options, *, min_count=1, max_count=1, context=0, turn=2):
    return {
        "select": {"context": context, "minCount": min_count, "maxCount": max_count,
                   "option": list(options)},
        "current": {"turn": turn, "yourIndex": 0, "players": [
            {"hand": [], "active": [], "bench": [], "discard": [], "prize": []},
            {"hand": None, "handCount": 0, "active": [], "bench": [], "discard": [],
             "prize": []},
        ]},
        "logs": [],
    }


def test_planner_setup_survives_a_facedown_opponent_active():
    runtime = _teacher()
    observation = _menu([engine_opt(type=14)], turn=1)
    observation["current"]["players"][1]["active"] = [None]

    assert runtime._planner(observation) is not None


def test_a_planner_failure_still_closes_the_retained_native_session():
    runtime = _teacher()

    class BoomPlanner:
        discarded = False

        def _epoch_seconds(self, _request):
            return 1.0

        def prove(self, _request):
            raise RuntimeError("boom mid-epoch")

        def discard_precheck(self):
            self.discarded = True

    planner = BoomPlanner()
    runtime._planner = lambda _observation: planner
    observation = _menu([engine_opt(type=3, area=2, index=0), engine_opt(type=14)])

    decision = runtime.decide(observation)

    assert planner.discarded
    assert decision.chosen == (1,)
    assert decision.diagnostics["backend"] == "strategy-fallback"
    assert decision.diagnostics["fallback"]["cause"] == "exception:RuntimeError"
