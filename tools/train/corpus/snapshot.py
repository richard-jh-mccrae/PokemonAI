from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from .bundle import load_episode_bundle
from .io import atomic_json, canonical_bytes, digest_bytes, read_gzip_jsonl, write_gzip_jsonl
from .replay import CorpusRejection, certify_replay


CORPUS_SCHEMA = "ledger.corpus-decision"
CORPUS_VERSION = 2
SNAPSHOT_SCHEMA = "ledger.corpus-snapshot"


class CorpusIntegrityError(ValueError):
    def __init__(self, rejections: list[dict]):
        self.rejections = tuple(rejections)
        super().__init__(f"Corpus Integrity Gate rejected {len(rejections)} item(s): "
                         f"{rejections[0]['reason']}")


def _terminal_target(outcome: dict, seat: int) -> dict:
    result = outcome["result"]
    return {
        "outcome_id": outcome["record_id"], "winner": result["winner"],
        "draw": result["draw"], "seat": seat,
        "seat_reward": result["rewards"][str(seat)],
        "relative_rewards": {
            "self": result["rewards"][str(seat)],
            "opponent": result["rewards"][str(1 - seat)],
        },
        "terminal_reason": result["terminal_reason"],
        "public_prizes": result["public_prizes"],
        "duration_seconds": result["duration_seconds"],
    }


def _validate_certificate(certificate: dict) -> None:
    if certificate.get("schema_version") != 2 \
            or certificate.get("mode") != "offline_replay":
        raise ValueError("Corpus Decision requires an offline replay certificate")
    for field in ("recorded_legal_actions_valid", "recorded_evaluation_valid",
                  "recorded_successors_valid", "legal_actions_exact", "root_exact",
                  "successors_exact"):
        if certificate.get(field) is not True:
            raise ValueError(f"Corpus replay certificate failed {field}")
    full = certificate.get("full_choice_exact")
    if full is not True and not (
            full is None and certificate.get("exclusion") == "time_budgeted_full_choice"):
        raise ValueError("Corpus replay certificate failed full_choice_exact")


def corpus_decision(decision: dict, receipt: dict, outcome: dict, *, bundle_id: str,
                    replay_certificate: dict) -> dict:
    _validate_certificate(replay_certificate)
    seat = decision["decision"]["seat"]
    candidates = decision["candidates"]
    return {
        "schema": CORPUS_SCHEMA, "schema_version": CORPUS_VERSION,
        "corpus_decision_id": decision["record_id"],
        "origin": {"kind": "native_telemetry", "bundle_ids": [bundle_id],
                   "source_schema": decision["schema"],
                   "source_schema_version": decision["schema_version"],
                   "source_record_id": decision["record_id"],
                   "source_sha256": digest_bytes(canonical_bytes(decision)),
                   "telemetry_receipt_id": receipt["record_id"],
                   "migrations": []},
        "decision": decision,
        "terminal_target": _terminal_target(outcome, seat),
        "supervision": {
            "behavior": {"chosen_action_id": decision["decision"]["chosen_action_id"],
                         "behavior_identity": decision["behavior_identity"]},
            "evaluator": [{"action_id": candidate["action_id"],
                           "delta": candidate["delta"], "status": candidate["status"]}
                          for candidate in candidates],
            "human": {"accepted_action_ids": [], "annotations": []},
        },
        "replay_certificate": replay_certificate,
        "quality": {"integrity": "valid", "signals": []},
    }


def excluded_corpus_decision(decision: dict, receipt: dict, outcome: dict, *,
                             bundle_id: str, reason: str) -> dict:
    seat = decision["decision"]["seat"]
    return {
        "schema": CORPUS_SCHEMA, "schema_version": CORPUS_VERSION,
        "corpus_decision_id": decision["record_id"],
        "origin": {"kind": "native_telemetry", "bundle_ids": [bundle_id],
                   "source_schema": decision["schema"],
                   "source_schema_version": decision["schema_version"],
                   "source_record_id": decision["record_id"],
                   "source_sha256": digest_bytes(canonical_bytes(decision)),
                   "telemetry_receipt_id": receipt["record_id"],
                   "migrations": []},
        "decision": decision,
        "terminal_target": _terminal_target(outcome, seat),
        "supervision": {
            "behavior": {"chosen_action_id": decision["decision"]["chosen_action_id"],
                         "behavior_identity": decision["behavior_identity"]},
            "evaluator": [],
            "human": {"accepted_action_ids": [], "annotations": []},
        },
        "replay_certificate": None,
        "exclusion": {"reason": str(reason)},
        "quality": {"integrity": "valid", "signals": []},
    }


def _merge_row(rows_by_id: dict, row: dict, *, path: Path, rejections: list[dict]) -> bool:
    previous = rows_by_id.get(row["corpus_decision_id"])
    if previous is None:
        rows_by_id[row["corpus_decision_id"]] = row
        return False
    previous_evidence = {**previous, "origin": {**previous["origin"], "bundle_ids": []}}
    row_evidence = {**row, "origin": {**row["origin"], "bundle_ids": []}}
    if canonical_bytes(previous_evidence) != canonical_bytes(row_evidence):
        rejections.append({"kind": "duplicate", "path": str(path),
                           "decision_id": row["corpus_decision_id"],
                           "reason": "conflicting Corpus Decision duplicate"})
        return False
    previous["origin"]["bundle_ids"] = sorted(set(
        previous["origin"]["bundle_ids"] + row["origin"]["bundle_ids"]))
    return True


def _bundle_paths(root: Path) -> list[Path]:
    root = Path(root)
    if (root / "manifest.json").exists():
        return [root]
    return sorted(path.parent for path in root.glob("*/manifest.json"))


def _manifest_identities(rows: list[dict]) -> dict:
    decisions = [row["decision"] for row in rows]
    ledger = [decision for decision in decisions
              if decision["decision"]["variant"] == "ledger"]
    return {
        "code": sorted({decision["provenance"]["code"] for decision in decisions}),
        "data": sorted({digest_bytes(canonical_bytes(decision["provenance"]["data"]))
                        for decision in decisions}),
        "schema": sorted({f"{decision['schema']}@{decision['schema_version']}"
                          for decision in decisions}),
        "evaluator": sorted({decision["behavior_identity"]["evaluator"]
                             for decision in ledger}),
        "configuration": sorted({decision["configuration"]["evaluation_model"]["identity"]
                                 for decision in ledger}),
        "provider": sorted({decision["behavior_identity"]["provider"]
                            for decision in ledger}),
        "behavior": sorted({digest_bytes(canonical_bytes(decision["behavior_identity"]))
                            for decision in decisions}),
    }


def build_snapshot(*, bundles_root: Path, output_root: Path,
                   replay_certifier=certify_replay) -> Path:
    if replay_certifier is None:
        raise ValueError("Corpus publication requires replay certification")
    rows_by_id = {}
    bundle_ids = []
    duplicate_count = 0
    rejections = []
    training_exclusions = []
    for path in _bundle_paths(Path(bundles_root)):
        try:
            manifest, decisions, receipt, outcome, replay = load_episode_bundle(path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            rejections.append({"kind": "bundle", "path": str(path),
                               "reason": str(error)})
            continue
        bundle_ids.append(manifest["bundle_id"])
        for decision in decisions:
            if decision["decision"]["variant"] != "ledger":
                exclusion = {
                    "decision_id": decision["record_id"],
                    "bundle_id": manifest["bundle_id"],
                    "telemetry_receipt_id": receipt["record_id"],
                    "reason": "pregame_not_ledger",
                    "receipt_certified": receipt["certified"],
                }
                training_exclusions.append(exclusion)
                row = excluded_corpus_decision(
                    decision, receipt, outcome, bundle_id=manifest["bundle_id"],
                    reason=exclusion["reason"])
                duplicate_count += int(_merge_row(
                    rows_by_id, row, path=path, rejections=rejections))
                continue
            try:
                certificate = replay_certifier(decision, replay)
                row = corpus_decision(
                    decision, receipt, outcome, bundle_id=manifest["bundle_id"],
                    replay_certificate=certificate)
            except (CorpusRejection, ValueError, TypeError) as error:
                rejections.append({"kind": "decision", "path": str(path),
                                   "decision_id": decision["record_id"],
                                   "reason": str(error)})
                continue
            duplicate_count += int(_merge_row(
                rows_by_id, row, path=path, rejections=rejections))
    if rejections:
        raise CorpusIntegrityError(rejections)
    if not rows_by_id:
        raise ValueError("no complete Episode Bundles found")
    rows = sorted(rows_by_id.values(), key=lambda row: (
        row["decision"]["episode"]["key"], row["decision"]["decision"]["seat"],
        row["decision"]["decision"]["index"], row["corpus_decision_id"]))
    identities = _manifest_identities(rows)
    identity = digest_bytes(canonical_bytes({"schema_version": CORPUS_VERSION,
                                             "bundles": sorted(set(bundle_ids)),
                                             "training_exclusions": training_exclusions,
                                             "rows": [digest_bytes(canonical_bytes(row))
                                                      for row in rows]}))
    output_root = Path(output_root)
    destination = output_root / "snapshots" / identity
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=destination.parent))
        try:
            shard_name = "decisions-00000.jsonl.gz"
            shard_hash = write_gzip_jsonl(temporary / shard_name, rows)
            atomic_json(temporary / "manifest.json", {
                "schema": SNAPSHOT_SCHEMA, "schema_version": CORPUS_VERSION,
                "snapshot_id": identity, "bundle_ids": sorted(set(bundle_ids)),
                "decision_count": len(rows), "duplicate_count": duplicate_count,
                "training_exclusions": training_exclusions,
                "identities": identities,
                "shards": [{"path": shard_name, "sha256": shard_hash,
                            "rows": len(rows)}],
            })
            temporary.replace(destination)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
    atomic_json(output_root / "latest.json", {"snapshot_id": identity})
    return destination


def load_snapshot(path: Path) -> tuple[dict, list[dict]]:
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != SNAPSHOT_SCHEMA \
            or manifest.get("schema_version") != CORPUS_VERSION:
        raise ValueError("unsupported Corpus Snapshot schema")
    rows = []
    from .io import digest_file
    for shard in manifest["shards"]:
        shard_path = path / shard["path"]
        if digest_file(shard_path) != shard["sha256"]:
            raise ValueError("Corpus Snapshot shard hash mismatch")
        rows.extend(read_gzip_jsonl(shard_path))
    if len(rows) != manifest["decision_count"]:
        raise ValueError("Corpus Snapshot row count mismatch")
    return manifest, rows
