from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from time import monotonic

from .contracts import EvaluationStatus


def _positive(name, value):
    if value <= 0:
        raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class SearchConfiguration:
    schema_version: int = 1
    depth_budget: int = 16
    path_node_budget: int = 128
    node_budget: int = 4096
    time_budget_ms: int = 100_000
    chance_sample_budget: int = 24
    chance_seed: int = 582
    noise_tolerance: float = 1e-9
    tie_seed: int = 1178

    def __post_init__(self):
        for name in ("schema_version", "depth_budget", "path_node_budget", "node_budget",
                     "time_budget_ms", "chance_sample_budget"):
            _positive(name, getattr(self, name))
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
    schema_version: int = 1
    search: SearchConfiguration = SearchConfiguration()
    policy: PolicyConfiguration = PolicyConfiguration()

    def __post_init__(self):
        _positive("schema_version", self.schema_version)

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

    def visit(self, frontier=None) -> bool:
        elapsed_ms = (self.clock() - self.started) * 1000
        if self.nodes >= self.configuration.node_budget:
            self.stop_reason = "node_budget"
        elif elapsed_ms >= self.configuration.time_budget_ms:
            self.stop_reason = "time_budget"
        else:
            self.nodes += 1
            return True
        if frontier is not None:
            self.frontier.append(frontier)
        return False


def _identity(value) -> str:
    blob = json.dumps(asdict(value), sort_keys=True).encode("utf-8")
    return hashlib.blake2b(blob, digest_size=8).hexdigest()


__all__ = ("BudgetController", "ComputeConfiguration", "PolicyConfiguration",
           "SearchConfiguration")
