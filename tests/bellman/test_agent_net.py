"""The deployment hook's last-resort net: a planning failure submits a legal choice, never dies.

Distinct from decision-quality fallbacks (which packaging bans): the net decides NOTHING — it
surrenders the turn as cheaply as the menu allows and reports the failure on stderr.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import common.runtime as runtime_module
from observation_helpers import engine_opt


REPO = Path(__file__).resolve().parents[2]


def _strategy(name: str = "mega_starmie"):
    path = REPO / "src" / "agents" / name / "strategy.py"
    spec = importlib.util.spec_from_file_location(f"_net_{name}_strategy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STRATEGY


def _agent_with_boom(monkeypatch, decide):
    class BoomRuntime:
        deck = tuple(range(1, 61))
        effects = None
        last_read = None
        last_decision_limit = None
        last_deadline_hit = False

        def decide(self, observation):
            return decide(observation)

    monkeypatch.setattr(runtime_module, "build_runtime", lambda *a, **k: BoomRuntime())
    monkeypatch.setattr(runtime_module, "_read_deck", lambda: list(range(1, 61)))
    return runtime_module.make_agent(strategy=None)


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


def test_a_planning_crash_submits_the_end_action(monkeypatch, capsys):
    def boom(_observation):
        raise RuntimeError("native session died")

    agent = _agent_with_boom(monkeypatch, boom)
    observation = _menu([engine_opt(type=3, area=2, index=0), engine_opt(type=14)])

    assert agent(observation) == [1]
    assert "native session died" in capsys.readouterr().err


def test_a_planning_crash_without_an_end_action_submits_the_minimum_picks(monkeypatch):
    def boom(_observation):
        raise ValueError("potential must be finite")

    agent = _agent_with_boom(monkeypatch, boom)
    observation = _menu(
        [engine_opt(type=3, area=2, index=0), engine_opt(type=3, area=2, index=1),
         engine_opt(type=3, area=2, index=2)],
        min_count=2, max_count=2)

    assert agent(observation) == [0, 1]


def test_a_telemetry_failure_never_discards_a_computed_decision(monkeypatch, capsys):
    decision = runtime_module.RootDecision(
        (2,), None, 1.0, True, {"unserializable": object()})
    agent = _agent_with_boom(monkeypatch, lambda _observation: decision)
    observation = _menu([engine_opt(type=3, area=2, index=0)])

    assert agent(observation) == [2]
    assert "telemetry" in capsys.readouterr().err.lower()


def _mega_starmie_runtime():
    strategy = _strategy()
    deck = [int(value) for value in
            (REPO / "src" / "agents" / "mega_starmie" / "deck.csv").read_text().splitlines()
            if value.strip()]
    return runtime_module.build_runtime(
        strategy, deck, stats=None, functions=None, scout=None, briefs=[])


def test_pregame_draw_count_survives_a_dense_non_number_option():
    runtime = _mega_starmie_runtime()
    observation = _menu(
        [engine_opt(type=1), engine_opt(type=0, number=2), engine_opt(type=0, number=1)],
        context=38, turn=0)

    decision = runtime.decide(observation)

    assert decision.chosen == (1,)                   # the largest offered count


def test_pregame_setup_active_survives_dense_card_options():
    runtime = _mega_starmie_runtime()
    cinderace, staryu = runtime.strategy.starter_priority
    observation = _menu(
        [engine_opt(type=3, area=2, index=0), engine_opt(type=3, area=2, index=1)],
        context=1, turn=0)
    observation["current"]["players"][0]["hand"] = [{"id": staryu}, {"id": cinderace}]

    decision = runtime.decide(observation)

    assert decision.chosen == (1,)                   # starter priority, not a crash


def test_planner_setup_survives_a_facedown_opponent_active():
    runtime = _mega_starmie_runtime()
    observation = _menu([engine_opt(type=14)], turn=1)
    observation["current"]["players"][1]["active"] = [None]

    assert runtime._planner(observation) is not None


def test_a_planner_failure_still_closes_the_retained_native_session():
    strategy = _strategy()
    deck = [int(value) for value in
            (REPO / "src" / "agents" / "mega_starmie" / "deck.csv").read_text().splitlines()
            if value.strip()]
    runtime = runtime_module.build_runtime(
        strategy, deck, stats=None, functions=None, scout=None, briefs=[])

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

    with pytest.raises(RuntimeError):
        runtime.decide(observation)
    assert planner.discarded
