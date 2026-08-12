"""Known uncertainty, causal Needs, and Scouting belief adapters."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import product
from math import comb
from typing import Mapping

from .state import OpponentBelief, freeze


DEFAULT_SEAT = 0
DEFAULT_BENCH_CAPACITY = 5
ACCELERATOR_RECIPIENT_WORTH = 32.0
LINE_EVOLUTION_WORTH = 30.0
TYPED_ENERGY_WORTH = 12.0
BURST_ENERGY_WORTH = 12.0
PROBABILITY_MIN = 0.0
PROBABILITY_MAX = 1.0
HYPERGEOMETRIC_MASS_TOLERANCE = 1e-12
OUTCOME_RNG_SEED = 0
CANDIDATE_PAIR_SIZE = 2


@dataclass(frozen=True)
class BellmanDeckProfile:
    """Deck declarations consumed by the neutral Bellman kernel.

    Card identity is allowed at the deck boundary, never in the planner.  The profile is inferred
    from a strategy's declared evolution lines, roles, card facts, and function tags so another
    deck supplies data rather than another branch of core logic.
    """

    lines: tuple[tuple[int, ...], ...] = ()
    accelerators: tuple[int, ...] = ()
    reusable_energy: tuple[int, ...] = ()
    burst_energy: tuple[int, ...] = ()
    prize_routes: tuple[tuple[int, ...], ...] = ()
    prizes_to_win: int | None = None

    @classmethod
    def from_registry(cls, registry) -> "BellmanDeckProfile":
        lines = tuple(getattr(registry, "lines", ()) or ())
        if not lines:
            lines = tuple((base, top) for top, base in
                          sorted(getattr(registry, "line_parents", {}).items()))
        functions = getattr(registry, "functions", {})
        facts = getattr(registry, "facts", {})
        roles = getattr(registry, "roles", {})
        accelerators = tuple(sorted(
            card_id for card_id, card_roles in roles.items()
            if "accel_source" in card_roles and bool(getattr(facts.get(card_id), "pokemon", False))))
        reusable_energy = tuple(sorted(
            card_id for card_id, fact in facts.items()
            if bool(getattr(fact, "typed_basic_energy", False))))
        burst_energy = tuple(sorted(
            card_id for card_id, tags in functions.items()
            if "discard_eot" in tags and any(str(tag).startswith("provides_evo:") for tag in tags)))
        prize_routes = tuple(tuple(int(card_id) for card_id in route)
                             for route in getattr(registry, "prize_routes", ()))
        return cls(lines=tuple(tuple(int(card_id) for card_id in line) for line in lines),
                   accelerators=accelerators, reusable_energy=reusable_energy,
                   burst_energy=burst_energy, prize_routes=prize_routes,
                   prizes_to_win=getattr(registry, "prizes_to_win", None))

    @property
    def line_bases(self) -> frozenset[int]:
        return frozenset(line[0] for line in self.lines if line)

    @property
    def line_tops(self) -> frozenset[int]:
        return frozenset(line[-1] for line in self.lines if line)

    @property
    def line_cards(self) -> frozenset[int]:
        return frozenset(card_id for line in self.lines for card_id in line)


@dataclass(frozen=True)
class Need:
    key: str
    card_ids: tuple[int, ...]
    value_worth: float
    rationale: str


class CausalNeeds:
    """Deck declaration translated into legal dependency demand; never an action chooser."""

    def __init__(self, *, profile: BellmanDeckProfile = BellmanDeckProfile()):
        self.profile = profile

    @staticmethod
    def _ids(player) -> list[int]:
        bodies = tuple(player.get("active") or ()) + tuple(player.get("bench") or ())
        return [int(body["id"]) for body in bodies if body]

    def derive(self, observation: Mapping, *, deck_counts: Mapping[int, int]) -> tuple[Need, ...]:
        current = observation.get("current") or {}
        seat = int(current.get("yourIndex", DEFAULT_SEAT))
        players = current.get("players") or ()
        me = players[seat] if 0 <= seat < len(players) and players[seat] else {}
        bodies = self._ids(me)
        bench_space = len(me.get("bench") or ()) < int(me.get("benchMax", DEFAULT_BENCH_CAPACITY))
        needs = []
        bases = self.profile.line_bases
        tops = self.profile.line_tops
        if (set(self.profile.accelerators).intersection(bodies) and not set(bodies).intersection(bases)
                and not set(bodies).intersection(tops) and bench_space
                and any(deck_counts.get(card_id, 0) > 0 for card_id in bases)):
            needs.append(Need(
                "accelerator-recipient", tuple(sorted(bases)), ACCELERATOR_RECIPIENT_WORTH,
                "A declared evolution-line base supplies a Bench recipient for acceleration",
            ))
        missing_tops = tuple(card_id for card_id in tops if card_id not in bodies
                             and deck_counts.get(card_id, 0) > 0)
        if set(bodies).intersection(bases) and missing_tops:
            needs.append(Need(
                "line-evolution", missing_tops, LINE_EVOLUTION_WORTH,
                "A declared top evolution converts the established dependency into a win condition",
            ))
        active = next((body for body in (me.get("active") or ()) if body), None)
        active_energy = len((active or {}).get("energyCards") or (active or {}).get("energies") or ())
        reusable = tuple(card_id for card_id in self.profile.reusable_energy
                         if deck_counts.get(card_id, 0) > 0)
        if active is not None and active_energy == 0 and reusable:
            needs.append(Need(
                "typed-attack-energy", reusable, TYPED_ENERGY_WORTH,
                "A reusable typed Energy funds the current attack and persists",
            ))
        burst = tuple(card_id for card_id in self.profile.burst_energy
                      if deck_counts.get(card_id, 0) > 0)
        if set(bodies).intersection(tops) and burst:
            needs.append(Need(
                "burst-energy", burst, BURST_ENERGY_WORTH,
                "Burst Energy can fund the evolved body's colourless attack this turn",
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
    if abs(mass - PROBABILITY_MAX) > HYPERGEOMETRIC_MASS_TOLERANCE:
        raise ValueError(f"hypergeometric outcome mass {mass} != 1")
    return tuple(outcomes)


def opponent_belief(observation: Mapping, *, candidates=(), properties=None) -> OpponentBelief:
    """Immutable posterior adapter.  Unclaimed probability is an explicit unknown bucket."""
    rows = []
    for candidate in candidates or ():
        if isinstance(candidate, Mapping):
            name = str(candidate.get("name") or candidate.get("slug") or "unknown")
            probability = float(candidate.get("probability", candidate.get("p", 0.0)) or 0.0)
        elif isinstance(candidate, (tuple, list)) and len(candidate) == CANDIDATE_PAIR_SIZE:
            name, probability = str(candidate[0]), float(candidate[1])
        else:
            name = str(getattr(candidate, "name", getattr(candidate, "slug", "unknown")))
            probability = float(getattr(candidate, "probability", getattr(candidate, "p", 0.0)) or 0.0)
        if probability > PROBABILITY_MIN:
            rows.append((name, probability))
    claimed = sum(probability for _name, probability in rows)
    if claimed > PROBABILITY_MAX:
        rows = [(name, probability / claimed) for name, probability in rows]
        claimed = PROBABILITY_MAX
    current = observation.get("current") or {}
    seat = int(current.get("yourIndex", DEFAULT_SEAT))
    players = current.get("players") or ()
    visible = players[1 - seat] if len(players) > 1 and players[1 - seat] else {}
    return OpponentBelief(
        visible=freeze(visible), archetypes=tuple(sorted(rows)),
        properties=tuple(sorted((str(key), freeze(value))
                                for key, value in (properties or {}).items())),
        unknown_mass=max(PROBABILITY_MIN, PROBABILITY_MAX - claimed),
    )


class OutcomeRng:
    """One branch's forced draw multiset; other randomness stays deterministic."""

    def __init__(self, *, seat: int, serial_to_card: Mapping[int, int], draw_ids):
        from cgpy.rng import SeededRng
        self._fallback = SeededRng(OUTCOME_RNG_SEED)
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
    "BellmanDeckProfile", "CausalNeeds", "DrawClass", "Need", "OutcomeRng", "hypergeometric_classes",
    "opponent_belief",
)
