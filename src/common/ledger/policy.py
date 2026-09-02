from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from common.decision import (
    EvaluationStatus,
    PolicyActionEvidence,
    PolicyDistribution,
    PolicyFallbackReason,
    PolicyRequest,
)

from .baseline import AUTHORITATIVE_DECKS, baseline_identities, require_baseline


POLICY_CONFIG_ID_DIGEST_BYTES = 8


@dataclass(frozen=True, slots=True)
class LedgerPolicyConfiguration:
    temperature: float
    uniform_mix: float
    accepted_statuses: tuple[EvaluationStatus, ...] = (EvaluationStatus.COMPLETE,)
    schema_version: int = 1

    def __post_init__(self):
        if self.schema_version != 1:
            raise ValueError("unsupported Ledger policy configuration schema version")
        if not math.isfinite(self.temperature) or self.temperature <= 0.0:
            raise ValueError("Ledger policy temperature must be positive and finite")
        if not math.isfinite(self.uniform_mix) or not 0.0 < self.uniform_mix < 1.0:
            raise ValueError("Ledger policy uniform mix must be strictly between zero and one")
        allowed = {EvaluationStatus.COMPLETE, EvaluationStatus.ESTIMATED}
        statuses = tuple(self.accepted_statuses)
        if (not statuses or set(statuses) - allowed
                or len(set(statuses)) != len(statuses)
                or any(not isinstance(status, EvaluationStatus) for status in statuses)):
            raise ValueError("Ledger policy accepted statuses are invalid")
        object.__setattr__(self, "accepted_statuses", tuple(
            sorted(statuses, key=lambda status: status.value)))

    @property
    def identity(self) -> str:
        blob = json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        return hashlib.blake2b(
            blob, digest_size=POLICY_CONFIG_ID_DIGEST_BYTES).hexdigest()

    @classmethod
    def load_calibrated(cls, expected_baseline_identity: str,
                        path: Path | str) -> "LedgerPolicyConfiguration":
        return LedgerPolicyCalibration.load(
            expected_baseline_identity, path).configuration


@dataclass(frozen=True, slots=True)
class LedgerPolicyDeckSmoke:
    deck: str
    rows: int
    mean_acceptable_log_loss: float
    all_priors_finite_normalized_nonzero: bool
    live_greedy_disagreements: int
    disagreement_samples: tuple[str, ...] = ()

    def __post_init__(self):
        if (not self.deck or self.rows <= 0
                or not math.isfinite(self.mean_acceptable_log_loss)
                or self.live_greedy_disagreements < 0
                or not self.all_priors_finite_normalized_nonzero):
            raise ValueError("invalid Ledger policy deck smoke result")

    def as_dict(self) -> dict:
        return {
            "all_priors_finite_normalized_nonzero":
                self.all_priors_finite_normalized_nonzero,
            "disagreement_samples": list(self.disagreement_samples),
            "live_greedy_disagreements": self.live_greedy_disagreements,
            "mean_acceptable_log_loss": self.mean_acceptable_log_loss,
            "rows": self.rows,
        }

    @classmethod
    def from_dict(cls, deck: str, value: dict) -> "LedgerPolicyDeckSmoke":
        required = {
            "all_priors_finite_normalized_nonzero", "disagreement_samples",
            "live_greedy_disagreements", "mean_acceptable_log_loss", "rows",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise ValueError("invalid Ledger policy deck smoke fields")
        return cls(
            deck,
            int(value["rows"]),
            float(value["mean_acceptable_log_loss"]),
            value["all_priors_finite_normalized_nonzero"] is True,
            int(value["live_greedy_disagreements"]),
            tuple(str(item) for item in value["disagreement_samples"]),
        )


@dataclass(frozen=True, slots=True)
class LedgerPolicyCalibration:
    baseline_identity: str
    value_scale_identity: str
    source_path: str
    source_sha256: str
    source_partition: str
    objective: str
    temperatures: tuple[float, ...]
    uniform_mixes: tuple[float, ...]
    configuration: LedgerPolicyConfiguration
    mean_acceptable_log_loss: float
    rows: int
    deck_smoke: tuple[LedgerPolicyDeckSmoke, ...]
    schema_version: int = 1

    def __post_init__(self):
        if self.schema_version != 1 or not all((
                self.baseline_identity, self.value_scale_identity, self.source_path,
                self.source_sha256, self.source_partition, self.objective)):
            raise ValueError("invalid Ledger policy calibration identity")
        if not self.temperatures or not self.uniform_mixes or self.rows <= 0 \
                or not math.isfinite(self.mean_acceptable_log_loss):
            raise ValueError("invalid Ledger policy calibration metrics")
        if {item.deck for item in self.deck_smoke} != set(AUTHORITATIVE_DECKS):
            raise ValueError("Ledger policy calibration lacks a deck-root smoke check")

    def as_dict(self) -> dict:
        return {
            "baseline_identity": self.baseline_identity,
            "configuration": {
                "accepted_statuses": [
                    status.value for status in self.configuration.accepted_statuses],
                "identity": self.configuration.identity,
                "schema_version": self.configuration.schema_version,
                "temperature": self.configuration.temperature,
                "uniform_mix": self.configuration.uniform_mix,
            },
            "deck_smoke": {
                item.deck: item.as_dict() for item in sorted(
                    self.deck_smoke, key=lambda result: result.deck)},
            "grid": {
                "configurations": len(self.temperatures) * len(self.uniform_mixes),
                "temperatures": list(self.temperatures),
                "uniform_mixes": list(self.uniform_mixes),
            },
            "heldout": {"consumed": False, "paths": []},
            "mean_acceptable_log_loss": self.mean_acceptable_log_loss,
            "objective": self.objective,
            "rows": self.rows,
            "schema": "ledger.policy-calibration",
            "schema_version": self.schema_version,
            "source": {
                "partition": self.source_partition,
                "path": self.source_path,
                "sha256": self.source_sha256,
            },
            "value_scale_identity": self.value_scale_identity,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "LedgerPolicyCalibration":
        required = {
            "schema", "schema_version", "baseline_identity", "value_scale_identity",
            "source", "heldout", "objective", "grid", "configuration",
            "mean_acceptable_log_loss", "rows", "deck_smoke",
        }
        if not isinstance(value, dict) or set(value) != required \
                or value["schema"] != "ledger.policy-calibration" \
                or value["schema_version"] != 1 \
                or value["heldout"] != {"consumed": False, "paths": []}:
            raise ValueError("invalid Ledger policy calibration artifact")
        source, grid, payload = value["source"], value["grid"], value["configuration"]
        if set(source) != {"path", "sha256", "partition"} \
                or set(grid) != {"temperatures", "uniform_mixes", "configurations"} \
                or set(payload) != {"temperature", "uniform_mix", "accepted_statuses",
                                        "schema_version", "identity"}:
            raise ValueError("invalid Ledger policy calibration fields")
        configuration = LedgerPolicyConfiguration(
            float(payload["temperature"]),
            float(payload["uniform_mix"]),
            tuple(EvaluationStatus(status) for status in payload["accepted_statuses"]),
            int(payload["schema_version"]),
        )
        if configuration.identity != payload["identity"] \
                or int(grid["configurations"]) != (
                    len(grid["temperatures"]) * len(grid["uniform_mixes"])):
            raise ValueError("Ledger policy calibration identity mismatch")
        return cls(
            str(value["baseline_identity"]),
            str(value["value_scale_identity"]),
            str(source["path"]),
            str(source["sha256"]),
            str(source["partition"]),
            str(value["objective"]),
            tuple(float(item) for item in grid["temperatures"]),
            tuple(float(item) for item in grid["uniform_mixes"]),
            configuration,
            float(value["mean_acceptable_log_loss"]),
            int(value["rows"]),
            tuple(LedgerPolicyDeckSmoke.from_dict(deck, result)
                  for deck, result in value["deck_smoke"].items()),
            int(value["schema_version"]),
        )

    @classmethod
    def load(cls, expected_baseline_identity: str,
             path: Path | str) -> "LedgerPolicyCalibration":
        artifact = cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
        if artifact.baseline_identity != expected_baseline_identity:
            raise ValueError("Ledger policy calibration baseline identity mismatch")
        return artifact


@dataclass(frozen=True, slots=True)
class LedgerPriorNormalization:
    normalized_scores: tuple[float, ...]
    priors: tuple[float, ...]
    fallback_reason: PolicyFallbackReason | None


def normalize_ledger_priors(
        raw_scores, statuses,
        configuration: LedgerPolicyConfiguration) -> LedgerPriorNormalization:
    raw_scores, statuses = tuple(raw_scores), tuple(statuses)
    if not raw_scores or len(raw_scores) != len(statuses):
        raise ValueError("Ledger policy scores and statuses must be nonempty and aligned")
    if any(score is not None and not math.isfinite(score) for score in raw_scores):
        raise ValueError("Ledger policy scores must be finite")
    if len(raw_scores) == 1:
        return LedgerPriorNormalization((1.0,), (1.0,), None)
    reason = None
    if any(status is EvaluationStatus.UNAVAILABLE or score is None
           for score, status in zip(raw_scores, statuses)):
        reason = PolicyFallbackReason.UNAVAILABLE_CANDIDATE
    elif any(status not in configuration.accepted_statuses for status in statuses):
        reason = PolicyFallbackReason.UNACCEPTED_STATUS
    if reason is not None:
        uniform = tuple(1.0 / len(raw_scores) for _score in raw_scores)
        return LedgerPriorNormalization(uniform, uniform, reason)
    greatest = max(raw_scores)
    weights = tuple(math.exp((score - greatest) / configuration.temperature)
                    for score in raw_scores)
    total = math.fsum(weights)
    normalized = tuple(weight / total for weight in weights)
    uniform = 1.0 / len(raw_scores)
    priors = tuple((1.0 - configuration.uniform_mix) * score
                   + configuration.uniform_mix * uniform for score in normalized)
    return LedgerPriorNormalization(normalized, priors, None)


@dataclass(frozen=True, slots=True)
class LedgerPolicyBaseline:
    baseline_identity: str
    evaluator_identity: str
    evaluation_model_identities: tuple[str, ...]
    value_scale_identity: str

    def __post_init__(self):
        if (not self.baseline_identity or not self.evaluator_identity
                or not self.evaluation_model_identities or not self.value_scale_identity):
            raise ValueError("Ledger policy baseline identities are required")
        if len(set(self.evaluation_model_identities)) != len(self.evaluation_model_identities):
            raise ValueError("Ledger policy baseline contains duplicate Evaluation Models")

    @classmethod
    def from_manifest(cls, manifest: dict,
                      value_scale_identity: str) -> "LedgerPolicyBaseline":
        identities = baseline_identities(manifest)
        return cls(
            identities.baseline,
            identities.evaluator,
            identities.evaluation_models,
            value_scale_identity,
        )

    @classmethod
    def load(cls, expected_identity: str, path: Path | str,
             value_scale_identity: str) -> "LedgerPolicyBaseline":
        return cls.from_manifest(
            require_baseline(expected_identity, path), value_scale_identity)


@dataclass(frozen=True, slots=True)
class LedgerPolicyModel:
    configuration: LedgerPolicyConfiguration
    baseline: LedgerPolicyBaseline

    @property
    def identity(self) -> str:
        return (f"ledger-policy-model-v1:{self.baseline.baseline_identity}:"
                f"{self.baseline.value_scale_identity}:{self.configuration.identity}")

    @classmethod
    def load_calibrated(cls, expected_baseline_identity: str,
                        baseline_path: Path | str,
                        calibration_path: Path | str) -> "LedgerPolicyModel":
        calibration = LedgerPolicyCalibration.load(
            expected_baseline_identity, calibration_path)
        baseline = LedgerPolicyBaseline.load(
            expected_baseline_identity, baseline_path,
            calibration.value_scale_identity)
        return cls(calibration.configuration, baseline)

    def priors(self, request: PolicyRequest) -> PolicyDistribution:
        self.validate_source(request.source)
        candidates = request.roster.candidates
        if any(candidate.delta is not None
               and candidate.delta.scale.identity != request.source.value_scale_identity
               for candidate in candidates):
            raise ValueError("Ledger policy candidate Value Scale mismatch")
        raw = tuple(None if candidate.delta is None else candidate.delta.total
                    for candidate in candidates)
        normalization = normalize_ledger_priors(
            raw, (candidate.status for candidate in candidates), self.configuration)
        return self._distribution(
            request, normalization.normalized_scores, normalization.priors,
            normalization.fallback_reason, raw)

    def validate_source(self, source) -> None:
        if source.baseline_identity != self.baseline.baseline_identity:
            raise ValueError("Ledger policy baseline identity mismatch")
        if source.evaluator_identity != self.baseline.evaluator_identity:
            raise ValueError("Ledger policy evaluator identity mismatch")
        if source.evaluation_model_identity not in self.baseline.evaluation_model_identities:
            raise ValueError("Ledger policy Evaluation Model identity mismatch")
        if source.value_scale_identity != self.baseline.value_scale_identity:
            raise ValueError("Ledger policy Value Scale identity mismatch")

    def _distribution(self, request, normalized, priors, fallback_reason, raw):
        actions = tuple(PolicyActionEvidence(
            identity,
            raw_delta,
            score,
            prior,
            candidate.status,
            fallback_reason,
        ) for identity, raw_delta, score, prior, candidate in zip(
            request.roster.policy_action_identities, raw, normalized, priors,
            request.roster.candidates))
        return PolicyDistribution(
            self.identity,
            self.configuration.identity,
            request.source,
            actions,
            self.configuration.temperature,
            self.configuration.uniform_mix,
            min(priors),
            fallback_reason,
        )


__all__ = ("LedgerPolicyBaseline", "LedgerPolicyCalibration", "LedgerPolicyConfiguration",
           "LedgerPolicyDeckSmoke", "LedgerPolicyModel", "LedgerPriorNormalization",
           "normalize_ledger_priors")
