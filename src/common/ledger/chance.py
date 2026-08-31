"""Bounded whole-hand sampling for shuffle-draw actions.

The caller receives the expected valuation and the bounded sampled successor roots that produced it.
"""
from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from dataclasses import dataclass
from dataclasses import replace

from common.observation import ObservationState, ObservationStateBuilder, OpponentBelief
from common.cards import card_store
from common.cards.card_facts import SUPPORTER
from common.ledger.evaluate import FeatureActivation, FeatureContribution, Valuation


PLAYER_COUNT = 2
SEED_DIGEST_BYTES = 8
SAMPLE_SEED_BITS = 64
MIN_ADAPTIVE_SAMPLES = 4
SAMPLES_PER_OUTCOME = 2


@dataclass(frozen=True, slots=True)
class RefreshSummary:
    sample_count: int
    expected_value: float
    variance: float
    seed: int
    configuration_identity: str
    method: str = "sampled"


class _RunningValuation:
    def __init__(self):
        self.count = 0
        self.mean = 0.0
        self.m2 = 0.0
        self.activations = defaultdict(float)
        self.provenance = defaultdict(set)
        self.coefficients = {}
        self.prize_maps = set()

    def add(self, valuation):
        self.count += 1
        delta = valuation.total - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (valuation.total - self.mean)
        for item in valuation.activations:
            self.activations[item.feature] += item.value
            self.provenance[item.feature].update(item.provenance)
        self.coefficients.update(
            (item.feature, item.coefficient) for item in valuation.contributions)
        self.prize_maps.add(valuation.prize_map)

    def finish(self, gaps):
        if not self.count:
            return Valuation(0.0, (), tuple(gaps))
        averaged = tuple(FeatureActivation(
            feature, total / self.count, tuple(sorted(self.provenance[feature])))
            for feature, total in sorted(self.activations.items()) if total)
        contributions = tuple(FeatureContribution(
            item.feature, item.value, self.coefficients[item.feature],
            item.value * self.coefficients[item.feature], item.provenance)
            for item in averaged)
        prize_map = next(iter(self.prize_maps)) if len(self.prize_maps) == 1 else None
        return Valuation(sum(item.value for item in contributions), (), tuple(gaps),
                         averaged, contributions, prize_map)


def refresh_outcomes(observation, board: ObservationState, card_id: int,
                     draws, opponent_shuffles: bool, evaluate_fn, compute, ctx=None):
    compute = getattr(compute, "search", compute)
    gaps = set()
    seat = board.seat
    mine = _player(observation, seat)
    hand_ids = [int(card["id"]) for card in (mine.get("hand") or ())
                if card and card.get("id") is not None]
    if int(card_id) in hand_ids:
        hand_ids.remove(int(card_id))
    else:
        gaps.add(f"refresh: played card {int(card_id)} not visible in hand")
    pool: list[int] = list(hand_ids)
    if board.deck_counts is not None:
        for target_id, count in board.deck_counts:
            pool.extend([int(target_id)] * int(count))
    else:
        gaps.add("refresh: own deck contents unknown; sampling hand-only pool")

    draws = tuple(draws)
    seed = _seed(board, card_id, compute.chance_seed)
    running = _RunningValuation()
    successors = []
    if draws:
        minimum_samples = min(
            compute.chance_sample_budget,
            max(MIN_ADAPTIVE_SAMPLES, len(draws) * SAMPLES_PER_OUTCOME))
        for index in range(compute.chance_sample_budget):
            own_draw, opponent_draw = draws[index % len(draws)]
            rng = random.Random(_sample_seed(seed, index))
            sampled = _sample(rng, pool, int(own_draw))
            synthetic = _synthesize(
                observation, seat, sampled, len(pool) - len(sampled),
                int(card_id), int(opponent_draw), opponent_shuffles)
            successor = ObservationStateBuilder(board.decklist).root(
                synthetic, knowledge=board.knowledge)
            valuation = evaluate_fn(successor)
            gaps.update(valuation.gaps)
            running.add(valuation)
            successors.append(successor)
            del valuation, synthetic
            if running.count >= minimum_samples and running.m2 == 0.0:
                break
    ordered_gaps = tuple(sorted(gaps))
    result = running.finish(ordered_gaps)
    variance = 0.0 if not running.count else running.m2 / running.count
    summary = RefreshSummary(
        running.count, result.total, variance, seed, compute.identity)
    probability = 0.0 if not successors else 1.0 / len(successors)
    landings = tuple((probability, successor, successor, False, ())
                     for successor in successors)
    return result, ordered_gaps, summary, landings


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
                             digest_size=SEED_DIGEST_BYTES).digest()
    return int.from_bytes(digest, "big")


def _sample_seed(seed: int, index: int) -> int:
    digest = hashlib.blake2b(
        f"{seed}:{index}".encode("ascii"), digest_size=SEED_DIGEST_BYTES).digest()
    return int.from_bytes(digest, "big")


def _sample(rng: random.Random, pool: list, count: int) -> list:
    if count >= len(pool):
        return list(pool)
    # Rank positions with a stable digest because `random.sample` varies by Python version.
    seed = rng.getrandbits(SAMPLE_SEED_BITS)
    ranked = sorted(
        range(len(pool)),
        key=lambda index: hashlib.blake2b(
            f"{seed}:{index}".encode("ascii"), digest_size=SEED_DIGEST_BYTES).digest())
    return [pool[index] for index in ranked[:count]]


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
    while len(players) < max(PLAYER_COUNT, seat + 1):
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


__all__ = ("RefreshSummary", "refresh_outcomes")
