"""Sampled hands for shuffle-draw supporters, per the supporter-decision handoff.

Never decide from P(draw the wanted card): draw whole hands from the pool the shuffle actually
creates, evaluate each resulting BOARD with the Ledger, and average — combinations matter, and
the demand-aware hand terms are what see them. Drawing without replacement from the real pool
IS the multivariate hypergeometric, so the branch probabilities are exact in distribution;
sampling is seeded from the board's semantic key plus the played card, so a replayed frame
prices identically every time. The opponent's side needs no sampling: their redrawn hand is
priced by count, which is exact under the boundary."""
from __future__ import annotations

import hashlib
import random
from collections import Counter
from dataclasses import replace

from common.observation import ObservationState, UnknownDeckTop, VisibleHand
from common.observation.nodes import Card, CardBag, digest
from common.cards import card_store
from common.cards.card_facts import SUPPORTER

SAMPLE_BUDGET = 24


def refresh_value(board: ObservationState, card_id: int,
                  draws, opponent_shuffles: bool, evaluate_fn):
    """Expected VALUE of the board after playing shuffle-draw supporter `card_id` (absolute,
    not a swing — the preview differences it against its own baseline), plus the gaps met."""
    gaps: list[str] = []
    seat = board.seat
    hand_ids = [card.card_id for card in board.me.hand]
    if int(card_id) in hand_ids:
        hand_ids.remove(int(card_id))
    else:
        gaps.append(f"refresh: played card {int(card_id)} not visible in hand")
    pool: list[int] = list(hand_ids)
    if board.deck_counts is not None:
        for target_id, count in board.deck_counts:
            pool.extend([int(target_id)] * int(count))
    else:
        gaps.append("refresh: own deck contents unknown; sampling hand-only pool")

    rng = random.Random(_seed(board, card_id))
    total, weight = 0.0, 0
    for own_draw, opponent_draw in draws:
        for _ in range(max(1, SAMPLE_BUDGET // max(1, len(draws)))):
            sampled = _sample(rng, pool, int(own_draw))
            synthetic = _synthesize(board, sampled, len(pool) - len(sampled),
                                    int(card_id), int(opponent_draw), opponent_shuffles)
            valuation = evaluate_fn(synthetic)
            gaps.extend(valuation.gaps)
            total += valuation.total
            weight += 1
    return (total / weight if weight else 0.0), tuple(gaps)


def _seed(board: ObservationState, card_id: int) -> int:
    digest = hashlib.blake2b(f"{board.key}:{int(card_id)}".encode("ascii"),
                             digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _sample(rng: random.Random, pool: list, count: int) -> list:
    if count >= len(pool):
        return list(pool)
    return rng.sample(pool, count)


def _bag(cards) -> CardBag:
    cards = tuple(cards)
    counts = tuple(sorted(Counter(card.card_id for card in cards).items()))
    return CardBag(cards, counts, digest(counts))


def _synthesize(board: ObservationState, hand_ids, deck_count: int, played_id: int,
                opponent_draw: int, opponent_shuffles: bool) -> ObservationState:
    seat = board.seat
    hand = VisibleHand(_bag(Card(int(card_id), None, seat) for card_id in hand_ids))
    discard = _bag((*board.me.discard.cards, Card(int(played_id), None, seat)))
    mine = replace(board.me, hand=hand, hand_count=len(hand_ids),
                   deck_count=max(0, int(deck_count)), discard=discard)
    other = board.them
    if opponent_shuffles:
        other_deck = max(0, other.deck_count + other.hand_count - int(opponent_draw))
    else:
        other_deck = max(0, other.deck_count - int(opponent_draw))
    other_hand = int(opponent_draw) if opponent_shuffles else other.hand_count + int(opponent_draw)
    other = replace(other, hand=replace(other.hand, count=other_hand),
                    hand_count=other_hand, deck_count=other_deck)
    supporter = getattr(card_store().get(int(played_id)), "kind", None) == SUPPORTER
    turn = replace(board.turn, supporter_played=board.turn.supporter_played or supporter)
    remaining = Counter(card_id for card_id, count in board.deck_counts or ()
                        for _ in range(count))
    remaining.subtract(hand_ids)
    knowledge = replace(board.knowledge, known_top=UnknownDeckTop())
    return replace(board, me=mine, them=other, turn=turn, select=None, legal_actions=(),
                   knowledge=knowledge,
                   deck_counts=tuple(sorted((card_id, count) for card_id, count in remaining.items()
                                            if count > 0)), events=())


__all__ = ("SAMPLE_BUDGET", "refresh_value")
