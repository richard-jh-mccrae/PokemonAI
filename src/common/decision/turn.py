"""Engine-independent node identities for bounded current-turn search."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from importlib import import_module
from typing import Callable, Protocol, runtime_checkable
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
class EngineBackendDescriptor:
    name: str
    api_module: str
    implementation_identity: str
    import_root: str

    def __post_init__(self):
        if not all((self.name, self.api_module, self.implementation_identity, self.import_root)):
            raise ValueError("engine backend descriptor fields cannot be empty")

    def resolve(self):
        try:
            module = import_module(self.api_module)
        except Exception as exc:
            raise SearchContractError(
                f"engine backend {self.name!r} is unavailable: {type(exc).__name__}") from exc
        actual = getattr(module, "ENGINE_IMPLEMENTATION_IDENTITY", None)
        if actual != self.implementation_identity:
            raise SearchContractError(
                f"engine backend {self.name!r} resolved implementation {actual!r}, "
                f"expected {self.implementation_identity!r}")
        return module


_BACKENDS: dict[str, EngineBackendDescriptor] = {}


def register_engine_backend(descriptor: EngineBackendDescriptor) -> None:
    previous = _BACKENDS.setdefault(descriptor.name, descriptor)
    if previous != descriptor:
        raise ValueError(f"engine backend {descriptor.name!r} is already registered differently")


def engine_backend(name: str) -> EngineBackendDescriptor:
    try:
        return _BACKENDS[str(name)]
    except KeyError:
        raise ValueError(f"engine backend {name!r} is unavailable") from None


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


@runtime_checkable
class TurnSearchProvider(Protocol):
    identity: str
    root: SearchNode
    retained_states: int

    def legal_actions(self, node: SearchNode) -> tuple: ...
    def ledger_state(self, node: SearchNode): ...
    def chance_plan(self, node: SearchNode, sample_count: int) -> ChancePlan: ...
    def reuse_from(self, previous, node: SearchNode) -> bool: ...
    def reproduction_input(self) -> str: ...
    def close(self) -> None: ...


@runtime_checkable
class WorkerTurnSearchProvider(TurnSearchProvider, Protocol):
    peak_retained_states: int

    def work_item(self, node: SearchNode, operation: str, arguments: tuple) -> ProviderJob: ...
    def accept_work(self, result): ...
    def observe_completion(self, completion: ProviderCompletion,
                           affinity: str | None = None) -> None: ...
    def release_worker_states(self) -> int: ...


@runtime_checkable
class DirectTurnSearchProvider(TurnSearchProvider, Protocol):
    def transition(self, node: SearchNode, action: TurnAction): ...
    def sample_for_search(self, node: SearchNode, experiment_seed: int,
                          sample_index: int): ...


NATIVE_ENGINE_BACKEND = EngineBackendDescriptor(
    "native-cg", "cg.api", "native-cg-api-v1", "cg")
register_engine_backend(NATIVE_ENGINE_BACKEND)


__all__ = (
    "BoundaryReason", "ChancePlan", "DirectTurnSearchProvider", "EngineBackendDescriptor",
    "NATIVE_ENGINE_BACKEND", "NodeKind", "ProviderCompletion", "ProviderJob",
    "SearchContractError", "SearchNode", "SearchStateKey", "TurnAction",
    "TurnSearchProvider", "WorkerTurnSearchProvider", "engine_backend",
    "register_engine_backend",
)
