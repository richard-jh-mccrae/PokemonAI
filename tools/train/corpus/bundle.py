from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile

from common.telemetry import RecordAssembler, validate_record

from .io import atomic_json, canonical_bytes, digest_bytes, digest_file


BUNDLE_SCHEMA = "ledger.episode-bundle"
BUNDLE_VERSION = 1


def _replay_episode(replay: dict) -> str | None:
    value = (replay.get("info") or {}).get("EpisodeId")
    return None if value is None else str(value)


def audit_records(records: list[dict], replay: dict) -> tuple[list[dict], dict]:
    validated = [dict(validate_record(record)) for record in records]
    decisions = [record for record in validated if record["record_type"] == "decision"]
    outcomes = [record for record in validated if record["record_type"] == "outcome"]
    if len(outcomes) != 1:
        raise ValueError("Episode Bundle requires exactly one Outcome record")
    outcome = outcomes[0]
    episode = outcome["episode"]["key"]
    if any(record["episode"]["key"] != episode for record in decisions):
        raise ValueError("Episode Bundle mixes episode keys")
    decision_ids = [record["record_id"] for record in decisions]
    if outcome["decision_ids"] != decision_ids:
        raise ValueError("Outcome decision set or order is incomplete")
    external = outcome["episode"]["external_id"]
    replay_episode = _replay_episode(replay)
    if external is not None and replay_episode != str(external):
        raise ValueError("Replay and Outcome episode ids disagree")
    keys = [(record["decision"]["seat"], record["decision"]["index"])
            for record in decisions]
    if len(keys) != len(set(keys)):
        raise ValueError("Episode Bundle repeats a seat decision index")
    return decisions, outcome


def _strict_records(lines: list[str]) -> list[dict]:
    assembler = RecordAssembler()
    records = []
    framed_ids, completed_ids = set(), set()
    for line in lines:
        if not line.strip():
            continue
        if not line.startswith("@T "):
            raise ValueError("Episode Bundle telemetry contains an unframed line")
        try:
            payload = json.loads(line[3:])
        except json.JSONDecodeError as error:
            raise ValueError("Episode Bundle telemetry contains invalid JSON") from error
        if payload.get("schema") == "ledger.telemetry.frame":
            framed_ids.add(str(payload.get("record_id")))
            record = assembler.ingest(line)
            if record is not None:
                records.append(record)
                completed_ids.add(record["record_id"])
        else:
            records.append(payload)
    if framed_ids != completed_ids:
        raise ValueError("Episode Bundle telemetry contains a partial record")
    return records


def stage_episode_bundle(*, replay_path: Path, telemetry_path: Path,
                         output_root: Path) -> Path:
    replay_path, telemetry_path = Path(replay_path), Path(telemetry_path)
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    records = _strict_records(telemetry_path.read_text(encoding="utf-8").splitlines())
    decisions, outcome = audit_records(records, replay)
    record_bytes = b"".join(canonical_bytes(record) + b"\n"
                            for record in [*decisions, outcome])
    identity = digest_bytes(canonical_bytes({
        "replay_sha256": digest_file(replay_path),
        "records_sha256": digest_bytes(record_bytes),
    }))
    destination = Path(output_root) / identity
    if destination.exists():
        return destination
    Path(output_root).mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".episode-", dir=output_root))
    try:
        shutil.copyfile(replay_path, temporary / "replay.json")
        (temporary / "telemetry.jsonl").write_bytes(record_bytes)
        atomic_json(temporary / "manifest.json", {
            "schema": BUNDLE_SCHEMA, "schema_version": BUNDLE_VERSION,
            "bundle_id": identity, "episode_key": outcome["episode"]["key"],
            "decision_count": len(decisions), "outcome_id": outcome["record_id"],
            "files": {
                "replay.json": digest_file(temporary / "replay.json"),
                "telemetry.jsonl": digest_file(temporary / "telemetry.jsonl"),
            },
        })
        temporary.replace(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def load_episode_bundle(path: Path) -> tuple[dict, list[dict], dict, dict]:
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != BUNDLE_SCHEMA or manifest.get("schema_version") != BUNDLE_VERSION:
        raise ValueError("unsupported Episode Bundle schema")
    for name, expected in manifest["files"].items():
        if digest_file(path / name) != expected:
            raise ValueError(f"Episode Bundle hash mismatch: {name}")
    replay = json.loads((path / "replay.json").read_text(encoding="utf-8"))
    records = [json.loads(line) for line in
               (path / "telemetry.jsonl").read_text(encoding="utf-8").splitlines()
               if line.strip()]
    decisions, outcome = audit_records(records, replay)
    return manifest, decisions, outcome, replay
