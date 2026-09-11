from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Protocol, TypeAlias, cast

from common.api import ActionIdentity


WireScalar: TypeAlias = str | int | float | bool | None
WireValue: TypeAlias = WireScalar | list["WireValue"] | dict[str, "WireValue"]
IdentityValue: TypeAlias = (
    WireScalar | tuple["IdentityValue", ...] | list["IdentityValue"]
    | dict[str, "IdentityValue"]
)


class ActionChoice(Protocol):
    @property
    def identity(self) -> ActionIdentity: ...

    @property
    def selection(self) -> tuple[int, ...]: ...


@dataclass(frozen=True, order=True, slots=True)
class ActionChoiceIdentity:
    identity: ActionIdentity
    selection: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ActionIdentity):
            raise TypeError("choice identity requires an Action Identity")
        if any(type(index) is not int or index < 0 for index in self.selection):
            raise ValueError("choice selection requires nonnegative integer indices")

    @classmethod
    def from_action(cls, action: ActionChoice) -> ActionChoiceIdentity:
        return cls(action.identity, tuple(action.selection))

    def as_dict(self) -> dict[str, WireValue]:
        return {
            "identity": {
                "kind": self.identity.kind,
                "parts": _wire(tuple(self.identity.parts)),
            },
            "selection": list(self.selection),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, WireValue]) -> ActionChoiceIdentity:
        if set(value) != {"identity", "selection"}:
            raise ValueError("invalid Action Choice Identity fields")
        identity = value["identity"]
        selection = value["selection"]
        if (not isinstance(identity, dict)
                or set(identity) != {"kind", "parts"}
                or not isinstance(identity["kind"], str)
                or not isinstance(identity["parts"], list)
                or not isinstance(selection, list)
                or any(type(index) is not int for index in selection)):
            raise ValueError("invalid Action Choice Identity")
        parts = _unwire(identity["parts"])
        if not isinstance(parts, tuple):
            raise ValueError("Action Identity parts must be a sequence")
        return cls(
            ActionIdentity(identity["kind"], parts),
            tuple(cast(int, index) for index in selection),
        )


def _wire(value: IdentityValue) -> WireValue:
    if isinstance(value, tuple):
        return [_wire(item) for item in value]
    if isinstance(value, list):
        return [_wire(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _wire(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Action Identity contains unsupported value {type(value).__name__}")


def _unwire(value: WireValue) -> IdentityValue:
    if isinstance(value, list):
        return tuple(_unwire(item) for item in value)
    if isinstance(value, dict):
        return {key: _unwire(item) for key, item in value.items()}
    return value


PolicyActionIdentity = ActionChoiceIdentity


__all__ = ("ActionChoice", "ActionChoiceIdentity", "PolicyActionIdentity")
