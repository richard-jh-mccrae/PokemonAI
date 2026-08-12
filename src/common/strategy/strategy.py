"""The declarative Strategy a deck supplies to the Pilot (see common/CONTEXT.md, ADR-0008).

Pure data: structure + tunable numbers, no engine and no control flow. The deck's
doctrine is expressed here as roles, prize plans, params, and hypotheses; the shared
Pilot interprets it. This module also owns the closed Plan vocabulary.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


STANDARD_PRIZES_TO_WIN = 6


class Plan(enum.Enum):
    """The Pilot's current-turn strategic mode — a closed set, the tempo/defensive axis of the Match
    Planner's Game Plan (ADR-0045)."""
    SETUP = "SETUP"
    RACE = "RACE"
    STALL = "STALL"
    STABILIZE = "STABILIZE"
    SACRIFICE = "SACRIFICE"
    CLOSE = "CLOSE"


@dataclass
class GamePlan:
    """The Match Planner's output (ADR-0045): route, mode, confidence and the directed Turn Goal it
    hands the Turn Planner. Re-derived each turn, NEVER a lock; withheld on low confidence."""
    mode: Plan = Plan.SETUP
    confidence: float = 0.0
    route: frozenset = field(default_factory=frozenset)   # opp card ids on my cheapest Prize Path
    route_turns: float | None = None                       # total feasibility turns of that route
    directed_goal: str | None = None                       # the goal-kind to steer the Turn Planner (S3)
    rationale: str = ""


@dataclass
class Ready:
    """When a Line's payoff counts as online: in play with >= `energy` attached. `energy=None`
    derives the threshold from the payoff's CHEAPEST attack cost, not its biggest."""
    energy: int | None = None


@dataclass
class Line:
    """Normalized evolution path consumed by legacy strategy code.

    Decks should declare evolution relationships through :class:`Roles`; ``Line`` remains the
    compatibility shape read by existing consumers.
    """
    path: list
    payoff: int
    role: str = "win_condition"
    ready: Ready = field(default_factory=Ready)


@dataclass(frozen=True)
class PrizePlan:
    """Preferred order(s) in which the opponent should knock out our Pokémon.

    Each route contains card ids in KO order. Printed prize values come from card facts, so the
    declaration describes bodies rather than repeating prize numbers.
    """

    routes: tuple[tuple[int, ...], ...]
    prizes_to_win: int = STANDARD_PRIZES_TO_WIN

    def __post_init__(self) -> None:
        routes = tuple(tuple(int(card_id) for card_id in route) for route in self.routes)
        if not routes or any(not route for route in routes):
            raise ValueError("a prize plan requires at least one non-empty route")
        if int(self.prizes_to_win) <= 0:
            raise ValueError("prizes_to_win must be positive")
        object.__setattr__(self, "routes", routes)
        object.__setattr__(self, "prizes_to_win", int(self.prizes_to_win))


class Roles(dict):
    """Card roles plus evolution relationships at the deck boundary.

    ``evolves`` is ``source card id -> target card id``. Chains are normalized into legacy
    :class:`Line` objects. The terminal card's role determines whether a line is a win condition or
    a secondary-attacker line; ``ready`` optionally overrides its online Energy threshold.
    """

    _LINE_ROLE_PRIORITY = ("win_condition", "primary_attacker", "secondary_attacker")

    def __init__(self, cards=None, *, evolves=None, ready=None):
        super().__init__({int(card_id): list(card_roles)
                          for card_id, card_roles in (cards or {}).items()})
        self.evolves = {int(source): int(target)
                        for source, target in (evolves or {}).items()}
        self.ready = {
            int(card_id): (threshold if isinstance(threshold, Ready) else Ready(int(threshold)))
            for card_id, threshold in (ready or {}).items()
        }
        self._lines = self._normalize_lines()
        for line in self._lines:
            base_role = ("win_condition_base" if line.role == "win_condition"
                         else "evolution_base")
            base_roles = self.setdefault(int(line.path[0]), [])
            if base_role not in base_roles:
                base_roles.append(base_role)

    @property
    def lines(self) -> tuple[Line, ...]:
        return self._lines

    def _normalize_lines(self) -> tuple[Line, ...]:
        if not self.evolves:
            return ()
        targets = set(self.evolves.values())
        roots = tuple(source for source in self.evolves if source not in targets)
        if not roots:
            raise ValueError("evolution relationships must not contain a cycle")
        lines = []
        visited = set()
        for root in roots:
            path, seen = [root], {root}
            while path[-1] in self.evolves:
                source = path[-1]
                target = self.evolves[source]
                if target in seen:
                    raise ValueError("evolution relationships must not contain a cycle")
                visited.add(source)
                path.append(target)
                seen.add(target)
            payoff = path[-1]
            payoff_roles = set(self.get(payoff, ()))
            role = next((candidate for candidate in self._LINE_ROLE_PRIORITY
                         if candidate in payoff_roles), None)
            if role == "primary_attacker":
                role = "win_condition"
            if role is None:
                raise ValueError(f"evolution payoff {payoff} requires an attacker role")
            lines.append(Line(path=path, payoff=payoff, role=role,
                              ready=self.ready.get(payoff, Ready())))
        if visited != set(self.evolves):
            raise ValueError("every evolution relationship must belong to a rooted line")
        return tuple(lines)


@dataclass
class Hypothesis:
    """A named, testable claim that biases scoring. ``weight`` is REQUIRED and has NO default: a `0.0`
    default made a rung authored by OMISSION indistinguishable from a deliberate `weight=0` seed."""
    id: str
    rationale: str
    when: object                  # callable: (ctx) -> bool
    weight: float
    status: str = "assumed"


@dataclass
class Strategy:
    name: str = ""
    lines: list = field(default_factory=list)          # normalized compatibility view of role relationships
    roles: dict = field(default_factory=dict)          # cardId -> [Role]
    params: dict = field(default_factory=dict)         # tunable scalars
    hypotheses: list = field(default_factory=list)     # weighted, status-tracked rules
    fetch_priority: list = field(default_factory=list)  # Tier-3 explicit grab order (cardIds, highest
                                                        # first) -- combo deck's override of derived
                                                        # fetch importance (ADR-0023); empty for most decks
    starter_priority: list = field(default_factory=list)  # ordered opening bodies (cardIds, best first)
                                                        # for the pregame Set-Up ACTIVE pick (ADR-0079).
                                                        # Must be COMPLETE -- every startable body ranked.
    weight_overrides: dict = field(default_factory=dict)  # authored per-deck seed overrides of (typically
                                                        # general) Hypothesis weights by id -- doctrine-driven,
                                                        # sparse, UNDER the learned tuned.json layer (ADR-0035)
    partners: dict = field(default_factory=dict)       # cardId -> [partner cardIds]: an engine body whose
                                                        # value REQUIRES a listed partner in play (ADR-0034);
                                                        # the attach oracle zeroes a partnerless one
    worth_overrides: dict = field(default_factory=dict)  # cardId -> Worth floor; deck doctrine may RAISE
                                                         # the shared function value, never lower it
    prize_plan: PrizePlan | None = None                  # deck-preferred own-Pokémon KO sequences

    def __post_init__(self) -> None:
        declared_lines = tuple(getattr(self.roles, "lines", ()))
        if declared_lines:
            if self.lines:
                raise ValueError("declare evolution lines in Roles or Strategy.lines, not both")
            self.lines = list(declared_lines)
