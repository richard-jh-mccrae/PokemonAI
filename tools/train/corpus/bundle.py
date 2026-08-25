from __future__ import annotations

import gzip
import json
from pathlib import Path
import shutil
import tempfile

from common.telemetry import RecordAssembler, validate_record

from .io import atomic_json, canonical_bytes, digest_bytes, digest_file


BUNDLE_SCHEMA = "ledger.episode-bundle"
BUNDLE_VERSION = 3


def _replay_episode(replay: dict) -> str | None:
    value = (replay.get("info") or {}).get("EpisodeId")
    return None if value is None else str(value)


def audit_records(records: list[dict], replay: dict) -> tuple[list[dict], dict, dict]:
    validated = [dict(validate_record(record)) for record in records]
    decisions = [record for record in validated if record["record_type"] == "decision"]
    receipts = [record for record in validated
                if record["record_type"] == "telemetry_receipt"]
    outcomes = [record for record in validated if record["record_type"] == "outcome"]
    if len(receipts) != 1:
        raise ValueError("Episode Bundle requires exactly one Episode Telemetry Receipt")
    if len(outcomes) != 1:
        raise ValueError("Episode Bundle requires exactly one Outcome record")
    receipt = receipts[0]
    outcome = outcomes[0]
    episode = outcome["episode"]["key"]
    if receipt["episode"]["key"] != episode \
            or any(record["episode"]["key"] != episode for record in decisions):
        raise ValueError("Episode Bundle mixes episode keys")
    decision_ids = [record["record_id"] for record in decisions]
    if outcome["decision_ids"] != decision_ids:
        raise ValueError("Outcome decision set or order is incomplete")
    if not receipt["certified"] or receipt["decision_ids"] != decision_ids \
            or outcome["telemetry_receipt_id"] != receipt["record_id"]:
        raise ValueError("Episode Telemetry Receipt does not certify the Outcome decision set")
    external = outcome["episode"]["external_id"]
    replay_episode = _replay_episode(replay)
    if external is not None and replay_episode != str(external):
        raise ValueError("Replay and Outcome episode ids disagree")
    keys = [(record["decision"]["seat"], record["decision"]["index"])
            for record in decisions]
    if len(keys) != len(set(keys)):
        raise ValueError("Episode Bundle repeats a seat decision index")
    return decisions, receipt, outcome


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


def _read_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    return gzip.decompress(raw) if path.suffix == ".gz" else raw


def _write_gzip(path: Path, payload: bytes) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as target:
            target.write(payload)


def stage_episode_bundle(*, replay_path: Path, telemetry_path: Path,
                         output_root: Path) -> Path:
    replay_path, telemetry_path = Path(replay_path), Path(telemetry_path)
    replay = json.loads(_read_bytes(replay_path).decode("utf-8"))
    records = _strict_records(_read_bytes(telemetry_path).decode("utf-8").splitlines())
    decisions, receipt, outcome = audit_records(records, replay)
    replay_bytes = canonical_bytes(replay) + b"\n"
    record_bytes = b"".join(canonical_bytes(record) + b"\n"
                            for record in [*decisions, receipt, outcome])
    identity = digest_bytes(canonical_bytes({
        "replay_sha256": digest_bytes(replay_bytes),
        "records_sha256": digest_bytes(record_bytes),
    }))
    destination = Path(output_root) / identity
    if destination.exists():
        load_episode_bundle(destination)
        return destination
    Path(output_root).mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".episode-", dir=output_root))
    try:
        _write_gzip(temporary / "replay.json.gz", replay_bytes)
        _write_gzip(temporary / "telemetry.jsonl.gz", record_bytes)
        atomic_json(temporary / "manifest.json", {
            "schema": BUNDLE_SCHEMA, "schema_version": BUNDLE_VERSION,
            "bundle_id": identity, "episode_key": outcome["episode"]["key"],
            "decision_count": len(decisions), "receipt_id": receipt["record_id"],
            "outcome_id": outcome["record_id"],
            "content": {
                "replay_sha256": digest_bytes(replay_bytes),
                "telemetry_sha256": digest_bytes(record_bytes),
            },
            "files": {
                "replay.json.gz": digest_file(temporary / "replay.json.gz"),
                "telemetry.jsonl.gz": digest_file(temporary / "telemetry.jsonl.gz"),
            },
        })
        try:
            temporary.replace(destination)
        except OSError:
            if not destination.exists():
                raise
            shutil.rmtree(temporary, ignore_errors=True)
            load_episode_bundle(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return destination


def load_episode_bundle(path: Path) -> tuple[dict, list[dict], dict, dict, dict]:
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    version = manifest.get("schema_version")
    if manifest.get("schema") != BUNDLE_SCHEMA or version not in {2, BUNDLE_VERSION}:
        raise ValueError("unsupported Episode Bundle schema")
    for name, expected in manifest["files"].items():
        if digest_file(path / name) != expected:
            raise ValueError(f"Episode Bundle hash mismatch: {name}")
    replay_name = "replay.json" if version == 2 else "replay.json.gz"
    telemetry_name = "telemetry.jsonl" if version == 2 else "telemetry.jsonl.gz"
    replay = json.loads(_read_bytes(path / replay_name).decode("utf-8"))
    records = [json.loads(line) for line in _read_bytes(path / telemetry_name).decode(
        "utf-8").splitlines() if line.strip()]
    decisions, receipt, outcome = audit_records(records, replay)
    if manifest.get("receipt_id") != receipt["record_id"]:
        raise ValueError("Episode Bundle receipt identity mismatch")
    content = manifest.get("content") or {}
    if content:
        if digest_bytes(canonical_bytes(replay) + b"\n") != content.get("replay_sha256"):
            raise ValueError("Episode Bundle replay content hash mismatch")
        record_bytes = b"".join(canonical_bytes(record) + b"\n"
                                for record in [*decisions, receipt, outcome])
        if digest_bytes(record_bytes) != content.get("telemetry_sha256"):
            raise ValueError("Episode Bundle telemetry content hash mismatch")
    return manifest, decisions, receipt, outcome, replay
