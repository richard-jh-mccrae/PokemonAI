"""Deck declarations and the opponent-belief posterior for the Bellman kernel."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from common.state import OpponentBelief, freeze


DEFAULT_SEAT = 0
PROBABILITY_MIN = 0.0
PROBABILITY_MAX = 1.0
CANDIDATE_PAIR_SIZE = 2


@dataclass(frozen=True)
class BellmanDeckProfile:
    """Deck declarations consumed by the neutral Bellman kernel.

    Card identity is allowed at the deck boundary, never in the planner.  The profile is inferred
    from a strategy's declared evolution lines, roles, card facts, and function tags so another
    deck supplies data rather than another branch of core logic.
    """

    lines: tuple[tuple[int, ...], ...] = ()
    partners: tuple[tuple[int, tuple[int, ...]], ...] = ()
    prize_routes: tuple[tuple[int, ...], ...] = ()
    prizes_to_win: int | None = None

    @classmethod
    def from_registry(cls, registry) -> "BellmanDeckProfile":
        lines = tuple(getattr(registry, "lines", ()) or ())
        if not lines:
            lines = tuple((base, top) for top, base in
                          sorted(getattr(registry, "line_parents", {}).items()))
        prize_routes = tuple(tuple(int(card_id) for card_id in route)
                             for route in getattr(registry, "prize_routes", ()))
        partners = tuple(sorted(
            (int(card_id), tuple(int(partner) for partner in values))
            for card_id, values in getattr(registry, "partners", {}).items()))
        return cls(lines=tuple(tuple(int(card_id) for card_id in line) for line in lines),
                   partners=partners, prize_routes=prize_routes,
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


__all__ = ("BellmanDeckProfile", "opponent_belief")
