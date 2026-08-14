"""Stable JSON telemetry for Bellman root decisions."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from contextlib import contextmanager
from contextvars import ContextVar


TAG = "@T"
_CAPTURE: ContextVar[list[dict] | None] = ContextVar("telemetry_capture", default=None)


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


def _compact_needs(needs: dict) -> dict:
    focused = needs.get("focused") or ()
    safety = needs.get("safety") or ()
    return {
        "focused": [{
            "action_key": row.get("action_key"), "family": row.get("family"),
            "score": row.get("score"), "reason": row.get("reason"),
            "path_count": len(row.get("path_ids") or ()),
        } for row in focused],
        "safety": [{
            "action_key": row.get("action_key"), "family": row.get("family"),
            "reason": row.get("reason"),
        } for row in safety],
        "unknown": list(needs.get("unknown") or ()),
        "held": [{"action_key": row.get("action_key"), "family": row.get("family"),
                  "reason": row.get("reason")} for row in needs.get("held") or ()],
        "inactive": [{"action_key": row.get("action_key"), "family": row.get("family"),
                      "reason": row.get("reason")} for row in needs.get("inactive") or ()],
        "features": list(needs.get("features") or ()),
        "path_count": len(needs.get("paths") or ()),
        "elapsed_ms": needs.get("elapsed_ms"), "exhausted": needs.get("exhausted"),
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
    needs = diagnostics.get("needs")
    if isinstance(needs, dict):
        compact["needs"] = _compact_needs(needs)
    return compact


def to_record(decision, *, read=None, seat=None, compact=False) -> dict:
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
    return record


def emit(decision, *, read=None, seat=None, out=None) -> None:
    record = to_record(decision, read=read, seat=seat, compact=True)
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
