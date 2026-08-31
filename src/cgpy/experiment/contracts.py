"""Public wire contracts for turn search."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from common.api import ActionIdentity
from common.observation import ObservationState

from .chance import ChanceBranchKey, ChanceBranchKind, ChanceSampleKey


SEARCH_STATE_KEY_SCHEMA_VERSION = 1
PRIMITIVE_TRANSITION_SCHEMA_VERSION = 1
PRIMITIVE_TRANSITION_SCHEMA = "cgpy-primitive-transition"
CHANCE_TRANSITION_SCHEMA_VERSION = 2
CHANCE_TRANSITION_SCHEMA = "cgpy-chance-transition"
CHANCE_EXPANSION_SCHEMA_VERSION = 1
CHANCE_EXPANSION_SCHEMA = "cgpy-chance-expansion"


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


class ChanceExpansionStatus(str, Enum):
    COMPLETE = "complete"
    ESTIMATED = "estimated"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ChanceExpansionRequest:
    experiment_seed: int
    exact_outcome_limit: int = 16
    sample_count: int = 12

    def __post_init__(self):
        if self.exact_outcome_limit < 1:
            raise ValueError("exact outcome limit must be positive")
        if self.sample_count < 1:
            raise ValueError("sample count must be positive")


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


def _key_document(value: SearchStateKey) -> dict:
    return {"digest": value.digest, "schema_version": value.schema_version}


def _action_document(value: ActionIdentity) -> dict:
    return {"kind": value.kind, "parts": value.parts}


def _tupleize(value):
    if isinstance(value, list):
        return tuple(_tupleize(child) for child in value)
    if isinstance(value, dict):
        return {key: _tupleize(child) for key, child in value.items()}
    return value


def _action_from(document: dict) -> ActionIdentity:
    return ActionIdentity(str(document["kind"]), _tupleize(document["parts"]))


def _sample_document(value: ChanceSampleKey) -> dict:
    return {
        "experiment_seed": value.experiment_seed,
        "root_state_key": value.root_state_key,
        "node_state_key": value.node_state_key,
        "action": _action_document(value.action),
        "sample_index": value.sample_index,
        "schema_version": value.schema_version,
    }


def _sample_from(document: dict) -> ChanceSampleKey:
    return ChanceSampleKey(
        int(document["experiment_seed"]), str(document["root_state_key"]),
        str(document["node_state_key"]), _action_from(document["action"]),
        int(document["sample_index"]), int(document["schema_version"]),
    )


def _branch_document(value: ChanceBranchKey) -> dict:
    document = {
        "kind": value.kind.value,
        "method": value.method,
        "index": value.index,
        "root_state_key": value.root_state_key,
        "node_state_key": value.node_state_key,
        "action": _action_document(value.action),
        "schema_version": value.schema_version,
    }
    if value.sample is not None:
        document["sample"] = _sample_document(value.sample)
    return document


def _branch_from(document: dict) -> ChanceBranchKey:
    sample = document.get("sample")
    return ChanceBranchKey(
        ChanceBranchKind(document["kind"]), str(document["method"]),
        int(document["index"]), str(document["root_state_key"]),
        str(document["node_state_key"]), _action_from(document["action"]),
        None if sample is None else _sample_from(sample),
        int(document["schema_version"]),
    )


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _validate_result(parent: SearchStateKey, result: SearchStateKey,
                     version: int, label: str) -> None:
    if version < 1:
        raise ValueError(f"{label} schema version must be positive")
    if not isinstance(parent, SearchStateKey) or not isinstance(result, SearchStateKey):
        raise TypeError(f"{label} keys must be Search State Keys")


def _result_document(value, schema: str) -> dict:
    return {
        "schema": schema,
        "schema_version": value.schema_version,
        "parent_state_key": _key_document(value.parent_state_key),
        "result_state_key": _key_document(value.result_state_key),
        "result_kind": value.result_kind.value,
        "boundary_reason": (None if value.boundary_reason is None
                            else value.boundary_reason.value),
        "failure": value.failure,
    }


def _result_from(document: dict, schema: str, label: str) -> tuple:
    if document["schema"] != schema:
        raise ValueError(f"unsupported {label} schema")
    reason = document["boundary_reason"]
    return (
        SearchStateKey(**document["parent_state_key"]),
        SearchStateKey(**document["result_state_key"]),
        NodeKind(document["result_kind"]),
        None if reason is None else BoundaryReason(reason),
        document.get("failure"), int(document["schema_version"]),
    )


@dataclass(frozen=True, slots=True)
class PrimitiveTransition:
    parent_state_key: SearchStateKey
    action: ActionIdentity
    result_state_key: SearchStateKey
    result_kind: NodeKind
    boundary_reason: BoundaryReason | None
    failure: str | None
    node: SearchNode | None = field(default=None, repr=False, compare=False)
    schema_version: int = PRIMITIVE_TRANSITION_SCHEMA_VERSION

    def __post_init__(self):
        _validate_result(
            self.parent_state_key, self.result_state_key,
            self.schema_version, "Primitive Transition")
        if not isinstance(self.action, ActionIdentity):
            raise TypeError("Primitive Transition action must be an ActionIdentity")

    def dumps(self) -> str:
        document = _result_document(self, PRIMITIVE_TRANSITION_SCHEMA)
        document["action"] = _action_document(self.action)
        return _canonical(document)

    @classmethod
    def loads(cls, encoded: str) -> "PrimitiveTransition":
        try:
            document = json.loads(encoded)
            parent, result, kind, reason, failure, version = _result_from(
                document, PRIMITIVE_TRANSITION_SCHEMA, "Primitive Transition")
            return cls(
                parent, _action_from(document["action"]), result, kind,
                reason, failure, None, version,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SearchContractError(f"invalid Primitive Transition: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ChanceTransition:
    parent_state_key: SearchStateKey
    sample: ChanceSampleKey | None
    outcome: ActionIdentity | None
    result_state_key: SearchStateKey
    result_kind: NodeKind
    boundary_reason: BoundaryReason | None
    failure: str | None
    node: SearchNode | None = field(default=None, repr=False, compare=False)
    schema_version: int = CHANCE_TRANSITION_SCHEMA_VERSION
    branch_key: ChanceBranchKey | None = None
    method: str = "coin"
    probability: float = 1.0

    def __post_init__(self):
        _validate_result(
            self.parent_state_key, self.result_state_key,
            self.schema_version, "Chance Transition")
        if not 0.0 <= self.probability <= 1.0:
            raise ValueError("Chance Transition probability must be within [0, 1]")
        if not self.method:
            raise ValueError("Chance Transition method must be non-empty")
        if self.schema_version == 1:
            if not isinstance(self.sample, ChanceSampleKey):
                raise TypeError("Chance Transition v1 sample must be a Chance Sample Key")
            if not isinstance(self.outcome, ActionIdentity):
                raise TypeError("Chance Transition v1 outcome must be an ActionIdentity")
        elif self.schema_version == 2:
            if not isinstance(self.branch_key, ChanceBranchKey):
                raise TypeError("Chance Transition v2 branch must be a Chance Branch Key")
            if self.branch_key.method != self.method:
                raise ValueError("Chance Transition method does not match its branch")
            if self.sample is not None and self.sample != self.branch_key.sample:
                raise ValueError("Chance Transition sample does not match its branch")
            if self.outcome is not None and not isinstance(self.outcome, ActionIdentity):
                raise TypeError("Chance Transition outcome must be an ActionIdentity")
        else:
            raise ValueError("unsupported Chance Transition schema version")

    def dumps(self) -> str:
        document = _result_document(self, CHANCE_TRANSITION_SCHEMA)
        if self.schema_version == 1:
            document.update({
                "sample": _sample_document(self.sample),
                "outcome": _action_document(self.outcome),
            })
        else:
            document.update({
                "branch_key": _branch_document(self.branch_key),
                "method": self.method,
                "probability": self.probability,
            })
            if self.outcome is not None:
                document["outcome"] = _action_document(self.outcome)
        return _canonical(document)

    @classmethod
    def loads(cls, encoded: str) -> "ChanceTransition":
        try:
            document = json.loads(encoded)
            parent, result, kind, reason, failure, version = _result_from(
                document, CHANCE_TRANSITION_SCHEMA, "Chance Transition")
            if version == 1:
                return cls(
                    parent, _sample_from(document["sample"]),
                    _action_from(document["outcome"]), result, kind,
                    reason, failure, None, version,
                )
            branch = _branch_from(document["branch_key"])
            outcome = document.get("outcome")
            return cls(
                parent, branch.sample,
                None if outcome is None else _action_from(outcome), result, kind,
                reason, failure, None, version, branch,
                str(document["method"]), float(document["probability"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SearchContractError(f"invalid Chance Transition: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ChanceSuccessor:
    probability: float
    branch_keys: tuple[ChanceBranchKey, ...]
    node: SearchNode

    def __post_init__(self):
        if not 0.0 < self.probability <= 1.0:
            raise ValueError("Chance Successor probability must be within (0, 1]")
        if not self.branch_keys:
            raise ValueError("Chance Successor requires at least one branch")
        if not isinstance(self.node, SearchNode):
            raise TypeError("Chance Successor node must be a Search Node")


@dataclass(frozen=True, slots=True)
class ChanceExpansion:
    parent_state_key: SearchStateKey
    method: str
    status: ChanceExpansionStatus
    transitions: tuple[ChanceTransition, ...]
    successors: tuple[ChanceSuccessor, ...]
    exact_outcome_limit: int
    sample_count: int
    support_size: int | None
    requested_count: int
    produced_count: int
    failure: str | None = None
    schema_version: int = CHANCE_EXPANSION_SCHEMA_VERSION

    def __post_init__(self):
        if not isinstance(self.status, ChanceExpansionStatus):
            raise TypeError("Chance Expansion status must be a Chance Expansion Status")
        if not self.method or self.schema_version < 1:
            raise ValueError("invalid Chance Expansion identity")
        if min(self.exact_outcome_limit, self.sample_count) < 1:
            raise ValueError("Chance Expansion limits must be positive")
        if not 0 <= self.produced_count <= self.requested_count:
            raise ValueError("invalid Chance Expansion branch counts")
        if len(self.transitions) != self.requested_count:
            raise ValueError("Chance Expansion transitions must match requested count")
        if any(transition.parent_state_key != self.parent_state_key
               for transition in self.transitions):
            raise ValueError("Chance Expansion transition parent mismatch")
        mass = self.probability_mass
        if not -1e-12 <= mass <= 1.0 + 1e-12:
            raise ValueError("Chance Expansion probability mass is outside [0, 1]")
        if self.status in (ChanceExpansionStatus.COMPLETE,
                           ChanceExpansionStatus.ESTIMATED):
            if self.produced_count != self.requested_count or abs(mass - 1.0) > 1e-9:
                raise ValueError("complete Chance Expansion must preserve full mass")
        elif self.status is ChanceExpansionStatus.INCOMPLETE:
            if not 0 < self.produced_count < self.requested_count or mass >= 1.0 - 1e-9:
                raise ValueError("incomplete Chance Expansion must expose missing mass")
        elif self.produced_count or mass > 1e-12:
            raise ValueError("unavailable Chance Expansion cannot expose successor mass")

    @property
    def probability_mass(self) -> float:
        return sum(successor.probability for successor in self.successors)

    def dumps(self) -> str:
        document = {
            "schema": CHANCE_EXPANSION_SCHEMA,
            "schema_version": self.schema_version,
            "parent_state_key": _key_document(self.parent_state_key),
            "method": self.method,
            "status": self.status.value,
            "exact_outcome_limit": self.exact_outcome_limit,
            "sample_count": self.sample_count,
            "support_size": self.support_size,
            "requested_count": self.requested_count,
            "produced_count": self.produced_count,
            "probability_mass": self.probability_mass,
            "failure": self.failure,
            "branches": [{
                "branch_key": _branch_document(transition.branch_key),
                "probability": transition.probability,
                "result_state_key": _key_document(transition.result_state_key),
                "result_kind": transition.result_kind.value,
                "boundary_reason": (None if transition.boundary_reason is None
                                    else transition.boundary_reason.value),
                "failure": transition.failure,
            } for transition in self.transitions],
        }
        return _canonical(document)


__all__ = (
    "BoundaryReason", "CHANCE_EXPANSION_SCHEMA", "CHANCE_EXPANSION_SCHEMA_VERSION",
    "CHANCE_TRANSITION_SCHEMA", "CHANCE_TRANSITION_SCHEMA_VERSION", "ChanceExpansion",
    "ChanceExpansionRequest", "ChanceExpansionStatus", "ChanceSuccessor",
    "ChanceTransition", "NodeKind", "PRIMITIVE_TRANSITION_SCHEMA",
    "PRIMITIVE_TRANSITION_SCHEMA_VERSION", "PrimitiveTransition",
    "SEARCH_STATE_KEY_SCHEMA_VERSION", "SearchContractError", "SearchNode", "SearchStateKey",
)
