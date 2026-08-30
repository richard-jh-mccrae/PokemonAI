"""Randomness sources for cgpy (ADR-0059). The native engine is unseedable, so cgpy owns its own.

`ReplayRandomness` RAISES when asked for anything the trace does not record, so a replay can never
silently absorb divergence. Manual-coin is an Engine flag, not an Rng: flips become COIN_HEAD selects.
"""
from __future__ import annotations

import random


class SeededRng:
    """Deck shuffles + coin flips from one seeded stream."""

    def __init__(self, seed: int | None = None):
        self._r = random.Random(seed)

    def export_state(self) -> tuple:
        return self._r.getstate()

    @classmethod
    def from_state(cls, state: tuple) -> "SeededRng":
        result = cls(0)
        result._r.setstate(state)
        return result

    def shuffle(self, seq: list, *, seat: int) -> None:
        self._r.shuffle(seq)

    def coin(self, seat: int | None = None) -> bool:
        return self._r.random() < 0.5

    def draw_bind(self, seat: int, deck: list[int],
                  *, prize: list[int] | None = None) -> int:
        """Which serial the next draw takes: the deck top (list end)."""
        return deck[-1]

    def prize_bind(self, seat: int, deck: list[int], count: int) -> list[int]:
        """Which serials the facedown prize deal takes: the top `count` cards."""
        return [deck[-(i + 1)] for i in range(count)]

    def hand_pick(self, seat: int, hand: list[int]) -> int:
        """Which serial a random pick from ``seat``'s hand takes (Psych Out family)."""
        return hand[self._r.randrange(len(hand))]

    def hand_pick_expect(self, seat: int, serials: list[int]) -> None:
        """Known-identity forced hand exits: nothing to bind in seeded play."""

    def look_bind(self, seat: int, deck: list[int], n: int,
                  *, from_bottom: bool = False) -> list[int]:
        """Which serials a look-at-deck reveal takes, in take order: positional
        (top = list end, bottom = list start)."""
        return list(deck[:n]) if from_bottom else [deck[-1 - i] for i in range(n)]

    def mill_bind(self, seat: int, deck: list[int], prize: list[int],
                  n: int) -> list[int]:
        """Which serials a top-of-deck mill discards, in discard order (top = list
        end). Seeded play: positional."""
        return [deck[-(i + 1)] for i in range(min(n, len(deck)))]


class ReplayError(AssertionError):
    """A replay asked for randomness the trace does not determine — a real divergence."""


class ReplayRandomness:
    """Binds every random outcome from a recorded native game, fed per-frame by the replayer. Draws
    consume the recorded identity WHEREVER it sits in the deck, multiset-checked."""

    def __init__(self):
        self.draw_queues: dict[int, list[int]] = {0: [], 1: []}
        self.coin_queue: list[bool] = []
        self.shuffle_orders: dict[int, list[list[int]]] = {0: [], 1: []}
        self.prize_feed: dict[int, list[int]] = {0: [], 1: []}
        self.prize_take_queue: dict[int, list[int]] = {0: [], 1: []}   # god-free path
        # Per-victim FIFO of forced hand exits during the OPPONENT's turn. Consumed by BOTH
        # hand_pick and hand_pick_expect, or the queue skews (the M4 alignment hazard).
        self.hand_pick_queue: dict[int, list[int]] = {0: [], 1: []}
        # The replayer pre-feeds the NEXT frame's recorded DECK->LOOKING serials; a look consumes
        # them in RECORDED order regardless of which end of the deck it reads.
        self.look_feed: dict[int, list[int]] = {0: [], 1: []}
        # The NEXT frame's recorded DECK->DISCARD serials in discard order; a provisionally
        # prize-parked one swaps back into the deck.
        self.mill_feed: dict[int, list[int]] = {0: [], 1: []}

    def shuffle(self, seq: list, *, seat: int) -> None:
        if self.shuffle_orders[seat]:
            order = self.shuffle_orders[seat].pop(0)
            if sorted(order) != sorted(seq):
                raise ReplayError(
                    f"seat {seat}: recorded shuffle order is a different multiset "
                    f"(recorded {len(order)} vs live {len(seq)})")
            seq[:] = order
        # else: leave order as-is; subsequent draws bind identities explicitly.

    def coin(self, seat: int | None = None) -> bool:
        if not self.coin_queue:
            raise ReplayError("coin flip requested but no recorded COIN outcome remains")
        return self.coin_queue.pop(0)

    def draw_bind(self, seat: int, deck: list[int],
                  *, prize: list[int] | None = None) -> int:
        if not self.draw_queues[seat]:
            raise ReplayError(f"seat {seat}: draw requested but no recorded DRAW remains")
        serial = self.draw_queues[seat].pop(0)
        if serial not in deck:
            # The DRAW proves this serial is really in the deck, so a provisional prize deal must
            # have parked it; exchange with the deck top to keep BOTH zones multiset-exact.
            if prize is not None and serial in prize and deck:
                prize[prize.index(serial)] = deck[-1]
                deck[-1] = serial
            else:
                raise ReplayError(
                    f"seat {seat}: recorded draw serial {serial} not in deck")
        return serial

    def prize_bind(self, seat: int, deck: list[int], count: int) -> list[int]:
        if len(self.prize_feed[seat]) >= count:          # god path: identities known
            serials = [self.prize_feed[seat].pop(0) for _ in range(count)]
            missing = [s for s in serials if s not in deck]
            if missing:
                raise ReplayError(
                    f"seat {seat}: recorded prize serials {missing} not in deck")
            return serials
        # God-free path: PROVISIONAL identities; the true one binds at take time via `prize_take`,
        # with a multiset-preserving swap.
        return [deck[-(i + 1)] for i in range(count)]

    def hand_pick(self, seat: int, hand: list[int]) -> int:
        q = self.hand_pick_queue[seat]
        if not q:
            raise ReplayError(
                f"seat {seat}: random hand pick requested but no recorded forced hand "
                f"exit remains")
        serial = q.pop(0)
        if serial not in hand:
            raise ReplayError(
                f"seat {seat}: recorded hand pick {serial} not in hand {hand}")
        return serial

    def hand_pick_expect(self, seat: int, serials: list[int]) -> None:
        """Drain the FIFO through a known-identity forced exit: one pop per moved card, popped set
        must match. An EMPTY queue skips silently; a partial or mismatched pop is a real skew."""
        q = self.hand_pick_queue[seat]
        if not q:
            return
        expected = list(serials)
        for _ in serials:
            if not q:
                raise ReplayError(
                    f"seat {seat}: forced hand exit of {len(serials)} cards but only "
                    f"{len(serials) - len(expected)} recorded picks remained")
            got = q.pop(0)
            if got not in expected:
                raise ReplayError(
                    f"seat {seat}: recorded forced hand exit {got} not among the "
                    f"cards this effect moves {expected}")
            expected.remove(got)

    def look_bind(self, seat: int, deck: list[int], n: int,
                  *, from_bottom: bool = False) -> list[int]:
        """Look-reveal identities: consume the pre-fed recorded serials (in recorded
        order — direction-agnostic), positional for any unfed remainder."""
        feed = self.look_feed.get(seat) or []
        out: list[int] = []
        while feed and len(out) < n:
            s = feed.pop(0)
            if s not in deck:
                raise ReplayError(
                    f"seat {seat}: recorded look serial {s} not in deck")
            out.append(s)
        if len(out) < n:
            rest = [s for s in (deck[:n] if from_bottom
                                else [deck[-1 - i] for i in range(n)])
                    if s not in out]
            out += rest[:n - len(out)]
        return out

    def mill_bind(self, seat: int, deck: list[int], prize: list[int],
                  n: int) -> list[int]:
        """Which serials a top-of-deck mill discards, in DISCARD order: the pre-fed recorded ones
        (a prize-parked serial swaps back, like draw_bind), then positional for any remainder."""
        feed = self.mill_feed.get(seat) or []
        out: list[int] = []
        for _ in range(min(n, len(deck))):
            if feed:
                s = feed.pop(0)
                if s not in deck:
                    if prize is not None and s in prize:
                        filler = next(d for d in reversed(deck) if d not in out)
                        prize[prize.index(s)] = filler
                        deck[deck.index(filler)] = s
                    else:
                        raise ReplayError(
                            f"seat {seat}: recorded mill serial {s} is in neither "
                            f"the deck nor the prize row")
                out.append(s)
            else:
                out.append(next(d for d in reversed(deck) if d not in out))
        return out

    def prize_take(self, seat: int, serial: int, *, deck: list[int],
                   prize: list[int]) -> int:
        """The RECORDED serial for this take. One provisionally in the deck exchanges with the
        `serial` occupant so both zones stay multiset-exact. No queue = god-path replay."""
        q = self.prize_take_queue.get(seat)
        if not q:
            return serial
        recorded = q.pop(0)
        if recorded in prize:
            return recorded
        if recorded in deck:
            deck[deck.index(recorded)] = serial
            prize[prize.index(serial)] = recorded
            return recorded
        raise ReplayError(
            f"seat {seat}: recorded prize take {recorded} is in neither the deck "
            f"nor the prize row — a real divergence")
