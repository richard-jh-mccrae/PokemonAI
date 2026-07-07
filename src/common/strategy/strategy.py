"""The declarative Strategy a deck supplies to the Pilot (see common/CONTEXT.md, ADR-0008).

Pure data: structure + tunable numbers, no engine and no control flow. The deck's
doctrine is expressed here as lines, role assignments, params, and hypotheses; the shared
Pilot interprets it. This module also owns the closed Plan vocabulary.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Plan(enum.Enum):
    """The Pilot's current-turn strategic mode — a closed set. The tempo/defensive axis of the Match
    Planner's Game Plan (ADR-0045): SETUP→develop; RACE→take the on-path KO on tempo; STALL→develop while
    declining giant-waking KOs to buy setup turns; STABILIZE→survive my threatened Active;
    SACRIFICE→trade the Active, race on prize math; CLOSE→force the finishing line."""
    SETUP = "SETUP"
    RACE = "RACE"
    STALL = "STALL"
    STABILIZE = "STABILIZE"
    SACRIFICE = "SACRIFICE"
    CLOSE = "CLOSE"


@dataclass
class GamePlan:
    """The Match Planner's output (ADR-0045): the committed route to victory + tempo/defensive **mode** +
    **confidence**, and the **directed Turn Goal** it hands the Turn Planner. A ranking/steering object,
    re-derived each turn, NEVER a lock; emitted to Decision telemetry so the blunder-buster can tie a
    ladder misplay to the match-scale read. When confidence is low the directed goal is withheld and the
    Pilot defers to the Turn Planner's own Goal Ladder plus the tuned weights (the fallback)."""
    mode: Plan = Plan.SETUP
    confidence: float = 0.0
    route: frozenset = field(default_factory=frozenset)   # opp card ids on my cheapest Prize Path
    route_turns: float | None = None                       # total feasibility turns of that route
    directed_goal: str | None = None                       # the goal-kind to steer the Turn Planner (S3)
    rationale: str = ""


@dataclass
class Ready:
    """When a Line's payoff counts as online: in play with >= `energy` attached. `energy=None`
    (the default) derives the threshold from the engine — the payoff's cheapest attack cost — so
    a Pokémon with a 1-Energy attack is 'online' at 1, not at the cost of its biggest attack."""
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
    """A named, testable claim that biases scoring (see common/CONTEXT.md).

    `when(ctx) -> bool` is the trigger; `weight` is the tunable surface; `status` tracks
    its test journey (assumed -> testing -> confirmed/refuted).
    """
    id: str
    rationale: str
    when: object                  # callable: (ctx) -> bool
    weight: float = 0.0
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
    weight_overrides: dict = field(default_factory=dict)  # authored per-deck seed overrides of (typically
                                                        # general) Hypothesis weights by id -- doctrine-driven,
                                                        # sparse, UNDER the learned tuned.json layer (ADR-0035)
