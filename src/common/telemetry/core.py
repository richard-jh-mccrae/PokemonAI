"""Strict Ledger record, framing, session, and emission implementation."""
from __future__ import annotations

import dataclasses
import base64
import hashlib
import json
import math
import os
import subprocess
import sys
import zlib
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from contextlib import contextmanager
from contextvars import ContextVar


TAG = "@T"
MAX_FRAME_BYTES = 16 * 1024
_FRAME_PAYLOAD_CHARS = 12_000
_FRAME_SCHEMA = "ledger.telemetry.frame"
_FRAME_VERSION = 1
_CAPTURE: ContextVar[list[dict] | None] = ContextVar("telemetry_capture", default=None)
_SUPPRESS_OUTPUT: ContextVar[bool] = ContextVar("telemetry_suppress_output", default=False)
_EPISODE_CONTEXT: ContextVar[str | None] = ContextVar("telemetry_episode", default=None)
SCHEMA = "ledger.telemetry"
SCHEMA_VERSION = 2
_DECISION_FIELDS = {
    "schema", "schema_version", "record_type", "record_id", "episode", "decision",
    "observation", "opponent_snapshot", "actions", "root", "candidates", "search",
    "behavior_identity", "configuration", "provenance", "timing", "completeness",
}
_OUTCOME_FIELDS = {
    "schema", "schema_version", "record_type", "record_id", "episode", "decision_ids",
    "telemetry_receipt_id", "result",
}
_RECEIPT_FIELDS = {
    "schema", "schema_version", "record_type", "record_id", "episode", "reservations",
    "decision_ids", "certified",
}
_EVALUATION_MODEL_CACHE: dict[str, dict] = {}
_COMPUTE_CONFIGURATION_CACHE: dict[str, dict] = {}
_EMITTER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ledger-telemetry")
_CALLER_SECONDS = 0.0
_PENDING = []


class _ValidatedRecord(dict):
    def _immutable(self, *_args, **_kwargs):
        raise TypeError("validated telemetry records are immutable")

    __delitem__ = __setitem__ = clear = pop = popitem = setdefault = update = _immutable


class _CapturedRecords(list):
    def __init__(self):
        super().__init__()
        self.emit_seconds = 0.0
        self.construction_seconds = 0.0
        self.delivery_seconds = 0.0
        self._sessions = []

    def register_session(self, session) -> None:
        if all(found is not session for found in self._sessions):
            self._sessions.append(session)

    def receipt(self, episode_key: str) -> dict:
        journal = {}
        for session in self._sessions:
            if session.episode_key == episode_key:
                for row in session.close_episode()["reservations"]:
                    journal[row["record_id"]] = dict(row)
        reservations = []
        for record in self:
            if record.get("record_type") != "decision" \
                    or record["episode"]["key"] != episode_key:
                continue
            saved = journal.pop(record["record_id"], None)
            reservations.append(saved or {
                "record_id": record["record_id"],
                "seat": record["decision"]["seat"],
                "index": record["decision"]["index"],
                "status": "delivery_failed",
                "error_type": "TelemetryReservationUnavailable",
            })
        reservations.extend(journal.values())
        return build_episode_receipt(
            episode_key=episode_key, reservations=reservations)


class _ValidatedObservation(dict):
    pass


def _exact_fields(value, expected: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"unknown {label} fields")


def _number(value, label: str, *, minimum=None, maximum=None, integer=False) -> None:
    expected = int if integer else (int, float)
    if isinstance(value, bool) or not isinstance(value, expected) or not math.isfinite(value):
        raise ValueError(f"invalid {label}")
    if minimum is not None and value < minimum:
        raise ValueError(f"invalid {label}")
    if maximum is not None and value > maximum:
        raise ValueError(f"invalid {label}")


def _validate_action(value) -> None:
    _exact_fields(value, {"id", "identity", "selection"}, "action")
    identity = value["identity"]
    if isinstance(identity, dict):
        _exact_fields(identity, {"kind", "parts"}, "action identity")
    if not isinstance(value["id"], str) or not isinstance(value["selection"], list) \
            or not all(isinstance(item, int) and not isinstance(item, bool)
                       for item in value["selection"]):
        raise ValueError("invalid action")
    if value["id"] != _identifier(identity):
        raise ValueError("action id mismatch")


def _validate_scale(value) -> None:
    _exact_fields(value, {
        "name", "schema_version", "lower_bound", "upper_bound",
    }, "value scale")
    _number(value["schema_version"], "value scale version", minimum=1, integer=True)
    for field in ("lower_bound", "upper_bound"):
        if value[field] is not None:
            _number(value[field], f"value scale {field}")
    if value["lower_bound"] is not None and value["upper_bound"] is not None \
            and value["lower_bound"] > value["upper_bound"]:
        raise ValueError("invalid value scale bounds")


def _validate_components(values) -> None:
    if not isinstance(values, list):
        raise ValueError("invalid value components")
    for value in values:
        _exact_fields(value, {
            "key", "activation", "coefficient", "value", "provenance",
        }, "value component")
        for field in ("activation", "coefficient", "value"):
            _number(value[field], f"value component {field}")


def _validate_valuation(value) -> None:
    _exact_fields(value, {
        "state_key", "total", "scale", "perspective", "evaluator_identity",
        "components", "status", "gaps", "evidence",
    }, "state valuation")
    _validate_scale(value["scale"])
    _validate_components(value["components"])
    _number(value["total"], "state valuation total")
    if value["status"] not in {"complete", "estimated", "unavailable"}:
        raise ValueError("invalid state valuation status")
    if value["evidence"] is not None:
        _exact_fields(value["evidence"], {
            "kind", "remaining", "route", "printed_prizes", "overrun",
        }, "valuation evidence")


def _validate_observation(value) -> None:
    _exact_fields(value, {"schema_version", "payload"}, "observation record")
    if isinstance(value, _ValidatedObservation):
        return
    from common.observation import ObservationRecord

    ObservationRecord(int(value["schema_version"]), value["payload"]).to_state()


def _validate_candidate(value) -> None:
    _exact_fields(value, {
        "action_id", "disposition", "status", "delta", "search_value", "prior", "gaps",
        "successors", "continuation", "policy_tie_break", "policy_evidence",
    }, "candidate")
    if value["delta"] is not None:
        _exact_fields(value["delta"], {"total", "scale", "components"}, "decision delta")
        _validate_scale(value["delta"]["scale"])
        _validate_components(value["delta"]["components"])
        _number(value["delta"]["total"], "decision delta total")
    if value["search_value"] is not None:
        _exact_fields(value["search_value"], {"total", "scale"}, "search value")
        _validate_scale(value["search_value"]["scale"])
        _number(value["search_value"]["total"], "search value total")
    if value["prior"] is not None:
        _number(value["prior"], "candidate prior", minimum=0.0, maximum=1.0)
    if value["continuation"] is not None:
        _exact_fields(value["continuation"], {
            "state_delta", "action_opportunity", "continues_turn", "zones_created",
            "zones_replaced", "allowances_consumed", "immediately_usable_outputs",
            "opportunities_created", "opportunities_preserved", "opportunities_consumed",
        }, "continuation")
    if value["policy_evidence"] is not None:
        _exact_fields(value["policy_evidence"], {
            "kind", "remaining", "route", "printed_prizes", "overrun",
        }, "policy evidence")
    for successor in value["successors"]:
        _exact_fields(successor, {
            "probability", "valuation", "ended", "observation", "trace", "action_path",
            "status", "failure_code",
        }, "successor")
        _validate_valuation(successor["valuation"])
        _validate_observation(successor["observation"])
        _number(successor["probability"], "successor probability", minimum=0.0, maximum=1.0)
        _exact_fields(successor["trace"], {
            "schema_version", "start_position_key", "actions", "terminal_position_key",
        }, "transition trace")
        for action in (*successor["trace"]["actions"], *successor["action_path"]):
            _validate_action(action)


def _validate_configuration(value, *, pregame: bool) -> None:
    _exact_fields(value, {"evaluation_model", "compute", "provider"},
                  "decision configuration")
    if pregame:
        if value != {"evaluation_model": None, "compute": None, "provider": None}:
            raise ValueError("pregame record contains Ledger configuration")
        return
    model = value["evaluation_model"]
    compute = value["compute"]
    provider = value["provider"]
    if compute.get("schema_version") not in {1, 2}:
        raise ValueError("unsupported compute configuration schema version")
    if compute.get("search", {}).get("schema_version") not in {1, 4, 5}:
        raise ValueError("unsupported search configuration schema version")
    _exact_fields(model, {
        "identity", "card_store_identity", "valuation", "roles", "prize_plan",
        "opponent_profiles",
    }, "evaluation model")
    _exact_fields(model["valuation"], {
        "identity", "schema_version", "values",
    }, "valuation configuration")
    _exact_fields(model["prize_plan"], {"identity", "protect", "offer"}, "prize plan")
    for profile in model["opponent_profiles"].values():
        _exact_fields(profile, {"roles", "traits", "mechanics", "resources"},
                      "opponent profile")
    compute_fields = {"identity", "schema_version", "search", "policy"}
    if compute.get("schema_version") == 2:
        compute_fields.add("profile")
    _exact_fields(compute, compute_fields, "compute configuration")
    search_fields = {
        "identity", "schema_version", "depth_budget",
        "path_node_budget", "node_budget", "time_budget_ms", "chance_sample_budget",
        "chance_seed", "noise_tolerance", "tie_seed",
    }
    if compute["search"].get("schema_version") == 4:
        search_fields.update({"main_depth_budget", "main_continuation_discount"})
    _exact_fields(compute["search"], search_fields, "search configuration")
    _exact_fields(compute["policy"], {
        "identity", "schema_version", "noise_tolerance", "tie_seed", "accepted_statuses",
        "unavailable_fallback",
    }, "policy configuration")
    _exact_fields(provider, {
        "identity", "backend", "factory", "version", "kwargs", "factory_kwargs",
    }, "provider configuration")
    if not all(isinstance(provider[field], str) and provider[field]
               for field in ("identity", "backend", "factory")) \
            or not isinstance(provider["kwargs"], dict) \
            or not isinstance(provider["factory_kwargs"], dict):
        raise ValueError("invalid provider configuration")


def validate_record(record: dict) -> dict:
    if isinstance(record, _ValidatedRecord):
        return record
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise ValueError("unsupported telemetry schema")
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported telemetry schema version")
    record_type = record.get("record_type")
    if record_type == "telemetry_receipt":
        _exact_fields(record, _RECEIPT_FIELDS, "Episode Telemetry Receipt")
        _exact_fields(record["episode"], {"key"}, "receipt episode")
        if not isinstance(record["reservations"], list):
            raise ValueError("invalid telemetry reservations")
        delivered = []
        reservation_ids = []
        terminal = True
        for reservation in record["reservations"]:
            _exact_fields(reservation, {
                "record_id", "seat", "index", "status", "error_type",
            }, "telemetry reservation")
            _number(reservation["seat"], "reservation seat", minimum=0, integer=True)
            _number(reservation["index"], "reservation index", minimum=0, integer=True)
            if reservation["status"] not in {
                    "reserved", "committed", "delivered", "emission_failed",
                    "delivery_failed"}:
                raise ValueError("invalid telemetry reservation status")
            failed = reservation["status"].endswith("_failed")
            if failed is not (isinstance(reservation["error_type"], str)
                              and bool(reservation["error_type"])):
                raise ValueError("telemetry reservation failure disagrees with error type")
            terminal = terminal and reservation["status"] in {
                "delivered", "emission_failed", "delivery_failed"}
            reservation_ids.append(reservation["record_id"])
            if reservation["status"] == "delivered":
                delivered.append(reservation["record_id"])
        if len(set(reservation_ids)) != len(reservation_ids):
            raise ValueError("telemetry reservations must be unique")
        if record["decision_ids"] != delivered:
            raise ValueError("receipt decision ids do not match delivered reservations")
        certified = terminal and len(delivered) == len(record["reservations"])
        if record["certified"] is not certified:
            raise ValueError("receipt certification disagrees with reservations")
    elif record_type == "outcome":
        _exact_fields(record, _OUTCOME_FIELDS, "outcome record")
        _exact_fields(record["episode"], {"key", "external_id"}, "outcome episode")
        _exact_fields(record["result"], {
            "winner", "draw", "terminal_reason", "public_prizes", "rewards",
            "duration_seconds",
        }, "outcome result")
        result = record["result"]
        if not isinstance(record["decision_ids"], list) \
                or not all(isinstance(value, str) and value for value in record["decision_ids"]):
            raise ValueError("invalid outcome decision ids")
        if len(set(record["decision_ids"])) != len(record["decision_ids"]):
            raise ValueError("outcome decision ids must be unique")
        if not isinstance(record["telemetry_receipt_id"], str) \
                or not record["telemetry_receipt_id"]:
            raise ValueError("outcome requires an Episode Telemetry Receipt")
        if result["winner"] not in (None, 0, 1) \
                or result["draw"] is not (result["winner"] is None):
            raise ValueError("outcome winner and draw disagree")
        if set(result["public_prizes"]) != {"0", "1"} \
                or set(result["rewards"]) != {"0", "1"}:
            raise ValueError("outcome must cover both seats")
        for value in result["public_prizes"].values():
            _number(value, "public prize count", minimum=0, integer=True)
        for value in result["rewards"].values():
            _number(value, "outcome reward")
        _number(result["duration_seconds"], "outcome duration", minimum=0.0)
    elif record_type == "decision":
        _exact_fields(record, _DECISION_FIELDS, "decision record")
        _exact_fields(record["episode"], {"key"}, "decision episode")
        variant = record["decision"].get("variant")
        if variant == "declarative_pregame":
            _exact_fields(record["decision"], {
                "variant", "index", "parent_id", "seat", "turn", "position_key", "decision_key",
                "chosen_action_id", "selection", "policy_action",
            }, "pregame decision")
            if record["root"] is not None or record["candidates"] != [] \
                    or record["search"] is not None \
                    or record["completeness"] != "not_evaluated":
                raise ValueError("pregame record contains Ledger evidence")
        else:
            if variant != "ledger":
                raise ValueError("unknown decision variant")
            _exact_fields(record["decision"], {
                "variant", "index", "parent_id", "seat", "turn", "position_key", "decision_key",
                "chosen_action_id", "selection", "policy_reason",
            }, "Ledger decision")
            _exact_fields(record["search"], {
                "nodes_visited", "stop_reason", "frontier", "failure", "trace",
            }, "search")
            _number(record["search"]["nodes_visited"], "search nodes", minimum=0, integer=True)
            if record["search"]["failure"] is not None:
                _exact_fields(record["search"]["failure"], {
                    "stage", "error_type",
                }, "search failure")
            if record["search"]["trace"] is not None:
                _exact_fields(record["search"]["trace"], {
                    "nodes_visited", "stop_reason", "frontier", "chosen_action_id",
                    "action_paths",
                }, "search trace")
                for path in record["search"]["trace"]["action_paths"]:
                    for action in path:
                        _validate_action(action)
            _validate_valuation(record["root"])
            for candidate in record["candidates"]:
                _validate_candidate(candidate)
        _validate_configuration(record["configuration"],
                                pregame=variant == "declarative_pregame")
        _exact_fields(record["timing"], {
            "decision_seconds", "decision_limit_seconds", "deadline_hit",
        }, "decision timing")
        for field in ("decision_seconds", "decision_limit_seconds"):
            if record["timing"][field] is not None:
                _number(record["timing"][field], field, minimum=0.0)
        if record["timing"]["deadline_hit"] not in (None, True, False):
            raise ValueError("invalid deadline_hit")
        for field in ("index", "seat", "turn"):
            _number(record["decision"][field], f"decision {field}", minimum=0, integer=True)
        _validate_observation(record["observation"])
        for action in record["actions"]:
            _validate_action(action)
        action_ids = [action["id"] for action in record["actions"]]
        if len(set(action_ids)) != len(action_ids) \
                or record["decision"]["chosen_action_id"] not in action_ids:
            raise ValueError("decision action ids are inconsistent")
        chosen_action = record["actions"][
            action_ids.index(record["decision"]["chosen_action_id"])]
        if record["decision"]["selection"] != chosen_action["selection"]:
            raise ValueError("decision selection differs from the chosen legal action")
        if variant == "ledger" \
                and [candidate["action_id"] for candidate in record["candidates"]] != action_ids:
            raise ValueError("candidate roster does not match legal actions")
        if record["opponent_snapshot"] is not None:
            _exact_fields(record["opponent_snapshot"], {"identity", "snapshot"},
                          "opponent snapshot")
            snapshot = record["opponent_snapshot"]["snapshot"]
            _exact_fields(snapshot, {
                "candidates", "evidence", "failures", "knowledge_identity", "observed_roles",
                "resource_delta", "timeline", "unknown_mass",
            }, "opponent snapshot payload")
            _exact_fields(snapshot["evidence"], {
                "in_play_card_ids", "opponent_seat", "resources", "revealed_card_ids", "turn",
            }, "opponent evidence")
            for failure in snapshot["failures"]:
                _exact_fields(failure, {"subsystem"}, "opponent failure")
            for candidate in snapshot["candidates"]:
                _exact_fields(candidate, {
                    "archetype", "probability", "resources", "roles", "traits", "mechanics",
                }, "opponent candidate")
            for event in snapshot["timeline"]:
                _exact_fields(event, {
                    "kind", "source", "raw_kind", "player_index", "card_id", "from_area",
                    "to_area", "public_fields", "recognized", "sequence", "turn",
                }, "opponent event")
        if variant == "ledger":
            if record["behavior_identity"] is not None:
                _exact_fields(record["behavior_identity"], {
                    "evaluator", "evaluation_model", "search", "policy_model", "decision_policy",
                    "fail_safe_policy", "provider", "compute", "prize_plan",
                }, "behavior identity")
                if record["configuration"]["provider"]["identity"] \
                        != record["behavior_identity"]["provider"]:
                    raise ValueError("provider configuration identity disagrees with behavior")
            if record["completeness"] not in {"complete", "estimated", "unavailable"}:
                raise ValueError("unknown decision completeness")
        else:
            _exact_fields(record["behavior_identity"], {"pregame_policy"},
                          "pregame behavior identity")
        _exact_fields(record["provenance"], {"agent", "artifact", "code", "data"},
                      "runtime provenance")
    else:
        raise ValueError("unknown telemetry record type")
    if record.get("record_id") != _record_identifier(record):
        raise ValueError("telemetry record id mismatch")
    return _ValidatedRecord(record)


def migrate_record(record: dict, *, target_version: int = SCHEMA_VERSION) -> dict:
    if record.get("bellman") is True:
        raise ValueError("Bellman telemetry is diagnostic-only and cannot migrate")
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("legacy telemetry is diagnostic-only and cannot migrate")
    if target_version != SCHEMA_VERSION:
        raise ValueError("no one-step telemetry migration is registered")
    return validate_record(record)


@contextmanager
def episode_context(episode_key: str):
    token = _EPISODE_CONTEXT.set(str(episode_key))
    try:
        yield
    finally:
        _EPISODE_CONTEXT.reset(token)


class TelemetrySession:
    def __init__(self):
        self.episode_key: str | None = None
        self._indices: dict[int, int] = {}
        self._parents: dict[int, str] = {}
        self._reservations: dict[str, dict] = {}

    def begin_episode(self, episode_key: str | None = None) -> str:
        target = str(episode_key or _EPISODE_CONTEXT.get() or uuid4().hex)
        if self.episode_key == target:
            return target
        self.episode_key = target
        self._indices.clear()
        self._parents.clear()
        self._reservations.clear()
        return self.episode_key

    def next_decision(self, *, seat: int) -> dict:
        if self.episode_key is None:
            self.begin_episode()
        index = self._indices.get(int(seat), 0)
        self._indices[int(seat)] = index + 1
        return {
            "episode_key": self.episode_key,
            "decision_index": index,
            "parent_decision_id": self._parents.get(int(seat)),
        }

    def commit_decision(self, *, seat: int, record_id: str) -> None:
        reservation = self._reservations.get(str(record_id))
        if reservation is not None:
            if reservation["status"] != "reserved":
                raise ValueError("telemetry reservation cannot be committed")
            reservation["status"] = "committed"
        self._parents[int(seat)] = str(record_id)

    def reserve_decision(self, *, seat: int, position_key: str,
                         decision_key: str) -> dict:
        link = self.next_decision(seat=seat)
        record_id = _identifier({
            "schema": SCHEMA, "schema_version": SCHEMA_VERSION,
            "episode": link["episode_key"], "seat": int(seat),
            "index": link["decision_index"], "position_key": str(position_key),
            "decision_key": str(decision_key),
        })
        self._reservations[record_id] = {
            "record_id": record_id, "seat": int(seat),
            "index": int(link["decision_index"]), "status": "reserved",
            "error_type": None,
        }
        return {**link, "record_id": record_id}

    def deliver_decision(self, *, record_id: str) -> None:
        reservation = self._reservations.get(str(record_id))
        if reservation is None or reservation["status"] != "committed":
            raise ValueError("telemetry reservation cannot be delivered")
        reservation["status"] = "delivered"

    def fail_decision(self, *, record_id: str, phase: str, error_type: str) -> None:
        if phase not in {"emission", "delivery"}:
            raise ValueError("unknown telemetry failure phase")
        reservation = self._reservations.get(str(record_id))
        if reservation is None or reservation["status"] not in {"reserved", "committed"}:
            raise ValueError("telemetry reservation cannot fail")
        reservation["status"] = f"{phase}_failed"
        reservation["error_type"] = str(error_type)

    def close_episode(self) -> dict:
        if self.episode_key is None:
            raise ValueError("telemetry episode has not begun")
        return build_episode_receipt(
            episode_key=self.episode_key,
            reservations=list(self._reservations.values()))


def _canonical_bytes(value: dict) -> bytes:
    return json.dumps(
        value, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def _identifier(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(_allowed(value))).hexdigest()


def _record_identifier(record: dict) -> str:
    if record.get("record_type") == "decision":
        decision = record["decision"]
        return _identifier({
            "schema": record["schema"], "schema_version": record["schema_version"],
            "episode": record["episode"]["key"], "seat": decision["seat"],
            "index": decision["index"], "position_key": decision["position_key"],
            "decision_key": decision["decision_key"],
        })
    return _identifier({**record, "record_id": None})


def _allowed(value):
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("telemetry numbers must be finite")
        return value
    if isinstance(value, (list, tuple)):
        return [_allowed(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("telemetry mapping keys must be strings")
        return {key: _allowed(item) for key, item in sorted(value.items())}
    if hasattr(value, "kind") and hasattr(value, "parts"):
        return {"kind": _allowed(value.kind), "parts": _allowed(value.parts)}
    if hasattr(value, "value"):
        return _allowed(value.value)
    raise TypeError(f"unsupported telemetry value {type(value).__name__}")


def _components(components) -> list[dict]:
    return [{
        "key": item.key,
        "activation": float(item.activation),
        "coefficient": float(item.coefficient),
        "value": float(item.value),
        "provenance": list(item.provenance),
    } for item in components]


def _scale(scale) -> dict:
    return {
        "name": scale.name,
        "schema_version": int(scale.schema_version),
        "lower_bound": scale.lower_bound,
        "upper_bound": scale.upper_bound,
    }


def _observation(state) -> dict:
    from common.observation import ObservationRecord

    record = ObservationRecord.from_state(state)
    return _ValidatedObservation({
        "schema_version": record.schema_version,
        "payload": record.payload,
    })


def _valuation(valuation) -> dict:
    return {
        "state_key": valuation.state_key,
        "total": float(valuation.total),
        "scale": _scale(valuation.scale),
        "perspective": valuation.perspective,
        "evaluator_identity": valuation.evaluator_identity,
        "components": _components(valuation.components),
        "status": valuation.status.value,
        "gaps": list(valuation.gaps),
        "evidence": _policy_evidence(valuation.evidence),
    }


def _evaluation_model_configuration(value) -> dict:
    if isinstance(value, dict):
        return _allowed(value)
    from common.ledger import EvaluationModel

    if not isinstance(value, EvaluationModel):
        raise TypeError("evaluation_model must be an EvaluationModel")
    cached = _EVALUATION_MODEL_CACHE.get(value.identity)
    if cached is not None:
        return cached
    result = {
        "identity": value.identity,
        "card_store_identity": value.store_identity,
        "valuation": {
            "identity": value.configuration.identity,
            "schema_version": int(value.configuration.schema_version),
            "values": {key: float(coefficient)
                       for key, coefficient in value.configuration.values},
        },
        "roles": {},
        "prize_plan": {
            "identity": value.prize_plan.identity,
            "protect": list(value.prize_plan.protect),
            "offer": list(value.prize_plan.offer),
        },
        "opponent_profiles": {
            name: _allowed(profile.canonical_data())
            for name, profile in sorted(value.opponent_profiles.items())
        },
    }
    _EVALUATION_MODEL_CACHE[value.identity] = result
    return result


def _compute_configuration(value) -> dict:
    if isinstance(value, dict):
        return _allowed(value)
    from common.decision import ComputeConfiguration

    if not isinstance(value, ComputeConfiguration):
        raise TypeError("compute_configuration must be a ComputeConfiguration")
    cached = _COMPUTE_CONFIGURATION_CACHE.get(value.identity)
    if cached is not None:
        return cached
    result = {
        "identity": value.identity,
        "schema_version": int(value.schema_version),
        "profile": value.profile,
        "search": {"identity": value.search.identity, **_allowed(dataclasses.asdict(value.search))},
        "policy": {"identity": value.policy.identity, **_allowed(dataclasses.asdict(value.policy))},
    }
    _COMPUTE_CONFIGURATION_CACHE[value.identity] = result
    return result


def _behavior_identity(value) -> dict | str | None:
    if value is None or isinstance(value, str):
        return value
    from common.ledger import BehaviorIdentity

    if not isinstance(value, BehaviorIdentity):
        raise TypeError("behavior_identity must be a BehaviorIdentity")
    return {field.name: str(getattr(value, field.name))
            for field in dataclasses.fields(BehaviorIdentity)}


def _action(action) -> dict:
    identity = getattr(action, "identity", action)
    if hasattr(identity, "kind") and hasattr(identity, "parts"):
        wire_identity = {"kind": identity.kind, "parts": _allowed(identity.parts)}
    else:
        wire_identity = _allowed(identity)
    selection = list(getattr(action, "selection", ()))
    return {"id": _identifier(wire_identity),
            "identity": wire_identity, "selection": selection}


def _continuation(value) -> dict | None:
    if value is None:
        return None
    return {
        "state_delta": float(value.state_delta),
        "action_opportunity": float(value.action_opportunity),
        "continues_turn": bool(value.continues_turn),
        "zones_created": list(value.zones_created),
        "zones_replaced": list(value.zones_replaced),
        "allowances_consumed": list(value.allowances_consumed),
        "immediately_usable_outputs": list(value.immediately_usable_outputs),
        "opportunities_created": list(value.opportunities_created),
        "opportunities_preserved": list(value.opportunities_preserved),
        "opportunities_consumed": list(value.opportunities_consumed),
    }


def _successor(value) -> dict:
    return {
        "probability": float(value.probability),
        "valuation": _valuation(value.valuation),
        "ended": bool(value.ended),
        "observation": _observation(value.state),
        "trace": {
            "schema_version": int(value.trace.schema_version),
            "start_position_key": value.trace.start_position_key,
            "actions": [_action(action) for action in value.trace.actions],
            "terminal_position_key": value.trace.terminal_position_key,
        },
        "action_path": [_action(action) for action in value.action_path],
        "status": value.status.value,
        "failure_code": None if value.failure is None else "successor_failure",
    }


def _policy_evidence(value) -> dict | None:
    if value is None:
        return None
    from common.ledger import PrizeMap

    if not isinstance(value, PrizeMap):
        raise TypeError("unsupported policy evidence")
    return {"kind": "prize_map", **_allowed(value.as_dict())}


def _opponent_snapshot(value) -> dict | None:
    if value is None:
        return None
    from common.opponent import OpponentSnapshot

    if not isinstance(value, OpponentSnapshot):
        raise TypeError("opponent_snapshot must be an OpponentSnapshot")
    data = value.canonical_data()
    data["failures"] = [
        {"subsystem": failure.subsystem.value} for failure in value.failures
    ]
    return {"identity": value.identity, "snapshot": _allowed(data)}


def build_decision_record(result, state, *, episode_key: str, decision_index: int,
                          parent_decision_id: str | None, selection: tuple[int, ...],
                          evaluation_model: dict, compute_configuration: dict,
                          provider_configuration: dict,
                          provenance: dict, decision_seconds: float,
                          decision_limit_seconds: float | None = None,
                          deadline_hit: bool | None = None,
                          opponent_snapshot=None) -> dict:
    """Build one lossless, hidden-safe record from the typed coordinator result."""

    if not result.roster.legal_actions_proven:
        raise ValueError("telemetry requires an authoritative legal-action roster proof")
    legal_actions = tuple(state.legal_actions)
    legal_proof = tuple((action.identity, tuple(action.selection))
                        for action in legal_actions)
    if legal_proof != result.roster.legal_action_identities:
        raise ValueError("telemetry legal actions differ from the proven candidate roster")
    actions = [_action(action) for action in legal_actions]
    action_ids = {
        tuple(getattr(action, "selection", ())): saved["id"]
        for action, saved in zip(legal_actions, actions)
    }
    candidates = []
    for candidate in result.roster.candidates:
        delta = candidate.delta
        action_id = action_ids.get(tuple(getattr(candidate.action, "selection", ())))
        if action_id is None:
            raise ValueError("candidate cannot join the ObservationState legal action table")
        candidates.append({
            "action_id": action_id,
            "disposition": candidate.disposition.value,
            "status": candidate.status.value,
            "delta": None if delta is None else {
                "total": float(delta.total), "scale": _scale(delta.scale),
                "components": _components(delta.components),
            },
            "search_value": (None if candidate.search_value is None else {
                "total": float(candidate.search_value.total),
                "scale": _scale(candidate.search_value.scale),
            }),
            "prior": candidate.prior,
            "gaps": list(candidate.gaps),
            "successors": [_successor(successor) for successor in candidate.successors],
            "continuation": _continuation(candidate.continuation),
            "policy_tie_break": _allowed(candidate.policy_tie_break),
            "policy_evidence": _policy_evidence(candidate.policy_evidence),
        })
    chosen = result.chosen_candidate
    if chosen is None:
        raise ValueError("Ledger decision requires a chosen candidate")
    chosen_id = action_ids[tuple(getattr(chosen.action, "selection", ()))]
    record = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "record_type": "decision",
        "record_id": "",
        "episode": {"key": str(episode_key)},
        "decision": {
            "variant": "ledger",
            "index": int(decision_index),
            "parent_id": parent_decision_id,
            "seat": int(state.seat),
            "turn": int(state.turn.number),
            "position_key": state.position_key,
            "decision_key": state.decision_key,
            "chosen_action_id": chosen_id,
            "selection": list(selection),
            "policy_reason": result.policy_reason.value,
        },
        "observation": _observation(state),
        "opponent_snapshot": _opponent_snapshot(opponent_snapshot),
        "actions": actions,
        "root": _valuation(result.baseline),
        "candidates": candidates,
        "search": {
            "nodes_visited": int(result.search.nodes_visited),
            "stop_reason": result.search.stop_reason,
            "frontier": _allowed(result.search.frontier),
            "failure": (None if result.search.failure is None else {
                "stage": result.search.failure.stage.value,
                "error_type": result.search.failure.error_type,
            }),
            "trace": (None if result.trace is None else {
                "nodes_visited": int(result.trace.nodes_visited),
                "stop_reason": result.trace.stop_reason,
                "frontier": _allowed(result.trace.frontier),
                "chosen_action_id": (None if result.trace.chosen_action is None else
                                     _action(result.trace.chosen_action)["id"]),
                "action_paths": [[_action(action) for action in path]
                                 for path in result.trace.action_paths],
            }),
        },
        "behavior_identity": _behavior_identity(result.behavior_identity),
        "configuration": {
            "evaluation_model": _evaluation_model_configuration(evaluation_model),
            "compute": _compute_configuration(compute_configuration),
            "provider": _allowed(provider_configuration),
        },
        "provenance": _allowed(provenance),
        "timing": {
            "decision_seconds": float(decision_seconds),
            "decision_limit_seconds": (None if decision_limit_seconds is None
                                       else float(decision_limit_seconds)),
            "deadline_hit": None if deadline_hit is None else bool(deadline_hit),
        },
        "completeness": ("unavailable" if any(
            candidate.status.value == "unavailable" for candidate in result.roster.candidates
        ) else "estimated" if any(
            candidate.status.value == "estimated" for candidate in result.roster.candidates
        ) else "complete"),
    }
    record["record_id"] = _record_identifier(record)
    return validate_record(record)


def build_pregame_record(decision, state, *, episode_key: str, decision_index: int,
                         parent_decision_id: str | None, provenance: dict,
                         decision_seconds: float,
                         decision_limit_seconds: float | None = None,
                         deadline_hit: bool | None = None) -> dict:
    actions = [_action(action) for action in state.legal_actions]
    chosen_index = next((index for index, legal in enumerate(state.legal_actions)
                         if tuple(decision.chosen) in legal.equivalent_selections), None)
    if chosen_index is None:
        raise ValueError("pregame selection is not in the legal action table")
    chosen = actions[chosen_index]
    chosen["selection"] = list(decision.chosen)
    policy_action = _action(decision.action)
    record = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "record_type": "decision",
        "record_id": "",
        "episode": {"key": str(episode_key)},
        "decision": {
            "variant": "declarative_pregame",
            "index": int(decision_index),
            "parent_id": parent_decision_id,
            "seat": int(state.seat),
            "turn": int(state.turn.number),
            "position_key": state.position_key,
            "decision_key": state.decision_key,
            "chosen_action_id": chosen["id"],
            "selection": list(decision.chosen),
            "policy_action": policy_action["identity"],
        },
        "observation": _observation(state),
        "opponent_snapshot": None,
        "actions": actions,
        "root": None,
        "candidates": [],
        "search": None,
        "behavior_identity": {"pregame_policy": "declarative-pregame-v1"},
        "configuration": {"evaluation_model": None, "compute": None, "provider": None},
        "provenance": _allowed(provenance),
        "timing": {
            "decision_seconds": float(decision_seconds),
            "decision_limit_seconds": (None if decision_limit_seconds is None
                                       else float(decision_limit_seconds)),
            "deadline_hit": None if deadline_hit is None else bool(deadline_hit),
        },
        "completeness": "not_evaluated",
    }
    record["record_id"] = _record_identifier(record)
    return validate_record(record)


def runtime_provenance(*, deck_name: str, opponent_knowledge_identity: str = "") -> dict:
    manifested = os.environ.get("AGENT_RUNTIME_PROVENANCE")
    if manifested:
        loaded = json.loads(manifested)
        _exact_fields(loaded, {"agent", "artifact", "code", "data"}, "runtime provenance")
        return _allowed(loaded)
    path = Path(__file__).with_name("build_provenance.json")
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        result = _allowed(loaded)
        _exact_fields(result, {"agent", "artifact", "code", "data"},
                      "runtime provenance")
        if result["artifact"] == "source-tree" or result["code"] == "source-tree":
            raise ValueError("runtime provenance contains placeholder identity")
        return result
    artifact, code, cards = _source_provenance()
    return {
        "artifact": artifact,
        "code": code,
        "agent": str(deck_name),
        "data": {
            "cards": cards,
            "opponent_knowledge": str(opponent_knowledge_identity),
        },
    }


@lru_cache(maxsize=1)
def _source_provenance() -> tuple[str, str, str]:
    root = next((parent for parent in Path(__file__).resolve().parents
                 if (parent / ".git").exists()), None)
    if root is None:
        raise ValueError("runtime source provenance is unavailable")
    code = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    digest = hashlib.sha256()
    for source in sorted((root / "src").rglob("*.py")):
        digest.update(source.relative_to(root).as_posix().encode("utf-8"))
        digest.update(source.read_bytes())
    from common.cards import card_store
    from common.ledger.worth import content_identity

    return digest.hexdigest(), code, content_identity(card_store())


def build_episode_receipt(*, episode_key: str, reservations) -> dict:
    if reservations is None:
        raise ValueError("Episode Telemetry Receipt requires journal reservations")
    rows = [_allowed(dict(row)) for row in reservations]
    delivered = [row["record_id"] for row in rows if row["status"] == "delivered"]
    certified = bool(all(row["status"] == "delivered" for row in rows))
    record = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "record_type": "telemetry_receipt",
        "record_id": "",
        "episode": {"key": str(episode_key)},
        "reservations": rows,
        "decision_ids": delivered,
        "certified": certified,
    }
    record["record_id"] = _record_identifier(record)
    return validate_record(record)


def build_outcome_record(*, episode_key: str, decision_records: list[dict],
                         telemetry_receipt: dict,
                         winner: int | None, terminal_reason: str,
                         public_prizes: dict[int, int], rewards: dict[int, float],
                         duration_seconds: float,
                         external_episode_id: str | None = None) -> dict:
    """Build the Episode owner's single terminal label record."""

    decision_ids = []
    for decision in decision_records:
        if decision.get("record_type") != "decision" \
                or (decision.get("episode") or {}).get("key") != episode_key:
            raise ValueError("outcome decisions must belong to the episode")
        decision_ids.append(str(decision["record_id"]))
    if len(set(decision_ids)) != len(decision_ids):
        raise ValueError("outcome decision ids must be unique")
    receipt = validate_record(telemetry_receipt)
    if receipt["record_type"] != "telemetry_receipt" \
            or receipt["episode"]["key"] != episode_key \
            or not receipt["certified"]:
        raise ValueError("Outcome requires a certified Episode Telemetry Receipt")
    if receipt["decision_ids"] != decision_ids:
        raise ValueError("Episode Telemetry Receipt does not match outcome decisions")
    duration = float(duration_seconds)
    if not math.isfinite(duration) or duration < 0.0:
        raise ValueError("outcome duration must be finite and non-negative")
    record = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "record_type": "outcome",
        "record_id": "",
        "episode": {"key": str(episode_key), "external_id": external_episode_id},
        "decision_ids": decision_ids,
        "telemetry_receipt_id": receipt["record_id"],
        "result": {
            "winner": None if winner is None else int(winner),
            "draw": winner is None,
            "terminal_reason": str(terminal_reason),
            "public_prizes": {str(seat): int(count)
                              for seat, count in sorted(public_prizes.items())},
            "rewards": {str(seat): float(value)
                        for seat, value in sorted(rewards.items())},
            "duration_seconds": duration,
        },
    }
    record["record_id"] = _record_identifier(record)
    return validate_record(record)


def frame_record(record: dict) -> tuple[str, ...]:
    """Encode one canonical record into independently bounded transport lines."""

    raw = _canonical_bytes(record if isinstance(record, _ValidatedRecord)
                           else validate_record(record))
    encoded = base64.b64encode(zlib.compress(raw, level=1)).decode("ascii")
    chunks = tuple(encoded[index:index + _FRAME_PAYLOAD_CHARS]
                   for index in range(0, len(encoded), _FRAME_PAYLOAD_CHARS)) or ("",)
    checksum = hashlib.sha256(raw).hexdigest()
    frames = []
    for index, chunk in enumerate(chunks):
        envelope = {
            "schema": _FRAME_SCHEMA,
            "transport_version": _FRAME_VERSION,
            "record_id": record["record_id"],
            "chunk_index": index,
            "chunk_count": len(chunks),
            "checksum": checksum,
            "encoding": "zlib+base64",
            "data": chunk,
        }
        line = f"{TAG} " + json.dumps(envelope, separators=(",", ":"), sort_keys=True)
        if len(line.encode("utf-8")) > MAX_FRAME_BYTES:
            raise ValueError("telemetry transport frame exceeds byte limit")
        frames.append(line)
    return tuple(frames)


class RecordAssembler:
    """Reassemble validated transport frames in any arrival order."""

    def __init__(self):
        self._pending: dict[str, dict] = {}

    def ingest(self, line: str) -> dict | None:
        prefix = f"{TAG} "
        if not line.startswith(prefix):
            raise ValueError("not a telemetry frame")
        if len(line.encode("utf-8")) > MAX_FRAME_BYTES:
            raise ValueError("telemetry transport frame exceeds byte limit")
        frame = json.loads(
            line[len(prefix):],
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {value}")),
        )
        expected = {
            "schema", "transport_version", "record_id", "chunk_index", "chunk_count",
            "checksum", "encoding", "data",
        }
        if set(frame) != expected or frame["schema"] != _FRAME_SCHEMA \
                or frame["transport_version"] != _FRAME_VERSION \
                or frame["encoding"] != "zlib+base64":
            raise ValueError("unsupported telemetry transport frame")
        record_id = str(frame["record_id"])
        count = int(frame["chunk_count"])
        index = int(frame["chunk_index"])
        if count <= 0 or not 0 <= index < count:
            raise ValueError("invalid telemetry chunk bounds")
        pending = self._pending.setdefault(record_id, {
            "count": count, "checksum": frame["checksum"], "chunks": {},
        })
        if pending["count"] != count or pending["checksum"] != frame["checksum"]:
            raise ValueError("conflicting telemetry frame metadata")
        previous = pending["chunks"].setdefault(index, frame["data"])
        if previous != frame["data"]:
            raise ValueError("conflicting duplicate telemetry chunk")
        if len(pending["chunks"]) != count:
            return None
        encoded = "".join(pending["chunks"][part] for part in range(count))
        try:
            raw = zlib.decompress(base64.b64decode(encoded, validate=True))
        except (ValueError, zlib.error) as exc:
            raise ValueError("invalid telemetry frame payload") from exc
        if hashlib.sha256(raw).hexdigest() != pending["checksum"]:
            raise ValueError("telemetry record checksum mismatch")
        record = json.loads(
            raw,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {value}")),
        )
        if record.get("record_id") != record_id:
            raise ValueError("telemetry record id mismatch")
        validate_record(record)
        del self._pending[record_id]
        return record


def parse_lines(lines) -> list[dict]:
    """Decode complete telemetry records from tagged log lines; malformed lines are ignored."""

    records = []
    assembler = RecordAssembler()
    for line in lines:
        if not line.startswith(TAG):
            continue
        try:
            raw = json.loads(line[len(TAG):].strip())
            if raw.get("schema") == _FRAME_SCHEMA:
                record = assembler.ingest(line)
                if record is not None:
                    records.append(record)
            else:
                records.append(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return records


def _build_emission(decision, opponent, seat, state, decision_seconds,
                    decision_limit_seconds, deadline_hit, evaluation_model,
                    compute_configuration, provider_configuration, provenance, link) -> dict:
    if decision.decision_result is None:
        return build_pregame_record(
            decision, state, provenance=provenance or {},
            decision_seconds=float(decision_seconds or 0.0),
            decision_limit_seconds=decision_limit_seconds,
            deadline_hit=deadline_hit, **link)
    return build_decision_record(
        decision.decision_result, state, selection=tuple(decision.chosen),
        evaluation_model=evaluation_model,
        compute_configuration=compute_configuration,
        provider_configuration=provider_configuration,
        provenance=provenance or {},
        decision_seconds=float(decision_seconds or 0.0),
        decision_limit_seconds=decision_limit_seconds,
        deadline_hit=deadline_hit, opponent_snapshot=opponent, **link)


def emit(decision, *, opponent=None, seat=None, state=None, out=None, decision_seconds=None,
         decision_limit_seconds=None, deadline_hit=None, session=None,
         evaluation_model=None, compute_configuration=None, provider_configuration=None,
         provenance=None) -> None:
    started = perf_counter()
    if state is None or seat is None or session is None:
        raise ValueError("Ledger telemetry requires state, seat, and session")
    reservation = session.reserve_decision(
        seat=int(seat), position_key=state.position_key, decision_key=state.decision_key)
    reserved_id = reservation["record_id"]
    link = {key: reservation[key] for key in (
        "episode_key", "decision_index", "parent_decision_id")}
    captured = _CAPTURE.get()
    if captured is not None:
        captured.register_session(session)
    try:
        record = _build_emission(
            decision, opponent, seat, state, decision_seconds, decision_limit_seconds,
            deadline_hit, evaluation_model, compute_configuration, provider_configuration,
            provenance, link)
        if record["record_id"] != reserved_id:
            raise ValueError("reserved telemetry decision id mismatch")
    except Exception as exc:
        session.fail_decision(
            record_id=reserved_id, phase="emission", error_type=type(exc).__name__)
        raise
    session.commit_decision(seat=int(seat), record_id=reserved_id)
    constructed = perf_counter()
    if captured is not None:
        captured.construction_seconds += constructed - started
    suppress_output = _SUPPRESS_OUTPUT.get()

    def deliver() -> dict:
        delivery_started = perf_counter()
        try:
            if not suppress_output:
                print("\n".join(frame_record(record)), file=out or sys.stderr, flush=True)
            session.deliver_decision(record_id=reserved_id)
        except Exception as exc:
            session.fail_decision(
                record_id=reserved_id, phase="delivery", error_type=type(exc).__name__)
            raise
        finally:
            if captured is not None:
                captured.delivery_seconds += perf_counter() - delivery_started
        return record

    if captured is not None or out is not None:
        record = deliver()
        if captured is not None:
            captured.append(record)
            captured.emit_seconds += perf_counter() - started
        return

    global _CALLER_SECONDS
    future = _EMITTER.submit(deliver)
    _PENDING[:] = [pending for pending in _PENDING
                   if not pending.done() or pending.exception() is not None]
    _PENDING.append(future)
    future.add_done_callback(
        lambda completed: print("telemetry emit failed", file=sys.stderr, flush=True)
        if completed.exception() is not None else None)
    _CALLER_SECONDS += perf_counter() - started


def take_caller_seconds() -> float:
    global _CALLER_SECONDS
    elapsed = _CALLER_SECONDS
    _CALLER_SECONDS = 0.0
    return elapsed


def flush() -> None:
    pending = tuple(_PENDING)
    _PENDING.clear()
    for future in pending:
        future.result()


@contextmanager
def capture_records(*, suppress_output: bool = False):
    records = _CapturedRecords()
    token = _CAPTURE.set(records)
    output_token = _SUPPRESS_OUTPUT.set(bool(suppress_output))
    try:
        yield records
    finally:
        _SUPPRESS_OUTPUT.reset(output_token)
        _CAPTURE.reset(token)


__all__ = [
    "MAX_FRAME_BYTES", "RecordAssembler", "TAG", "TelemetrySession",
    "build_decision_record", "build_episode_receipt", "build_outcome_record",
    "capture_records", "emit", "episode_context", "flush", "frame_record",
    "migrate_record", "runtime_provenance", "take_caller_seconds",
    "validate_record",
]
