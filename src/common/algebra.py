"""Immutable Bellman node and diagnostic algebra."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from .state import DecisionState


PROBABILITY_MIN = 0.0
PROBABILITY_MAX = 1.0
CHANCE_MASS_TOLERANCE = 1e-12
MINIMUM_CARD_ID = 1


class Actor(str, Enum):
    OURS = "ours"
    OPPONENT = "opponent"


@dataclass(frozen=True)
class Ledger:
    benefits: tuple[tuple[str, float], ...] = ()
    costs: tuple[tuple[str, float], ...] = ()
    continuation: float = 0.0

    def __post_init__(self) -> None:
        values = [value for _key, value in self.benefits + self.costs]
        values.append(self.continuation)
        if any(not math.isfinite(float(value)) for value in values):
            raise ValueError("ledger values must be finite")

    @property
    def immediate(self) -> float:
        return sum(value for _key, value in self.benefits) - sum(value for _key, value in self.costs)

    @property
    def total(self) -> float:
        return self.immediate + self.continuation

    def as_dict(self) -> dict:
        return {"benefits": dict(self.benefits), "costs": dict(self.costs),
                "immediate": self.immediate, "continuation": self.continuation,
                "total": self.total}


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
    state: "DecisionState"


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
    """A shuffle-refresh valued analytically before real randomness resolves.

    ``draws`` contains the printed own/opponent redraw counts for each equally likely card-effect
    branch (for example, the two sides of a coin).  It deliberately contains no sampled cards and
    no successor state: the live engine resolves the gamble after the solver commits the play.
    """

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
    state: "DecisionState"
    result: str
    ledger: Ledger = Ledger()


@dataclass(frozen=True)
class Unknown:
    reason: str
    missing_fact: str

    def __post_init__(self) -> None:
        if not self.reason or not self.missing_fact:
            raise ValueError("unknown nodes require reason and missing fact")


TransitionResult = Deterministic | Choice | Chance | RevealChoice | Refresh | Terminal | Unknown


@dataclass(frozen=True)
class ActionDiagnostic:
    action_key: str
    ledger: Ledger
    complete: bool
    reason: str = ""
    branches: tuple[Mapping, ...] = ()
    decisions: float = 0.0


@dataclass(frozen=True)
class RootDiagnostics:
    chosen_key: str
    end: ActionDiagnostic
    alternatives: tuple[ActionDiagnostic, ...]
    nodes: int
    cache_hits: int
    stopped_reason: str


__all__ = (
    "ActionDiagnostic", "Actor", "Chance", "Choice", "Deterministic", "Edge", "Ledger",
    "Refresh", "RevealChoice", "RevealOutcome", "RootDiagnostics", "Terminal", "TransitionResult", "Unknown",
    "WeightedEdge",
)
