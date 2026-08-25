"""Immutable one-ply Ledger Baseline identity validation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


SCHEMA = "ledger.baseline"
SCHEMA_VERSION = 1
AUTHORITATIVE_DECKS = ("dragapult_ex", "mega_lucario", "mega_starmie")
BLUNDER_POLICY = {
    "during_experiments": "record_only",
    "retune": "create_new_baseline_version",
}
REQUIRED_GATES = {
    "historical_corrections", "cross_deck_regressions",
    "native_full_games", "twin_full_games",
}
_SHA256_HEX_LENGTH = hashlib.sha256().digest_size * len("00")


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _identity(manifest: dict) -> str:
    return hashlib.sha256(_canonical({**manifest, "baseline_id": None})).hexdigest()


def certified_evidence(manifest: dict) -> dict:
    runs = manifest["correction_runs"]
    return {
        "source_identity": manifest["source_identity"],
        "ledger": manifest["ledger"],
        "contestants": manifest["contestants"],
        "behavior_identities": manifest["behavior_identities"],
        "correction_runs": [
            {"run_id": run["run_id"], "manifest_sha256": run["manifest_sha256"]}
            for run in runs
        ],
        "tuning_bundle_ids": sorted(
            str(slot["bundle_id"]) for run in runs for slot in run["tuning"]),
        "heldout_bundle_ids": sorted(
            str(slot["bundle_id"]) for run in runs for slot in run["heldout"]),
        "tuning_ledger_decisions": sum(
            int(run["report"]["tuning_ledger_decisions"]) for run in runs),
    }


def validate_certification(report: dict) -> dict:
    gates = report.get("gates") if isinstance(report, dict) else None
    names = {gate.get("name") for gate in gates or () if isinstance(gate, dict)}
    if report.get("passed") is not True or not isinstance(gates, list) \
            or len(gates) != len(REQUIRED_GATES) \
            or names != REQUIRED_GATES or any(
                gate.get("passed") is not True or not gate.get("command")
                or len(str(gate.get("output_sha256"))) != _SHA256_HEX_LENGTH for gate in gates):
        raise ValueError("Ledger Baseline certification gates did not pass")
    review = report.get("manual_review") or {}
    if review.get("completed") is not True or int(review.get("reviewed_decisions") or 0) <= 0:
        raise ValueError("Ledger Baseline manual review is incomplete")
    if not isinstance(review.get("episode_ids"), list) or not review["episode_ids"]:
        raise ValueError("Ledger Baseline manual review lacks Episode identities")
    heldout = report.get("heldout") or {}
    if heldout.get("passed") is not True \
            or not isinstance(heldout.get("episode_ids"), list) or not heldout["episode_ids"]:
        raise ValueError("Ledger Baseline held-out evaluation did not pass")
    target = report.get("tuning_target") or {}
    before, after = target.get("before"), target.get("after")
    if not target.get("name") or not isinstance(before, (int, float)) \
            or not isinstance(after, (int, float)) or after <= before:
        raise ValueError("Ledger Baseline tuning target did not improve")
    regressions = report.get("regressions") or {}
    if regressions.get("passed") is not True or regressions.get("unreported") != []:
        raise ValueError("Ledger Baseline has unreported regressions")
    if len(str(report.get("corrections_identity") or "")) != _SHA256_HEX_LENGTH:
        raise ValueError("Ledger Baseline certification lacks Corrections identity")
    return report


def validate_baseline(manifest: dict) -> dict:
    required = {
        "schema", "schema_version", "baseline_id", "created_at", "focals",
        "source_identity", "ledger", "contestants", "behavior_identities",
        "correction_runs", "reports", "heldout_manifest", "corrections",
        "corrections_identity", "certification", "blunder_policy", "known_weaknesses",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        raise ValueError("invalid Ledger Baseline fields")
    if manifest["schema"] != SCHEMA or manifest["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported Ledger Baseline schema")
    if manifest["focals"] != list(AUTHORITATIVE_DECKS) \
            or set(manifest["focals"]) != set(manifest["reports"]):
        raise ValueError("Ledger Baseline lacks per-deck reports")
    if set(manifest["focals"]) != set(manifest["heldout_manifest"]):
        raise ValueError("Ledger Baseline lacks per-deck held-out state manifests")
    if not manifest["correction_runs"] or not manifest["behavior_identities"]:
        raise ValueError("Ledger Baseline lacks Correction Run behavior evidence")
    if not manifest["corrections"] or not all(
            int(item.get("records", 0)) > 0 for item in manifest["corrections"]):
        raise ValueError("Ledger Baseline requires a manual Correction")
    expected_corrections = hashlib.sha256(_canonical(manifest["corrections"])).hexdigest()
    if manifest["corrections_identity"] != expected_corrections:
        raise ValueError("Ledger Baseline corrections identity mismatch")
    if manifest["blunder_policy"] != BLUNDER_POLICY:
        raise ValueError("Ledger Baseline blunder policy is invalid")
    certification = manifest["certification"]
    if set(certification) != {"path", "sha256", "report"}:
        raise ValueError("Ledger Baseline certification artifact is invalid")
    report = validate_certification(certification["report"])
    evidence = certified_evidence(manifest)
    if report.get("evidence") != evidence:
        raise ValueError("Ledger Baseline certification evidence does not match")
    if report["manual_review"]["reviewed_decisions"] != evidence["tuning_ledger_decisions"]:
        raise ValueError("Ledger Baseline manual review decision count is incomplete")
    if len(str(certification["sha256"])) != _SHA256_HEX_LENGTH:
        raise ValueError("Ledger Baseline certification artifact hash is invalid")
    if manifest["baseline_id"] != _identity(manifest):
        raise ValueError("Ledger Baseline content hash mismatch")
    return manifest


def load_baseline(path: Path | str) -> dict:
    return validate_baseline(json.loads(Path(path).read_text(encoding="utf-8")))


def require_baseline(expected_id: str, path: Path | str) -> dict:
    baseline = load_baseline(path)
    if baseline["baseline_id"] != str(expected_id):
        raise ValueError(
            f"baseline identity mismatch: expected {expected_id}, got {baseline['baseline_id']}")
    return baseline


__all__ = ("AUTHORITATIVE_DECKS", "BLUNDER_POLICY", "REQUIRED_GATES",
           "certified_evidence", "load_baseline", "require_baseline", "validate_baseline",
           "validate_certification")
