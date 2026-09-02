"""Process transport and result contracts for independent Teacher roots."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum

from .parity import ExperimentParityManifest
from .teacher_contracts import (
    TeacherSearchConfiguration,
    TeacherSearchResult,
    TeacherStopReason,
)


TEACHER_BATCH_SCHEMA = "cgpy-within-horizon-teacher-batch"
TEACHER_BATCH_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class TeacherExecutionConfiguration:
    schema_version: int = 1
    workers: int = 1
    root_timeout_seconds: float = 660.0

    def __post_init__(self):
        if self.schema_version != 1:
            raise ValueError("unsupported Teacher Execution Configuration schema")
        if self.workers <= 0:
            raise ValueError("workers must be positive")
        if not math.isfinite(self.root_timeout_seconds) or self.root_timeout_seconds <= 0:
            raise ValueError("root_timeout_seconds must be positive and finite")


@dataclass(frozen=True, slots=True)
class TeacherOpponentProfileRecord:
    name: str
    roles: tuple[tuple[int, tuple[str, ...]], ...]
    traits: tuple[tuple[str, bool | str], ...]
    mechanics: tuple[tuple[str, float], ...]
    resources: tuple[tuple[int, float], ...]


@dataclass(frozen=True, slots=True)
class TeacherModelRecord:
    configuration_schema_version: int
    configuration_values: tuple[tuple[str, float], ...]
    prize_protect: tuple[int | str, ...]
    prize_offer: tuple[int | str, ...]
    opponent_profiles: tuple[TeacherOpponentProfileRecord, ...]
    evaluation_model_identity: str
    store_identity: str
    schema_version: int = 1

    @classmethod
    def from_model(cls, model) -> "TeacherModelRecord":
        profiles = tuple(TeacherOpponentProfileRecord(
            str(name),
            tuple((int(card_id), tuple(roles))
                  for card_id, roles in sorted(profile.roles.items())),
            tuple((trait.name, trait.value) for trait in profile.traits),
            tuple((mechanic.name, mechanic.probability)
                  for mechanic in profile.mechanics),
            tuple((int(card_id), float(value))
                  for card_id, value in sorted(profile.resources.items())),
        ) for name, profile in sorted(model.opponent_profiles.items()))
        return cls(
            model.configuration.schema_version, tuple(model.configuration.values),
            tuple(model.prize_plan.protect), tuple(model.prize_plan.offer), profiles,
            model.identity, model.store_identity)

    def to_model(self):
        if self.schema_version != 1:
            raise ValueError("unsupported Teacher Model Record schema")
        from common.ledger import EvaluationModel, OpponentProfile, ValuationConfiguration
        from common.opponent import OpponentMechanic, OpponentTrait
        from common.strategy import PrizePlan

        profiles = {
            profile.name: OpponentProfile(
                dict(profile.roles),
                tuple(OpponentTrait(name, value) for name, value in profile.traits),
                tuple(OpponentMechanic(name, probability)
                      for name, probability in profile.mechanics),
                dict(profile.resources))
            for profile in self.opponent_profiles}
        model = EvaluationModel.build(
            configuration=ValuationConfiguration(
                dict(self.configuration_values),
                schema_version=self.configuration_schema_version),
            prize_plan=PrizePlan(self.prize_protect, self.prize_offer),
            opponent_profiles=profiles)
        if model.identity != self.evaluation_model_identity:
            raise ValueError("Teacher Model Record identity mismatch")
        if model.store_identity != self.store_identity:
            raise ValueError("Teacher Model Record card-store identity mismatch")
        return model


@dataclass(frozen=True, slots=True)
class TeacherBatchCase:
    case_id: str
    snapshot_path: str
    experiment_seed: int
    model: TeacherModelRecord
    search_configuration: TeacherSearchConfiguration = TeacherSearchConfiguration()
    baseline_identity: str | None = None
    parity: ExperimentParityManifest | None = None

    def __post_init__(self):
        if not self.case_id or not self.snapshot_path:
            raise ValueError("Teacher Batch Case identity and snapshot path are required")


class TeacherWorkerStatus(str, Enum):
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class TeacherBatchItem:
    case_id: str
    status: TeacherWorkerStatus
    stop_reason: TeacherStopReason
    result: TeacherSearchResult | None = None
    failure: str | None = None

    def __post_init__(self):
        if self.status is TeacherWorkerStatus.COMPLETED and self.result is None:
            raise ValueError("completed Teacher Batch Item requires a result")
        if self.status is TeacherWorkerStatus.UNAVAILABLE and self.result is not None:
            raise ValueError("unavailable Teacher Batch Item cannot carry a result")


@dataclass(frozen=True, slots=True)
class TeacherBatchResult:
    items: tuple[TeacherBatchItem, ...]
    requested_workers: int
    effective_workers: int
    elapsed_seconds: float
    schema_version: int = TEACHER_BATCH_SCHEMA_VERSION

    def __post_init__(self):
        if self.schema_version != TEACHER_BATCH_SCHEMA_VERSION:
            raise ValueError("unsupported Teacher Batch Result schema")
        if self.requested_workers <= 0:
            raise ValueError("requested_workers must be positive")
        if not 0 <= self.effective_workers <= self.requested_workers:
            raise ValueError("invalid effective Teacher worker count")
        if self.items and self.effective_workers < 1:
            raise ValueError("non-empty Teacher batch requires an effective worker")
        if not math.isfinite(self.elapsed_seconds) or self.elapsed_seconds < 0:
            raise ValueError("Teacher batch elapsed time must be finite and nonnegative")

    def dumps(self) -> str:
        document = {
            "schema": TEACHER_BATCH_SCHEMA,
            "schema_version": self.schema_version,
            "requested_workers": self.requested_workers,
            "effective_workers": self.effective_workers,
            "elapsed_seconds": self.elapsed_seconds,
            "items": [{
                "case_id": item.case_id, "status": item.status.value,
                "stop_reason": item.stop_reason.value, "failure": item.failure,
                "result": None if item.result is None else item.result.document(),
            } for item in self.items],
        }
        return json.dumps(document, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False)

    @classmethod
    def loads(cls, encoded: str) -> "TeacherBatchResult":
        document = json.loads(encoded)
        if (document.get("schema") != TEACHER_BATCH_SCHEMA
                or document.get("schema_version") != TEACHER_BATCH_SCHEMA_VERSION):
            raise ValueError("unsupported Teacher Batch Result schema")
        items = []
        for item in document["items"]:
            result = item["result"]
            items.append(TeacherBatchItem(
                str(item["case_id"]), TeacherWorkerStatus(item["status"]),
                TeacherStopReason(item["stop_reason"]),
                None if result is None else TeacherSearchResult.loads(json.dumps(result)),
                item.get("failure")))
        return cls(
            tuple(items), int(document["requested_workers"]),
            int(document["effective_workers"]), float(document["elapsed_seconds"]),
            int(document["schema_version"]))


__all__ = (
    "TEACHER_BATCH_SCHEMA", "TEACHER_BATCH_SCHEMA_VERSION", "TeacherBatchCase",
    "TeacherBatchItem", "TeacherBatchResult", "TeacherExecutionConfiguration",
    "TeacherModelRecord", "TeacherOpponentProfileRecord", "TeacherWorkerStatus",
)
