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
from collections import defaultdict
from dataclasses import replace

from common.observation import ObservationState, ObservationStateBuilder, OpponentBelief
from common.cards import card_store
from common.cards.card_facts import SUPPORTER
from common.ledger.evaluate import FeatureActivation, FeatureContribution, Valuation


def refresh_valuation(observation, board: ObservationState, card_id: int,
                      draws, opponent_shuffles: bool, evaluate_fn, compute):
    samples, gaps = _refresh_samples(
        observation, board, card_id, draws, opponent_shuffles, evaluate_fn, compute)
    return _average(samples, gaps)


def _average(samples, gaps):
    valuations = tuple(valuation for valuation, _board, _observation in samples)
    if not valuations:
        return Valuation(0.0, (), tuple(gaps)), tuple(gaps)
    activations = defaultdict(float)
    provenance = defaultdict(set)
    for valuation in valuations:
        for item in valuation.activations:
            activations[item.feature] += item.value / len(valuations)
            provenance[item.feature].update(item.provenance)
    averaged = tuple(FeatureActivation(feature, value, tuple(sorted(provenance[feature])))
                     for feature, value in sorted(activations.items()) if value)
    coefficients = {item.feature: item.coefficient
                    for valuation in valuations for item in valuation.contributions}
    contributions = tuple(FeatureContribution(
        item.feature, item.value, coefficients[item.feature],
        item.value * coefficients[item.feature], item.provenance) for item in averaged)
    prize_maps = {valuation.prize_map for valuation in valuations}
    prize_map = next(iter(prize_maps)) if len(prize_maps) == 1 else None
    result = Valuation(sum(item.value for item in contributions), (), tuple(gaps),
                       averaged, contributions, prize_map)
    return result, tuple(gaps)


def refresh_outcomes(observation, board: ObservationState, card_id: int,
                     draws, opponent_shuffles: bool, evaluate_fn, compute):
    samples, gaps = _refresh_samples(
        observation, board, card_id, draws, opponent_shuffles, evaluate_fn, compute)
    valuation, _ = _average(samples, gaps)
    probability = 1.0 / len(samples) if samples else 0.0
    outcomes = tuple((probability, successor, synthetic)
                     for _valuation, successor, synthetic in samples)
    return valuation, gaps, outcomes

def refresh_value(observation, board: ObservationState, card_id: int,
                  draws, opponent_shuffles: bool, evaluate_fn, compute):
    """Expected VALUE of the board after playing shuffle-draw supporter `card_id` (absolute,
    not a swing — the preview differences it against its own baseline), plus the gaps met."""
    valuation, gaps = refresh_valuation(
        observation, board, card_id, draws, opponent_shuffles, evaluate_fn, compute)
    return valuation.total, gaps


def _refresh_samples(observation, board: ObservationState, card_id: int,
                     draws, opponent_shuffles: bool, evaluate_fn, compute):
    compute = getattr(compute, "search", compute)
    gaps: list[str] = []
    seat = board.seat
    mine = _player(observation, seat)
    hand_ids = [int(card["id"]) for card in (mine.get("hand") or ())
                if card and card.get("id") is not None]
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

    rng = random.Random(_seed(board, card_id, compute.chance_seed))
    samples = []
    for own_draw, opponent_draw in draws:
        for _ in range(max(1, compute.chance_sample_budget // max(1, len(draws)))):
            sampled = _sample(rng, pool, int(own_draw))
            synthetic = _synthesize(observation, seat, sampled, len(pool) - len(sampled),
                                    int(card_id), int(opponent_draw), opponent_shuffles)
            successor = ObservationStateBuilder(board.decklist).root(
                synthetic, knowledge=board.knowledge)
            valuation = evaluate_fn(successor)
            gaps.extend(valuation.gaps)
            samples.append((valuation, successor, synthetic))
    return tuple(samples), tuple(gaps)


def _seed(board: ObservationState, card_id: int, seed: int) -> int:
    evidence = dict(board.knowledge.opponent.evidence)
    key = board.key
    if board.knowledge.opponent.decision_evidence is not None:
        coarse = OpponentBelief(
            evidence=(("snapshot", evidence["snapshot"]),
                      ("archetypes", evidence["archetypes"])),
            probabilities=board.knowledge.opponent.probabilities,
        )
        legacy = replace(board, knowledge=replace(board.knowledge, opponent=coarse))
        key = legacy.key
    digest = hashlib.blake2b(f"{seed}:{key}:{int(card_id)}".encode("ascii"),
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
    players = list(current.get("players") or ())
    while len(players) < max(2, seat + 1):         # both seats must exist to be rewritten
        players.append({})
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


__all__ = ("refresh_outcomes", "refresh_value", "refresh_valuation")
