"""Public wire contracts for primitive turn search."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from common.api import ActionIdentity
from common.observation import ObservationState

from .chance import ChanceSampleKey


SEARCH_STATE_KEY_SCHEMA_VERSION = 1
PRIMITIVE_TRANSITION_SCHEMA_VERSION = 1
PRIMITIVE_TRANSITION_SCHEMA = "cgpy-primitive-transition"
CHANCE_TRANSITION_SCHEMA_VERSION = 1
CHANCE_TRANSITION_SCHEMA = "cgpy-chance-transition"


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
    sample: ChanceSampleKey
    outcome: ActionIdentity
    result_state_key: SearchStateKey
    result_kind: NodeKind
    boundary_reason: BoundaryReason | None
    failure: str | None
    node: SearchNode | None = field(default=None, repr=False, compare=False)
    schema_version: int = CHANCE_TRANSITION_SCHEMA_VERSION

    def __post_init__(self):
        _validate_result(
            self.parent_state_key, self.result_state_key,
            self.schema_version, "Chance Transition")
        if not isinstance(self.sample, ChanceSampleKey):
            raise TypeError("Chance Transition sample must be a Chance Sample Key")
        if not isinstance(self.outcome, ActionIdentity):
            raise TypeError("Chance Transition outcome must be an ActionIdentity")

    def dumps(self) -> str:
        document = _result_document(self, CHANCE_TRANSITION_SCHEMA)
        document.update({
            "sample": _sample_document(self.sample),
            "outcome": _action_document(self.outcome),
        })
        return _canonical(document)

    @classmethod
    def loads(cls, encoded: str) -> "ChanceTransition":
        try:
            document = json.loads(encoded)
            parent, result, kind, reason, failure, version = _result_from(
                document, CHANCE_TRANSITION_SCHEMA, "Chance Transition")
            return cls(
                parent, _sample_from(document["sample"]),
                _action_from(document["outcome"]), result, kind,
                reason, failure, None, version,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SearchContractError(f"invalid Chance Transition: {exc}") from exc


__all__ = (
    "BoundaryReason", "CHANCE_TRANSITION_SCHEMA", "CHANCE_TRANSITION_SCHEMA_VERSION",
    "ChanceTransition", "NodeKind", "PRIMITIVE_TRANSITION_SCHEMA",
    "PRIMITIVE_TRANSITION_SCHEMA_VERSION", "PrimitiveTransition",
    "SEARCH_STATE_KEY_SCHEMA_VERSION", "SearchContractError", "SearchNode", "SearchStateKey",
)
