"""Traversal-order-independent chance identities for cgpy experiments."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from common.api import ActionIdentity


CHANCE_SCHEMA_VERSION = 1
_DOMAIN = b"cgpy-chance-sample"
_BRANCH_DOMAIN = b"cgpy-chance-branch"


class ChanceBranchKind(str, Enum):
    EXACT = "exact"
    SAMPLED = "sampled"


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


@dataclass(frozen=True, slots=True)
class ChanceBranchKey:
    kind: ChanceBranchKind
    method: str
    index: int
    root_state_key: str
    node_state_key: str
    action: ActionIdentity
    sample: ChanceSampleKey | None = None
    schema_version: int = CHANCE_SCHEMA_VERSION

    def __post_init__(self):
        if not isinstance(self.kind, ChanceBranchKind):
            raise TypeError("Chance Branch kind must be a Chance Branch Kind")
        if not self.method or self.index < 0 or self.schema_version < 1:
            raise ValueError("invalid Chance Branch Key")
        if not self.root_state_key or not self.node_state_key:
            raise ValueError("Chance Branch state keys must be non-empty")
        if not isinstance(self.action, ActionIdentity):
            raise TypeError("Chance Branch action must be an ActionIdentity")
        if self.kind is ChanceBranchKind.EXACT and self.sample is not None:
            raise ValueError("exact Chance Branch cannot carry a Chance Sample Key")
        if self.kind is ChanceBranchKind.SAMPLED:
            if not isinstance(self.sample, ChanceSampleKey):
                raise TypeError("sampled Chance Branch requires a Chance Sample Key")
            expected = (
                self.index, self.root_state_key, self.node_state_key, self.action)
            actual = (
                self.sample.sample_index, self.sample.root_state_key,
                self.sample.node_state_key, self.sample.action)
            if actual != expected:
                raise ValueError("Chance Branch does not match its Chance Sample Key")

    @classmethod
    def exact(cls, *, method: str, index: int, root_state_key: str,
              node_state_key: str, action: ActionIdentity) -> "ChanceBranchKey":
        return cls(
            ChanceBranchKind.EXACT, method, index, root_state_key,
            node_state_key, action)

    @classmethod
    def sampled(cls, sample: ChanceSampleKey, *, method: str) -> "ChanceBranchKey":
        return cls(
            ChanceBranchKind.SAMPLED, method, sample.sample_index,
            sample.root_state_key, sample.node_state_key, sample.action, sample)

    @property
    def digest(self) -> str:
        parts = (
            _BRANCH_DOMAIN,
            str(self.schema_version).encode("ascii"),
            self.kind.value.encode("ascii"),
            self.method.encode("utf-8"),
            str(self.index).encode("ascii"),
            self.root_state_key.encode("utf-8"),
            self.node_state_key.encode("utf-8"),
            json.dumps([self.action.kind, self.action.parts], sort_keys=True,
                       separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        )
        if self.sample is not None:
            parts += (self.sample.digest.encode("ascii"),)
        return hashlib.sha256(b"".join(_frame(part) for part in parts)).hexdigest()


__all__ = (
    "CHANCE_SCHEMA_VERSION", "ChanceBranchKey", "ChanceBranchKind", "ChanceSampleKey",
)
