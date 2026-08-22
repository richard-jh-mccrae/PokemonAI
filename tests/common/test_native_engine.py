from __future__ import annotations

from observation_builders import build_observation, advance_observation

from functools import partial
import importlib.util
import os
import random
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from common import (
    Chance,
    Deterministic,
    NativeCgTransitionProvider,
    Terminal,
    Unknown,
    enumerate_legal_actions,
)
from deprecated.bellman.state import DecisionState
from common.engine import CgpyTransitionProvider
from common.runtime import build_runtime
from common.native_engine import _hidden_signature


REPO = Path(__file__).resolve().parents[2]


def test_partial_ability_that_resolves_as_a_noop_fails_closed():
    observation = {
        "current": {"yourIndex": 0, "turnActionCount": 1,
                    "players": [{"hand": [], "active": [], "bench": [], "discard": []},
                                {"hand": None, "active": [], "bench": [], "discard": []}],
                    "stadium": [{"id": 1259, "playerIndex": 1}]},
        "select": {"context": 0, "minCount": 1, "maxCount": 1,
                   "option": [{"type": 10, "area": 7, "index": 0}]},
    }
    state = DecisionState.from_observation(observation, deck=(), deck_name="test")
    successor_observation = deepcopy(observation)
    successor_observation["current"]["turnActionCount"] = 2
    successor_observation["select"]["option"] = [{"type": 14}]
    successor = state.with_observation(successor_observation)
    child = SimpleNamespace(gs=SimpleNamespace(pending=None), step=lambda _choice: None)
    engine = SimpleNamespace(fork=lambda: child)
    from common.cards.card_facts import Clause, STADIUM, TrainerCard
    provider = object.__new__(CgpyTransitionProvider)
    provider._local_nested = False
    provider._engines = {state.semantic_key: engine}
    provider.cards = {1259: TrainerCard(
        1259, "Test Stadium", STADIUM,
        clauses=(Clause("fetch", target="pokemon", zone="deck", name_family="Marnie's"),))}
    provider.effects = None
    provider.stats = None
    provider._register_successor = lambda *_args: Deterministic(successor)

    result = provider.transition(state, enumerate_legal_actions(observation)[0])

    assert isinstance(result, Unknown)
    assert result.reason == "unsupported ability produced no observable effect"


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
    provider.stats = None            # no printed attacks to read, so no self-lock can fold

    successor = provider._observation(observation, parent, actor_seat=1)

    assert successor["current"]["yourIndex"] == 0
    assert provider._provider_metadata[id(successor)]["actor_seat"] == 1
    assert "bellmanActor" not in successor


def test_successor_preserves_unchanged_root_hand_when_native_perspective_flips():
    known_hand = [{"id": 3, "serial": 10}, {"id": 1086, "serial": 20}]
    parent_observation = {"current": {"yourIndex": 0, "players": [
        {"deck": [], "prize": [], "hand": known_hand, "handCount": 2},
        {"deck": [], "prize": [], "hand": None, "handCount": 4},
    ]}, "select": {"context": 0, "option": []}}
    native_successor = {"current": {"yourIndex": 1, "players": [
        {"deck": [], "prize": [], "hand": None, "handCount": 2},
        {"deck": [], "prize": [], "hand": [{"id": 1}] * 4, "handCount": 4},
    ]}, "select": {"context": 0, "option": []}}
    parent = DecisionState.from_observation(parent_observation, deck=(), deck_name="test")
    provider = object.__new__(NativeCgTransitionProvider)
    provider.stats = None            # no printed attacks to read, so no self-lock can fold

    successor = provider._observation(native_successor, parent, actor_seat=1)

    assert successor["current"]["players"][0]["hand"] == known_hand
    assert successor["current"]["players"][1]["hand"] is None


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


def test_production_runtime_returns_a_legal_native_action_without_fallback():
    deck = _deck()
    observation, start = battle_start(list(deck), list(deck))
    try:
        assert start.errorPlayer == -1
        observation = _first_main(observation)
        runtime = build_runtime(
            _strategy(), deck,
            provider_factory=partial(NativeCgTransitionProvider, world_count=1),
        )
        legal_selections = {action.selection for action in enumerate_legal_actions(observation)}

        decision = runtime.decide(observation)

        assert decision.chosen in legal_selections
        assert decision.diagnostics["backend"] == "ledger"
    finally:
        battle_finish()


def test_preview_seam_prices_match_the_decisionstate_path_on_native():
    """ADR-0146's native half: the light PreviewState path and the heavy DecisionState path
    must price every root option identically on a live native frame."""
    from common.observation import ObservationState
    from common.ledger import EvaluationModel, LedgerNativeProvider, PreviewState
    from common.ledger.evaluate import evaluate
    from common.ledger.preview import price_actions

    deck = _deck()
    observation, start = battle_start(list(deck), list(deck))
    try:
        assert start.errorPlayer == -1
        observation = _first_main(observation)
        ctx = EvaluationModel.build()
        board = build_observation(observation, decklist=deck)
        baseline = evaluate(board, ctx).total

        heavy_state = DecisionState.from_observation(observation, deck=deck,
                                                     deck_name="mega_starmie")
        heavy_provider = NativeCgTransitionProvider(heavy_state, world_count=1)
        try:
            heavy = price_actions(heavy_state, board, baseline, heavy_provider, ctx)
        finally:
            heavy_provider.close()

        light_state = PreviewState(observation, board.seat, "root", deck=deck,
                                   deck_counts=board.deck_counts or (),
                                   prize_counts=getattr(board.knowledge.own_prizes, "cards", ()))
        light_provider = LedgerNativeProvider(light_state, world_count=1)
        try:
            light = price_actions(light_state, board, baseline, light_provider, ctx)
        finally:
            light_provider.close()

        heavy_prices = {str(p.action.identity): round(p.swing, 9) for p in heavy}
        light_prices = {str(p.action.identity): round(p.swing, 9) for p in light}
        assert light_prices == heavy_prices
    finally:
        battle_finish()
