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

from common.board import BoardState
from common.cards import card_store
from common.cards.card_facts import SUPPORTER

SAMPLE_BUDGET = 24


def refresh_value(observation, board: BoardState, card_id: int,
                  draws, opponent_shuffles: bool, evaluate_fn):
    """Expected VALUE of the board after playing shuffle-draw supporter `card_id` (absolute,
    not a swing — the preview differences it against its own baseline), plus the gaps met."""
    gaps: list[str] = []
    seat = board.seat
    mine = _player(observation, seat)
    hand_ids = [int(card["id"]) for card in (mine.get("hand") or ()) if card]
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
            synthetic = _synthesize(observation, seat, sampled, len(pool) - len(sampled),
                                    int(card_id), int(opponent_draw), opponent_shuffles)
            valuation = evaluate_fn(BoardState.root(synthetic, decklist=board.decklist))
            gaps.extend(valuation.gaps)
            total += valuation.total
            weight += 1
    return (total / weight if weight else 0.0), tuple(gaps)


def _seed(board: BoardState, card_id: int) -> int:
    digest = hashlib.blake2b(f"{board.key}:{int(card_id)}".encode("ascii"),
                             digest_size=8).digest()
    return int.from_bytes(digest, "big")


def _sample(rng: random.Random, pool: list, count: int) -> list:
    if count >= len(pool):
        return list(pool)
    return rng.sample(pool, count)


def _player(observation, seat: int) -> dict:
    players = (observation.get("current") or {}).get("players") or ()
    return players[seat] if 0 <= seat < len(players) and players[seat] else {}


def _synthesize(observation, seat: int, hand_ids, deck_count: int, played_id: int,
                opponent_draw: int, opponent_shuffles: bool) -> dict:
    """The post-shuffle printout: my sampled hand, the played Supporter in the discard, the
    opponent's counts moved. Serials are synthetic — the evaluator never reads them."""
    root = dict(observation)
    current = dict(root.get("current") or {})
    players = list(current.get("players") or ({}, {}))
    mine = dict(players[seat] or {})
    mine["hand"] = [{"id": int(card_id), "serial": None, "playerIndex": seat}
                    for card_id in hand_ids]
    mine["handCount"] = len(hand_ids)
    mine["deckCount"] = max(0, int(deck_count))
    mine["discard"] = list(mine.get("discard") or ()) + [
        {"id": int(played_id), "serial": None, "playerIndex": seat}]
    players[seat] = mine

    other = dict(players[1 - seat] or {})
    if opponent_shuffles:
        previous = int(other.get("handCount") or 0)
        other["deckCount"] = max(0, int(other.get("deckCount") or 0) + previous
                                 - int(opponent_draw))
        other["handCount"] = int(opponent_draw)
    else:
        other["handCount"] = int(other.get("handCount") or 0) + int(opponent_draw)
        other["deckCount"] = max(0, int(other.get("deckCount") or 0) - int(opponent_draw))
    other["hand"] = None
    players[1 - seat] = other

    current["players"] = players
    # Only a Supporter spends the Supporter allowance; an Item-borne shuffle-refresh must not.
    if getattr(card_store().get(int(played_id)), "kind", None) == SUPPORTER:
        current["supporterPlayed"] = True
    root["current"] = current
    root["select"] = None
    return root


__all__ = ("SAMPLE_BUDGET", "refresh_value")
