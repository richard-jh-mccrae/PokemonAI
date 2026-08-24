from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from .bundle import load_episode_bundle
from .io import atomic_json, canonical_bytes, digest_bytes, read_gzip_jsonl, write_gzip_jsonl


CORPUS_SCHEMA = "ledger.corpus-decision"
CORPUS_VERSION = 1
SNAPSHOT_SCHEMA = "ledger.corpus-snapshot"


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


def _certificate(decision: dict) -> dict:
    action_ids = [action["id"] for action in decision["actions"]]
    variant = decision["decision"]["variant"]
    return {
        "schema_version": 1, "mode": "not_replayed",
        "recorded_legal_actions_valid": decision["decision"]["chosen_action_id"] in action_ids,
        "recorded_evaluation_valid": variant != "ledger" or decision["root"] is not None,
        "recorded_successors_valid": variant != "ledger" or all(
            candidate["status"] == "unavailable" or candidate["successors"]
            or candidate["disposition"] in {"forced", "ends_turn"}
            for candidate in decision["candidates"]),
        "legal_actions_exact": None, "root_exact": None, "successors_exact": None,
        "full_choice_exact": None, "exclusion": "replay_not_requested",
    }


def corpus_decision(decision: dict, outcome: dict, *, bundle_id: str,
                    replay_certificate: dict | None = None) -> dict:
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
        "replay_certificate": replay_certificate or _certificate(decision),
        "quality": {"integrity": "valid", "signals": ["replay_not_run"]
                    if (replay_certificate or {}).get("mode", "not_replayed") == "not_replayed"
                    else []},
    }


def _bundle_paths(root: Path) -> list[Path]:
    root = Path(root)
    if (root / "manifest.json").exists():
        return [root]
    return sorted(path.parent for path in root.glob("*/manifest.json"))


def build_snapshot(*, bundles_root: Path, output_root: Path, replay_certifier=None) -> Path:
    rows_by_id = {}
    bundle_ids = []
    duplicate_count = 0
    for path in _bundle_paths(Path(bundles_root)):
        manifest, decisions, outcome, replay = load_episode_bundle(path)
        bundle_ids.append(manifest["bundle_id"])
        for decision in decisions:
            certificate = (None if replay_certifier is None
                           else replay_certifier(decision, replay))
            row = corpus_decision(decision, outcome, bundle_id=manifest["bundle_id"],
                                  replay_certificate=certificate)
            previous = rows_by_id.get(row["corpus_decision_id"])
            if previous is not None:
                previous_evidence = {**previous, "origin": {
                    **previous["origin"], "bundle_ids": []}}
                row_evidence = {**row, "origin": {**row["origin"], "bundle_ids": []}}
                if canonical_bytes(previous_evidence) != canonical_bytes(row_evidence):
                    raise ValueError("conflicting Corpus Decision duplicate")
                previous["origin"]["bundle_ids"] = sorted(set(
                    previous["origin"]["bundle_ids"] + row["origin"]["bundle_ids"]))
                duplicate_count += 1
            else:
                rows_by_id[row["corpus_decision_id"]] = row
    if not rows_by_id:
        raise ValueError("no complete Episode Bundles found")
    rows = sorted(rows_by_id.values(), key=lambda row: (
        row["decision"]["episode"]["key"], row["decision"]["decision"]["seat"],
        row["decision"]["decision"]["index"], row["corpus_decision_id"]))
    identity = digest_bytes(canonical_bytes({"schema_version": 1,
                                             "bundles": sorted(set(bundle_ids)),
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
                "schema": SNAPSHOT_SCHEMA, "schema_version": 1,
                "snapshot_id": identity, "bundle_ids": sorted(set(bundle_ids)),
                "decision_count": len(rows), "duplicate_count": duplicate_count,
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
    if manifest.get("schema") != SNAPSHOT_SCHEMA or manifest.get("schema_version") != 1:
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
