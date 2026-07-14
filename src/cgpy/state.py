"""cgpy game state: zones, in-play stacks, per-seat log outboxes, select plumbing (ADR-0059).

Everything is plain data (no closures/generators), so `clone()` is a straight deepcopy — the
property the verification API (M3) needs. Serials follow the pinned native scheme: seat 0's
submitted position i -> serial 3+i, seat 1 -> 63+i (docs/pyeng/determinism.md §1). Deck lists
are bottom-first: THE TOP OF THE DECK IS THE LIST END (§ deck-top pin).

Log emission happens at the mutation sites via `emit()`, which appends the viewer-correct
rendering (full vs REVERSE) to each seat's outbox; `render.py` drains an outbox when that seat
receives a select. Visibility is decided per call site (e.g. a mulligan hand returns to deck
revealed, an effect shuffle-in does not), matching observed native behavior.
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
    entered_turn: int = 1   # turn number it entered play / evolved (setup counts as turn 1);
                            # appearThisTurn renders as entered_turn >= current turn (pinned)
    ability_used_turn: int = -1   # once-per-turn activated-ability gate
    attack_locks: dict = field(default_factory=dict)  # attackId(str) -> global turn locked
    moved_active_turn: int = -1   # turn it moved bench->active (switch/promotion) — the
                                  # "moved from your Bench to the Active Spot this turn" cond
    retreat_lock_turn: int = -1   # global turn this mon cannot RETREAT (lockDefenderRetreat)
    take_less_turn: int = -1      # "takes N less damage" transient: the global turn it
    take_less: int = 0            # applies (the attacker's turn after the granting attack)
    protect_turn: int = -1        # Dig-family "prevent all damage from and effects of
                                  # attacks" transient: the global turn it applies
    outgoing_less_turn: int = -1  # Intimidating-Stare transient on the DEFENDING mon:
    outgoing_less: int = 0        # its attacks do N less (pre-W/R) on this global turn
    no_attack_turn: int = -1      # Snotted-Up transient: this mon can't attack on this
                                  # global turn (menu-enforced, like sleep/paralysis)
    attack_gate_turn: int = -1    # Sand-Attack transient: on this global turn, this
                                  # mon's attacks need a heads first (tails = nothing)
    no_weakness_turn: int = -1    # Metal-Defender transient: on this global turn,
                                  # this mon has no Weakness

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
    items_locked_turn: int = -1   # Itchy-Pollen class: the global turn this seat cannot
                                  # play ITEM cards ("During your opponent's next turn,
                                  # they can't play any Item cards from their hand")


@dataclass
class EffectFrame:
    """A resumable chain-program frame: plain data only (clone-safe)."""
    program: list          # list of op dicts
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
    context_card: int | None = None         # serial
    effect_card: int | None = None          # serial


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
    attach_tick: int = 0        # energy-discard selects list targets in global attach order
    looking: list[int] | None = None
    looking_owner: int = -1
    pending: PendingSelect | None = None
    frames: list = field(default_factory=list)   # EffectFrame stack (chain programs)
    pending_triggers: list = field(default_factory=list)  # queued bench/evolve triggers
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
        rng, db = self.rng, self.db
        self.rng = self.db = None      # db is an immutable table (frozen dataclasses,
        try:                           # lru_cache-shared already) — never deep-copied
            twin = copy.deepcopy(self)
        finally:
            self.rng, self.db = rng, db
        twin.rng = rng   # shared rng: forks that need independence pass their own
        twin.db = db
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
        """Append `entry` to every seat's outbox; the non-actor seat gets `reverse` instead
        when given. Entries are final rendered dicts (sparse keys, int enums)."""
        for seat in (0, 1):
            if reverse is not None and actor is not None and seat != actor:
                self.outbox[seat].append(dict(reverse))
            else:
                self.outbox[seat].append(dict(entry))
        self.outbox_god.append(dict(entry))   # god view always sees the full entry

    # ---------------------------------------------------------------- zone mutations

    def shuffle_deck(self, seat: int, *, log: bool = True) -> None:
        self.rng.shuffle(self.players[seat].deck, seat=seat)
        if log:
            self.emit({"type": int(LogType.SHUFFLE), "playerIndex": seat})

    def draw(self, seat: int) -> int | None:
        """Draw the top deck card into the hand (owner sees ids, opponent sees DRAW_REVERSE)."""
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
        """Emit the MOVE_CARD/_REVERSE pair for a card movement (zone lists are mutated by
        the caller, which knows list positions); visibility is per call site."""
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
        """Record energy-attach order (Crushing Hammer-class selects list the opponent's
        energies oldest-attach-first, pinned ml_dx_2001 f175 / ml_dx_2000 f95)."""
        self.attach_tick += 1
        self.attach_seq[serial] = self.attach_tick

    def coin_flip(self, seat: int) -> bool:
        try:
            head = self.rng.coin(seat=seat)   # replay binds per-OWNER (checkup flips
        except TypeError:                     # belong to the condition owner, not the
            head = self.rng.coin()            # frame's mover — pinned collapse_9740 f17)
        self.emit({"type": int(LogType.COIN), "playerIndex": seat, "head": bool(head)})
        return head

    def set_result(self, result: int, reason: int) -> None:
        from .state import PendingSelect  # local import keeps dataclass order simple

        self.result = result
        self.result_reason = reason
        self.emit({"type": int(LogType.RESULT), "result": int(result), "reason": int(reason)})
        # The native terminal frame carries a degenerate EMPTY select (type 0, the last
        # posed context AND min/max, no options) rather than select=null — pinned
        # (v2_ms_mirror_5000 f147: min/max 2 after a 2-prize pick).
        last_seat, last_ctx, last_min, last_max = self.last_posed
        self.pending = PendingSelect(seat=last_seat, type=0, context=last_ctx,
                                     min_count=last_min, max_count=last_max, options=[])
        self.phase = "DONE"
