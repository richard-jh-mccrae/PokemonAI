"""Forced and degraded decisions stay legal inside the coordinator contract."""
from __future__ import annotations

import importlib.util
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path

import pytest

import common.runtime as runtime_module
from observation_helpers import engine_opt


REPO = Path(__file__).resolve().parents[2]


def test_external_decision_limit_sets_the_inner_search_budget(monkeypatch):
    monkeypatch.setenv("AGENT_DECISION_SECONDS", "20")

    compute = runtime_module._compute_configuration_from_environment()

    assert compute.search.time_budget_ms == 19_000


def test_correction_limit_becomes_failure_containment_not_search_allocation(monkeypatch):
    monkeypatch.setenv("AGENT_LEDGER_COMPUTE_PROFILE", "correction")
    monkeypatch.setenv("AGENT_DECISION_SECONDS", "20")

    compute = runtime_module._compute_configuration_from_environment()
    containment = runtime_module._decision_containment_seconds_from_environment()

    assert compute.search.time_budget_ms is None
    assert containment == 19.0


def test_correction_agent_wires_the_failure_containment_limit(monkeypatch):
    captured = {}

    class Runtime:
        deck = tuple(range(1, 61))
        opponent_snapshot = None

    def build(*_args, **kwargs):
        captured.update(kwargs)
        return Runtime()

    monkeypatch.setenv("AGENT_LEDGER_COMPUTE_PROFILE", "correction")
    monkeypatch.setenv("AGENT_DECISION_SECONDS", "20")
    monkeypatch.setattr(runtime_module, "build_runtime", build)
    monkeypatch.setattr(runtime_module, "_read_deck", lambda: list(range(1, 61)))

    runtime_module.make_agent(strategy=None)

    assert captured["decision_containment_seconds"] == 19.0


@pytest.mark.parametrize("seconds", ("0.05", "0.1"))
def test_external_decision_limit_rejects_an_outer_clock_without_fallback_room(
        monkeypatch, seconds):
    monkeypatch.setenv("AGENT_DECISION_SECONDS", seconds)

    with pytest.raises(ValueError, match="greater than 0.1"):
        runtime_module._compute_configuration_from_environment()


def test_default_search_budget_is_unchanged_without_an_external_limit(monkeypatch):
    monkeypatch.delenv("AGENT_DECISION_SECONDS", raising=False)

    compute = runtime_module._compute_configuration_from_environment()

    assert compute.search.time_budget_ms == 1_000


def _strategy(name: str = "mega_starmie"):
    path = REPO / "src" / "agents" / name / "strategy.py"
    spec = importlib.util.spec_from_file_location(f"_net_{name}_strategy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STRATEGY


def _agent_with_boom(monkeypatch, decide):
    def broken_provider(state, **_kwargs):
        decide(state._provider_payload)
        raise AssertionError("failure fixture did not raise")

    runtime = _mega_starmie_runtime(provider_factory=broken_provider)
    monkeypatch.setattr(runtime_module, "build_runtime", lambda *a, **k: runtime)
    monkeypatch.setattr(runtime_module, "_read_deck", lambda: list(runtime.deck))
    return runtime_module.make_agent(strategy=None)


def _agent_with_decision(monkeypatch, decide):
    class BoomRuntime:
        deck = tuple(range(1, 61))
        opponent_snapshot = None

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
    agent = _agent_with_decision(monkeypatch, lambda _observation: decision)
    observation = _menu([engine_opt(type=3, area=2, index=0)])

    assert agent(observation) == [2]
    assert "telemetry" in capsys.readouterr().err.lower()


def test_deck_submission_is_the_only_protocol_bypass(monkeypatch):
    calls = []

    class RecordingRuntime:
        deck = tuple(range(1, 61))
        opponent_snapshot = None

        def decide(self, observation):
            calls.append(observation)
            return runtime_module.RootDecision(
                (), runtime_module.ActionIdentity("decline"), 0.0, True,
                {"backend": "ledger"})

    monkeypatch.setattr(runtime_module, "build_runtime", lambda *a, **k: RecordingRuntime())
    monkeypatch.setattr(runtime_module, "_read_deck", lambda: list(range(1, 61)))
    agent = runtime_module.make_agent(strategy=None)

    assert runtime_module.PROTOCOL_BYPASS_ALLOWLIST == frozenset({"deck_submission"})
    assert agent({"select": None, "current": None}) == list(range(1, 61))
    assert calls == []

    with pytest.raises(ValueError, match="not an approved protocol bypass"):
        agent({"select": None, "current": {"result": 0}})
    assert calls == []

    game_menu = _menu([], min_count=0, max_count=0)
    assert agent(game_menu) == []
    assert calls == [game_menu]


def _mega_starmie_runtime(**kwargs):
    strategy = _strategy()
    deck = [int(value) for value in
            (REPO / "src" / "agents" / "mega_starmie" / "deck.csv").read_text().splitlines()
            if value.strip()]
    return runtime_module.build_runtime(strategy, deck, stats=None, **kwargs)


def test_post_pregame_forced_menu_is_a_complete_ledger_decision_without_preview():
    def forbidden_provider(_state, **_kwargs):
        raise AssertionError("forced decision must not construct a transition provider")

    runtime = _mega_starmie_runtime(provider_factory=forbidden_provider)
    observation = _menu([engine_opt(type=14)], context=0, turn=2)

    decision = runtime.decide(observation)

    assert decision.diagnostics["backend"] == "ledger"
    assert decision.diagnostics["policy_reason"] == "forced"
    assert decision.complete is False
    assert decision.value == 0.0
    assert decision.chosen == (0,)
    assert decision.diagnostics["prices"] == ({
        "action": str(decision.action),
        "selection": [0],
        "swing": None,
        "ends_turn": False,
        "status": "unavailable",
        "continuation": None,
    },)


def test_live_runtime_captures_the_typed_ledger_record(monkeypatch):
    from common.telemetry import capture_records

    runtime = _mega_starmie_runtime(provider_factory=lambda *_a, **_kw: None)
    monkeypatch.setattr(runtime_module, "build_runtime", lambda *a, **k: runtime)
    monkeypatch.setattr(runtime_module, "_read_deck", lambda: list(runtime.deck))
    monkeypatch.delenv("AGENT_NO_TELEMETRY", raising=False)
    agent = runtime_module.make_agent(strategy=None)
    observation = _menu([engine_opt(type=14)], context=0, turn=2)

    with capture_records() as records:
        assert agent(observation) == [0]

    assert len(records) == 1
    assert records[0]["record_type"] == "decision"
    assert records[0]["decision"]["chosen_action_id"] == records[0]["actions"][0]["id"]
    assert records[0]["candidates"][0]["status"] == "unavailable"
    assert records[0]["configuration"]["evaluation_model"]["identity"] \
        == runtime.ledger.ctx.identity
    assert records.construction_seconds > 0.0
    assert records.delivery_seconds > 0.0
    assert records.emit_seconds >= records.construction_seconds


def test_pregame_telemetry_is_explicit_and_has_no_invented_ledger_values(monkeypatch):
    from common.telemetry import capture_records, episode_context

    runtime = _mega_starmie_runtime(provider_factory=lambda *_a, **_kw: None)
    monkeypatch.setattr(runtime_module, "build_runtime", lambda *a, **k: runtime)
    monkeypatch.setattr(runtime_module, "_read_deck", lambda: list(runtime.deck))
    monkeypatch.delenv("AGENT_NO_TELEMETRY", raising=False)
    agent = runtime_module.make_agent(strategy=None)

    with episode_context("owner-episode"), capture_records() as records:
        assert agent(_menu([engine_opt(type=14)], context=0, turn=0)) == [0]

    assert records[0]["episode"]["key"] == "owner-episode"
    assert records[0]["decision"]["variant"] == "declarative_pregame"
    assert records[0]["root"] is None
    assert records[0]["candidates"] == []
    assert records[0]["search"] is None
    assert records[0]["completeness"] == "not_evaluated"


def test_production_runtime_emits_a_reassemblable_record(monkeypatch):
    from common.telemetry import episode_context, flush, parse_lines

    runtime = _mega_starmie_runtime(provider_factory=lambda *_a, **_kw: None)
    monkeypatch.setattr(runtime_module, "build_runtime", lambda *a, **k: runtime)
    monkeypatch.setattr(runtime_module, "_read_deck", lambda: list(runtime.deck))
    monkeypatch.delenv("AGENT_NO_TELEMETRY", raising=False)
    agent = runtime_module.make_agent(strategy=None)
    output = StringIO()

    with redirect_stderr(output), episode_context("production-emission"):
        agent(_menu([engine_opt(type=14)], context=0, turn=2))
        flush()

    records = parse_lines(output.getvalue().splitlines())
    assert len(records) == 1
    assert records[0]["record_type"] == "decision"
    assert records[0]["episode"]["key"] == "production-emission"


def test_one_canonical_action_with_equivalent_selections_is_still_forced():
    def forbidden_provider(_state, **_kwargs):
        raise AssertionError("forced decision must not construct a transition provider")

    runtime = _mega_starmie_runtime(provider_factory=forbidden_provider)
    observation = _menu([engine_opt(type=14), engine_opt(type=14)], context=0, turn=2)

    decision = runtime.decide(observation)

    assert decision.diagnostics["policy_reason"] == "forced"
    assert decision.complete is False
    assert decision.value == 0.0
    assert len(decision.diagnostics["prices"]) == 1


def test_post_pregame_provider_failure_is_a_typed_ledger_fail_safe_decision():
    def broken_provider(_state, **_kwargs):
        raise RuntimeError("native session died")

    runtime = _mega_starmie_runtime(provider_factory=broken_provider)
    observation = _menu([
        engine_opt(type=3, area=2, index=0),
        engine_opt(type=14),
    ], context=0, turn=2)

    decision = runtime.decide(observation)

    assert decision.diagnostics["backend"] == "ledger"
    assert decision.diagnostics["policy_reason"] == "fail_safe_provider_failure"
    assert decision.complete is False
    assert decision.chosen == (1,)
    assert decision.diagnostics["failure"]["stage"] == "provider"
    assert decision.diagnostics["failure"]["error_type"] == "RuntimeError"
    assert "native session died" in decision.diagnostics["failure"]["message"]
    assert {price["status"] for price in decision.diagnostics["prices"]} == {"unavailable"}
    assert {tuple(price["selection"]) for price in decision.diagnostics["prices"]} == {
        (0,), (1,),
    }


def test_every_post_pregame_menu_enters_the_decision_coordinator_once():
    def broken_provider(_state, **_kwargs):
        raise RuntimeError("provider unavailable")

    runtime = _mega_starmie_runtime(provider_factory=broken_provider)
    entered = []
    real = runtime.ledger.coordinator

    class RecordingCoordinator:
        def decide(self, *args, **kwargs):
            entered.append(args[0])
            return real.decide(*args, **kwargs)

    runtime.ledger.coordinator = RecordingCoordinator()

    runtime.decide(_menu([engine_opt(type=0, number=1)], context=38, turn=0))
    assert entered == []

    runtime.decide(_menu([engine_opt(type=14)], context=0, turn=2))
    assert len(entered) == 1

    runtime.decide(_menu([
        engine_opt(type=3, area=2, index=0),
        engine_opt(type=14),
    ], context=0, turn=2))
    assert len(entered) == 2

    malformed = _menu([
        engine_opt(type=3, area=2, index=0),
        engine_opt(type=14),
    ], context=0, turn=2)
    malformed["current"]["players"] = malformed["current"]["players"][:1]
    decision = runtime.decide(malformed)
    assert len(entered) == 3
    assert decision.chosen == (1,)
    assert decision.diagnostics["policy_reason"] == "fail_safe_runtime_failure"


def test_a_post_coordinator_mapping_bug_returns_the_same_typed_choice_without_reentry():
    runtime = _mega_starmie_runtime(
        provider_factory=lambda _state, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("provider unavailable")))
    entered = 0
    real = runtime.ledger.coordinator

    class RecordingCoordinator:
        def decide(self, *args, **kwargs):
            nonlocal entered
            entered += 1
            return real.decide(*args, **kwargs)

        def recover(self, *args, **kwargs):
            return real.recover(*args, **kwargs)

    runtime.ledger.coordinator = RecordingCoordinator()
    runtime.ledger._root_decision = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("mapping bug"))

    decision = runtime.decide(_menu([
        engine_opt(type=3, area=2, index=0),
        engine_opt(type=14),
    ], context=0, turn=2))
    assert entered == 1
    assert decision.decision_result is not None
    assert decision.chosen == tuple(decision.decision_result.chosen_candidate.action.selection)
    assert decision.diagnostics["failure"]["stage"] == "presentation"


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


def test_each_effect_menu_is_decided_from_its_current_observation():
    deployed = _mega_starmie_runtime()
    calls = 0

    def timed_out(_state, _observation):
        nonlocal calls
        calls += 1
        return runtime_module.RootDecision(
            (0,), runtime_module.ActionIdentity("card"), 1.0, False,
            {})

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
    assert deployed.decide(observation).chosen == (0,)
    assert calls == 2

    observation["select"] = {
        "context": 0, "minCount": 1, "maxCount": 1,
        "option": [engine_opt(type=14)],
    }
    deployed.decide(observation)
    assert calls == 3
