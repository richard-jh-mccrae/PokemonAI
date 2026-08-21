"""Planning failure and deadline fallback always submit a productive legal choice."""
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
        last_read = None
        last_decision_limit = None
        last_deadline_hit = False

        def decide(self, observation):
            return decide(observation)

    monkeypatch.setattr(runtime_module, "build_runtime", lambda *a, **k: BoomRuntime())
    monkeypatch.setattr(runtime_module, "_read_deck", lambda: list(range(1, 61)))
    return runtime_module.make_agent(strategy=None)


def _menu(options, *, min_count=1, max_count=1, context=0, turn=2):
    side = {"hand": [], "handCount": 0, "active": [], "bench": [], "benchMax": 5,
            "discard": [], "prize": [], "deckCount": 0, "poisoned": False,
            "burned": False, "asleep": False, "paralyzed": False, "confused": False}
    return {
        "select": {"context": context, "minCount": min_count, "maxCount": max_count,
                   "option": list(options)},
        "current": {"turn": turn, "yourIndex": 0, "firstPlayer": 0,
                    "supporterPlayed": False, "stadiumPlayed": False,
                    "energyAttached": False, "retreated": False, "result": None,
                    "stadium": [], "looking": None, "players": [
            dict(side),
            {**side, "hand": None},
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


def test_a_planning_crash_never_declines_an_optional_productive_fetch(monkeypatch):
    def boom(_observation):
        raise RuntimeError("search deadline")

    agent = _agent_with_boom(monkeypatch, boom)
    observation = _menu(
        [engine_opt(type=3, area=12, index=0), engine_opt(type=3, area=12, index=1)],
        min_count=0, max_count=1, context=7)

    assert agent(observation) == [0]


def test_a_planning_crash_takes_the_maximum_fetch_to_hand(monkeypatch):
    def boom(_observation):
        raise RuntimeError("search deadline")

    agent = _agent_with_boom(monkeypatch, boom)
    observation = _menu(
        [engine_opt(type=3, area=12, index=index) for index in range(3)],
        min_count=0, max_count=2, context=7)

    assert agent(observation) == [0, 1]


def test_a_planning_crash_respects_a_zero_maximum_fetch(monkeypatch):
    def boom(_observation):
        raise RuntimeError("search deadline")

    agent = _agent_with_boom(monkeypatch, boom)
    observation = _menu(
        [engine_opt(type=3, area=12, index=0)],
        min_count=0, max_count=0, context=7)

    assert agent(observation) == []


def test_a_planning_crash_fills_a_multi_card_field_placement(monkeypatch):
    def boom(_observation):
        raise RuntimeError("search deadline")

    agent = _agent_with_boom(monkeypatch, boom)
    observation = _menu(
        [engine_opt(type=3, area=12, index=index) for index in range(3)],
        min_count=2, max_count=3, context=5)

    assert agent(observation) == [0, 1]


def test_a_planning_crash_places_damage_on_an_available_ko(monkeypatch):
    def boom(_observation):
        raise RuntimeError("search deadline")

    agent = _agent_with_boom(monkeypatch, boom)
    observation = _menu(
        [engine_opt(type=3, area=5, index=0, playerIndex=1),
         engine_opt(type=3, area=5, index=1, playerIndex=1)],
        context=14)
    observation["select"]["remainDamageCounter"] = 6
    observation["current"]["players"][1]["bench"] = [
        {"id": 10, "serial": 10, "hp": 120, "maxHp": 120},
        {"id": 11, "serial": 11, "hp": 50, "maxHp": 100},
    ]

    assert agent(observation) == [1]


def test_a_planning_crash_spends_the_full_draw_or_damage_count(monkeypatch):
    def boom(_observation):
        raise RuntimeError("search deadline")

    agent = _agent_with_boom(monkeypatch, boom)
    draw = _menu(
        [engine_opt(type=0, number=1), engine_opt(type=0, number=3)], context=38)
    counters = _menu(
        [engine_opt(type=0, number=1), engine_opt(type=0, number=6)], context=39)

    assert agent(draw) == [1]
    assert agent(counters) == [1]


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


def test_one_effect_timeout_latches_the_fallback_until_main_returns():
    deployed = _mega_starmie_runtime()
    calls = 0

    def timed_out(_state, _observation):
        nonlocal calls
        calls += 1
        return runtime_module.RootDecision(
            (0,), runtime_module.ActionIdentity("card"), 1.0, False,
            {"production": {"deadline_hit": True}})

    deployed._decide_core = timed_out
    observation = _menu(
        [engine_opt(type=3, area=5, index=0, playerIndex=1),
         engine_opt(type=3, area=5, index=1, playerIndex=1)], context=14)
    observation["select"]["remainDamageCounter"] = 6
    observation["current"]["players"][1]["bench"] = [
        {"id": 10, "serial": 10, "hp": 120, "maxHp": 120},
        {"id": 11, "serial": 11, "hp": 50, "maxHp": 100},
    ]

    assert deployed.decide(observation).chosen == (0,)
    assert deployed.decide(observation).chosen == (1,)
    assert calls == 1

    observation["select"] = {
        "context": 0, "minCount": 1, "maxCount": 1,
        "option": [engine_opt(type=14)],
    }
    deployed.decide(observation)
    assert calls == 2
