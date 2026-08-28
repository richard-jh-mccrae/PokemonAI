"""Immutable player-visible state built from an engine printout at one boundary."""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field, replace
from functools import cached_property

from common.cards.functions.attack_lock import fold_attack_locks
from common.options import enumerate_legal_actions
from .knowledge import (KnownAttackLocks, KnownDeckTop, KnownOwnPrizes, LegalKnowledge,
                        UnknownAttackLocks, UnknownDeckTop, UnknownOwnPrizes, reduce_knowledge)

from .nodes import (
    Body, Card, HiddenHand, Looking, SelectPrompt, Side, Turn, VisibleHand, active_node,
    body_node, canon, card_bag, card_tuple, feed, looking_node, select_node, turn_node)

ME, THEM = "me", "them"
_SIDE_PIECES = ("active", "bench", "hand", "discard", "scalars")
#: The pieces whose change can move my remaining-deck arithmetic.
_DECK_PIECES = frozenset({(ME, "active"), (ME, "bench"), (ME, "hand"), (ME, "discard"),
                          ("stadium",), ("extras",)})
KEY_BYTES = 32
SCHEMA_VERSION = 1
_LEGAL_RAW_FIELDS = frozenset({
    "active", "appearThisTurn", "area", "asleep", "attackId", "bench", "benchMax",
    "burned", "cardId", "confused", "context", "contextCard", "count", "deck",
    "deckCount", "discard", "effect", "energies", "energyCards", "energyIndex", "hand",
    "handCount", "hp", "id", "inPlayArea", "inPlayIndex", "index", "maxCount", "maxHp",
    "minCount", "number", "option", "paralyzed", "playerIndex", "poisoned", "preEvolution",
    "prize", "remainDamageCounter", "remainEnergyCost", "serial", "specialConditionType",
    "stadium", "toolIndex", "tools", "type",
})
_EVENT_FIELDS = frozenset({
    "area", "attackId", "cardId", "cardIdActive", "cardIdAfter", "cardIdBefore",
    "cardIdBench", "cardIdTarget", "count", "damage", "drawcount", "energyIndex",
    "fromArea", "index", "inPlayArea", "inPlayIndex", "isRecover", "playerIndex",
    "putDamageCounter", "reason", "result", "serial", "serialActive", "serialAfter",
    "serialBefore", "serialBench", "serialTarget", "specialConditionType", "toArea",
    "toolIndex", "value",
})


class ObservationConstructionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ObservationEvent:
    kind: int | None
    public_fields: tuple[tuple[str, object], ...]
    recognized: bool


@dataclass(frozen=True, slots=True)
class AttackEvent(ObservationEvent):
    pass


@dataclass(frozen=True, slots=True)
class MoveCardEvent(ObservationEvent):
    pass


@dataclass(frozen=True, slots=True)
class DrawEvent(ObservationEvent):
    pass


@dataclass(frozen=True, slots=True)
class ShuffleEvent(ObservationEvent):
    pass


@dataclass(frozen=True, slots=True)
class KnownObservationEvent(ObservationEvent):
    pass


@dataclass(frozen=True, slots=True)
class UnknownObservationEvent(ObservationEvent):
    pass


@dataclass(frozen=True, slots=True)
class ObservationDelta:
    parts: tuple[tuple[str, ...], ...]


class ObservationStateBuilder:
    __slots__ = ("decklist",)

    def __init__(self, decklist=None):
        self.decklist = None if decklist is None else tuple(int(card_id) for card_id in decklist)

    def root(self, printout, *, knowledge: LegalKnowledge | None = None) -> "ObservationState":
        try:
            _validate(printout)
            current = printout["current"]
            seat = int(current["yourIndex"])
            state, _delta = _build(
                ObservationState, printout, seat, self.decklist, None, knowledge)
            return state
        except ObservationConstructionError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ObservationConstructionError(str(exc)) from exc

    def advance(self, parent: "ObservationState", printout, *, knowledge: LegalKnowledge | None = None) -> tuple["ObservationState", ObservationDelta]:
        try:
            _validate(printout)
            state, delta = _build(type(parent), printout, parent.seat, parent.decklist, parent,
                                  parent.knowledge if knowledge is None else knowledge)
            return state, delta
        except ObservationConstructionError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ObservationConstructionError(str(exc)) from exc

    def rebind_knowledge(self, state: "ObservationState",
                         knowledge: LegalKnowledge) -> tuple["ObservationState", ObservationDelta]:
        if not isinstance(knowledge, LegalKnowledge):
            raise TypeError("knowledge must be LegalKnowledge")
        if any(not event.recognized for event in state.events):
            knowledge = LegalKnowledge(opponent=knowledge.opponent)
        if state.knowledge == knowledge:
            return state, ObservationDelta(())
        deck_counts = state.deck_counts
        if state.knowledge.own_prizes != knowledge.own_prizes:
            own_prizes = (knowledge.own_prizes.cards
                          if isinstance(knowledge.own_prizes, KnownOwnPrizes) else None)
            deck_counts = _remaining_deck_counts(
                state.decklist, state.seat, state.me, state.stadium, own_prizes)
        rebound = replace(state, deck_counts=deck_counts, knowledge=knowledge)
        parts = []
        for field_name, path_name in (
                ("own_prizes", "own_prizes"),
                ("known_top", "deck_top"),
                ("attack_locks", "attack_locks"),
                ("opponent", "opponent_belief")):
            if getattr(state.knowledge, field_name) != getattr(knowledge, field_name):
                parts.append(("knowledge", path_name))
        return rebound, ObservationDelta(tuple(sorted(parts)))


@dataclass(frozen=True)
class ObservationState:
    """One decision point's immutable legal view; built by ObservationStateBuilder."""

    seat: int
    me: Side
    them: Side
    turn: Turn
    stadium: tuple[Card, ...]
    looking: Looking | None
    select: SelectPrompt | None
    decklist: tuple[int, ...] | None
    #: MY unseen pool by card id — exact deck once `own_prizes` anchors, deck∪prizes before it.
    deck_counts: tuple[tuple[int, int], ...] | None
    knowledge: LegalKnowledge
    legal_actions: tuple = ()
    events: tuple = field(default=(), compare=False)
    _pieces: tuple = field(default=(), compare=False, repr=False)

    def side(self, name: str) -> Side:
        return self.me if name == ME else self.them

    @cached_property
    def position_key(self) -> str:
        hasher = hashlib.blake2b(digest_size=KEY_BYTES)
        feed(hasher.update, SCHEMA_VERSION)
        feed(hasher.update, self.seat)
        # Deck knowledge is position identity: the same pieces under another decklist must differ.
        feed(hasher.update, self.deck_counts)
        opponent = self.knowledge.opponent
        knowledge_identity = (_knowledge_key(self.knowledge), _semantic_locks(self),
                              opponent.evidence, opponent.probabilities)
        if opponent.decision_evidence is not None:
            knowledge_identity += (opponent.decision_evidence.identity,)
        feed(hasher.update, knowledge_identity)
        feed(hasher.update, (_side_identity(self.me), _side_identity(self.them),
                             self.turn.scalars(), tuple(sorted(card.card_id for card in self.stadium)),
                             _looking_identity(self.looking)))
        return hasher.hexdigest()

    @cached_property
    def decision_key(self) -> str:
        hasher = hashlib.blake2b(digest_size=KEY_BYTES)
        feed(hasher.update, 1)
        feed(hasher.update, self.position_key)
        feed(hasher.update, None if self.select is None else self.select.identity())
        feed(hasher.update, tuple((action.identity.kind, action.identity.parts)
                                  for action in self.legal_actions))
        return hasher.hexdigest()

    @cached_property
    def valuation_key(self) -> str:
        hasher = hashlib.blake2b(digest_size=KEY_BYTES)
        feed(hasher.update, 1)
        feed(hasher.update, self.position_key)
        feed(hasher.update, tuple(
            (card.card_id, card.owner) for card in self.stadium))
        feed(hasher.update, tuple(
            (action.identity.kind, action.identity.parts)
            for action in self.legal_actions))
        feed(hasher.update, tuple(
            (event.kind, event.public_fields, event.recognized)
            for event in self.events))
        return hasher.hexdigest()

    @property
    def key(self) -> str:
        return self.position_key


class _Build:
    """One root/advance pass: piece bookkeeping shared by every zone builder below."""

    def __init__(self, printout, seat, parent, knowledge):
        self.printout, self.seat, self.parent = printout, seat, parent
        self.knowledge = knowledge
        self.parent_pieces = {} if parent is None else dict(parent._pieces)
        self.pieces: dict = {}
        self.changed: set = set()

    def reuse(self, label, raw_value) -> bool:
        """Record the piece's new raw subtree; True when the parent's piece survives as-is."""
        normalized = _legal_raw(raw_value)
        self.pieces[label] = normalized
        if label in self.parent_pieces and self.parent_pieces[label] == normalized:
            return True
        self.changed.add(label)
        return False

def _validate(printout) -> None:
    if not isinstance(printout, dict) or not isinstance(printout.get("current"), dict):
        raise ObservationConstructionError("observation.current must be an object")
    current = printout["current"]
    required_current = {"turn", "yourIndex", "players", "firstPlayer", "supporterPlayed",
                        "stadiumPlayed", "energyAttached", "retreated", "result", "stadium",
                        "looking"}
    missing = sorted(required_current - current.keys())
    if missing:
        raise ObservationConstructionError(
            f"observation.current missing required fields: {', '.join(missing)}")
    players = current["players"]
    if not isinstance(players, (list, tuple)) or len(players) != 2:
        raise ObservationConstructionError("observation.current.players must contain two seats")
    if not all(isinstance(player, dict) for player in players):
        raise ObservationConstructionError("observation.current.players entries must be objects")
    seat = printout["current"].get("yourIndex")
    if seat not in (0, 1):
        raise ObservationConstructionError("observation.current.yourIndex must be 0 or 1")
    if "turn" not in printout["current"]:
        raise ObservationConstructionError("observation.current.turn is required")
    for player in players:
        required_player = {"active", "bench", "benchMax", "deckCount", "hand", "handCount",
                           "discard", "prize", "poisoned", "burned", "asleep", "paralyzed",
                           "confused"}
        missing = sorted(required_player - player.keys())
        if missing:
            raise ObservationConstructionError(
                f"player missing required fields: {', '.join(missing)}")
        for zone in ("active", "bench"):
            entries = player.get(zone)
            if entries is None or not isinstance(entries, (list, tuple)):
                raise ObservationConstructionError(f"player.{zone} must be a list")
            for body in entries:
                if body is None:
                    continue
                if not isinstance(body, dict) or any(key not in body for key in ("id", "hp", "maxHp")):
                    raise ObservationConstructionError(
                        f"player.{zone} bodies require id, hp, and maxHp")


def _legal_raw(value):
    if isinstance(value, dict):
        return tuple((str(key), _legal_raw(child)) for key, child in
                     sorted(value.items(), key=lambda item: str(item[0]))
                     if key in _LEGAL_RAW_FIELDS)
    if isinstance(value, (list, tuple)):
        return tuple(_legal_raw(child) for child in value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise ObservationConstructionError(
        f"unsupported observation value {type(value).__name__}")


def _build(cls, printout, seat, decklist, parent, knowledge=None):
    build = _Build(printout, seat, parent, knowledge)
    current = printout.get("current") or {}
    players = current.get("players") or ()

    def player(index):
        return players[index] if 0 <= index < len(players) and players[index] else {}

    me = _side(build, ME, player(seat), parent.me if parent else None, own=True)
    them = _side(build, THEM, player(1 - seat), parent.them if parent else None, own=False)
    turn = _turn(build, current)
    stadium = _stadium(build, current)
    looking = _looking(build, current)
    select = _select(build, printout)
    own_prizes, known_top, attack_locks = _extras(build, printout)
    legal_actions = enumerate_legal_actions(printout)
    events = _observation_events(build, printout.get("logs"))
    resolved_knowledge = (LegalKnowledge(
                              own_prizes=(KnownOwnPrizes(own_prizes)
                                          if "own_prizes" in printout else UnknownOwnPrizes()),
                              known_top=(KnownDeckTop(known_top)
                                         if "known_top" in printout else UnknownDeckTop()),
                              attack_locks=(KnownAttackLocks(attack_locks)
                                            if attack_locks else UnknownAttackLocks()))
                          if knowledge is None else
                          (reduce_knowledge(knowledge, attack_locks=attack_locks or ())
                           if attack_locks or isinstance(knowledge.attack_locks, KnownAttackLocks)
                           else knowledge))
    if any(not event.recognized for event in events):
        resolved_knowledge = LegalKnowledge(opponent=resolved_knowledge.opponent)
    own_prizes = (resolved_knowledge.own_prizes.cards
                  if isinstance(resolved_knowledge.own_prizes, KnownOwnPrizes) else None)
    known_top = (resolved_knowledge.known_top.cards
                 if isinstance(resolved_knowledge.known_top, KnownDeckTop) else None)
    attack_locks = (resolved_knowledge.attack_locks.locks
                    if isinstance(resolved_knowledge.attack_locks, KnownAttackLocks) else None)
    deck_counts = _deck_counts(build, decklist, seat, me, stadium, own_prizes)
    state = cls(seat, me, them, turn, stadium, looking, select,
                decklist, deck_counts, resolved_knowledge, legal_actions, events,
                tuple(build.pieces.items()))
    return state, ObservationDelta(_delta_parts(build.changed, parent, state))


def _side(build: _Build, prefix: str, raw_player, parent_side: Side | None, *, own: bool) -> Side:
    label = (prefix, "active")
    if build.reuse(label, raw_player.get("active")):
        active, hidden = parent_side.active, parent_side.active_hidden
    else:
        active, hidden = active_node(raw_player.get("active"))

    label = (prefix, "bench")
    if build.reuse(label, raw_player.get("bench")):
        bench = parent_side.bench
    else:
        bench = _bench(build, label, raw_player.get("bench"), parent_side)

    # The boundary: an opponent's hand contents are never read, even off a full-truth frame.
    raw_hand = (raw_player.get("hand") if own else
                ("hidden", int(raw_player.get("handCount") or 0)))
    label = (prefix, "hand")
    if build.reuse(label, raw_hand):
        hand = parent_side.hand
    else:
        hand = (HiddenHand(int(raw_player.get("handCount") or 0)) if not own
                else VisibleHand(card_bag(raw_hand or ())))

    label = (prefix, "discard")
    if build.reuse(label, raw_player.get("discard")):
        discard = parent_side.discard
    else:
        discard = card_bag(raw_player.get("discard"))

    raw_hand_count = raw_player.get("handCount")
    scalars = (int(raw_player.get("benchMax") or 5), int(raw_player.get("deckCount") or 0),
               int(raw_hand_count if raw_hand_count is not None else len(raw_hand or ())),
               len(raw_player.get("prize") or ()), bool(raw_player.get("poisoned")),
               bool(raw_player.get("burned")), bool(raw_player.get("asleep")),
               bool(raw_player.get("paralyzed")), bool(raw_player.get("confused")))
    label = (prefix, "scalars")
    build.reuse(label, scalars)

    if parent_side is not None and not (build.changed & {(prefix, p) for p in _SIDE_PIECES}):
        return parent_side
    return Side(active=active, active_hidden=hidden, bench=bench, bench_max=scalars[0],
                deck_count=scalars[1], hand=hand, hand_count=scalars[2], discard=discard,
                prize_count=scalars[3], poisoned=scalars[4], burned=scalars[5],
                asleep=scalars[6], paralyzed=scalars[7], confused=scalars[8])


def _bench(build: _Build, label, raw_bench, parent_side: Side | None) -> tuple[Body, ...]:
    """Rebuild the bench, but a body whose raw dict is unchanged keeps its parent node."""
    survivors = {}
    if parent_side is not None:
        for node in parent_side.bench:
            survivors.setdefault(node.card.serial, []).append(node)
    bench = []
    for entry in raw_bench or ():
        if not entry:
            continue
        candidate = body_node(entry)
        node = next((old for old in survivors.get(entry.get("serial"), ())
                     if old == candidate), candidate)
        if node is not None:
            bench.append(node)
    return tuple(bench)


def _turn(build: _Build, current) -> Turn:
    values = (current.get("turn"), current.get("firstPlayer"), current.get("supporterPlayed"),
              current.get("stadiumPlayed"), current.get("energyAttached"),
              current.get("retreated"), canon(current.get("result")))
    if build.reuse(("turn",), values):
        return build.parent.turn
    node = turn_node(current)
    return node


def _stadium(build: _Build, current) -> tuple[Card, ...]:
    if build.reuse(("stadium",), current.get("stadium")):
        return build.parent.stadium
    cards = card_tuple(current.get("stadium"))
    return cards


def _looking(build: _Build, current) -> Looking | None:
    if build.reuse(("looking",), current.get("looking")):
        return build.parent.looking
    node = looking_node(current.get("looking"))
    return node


def _select(build: _Build, printout) -> SelectPrompt | None:
    if build.reuse(("select",), printout.get("select")):
        return build.parent.select
    node = select_node(printout.get("select"))
    return node


def _extras(build: _Build, printout):
    knowledge = build.knowledge
    raw_prizes = (_known_prizes(knowledge) if knowledge is not None
                  else printout.get("own_prizes"))
    own_prizes = None if raw_prizes is None else tuple(
        sorted((int(card_id), int(count)) for card_id, count in raw_prizes.items()
               if card_id is not None and count is not None))
    known_top = canon(_known_top(knowledge) if knowledge is not None
                      else printout.get("known_top"))
    attack_locks = canon(_attack_locks(build, printout) or ())
    values = (own_prizes, known_top, attack_locks)
    build.reuse(("extras",), values)
    return values


def _attack_locks(build: _Build, printout):
    """The lock ledger folds here, not upstream: an enriched printout's own ledger is
    authoritative, else the parent's carries over; the log delta then stamps new locks."""
    prior = None if build.knowledge is not None else printout.get("attack_locks")
    if build.knowledge is not None:
        known = build.knowledge.attack_locks
        prior = ({serial: dict(rows) for serial, rows in known.locks}
                 if isinstance(known, KnownAttackLocks) else {})
    if prior is None and build.parent is not None:
        parent_locks = build.parent.knowledge.attack_locks
        prior = ({serial: dict(rows) for serial, rows in parent_locks.locks}
                 if isinstance(parent_locks, KnownAttackLocks) else {})
    locks = fold_attack_locks(prior, printout.get("logs"),
                              turn=int((printout.get("current") or {}).get("turn") or 0))
    return locks or None


def _deck_counts(build: _Build, decklist, seat, me: Side, stadium, own_prizes):
    """`decklist - own visible - own prizes`, reused whenever no contributing piece changed."""
    if decklist is None:
        return None
    parent = build.parent
    if (parent is not None and parent.decklist == decklist
            and not (build.changed & _DECK_PIECES)):
        return parent.deck_counts
    return _remaining_deck_counts(decklist, seat, me, stadium, own_prizes)


def _remaining_deck_counts(decklist, seat, me: Side, stadium, own_prizes):
    if decklist is None:
        return None
    remaining = Counter(decklist)
    visible_hand = me.hand if isinstance(me.hand, VisibleHand) else ()
    for card in tuple(visible_hand) + tuple(me.discard):
        remaining[card.card_id] -= 1
    for body in me.bodies:
        remaining[body.card.card_id] -= 1
        for card in body.pre_evolution + body.energy_cards + body.tools:
            remaining[card.card_id] -= 1
    for card in stadium:
        # A missing owner stamp is the root viewer's card in both provider dialects.
        if card.owner is None or int(card.owner) == seat:
            remaining[card.card_id] -= 1
    for card_id, count in own_prizes or ():
        remaining[card_id] -= count
    return tuple(sorted((card_id, count) for card_id, count in remaining.items() if count > 0))


def _events(logs) -> tuple[ObservationEvent, ...]:
    events = []
    for row in logs or ():
        if not isinstance(row, dict):
            events.append(ObservationEvent(None, (), False))
            continue
        kind = row.get("type")
        kind = int(kind) if kind is not None else None
        recognized = kind is not None and 0 <= kind <= 23
        fields = tuple((str(key), value) for key, value in sorted(row.items())
                       if key in _EVENT_FIELDS
                       and (value is None or isinstance(value, (bool, int, float, str))))
        event_type = ({15: AttackEvent, 6: MoveCardEvent, 7: MoveCardEvent,
                       4: DrawEvent, 5: DrawEvent, 0: ShuffleEvent}.get(
            kind, KnownObservationEvent) if recognized else UnknownObservationEvent)
        events.append(event_type(kind, fields, recognized))
    return tuple(events)


def _observation_events(build: _Build, logs) -> tuple[ObservationEvent, ...]:
    events = _events(logs)
    identity = tuple((event.kind, event.public_fields, event.recognized) for event in events)
    if build.reuse(("events",), identity):
        return build.parent.events
    return events


def _known_top_ids(known_top) -> tuple:
    return tuple(row[1] if isinstance(row, tuple) and len(row) > 1 else row
                 for row in known_top or ())


def _semantic_locks(state: ObservationState) -> tuple:
    knowledge = state.knowledge.attack_locks
    locks = ({str(serial): rows for serial, rows in knowledge.locks}
             if isinstance(knowledge, KnownAttackLocks) else {})
    bodies = tuple(state.me.bodies) + tuple(state.them.bodies)
    return tuple(sorted((body.digest, locks.get(str(body.card.serial), ())) for body in bodies))


def _known_prizes(knowledge: LegalKnowledge):
    value = knowledge.own_prizes
    return dict(value.cards) if isinstance(value, KnownOwnPrizes) else None


def _known_top(knowledge: LegalKnowledge):
    value = knowledge.known_top
    return value.cards if isinstance(value, KnownDeckTop) else None


def _knowledge_key(knowledge: LegalKnowledge) -> tuple:
    prizes = knowledge.own_prizes
    top = knowledge.known_top
    locks = knowledge.attack_locks
    return (
        ("known", prizes.cards) if isinstance(prizes, KnownOwnPrizes) else ("unknown",),
        ("known", _known_top_ids(top.cards)) if isinstance(top, KnownDeckTop) else ("unknown",),
        ("known",) if isinstance(locks, KnownAttackLocks) else ("unknown",),
    )


def _side_identity(side: Side) -> tuple:
    hand = (("hidden", side.hand.count) if isinstance(side.hand, HiddenHand)
            else ("visible", side.hand.counts))
    return (
        (side.active_hidden, None if side.active is None else side.active.digest),
        tuple(sorted(body.digest for body in side.bench)), hand, side.discard.counts,
        side.bench_max, side.deck_count, side.hand_count, side.prize_count,
        side.poisoned, side.burned, side.asleep, side.paralyzed, side.confused,
    )


def _looking_identity(looking: Looking | None):
    if looking is None:
        return None
    return (looking.count, None if looking.cards is None
            else tuple(sorted(card.card_id for card in looking.cards)))


def _delta_parts(changed, parent, state: ObservationState) -> tuple[tuple[str, ...], ...]:
    parts = set(changed)
    if parent is not None:
        for side_name in (ME, THEM):
            if (side_name, "bench") not in changed:
                continue
            before = Counter(body.digest for body in parent.side(side_name).bench)
            after = Counter(body.digest for body in state.side(side_name).bench)
            for body_digest in (before - after) + (after - before):
                parts.add((side_name, "bench", "body", body_digest.hex()))
        if ("extras",) in parts:
            parts.remove(("extras",))
            if parent.knowledge.own_prizes != state.knowledge.own_prizes:
                parts.add(("knowledge", "own_prizes"))
            if parent.knowledge.known_top != state.knowledge.known_top:
                parts.add(("knowledge", "deck_top"))
            if parent.knowledge.attack_locks != state.knowledge.attack_locks:
                parts.add(("knowledge", "attack_locks"))
        if parent.knowledge.opponent != state.knowledge.opponent:
            parts.add(("knowledge", "opponent_belief"))
        if parent.legal_actions != state.legal_actions:
            parts.add(("legal_actions",))
    return tuple(sorted(parts))


__all__ = ("AttackEvent", "DrawEvent", "KnownObservationEvent", "ME", "MoveCardEvent",
           "ObservationConstructionError", "ObservationDelta", "ObservationEvent",
           "ObservationState", "ObservationStateBuilder", "SCHEMA_VERSION",
           "ShuffleEvent", "THEM", "UnknownObservationEvent")
