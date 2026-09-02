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
from .decision import LEDGER_VALUE_SCALE


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
        artifact = json.loads(Path(path).read_text(encoding="utf-8"))
        required = {
            "schema", "schema_version", "baseline_identity", "source", "heldout",
            "objective", "grid", "configuration", "mean_acceptable_log_loss",
            "rows", "deck_smoke",
        }
        if not isinstance(artifact, dict) or set(artifact) != required \
                or artifact["schema"] != "ledger.policy-calibration" \
                or artifact["schema_version"] != 1:
            raise ValueError("invalid Ledger policy calibration artifact")
        if artifact["baseline_identity"] != expected_baseline_identity:
            raise ValueError("Ledger policy calibration baseline identity mismatch")
        if artifact["heldout"] != {"consumed": False, "paths": []}:
            raise ValueError("Ledger policy calibration consumed held-out evidence")
        if set(artifact["deck_smoke"]) != set(AUTHORITATIVE_DECKS):
            raise ValueError("Ledger policy calibration lacks a deck-root smoke check")
        payload = artifact["configuration"]
        configuration = cls(
            float(payload["temperature"]),
            float(payload["uniform_mix"]),
            tuple(EvaluationStatus(status) for status in payload["accepted_statuses"]),
            int(payload["schema_version"]),
        )
        if configuration.identity != payload["identity"]:
            raise ValueError("Ledger policy calibration configuration identity mismatch")
        return configuration


@dataclass(frozen=True, slots=True)
class LedgerPolicyBaseline:
    baseline_identity: str
    evaluator_identity: str
    evaluation_model_identities: tuple[str, ...]
    value_scale_identity: str = LEDGER_VALUE_SCALE.identity

    def __post_init__(self):
        if (not self.baseline_identity or not self.evaluator_identity
                or not self.evaluation_model_identities or not self.value_scale_identity):
            raise ValueError("Ledger policy baseline identities are required")
        if len(set(self.evaluation_model_identities)) != len(self.evaluation_model_identities):
            raise ValueError("Ledger policy baseline contains duplicate Evaluation Models")

    @classmethod
    def from_manifest(cls, manifest: dict) -> "LedgerPolicyBaseline":
        identities = baseline_identities(manifest)
        return cls(
            identities.baseline,
            identities.evaluator,
            identities.evaluation_models,
        )

    @classmethod
    def load(cls, expected_identity: str, path: Path | str) -> "LedgerPolicyBaseline":
        return cls.from_manifest(require_baseline(expected_identity, path))


@dataclass(frozen=True, slots=True)
class LedgerPolicyModel:
    configuration: LedgerPolicyConfiguration
    baseline: LedgerPolicyBaseline

    @property
    def identity(self) -> str:
        return (f"ledger-policy-model-v1:{self.baseline.baseline_identity}:"
                f"{self.configuration.identity}")

    def priors(self, request: PolicyRequest) -> PolicyDistribution:
        self.validate_source(request.source)
        candidates = request.roster.candidates
        if any(candidate.delta is not None
               and candidate.delta.scale.identity != request.source.value_scale_identity
               for candidate in candidates):
            raise ValueError("Ledger policy candidate Value Scale mismatch")
        if len(candidates) == 1:
            candidate = candidates[0]
            return self._distribution(
                request, (1.0,), (1.0,), None,
                (None if candidate.delta is None else candidate.delta.total,))
        reason = self._fallback_reason(candidates)
        if reason is not None:
            uniform = tuple(1.0 / len(candidates) for _candidate in candidates)
            raw = tuple(None if candidate.delta is None else candidate.delta.total
                        for candidate in candidates)
            return self._distribution(request, uniform, uniform, reason, raw)
        raw = tuple(candidate.delta.total for candidate in candidates)
        greatest = max(raw)
        weights = tuple(math.exp((value - greatest) / self.configuration.temperature)
                        for value in raw)
        total = math.fsum(weights)
        normalized = tuple(weight / total for weight in weights)
        uniform = 1.0 / len(candidates)
        priors = tuple((1.0 - self.configuration.uniform_mix) * score
                       + self.configuration.uniform_mix * uniform
                       for score in normalized)
        return self._distribution(request, normalized, priors, None, raw)

    def validate_source(self, source) -> None:
        if source.baseline_identity != self.baseline.baseline_identity:
            raise ValueError("Ledger policy baseline identity mismatch")
        if source.evaluator_identity != self.baseline.evaluator_identity:
            raise ValueError("Ledger policy evaluator identity mismatch")
        if source.evaluation_model_identity not in self.baseline.evaluation_model_identities:
            raise ValueError("Ledger policy Evaluation Model identity mismatch")
        if source.value_scale_identity != self.baseline.value_scale_identity:
            raise ValueError("Ledger policy Value Scale identity mismatch")

    def _fallback_reason(self, candidates) -> PolicyFallbackReason | None:
        for candidate in candidates:
            if candidate.status is EvaluationStatus.UNAVAILABLE or candidate.delta is None:
                return PolicyFallbackReason.UNAVAILABLE_CANDIDATE
            if candidate.status not in self.configuration.accepted_statuses:
                return PolicyFallbackReason.UNACCEPTED_STATUS
        return None

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


__all__ = ("LedgerPolicyBaseline", "LedgerPolicyConfiguration", "LedgerPolicyModel")
