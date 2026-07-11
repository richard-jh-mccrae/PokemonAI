"""Randomness sources for cgpy (ADR-0050).

The native engine is unseedable; cgpy owns its randomness instead:

- `SeededRng`  — reproducible self-play (a property the native engine never had).
- `ReplayRandomness` — differential replay: shuffles/draw identities/coin outcomes are bound
  from a recorded native trace (reveal-oracle style); asking it for anything unrecorded raises,
  so a replay can never silently absorb divergence.
- manual-coin is an Engine flag, not an Rng: flips surface as COIN_HEAD selects.
"""
from __future__ import annotations

import random


class SeededRng:
    """Deck shuffles + coin flips from one seeded stream."""

    def __init__(self, seed: int | None = None):
        self._r = random.Random(seed)

    def shuffle(self, seq: list, *, seat: int) -> None:
        self._r.shuffle(seq)

    def coin(self, seat: int | None = None) -> bool:
        return self._r.random() < 0.5

    def draw_bind(self, seat: int, deck: list[int]) -> int:
        """Which serial the next draw takes: the deck top (list end)."""
        return deck[-1]

    def prize_bind(self, seat: int, deck: list[int], count: int) -> list[int]:
        """Which serials the facedown prize deal takes: the top `count` cards."""
        return [deck[-(i + 1)] for i in range(count)]


class ReplayError(AssertionError):
    """A replay asked for randomness the trace does not determine — a real divergence."""


class ReplayRandomness:
    """Binds every random outcome from a recorded native game.

    Fed per-frame by the replayer: queues of drawn serials (from the trace's DRAW logs, per
    seat), coin outcomes (COIN logs), and post-shuffle deck orders (god frames). Draws consume
    the recorded identity wherever it sits in the deck (multiset-checked); shuffles adopt the
    recorded order when one is pending, else mark the deck order unknown until the next sync.
    """

    def __init__(self):
        self.draw_queues: dict[int, list[int]] = {0: [], 1: []}
        self.coin_queue: list[bool] = []
        self.shuffle_orders: dict[int, list[list[int]]] = {0: [], 1: []}
        self.prize_feed: dict[int, list[int]] = {0: [], 1: []}
        self.prize_take_queue: dict[int, list[int]] = {0: [], 1: []}   # god-free path

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

    def draw_bind(self, seat: int, deck: list[int]) -> int:
        if not self.draw_queues[seat]:
            raise ReplayError(f"seat {seat}: draw requested but no recorded DRAW remains")
        serial = self.draw_queues[seat].pop(0)
        if serial not in deck:
            raise ReplayError(f"seat {seat}: recorded draw serial {serial} not in deck")
        return serial

    def prize_bind(self, seat: int, deck: list[int], count: int) -> list[int]:
        if len(self.prize_feed[seat]) >= count:          # god path: identities known
            serials = [self.prize_feed[seat].pop(0) for _ in range(count)]
            missing = [s for s in serials if s not in deck]
            if missing:
                raise ReplayError(
                    f"seat {seat}: recorded prize serials {missing} not in deck")
            return serials
        # God-free (cabt) path: deal PROVISIONAL identities (deck top, like the live
        # rule); the true identity binds at take time via `prize_take` (the owner's
        # PRIZE->HAND move log carries the serial) with a multiset-preserving swap.
        return [deck[-(i + 1)] for i in range(count)]

    def prize_take(self, seat: int, serial: int, *, deck: list[int],
                   prize: list[int]) -> int:
        """Resolve a provisional prize identity at take time (reveal-oracle, M4).

        Returns the RECORDED serial for this take. Already in the row: removal by
        identity needs no bookkeeping. Provisionally in the deck: exchange it with the
        `serial` occupant so both zones stay multiset-exact. No queue = god-path replay
        (identities were exact at deal)."""
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
