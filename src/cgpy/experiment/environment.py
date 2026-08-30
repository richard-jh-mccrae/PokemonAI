"""Primitive, hidden-safe turn-search traversal over exact cgpy roots."""
from __future__ import annotations

from dataclasses import dataclass, replace

from common.api import ActionIdentity
from common.observation import ObservationState, ObservationStateBuilder

from .. import render
from ..engine import Engine
from ..execution import before_begin_turn
from ..rng import SeededRng
from ..schema import SelectContext
from .chance import ChanceSampleKey
from .contracts import (BoundaryReason, ChanceTransition, NodeKind, PrimitiveTransition,
                        SearchContractError, SearchNode, SearchStateKey)
from .snapshot import ExperimentSnapshot
from .state_key import search_state_key, unavailable_state_key


class _RandomBoundary(Exception):
    def __init__(self, kind: NodeKind, reason: BoundaryReason):
        self.kind = kind
        self.reason = reason


_RANDOM_METHODS = {
    "shuffle": (NodeKind.INFORMATION_BOUNDARY, BoundaryReason.SHUFFLE_DRAW),
    "draw_bind": (NodeKind.INFORMATION_BOUNDARY, BoundaryReason.SHUFFLE_DRAW),
    "prize_bind": (NodeKind.INFORMATION_BOUNDARY, BoundaryReason.SHUFFLE_DRAW),
    "coin": (NodeKind.CHANCE, BoundaryReason.RANDOM_REVEAL),
    "hand_pick": (NodeKind.INFORMATION_BOUNDARY, BoundaryReason.RANDOM_REVEAL),
    "look_bind": (NodeKind.INFORMATION_BOUNDARY, BoundaryReason.RANDOM_REVEAL),
    "mill_bind": (NodeKind.INFORMATION_BOUNDARY, BoundaryReason.RANDOM_REVEAL),
    "prize_take": (NodeKind.INFORMATION_BOUNDARY, BoundaryReason.RANDOM_REVEAL),
}


class _BoundaryProbeRng:
    def __init__(self, delegate, turn_changed, outcomes: tuple[bool, ...]):
        self.delegate = delegate
        self._turn_changed = turn_changed
        self._outcomes = outcomes
        self._outcome_index = 0

    def hand_pick_expect(self, *args, **kwargs):
        return self.delegate.hand_pick_expect(*args, **kwargs)

    def coin(self, *_args, **_kwargs) -> bool:
        if self._outcome_index >= len(self._outcomes):
            raise _RandomBoundary(NodeKind.CHANCE, BoundaryReason.RANDOM_REVEAL)
        outcome = self._outcomes[self._outcome_index]
        self._outcome_index += 1
        return outcome

    def __getattr__(self, name):
        kind, reason = _RANDOM_METHODS.get(name, (
            NodeKind.INFORMATION_BOUNDARY,
            BoundaryReason.UNSUPPORTED_HIDDEN_TRANSITION,
        ))

        def stop(*_args, **_kwargs):
            if self._turn_changed():
                raise _RandomBoundary(
                    NodeKind.TURN_BOUNDARY, BoundaryReason.TURN_TRANSITION)
            raise _RandomBoundary(kind, reason)

        return stop


@dataclass(slots=True)
class _ReplayPlan:
    source: Engine
    selection: tuple[int, ...]
    action: ActionIdentity
    outcomes: tuple[bool, ...]


@dataclass(slots=True)
class _NodeState:
    engine: Engine
    replay_plan: _ReplayPlan | None = None


def _stop_before_turn(_gs, _seat) -> None:
    raise _RandomBoundary(NodeKind.TURN_BOUNDARY, BoundaryReason.TURN_TRANSITION)


def _decklist(engine: Engine, seat: int) -> tuple[int, ...]:
    cards = sorted(engine.gs.cards.values(), key=lambda card: card.serial)
    return tuple(card.card_id for card in cards if card.owner == seat)


def _observation(engine: Engine, seat: int, *, include_select: bool) -> ObservationState:
    gs = engine.gs
    printout = {
        "select": render.select_dict(gs) if include_select else None,
        "logs": [dict(entry) for entry in gs.outbox[seat]],
        "current": render.current_dict(gs, seat),
        "search_begin_input": None,
    }
    observation = ObservationStateBuilder(_decklist(engine, seat)).root(printout)
    return observation if include_select else replace(observation, legal_actions=())


def _classification(engine: Engine, perspective_seat: int,
                    root_turn: int) -> tuple[NodeKind, int | None,
                                             BoundaryReason | None]:
    gs = engine.gs
    pending = gs.pending
    if gs.result != -1:
        return NodeKind.TERMINAL, None, None
    if pending is None:
        return NodeKind.UNAVAILABLE, None, None
    if pending.context == int(SelectContext.COIN_HEAD):
        return NodeKind.CHANCE, None, BoundaryReason.RANDOM_REVEAL
    if gs.turn != root_turn:
        return NodeKind.TURN_BOUNDARY, None, BoundaryReason.TURN_TRANSITION
    if pending.seat != perspective_seat:
        return NodeKind.INFORMATION_BOUNDARY, None, BoundaryReason.OPPONENT_DECISION
    if pending.context == int(SelectContext.MAIN):
        return NodeKind.PLAYER_DECISION, pending.seat, None
    return NodeKind.FORCED_DECISION, pending.seat, None


class TurnSearchEnvironment:
    def __init__(self, engine: Engine, *, perspective_seat: int):
        if perspective_seat not in (0, 1):
            raise ValueError("Perspective Seat must be 0 or 1")
        if not isinstance(engine.gs.rng, SeededRng):
            raise ValueError("Turn Search Environment requires SeededRng")
        self.perspective_seat = int(perspective_seat)
        self._states: dict[object, _NodeState] = {}
        root_engine = engine.fork()
        self._root_turn = root_engine.gs.turn
        self._root = self._make_node(root_engine)

    @classmethod
    def from_snapshot(cls, snapshot: ExperimentSnapshot, *,
                      perspective_seat: int | None = None) -> "TurnSearchEnvironment":
        seat = snapshot.observation.seat if perspective_seat is None else perspective_seat
        return cls(snapshot.fork_engine(), perspective_seat=seat)

    @classmethod
    def from_engine(cls, engine: Engine, *,
                    perspective_seat: int) -> "TurnSearchEnvironment":
        return cls(engine, perspective_seat=perspective_seat)

    @property
    def root(self) -> SearchNode:
        return self._root

    def _node_state(self, node: SearchNode) -> _NodeState:
        if not isinstance(node, SearchNode) or node._handle not in self._states:
            raise ValueError("Search Node belongs to another Turn Search Environment")
        return self._states[node._handle]

    def _register(self, engine: Engine, kind: NodeKind, actor: int | None,
                  reason: BoundaryReason | None, observation: ObservationState,
                  key: SearchStateKey, *, failure: str | None = None,
                  replay_plan: _ReplayPlan | None = None) -> SearchNode:
        handle = object()
        self._states[handle] = _NodeState(engine, replay_plan)
        return SearchNode(
            kind, actor, self.perspective_seat, observation, key, self._root_turn,
            reason, failure, handle)

    def _make_node(self, engine: Engine) -> SearchNode:
        kind, actor, reason = _classification(
            engine, self.perspective_seat, self._root_turn)
        observation = _observation(
            engine, self.perspective_seat,
            include_select=kind not in (
                NodeKind.INFORMATION_BOUNDARY, NodeKind.TURN_BOUNDARY))
        key = search_state_key(
            engine, kind, actor, self.perspective_seat, self._root_turn, reason)
        return self._register(engine, kind, actor, reason, observation, key)

    def _boundary_node(self, engine: Engine, kind: NodeKind,
                       reason: BoundaryReason, *,
                       replay_plan: _ReplayPlan | None = None) -> SearchNode:
        observation = _observation(engine, self.perspective_seat, include_select=False)
        continuation = None
        if replay_plan is not None:
            continuation = (
                replay_plan.action.kind, replay_plan.action.parts,
                len(replay_plan.outcomes))
        key = search_state_key(
            engine, kind, None, self.perspective_seat, self._root_turn, reason,
            continuation=continuation)
        return self._register(
            engine, kind, None, reason, observation, key, replay_plan=replay_plan)

    def _unavailable_node(self, parent: SearchNode, engine: Engine,
                          action: ActionIdentity, exc: Exception) -> SearchNode:
        failure = f"{type(exc).__name__}: {exc}"
        observation = _observation(engine, self.perspective_seat, include_select=False)
        key = unavailable_state_key(parent.state_key, action, type(exc).__name__)
        return self._register(
            engine, NodeKind.UNAVAILABLE, None, None, observation, key, failure=failure)

    def fork(self, node: SearchNode) -> SearchNode:
        state = self._node_state(node)
        return self._register(
            state.engine.fork(), node.kind, node.actor_seat, node.boundary_reason,
            node.observation, node.state_key, failure=node.failure,
            replay_plan=state.replay_plan)

    def _run_plan(self, parent: SearchNode, plan: _ReplayPlan) -> SearchNode:
        child_engine = plan.source.fork()
        probe = _BoundaryProbeRng(
            child_engine.gs.rng,
            lambda: child_engine.gs.turn != self._root_turn,
            plan.outcomes)
        child_engine.gs.rng = probe
        hook_token = before_begin_turn.set(_stop_before_turn)
        try:
            child_engine.step(list(plan.selection))
        except _RandomBoundary as boundary:
            replay_plan = plan if boundary.kind is NodeKind.CHANCE else None
            child = self._boundary_node(
                child_engine, boundary.kind, boundary.reason,
                replay_plan=replay_plan)
        except Exception as exc:
            child = self._unavailable_node(parent, child_engine, plan.action, exc)
        else:
            child = self._make_node(child_engine)
        finally:
            child_engine.gs.rng = probe.delegate
            before_begin_turn.reset(hook_token)
        return child

    def transition(self, node: SearchNode,
                   action: ActionIdentity) -> PrimitiveTransition:
        state = self._node_state(node)
        if node.kind not in (NodeKind.PLAYER_DECISION, NodeKind.FORCED_DECISION):
            raise SearchContractError(f"cannot transition a {node.kind.value} Search Node")
        if not isinstance(action, ActionIdentity):
            raise TypeError("Primitive Action must be an ActionIdentity")
        matching = tuple(candidate for candidate in self.legal_actions(node)
                         if candidate.identity == action)
        if len(matching) != 1:
            detail = "missing" if not matching else "ambiguous"
            raise SearchContractError(f"Primitive Action identity is {detail}")
        child = self._run_plan(node, _ReplayPlan(
            state.engine, tuple(matching[0].selection), action, ()))
        return PrimitiveTransition(
            node.state_key, action, child.state_key, child.kind,
            child.boundary_reason, child.failure, child)

    def replay(self, node: SearchNode,
               recorded: PrimitiveTransition) -> PrimitiveTransition:
        self._assert_replay(node, recorded, PrimitiveTransition, "Primitive Transition")
        replayed = self.transition(node, recorded.action)
        if replayed != recorded:
            raise SearchContractError("Primitive Transition replay diverged")
        return replayed

    def sample(self, node: SearchNode, sample: ChanceSampleKey) -> ChanceTransition:
        state = self._node_state(node)
        if node.kind is not NodeKind.CHANCE:
            raise SearchContractError(f"cannot sample a {node.kind.value} Search Node")
        if not isinstance(sample, ChanceSampleKey):
            raise TypeError("sample requires a Chance Sample Key")
        if sample.root_state_key != self.root.state_key.digest:
            raise SearchContractError("Chance Sample root key does not match")
        if sample.node_state_key != node.state_key.digest:
            raise SearchContractError("Chance Sample node key does not match")
        if (state.replay_plan is not None
                and sample.action != state.replay_plan.action):
            raise SearchContractError("Chance Sample action does not match")
        head = SeededRng(sample.seed).coin()
        outcome = ActionIdentity("coin", (("head", head),))
        if state.replay_plan is not None:
            plan = replace(
                state.replay_plan,
                outcomes=state.replay_plan.outcomes + (head,))
        else:
            matching = tuple(
                action for action in node.observation.legal_actions
                if action.identity.kind == ("yes" if head else "no"))
            if len(matching) != 1:
                raise SearchContractError("Chance Node has no canonical coin outcomes")
            outcome = matching[0].identity
            plan = _ReplayPlan(
                state.engine, tuple(matching[0].selection), outcome, ())
        child = self._run_plan(node, plan)
        return ChanceTransition(
            node.state_key, sample, outcome, child.state_key, child.kind,
            child.boundary_reason, child.failure, child)

    def replay_chance(self, node: SearchNode,
                      recorded: ChanceTransition) -> ChanceTransition:
        self._assert_replay(node, recorded, ChanceTransition, "Chance Transition")
        replayed = self.sample(node, recorded.sample)
        if replayed != recorded:
            raise SearchContractError("Chance Transition replay diverged")
        return replayed

    def _assert_replay(self, node: SearchNode, recorded, expected, label: str) -> None:
        self._node_state(node)
        if not isinstance(recorded, expected):
            raise TypeError(f"replay requires a {label}")
        if recorded.schema_version != 1:
            raise SearchContractError(f"{label} schema is unsupported")
        if recorded.parent_state_key != node.state_key:
            raise SearchContractError(f"{label} parent key does not match")

    def legal_actions(self, node: SearchNode) -> tuple:
        self._node_state(node)
        if node.kind not in (NodeKind.PLAYER_DECISION, NodeKind.FORCED_DECISION):
            return ()
        return node.observation.legal_actions

    def observation(self, node: SearchNode) -> ObservationState:
        self._node_state(node)
        return node.observation

    def actor(self, node: SearchNode) -> int | None:
        self._node_state(node)
        return node.actor_seat

    def node_kind(self, node: SearchNode) -> NodeKind:
        self._node_state(node)
        return node.kind

    def is_terminal(self, node: SearchNode) -> bool:
        return self.node_kind(node) is NodeKind.TERMINAL

    def is_turn_boundary(self, node: SearchNode) -> bool:
        return self.node_kind(node) is NodeKind.TURN_BOUNDARY

    def is_information_boundary(self, node: SearchNode) -> bool:
        return self.node_kind(node) is NodeKind.INFORMATION_BOUNDARY

    def state_key(self, node: SearchNode) -> SearchStateKey:
        self._node_state(node)
        return node.state_key


__all__ = ("TurnSearchEnvironment",)
