"""Shared replay and telemetry artifact helpers."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


def episode_id(run_stem: str, index: int) -> int:
    return int(hashlib.sha1(f"{run_stem}:{index}".encode("utf-8")).hexdigest()[:12], 16)


def tag_replay(replay: dict, *, episode_id: int, team_names: list[str]) -> dict:
    info = {**(replay.get("info") or {}), "EpisodeId": episode_id,
            "TeamNames": list(team_names)}
    return {**replay, "info": info}


def lethal_proof_seconds(record: dict | None) -> float | None:
    if not isinstance(record, dict):
        return None
    proof = ((record.get("diagnostics") or {}).get("terminal_proof") or {})
    value = proof.get("elapsed_ms")
    if proof.get("attempted") is not True or isinstance(value, bool) \
            or not isinstance(value, (int, float)):
        return None
    seconds = float(value) / 1000.0
    return seconds if math.isfinite(seconds) and seconds >= 0.0 else None


def save_legacy_telemetry(run_dir: Path, episode_id: int, captured: list[dict]) -> None:
    from common.telemetry import TAG, frame_record

    run_dir = Path(run_dir)
    by_seat = {0: [], 1: []}
    stream = []
    for record in captured:
        framed = record.get("schema") == "ledger.telemetry"
        lines = list(frame_record(record)) if framed else [
            f"{TAG} " + json.dumps(record, separators=(",", ":"))]
        if framed:
            stream.extend(lines)
        seat = ((record.get("decision") or {}).get("seat") if framed else record.get("seat"))
        if seat in by_seat:
            by_seat[seat].extend([[{"stderr": line}] for line in lines])
    if stream:
        (run_dir / f"episode-{episode_id}-telemetry.jsonl").write_text(
            "\n".join(stream) + "\n", encoding="utf-8")
    for seat, records in by_seat.items():
        if records:
            (run_dir / f"episode-{episode_id}-agent-{seat}-logs.json").write_text(
                json.dumps(records, ensure_ascii=False), encoding="utf-8")


__all__ = ("episode_id", "lethal_proof_seconds", "save_legacy_telemetry", "tag_replay")
