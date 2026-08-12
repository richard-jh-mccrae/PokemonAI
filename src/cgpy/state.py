"""cgpy game state: zones, in-play stacks, per-seat log outboxes, select plumbing (ADR-0059).

Everything is plain data — no closures or generators — so `clone()` can be a straight deepcopy.
Deck lists are bottom-first: THE TOP OF THE DECK IS THE LIST END. Log visibility is decided per
call site, not centrally, matching native behavior.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from .cards import CardDB
from .schema import AreaType, LogType

SERIAL_BASE = (3, 63)  # pinned: seat 0 serials 3..62, seat 1 63..122


@dataclass
class CardInstance:
    serial: int
    card_id: int
    owner: int


@dataclass
class PokemonInPlay:
    stack: list[int] = field(default_factory=list)   # serials, bottom-first; top = stack[-1]
    energy: list[int] = field(default_factory=list)  # attached energy card serials, attach order
    tools: list[int] = field(default_factory=list)
    hp: int = 0
    max_hp: int = 0
    entered_turn: int = 1  # setup counts as turn 1; appearThisTurn renders as entered_turn >= the current turn
    ability_used_turn: int = -1
    attack_locks: dict = field(default_factory=dict)  # attackId(str) -> global turn locked
    moved_active_turn: int = -1   # the turn it moved bench -> active
    retreat_lock_turn: int = -1   # global turn this mon cannot RETREAT (lockDefenderRetreat)
    take_less_turn: int = -1      # the global turn the "takes N less damage" transient applies
    take_less: int = 0
    protect_turn: int = -1        # the global turn the Dig-family prevent-all transient applies
    outgoing_less_turn: int = -1  # the global turn this mon's own attacks do N less, pre-W/R
    outgoing_less: int = 0
    no_attack_turn: int = -1      # the global turn this mon cannot attack (menu-enforced)
    attack_gate_turn: int = -1    # the global turn this mon's attacks need a heads first
    no_weakness_turn: int = -1    # the global turn this mon has no Weakness

    @property
    def top(self) -> int:
        return self.stack[-1]


@dataclass
class PlayerBoard:
    deck: list[int] = field(default_factory=list)      # bottom-first; top = end
    hand: list[int] = field(default_factory=list)
    discard: list[int] = field(default_factory=list)
    prize: list[int] = field(default_factory=list)     # bottom-first, 6 at setup
    active: PokemonInPlay | None = None
    active_facedown: bool = False
    bench: list[PokemonInPlay] = field(default_factory=list)
    bench_max: int = 5
    # Special conditions (Active only). poison/burn are markers; sleep/paralyze/confuse rotate.
    poisoned: bool = False
    burned: bool = False
    asleep: bool = False
    paralyzed: bool = False
    confused: bool = False
    paralyzed_since_turn: int = -1   # for auto-recovery after the owner's next turn
    mulligans: int = 0
    mulligan_asked: bool = False
    items_locked_turn: int = -1  # the global turn this seat cannot play ITEM cards


@dataclass
class EffectFrame:
    """A resumable chain-program frame: plain data only (clone-safe)."""
    program: list
    pc: int
    vars: dict
    seat: int
    source: int            # serial of the card whose effect runs (renders SelectData.effect)
    kind: str = "play"     # play | ability | attack


@dataclass
class PendingSelect:
    seat: int
    type: int
    context: int
    min_count: int
    max_count: int
    options: list[dict]
    remain_damage_counter: int = 0
    remain_energy_cost: int = 0
    deck_listing: list[int] | None = None   # serials, when the select reveals the deck
    context_card: int | None = None
    effect_card: int | None = None


@dataclass
class GameState:
    db: CardDB
    cards: dict[int, CardInstance]
    players: list[PlayerBoard]
    rng: Any
    turn: int = 0
    turn_action_count: int = 0
    first_player: int = -1
    supporter_played: bool = False
    stadium_played: bool = False
    energy_attached: bool = False
    retreated: bool = False
    result: int = -1
    result_reason: int = 0
    stadium: list[int] = field(default_factory=list)
    turn_markers: dict = field(default_factory=dict)   # this-turn effects, cleared at begin_turn
    ko_turn: list[int] = field(default_factory=lambda: [-1, -1])  # per-seat: turn a KO was suffered
    attach_seq: dict[int, int] = field(default_factory=dict)  # energy serial -> attach tick
    attach_tick: int = 0
    looking: list[int] | None = None
    looking_owner: int = -1
    pending: PendingSelect | None = None
    frames: list = field(default_factory=list)
    pending_triggers: list = field(default_factory=list)
    last_posed: tuple[int, int, int, int] = (0, 0, 1, 1)   # (seat, context, min, max)
                                                           # of the last posed select
    outbox: list[list[dict]] = field(default_factory=lambda: [[], []])
    outbox_god: list[dict] = field(default_factory=list)   # full-visible stream (visualize)
    phase: str = "IS_FIRST"
    phase_data: dict = field(default_factory=dict)
    manual_coin: bool = False

    # ---------------------------------------------------------------- construction

    @classmethod
    def start(cls, db: CardDB, deck0: list[int], deck1: list[int], rng) -> "GameState":
        cards: dict[int, CardInstance] = {}
        players = []
        for seat, deck in enumerate((deck0, deck1)):
            board = PlayerBoard()
            for i, cid in enumerate(deck):
                serial = SERIAL_BASE[seat] + i
                cards[serial] = CardInstance(serial=serial, card_id=cid, owner=seat)
                board.deck.append(serial)
            players.append(board)
        return cls(db=db, cards=cards, players=players, rng=rng)

    def clone(self) -> "GameState":
        def pokemon(body: PokemonInPlay | None) -> PokemonInPlay | None:
            if body is None:
                return None
            result = copy.copy(body)
            result.stack = list(body.stack)
            result.energy = list(body.energy)
            result.tools = list(body.tools)
            result.attack_locks = dict(body.attack_locks)
            return result

        def board(source: PlayerBoard) -> PlayerBoard:
            result = copy.copy(source)
            result.deck = list(source.deck)
            result.hand = list(source.hand)
            result.discard = list(source.discard)
            result.prize = list(source.prize)
            result.active = pokemon(source.active)
            result.bench = [pokemon(body) for body in source.bench]
            return result

        twin = copy.copy(self)
        twin.players = [board(source) for source in self.players]
        twin.stadium = list(self.stadium)
        twin.turn_markers = copy.deepcopy(self.turn_markers)
        twin.ko_turn = list(self.ko_turn)
        twin.attach_seq = dict(self.attach_seq)
        twin.looking = None if self.looking is None else list(self.looking)
        twin.pending = (None if self.pending is None else PendingSelect(
            seat=self.pending.seat, type=self.pending.type, context=self.pending.context,
            min_count=self.pending.min_count, max_count=self.pending.max_count,
            options=[dict(option) for option in self.pending.options],
            remain_damage_counter=self.pending.remain_damage_counter,
            remain_energy_cost=self.pending.remain_energy_cost,
            deck_listing=(None if self.pending.deck_listing is None
                          else list(self.pending.deck_listing)),
            context_card=self.pending.context_card, effect_card=self.pending.effect_card,
        ))
        twin.frames = [EffectFrame(
            program=frame.program, pc=frame.pc, vars=copy.deepcopy(frame.vars),
            seat=frame.seat, source=frame.source, kind=frame.kind) for frame in self.frames]
        twin.pending_triggers = copy.deepcopy(self.pending_triggers)
        twin.outbox = [[dict(entry) for entry in rows] for rows in self.outbox]
        twin.outbox_god = [dict(entry) for entry in self.outbox_god]
        twin.phase_data = copy.deepcopy(self.phase_data)
        # Card instances and the card database are immutable after construction. The caller that
        # needs independent randomness (Engine.fork) replaces this shared RNG immediately.
        twin.cards = self.cards
        twin.db = self.db
        twin.rng = self.rng
        return twin

    # ---------------------------------------------------------------- helpers

    def card_id(self, serial: int) -> int:
        return self.cards[serial].card_id

    def owner(self, serial: int) -> int:
        return self.cards[serial].owner

    def stat(self, serial: int):
        return self.db.card(self.cards[serial].card_id)

    def in_play(self, seat: int) -> list[PokemonInPlay]:
        b = self.players[seat]
        out = [b.active] if b.active else []
        return out + list(b.bench)

    # ---------------------------------------------------------------- log emission

    def emit(self, entry: dict, *, reverse: dict | None = None,
             actor: int | None = None) -> None:
        """The non-actor seat gets `reverse` instead when given. Entries are FINAL rendered dicts."""
        for seat in (0, 1):
            if reverse is not None and actor is not None and seat != actor:
                self.outbox[seat].append(dict(reverse))
            else:
                self.outbox[seat].append(dict(entry))
        self.outbox_god.append(dict(entry))

    # ---------------------------------------------------------------- zone mutations

    def shuffle_deck(self, seat: int, *, log: bool = True) -> None:
        self.rng.shuffle(self.players[seat].deck, seat=seat)
        if log:
            self.emit({"type": int(LogType.SHUFFLE), "playerIndex": seat})

    def draw(self, seat: int) -> int | None:
        board = self.players[seat]
        if not board.deck:
            return None
        serial = self.rng.draw_bind(seat, board.deck, prize=board.prize)
        board.deck.remove(serial)
        board.hand.append(serial)
        self.emit({"type": int(LogType.DRAW), "playerIndex": seat,
                   "cardId": self.card_id(serial), "serial": serial},
                  reverse={"type": int(LogType.DRAW_REVERSE), "playerIndex": seat},
                  actor=seat)
        return serial

    def move_card(self, serial: int, from_area: int, to_area: int, *,
                  seat: int, visible_to_owner: bool, visible_to_opponent: bool) -> None:
        """Zone lists are mutated by the CALLER, which knows list positions; visibility is per call site."""
        full = {"type": int(LogType.MOVE_CARD), "playerIndex": seat,
                "cardId": self.card_id(serial), "serial": serial,
                "fromArea": int(from_area), "toArea": int(to_area)}
        rev = {"type": int(LogType.MOVE_CARD_REVERSE), "playerIndex": seat,
               "fromArea": int(from_area), "toArea": int(to_area)}
        for viewer in (0, 1):
            visible = visible_to_owner if viewer == seat else visible_to_opponent
            self.outbox[viewer].append(dict(full if visible else rev))
        self.outbox_god.append(dict(full))

    def note_attach(self, serial: int) -> None:
        """Records attach order: energy-discard selects list targets OLDEST-attach-first."""
        self.attach_tick += 1
        self.attach_seq[serial] = self.attach_tick

    def coin_flip(self, seat: int) -> bool:
        try:
            head = self.rng.coin(seat=seat)   # replay binds per-OWNER: a checkup flip belongs to
        except TypeError:                     # the condition's owner, not the frame's mover
            head = self.rng.coin()
        self.emit({"type": int(LogType.COIN), "playerIndex": seat, "head": bool(head)})
        return head

    def set_result(self, result: int, reason: int) -> None:
        from .state import PendingSelect

        self.result = result
        self.result_reason = reason
        self.emit({"type": int(LogType.RESULT), "result": int(result), "reason": int(reason)})
        # The native terminal frame carries a degenerate EMPTY select — type 0, the LAST POSED
        # context and min/max, no options — rather than select=null.
        last_seat, last_ctx, last_min, last_max = self.last_posed
        self.pending = PendingSelect(seat=last_seat, type=0, context=last_ctx,
                                     min_count=last_min, max_count=last_max, options=[])
        self.phase = "DONE"
