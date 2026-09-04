from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from time import monotonic

from .contracts import EvaluationStatus


class DecisionDeadlineExceeded(RuntimeError):
    pass


class DecisionCancelled(RuntimeError):
    pass


class DecisionCancellation:
    def __init__(self):
        from threading import Event
        self._event = Event()

    def cancel(self):
        self._event.set()

    def check(self):
        if self._event.is_set():
            raise DecisionCancelled("decision cancelled")


class DecisionExecutionGuard:
    def __init__(self, limit_seconds: float, *, clock=monotonic):
        if not math.isfinite(limit_seconds) or limit_seconds <= 0:
            raise ValueError("decision containment limit must be positive and finite")
        self.limit_seconds = float(limit_seconds)
        self.clock = clock
        self.started = clock()

    def check(self) -> None:
        if self.clock() - self.started >= self.limit_seconds:
            raise DecisionDeadlineExceeded(
                f"decision failure containment expired after {self.limit_seconds:g}s")


def _positive(name, value):
    if value <= 0:
        raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class SearchConfiguration:
    schema_version: int = 5
    depth_budget: int = 16
    path_node_budget: int = 128
    node_budget: int = 4096
    time_budget_ms: int | None = 1_000
    chance_sample_budget: int = 12
    chance_seed: int = 582
    noise_tolerance: float = 1e-9
    tie_seed: int = 1178

    def __post_init__(self):
        if self.schema_version != 5:
            raise ValueError("unsupported search configuration schema version")
        for name in ("schema_version", "depth_budget",
                     "path_node_budget", "node_budget",
                     "chance_sample_budget"):
            _positive(name, getattr(self, name))
        if self.time_budget_ms is not None:
            _positive("time_budget_ms", self.time_budget_ms)
        if not math.isfinite(self.noise_tolerance) or self.noise_tolerance <= 0:
            raise ValueError("noise_tolerance must be positive and finite")

    @property
    def identity(self) -> str:
        return _identity(self)


@dataclass(frozen=True, slots=True)
class PolicyConfiguration:
    schema_version: int = 1
    noise_tolerance: float = 1e-9
    tie_seed: int = 1178
    accepted_statuses: tuple[str, ...] = ("complete", "estimated")
    unavailable_fallback: str = "neutral_lottery"

    def __post_init__(self):
        if self.schema_version != 1:
            raise ValueError("unsupported policy configuration schema version")
        _positive("schema_version", self.schema_version)
        if not math.isfinite(self.noise_tolerance) or self.noise_tolerance <= 0:
            raise ValueError("noise_tolerance must be positive and finite")
        if not self.accepted_statuses:
            raise ValueError("accepted_statuses cannot be empty")
        allowed = {status.value for status in EvaluationStatus}
        if any(status not in allowed for status in self.accepted_statuses):
            raise ValueError("accepted_statuses contains an unknown evaluation status")
        if self.unavailable_fallback != "neutral_lottery":
            raise ValueError("unknown unavailable fallback")

    @property
    def identity(self) -> str:
        return _identity(self)


@dataclass(frozen=True, slots=True)
class ComputeConfiguration:
    schema_version: int = 2
    search: SearchConfiguration = SearchConfiguration()
    policy: PolicyConfiguration = PolicyConfiguration()
    profile: str = "deployment"

    def __post_init__(self):
        if self.schema_version != 2:
            raise ValueError("unsupported compute configuration schema version")
        _positive("schema_version", self.schema_version)
        if self.profile not in {"deployment", "correction"}:
            raise ValueError("unknown compute profile")

    @property
    def identity(self) -> str:
        return _identity(self)


class BudgetController:
    def __init__(self, configuration: SearchConfiguration, *, clock=monotonic):
        self.configuration = configuration
        self.clock = clock
        self.started = clock()
        self.nodes = 0
        self.stop_reason = "complete"
        self.frontier: list[object] = []

    def check(self, frontier=None) -> bool:
        elapsed_ms = (self.clock() - self.started) * 1000
        if self.nodes >= self.configuration.node_budget:
            self.stop_reason = "node_budget"
        elif (self.configuration.time_budget_ms is not None
              and elapsed_ms >= self.configuration.time_budget_ms):
            self.stop_reason = "time_budget"
        else:
            return False
        if frontier is not None:
            self.frontier.append(frontier)
        return True

    def visit(self, frontier=None) -> bool:
        if self.check(frontier):
            return False
        self.nodes += 1
        return True


def _identity(value) -> str:
    blob = json.dumps(asdict(value), sort_keys=True).encode("utf-8")
    return hashlib.blake2b(blob, digest_size=8).hexdigest()


def correction_compute_profile() -> ComputeConfiguration:
    return ComputeConfiguration(
        search=SearchConfiguration(
            depth_budget=32,
            path_node_budget=512,
            node_budget=8_192,
            time_budget_ms=None,
            chance_sample_budget=12,
        ),
        policy=PolicyConfiguration(accepted_statuses=("complete", "estimated")),
        profile="correction",
    )


__all__ = ("BudgetController", "ComputeConfiguration", "DecisionCancellation", "DecisionCancelled",
           "DecisionDeadlineExceeded",
           "DecisionExecutionGuard", "PolicyConfiguration", "SearchConfiguration",
           "correction_compute_profile")
