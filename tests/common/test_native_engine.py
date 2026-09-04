from __future__ import annotations

from observation_builders import build_observation, advance_observation

from contextlib import ExitStack
from functools import partial
import importlib.util
import json
import os
import random
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from common import (
    Chance,
    Choice,
    Deterministic,
    NativeCgTransitionProvider,
    Terminal,
    Unknown,
    enumerate_legal_actions,
)
from deprecated.bellman.state import DecisionState
from common.engine import CgpyTransitionProvider
from common.deck_tracker import OwnCardModel
from common.observation import ObservationStateBuilder, reduce_knowledge
from common.runtime import build_runtime
from common.telemetry import (build_outcome_record, capture_records, emit,
                              episode_context, runtime_provenance)
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


def test_isolated_triggered_gust_exposes_each_visible_bench_target():
    observation = {
        "current": {
            "yourIndex": 0, "turnActionCount": 1,
            "players": [
                {"hand": [], "active": [{"id": 674}], "bench": [], "discard": []},
                {"hand": None, "active": [{"id": 65}],
                 "bench": [{"id": 119}, {"id": 235}], "discard": []},
            ]},
        "select": {
            "type": 9, "context": 43, "minCount": 1, "maxCount": 1,
            "contextCard": {"id": 674, "playerIndex": 0},
            "option": [{"type": 1}, {"type": 2}]},
    }
    state = SimpleNamespace(
        root_seat=0, observation=observation, provider_payload=observation,
        with_observation=lambda value: SimpleNamespace(observation=value))
    provider = object.__new__(CgpyTransitionProvider)
    provider._local_nested = True
    from common.cards import card_store
    provider.cards = card_store()

    yes = next(action for action in enumerate_legal_actions(observation)
               if action.identity.kind == "yes")
    result = provider.transition(state, yes)

    assert isinstance(result, Choice)
    assert {
        edge.node.state.observation["current"]["players"][1]["active"][0]["id"]
        for edge in result.children
    } == {119, 235}


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

    observation["current"]["yourIndex"] = 1
    successor = provider._observation(observation, parent)

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

    native_successor["logs"] = [{"type": 3, "playerIndex": 0}]
    successor = provider._observation(native_successor, parent)

    assert successor["current"]["players"][0]["hand"] == known_hand
    assert successor["current"]["players"][1]["hand"] is None


def test_successor_treats_empty_positive_count_root_hand_as_hidden():
    known_hand = [{"id": 3, "serial": 10}, {"id": 1086, "serial": 20}]
    parent_observation = {"current": {"yourIndex": 0, "players": [
        {"deck": [], "prize": [], "hand": known_hand, "handCount": 2},
        {"deck": [], "prize": [], "hand": None, "handCount": 4},
    ]}, "select": {"context": 0, "option": []}}
    native_successor = {"current": {"yourIndex": 1, "players": [
        {"deck": [], "prize": [], "hand": [], "handCount": 2},
        {"deck": [], "prize": [], "hand": [{"id": 1}] * 4, "handCount": 4},
    ]}, "select": {"context": 0, "option": []}}
    parent = SimpleNamespace(
        root_seat=0, prize_counts=(), _provider_payload=parent_observation)
    provider = object.__new__(NativeCgTransitionProvider)

    native_successor["logs"] = [{"type": 3, "playerIndex": 0}]
    successor = provider._observation(native_successor, parent)

    assert successor["current"]["players"][0]["hand"] == known_hand


def test_successor_adds_known_taken_prize_to_hidden_root_hand():
    known_hand = [{"id": 3, "serial": 10}]
    parent_observation = {"current": {"yourIndex": 0, "players": [
        {"deck": [], "prize": [None, None], "hand": known_hand, "handCount": 1},
        {"deck": [], "prize": [], "hand": None, "handCount": 0},
    ]}, "select": {"context": 0, "option": []}}
    native_successor = {"current": {"yourIndex": 1, "players": [
        {"deck": [], "prize": [{"id": 100}], "hand": [], "handCount": 2},
        {"deck": [], "prize": [], "hand": [], "handCount": 0},
    ]}, "select": {"context": 0, "option": []}}
    parent = SimpleNamespace(
        root_seat=0, prize_counts=((99, 1), (100, 1)),
        _provider_payload=parent_observation)
    provider = object.__new__(NativeCgTransitionProvider)

    native_successor["logs"] = [{"type": 7, "playerIndex": 0, "fromArea": 6, "toArea": 2}]
    successor = provider._observation(native_successor, parent)

    assert successor["current"]["players"][0]["hand"] == [*known_hand, {"id": 99}]
    assert successor["current"]["players"][0]["prize"] == [None]


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


def test_configured_puct_backends_replay_inside_a_spawned_worker():
    from common.puct import NativeTurnSearchProvider
    from common.puct.workers import BoundedWorkers, WorkItem
    from common.decision.turn import (NATIVE_ENGINE_BACKEND, NodeKind, ProviderCompletion,
                                      WorkerTurnSearchProvider)
    from cgpy.puct import ENGINE_BACKEND as CGPY_ENGINE_BACKEND

    deck = _deck()
    observation, start = battle_start(list(deck), list(deck))
    workers = BoundedWorkers(1, outstanding_limit=1)
    try:
        assert start.errorPlayer == -1
        observation = _first_main(observation)
        board = build_observation(observation, decklist=deck)
        boundaries = []
        for task_id, backend in enumerate((NATIVE_ENGINE_BACKEND, CGPY_ENGINE_BACKEND)):
            provider = NativeTurnSearchProvider.from_observation(
                observation, board, backend=backend)
            assert isinstance(provider, WorkerTurnSearchProvider)
            end = next(action for action in provider.legal_actions(provider.root)
                       if action.identity.kind == "end")
            job = provider.work_item(provider.root, "transition", (end.identity,))

            result = workers.run_batch(
                (WorkItem(task_id, job.function, job.arguments),),
                deadline=time.monotonic() + 20)

            assert job.arguments[0] == backend
            assert len(result) == 1 and result[0].error_type is None, result
            completion = result[0].value
            assert isinstance(completion, ProviderCompletion)
            assert completion.operation_units >= 1
            assert completion.state_capacity >= 2
            assert completion.value.kind in (
                NodeKind.TURN_BOUNDARY, NodeKind.INFORMATION_BOUNDARY)
            boundary = completion.value.observation
            boundaries.append((
                boundary.turn.number, boundary.them.deck_count,
                boundary.them.hand.count, boundary.position_key))
        assert boundaries[0] == boundaries[1]
    finally:
        workers.close()
        battle_finish()


def test_native_puct_search_identity_ignores_private_replay_input():
    from common.puct import NativeTurnSearchProvider

    deck = _deck()
    observation, start = battle_start(list(deck), list(deck))
    try:
        assert start.errorPlayer == -1
        observation = _first_main(observation)
        board = build_observation(observation, decklist=deck)
        changed = deepcopy(observation)
        changed["search_begin_input"] = "private-replay-data-must-not-key-search"

        first = NativeTurnSearchProvider.from_observation(observation, board)
        second = NativeTurnSearchProvider.from_observation(changed, board)

        assert first.root.state_key == second.root.state_key
    finally:
        battle_finish()


def test_native_puct_samples_shuffle_draw_and_replays_the_continuation():
    from common.puct import NativeTurnSearchProvider
    from common.puct.workers import BoundedWorkers, WorkItem
    from common.decision.turn import NodeKind, ProviderCompletion

    deck = _deck()
    workers = BoundedWorkers(1, outstanding_limit=1)
    observation = None
    try:
        for _attempt in range(20):
            candidate, start = battle_start(list(deck), list(deck))
            assert start.errorPlayer == -1
            candidate = _first_main(candidate)
            for _step in range(100):
                actions = enumerate_legal_actions(candidate)
                if any(action.identity.kind == "play" and "1227" in str(action.identity.parts)
                       for action in actions):
                    observation = candidate
                    break
                end = next((action for action in actions if action.identity.kind == "end"), None)
                chosen = end or (actions[0] if actions else None)
                if chosen is None:
                    break
                candidate = battle_select(list(chosen.selection))
            if observation is not None:
                break
            battle_finish()
        assert observation is not None, "native setup did not deal the configured draw Supporter"
        board = build_observation(observation, decklist=deck)
        provider = NativeTurnSearchProvider.from_observation(observation, board)
        lillie = next(action for action in provider.legal_actions(provider.root)
                      if action.identity.kind == "play" and "1227" in str(action.identity.parts))
        transition = provider.work_item(provider.root, "transition", (lillie.identity,))
        first = workers.run_batch(
            (WorkItem(0, transition.function, transition.arguments),),
            deadline=time.monotonic() + 20)[0]
        assert first.error_type is None and isinstance(first.value, ProviderCompletion)
        chance = first.value.value
        assert chance.kind is NodeKind.CHANCE
        assert provider.chance_plan(chance, 8).method == "bounded_shuffle_draw"

        sample = provider.work_item(chance, "sample_for_search", (607, 3))
        second = workers.run_batch(
            (WorkItem(1, sample.function, sample.arguments, sample.affinity),),
            deadline=time.monotonic() + 20)[0]

        assert second.error_type is None and isinstance(second.value, ProviderCompletion)
        assert second.value.value.kind is NodeKind.PLAYER_DECISION
        assert second.value.value.observation.me.hand_count == 8
        assert provider.legal_actions(second.value.value)
        repeated = workers.run_batch(
            (WorkItem(3, sample.function, sample.arguments, sample.affinity),),
            deadline=time.monotonic() + 20)[0]
        assert repeated.error_type is None
        assert (repeated.value.value.observation.decision_key
                == second.value.value.observation.decision_key)
        follow = provider.legal_actions(second.value.value)[0]
        continuation = provider.work_item(second.value.value, "transition", (follow.identity,))
        third = workers.run_batch(
            (WorkItem(2, continuation.function, continuation.arguments,
                      continuation.affinity),),
            deadline=time.monotonic() + 20)[0]
        assert third.error_type is None and isinstance(third.value, ProviderCompletion)
    finally:
        workers.close()
        battle_finish()


def test_native_puct_completes_a_bounded_root_search():
    from common.puct import (NativeTurnSearchProvider, PuctConfiguration,
                             build_puct_coordinator)
    from common.decision.puct import PuctOutcome

    baseline = "98a582d49a32146b18e59beed0019041ce1745fd653e94f7d9c86f8cf0aec92d"
    deck = _deck()
    observation, start = battle_start(list(deck), list(deck))
    search = None
    try:
        assert start.errorPlayer == -1
        observation = _first_main(observation)
        runtime = build_runtime(_strategy(), deck)
        board = build_observation(observation, decklist=deck)
        provider = NativeTurnSearchProvider.from_observation(observation, board)
        coordinator = build_puct_coordinator(
            runtime.ledger.ctx, baseline_identity=baseline,
            baseline_path=REPO / "data" / "ledger-baselines" / baseline / "manifest.json",
            calibration_path=REPO / "data" / "ledger-policy-calibrations" / f"{baseline}.json",
            prior_mode="uniform", provider_identity=provider.identity,
            configuration=PuctConfiguration(
                simulation_limit=4, batch_size=2, worker_count=2, chance_samples=4,
                transition_limit=100, evaluation_limit=100, chance_limit=20,
                state_limit=200, time_limit_seconds=30, cleanup_reserve_seconds=2))
        search = coordinator.search

        decision = coordinator.decide(provider.root, provider=provider, strict=True)

        assert decision.search.puct.outcome is PuctOutcome.SEARCHED, decision.search.failure
        assert decision.chosen is not None
        assert decision.search.puct.simulations == 4
        assert decision.search.puct.work.transitions > 0
        assert decision.search.puct.retained_engine_states == 0
        assert decision.search.puct.peak_retained_engine_states > 0
        replay = json.loads(decision.search.puct.reproduction_input)
        assert replay["payload"]["search_begin_input"] == observation["search_begin_input"]
        transitions = next(item for item in decision.search.puct.resources
                           if item.category == "transitions")
        assert transitions.reserved > transitions.attempted >= transitions.completed
    finally:
        if search is not None:
            search.close()
        battle_finish()


def test_agent_runtime_can_select_puct_independently_for_each_backend():
    from common.decision.turn import NATIVE_ENGINE_BACKEND
    from common.puct import PuctConfiguration
    from common.runtime import DecisionPilot, DecisionSearchConfiguration
    from common.telemetry import build_decision_record
    from cgpy.puct import ENGINE_BACKEND as CGPY_ENGINE_BACKEND

    deck = _deck()
    observation, start = battle_start(list(deck), list(deck))
    runtimes = []
    public_results = []
    try:
        assert start.errorPlayer == -1
        observation = _first_main(observation)
        for backend in (NATIVE_ENGINE_BACKEND, CGPY_ENGINE_BACKEND):
            runtime = build_runtime(
                _strategy(), deck,
                decision_configuration=DecisionSearchConfiguration(
                    DecisionPilot.PUCT, backend,
                    PuctConfiguration(
                        profile="play", simulation_limit=4, batch_size=2,
                        worker_count=2, chance_samples=4, transition_limit=100,
                        evaluation_limit=100, chance_limit=20, state_limit=200,
                        time_limit_seconds=30, cleanup_reserve_seconds=2)))
            runtimes.append(runtime)

            decision = runtime.decide(observation)

            assert decision.diagnostics["pilot"] == "puct"
            assert decision.diagnostics["backend"] == backend.name
            assert decision.diagnostics["engine_backend"] == backend.name
            assert decision.decision_result.search.puct.simulations == 4
            assert decision.chosen in tuple(
                action.selection for action in runtime.last_state.legal_actions)
            record = build_decision_record(
                decision.decision_result, runtime.last_state,
                episode_key=f"puct-{backend.name}", decision_index=0,
                parent_decision_id=None, selection=decision.chosen,
                evaluation_model=runtime.puct.ctx,
                compute_configuration=runtime.puct.compute,
                provider_configuration=runtime.puct.provider_configuration,
                provenance={"agent": "test", "artifact": "fixture", "code": "abc",
                            "data": {}}, decision_seconds=0.1)
            assert record["decision"]["variant"] == "puct"
            assert record["configuration"]["provider"]["backend"] == backend.name
            assert record["search"]["puct"]["simulations"] == 4
            assert "reproduction_input" not in record["search"]["puct"]
            assert "search_begin_input" not in json.dumps(record)
            evidence = decision.decision_result.search.puct
            public_results.append((
                decision.chosen,
                tuple((candidate.prior, candidate.puct.visits,
                       candidate.puct.value_sum, candidate.puct.exclusion)
                      for candidate in decision.decision_result.roster.candidates),
                evidence.simulations, evidence.work,
                tuple((step.action, step.decision_key, step.chance_slot, step.probability)
                      for step in evidence.principal_variation),
                evidence.principal_variation_stop_reason,
            ))
        assert public_results[0] == public_results[1]
    finally:
        for runtime in runtimes:
            runtime.puct.close()
        battle_finish()


def test_agent_runtime_can_select_the_compat_backend_for_one_ply_ledger():
    from common.runtime import DecisionPilot, DecisionSearchConfiguration
    from cgpy.puct import ENGINE_BACKEND as CGPY_ENGINE_BACKEND

    deck = _deck()
    observation, start = battle_start(list(deck), list(deck))
    try:
        assert start.errorPlayer == -1
        observation = _first_main(observation)
        runtime = build_runtime(
            _strategy(), deck,
            decision_configuration=DecisionSearchConfiguration(
                DecisionPilot.LEDGER, CGPY_ENGINE_BACKEND))

        decision = runtime.decide(observation)

        assert runtime.ledger.provider_configuration["backend"] == "cgpy"
        assert decision.diagnostics["pilot"] == "ledger"
        assert decision.diagnostics["engine_backend"] == "cgpy"
        assert decision.chosen in tuple(
            action.selection for action in runtime.last_state.legal_actions)
    finally:
        battle_finish()


def test_native_puct_reuses_a_verified_deterministic_subtree_after_actual_action():
    from common.puct import NativeTurnSearchProvider
    from common.puct.workers import BoundedWorkers, WorkItem
    from common.decision.turn import NodeKind, ProviderCompletion

    deck = _deck()
    workers = BoundedWorkers(1, outstanding_limit=1)
    active = False
    try:
        selected = child = None
        task = 0
        for _attempt in range(20):
            observation, start = battle_start(list(deck), list(deck))
            active = True
            assert start.errorPlayer == -1
            observation = _first_main(observation)
            board = build_observation(observation, decklist=deck)
            previous = NativeTurnSearchProvider.from_observation(observation, board)
            for action in previous.legal_actions(previous.root):
                job = previous.work_item(previous.root, "transition", (action,))
                result = workers.run_batch(
                    (WorkItem(task, job.function, job.arguments),),
                    deadline=time.monotonic() + 20)[0]
                task += 1
                if (result.error_type is None and isinstance(result.value, ProviderCompletion)
                        and result.value.value.kind is NodeKind.PLAYER_DECISION):
                    selected, child = action, result.value.value
                    break
            if selected is not None:
                break
            battle_finish()
            active = False
        assert selected is not None and child is not None

        actual = battle_select(list(selected.selection))
        current = NativeTurnSearchProvider.from_observation(
            actual, advance_observation(board, actual))

        assert current.reuse_from(previous, child), (
            current.root.observation.decision_key, child.observation.decision_key,
            current.root.root_turn, child.root_turn,
            current.root.perspective_seat, child.perspective_seat,
            current.root.observation.knowledge == child.observation.knowledge)
        follow = current.legal_actions(child)[0]
        continuation = current.work_item(child, "transition", (follow,))
        result = workers.run_batch(
            (WorkItem(999, continuation.function, continuation.arguments,
                      continuation.affinity),),
            deadline=time.monotonic() + 20)[0]
        assert result.error_type is None and isinstance(result.value, ProviderCompletion)
        descendant = result.value.value
        assert (current._local_handle(descendant._handle).path
                == descendant._handle.path)
        if descendant.kind is NodeKind.PLAYER_DECISION:
            next_action = current.legal_actions(descendant)[0]
            next_job = current.work_item(descendant, "transition", (next_action,))
            next_result = workers.run_batch(
                (WorkItem(1000, next_job.function, next_job.arguments,
                          next_job.affinity),),
                deadline=time.monotonic() + 20)[0]
            assert next_result.error_type is None
    finally:
        workers.close()
        if active:
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


def test_production_runtime_completes_a_full_native_game_with_explicit_projection_gaps(monkeypatch):
    monkeypatch.setenv("AGENT_BRAIN_STRICT", "0")
    deck = _deck()
    observation, start = battle_start(list(deck), list(deck))
    runtimes = {
        seat: build_runtime(
            _strategy(), deck,
            provider_factory=partial(NativeCgTransitionProvider, world_count=1),
        )
        for seat in (0, 1)
    }
    own_cards = {seat: OwnCardModel(deck) for seat in (0, 1)}
    contexts = ExitStack()
    contexts.enter_context(episode_context("native-full-game"))
    records = contexts.enter_context(capture_records(suppress_output=True))
    coordinator_entries = {seat: 0 for seat in (0, 1)}
    for seat, runtime in runtimes.items():
        real = runtime.ledger.coordinator

        class RecordingCoordinator:
            def decide(self, *args, _seat=seat, _real=real, **kwargs):
                coordinator_entries[_seat] += 1
                return _real.decide(*args, **kwargs)

        runtime.ledger.coordinator = RecordingCoordinator()

    try:
        assert start.errorPlayer == -1
        for step in range(2000):
            current = observation.get("current") or {}
            result = current.get("result")
            if result is not None and result != -1:
                break
            assert observation.get("select") is not None, (step, observation)
            seat = int(current.get("yourIndex", 0))
            board = ObservationStateBuilder(deck).root(observation)
            own_cards[seat].observe(board)
            runtime = runtimes[seat]
            runtime.knowledge = reduce_knowledge(
                runtime.knowledge,
                own_prizes=tuple(sorted((own_cards[seat].prize_export() or {}).items())),
                known_top=own_cards[seat].known_top_export() or (),
            )
            before = coordinator_entries[seat]
            decision = runtime.decide(observation)
            emit(
                decision, opponent=runtime.opponent_snapshot, seat=seat,
                state=runtime.last_state, decision_seconds=0.0,
                session=runtime.telemetry_session,
                evaluation_model=runtime.ledger.ctx,
                compute_configuration=runtime.ledger.compute,
                provider_configuration=runtime.ledger.provider_configuration,
                provenance=runtime_provenance(deck_name="mega_starmie"),
            )
            turn = int(current.get("turn", 0))
            if turn <= 0:
                assert decision.diagnostics["backend"] == "declarative-pregame"
                assert coordinator_entries[seat] == before
            else:
                assert decision.diagnostics["backend"] == "ledger"
                if "failure" in decision.diagnostics:
                    candidates = decision.decision_result.roster.candidates
                    assert candidates and all(candidate.status.value == "unavailable" for candidate in candidates)
                    assert all(not candidate.successors for candidate in candidates)
                    assert any("observation unavailable" in gap or "private opponent selection" in gap
                               for candidate in candidates for gap in candidate.gaps)
                assert coordinator_entries[seat] == before + 1
            legal = {selection for action in enumerate_legal_actions(observation)
                     for selection in action.equivalent_selections}
            assert decision.chosen in legal, (step, decision, legal)
            observation = battle_select(list(decision.chosen))
        else:
            raise AssertionError("native game did not finish within 2000 decisions")

        assert (observation.get("current") or {}).get("result") in (0, 1, 2)
    finally:
        battle_finish()
        contexts.close()

    decisions = [record for record in records if record["record_type"] == "decision"]
    receipt = records.receipt("native-full-game")
    current = observation["current"]
    result = current["result"]
    winner = result if result in (0, 1) else None
    outcome = build_outcome_record(
        episode_key="native-full-game", decision_records=decisions,
        telemetry_receipt=receipt, winner=winner, terminal_reason="engine_win",
        public_prizes={seat: len(current["players"][seat]["prize"]) for seat in (0, 1)},
        rewards={seat: 0.0 if winner is None else 1.0 if winner == seat else -1.0
                 for seat in (0, 1)},
        duration_seconds=0.0,
    )
    assert receipt["certified"]
    assert receipt["decision_ids"] == [record["record_id"] for record in decisions]
    assert outcome["decision_ids"] == receipt["decision_ids"]


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
