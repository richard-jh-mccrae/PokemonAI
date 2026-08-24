"""Immutable transition-result algebra shared by transition providers and consumers."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math


PROBABILITY_MIN = 0.0
PROBABILITY_MAX = 1.0
CHANCE_MASS_TOLERANCE = 1e-12
MINIMUM_CARD_ID = 1


class Actor(str, Enum):
    OURS = "ours"
    OPPONENT = "opponent"


@dataclass(frozen=True)
class Edge:
    label: str
    node: object

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("edge label is required")


@dataclass(frozen=True)
class WeightedEdge:
    probability: float
    label: str
    node: object

    def __post_init__(self) -> None:
        if not self.label or not (PROBABILITY_MIN <= float(self.probability) <= PROBABILITY_MAX):
            raise ValueError("chance edge needs a label and probability in [0, 1]")


@dataclass(frozen=True)
class Deterministic:
    state: object


@dataclass(frozen=True)
class Choice:
    actor: Actor
    children: tuple[Edge, ...]

    def __post_init__(self) -> None:
        if not self.children:
            raise ValueError("choice nodes cannot be empty")


@dataclass(frozen=True)
class Chance:
    children: tuple[WeightedEdge, ...]

    def __post_init__(self) -> None:
        if not self.children:
            raise ValueError("chance nodes cannot be empty")
        if not math.isclose(sum(edge.probability for edge in self.children), PROBABILITY_MAX,
                            rel_tol=PROBABILITY_MIN, abs_tol=CHANCE_MASS_TOLERANCE):
            raise ValueError("chance probabilities must sum to one")


@dataclass(frozen=True)
class RevealOutcome:
    probability: float
    choices: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.choices or not (PROBABILITY_MIN <= float(self.probability) <= PROBABILITY_MAX):
            raise ValueError("reveal outcomes need choices and probability in [0, 1]")


@dataclass(frozen=True)
class RevealChoice:
    """Chance reveals a set; the actor chooses the best continuation available in that set."""

    actor: Actor
    choices: tuple[Edge, ...]
    outcomes: tuple[RevealOutcome, ...]

    def __post_init__(self) -> None:
        labels = {edge.label for edge in self.choices}
        if not labels or not self.outcomes:
            raise ValueError("reveal choices and outcomes cannot be empty")
        if any(not set(outcome.choices) <= labels for outcome in self.outcomes):
            raise ValueError("reveal outcome references an undeclared choice")
        if not math.isclose(sum(outcome.probability for outcome in self.outcomes), PROBABILITY_MAX,
                            rel_tol=PROBABILITY_MIN, abs_tol=CHANCE_MASS_TOLERANCE):
            raise ValueError("reveal probabilities must sum to one")


@dataclass(frozen=True)
class Refresh:
    """An analytic pre-resolution shuffle-refresh with printed redraw-count branches.
    It carries no sampled cards or successor; the engine resolves those after commitment."""

    card_id: int
    draws: tuple[tuple[int, int], ...]
    opponent_shuffles: bool

    def __post_init__(self) -> None:
        if int(self.card_id) < MINIMUM_CARD_ID or not self.draws:
            raise ValueError("refresh nodes need a card identity and at least one draw branch")
        if any(int(mine) < 0 or int(theirs) < 0 for mine, theirs in self.draws):
            raise ValueError("refresh draw counts cannot be negative")


@dataclass(frozen=True)
class Terminal:
    state: object
    result: str


@dataclass(frozen=True)
class Unknown:
    reason: str
    missing_fact: str

    def __post_init__(self) -> None:
        if not self.reason or not self.missing_fact:
            raise ValueError("unknown nodes require reason and missing fact")


TransitionResult = Deterministic | Choice | Chance | RevealChoice | Refresh | Terminal | Unknown


__all__ = (
    "Actor", "Chance", "Choice", "Deterministic", "Edge", "Refresh", "RevealChoice",
    "RevealOutcome", "Terminal", "TransitionResult", "Unknown", "WeightedEdge",
)
