"""Stable JSON telemetry for Bellman root decisions."""
from __future__ import annotations

import dataclasses
import json
import sys


TAG = "@T"


def _wire(value):
    if dataclasses.is_dataclass(value):
        return _wire(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _wire(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire(item) for item in value]
    if hasattr(value, "value"):
        return _wire(value.value)
    return value


def to_record(decision, *, read=None, seat=None) -> dict:
    """Serialize the complete Bellman explanation for one committed choice."""

    diagnostics = _wire(dict(decision.diagnostics))
    record = {
        "bellman": True,
        "chosen": list(decision.chosen),
        "action": _wire(decision.action),
        "value": float(decision.value),
        "complete": bool(decision.complete),
        "diagnostics": diagnostics,
        "belief": ({
            "candidates": _wire(read.candidates),
            "unknown_mass": float(read.unknown_mass),
        } if read is not None and read.candidates else None),
    }
    if seat is not None:
        record["seat"] = int(seat)
    return record


def emit(decision, *, read=None, seat=None, out=None) -> None:
    print(f"{TAG} " + json.dumps(to_record(decision, read=read, seat=seat), separators=(",", ":")),
          file=out or sys.stderr, flush=True)


__all__ = ["TAG", "emit", "to_record"]
