"""BoardState: the agent's observable board as reusable typed pieces (ADR-0144).

`root()` builds every piece from one engine reprint; `advance()` C-compares the next reprint
against the raw subtree each parent piece was built from and rebuilds ONLY the unequal pieces,
so hashing, fact-pinning and derived counts are paid where the board changed and nowhere else.
Both engine dialects normalize here. The type is the information boundary: an opponent's hand
contents or any deck order cannot be represented, only counted. Reprints are treated as frozen;
a caller that mutates one after building from it forfeits the reuse guarantee."""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from functools import cached_property

from common.cards import card_store
from common.cards.functions.attack_lock import fold_attack_locks

from .nodes import (
    Body, Card, CardBag, Looking, SelectPrompt, Side, Turn, active_node, body_node, canon,
    card_bag, card_tuple, digest, feed, looking_node, select_node, turn_node)

ME, THEM = "me", "them"
_SIDE_PIECES = ("active", "bench", "hand", "discard", "scalars")
#: Every piece label, in the fixed order `key` combines their digests.
PIECES = (tuple((side, piece) for side in (ME, THEM) for piece in _SIDE_PIECES)
          + (("turn",), ("stadium",), ("looking",), ("select",), ("extras",)))
#: The pieces whose change can move my remaining-deck arithmetic.
_DECK_PIECES = frozenset({(ME, "active"), (ME, "bench"), (ME, "hand"), (ME, "discard"),
                          ("stadium",), ("extras",)})
KEY_BYTES = 32


@dataclass(frozen=True)
class BoardState:
    """One decision point's observable board; build via `root`, derive via `advance`."""

    seat: int
    me: Side
    them: Side
    turn: Turn
    stadium: tuple[Card, ...]
    looking: Looking | None
    select: SelectPrompt | None
    #: MY face-down prize multiset, once the deck tracker anchors it; opponent prizes stay a count.
    own_prizes: tuple[tuple[int, int], ...] | None
    #: Ordered (serial, card id) belief about MY deck's top from stacking effects; None = unknown.
    known_top: tuple | None
    #: Self-locked attacks by body serial, folded from each step's log delta (never mutates input).
    attack_locks: tuple | None
    decklist: tuple[int, ...] | None
    #: MY unseen pool by card id — exact deck once `own_prizes` anchors, deck∪prizes before it.
    deck_counts: tuple[tuple[int, int], ...] | None
    changed: frozenset = field(compare=False)
    raw: dict = field(compare=False, repr=False)
    digests: dict = field(compare=False, repr=False)

    @classmethod
    def root(cls, printout, *, decklist=None) -> "BoardState":
        current = printout.get("current") or {}
        seat = int(current.get("yourIndex") or 0)
        deck = None if decklist is None else tuple(int(card_id) for card_id in decklist)
        return _build(cls, printout, seat, deck, None)

    def advance(self, printout) -> "BoardState":
        # The viewer is pinned at root: every in-search reprint renders the same seat's view.
        return _build(type(self), printout, self.seat, self.decklist, self)

    def side(self, name: str) -> Side:
        return self.me if name == ME else self.them

    @cached_property
    def key(self) -> str:
        hasher = hashlib.blake2b(digest_size=KEY_BYTES)
        feed(hasher.update, self.seat)
        # Deck knowledge is position identity: the same pieces under another decklist must differ.
        feed(hasher.update, self.deck_counts)
        for label in PIECES:
            feed(hasher.update, self.digests[label])
        return hasher.hexdigest()


class _Build:
    """One root/advance pass: piece bookkeeping shared by every zone builder below."""

    def __init__(self, printout, seat, parent):
        self.printout, self.seat, self.parent = printout, seat, parent
        self.store = card_store()
        self.raw: dict = {}
        self.digests: dict = {}
        self.changed: set = set()

    def reuse(self, label, raw_value) -> bool:
        """Record the piece's new raw subtree; True when the parent's piece survives as-is."""
        self.raw[label] = raw_value
        parent = self.parent
        if parent is not None and label in parent.raw and parent.raw[label] == raw_value:
            self.digests[label] = parent.digests[label]
            return True
        self.changed.add(label)
        return False

    def keep(self, label, node, piece_digest: bytes):
        self.digests[label] = piece_digest
        return node


def _build(cls, printout, seat, decklist, parent) -> BoardState:
    build = _Build(printout, seat, parent)
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
    deck_counts = _deck_counts(build, decklist, seat, me, stadium, own_prizes)
    return cls(seat, me, them, turn, stadium, looking, select, own_prizes, known_top,
               attack_locks, decklist, deck_counts, frozenset(build.changed), build.raw,
               build.digests)


def _side(build: _Build, prefix: str, raw_player, parent_side: Side | None, *, own: bool) -> Side:
    label = (prefix, "active")
    if build.reuse(label, raw_player.get("active")):
        active, hidden = parent_side.active, parent_side.active_hidden
    else:
        active, hidden = active_node(raw_player.get("active"), build.store)
        build.keep(label, active, digest(hidden, None if active is None else active.digest))

    label = (prefix, "bench")
    if build.reuse(label, raw_player.get("bench")):
        bench = parent_side.bench
    else:
        bench = _bench(build, label, raw_player.get("bench"), parent_side)
        build.keep(label, bench, digest(tuple(sorted(body.digest for body in bench))))

    # The boundary: an opponent's hand contents are never read, even off a full-truth frame.
    raw_hand = raw_player.get("hand") if own else None
    label = (prefix, "hand")
    if build.reuse(label, raw_hand):
        hand = parent_side.hand
    else:
        hand = None if raw_hand is None else card_bag(raw_hand, build.store)
        build.keep(label, hand, digest(None) if hand is None else hand.digest)

    label = (prefix, "discard")
    if build.reuse(label, raw_player.get("discard")):
        discard = parent_side.discard
    else:
        discard = card_bag(raw_player.get("discard"), build.store)
        build.keep(label, discard, discard.digest)

    raw_hand_count = raw_player.get("handCount")
    scalars = (int(raw_player.get("benchMax") or 5), int(raw_player.get("deckCount") or 0),
               int(raw_hand_count if raw_hand_count is not None else len(raw_hand or ())),
               len(raw_player.get("prize") or ()), bool(raw_player.get("poisoned")),
               bool(raw_player.get("burned")), bool(raw_player.get("asleep")),
               bool(raw_player.get("paralyzed")), bool(raw_player.get("confused")))
    label = (prefix, "scalars")
    if not build.reuse(label, scalars):
        build.keep(label, scalars, digest(scalars))

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
        parent_raw = build.parent.raw.get(label) or ()
        # Empty entries never became nodes, so drop them on both sides to keep the zip aligned.
        for raw_body, node in zip((entry for entry in parent_raw if entry), parent_side.bench):
            survivors.setdefault(raw_body.get("serial"), []).append((raw_body, node))
    bench = []
    for entry in raw_bench or ():
        if not entry:
            continue
        node = next((old for raw_old, old in survivors.get(entry.get("serial"), ())
                     if raw_old == entry), None)
        node = node if node is not None else body_node(entry, build.store)
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
    return build.keep(("turn",), node, digest(node.scalars()))


def _stadium(build: _Build, current) -> tuple[Card, ...]:
    if build.reuse(("stadium",), current.get("stadium")):
        return build.parent.stadium
    cards = card_tuple(current.get("stadium"), build.store)
    return build.keep(("stadium",), cards,
                      digest(tuple(sorted(card.card_id for card in cards))))


def _looking(build: _Build, current) -> Looking | None:
    if build.reuse(("looking",), current.get("looking")):
        return build.parent.looking
    node = looking_node(current.get("looking"), build.store)
    ids = None if node is None or node.cards is None else \
        tuple(sorted(card.card_id for card in node.cards))
    return build.keep(("looking",), node,
                      digest(None if node is None else (node.count, ids)))


def _select(build: _Build, printout) -> SelectPrompt | None:
    if build.reuse(("select",), printout.get("select")):
        return build.parent.select
    node = select_node(printout.get("select"), build.store)
    return build.keep(("select",), node, digest(None if node is None else node.identity()))


def _extras(build: _Build, printout):
    raw_prizes = printout.get("own_prizes")
    own_prizes = None if raw_prizes is None else tuple(
        sorted((int(card_id), int(count)) for card_id, count in raw_prizes.items()))
    known_top = canon(printout.get("known_top"))
    attack_locks = canon(_attack_locks(build, printout))
    values = (own_prizes, known_top, attack_locks)
    if not build.reuse(("extras",), values):
        build.keep(("extras",), values, digest(values))
    return values


def _attack_locks(build: _Build, printout):
    """The lock ledger folds here, not upstream: an enriched printout's own ledger is
    authoritative, else the parent's carries over; the log delta then stamps new locks."""
    prior = printout.get("attack_locks")
    if prior is None and build.parent is not None:
        prior = {serial: dict(rows) for serial, rows in build.parent.attack_locks or ()}
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
    remaining = Counter(decklist)
    for card in tuple(me.hand or ()) + tuple(me.discard):
        remaining[card.card_id] -= 1
    for body in me.bodies:
        remaining[body.card.card_id] -= 1
        for card in body.pre_evolution + body.energy_cards + body.tools:
            remaining[card.card_id] -= 1
    for card in stadium:
        # A stadium card missing its owner stamp counts as mine — `common.state`'s reading.
        if card.owner is None or int(card.owner) == seat:
            remaining[card.card_id] -= 1
    for card_id, count in own_prizes or ():
        remaining[card_id] -= count
    return tuple(sorted((card_id, count) for card_id, count in remaining.items() if count > 0))


__all__ = ("BoardState", "ME", "PIECES", "THEM")
