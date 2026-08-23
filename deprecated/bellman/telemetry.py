"""Diagnostic-only serializer for quarantined Bellman teacher records."""
from __future__ import annotations

import dataclasses
import hashlib
import json


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


def to_record(decision, *, opponent=None, seat=None, compact=False, state=None,
              decision_seconds=None, decision_limit_seconds=None, deadline_hit=None) -> dict:
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
        "belief": ({"identity": opponent.identity,
                    "snapshot": _wire(opponent.canonical_data())}
                   if opponent is not None else None),
    }
    if state is not None:
        from common.observation import ObservationRecord
        record["observation_record"] = json.loads(ObservationRecord.from_state(state).dumps())
    if seat is not None:
        record["seat"] = int(seat)
    if decision_seconds is not None:
        record["decision_seconds"] = float(decision_seconds)
    if decision_limit_seconds is not None:
        record["decision_limit_seconds"] = float(decision_limit_seconds)
    if deadline_hit is not None:
        record["deadline_hit"] = bool(deadline_hit)
    return record


__all__ = ("to_record",)
