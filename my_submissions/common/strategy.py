"""The declarative Strategy a deck supplies to the Pilot (see common/CONTEXT.md, ADR-0008).

Pure data: structure + tunable numbers, no engine and no control flow. The deck's
doctrine is expressed here as lines, role assignments, params, and hypotheses; the shared
Pilot interprets it. This module also owns the closed Plan vocabulary.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Plan(enum.Enum):
    """The Pilot's current-turn strategic mode — a closed set."""
    SETUP = "SETUP"
    RACE = "RACE"
    STABILIZE = "STABILIZE"
    CLOSE = "CLOSE"


@dataclass
class Ready:
    """When a Line's payoff counts as online: in play with >= `energy` attached."""
    energy: int = 0


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
