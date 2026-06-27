"""Read the agent's live Decision Telemetry (ADR-0019) and join it to a Correction.

Each ladder match yields a per-seat agent log (``episode-<id>-agent-<seat>-logs.json``) whose
stderr carries one ``@T <json>`` line per decision (see ``common.telemetry``). This maps a
Correction's ``(seat, film frame)`` to the live record the SHIPPED agent emitted at that
decision — the ground truth for *how the agent actually decided*, diffable against an offline
re-derivation (the retest in ``tools/train/tuner/retest.py``).

The join is positional (the record stream carries no frame id): the k-th decision-frame for a
seat maps to the k-th ``@T`` record. It is validated by option count + chosen positions, a cheap
guard against any telemetry/film drift.
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

from common.telemetry import TAG

from .decisions import iter_decisions


def parse_records(log: list) -> list[dict]:
    """The ordered ``@T`` decision records from a loaded agent-log structure.

    Flattens both shapes (downloaded single-agent ``[[{...}], ...]`` and local env logs),
    skips the handshake and any non-``@T`` stderr.
    """
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
    """The sibling agent-log for ``seat`` next to a collected replay, or None.

    ``collect`` writes ``episode-<id>-replay.json`` + ``episode-<id>-agent-<seat>-logs.json`` in
    one build dir; the bare ``<id>.json`` layout is also accepted. The log name is derived from
    the episode id in the replay filename.
    """
    replay_path = Path(replay_path)
    match = re.search(r"episode-(\d+)-replay", replay_path.name) or re.match(r"(\d+)\.", replay_path.name)
    if not match:
        return None
    candidate = replay_path.parent / f"episode-{match.group(1)}-agent-{seat}-logs.json"
    return candidate if candidate.exists() else None


def find_log_any(replay_path: Path | str) -> tuple[Path | None, int | None]:
    """The collected agent-log sibling for any seat next to a replay, with its seat (or None,None).

    ``collect`` writes exactly our seat's log, so the filename's ``-agent-<seat>-`` encodes which
    seat the telemetry is for. Used by the inspector to auto-load the live trace.
    """
    replay_path = Path(replay_path)
    match = re.search(r"episode-(\d+)-replay", replay_path.name) or re.match(r"(\d+)\.", replay_path.name)
    if not match:
        return None, None
    for cand in sorted(replay_path.parent.glob(f"episode-{match.group(1)}-agent-*-logs.json")):
        seat = re.search(r"-agent-(\d+)-logs", cand.name)
        if seat:
            return cand, int(seat.group(1))
    return None, None


def record_for(replay: dict, records: list[dict], *, seat: int, frame: int) -> dict | None:
    """The live ``@T`` record for the Decision at (``seat``, film ``frame``), or None if it
    can't be matched/validated.

    Join: the k-th seat decision-frame maps to ``records[k]``; accepted only when the record's
    option count and ``chosen`` positions match the film Decision (integrity guard).
    """
    seat_decisions = [d for d in iter_decisions(replay) if d.seat == seat]
    frames = [d.frame for d in seat_decisions]
    if frame not in frames:
        return None
    k = frames.index(frame)
    if not 0 <= k < len(records):
        return None
    record, decision = records[k], seat_decisions[k]
    if len(record.get("opts", [])) != len(decision.options) or record.get("chosen") != decision.chosen:
        return None
    return record
