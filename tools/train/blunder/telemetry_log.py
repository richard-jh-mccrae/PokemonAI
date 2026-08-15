"""Read the agent's live Decision Telemetry (ADR-0019) and join it to a Correction.

The record stream carries no frame id, so the join is POSITIONAL — the k-th decision-frame for a
seat maps to the k-th ``@T`` record — validated by option count + chosen positions.
"""
from __future__ import annotations

import gzip
import json
import math
import re
from pathlib import Path

from common.telemetry import TAG

from .decisions import iter_decisions


def parse_records(log: list) -> list[dict]:
    """Flattens both shapes (downloaded single-agent ``[[{...}], ...]`` and local env logs)."""
    records: list[dict] = []
    for step in log or []:
        for entry in step or []:
            if not entry:
                continue
            for line in (entry.get("stderr") or "").splitlines():
                if line.startswith(TAG):
                    try:
                        records.append(json.loads(line[len(TAG):].strip()))
                    except json.JSONDecodeError:
                        pass
    return records


def load_log(path: Path | str) -> list[dict]:
    """Load an agent-log file (``.json`` or ``.json.gz``) and return its ordered ``@T`` records."""
    path = Path(path)
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return parse_records(json.loads(raw.decode("utf-8")))


def find_log(replay_path: Path | str, seat: int) -> Path | None:
    """``collect``'s layout, plus the bare ``<id>.json`` one."""
    replay_path = Path(replay_path)
    match = re.search(r"episode-(\d+)-replay", replay_path.name) or re.match(r"(\d+)\.", replay_path.name)
    if not match:
        return None
    candidate = replay_path.parent / f"episode-{match.group(1)}-agent-{seat}-logs.json"
    return candidate if candidate.exists() else None


def find_log_any(replay_path: Path | str) -> tuple[Path | None, int | None]:
    """``collect`` writes exactly our seat's log, so the filename's ``-agent-<seat>-`` says which
    seat the telemetry is for."""
    replay_path = Path(replay_path)
    match = re.search(r"episode-(\d+)-replay", replay_path.name) or re.match(r"(\d+)\.", replay_path.name)
    if not match:
        return None, None
    for cand in sorted(replay_path.parent.glob(f"episode-{match.group(1)}-agent-*-logs.json")):
        seat = re.search(r"-agent-(\d+)-logs", cand.name)
        if seat:
            return cand, int(seat.group(1))
    return None, None


def find_logs(replay_path: Path | str) -> dict[int, Path]:
    replay_path = Path(replay_path)
    match = (re.search(r"episode-(\d+)-replay", replay_path.name)
             or re.match(r"(\d+)\.", replay_path.name))
    if not match:
        return {}
    found = {}
    for candidate in sorted(replay_path.parent.glob(f"episode-{match.group(1)}-agent-*-logs.json")):
        seat = re.search(r"-agent-(\d+)-logs", candidate.name)
        if seat:
            found[int(seat.group(1))] = candidate
    return found


def decision_seconds(record: dict | None) -> float | None:
    if not isinstance(record, dict):
        return None
    value = record.get("decision_seconds")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0.0 else None


def record_for(replay: dict, records: list[dict], *, seat: int, frame: int) -> dict | None:
    """Positional join: the k-th seat decision-frame maps to ``records[k]``, accepted only when the
    record's option count and ``chosen`` positions match the film Decision."""
    return records_for(iter_decisions(replay), {seat: records}).get((seat, frame))


def records_for(decisions, records_by_seat: dict[int, list[dict]]) -> dict[tuple[int, int], dict]:
    positions: dict[int, int] = {}
    joined = {}
    for decision in decisions:
        seat = int(decision.seat)
        position = positions.get(seat, 0)
        positions[seat] = position + 1
        records = records_by_seat.get(seat, ())
        if not 0 <= position < len(records):
            continue
        record = records[position]
        if not _record_matches(record, decision):
            continue
        joined[(seat, int(decision.frame))] = record
    return joined


def _record_matches(record: dict, decision) -> bool:
    if record.get("chosen") != decision.chosen:
        return False
    if not record.get("bellman") and record.get("schema") not in {"bellman", "setup"} \
            and len(record.get("opts", [])) != len(decision.options):
        return False
    return True
