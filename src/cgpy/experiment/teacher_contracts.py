"""Versioned hidden-safe contracts for the Within-Horizon Teacher."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from enum import Enum

from common.api import ActionIdentity
from common.decision import EvaluationStatus

from .action_policy import ALL_LEGAL_ACTION_POLICY, SUPPORTED_ACTION_POLICIES
from .contracts import NodeKind


TEACHER_RESULT_SCHEMA = "cgpy-within-horizon-teacher-result"
TEACHER_RESULT_SCHEMA_VERSION = 1


class TeacherCoverage(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"


class TeacherStopReason(str, Enum):
    COMPLETE = "complete"
    NODE_CAP = "node_cap"
    TIME_CAP = "time_cap"
    PATH_CAP = "path_cap"
    CHANCE_CAP = "chance_cap"
    CYCLE = "cycle"
    EMPTY_DECISION = "empty_decision"
    UNAVAILABLE = "unavailable"
    EVALUATION_UNAVAILABLE = "evaluation_unavailable"
    TRANSITION_FAILURE = "transition_failure"
    CHANCE_INCOMPLETE = "chance_incomplete"
    WORKER_TIMEOUT = "worker_timeout"
    WORKER_ERROR = "worker_error"


def _positive(name, value) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class TeacherSearchConfiguration:
    schema_version: int = 1
    node_cap: int = 100_000
    path_node_cap: int = 512
    chance_branch_cap: int = 100_000
    exact_outcome_limit: int = 16
    chance_sample_count: int = 12
    time_cap_seconds: float = 600.0
    noise_tolerance: float = 1e-9
    tie_seed: int = 1178
    action_policy: str = ALL_LEGAL_ACTION_POLICY

    def __post_init__(self):
        if self.schema_version != 1:
            raise ValueError("unsupported Teacher Search Configuration schema")
        for name in (
                "schema_version", "node_cap", "path_node_cap", "chance_branch_cap",
                "exact_outcome_limit", "chance_sample_count"):
            _positive(name, getattr(self, name))
        if not math.isfinite(self.time_cap_seconds) or self.time_cap_seconds <= 0:
            raise ValueError("time_cap_seconds must be positive and finite")
        if not math.isfinite(self.noise_tolerance) or self.noise_tolerance <= 0:
            raise ValueError("noise_tolerance must be positive and finite")
        if self.action_policy not in SUPPORTED_ACTION_POLICIES:
            raise ValueError(f"unsupported Teacher action policy {self.action_policy!r}")

    @property
    def identity(self) -> str:
        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.blake2b(encoded, digest_size=8).hexdigest()


@dataclass(frozen=True, slots=True)
class TeacherPolicyEntry:
    state_key: str
    action: ActionIdentity
    expected_value: float
    value_quality: EvaluationStatus
    indifference_set: tuple[ActionIdentity, ...] = ()


@dataclass(frozen=True, slots=True)
class TeacherLeaf:
    state_key: str
    kind: NodeKind
    probability: float
    value: float
    value_quality: EvaluationStatus


@dataclass(frozen=True, slots=True)
class TeacherPathStep:
    state_key: str
    kind: NodeKind
    action: ActionIdentity | None = None
    branch_keys: tuple[str, ...] = ()
    probability: float | None = None


@dataclass(frozen=True, slots=True)
class TeacherRootAction:
    action: ActionIdentity
    coverage: TeacherCoverage
    value_quality: EvaluationStatus
    expected_value: float | None
    delta: float | None
    stop_reason: TeacherStopReason
    policy: tuple[TeacherPolicyEntry, ...] = ()
    leaves: tuple[TeacherLeaf, ...] = ()
    principal_variation: tuple[TeacherPathStep, ...] = ()
    best_full_sequence: tuple[ActionIdentity, ...] | None = None
    failure: str | None = None


@dataclass(frozen=True, slots=True)
class TeacherSearchStatistics:
    nodes_visited: int = 0
    leaf_evaluations: int = 0
    chance_nodes: int = 0
    chance_branches: int = 0
    cache_hits: int = 0
    transpositions: int = 0
    memo_entries: int = 0
    cycles: int = 0
    elapsed_seconds: float = 0.0


def _action_document(action: ActionIdentity | None):
    if action is None:
        return None
    return {"kind": action.kind, "parts": action.parts}


def _tupleize(value):
    if isinstance(value, list):
        return tuple(_tupleize(child) for child in value)
    if isinstance(value, dict):
        return {key: _tupleize(child) for key, child in value.items()}
    return value


def _action_from(document) -> ActionIdentity | None:
    if document is None:
        return None
    return ActionIdentity(str(document["kind"]), _tupleize(document.get("parts", ())))


def _policy_document(item: TeacherPolicyEntry) -> dict:
    return {
        "state_key": item.state_key, "action": _action_document(item.action),
        "expected_value": item.expected_value, "value_quality": item.value_quality.value,
        "indifference_set": [_action_document(action) for action in item.indifference_set],
    }


def _policy_from(document: dict) -> TeacherPolicyEntry:
    return TeacherPolicyEntry(
        str(document["state_key"]), _action_from(document["action"]),
        float(document["expected_value"]), EvaluationStatus(document["value_quality"]),
        tuple(_action_from(action) for action in document["indifference_set"]),
    )


def _leaf_document(item: TeacherLeaf) -> dict:
    return {
        "state_key": item.state_key, "kind": item.kind.value,
        "probability": item.probability, "value": item.value,
        "value_quality": item.value_quality.value,
    }


def _leaf_from(document: dict) -> TeacherLeaf:
    return TeacherLeaf(
        str(document["state_key"]), NodeKind(document["kind"]),
        float(document["probability"]), float(document["value"]),
        EvaluationStatus(document["value_quality"]),
    )


def _step_document(item: TeacherPathStep) -> dict:
    return {
        "state_key": item.state_key, "kind": item.kind.value,
        "action": _action_document(item.action), "branch_keys": item.branch_keys,
        "probability": item.probability,
    }


def _step_from(document: dict) -> TeacherPathStep:
    probability = document["probability"]
    return TeacherPathStep(
        str(document["state_key"]), NodeKind(document["kind"]),
        _action_from(document["action"]), tuple(document["branch_keys"]),
        None if probability is None else float(probability),
    )


def _root_action_document(item: TeacherRootAction) -> dict:
    return {
        "action": _action_document(item.action), "coverage": item.coverage.value,
        "value_quality": item.value_quality.value, "expected_value": item.expected_value,
        "delta": item.delta, "stop_reason": item.stop_reason.value,
        "policy": [_policy_document(value) for value in item.policy],
        "leaves": [_leaf_document(value) for value in item.leaves],
        "principal_variation": [_step_document(value) for value in item.principal_variation],
        "best_full_sequence": (None if item.best_full_sequence is None else
                               [_action_document(value) for value in item.best_full_sequence]),
        "failure": item.failure,
    }


def _root_action_from(document: dict) -> TeacherRootAction:
    expected = document["expected_value"]
    delta = document["delta"]
    sequence = document["best_full_sequence"]
    return TeacherRootAction(
        _action_from(document["action"]), TeacherCoverage(document["coverage"]),
        EvaluationStatus(document["value_quality"]),
        None if expected is None else float(expected),
        None if delta is None else float(delta), TeacherStopReason(document["stop_reason"]),
        tuple(_policy_from(value) for value in document["policy"]),
        tuple(_leaf_from(value) for value in document["leaves"]),
        tuple(_step_from(value) for value in document["principal_variation"]),
        None if sequence is None else tuple(_action_from(value) for value in sequence),
        document.get("failure"),
    )


@dataclass(frozen=True, slots=True)
class TeacherSearchResult:
    root_state_key: str
    snapshot_id: str | None
    experiment_seed: int
    configuration_identity: str
    evaluator_identity: str
    evaluation_model_identity: str
    baseline_identity: str | None
    baseline_value: float | None
    baseline_quality: EvaluationStatus
    root_actions: tuple[TeacherRootAction, ...]
    preferred_action: ActionIdentity | None
    indifference_set: tuple[ActionIdentity, ...]
    selected_policy: tuple[TeacherPolicyEntry, ...]
    leaves: tuple[TeacherLeaf, ...]
    principal_variation: tuple[TeacherPathStep, ...]
    best_full_sequence: tuple[ActionIdentity, ...] | None
    coverage: TeacherCoverage
    value_quality: EvaluationStatus
    stop_reason: TeacherStopReason
    statistics: TeacherSearchStatistics
    benchmark_ready: bool
    failure: str | None = None
    schema_version: int = TEACHER_RESULT_SCHEMA_VERSION

    def document(self, *, semantic: bool = False) -> dict:
        statistics = asdict(self.statistics)
        if semantic:
            statistics.pop("elapsed_seconds")
        return {
            "schema": TEACHER_RESULT_SCHEMA, "schema_version": self.schema_version,
            "root_state_key": self.root_state_key, "snapshot_id": self.snapshot_id,
            "experiment_seed": self.experiment_seed,
            "configuration_identity": self.configuration_identity,
            "evaluator_identity": self.evaluator_identity,
            "evaluation_model_identity": self.evaluation_model_identity,
            "baseline_identity": self.baseline_identity,
            "baseline_value": self.baseline_value,
            "baseline_quality": self.baseline_quality.value,
            "root_actions": [_root_action_document(item) for item in self.root_actions],
            "preferred_action": _action_document(self.preferred_action),
            "indifference_set": [_action_document(item) for item in self.indifference_set],
            "selected_policy": [_policy_document(item) for item in self.selected_policy],
            "leaves": [_leaf_document(item) for item in self.leaves],
            "principal_variation": [_step_document(item) for item in self.principal_variation],
            "best_full_sequence": (None if self.best_full_sequence is None else
                                   [_action_document(item) for item in self.best_full_sequence]),
            "coverage": self.coverage.value, "value_quality": self.value_quality.value,
            "stop_reason": self.stop_reason.value, "statistics": statistics,
            "benchmark_ready": self.benchmark_ready, "failure": self.failure,
        }

    @property
    def semantic_identity(self) -> str:
        encoded = json.dumps(
            self.document(semantic=True), sort_keys=True,
            separators=(",", ":"), ensure_ascii=False).encode()
        return hashlib.sha256(encoded).hexdigest()

    def dumps(self) -> str:
        return json.dumps(
            self.document(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def loads(cls, encoded: str) -> "TeacherSearchResult":
        document = json.loads(encoded)
        if (document.get("schema") != TEACHER_RESULT_SCHEMA
                or document.get("schema_version") != TEACHER_RESULT_SCHEMA_VERSION):
            raise ValueError("unsupported Within-Horizon Teacher Result schema")
        baseline = document["baseline_value"]
        sequence = document["best_full_sequence"]
        return cls(
            str(document["root_state_key"]), document["snapshot_id"],
            int(document["experiment_seed"]), str(document["configuration_identity"]),
            str(document["evaluator_identity"]), str(document["evaluation_model_identity"]),
            document["baseline_identity"], None if baseline is None else float(baseline),
            EvaluationStatus(document["baseline_quality"]),
            tuple(_root_action_from(item) for item in document["root_actions"]),
            _action_from(document["preferred_action"]),
            tuple(_action_from(item) for item in document["indifference_set"]),
            tuple(_policy_from(item) for item in document["selected_policy"]),
            tuple(_leaf_from(item) for item in document["leaves"]),
            tuple(_step_from(item) for item in document["principal_variation"]),
            None if sequence is None else tuple(_action_from(item) for item in sequence),
            TeacherCoverage(document["coverage"]),
            EvaluationStatus(document["value_quality"]),
            TeacherStopReason(document["stop_reason"]),
            TeacherSearchStatistics(**document["statistics"]),
            bool(document["benchmark_ready"]), document.get("failure"),
            int(document["schema_version"]),
        )


__all__ = (
    "TEACHER_RESULT_SCHEMA", "TEACHER_RESULT_SCHEMA_VERSION", "TeacherCoverage",
    "TeacherLeaf", "TeacherPathStep", "TeacherPolicyEntry", "TeacherRootAction",
    "TeacherSearchConfiguration", "TeacherSearchResult", "TeacherSearchStatistics",
    "TeacherStopReason",
)
