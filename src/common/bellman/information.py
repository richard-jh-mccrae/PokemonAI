"""Known uncertainty, causal Needs, and Scouting belief adapters."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import product
from math import comb
from typing import Mapping

from .state import OpponentBelief, freeze


STARYU, MEGA_STARMIE, CINDERACE = 1030, 1031, 666
WATER, IGNITION = 3, 17


@dataclass(frozen=True)
class Need:
    key: str
    card_ids: tuple[int, ...]
    value_worth: float
    rationale: str


class CausalNeeds:
    """Deck declaration translated into legal dependency demand; never an action chooser."""

    def __init__(self, *, line=(STARYU, MEGA_STARMIE), accelerator=CINDERACE,
                 reusable_energy=WATER, burst_energy=IGNITION):
        self.line = tuple(int(card_id) for card_id in line)
        self.accelerator = int(accelerator)
        self.reusable_energy = int(reusable_energy)
        self.burst_energy = int(burst_energy)

    @staticmethod
    def _ids(player) -> list[int]:
        bodies = tuple(player.get("active") or ()) + tuple(player.get("bench") or ())
        return [int(body["id"]) for body in bodies if body]

    def derive(self, observation: Mapping, *, deck_counts: Mapping[int, int]) -> tuple[Need, ...]:
        current = observation.get("current") or {}
        seat = int(current.get("yourIndex", 0))
        players = current.get("players") or ()
        me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
        bodies = self._ids(me)
        bench_space = len(me.get("bench") or ()) < int(me.get("benchMax", 5))
        needs = []
        if (self.accelerator in bodies and self.line[0] not in bodies
                and self.line[1] not in bodies and bench_space
                and deck_counts.get(self.line[0], 0) > 0):
            needs.append(Need(
                "turbo-recipient", (self.line[0],), 32.0,
                "Staryu supplies a Bench recipient for Turbo Flare and the Mega Starmie line",
            ))
        if (self.line[0] in bodies and self.line[1] not in bodies
                and deck_counts.get(self.line[1], 0) > 0):
            needs.append(Need(
                "line-evolution", (self.line[1],), 30.0,
                "Mega Starmie converts the established Staryu dependency into the win condition",
            ))
        active = next((body for body in (me.get("active") or ()) if body), None)
        active_energy = len((active or {}).get("energyCards") or (active or {}).get("energies") or ())
        if active is not None and active_energy == 0 and deck_counts.get(self.reusable_energy, 0) > 0:
            needs.append(Need(
                "typed-attack-energy", (self.reusable_energy,), 12.0,
                "reusable Water funds the current attack and persists",
            ))
        if (self.line[1] in bodies and deck_counts.get(self.burst_energy, 0) > 0):
            needs.append(Need(
                "burst-energy", (self.burst_energy,), 12.0,
                "Ignition can fund the evolved body's colorless burst this turn",
            ))
        return tuple(needs)


@dataclass(frozen=True)
class DrawClass:
    probability: float
    counts: tuple[int, ...]
    remainder: int
    label: str


def hypergeometric_classes(pool_ids, draws: int, needs: tuple[Need, ...]) -> tuple[DrawClass, ...]:
    """Exact mutually-exclusive count classes for disjoint need groups plus explicit remainder."""
    pool = Counter(int(card_id) for card_id in pool_ids)
    groups, claimed = [], set()
    for need in needs:
        ids = tuple(card_id for card_id in need.card_ids if card_id not in claimed)
        claimed.update(ids)
        groups.append(sum(pool[card_id] for card_id in ids))
    total = sum(pool.values())
    draws = min(max(0, int(draws)), total)
    remainder_n = total - sum(groups)
    denominator = comb(total, draws) if total >= draws else 0
    if denominator == 0:
        return (DrawClass(1.0, tuple(0 for _ in groups), 0, "empty"),)
    outcomes = []
    ranges = [range(min(size, draws) + 1) for size in groups]
    for counts in product(*ranges):
        remainder = draws - sum(counts)
        if not 0 <= remainder <= remainder_n:
            continue
        numerator = comb(remainder_n, remainder)
        for size, count in zip(groups, counts):
            numerator *= comb(size, count)
        if not numerator:
            continue
        labels = [f"{need.key}={count}" for need, count in zip(needs, counts)]
        labels.append(f"other={remainder}")
        outcomes.append(DrawClass(numerator / denominator, tuple(counts), remainder,
                                  ",".join(labels)))
    mass = sum(outcome.probability for outcome in outcomes)
    if abs(mass - 1.0) > 1e-12:
        raise ValueError(f"hypergeometric outcome mass {mass} != 1")
    return tuple(outcomes)


def opponent_belief(observation: Mapping, *, candidates=(), properties=None) -> OpponentBelief:
    """Immutable posterior adapter.  Unclaimed probability is an explicit unknown bucket."""
    rows = []
    for candidate in candidates or ():
        if isinstance(candidate, Mapping):
            name = str(candidate.get("name") or candidate.get("slug") or "unknown")
            probability = float(candidate.get("probability", candidate.get("p", 0.0)) or 0.0)
        elif isinstance(candidate, (tuple, list)) and len(candidate) == 2:
            name, probability = str(candidate[0]), float(candidate[1])
        else:
            name = str(getattr(candidate, "name", getattr(candidate, "slug", "unknown")))
            probability = float(getattr(candidate, "probability", getattr(candidate, "p", 0.0)) or 0.0)
        if probability > 0.0:
            rows.append((name, probability))
    claimed = sum(probability for _name, probability in rows)
    if claimed > 1.0:
        rows = [(name, probability / claimed) for name, probability in rows]
        claimed = 1.0
    current = observation.get("current") or {}
    seat = int(current.get("yourIndex", 0))
    players = current.get("players") or ()
    visible = players[1 - seat] if len(players) > 1 and players[1 - seat] else {}
    return OpponentBelief(
        visible=freeze(visible), archetypes=tuple(sorted(rows)),
        properties=tuple(sorted((str(key), freeze(value))
                                for key, value in (properties or {}).items())),
        unknown_mass=max(0.0, 1.0 - claimed),
    )


class OutcomeRng:
    """One branch's forced draw multiset; other randomness stays deterministic."""

    def __init__(self, *, seat: int, serial_to_card: Mapping[int, int], draw_ids):
        from cgpy.rng import SeededRng
        self._fallback = SeededRng(0)
        self.seat = int(seat)
        self.serial_to_card = dict(serial_to_card)
        self.draw_ids = list(int(card_id) for card_id in draw_ids)
        self._armed = True

    def shuffle(self, seq, *, seat: int):
        if seat != self.seat or not self._armed:
            self._fallback.shuffle(seq, seat=seat)
            return
        chosen, remaining = [], list(seq)
        for card_id in self.draw_ids:
            serial = next((serial for serial in remaining
                           if self.serial_to_card.get(serial) == card_id), None)
            if serial is None:
                raise ValueError(f"branch requested unavailable card {card_id}")
            remaining.remove(serial)
            chosen.append(serial)
        seq[:] = remaining + list(reversed(chosen))
        self._armed = False

    def coin(self, seat=None):
        return self._fallback.coin(seat=seat)

    def draw_bind(self, seat, deck, *, prize=None):
        return deck[-1]

    def prize_bind(self, seat, deck, count):
        return self._fallback.prize_bind(seat, deck, count)

    def hand_pick(self, seat, hand):
        return self._fallback.hand_pick(seat, hand)

    def hand_pick_expect(self, seat, serials):
        return None

    def look_bind(self, seat, deck, n, *, from_bottom=False):
        return self._fallback.look_bind(seat, deck, n, from_bottom=from_bottom)

    def mill_bind(self, seat, deck, prize, n):
        return self._fallback.mill_bind(seat, deck, prize, n)


__all__ = (
    "CausalNeeds", "DrawClass", "Need", "OutcomeRng", "hypergeometric_classes",
    "opponent_belief",
)
