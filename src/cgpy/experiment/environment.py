"""Hidden-safe deterministic and chance traversal over exact cgpy roots."""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
from itertools import permutations
from math import perm

from common.api import ActionIdentity
from common.decision.turn import ChancePlan, ProviderCompletion, ProviderJob
from copy import copy
from common.observation.provider import ProviderState
from common.observation import (KnownDeckTop, KnownOwnPrizes, LegalKnowledge,
                                ObservationState, ObservationStateBuilder,
                                UnknownDeckTop)

from .. import render
from ..engine import Engine
from ..execution import after_begin_turn
from ..rng import SeededRng
from ..schema import SelectContext
from .chance import (ChanceBranchKey, ChanceBranchKind, ChanceInformationKey,
                     ChanceSampleKey)
from .contracts import (BoundaryReason, ChanceExpansion, ChanceExpansionRequest,
                        ChanceExpansionStatus, ChanceSuccessor, ChanceTransition,
                        NodeKind, PrimitiveTransition, SearchContractError,
                        SearchNode, SearchStateKey)
from .snapshot import ExperimentSnapshot
from .state_key import (search_state_key, turn_boundary_state_key,
                        unavailable_state_key)


@dataclass(frozen=True, slots=True)
class _ChanceEvent:
    method: str
    seat: int | None
    values: tuple[int, ...] = ()
    count: int = 0
    from_bottom: bool = False
    prefix: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class _ExactChoice:
    method: str
    payload: object
    probability: float


class _RandomBoundary(Exception):
    def __init__(self, kind: NodeKind, reason: BoundaryReason,
                 event: _ChanceEvent):
        self.kind = kind
        self.reason = reason
        self.event = event

    @property
    def method(self) -> str:
        return self.event.method


_RANDOM_METHODS = {
    "draw_bind": (NodeKind.CHANCE, BoundaryReason.SHUFFLE_DRAW),
    "prize_bind": (NodeKind.CHANCE, BoundaryReason.SHUFFLE_DRAW),
    "coin": (NodeKind.CHANCE, BoundaryReason.RANDOM_REVEAL),
    "hand_pick": (NodeKind.CHANCE, BoundaryReason.RANDOM_REVEAL),
    "look_bind": (NodeKind.CHANCE, BoundaryReason.RANDOM_REVEAL),
    "mill_bind": (NodeKind.CHANCE, BoundaryReason.RANDOM_REVEAL),
    "prize_take": (NodeKind.CHANCE, BoundaryReason.RANDOM_REVEAL),
}


def _chance_event(method: str, args: tuple, kwargs: dict) -> _ChanceEvent:
    if method == "coin":
        seat = args[0] if args else kwargs.get("seat")
        return _ChanceEvent(method, None if seat is None else int(seat))
    if method in ("draw_bind", "hand_pick"):
        return _ChanceEvent(method, int(args[0]), tuple(args[1]), 1)
    if method == "prize_bind":
        return _ChanceEvent(method, int(args[0]), tuple(args[1]), int(args[2]))
    if method == "look_bind":
        return _ChanceEvent(
            method, int(args[0]), tuple(args[1]), int(args[2]),
            bool(kwargs.get("from_bottom", False)))
    if method == "mill_bind":
        return _ChanceEvent(method, int(args[0]), tuple(args[1]), int(args[3]))
    if method == "prize_take":
        return _ChanceEvent(method, int(args[0]), tuple(kwargs["prize"]), 1)
    return _ChanceEvent(method, None)


def _consume_known_top(known_top: list[tuple[int, int]], values) -> None:
    for serial in values:
        if not known_top:
            return
        if serial != known_top[0][0]:
            known_top.clear()
            return
        known_top.pop(0)


class _BoundaryProbeRng:
    def __init__(self, delegate, turn_changed, outcomes: tuple[bool, ...], *,
                 perspective_seat: int, knowledge: LegalKnowledge, game_state):
        self.delegate = delegate
        self._turn_changed = turn_changed
        self._outcomes = outcomes
        self._outcome_index = 0
        self._perspective_seat = perspective_seat
        self._knowledge = knowledge
        self._game_state = game_state
        self._known_top = list(
            knowledge.known_top.cards
            if isinstance(knowledge.known_top, KnownDeckTop) else ())

    @property
    def knowledge(self) -> LegalKnowledge:
        known_top = (KnownDeckTop(tuple(self._known_top))
                     if self._known_top else UnknownDeckTop())
        return replace(self._knowledge, known_top=known_top)

    def shuffle(self, seq: list, *, seat: int) -> None:
        seq.sort(key=lambda serial: (self._game_state.card_id(serial), serial))
        if seat == self._perspective_seat:
            self._known_top.clear()

    def hand_pick_expect(self, *args, **kwargs):
        return self.delegate.hand_pick_expect(*args, **kwargs)

    def coin(self, *_args, **_kwargs) -> bool:
        if self._outcome_index >= len(self._outcomes):
            raise _RandomBoundary(
                NodeKind.CHANCE, BoundaryReason.RANDOM_REVEAL,
                _chance_event("coin", _args, _kwargs))
        outcome = self._outcomes[self._outcome_index]
        self._outcome_index += 1
        return outcome

    def __getattr__(self, name):
        kind, reason = _RANDOM_METHODS.get(name, (
            NodeKind.INFORMATION_BOUNDARY,
            BoundaryReason.UNSUPPORTED_HIDDEN_TRANSITION,
        ))

        def stop(*_args, **_kwargs):
            event = _chance_event(name, _args, _kwargs)
            if self._turn_changed():
                return getattr(self.delegate, name)(*_args, **_kwargs)
            raise _RandomBoundary(kind, reason, event)

        return stop


class _SegmentRng:
    def __init__(self, seed: int, outcomes: tuple[bool, ...] = (), *,
                 perspective_seat: int, knowledge: LegalKnowledge,
                 game_state):
        self.delegate = SeededRng(seed)
        self._outcomes = outcomes
        self._outcome_index = 0
        self._shuffled: set[int] = set()
        self._perspective_seat = perspective_seat
        self._knowledge = knowledge
        self._game_state = game_state
        self._known_top = list(
            knowledge.known_top.cards
            if isinstance(knowledge.known_top, KnownDeckTop) else ())

    @property
    def knowledge(self) -> LegalKnowledge:
        known_top = (KnownDeckTop(tuple(self._known_top))
                     if self._known_top else UnknownDeckTop())
        return replace(self._knowledge, known_top=known_top)

    def _sample(self, values, count: int, *, seat: int) -> list[int]:
        candidates = sorted(
            values, key=lambda serial: (self._game_state.card_id(serial), serial))
        self.delegate.shuffle(candidates, seat=seat)
        return candidates[:min(max(0, count), len(candidates))]

    def _stop_hidden(self, method: str, args: tuple, kwargs: dict) -> None:
        raise _RandomBoundary(
            NodeKind.INFORMATION_BOUNDARY,
            BoundaryReason.UNSUPPORTED_HIDDEN_TRANSITION,
            _chance_event(method, args, kwargs))

    def _sample_deck_pool(
            self, seat: int, deck: list[int], count: int, *, exclude=()) -> list[int]:
        excluded = set(exclude)
        if seat == self._perspective_seat:
            excluded.update(serial for serial, _card_id in self._known_top)
        if (seat == self._perspective_seat
                and isinstance(self._knowledge.own_prizes, KnownOwnPrizes)):
            return self._sample(
                [serial for serial in deck if serial not in excluded], count,
                seat=seat)
        board = self._game_state.players[seat]
        hidden_zones = (board.prize,) if seat == self._perspective_seat else (
            board.hand, board.prize)
        pool = (deck, *hidden_zones)
        selected = self._sample(
            [serial for zone in pool for serial in zone
             if serial not in excluded],
            count, seat=seat)
        selected_set = set(selected)
        fillers = iter(serial for serial in sorted(
            deck, key=lambda serial: (self._game_state.card_id(serial), serial))
                       if serial not in selected_set and serial not in excluded)
        for serial in selected:
            if serial in deck:
                continue
            filler = next(fillers)
            deck[deck.index(filler)] = serial
            source = next(zone for zone in hidden_zones if serial in zone)
            source[source.index(serial)] = filler
        return selected

    def _pin_known_top(self, deck: list[int]) -> list[int]:
        serials = [serial for serial, _card_id in self._known_top]
        if not serials:
            return []
        prize = self._game_state.players[self._perspective_seat].prize
        reserved = set(serials)
        fillers = iter(serial for serial in sorted(
            deck, key=lambda value: (self._game_state.card_id(value), value))
                       if serial not in reserved)
        for serial in serials:
            if serial in deck:
                continue
            if (isinstance(self._knowledge.own_prizes, KnownOwnPrizes)
                    or serial not in prize):
                raise SearchContractError(
                    "Known Deck Top disagrees with the exact search fork")
            filler = next(fillers)
            deck[deck.index(filler)] = serial
            prize[prize.index(serial)] = filler
        return serials

    def shuffle(self, seq: list, *, seat: int) -> None:
        seq.sort(key=lambda serial: (self._game_state.card_id(serial), serial))
        self.delegate.shuffle(seq, seat=seat)
        if (seat == self._perspective_seat
                and isinstance(self._knowledge.own_prizes, KnownOwnPrizes)):
            self._shuffled.add(id(seq))
        if seat == self._perspective_seat:
            self._known_top.clear()

    def coin(self, seat: int | None = None) -> bool:
        if self._outcome_index < len(self._outcomes):
            outcome = self._outcomes[self._outcome_index]
            self._outcome_index += 1
            return outcome
        return self.delegate.coin(seat)

    def draw_bind(self, seat: int, deck: list[int],
                  *, prize: list[int] | None = None) -> int:
        if id(deck) in self._shuffled:
            return deck[-1]
        if seat == self._perspective_seat and self._known_top:
            serial = self._pin_known_top(deck)[0]
            self._known_top.pop(0)
            return serial
        return self._sample_deck_pool(seat, deck, 1)[0]

    def prize_bind(self, seat: int, deck: list[int], count: int) -> list[int]:
        if seat == self._perspective_seat and self._known_top:
            known = self._pin_known_top(deck)[:count]
            result = known + self._sample_deck_pool(
                seat, deck, count - len(known), exclude=known)
            _consume_known_top(self._known_top, result)
            return result
        return self._sample_deck_pool(seat, deck, count)

    def hand_pick(self, seat: int, hand: list[int]) -> int:
        if seat != self._perspective_seat:
            self._stop_hidden("hand_pick", (seat, hand), {})
        return self._sample(hand, 1, seat=seat)[0]

    def hand_pick_expect(self, *_args, **_kwargs) -> None:
        return None

    def look_bind(self, seat: int, deck: list[int], n: int,
                  *, from_bottom: bool = False) -> list[int]:
        if seat != self._perspective_seat:
            self._stop_hidden(
                "look_bind", (seat, deck, n), {"from_bottom": from_bottom})
        if id(deck) in self._shuffled:
            result = (list(deck[:n]) if from_bottom
                      else [deck[-1 - index] for index in range(min(n, len(deck)))])
        elif seat == self._perspective_seat and self._known_top:
            known = self._pin_known_top(deck)
            if from_bottom:
                unknown_count = max(0, len(deck) - len(known))
                sampled_count = min(n, unknown_count)
                result = self._sample_deck_pool(seat, deck, sampled_count)
                result += list(reversed(known))[:n - sampled_count]
            else:
                prefix = known[:n]
                result = prefix + self._sample_deck_pool(
                    seat, deck, n - len(prefix), exclude=prefix)
        else:
            result = self._sample_deck_pool(seat, deck, n)
        if seat == self._perspective_seat:
            if from_bottom:
                removed = set(result)
                self._known_top[:] = [
                    entry for entry in self._known_top if entry[0] not in removed]
            else:
                _consume_known_top(self._known_top, result)
        return result

    def mill_bind(self, seat: int, deck: list[int], prize: list[int],
                  n: int) -> list[int]:
        if seat != self._perspective_seat:
            self._stop_hidden("mill_bind", (seat, deck, prize, n), {})
        if id(deck) in self._shuffled:
            return [deck[-1 - index] for index in range(min(n, len(deck)))]
        if seat == self._perspective_seat and self._known_top:
            known = self._pin_known_top(deck)[:n]
            result = known + self._sample_deck_pool(
                seat, deck, n - len(known), exclude=known)
        else:
            result = self._sample_deck_pool(seat, deck, n)
        if seat == self._perspective_seat:
            _consume_known_top(self._known_top, result)
        return result

    def prize_take(self, seat: int, _serial: int, *, deck: list[int],
                   prize: list[int]) -> int:
        if (seat == self._perspective_seat
                and isinstance(self._knowledge.own_prizes, KnownOwnPrizes)):
            return self._sample(prize, 1, seat=seat)[0]
        slot_index = prize.index(_serial)
        if seat == self._perspective_seat:
            self._pin_known_top(deck)
        slot_serial = prize[slot_index]
        board = self._game_state.players[seat]
        hidden_zones = (deck, prize) if seat == self._perspective_seat else (
            deck, board.hand, prize)
        reserved = ({entry[0] for entry in self._known_top}
                    if seat == self._perspective_seat else set())
        selected = self._sample(
            [serial for zone in hidden_zones for serial in zone
             if serial not in reserved],
            1, seat=seat)[0]
        if selected == slot_serial:
            return selected
        source = next(zone for zone in hidden_zones if selected in zone)
        source[source.index(selected)] = slot_serial
        prize[slot_index] = selected
        return selected


class _PrescribedRng:
    def __init__(self, choices: tuple[_ExactChoice, ...],
                 outcomes: tuple[bool, ...] = (), *, perspective_seat: int,
                  knowledge: LegalKnowledge, game_state, turn_changed=lambda: False):
        self.delegate = SeededRng(0)
        self._choices = choices
        self._choice_index = 0
        self._outcomes = outcomes
        self._outcome_index = 0
        self._perspective_seat = perspective_seat
        self._knowledge = knowledge
        self._game_state = game_state
        self._turn_changed = turn_changed
        self._known_top = list(
            knowledge.known_top.cards
            if isinstance(knowledge.known_top, KnownDeckTop) else ())

    @property
    def knowledge(self) -> LegalKnowledge:
        known_top = (KnownDeckTop(tuple(self._known_top))
                     if self._known_top else UnknownDeckTop())
        return replace(self._knowledge, known_top=known_top)

    def _constrain(self, event: _ChanceEvent) -> _ChanceEvent:
        if event.seat != self._perspective_seat or not self._known_top:
            return event
        if event.method == "draw_bind":
            serial = self._known_top[0][0]
            if serial in event.values:
                return replace(event, values=(serial,))
        if event.method in ("look_bind", "mill_bind"):
            if event.method == "look_bind" and event.from_bottom:
                return event
            prefix = tuple(
                serial for serial, _card_id in self._known_top
                if serial in event.values)[:event.count]
            return replace(event, prefix=prefix)
        return event

    def _take(self, event: _ChanceEvent):
        event = self._constrain(event)
        if self._choice_index >= len(self._choices):
            kind, reason = _RANDOM_METHODS[event.method]
            raise _RandomBoundary(kind, reason, event)
        choice = self._choices[self._choice_index]
        if choice.method != event.method:
            raise SearchContractError("exact Chance Branch method diverged")
        self._choice_index += 1
        return choice.payload

    def shuffle(self, seq: list, *, seat: int) -> None:
        seq.sort(key=lambda serial: (self._game_state.card_id(serial), serial))
        if seat == self._perspective_seat:
            self._known_top.clear()

    def coin(self, seat: int | None = None) -> bool:
        if self._outcome_index < len(self._outcomes):
            outcome = self._outcomes[self._outcome_index]
            self._outcome_index += 1
            return outcome
        return bool(self._take(_chance_event("coin", (seat,), {})))

    def draw_bind(self, seat: int, deck: list[int],
                  *, prize: list[int] | None = None) -> int:
        if self._turn_changed():
            return self.delegate.draw_bind(seat, deck, prize=prize)
        serial = int(self._take(_chance_event("draw_bind", (seat, deck), {})))
        if serial not in deck:
            raise SearchContractError("exact draw branch selected a missing card")
        if seat == self._perspective_seat and self._known_top:
            if serial == self._known_top[0][0]:
                self._known_top.pop(0)
            else:
                self._known_top.clear()
        return serial

    def prize_bind(self, seat: int, deck: list[int], count: int) -> list[int]:
        return list(self._take(
            _chance_event("prize_bind", (seat, deck, count), {})))

    def hand_pick(self, seat: int, hand: list[int]) -> int:
        serial = int(self._take(_chance_event("hand_pick", (seat, hand), {})))
        if serial not in hand:
            raise SearchContractError("exact hand branch selected a missing card")
        return serial

    def hand_pick_expect(self, *_args, **_kwargs) -> None:
        return None

    def look_bind(self, seat: int, deck: list[int], n: int,
                  *, from_bottom: bool = False) -> list[int]:
        result = list(self._take(_chance_event(
            "look_bind", (seat, deck, n), {"from_bottom": from_bottom})))
        if seat == self._perspective_seat and not from_bottom:
            _consume_known_top(self._known_top, result)
        return result

    def mill_bind(self, seat: int, deck: list[int], prize: list[int],
                  n: int) -> list[int]:
        result = list(self._take(_chance_event(
            "mill_bind", (seat, deck, prize, n), {})))
        if seat == self._perspective_seat:
            _consume_known_top(self._known_top, result)
        return result

    def prize_take(self, seat: int, serial: int, *, deck: list[int],
                   prize: list[int]) -> int:
        return int(self._take(_chance_event(
            "prize_take", (seat, serial), {"deck": deck, "prize": prize})))


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
    chance_method: str | None = None
    chance_event: _ChanceEvent | None = None


def _stop_after_turn(_gs, _seat) -> None:
    raise _RandomBoundary(
        NodeKind.TURN_BOUNDARY, BoundaryReason.TURN_TRANSITION,
        _ChanceEvent("turn", None))


def _decklist(engine: Engine, seat: int) -> tuple[int, ...]:
    cards = sorted(engine.gs.cards.values(), key=lambda card: card.serial)
    return tuple(card.card_id for card in cards if card.owner == seat)


def _failure_type(failure: str | None) -> str | None:
    return None if failure is None else failure.split(":", 1)[0]


def _observation(engine: Engine, seat: int, *, include_select: bool,
                 knowledge: LegalKnowledge | None = None) -> ObservationState:
    gs = engine.gs
    printout = {
        "select": render.select_dict(gs) if include_select else None,
        "logs": [dict(entry) for entry in gs.outbox[seat]],
        "current": render.current_dict(gs, seat),
        "search_begin_input": None,
    }
    observation = ObservationStateBuilder(_decklist(engine, seat)).root(
        printout, knowledge=knowledge)
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
    identity = "cgpy-exact-turn-search-v1"

    def __init__(self, engine: Engine, *, perspective_seat: int,
                 knowledge: LegalKnowledge | None = None):
        if perspective_seat not in (0, 1):
            raise ValueError("Perspective Seat must be 0 or 1")
        if not isinstance(engine.gs.rng, SeededRng):
            raise ValueError("Turn Search Environment requires SeededRng")
        self.perspective_seat = int(perspective_seat)
        self._states: dict[object, _NodeState] = {}
        self._information_keys: dict[str, str] = {}
        root_engine = engine.fork()
        self._root_turn = root_engine.gs.turn
        self._root = self._make_node(root_engine, knowledge=knowledge)
        self._search_sample_origin = self._chance_information_key(self._root)

    @classmethod
    def from_snapshot(cls, snapshot: ExperimentSnapshot, *,
                      perspective_seat: int | None = None) -> "TurnSearchEnvironment":
        seat = snapshot.observation.seat if perspective_seat is None else perspective_seat
        return cls(
            snapshot.fork_engine(), perspective_seat=seat,
            knowledge=snapshot.observation.knowledge)

    @classmethod
    def from_engine(cls, engine: Engine, *,
                    perspective_seat: int,
                    knowledge: LegalKnowledge | None = None) -> "TurnSearchEnvironment":
        return cls(engine, perspective_seat=perspective_seat, knowledge=knowledge)

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
                  replay_plan: _ReplayPlan | None = None,
                  chance_method: str | None = None,
                  chance_event: _ChanceEvent | None = None) -> SearchNode:
        information_key = observation.decision_key
        previous = self._information_keys.setdefault(key.digest, information_key)
        if previous != information_key:
            raise SearchContractError(
                "one Search State Key produced conflicting legal information states")
        handle = object()
        self._states[handle] = _NodeState(
            engine, replay_plan, chance_method, chance_event)
        return SearchNode(
            kind, actor, self.perspective_seat, observation, key, self._root_turn,
            reason, failure, handle)

    def _make_node(self, engine: Engine, *,
                   knowledge: LegalKnowledge | None = None) -> SearchNode:
        kind, actor, reason = _classification(
            engine, self.perspective_seat, self._root_turn)
        observation = _observation(
            engine, self.perspective_seat,
            include_select=kind not in (
                NodeKind.INFORMATION_BOUNDARY, NodeKind.TURN_BOUNDARY),
            knowledge=knowledge)
        key = search_state_key(
            engine, kind, actor, self.perspective_seat, self._root_turn, reason,
            observation_key=observation.position_key)
        return self._register(engine, kind, actor, reason, observation, key)

    def _boundary_node(self, engine: Engine, kind: NodeKind,
                       reason: BoundaryReason, *,
                       replay_plan: _ReplayPlan | None = None,
                       chance_method: str | None = None,
                       chance_event: _ChanceEvent | None = None,
                       knowledge: LegalKnowledge | None = None) -> SearchNode:
        observation = _observation(
            engine, self.perspective_seat, include_select=False,
            knowledge=knowledge)
        continuation = None
        if replay_plan is not None:
            continuation = (
                replay_plan.action.kind, replay_plan.action.parts,
                len(replay_plan.outcomes), chance_method)
        key = (turn_boundary_state_key(
            perspective_seat=self.perspective_seat, root_turn=self._root_turn,
            observation_key=observation.position_key)
            if kind is NodeKind.TURN_BOUNDARY else search_state_key(
                engine, kind, None, self.perspective_seat, self._root_turn, reason,
                continuation=continuation, observation_key=observation.position_key))
        return self._register(
            engine, kind, None, reason, observation, key, replay_plan=replay_plan,
            chance_method=chance_method, chance_event=chance_event)

    def _unavailable_node(self, parent: SearchNode, engine: Engine,
                          action: ActionIdentity, exc: Exception) -> SearchNode:
        failure = f"{type(exc).__name__}: {exc}"
        observation = _observation(
            engine, self.perspective_seat, include_select=False,
            knowledge=parent.observation.knowledge)
        key = unavailable_state_key(parent.state_key, action, type(exc).__name__)
        return self._register(
            engine, NodeKind.UNAVAILABLE, None, None, observation, key, failure=failure)

    def fork(self, node: SearchNode) -> SearchNode:
        state = self._node_state(node)
        return self._register(
            state.engine.fork(), node.kind, node.actor_seat, node.boundary_reason,
            node.observation, node.state_key, failure=node.failure,
            replay_plan=state.replay_plan, chance_method=state.chance_method,
            chance_event=state.chance_event)

    def _run_plan(self, parent: SearchNode, plan: _ReplayPlan) -> SearchNode:
        child_engine = plan.source.fork()
        probe = _BoundaryProbeRng(
            child_engine.gs.rng,
            lambda: child_engine.gs.turn != self._root_turn,
            plan.outcomes, perspective_seat=self.perspective_seat,
            knowledge=parent.observation.knowledge,
            game_state=child_engine.gs)
        child_engine.gs.rng = probe
        hook_token = after_begin_turn.set(_stop_after_turn)
        try:
            child_engine.step(list(plan.selection))
        except _RandomBoundary as boundary:
            replay_plan = plan if boundary.kind is NodeKind.CHANCE else None
            child = self._boundary_node(
                child_engine, boundary.kind, boundary.reason,
                replay_plan=replay_plan, chance_method=boundary.method,
                chance_event=boundary.event,
                knowledge=probe.knowledge)
        except Exception as exc:
            child = self._unavailable_node(parent, child_engine, plan.action, exc)
        else:
            child = self._make_node(
                child_engine, knowledge=probe.knowledge)
        finally:
            child_engine.gs.rng = probe.delegate
            after_begin_turn.reset(hook_token)
        return child

    def _run_sampled_plan(self, parent: SearchNode, plan: _ReplayPlan,
                          seed: int) -> SearchNode:
        child_engine = plan.source.fork()
        rng = _SegmentRng(
            seed, plan.outcomes, perspective_seat=self.perspective_seat,
            knowledge=parent.observation.knowledge,
            game_state=child_engine.gs)
        child_engine.gs.rng = rng
        hook_token = after_begin_turn.set(_stop_after_turn)
        try:
            child_engine.step(list(plan.selection))
        except _RandomBoundary as boundary:
            child = self._boundary_node(
                child_engine, boundary.kind, boundary.reason,
                chance_method=boundary.method, chance_event=boundary.event,
                knowledge=rng.knowledge)
        except Exception as exc:
            child = self._unavailable_node(parent, child_engine, plan.action, exc)
        else:
            child = self._make_node(child_engine, knowledge=rng.knowledge)
        finally:
            child_engine.gs.rng = rng.delegate
            after_begin_turn.reset(hook_token)
        return child

    def _probe_exact_plan(
            self, parent: SearchNode, plan: _ReplayPlan,
            choices: tuple[_ExactChoice, ...]) -> tuple[SearchNode | None,
                                                        _ChanceEvent | None]:
        child_engine = plan.source.fork()
        rng = _PrescribedRng(
            choices, plan.outcomes, perspective_seat=self.perspective_seat,
            knowledge=parent.observation.knowledge, game_state=child_engine.gs,
            turn_changed=lambda: child_engine.gs.turn != self._root_turn)
        child_engine.gs.rng = rng
        hook_token = after_begin_turn.set(_stop_after_turn)
        child = None
        event = None
        try:
            child_engine.step(list(plan.selection))
        except _RandomBoundary as boundary:
            if boundary.kind is NodeKind.CHANCE:
                event = boundary.event
            else:
                child = self._boundary_node(
                    child_engine, boundary.kind, boundary.reason,
                    knowledge=rng.knowledge)
        except Exception as exc:
            child = self._unavailable_node(parent, child_engine, plan.action, exc)
        else:
            child = self._make_node(
                child_engine, knowledge=rng.knowledge)
        finally:
            child_engine.gs.rng = rng.delegate
            after_begin_turn.reset(hook_token)
        return child, event

    @staticmethod
    def _exact_choices(event: _ChanceEvent,
                       limit: int | None) -> tuple[_ExactChoice, ...] | None:
        values = event.values
        if event.method == "coin":
            return (
                _ExactChoice("coin", False, 0.5),
                _ExactChoice("coin", True, 0.5),
            ) if limit is None or limit >= 2 else None
        if event.method in ("draw_bind", "hand_pick", "prize_take"):
            support = len(values)
            if support == 0 or (limit is not None and support > limit):
                return None
            probability = 1.0 / support
            return tuple(_ExactChoice(event.method, value, probability)
                         for value in values)
        if event.method in ("prize_bind", "look_bind", "mill_bind"):
            count = min(max(0, event.count), len(values))
            prefix = event.prefix[:count]
            remaining = tuple(value for value in values if value not in prefix)
            remainder_count = count - len(prefix)
            support = perm(len(remaining), remainder_count)
            if limit is not None and support > limit:
                return None
            probability = 1.0 / support
            return tuple(_ExactChoice(
                event.method, prefix + value, probability)
                         for value in permutations(remaining, remainder_count))
        return None

    def _exact_transitions(
            self, node: SearchNode,
            limit: int | None) -> tuple[ChanceTransition, ...] | None:
        state = self._node_state(node)
        plan = state.replay_plan
        if plan is None:
            return None
        leaves: list[tuple[tuple[_ExactChoice, ...], float, SearchNode]] = []
        aborted = False

        def visit(choices: tuple[_ExactChoice, ...], probability: float) -> None:
            nonlocal aborted
            if aborted:
                return
            child, event = self._probe_exact_plan(node, plan, choices)
            if child is not None:
                leaves.append((choices, probability, child))
                if limit is not None and len(leaves) > limit:
                    aborted = True
                return
            if self._event_has_hidden_support(event, node.observation.knowledge):
                aborted = True
                return
            options = self._exact_choices(event, limit)
            if options is None:
                aborted = True
                return
            for option in options:
                visit(choices + (option,), probability * option.probability)

        visit((), 1.0)
        if aborted or not leaves:
            return None
        method = state.chance_method or leaves[0][0][0].method
        return tuple(
            ChanceTransition(
                node.state_key, None, None, child.state_key, child.kind,
                child.boundary_reason, _failure_type(child.failure), child,
                branch_key=ChanceBranchKey.exact(
                    method=method, index=index,
                    root_state_key=self.root.state_key.digest,
                    node_state_key=node.state_key.digest, action=plan.action),
                method=method, probability=probability)
            for index, (_choices, probability, child) in enumerate(leaves)
        )

    def transition(self, node: SearchNode,
                   action: object) -> PrimitiveTransition:
        state = self._node_state(node)
        if node.kind not in (NodeKind.PLAYER_DECISION, NodeKind.FORCED_DECISION):
            raise SearchContractError(f"cannot transition a {node.kind.value} Search Node")
        identity = getattr(action, "identity", action)
        selection = getattr(action, "selection", None)
        if not isinstance(identity, ActionIdentity):
            raise TypeError("Primitive Action must be an ActionIdentity")
        matching = tuple(candidate for candidate in self.legal_actions(node)
                         if candidate.identity == identity
                         and (selection is None or tuple(candidate.selection) == tuple(selection)))
        if len(matching) != 1:
            detail = "missing" if not matching else "ambiguous"
            raise SearchContractError(f"Primitive Action identity is {detail}")
        child = self._run_plan(node, _ReplayPlan(
            state.engine, tuple(matching[0].selection), identity, ()))
        return PrimitiveTransition(
            node.state_key, identity, child.state_key, child.kind,
            child.boundary_reason, child.failure, child)

    def replay(self, node: SearchNode,
               recorded: PrimitiveTransition) -> PrimitiveTransition:
        self._assert_replay(node, recorded, PrimitiveTransition, "Primitive Transition")
        replayed = self.transition(node, recorded.action)
        if replayed != recorded:
            raise SearchContractError("Primitive Transition replay diverged")
        return replayed

    @property
    def retained_states(self) -> int:
        return len(self._states)

    @property
    def peak_retained_states(self) -> int:
        return len(self._states)

    def ledger_state(self, node: SearchNode) -> ProviderState:
        state = self._node_state(node)
        payload = state.engine.observation(viewer=self.perspective_seat, sbi_token=None)
        return ProviderState(payload, node.observation, token=node.observation.decision_key,
                             deck=node.observation.decklist, deck_counts=node.observation.deck_counts or ())

    def work_item(self, node: SearchNode, operation: str, arguments: tuple) -> ProviderJob:
        self._node_state(node)
        isolated = copy(self)
        handles = {self.root._handle, node._handle}
        isolated._states = {handle: self._states[handle] for handle in handles}
        isolated._information_keys = {
            str(item.state_key): item.observation.decision_key for item in (self.root, node)}
        return ProviderJob(_execute_turn_operation, (isolated, node, operation, arguments), 6)

    def accept_work(self, result) -> SearchNode:
        node, state = result
        self._states[node._handle] = state
        self._information_keys[str(node.state_key)] = node.observation.decision_key
        return node

    def reuse_from(self, previous, node: SearchNode) -> bool:
        if (not isinstance(previous, TurnSearchEnvironment)
                or node._handle not in previous._states
                or self.root.state_key != node.state_key
                or self.root.observation.decision_key != node.observation.decision_key
                or self.root.root_turn != node.root_turn):
            return False
        self._states, previous._states = previous._states, {}
        self._information_keys, previous._information_keys = previous._information_keys, {}
        self._search_sample_origin = previous._search_sample_origin
        self._root = node
        return True

    def close(self) -> None:
        self._states.clear()
        self._information_keys.clear()

    def reproduction_input(self) -> str:
        return json.dumps({
            "schema": "cgpy-exact-search-root", "schema_version": 1,
            "state_key": str(self.root.state_key),
            "decision_key": self.root.observation.decision_key,
        }, sort_keys=True, separators=(",", ":"))

    def release_worker_states(self) -> int:
        return 0

    def observe_completion(self, _completion, affinity=None) -> None:
        return None

    def chance_plan(self, node: SearchNode, sample_count: int) -> ChancePlan:
        state = self._node_state(node)
        if node.kind is not NodeKind.CHANCE or sample_count < 1:
            raise SearchContractError("chance plan requires a chance node and positive sample count")
        method = state.chance_method or "coin"
        probabilities = (0.5, 0.5) if method == "coin" else (1.0 / sample_count,) * sample_count
        return ChancePlan(self._chance_information_key(node), method, probabilities, method != "coin")

    def sample_for_search(self, node: SearchNode, experiment_seed: int,
                          sample_index: int) -> ChanceTransition:
        state = self._node_state(node)
        action = state.replay_plan.action if state.replay_plan is not None else ActionIdentity("coin")
        if state.chance_method in (None, "coin"):
            if sample_index not in (0, 1):
                raise SearchContractError("exact coin slot must be zero or one")
            branch = ChanceBranchKey.exact(
                method="coin", index=sample_index,
                root_state_key=self._search_sample_origin,
                node_state_key=self._chance_information_key(node), action=action)
            return self._resolve_coin(node, bool(sample_index), branch, 0.5)
        return self.sample(node, ChanceSampleKey(
            experiment_seed, self._search_sample_origin,
            self._chance_information_key(node), action, sample_index))

    def sample(self, node: SearchNode, sample: ChanceSampleKey) -> ChanceTransition:
        state = self._node_state(node)
        if node.kind is not NodeKind.CHANCE:
            raise SearchContractError(f"cannot sample a {node.kind.value} Search Node")
        if not isinstance(sample, ChanceSampleKey):
            raise TypeError("sample requires a Chance Sample Key")
        root_keys = {self.root.state_key.digest,
                     self._chance_information_key(self.root), self._search_sample_origin}
        if sample.root_state_key not in root_keys:
            raise SearchContractError("Chance Sample root key does not match")
        node_keys = {node.state_key.digest, self._chance_information_key(node)}
        if sample.node_state_key not in node_keys:
            raise SearchContractError("Chance Sample node key does not match")
        if (state.replay_plan is not None
                and sample.action != state.replay_plan.action):
            raise SearchContractError("Chance Sample action does not match")
        method = state.chance_method or "coin"
        branch = ChanceBranchKey.sampled(sample, method=method)
        if method == "coin":
            return self._resolve_coin(node, SeededRng(sample.seed).coin(), branch, 1.0)
        return self._resolve_sampled_segment(node, branch, 1.0)

    def _resolve_sampled_segment(self, node: SearchNode,
                                 branch: ChanceBranchKey,
                                 probability: float) -> ChanceTransition:
        state = self._node_state(node)
        if state.replay_plan is None or branch.sample is None:
            raise SearchContractError("Chance Node has no replayable stochastic segment")
        child = self._run_sampled_plan(
            node, state.replay_plan, branch.sample.seed)
        return ChanceTransition(
            node.state_key, branch.sample, None, child.state_key, child.kind,
            child.boundary_reason, _failure_type(child.failure), child,
            branch_key=branch, method=branch.method, probability=probability)

    def _resolve_coin(self, node: SearchNode, head: bool,
                      branch: ChanceBranchKey, probability: float) -> ChanceTransition:
        state = self._node_state(node)
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
            node.state_key, branch.sample, outcome, child.state_key, child.kind,
            child.boundary_reason, _failure_type(child.failure), child,
            branch_key=branch, method="coin", probability=probability)

    def expand(self, node: SearchNode,
               request: ChanceExpansionRequest) -> ChanceExpansion:
        state = self._node_state(node)
        if node.kind is not NodeKind.CHANCE:
            raise SearchContractError(f"cannot expand a {node.kind.value} Search Node")
        if not isinstance(request, ChanceExpansionRequest):
            raise TypeError("expand requires a Chance Expansion Request")
        method = state.chance_method or "coin"
        action = (state.replay_plan.action if state.replay_plan is not None
                  else ActionIdentity("coin"))
        exact = self._exact_transitions(node, request.exact_outcome_limit)
        if exact is not None:
            successors = self._coalesce_successors(exact)
            produced = sum(transition.result_kind is not NodeKind.UNAVAILABLE
                           for transition in exact)
            status = (ChanceExpansionStatus.COMPLETE
                      if produced == len(exact) else
                      ChanceExpansionStatus.INCOMPLETE if produced else
                      ChanceExpansionStatus.UNAVAILABLE)
            return ChanceExpansion(
                node.state_key, method, status, exact, successors,
                request.exact_outcome_limit, request.sample_count, len(exact),
                len(exact), produced,
                None if produced else "no exact branch resolved")
        if state.replay_plan is not None or request.exact_outcome_limit < 2:
            root_information_key = self._chance_information_key(self.root)
            node_information_key = self._chance_information_key(node)

            def resolve_sample(index: int) -> ChanceTransition:
                branch = ChanceBranchKey.sampled(ChanceSampleKey(
                    request.experiment_seed, root_information_key,
                    node_information_key, action, index), method=method)
                if state.replay_plan is None:
                    return self._resolve_coin(
                        node, SeededRng(branch.sample.seed).coin(), branch,
                        1.0 / request.sample_count)
                return self._resolve_sampled_segment(
                    node, branch, 1.0 / request.sample_count)

            transitions = tuple(resolve_sample(index)
                                for index in range(request.sample_count))
            successors = self._coalesce_successors(transitions)
            produced = sum(
                transition.result_kind is not NodeKind.UNAVAILABLE
                for transition in transitions)
            status = (ChanceExpansionStatus.ESTIMATED
                      if produced == request.sample_count else
                      ChanceExpansionStatus.INCOMPLETE if produced else
                      ChanceExpansionStatus.UNAVAILABLE)
            return ChanceExpansion(
                node.state_key, method, status, transitions, successors,
                request.exact_outcome_limit, request.sample_count, None,
                request.sample_count, produced,
                None if produced else "no sampled branch resolved")
        branches = tuple(ChanceBranchKey.exact(
            method="coin", index=index,
            root_state_key=self.root.state_key.digest,
            node_state_key=node.state_key.digest, action=action)
                         for index in range(2))
        transitions = tuple(
            self._resolve_coin(node, bool(index), branch, 0.5)
            for index, branch in enumerate(branches))
        successors = self._coalesce_successors(transitions)
        produced = sum(transition.result_kind is not NodeKind.UNAVAILABLE
                       for transition in transitions)
        status = (ChanceExpansionStatus.COMPLETE if produced == 2 else
                  ChanceExpansionStatus.INCOMPLETE if produced else
                  ChanceExpansionStatus.UNAVAILABLE)
        return ChanceExpansion(
            node.state_key, "coin", status,
            transitions, successors, request.exact_outcome_limit,
            request.sample_count, 2, 2, produced,
            None if produced else "no exact branch resolved")

    @staticmethod
    def _coalesce_successors(
            transitions: tuple[ChanceTransition, ...]) -> tuple[ChanceSuccessor, ...]:
        grouped = {}
        for transition in transitions:
            if transition.node is None or transition.result_kind is NodeKind.UNAVAILABLE:
                continue
            key = transition.result_state_key
            if key not in grouped:
                grouped[key] = [0.0, [], transition.node]
            grouped[key][0] += transition.probability
            grouped[key][1].append(transition.branch_key)
        return tuple(
            ChanceSuccessor(probability, tuple(branches), node)
            for probability, branches, node in grouped.values())

    def replay_chance(self, node: SearchNode,
                      recorded: ChanceTransition) -> ChanceTransition:
        self._assert_replay(node, recorded, ChanceTransition, "Chance Transition")
        if recorded.schema_version == 1:
            current = self.sample(node, recorded.sample)
            replayed = ChanceTransition(
                current.parent_state_key, current.sample, current.outcome,
                current.result_state_key, current.result_kind,
                current.boundary_reason, current.failure, current.node,
                schema_version=1)
        elif recorded.branch_key.kind is ChanceBranchKind.SAMPLED:
            if recorded.method == "coin":
                replayed = self._resolve_coin(
                    node, SeededRng(recorded.branch_key.sample.seed).coin(),
                    recorded.branch_key, recorded.probability)
            else:
                replayed = self._resolve_sampled_segment(
                    node, recorded.branch_key, recorded.probability)
        else:
            state = self._node_state(node)
            if state.replay_plan is None:
                replayed = self._resolve_coin(
                    node, bool(recorded.branch_key.index),
                    recorded.branch_key, recorded.probability)
            else:
                exact = self._exact_transitions(node, None)
                if exact is None or recorded.branch_key.index >= len(exact):
                    raise SearchContractError("exact Chance Branch is unavailable")
                replayed = exact[recorded.branch_key.index]
        if replayed != recorded:
            raise SearchContractError("Chance Transition replay diverged")
        return replayed

    def _assert_replay(self, node: SearchNode, recorded, expected, label: str) -> None:
        self._node_state(node)
        if not isinstance(recorded, expected):
            raise TypeError(f"replay requires a {label}")
        supported = ((1, 2) if expected is ChanceTransition else (1,))
        if recorded.schema_version not in supported:
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

    def information_key(self, state_key: SearchStateKey | str) -> str:
        digest = state_key.digest if isinstance(state_key, SearchStateKey) else str(state_key)
        try:
            return self._information_keys[digest]
        except KeyError as exc:
            raise SearchContractError("Search State Key is absent from this environment") from exc

    def _chance_information_key(self, node: SearchNode) -> str:
        state = self._node_state(node)
        plan = state.replay_plan
        return ChanceInformationKey(
            node.observation.decision_key,
            node.kind.value,
            None if node.boundary_reason is None else node.boundary_reason.value,
            None if plan is None else plan.action,
            0 if plan is None else len(plan.outcomes),
            state.chance_method,
        ).digest

    def _event_has_hidden_support(
            self, event: _ChanceEvent, knowledge: LegalKnowledge) -> bool:
        if event.method == "coin":
            return False
        if event.seat != self.perspective_seat:
            return True
        return (
            not isinstance(knowledge.own_prizes, KnownOwnPrizes)
            and event.method in {
                "shuffle", "draw_bind", "prize_bind", "look_bind",
                "mill_bind", "prize_take",
            }
        )


def _execute_turn_operation(environment, node, operation, arguments):
    try:
        transition = (environment.transition(node, *arguments) if operation == "transition"
                      else environment.sample_for_search(node, *arguments))
        value = transition.node, environment._node_state(transition.node)
        return ProviderCompletion(value, 1, environment.retained_states)
    finally:
        environment.close()


__all__ = ("TurnSearchEnvironment",)
