"""Immutable PUCT evidence shared by search, selection, and inspection."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import TYPE_CHECKING

from common.api import ActionIdentity

if TYPE_CHECKING:
    from .contracts import PolicyDistribution


class PuctOutcome(str, Enum):
    SEARCHED = "searched"
    FORCED = "forced"
    INITIALIZATION_DEGRADED = "initialization_degraded"
    HARD_FAILURE = "hard_failure"
    CANCELLED = "cancelled"

    @property
    def permits_action(self) -> bool:
        return self in (self.SEARCHED, self.FORCED)


@dataclass(frozen=True, slots=True)
class PuctEdgeStatistics:
    visits: int
    value_sum: float
    inherited_visits: int = 0
    exclusion: str | None = None
    tie_break: str = ""

    def __post_init__(self):
        if type(self.visits) is not int or not 0 <= self.inherited_visits <= self.visits:
            raise ValueError("invalid completed PUCT visit counts")
        if not math.isfinite(self.value_sum) or (self.visits == 0 and self.value_sum != 0):
            raise ValueError("PUCT returns require completed visits and finite values")

    @property
    def mean_value(self) -> float | None:
        return self.value_sum / self.visits if self.visits else None


@dataclass(frozen=True, slots=True)
class PuctPathStep:
    action: ActionIdentity | None
    decision_key: str
    chance_slot: int | None = None
    probability: float | None = None


class PuctPathStop(str, Enum):
    NO_COMPLETED_EDGE = "no_completed_edge"
    UNRESOLVED_CHANCE = "unresolved_chance"
    UNEVALUATED_SUCCESSOR = "unevaluated_successor"
    CYCLE = "cycle"
    TURN_BOUNDARY = "turn_boundary"
    INFORMATION_BOUNDARY = "information_boundary"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class PuctWork:
    transitions: int = 0
    evaluations: int = 0
    chances: int = 0
    state_capacity_charged: int = 0

    def __post_init__(self):
        values = (self.transitions, self.evaluations, self.chances, self.state_capacity_charged)
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("PUCT work counters must be nonnegative integers")


@dataclass(frozen=True, slots=True)
class PuctResourceUsage:
    category: str
    reserved: int
    attempted: int
    completed: int
    cancelled_unused: int
    uncertain: int

    def __post_init__(self):
        values = (self.reserved, self.attempted, self.completed,
                  self.cancelled_unused, self.uncertain)
        if (not self.category or any(type(value) is not int or value < 0 for value in values)
                or self.completed > self.attempted
                or self.attempted + self.cancelled_unused + self.uncertain > self.reserved):
            raise ValueError("invalid PUCT resource accounting")


@dataclass(frozen=True, slots=True)
class PuctChanceStatistics:
    identity: str
    method: str
    estimated: bool
    configured_slots: int
    resolved_slots: int
    distinct_successors: int
    completed_visits: int


@dataclass(frozen=True, slots=True)
class PuctPriorEvidence:
    decision_key: str
    distribution: PolicyDistribution
    preparation_limited: bool = False


@dataclass(frozen=True, slots=True)
class PuctTiming:
    prior_seconds: float
    search_seconds: float
    overhead_seconds: float
    elapsed_seconds: float
    overlapping_worker_prior_seconds: float = 0.0
    overlapping_worker_search_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class PuctTransport:
    worker_count: int = 0
    startup_seconds: float = 0.0
    request_messages: int = 0
    response_messages: int = 0
    request_bytes: int = 0
    response_bytes: int = 0


@dataclass(frozen=True, slots=True)
class PuctConvergence:
    simulations: int
    visits: tuple[int, ...]
    means: tuple[float | None, ...]


@dataclass(frozen=True, slots=True)
class PuctInspectionComponent:
    key: str
    activation: float
    coefficient: float
    value: float


@dataclass(frozen=True, slots=True)
class PuctInspectionValuation:
    total: float
    status: str
    components: tuple[PuctInspectionComponent, ...] = ()
    gaps: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PuctInspectionNode:
    node_id: int
    state_key: str
    decision_key: str
    observation: str
    kind: str
    actor_seat: int | None
    boundary_reason: str | None
    depth: int | None
    visits: int
    outgoing_visits: int
    selections: int
    valuation: PuctInspectionValuation | None


@dataclass(frozen=True, slots=True)
class PuctInspectionEdge:
    source_node_id: int
    target_node_id: int | None
    kind: str
    action: ActionIdentity | None = None
    selection: tuple[int, ...] = ()
    prior: float | None = None
    visits: int = 0
    value_sum: float = 0.0
    inherited_visits: int = 0
    exclusion: str | None = None
    chance_slot: int | None = None
    probability: float | None = None

    @property
    def mean_value(self) -> float | None:
        return self.value_sum / self.visits if self.visits else None


@dataclass(frozen=True, slots=True)
class PuctInspection:
    root_node_id: int
    nodes: tuple[PuctInspectionNode, ...]
    edges: tuple[PuctInspectionEdge, ...]
    schema_version: int = 2


@dataclass(frozen=True, slots=True)
class PuctEvidence:
    simulations: int
    principal_variation: tuple[PuctPathStep, ...]
    configuration_identity: str
    work: PuctWork = PuctWork()
    chance_nodes: tuple[PuctChanceStatistics, ...] = ()
    schema_version: int = 2
    outcome: PuctOutcome = PuctOutcome.SEARCHED
    prior_distributions: tuple[PuctPriorEvidence, ...] = ()
    timing: PuctTiming | None = None
    batches: int = 0
    peak_pending: int = 0
    reuse_reason: str = "fresh_requested"
    inherited_visits: int = 0
    resources: tuple[PuctResourceUsage, ...] = ()
    convergence: tuple[PuctConvergence, ...] = ()
    tree_nodes: int = 0
    cache_entries: int = 0
    cache_capacity_charged: int = 0
    retained_engine_states: int | None = None
    peak_retained_engine_states: int | None = None
    principal_variation_stop_reason: PuctPathStop = PuctPathStop.NO_COMPLETED_EDGE
    reproduction_input: str | None = None
    inspection: PuctInspection | None = None
    transport: PuctTransport = PuctTransport()
