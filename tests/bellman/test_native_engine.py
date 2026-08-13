from __future__ import annotations

from functools import partial
import importlib.util
import os
import random
from pathlib import Path

import pytest

from common import Chance, DecisionState, Deterministic, NativeCgTransitionProvider, Terminal, Unknown
from common.runtime import build_runtime
from common.native_engine import _hidden_signature


REPO = Path(__file__).resolve().parents[2]


def test_hidden_signature_tracks_world_contents_not_action_path():
    observation = {"current": {"players": [
        {"deck": [{"id": 1}, {"id": 2}], "prize": [{"id": 3}], "hand": []},
        {"deck": [{"id": 4}], "prize": [{"id": 5}], "hand": [{"id": 6}]},
    ]}}
    same_world_after_another_path = {"current": {"players": [
        {"deck": [{"id": 1}, {"id": 2}], "prize": [{"id": 3}]},
        {"deck": [{"id": 4}], "prize": [{"id": 5}], "hand": [{"id": 6}]},
    ]}, "logs": ["different action path"]}
    different_draw_order = {"current": {"players": [
        {"deck": [{"id": 2}, {"id": 1}], "prize": [{"id": 3}]},
        {"deck": [{"id": 4}], "prize": [{"id": 5}], "hand": [{"id": 6}]},
    ]}}

    signature = _hidden_signature(observation, 0)
    assert signature == _hidden_signature(same_world_after_another_path, 0)
    assert signature != _hidden_signature(different_draw_order, 0)


def test_end_observation_can_preserve_the_actual_next_turn_actor():
    observation = {"current": {"yourIndex": 0, "players": [
        {"deck": [], "prize": [], "hand": []},
        {"deck": [], "prize": [], "hand": []},
    ]}, "select": {"context": 0, "option": []}}
    parent = DecisionState.from_observation(observation, deck=(), deck_name="test")
    provider = object.__new__(NativeCgTransitionProvider)

    successor = provider._observation(observation, parent, actor_seat=1)

    assert successor["current"]["yourIndex"] == 0
    assert successor["bellmanActor"] == 1


pytest.importorskip("cg.sim", reason="native engine unavailable")
if os.environ.get("CG_ENGINE") == "py":
    pytest.skip("production-provider test requires native cg", allow_module_level=True)

from cg.game import battle_finish, battle_select, battle_start  # noqa: E402


def _deck() -> tuple[int, ...]:
    return tuple(int(value) for value in
                 (REPO / "src" / "agents" / "mega_starmie" / "deck.csv").read_text().split())


def _strategy():
    path = REPO / "src" / "agents" / "mega_starmie" / "strategy.py"
    spec = importlib.util.spec_from_file_location("_native_runtime_strategy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STRATEGY


def _first_main(observation):
    rng = random.Random(7)
    for _step in range(200):
        current = observation.get("current") or {}
        select = observation.get("select") or {}
        if int(current.get("turn", 0)) > 0 and int(select.get("context", -1)) == 0:
            return observation
        minimum, maximum = int(select.get("minCount", 0)), int(select.get("maxCount", 0))
        count = minimum if minimum > 0 else (1 if maximum >= 1 else 0)
        options = select.get("option") or ()
        chosen = rng.sample(range(len(options)), min(count, len(options))) if options else []
        observation = battle_select(chosen)
    raise AssertionError("native game did not reach a normal-turn MAIN selection")


def test_production_provider_branches_a_live_native_search_without_hidden_zone_leaks():
    deck = _deck()
    observation, start = battle_start(list(deck), list(deck))
    provider = None
    try:
        assert start.errorPlayer == -1
        observation = _first_main(observation)
        assert observation.get("search_begin_input")
        state = DecisionState.from_observation(
            observation, deck=deck, deck_name="mega_starmie")
        provider = NativeCgTransitionProvider(state, world_count=2)

        assert provider.available, provider._error
        actions = provider.actions(state)
        assert any(action.identity.kind != "end" for action in actions)
        action = next(action for action in actions if action.identity.kind != "end")
        result = provider.transition(state, action)

        assert isinstance(result, (Deterministic, Chance, Terminal))
        assert not isinstance(result, Unknown)
        nodes = (result.node for result in result.children) if isinstance(result, Chance) else (result,)
        for node in nodes:
            successor = node.state
            players = successor.obs["current"]["players"]
            assert all(card is None for player in players for card in (player.get("prize") or ()))
            assert players[1 - successor.root_seat]["hand"] is None
    finally:
        if provider is not None:
            provider.close()
        battle_finish()


def test_production_runtime_plays_a_card_instead_of_falling_back_to_end():
    deck = _deck()
    observation, start = battle_start(list(deck), list(deck))
    try:
        assert start.errorPlayer == -1
        observation = _first_main(observation)
        runtime = build_runtime(
            _strategy(), deck, scout=None, briefs=[],
            provider_factory=partial(NativeCgTransitionProvider, world_count=1),
        )

        decision = runtime.decide(observation)

        assert decision.action.kind != "end"
        assert decision.diagnostics["backend"] == "native-cg-bellman"
    finally:
        battle_finish()
