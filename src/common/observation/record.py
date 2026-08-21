from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass

from common.api import ActionIdentity
from common.options import LegalAction

from . import nodes
from .state import (AttackEvent, DrawEvent, KnownObservationEvent, MoveCardEvent,
                    ObservationDelta, ObservationEvent, ObservationState, SCHEMA_VERSION,
                    ShuffleEvent, UnknownObservationEvent)
from .knowledge import (KnownAttackLocks, KnownDeckTop, KnownOwnPrizes, LegalKnowledge,
                        OpponentBelief, TransitionTrace, UnknownAttackLocks, UnknownDeckTop,
                        UnknownOwnPrizes)


_TYPES = {item.__name__: item for item in (
    ActionIdentity, LegalAction, LegalKnowledge, ObservationDelta, ObservationEvent,
    AttackEvent, DrawEvent, KnownObservationEvent, MoveCardEvent, ShuffleEvent,
    UnknownObservationEvent,
    ObservationState, OpponentBelief, TransitionTrace, KnownAttackLocks, KnownDeckTop,
    KnownOwnPrizes, UnknownAttackLocks, UnknownDeckTop, UnknownOwnPrizes,
    nodes.Body, nodes.Card, nodes.CardBag, nodes.HiddenHand, nodes.Looking, nodes.Option,
    nodes.SelectPrompt, nodes.Side, nodes.Turn, nodes.VisibleHand,
)}


def _encode(value):
    if is_dataclass(value) and not isinstance(value, type):
        return {"$type": type(value).__name__,
                "fields": {field.name: _encode(getattr(value, field.name))
                           for field in fields(value) if not field.name.startswith("_")}}
    if isinstance(value, tuple):
        return {"$tuple": [_encode(child) for child in value]}
    if isinstance(value, frozenset):
        return {"$frozenset": [_encode(child) for child in sorted(value)]}
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported observation record value {type(value).__name__}")


def _decode(value):
    if isinstance(value, list):
        return [_decode(child) for child in value]
    if not isinstance(value, dict):
        return value
    if "$tuple" in value:
        return tuple(_decode(child) for child in value["$tuple"])
    if "$frozenset" in value:
        return frozenset(_decode(child) for child in value["$frozenset"])
    if "$bytes" in value:
        return bytes.fromhex(value["$bytes"])
    name = value.get("$type")
    if name is None:
        return {key: _decode(child) for key, child in value.items()}
    cls = _TYPES.get(name)
    if cls is None:
        raise ValueError(f"unknown observation record type {name!r}")
    return cls(**{key: _decode(child) for key, child in value["fields"].items()})


@dataclass(frozen=True, slots=True)
class ObservationRecord:
    schema_version: int
    payload: object

    @classmethod
    def from_state(cls, state: ObservationState) -> "ObservationRecord":
        return cls(SCHEMA_VERSION, _encode(state))

    def to_state(self) -> ObservationState:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported observation schema {self.schema_version}")
        state = _decode(self.payload)
        if not isinstance(state, ObservationState):
            raise ValueError("record payload is not an ObservationState")
        _validate_state(state)
        return state

    def dumps(self) -> str:
        return json.dumps({"schema_version": self.schema_version, "payload": self.payload},
                          sort_keys=True, separators=(",", ":"))

    @classmethod
    def loads(cls, encoded: str) -> "ObservationRecord":
        raw = json.loads(encoded)
        return cls(int(raw["schema_version"]), raw["payload"])


def _validate_state(state: ObservationState) -> None:
    if not isinstance(state.me.hand, nodes.VisibleHand):
        raise ValueError("record root hand must be visible")
    if not isinstance(state.them.hand, nodes.HiddenHand):
        raise ValueError("record opponent hand must be hidden")
    _validate_frozen(state)


def _validate_frozen(value) -> None:
    if is_dataclass(value) and not isinstance(value, type):
        if type(value).__name__ not in _TYPES:
            raise ValueError(f"record contains unsupported type {type(value).__name__}")
        for field in fields(value):
            _validate_frozen(getattr(value, field.name))
        return
    if isinstance(value, tuple):
        for child in value:
            _validate_frozen(child)
        return
    if isinstance(value, (frozenset, bytes)) or value is None \
            or isinstance(value, (bool, int, float, str)):
        return
    raise ValueError(f"record contains mutable {type(value).__name__}")


__all__ = ("ObservationRecord",)
