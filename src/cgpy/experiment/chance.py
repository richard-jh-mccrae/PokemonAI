"""Traversal-order-independent chance identities for cgpy experiments."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from common.api import ActionIdentity


CHANCE_SCHEMA_VERSION = 1
_DOMAIN = b"cgpy-chance-sample"


def _frame(value: bytes) -> bytes:
    return len(value).to_bytes(8, "big") + value


@dataclass(frozen=True, slots=True)
class ChanceSampleKey:
    experiment_seed: int
    root_state_key: str
    node_state_key: str
    action: ActionIdentity
    sample_index: int
    schema_version: int = CHANCE_SCHEMA_VERSION

    def __post_init__(self):
        if self.sample_index < 0:
            raise ValueError("Chance Sample index must be non-negative")
        if self.schema_version < 1:
            raise ValueError("Chance Sample schema version must be positive")
        if not self.root_state_key or not self.node_state_key:
            raise ValueError("Chance Sample state keys must be non-empty")
        if not isinstance(self.action, ActionIdentity):
            raise TypeError("Chance Sample action must be an ActionIdentity")

    @property
    def digest(self) -> str:
        parts = (
            _DOMAIN,
            str(self.schema_version).encode("ascii"),
            str(self.experiment_seed).encode("ascii"),
            self.root_state_key.encode("utf-8"),
            self.node_state_key.encode("utf-8"),
            json.dumps([self.action.kind, self.action.parts], sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            str(self.sample_index).encode("ascii"),
        )
        return hashlib.sha256(b"".join(_frame(part) for part in parts)).hexdigest()

    @property
    def seed(self) -> int:
        return int(self.digest, 16)


__all__ = ("CHANCE_SCHEMA_VERSION", "ChanceSampleKey")
