"""The declarative Strategy a deck supplies to the Pilot (see common/CONTEXT.md, ADR-0008).

Pure data: structure + tunable numbers, no engine and no control flow. The deck's
doctrine is expressed here as lines, role assignments, params, and hypotheses; the shared
Pilot interprets it. This module also owns the closed Plan vocabulary.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


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
    """A win-condition evolution path, basic -> payoff (by cardId)."""
    path: list
    payoff: int
    role: str = "win_condition"
    ready: Ready = field(default_factory=Ready)


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
    lines: list = field(default_factory=list)          # win-condition Lines
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
