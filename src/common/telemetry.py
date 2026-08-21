"""Stable JSON telemetry for Bellman root decisions."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import sys
from contextlib import contextmanager
from contextvars import ContextVar


TAG = "@T"
_CAPTURE: ContextVar[list[dict] | None] = ContextVar("telemetry_capture", default=None)


def lethal_proof_seconds(record: dict | None) -> float | None:
    if not isinstance(record, dict):
        return None
    proof = ((record.get("diagnostics") or {}).get("terminal_proof") or {})
    value = proof.get("elapsed_ms")
    if proof.get("attempted") is not True or isinstance(value, bool) \
            or not isinstance(value, (int, float)):
        return None
    seconds = float(value) / 1000.0
    return seconds if math.isfinite(seconds) and seconds >= 0.0 else None


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


def _action_key(value) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:20]


def _compact_family(candidate: dict) -> dict:
    return {
        "action_key": _action_key(candidate.get("action")),
        **{key: candidate.get(key) for key in (
            "family", "features", "contributions", "score", "gap", "wave", "status", "shadow")},
    }


def _compact_diagnostics(diagnostics: dict) -> dict:
    compact = {key: value for key, value in diagnostics.items()
               if key not in {"root", "production"}}
    root = diagnostics.get("root")
    if isinstance(root, dict):
        compact["root"] = {
            "chosen_key": _action_key(root.get("chosen_key")),
            "nodes": root.get("nodes"), "cache_hits": root.get("cache_hits"),
            "stopped_reason": root.get("stopped_reason"),
            "alternative_count": len(root.get("alternatives") or ()),
        }
    production = diagnostics.get("production")
    if isinstance(production, dict):
        family = production.get("family_candidates") or ()
        prunes = production.get("structural_prunes") or ()
        compact["production"] = {
            **{key: value for key, value in production.items()
               if key not in {"family_candidates", "structural_prunes"}},
            "structural_prunes": [{
                **{key: row.get(key) for key in ("proof_type", "retained_event", "gain")
                   if row.get(key) is not None},
                **({"pruned_key": _action_key(row.get("pruned"))}
                   if row.get("pruned") is not None else {}),
            } for row in prunes if isinstance(row, dict)],
            "family_candidates": [_compact_family(row) for row in family],
        }
    return compact


def to_record(decision, *, read=None, seat=None, compact=False,
              decision_seconds: float | None = None,
              decision_limit_seconds: float | None = None,
              deadline_hit: bool | None = None) -> dict:
    """Serialize the complete Bellman explanation for one committed choice."""

    diagnostics = _wire(dict(decision.diagnostics))
    if compact:
        diagnostics = _compact_diagnostics(diagnostics)
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
    if decision_seconds is not None:
        record["decision_seconds"] = float(decision_seconds)
    if decision_limit_seconds is not None:
        record["decision_limit_seconds"] = float(decision_limit_seconds)
    if deadline_hit is not None:
        record["deadline_hit"] = bool(deadline_hit)
    return record


def emit(decision, *, read=None, seat=None, out=None, decision_seconds=None,
         decision_limit_seconds=None, deadline_hit=None) -> None:
    record = to_record(decision, read=read, seat=seat, compact=True,
                       decision_seconds=decision_seconds,
                       decision_limit_seconds=decision_limit_seconds,
                       deadline_hit=deadline_hit)
    captured = _CAPTURE.get()
    if captured is not None:
        captured.append(record)
    print(f"{TAG} " + json.dumps(record, separators=(",", ":")),
          file=out or sys.stderr, flush=True)


@contextmanager
def capture_records():
    records = []
    token = _CAPTURE.set(records)
    try:
        yield records
    finally:
        _CAPTURE.reset(token)


__all__ = ["TAG", "capture_records", "emit", "to_record"]
