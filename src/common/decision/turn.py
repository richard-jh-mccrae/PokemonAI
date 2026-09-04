"""Engine-independent node identities for bounded current-turn search."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Callable, Protocol
from common.api import ActionIdentity

from common.observation import ObservationState


SEARCH_STATE_KEY_SCHEMA_VERSION = 1


class TurnAction(Protocol):
    identity: ActionIdentity
    selection: tuple[int, ...]


class NodeKind(str, Enum):
    PLAYER_DECISION = "player_decision"
    FORCED_DECISION = "forced_decision"
    CHANCE = "chance"
    TERMINAL = "terminal"
    INFORMATION_BOUNDARY = "information_boundary"
    TURN_BOUNDARY = "turn_boundary"
    UNAVAILABLE = "unavailable"


class BoundaryReason(str, Enum):
    SHUFFLE_DRAW = "shuffle_draw"
    RANDOM_REVEAL = "random_reveal"
    OPPONENT_DECISION = "opponent_decision"
    TURN_TRANSITION = "turn_transition"
    UNSUPPORTED_HIDDEN_TRANSITION = "unsupported_hidden_transition"


class SearchContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SearchStateKey:
    digest: str
    schema_version: int = SEARCH_STATE_KEY_SCHEMA_VERSION

    def __post_init__(self):
        if self.schema_version < 1 or len(self.digest) != 64:
            raise ValueError("invalid Search State Key")

    def __str__(self) -> str:
        return self.digest


@dataclass(frozen=True, slots=True)
class SearchNode:
    kind: NodeKind
    actor_seat: int | None
    perspective_seat: int
    observation: ObservationState
    state_key: SearchStateKey
    root_turn: int
    boundary_reason: BoundaryReason | None
    failure: str | None
    _handle: object = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class ChancePlan:
    identity: str
    method: str
    probabilities: tuple[float, ...]
    estimated: bool

    def __post_init__(self):
        if not self.identity or not self.method or not self.probabilities:
            raise SearchContractError("chance plan requires identity, method, and outcomes")
        if any(not math.isfinite(p) or p <= 0 for p in self.probabilities):
            raise SearchContractError("chance probabilities must be positive and finite")
        if not math.isclose(math.fsum(self.probabilities), 1.0, abs_tol=1e-12, rel_tol=0):
            raise SearchContractError("chance plan must preserve full probability mass")


@dataclass(frozen=True, slots=True)
class ProviderJob:
    function: Callable
    arguments: tuple
    state_capacity: int
    operation_capacity: int = 1
    affinity: str | None = None


@dataclass(frozen=True, slots=True)
class ProviderCompletion:
    value: object
    operation_units: int = 1
    state_capacity: int = 1
    retained_states: int | None = None

    def __post_init__(self):
        if not 0 <= self.operation_units or not 0 <= self.state_capacity:
            raise ValueError("provider completion usage cannot be negative")
        if self.retained_states is not None and self.retained_states < 0:
            raise ValueError("provider retained state count cannot be negative")
