from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class PuctConfiguration:
    profile: str = "inspection"
    simulation_limit: int = 10_000
    exploration: float = 8.0
    seed: int = 607
    transition_limit: int = 100_000
    evaluation_limit: int = 100_000
    chance_limit: int = 10_000
    chance_samples: int = 16
    state_limit: int = 50_000
    time_limit_seconds: float = 300.0
    prior_node_operations: int = 512
    prior_total_operations: int = 20_000
    prior_chance_samples: int = 12
    action_policy: str = "all_legal-v1"
    worker_count: int = 1
    batch_size: int = 1
    outstanding_limit: int = 32
    ipc_message_bytes: int = 16 * 1024 * 1024
    reuse_tree: bool = False
    node_limit: int = 50_000
    cache_limit: int = 150_000
    cleanup_reserve_seconds: float = 2.0
    remaining_match_seconds: float | None = None
    convergence_interval: int = 128
    convergence_limit: int = 128
    schema_version: int = 1

    def __post_init__(self):
        if self.profile not in ("play", "inspection", "evaluation"):
            raise ValueError("profile must be play, inspection, or evaluation")
        for name in ("simulation_limit", "transition_limit", "evaluation_limit", "chance_limit",
                     "chance_samples", "state_limit", "prior_node_operations",
                     "prior_total_operations", "prior_chance_samples"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("worker_count", "batch_size", "outstanding_limit", "ipc_message_bytes"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("node_limit", "cache_limit", "convergence_interval", "convergence_limit"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if type(self.reuse_tree) is not bool:
            raise ValueError("reuse_tree must be a boolean")
        if not math.isfinite(self.cleanup_reserve_seconds) or self.cleanup_reserve_seconds < 1:
            raise ValueError("cleanup reserve must be finite and at least one second")
        if self.remaining_match_seconds is not None and (
                not math.isfinite(self.remaining_match_seconds) or self.remaining_match_seconds <= 0):
            raise ValueError("remaining match allowance must be positive and finite")
        if max(self.worker_count, self.batch_size) > self.outstanding_limit:
            raise ValueError("worker and batch sizes must fit the outstanding task cap")
        if not math.isfinite(self.exploration) or self.exploration <= 0:
            raise ValueError("exploration must be positive and finite")
        if self.schema_version != 1:
            raise ValueError("unsupported PUCT configuration version")
        if not math.isfinite(self.time_limit_seconds) or self.time_limit_seconds <= 0:
            raise ValueError("time limit must be positive and finite")
        from common.decision.action_policy import SUPPORTED_ACTION_POLICIES
        if self.action_policy not in SUPPORTED_ACTION_POLICIES:
            raise ValueError("unsupported action policy")

    @property
    def identity(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()
