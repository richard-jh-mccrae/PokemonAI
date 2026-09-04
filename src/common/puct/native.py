"""Bounded replay adapter between native search and the shared current-turn contract."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from common.algebra import Chance, Deterministic, Refresh, Terminal, Unknown
from common.api import ActionIdentity
from common.decision.turn import (BoundaryReason, ChancePlan, NodeKind, ProviderCompletion,
                                  ProviderJob, SearchContractError, SearchNode, SearchStateKey,
                                  TurnAction)
from common.ledger.decision import evaluator_semantics_identity
from common.ledger.seam import LedgerNativeProvider
from common.observation.provider import ProviderState, provider_payload
from common.observation import KnownOwnPrizes, ObservationState
from common.strategy.context import _MAIN


@dataclass(frozen=True, slots=True)
class _ReplayStep:
    action: ActionIdentity
    selection: tuple[int, ...]
    branch: int | None = None
    realized_refresh: bool = False
    sample_slot: int | None = None


@dataclass(frozen=True, slots=True)
class _StateHandle:
    path: tuple[_ReplayStep, ...]
    state: ProviderState
    hidden_order_token: str | None = None
    affinity: str | None = None
    path_origin: str = ""


@dataclass(frozen=True, slots=True)
class _EngineChanceHandle:
    path: tuple[_ReplayStep, ...]
    state: ProviderState
    action: TurnAction
    outcomes: tuple[tuple[float, ProviderState], ...]
    hidden_order_token: str | None = None
    affinity: str | None = None
    path_origin: str = ""


@dataclass(frozen=True, slots=True)
class _RefreshHandle:
    path: tuple[_ReplayStep, ...]
    state: ProviderState
    action: TurnAction
    refresh: Refresh
    hidden_order_token: str | None = None
    affinity: str | None = None
    path_origin: str = ""


_NATIVE_SESSIONS: dict[str, LedgerNativeProvider] = {}
_NATIVE_SAMPLE_RESULTS: dict[str, SearchNode] = {}


class _CountingApi:
    def __init__(self, target):
        self.target = target
        self.begins = 0
        self.steps = 0

    def __getattr__(self, name):
        return getattr(self.target, name)

    def search_begin(self, *args, **kwargs):
        self.begins += 1
        return self.target.search_begin(*args, **kwargs)

    def search_step(self, *args, **kwargs):
        self.steps += 1
        return self.target.search_step(*args, **kwargs)


def _api_counts(provider) -> tuple[int, int]:
    api = getattr(provider, "_api", None)
    return int(getattr(api, "begins", 0)), int(getattr(api, "steps", 0))


def _digest(*parts) -> str:
    return hashlib.sha256(repr(parts).encode("utf-8")).hexdigest()


def _classify(state: ProviderState, root_turn: int) -> tuple[NodeKind, int | None, BoundaryReason | None]:
    observation = state.observation
    if observation.turn.result in (0, 1, 2):
        return NodeKind.TERMINAL, None, None
    if observation.turn.number != root_turn:
        return NodeKind.TURN_BOUNDARY, None, BoundaryReason.TURN_TRANSITION
    if state.actor_seat != observation.seat:
        return NodeKind.INFORMATION_BOUNDARY, None, BoundaryReason.OPPONENT_DECISION
    raw = provider_payload(state)
    select = raw.get("select") or {}
    if not select:
        return NodeKind.UNAVAILABLE, None, None
    kind = NodeKind.PLAYER_DECISION if int(select.get("context", -1)) == _MAIN else NodeKind.FORCED_DECISION
    return kind, state.actor_seat, None


def _node(handle, root_turn: int, origin: str, *, kind=None, reason=None) -> SearchNode:
    state = handle.state
    if kind is None:
        kind, actor, reason = _classify(state, root_turn)
    else:
        actor = None
    key = SearchStateKey(_digest(origin, handle.path, state.observation.decision_key, kind, reason))
    return SearchNode(kind, actor, state.observation.seat, state.observation, key,
                      root_turn, reason, None, handle)


def _result_state(result):
    if isinstance(result, (Deterministic, Terminal)):
        return result.state
    raise SearchContractError(f"native replay produced {type(result).__name__} where a state was required")


def _pick_action(provider, state, requested, selection=None):
    identity = getattr(requested, "identity", requested)
    selection = getattr(requested, "selection", selection)
    matches = tuple(
        action for action in provider.actions(state)
        if action.identity == identity
        and (selection is None or tuple(action.selection) == tuple(selection)))
    if len(matches) != 1:
        raise SearchContractError("native replay action identity is missing or ambiguous")
    return matches[0]


def _resolve_action(actions, requested):
    identity = getattr(requested, "identity", requested)
    selection = getattr(requested, "selection", None)
    matches = tuple(
        action for action in actions
        if action.identity == identity
        and (selection is None or tuple(action.selection) == tuple(selection)))
    if len(matches) != 1:
        raise SearchContractError("native action identity is missing or ambiguous")
    return matches[0]


def _advance(provider, state, step: _ReplayStep):
    previous = provider.analytic_refresh
    if step.realized_refresh:
        provider.analytic_refresh = False
    try:
        result = provider.transition(
            state, _pick_action(provider, state, step.action, step.selection))
    finally:
        provider.analytic_refresh = previous
    if step.branch is None:
        return _result_state(result)
    if not isinstance(result, Chance) or not 0 <= step.branch < len(result.children):
        raise SearchContractError("native replay chance branch diverged")
    return _result_state(result.children[step.branch].node)


def _native_transition_job(root, handle, action, root_turn, origin, affinity):
    from cg import api

    counted = _CountingApi(api)
    owned = affinity in _NATIVE_SESSIONS
    provider = (_NATIVE_SESSIONS[affinity] if owned else LedgerNativeProvider(
        root, api_module=counted, analytic_refresh=True,
        hidden_order_token=handle.hidden_order_token))
    try:
        _before_begins, before_steps = _api_counts(provider)
        before_states = provider.retained_states
        state = handle.state if owned else root
        if not owned:
            for step in handle.path:
                state = _advance(provider, state, step)
        result = provider.transition(state, _pick_action(provider, state, action))
        child_handle: _RefreshHandle | _EngineChanceHandle | _StateHandle
        if isinstance(result, Refresh):
            child_handle = _RefreshHandle(
                handle.path, state, action, result, handle.hidden_order_token,
                affinity, handle.path_origin)
            child = _node(child_handle, root_turn, origin, kind=NodeKind.CHANCE,
                          reason=BoundaryReason.SHUFFLE_DRAW)
        elif isinstance(result, Chance):
            outcomes = tuple((edge.probability, _result_state(edge.node)) for edge in result.children)
            child_handle = _EngineChanceHandle(
                handle.path, state, action, outcomes, handle.hidden_order_token,
                affinity, handle.path_origin)
            child = _node(child_handle, root_turn, origin, kind=NodeKind.CHANCE,
                          reason=BoundaryReason.RANDOM_REVEAL)
        elif isinstance(result, Unknown):
            raise SearchContractError(f"{result.reason}: {result.missing_fact}")
        else:
            child_state = _result_state(result)
            child_handle = _StateHandle(
                handle.path + (_ReplayStep(action.identity, tuple(action.selection)),), child_state,
                handle.hidden_order_token, affinity, handle.path_origin)
            child = _node(child_handle, root_turn, origin)
        _NATIVE_SESSIONS[affinity] = provider
        _after_begins, after_steps = _api_counts(provider)
        used = max(1, after_steps - before_steps)
        states = max(0, (provider.retained_states - before_states
                         if owned else provider.retained_states))
        return ProviderCompletion(
            child, used, states,
            provider.retained_states)
    except Exception:
        if not owned:
            provider.close()
        raise


def _sample_engine_chance(handle, slot, root_turn, origin):
    probability, state = handle.outcomes[slot]
    child_handle = _StateHandle(
        handle.path + (_ReplayStep(handle.action.identity, tuple(handle.action.selection), slot),), state,
        handle.hidden_order_token, handle.affinity, handle.path_origin)
    provider = _NATIVE_SESSIONS.get(handle.affinity)
    retained = None if provider is None else provider.retained_states
    return ProviderCompletion(_node(child_handle, root_turn, origin), 1, 0, retained)


def _sample_refresh(root, handle, seed, slot, root_turn, origin, affinity, sample_key):
    from cg import api

    if sample_key in _NATIVE_SAMPLE_RESULTS:
        provider = _NATIVE_SESSIONS.get(affinity)
        retained = None if provider is None else provider.retained_states
        return ProviderCompletion(_NATIVE_SAMPLE_RESULTS[sample_key], 0, 0, retained)
    counted = _CountingApi(api)
    token = handle.hidden_order_token or sample_key
    owned = affinity in _NATIVE_SESSIONS
    provider = (_NATIVE_SESSIONS[affinity] if owned else LedgerNativeProvider(
        root, api_module=counted, analytic_refresh=True,
        hidden_order_token=token))
    try:
        _before_begins, before_steps = _api_counts(provider)
        before_states = provider.retained_states
        state = handle.state if owned else root
        if not owned:
            for step in handle.path:
                state = _advance(provider, state, step)
        previous = provider.analytic_refresh
        provider.analytic_refresh = False
        try:
            result = provider.transition(state, _pick_action(provider, state, handle.action))
        finally:
            provider.analytic_refresh = previous
        branch = None
        if isinstance(result, Chance):
            branch = slot % len(result.children)
            child_state = _result_state(result.children[branch].node)
        else:
            child_state = _result_state(result)
        child_handle = _StateHandle(
            handle.path + (_ReplayStep(
                handle.action.identity, tuple(handle.action.selection), branch, True, slot),),
            child_state, token, affinity, handle.path_origin)
        _NATIVE_SESSIONS[affinity] = provider
        _after_begins, after_steps = _api_counts(provider)
        used = max(1, after_steps - before_steps)
        states = max(0, (provider.retained_states - before_states
                         if owned else provider.retained_states))
        child = _node(child_handle, root_turn, origin)
        _NATIVE_SAMPLE_RESULTS[sample_key] = child
        return ProviderCompletion(
            child, used, states,
            provider.retained_states)
    except Exception:
        if not owned:
            provider.close()
        raise


class NativeTurnSearchProvider:
    identity = "native-bounded-replay-v1:" + evaluator_semantics_identity((
        Path(__file__), Path(__file__).parents[1] / "native_engine.py",
        Path(__file__).parents[1] / "ledger" / "chance.py",
        Path(__file__).parents[1] / "ledger" / "seam.py"))

    def __init__(self, root: ProviderState):
        if not isinstance(root, ProviderState):
            raise TypeError("native turn search requires a ProviderState root")
        self._source = root
        self._root_turn = root.observation.turn.number
        self._origin = _digest(
            root.observation.decision_key, root.observation.position_key,
            self._root_turn, root.observation.seat)
        self.root = _node(
            _StateHandle((), root, path_origin=self._origin),
            self._root_turn, self._origin)
        self._rebase_prefix: tuple[_ReplayStep, ...] = ()
        self._retained_by_affinity: dict[str, int] = {}
        self._peak_retained_states = 0

    @classmethod
    def from_observation(cls, payload: dict, observation: ObservationState):
        prizes = (observation.knowledge.own_prizes.cards
                  if isinstance(observation.knowledge.own_prizes, KnownOwnPrizes) else ())
        root = ProviderState(
            payload, observation, token=observation.decision_key,
            deck=observation.decklist or (), deck_counts=observation.deck_counts or (),
            prize_counts=prizes)
        return cls(root)

    @property
    def retained_states(self) -> int:
        return sum(self._retained_by_affinity.values())

    @property
    def peak_retained_states(self) -> int:
        return self._peak_retained_states

    def close(self) -> None:
        pass

    def release_worker_states(self) -> int:
        released = self.retained_states
        self._retained_by_affinity.clear()
        return released

    def reproduction_input(self) -> str:
        return json.dumps({
            "schema": "native-puct-replay-input", "schema_version": 1,
            "payload": provider_payload(self._source),
            "deck": list(self._source.deck),
            "deck_counts": [list(item) for item in self._source.deck_counts],
            "prize_counts": [list(item) for item in self._source.prize_counts],
        }, sort_keys=True, separators=(",", ":"))

    def _local_handle(self, handle):
        if handle.path_origin == self._origin:
            return handle
        prefix = self._rebase_prefix
        if tuple(handle.path[:len(prefix)]) != prefix:
            raise SearchContractError("retained native node does not share the verified reroot path")
        path = tuple(handle.path[len(prefix):])
        if isinstance(handle, _StateHandle):
            return _StateHandle(path, handle.state, path_origin=self._origin)
        if isinstance(handle, _RefreshHandle):
            return _RefreshHandle(
                path, handle.state, handle.action, handle.refresh,
                handle.hidden_order_token, path_origin=self._origin)
        if isinstance(handle, _EngineChanceHandle):
            return _EngineChanceHandle(
                path, handle.state, handle.action, handle.outcomes,
                handle.hidden_order_token, path_origin=self._origin)
        raise SearchContractError("unknown native replay handle")

    def legal_actions(self, node):
        return node.observation.legal_actions

    def ledger_state(self, node):
        return node._handle.state

    def chance_plan(self, node, sample_count):
        handle = node._handle
        if isinstance(handle, _RefreshHandle):
            probabilities = (1.0 / sample_count,) * sample_count
            method, estimated = "bounded_shuffle_draw", True
        elif isinstance(handle, _EngineChanceHandle):
            probabilities = tuple(probability for probability, _state in handle.outcomes)
            method, estimated = "native_exact", False
        else:
            raise SearchContractError("native chance node has no chance descriptor")
        identity = _digest(node.observation.decision_key, handle.action, method)
        return ChancePlan(identity, method, probabilities, estimated)

    def work_item(self, node, operation, arguments):
        handle = self._local_handle(node._handle)
        if operation == "transition" and isinstance(handle, _StateHandle):
            action = _resolve_action(self.legal_actions(node), arguments[0])
            affinity = handle.affinity or _digest(
                self._origin, handle.path, action.identity, tuple(action.selection),
                "native-session")
            capacity = max(1, 3 * (len(handle.path) + 1))
            return ProviderJob(
                _native_transition_job,
                (self._source, handle, action, self._root_turn, self._origin, affinity),
                capacity + 1, capacity, affinity)
        if operation == "sample_for_search" and isinstance(handle, _EngineChanceHandle):
            return ProviderJob(_sample_engine_chance,
                               (handle, arguments[1], self._root_turn, self._origin), 0,
                               affinity=handle.affinity)
        if operation == "sample_for_search" and isinstance(handle, _RefreshHandle):
            sample_key = _digest(
                self._origin, handle.path, arguments[0], arguments[1])
            affinity = handle.affinity or sample_key
            return ProviderJob(_sample_refresh,
                               (self._source, handle, arguments[0], arguments[1],
                                self._root_turn, self._origin, affinity, sample_key),
                               max(1, 3 * (len(handle.path) + 1)),
                               max(1, 3 * (len(handle.path) + 1)) + 1,
                               affinity)
        raise SearchContractError("native replay operation does not match its node")

    @staticmethod
    def accept_work(result):
        return result

    def observe_completion(self, completion, affinity=None):
        if completion.retained_states is not None and affinity is not None:
            self._retained_by_affinity[affinity] = completion.retained_states
            self._peak_retained_states = max(
                self._peak_retained_states, self.retained_states)

    def reuse_from(self, previous, node):
        if not isinstance(previous, NativeTurnSearchProvider):
            return False
        handle = node._handle
        if not isinstance(handle, _StateHandle):
            return False
        if any(step.branch is not None or step.realized_refresh for step in handle.path):
            return False
        if (node.observation.decision_key != self.root.observation.decision_key
                or node.observation.knowledge != self.root.observation.knowledge
                or tuple((action.identity, tuple(action.selection))
                         for action in node.observation.legal_actions)
                != tuple((action.identity, tuple(action.selection))
                         for action in self.root.observation.legal_actions)
                or node.perspective_seat != self.root.perspective_seat
                or node.root_turn != self.root.root_turn):
            return False
        if not provider_payload(self._source).get("search_begin_input"):
            return False
        self._rebase_prefix = handle.path
        return True


__all__ = ("NativeTurnSearchProvider",)
