"""Batch mode for the blunder inspector: tag Corrections across a directory of Replays.

``blunder_correction`` accepts a single Replay file (one Episode) or a directory of collected
Replays (e.g. ``data/replays/<build_stem>/``). The shell steps across them in episode-id order
without leaving the tool; each Replay carries its own own-seat + live trace (ADR-0019), while the
build identity comes from the shared directory stem.
"""
from __future__ import annotations

import re
from pathlib import Path

from meta_tracker.parse import load_replay

from .provenance import build_identity
from .telemetry_log import find_log_any, load_log

_REPLAY = re.compile(r"(?:episode-)?(\d+)(?:-replay)?\.json(?:\.gz)?$")


def _episode_id(path: Path) -> int | None:
    name = path.name
    if "-logs.json" in name:                       # per-seat agent telemetry log, not a Replay
        return None
    m = _REPLAY.fullmatch(name)
    return int(m.group(1)) if m else None


def discover_replays(path: Path | str) -> list[Path]:
    """A Replay file -> ``[it]``; a directory -> its Replay files ordered by episode id. Recognises
    both ``episode-<id>-replay.json[.gz]`` and bare ``<id>.json[.gz]``; other files are ignored."""
    path = Path(path)
    if path.is_file():
        return [path]
    found = [(eid, p) for p in path.iterdir() if (eid := _episode_id(p)) is not None]
    return [p for _, p in sorted(found, key=lambda t: t[0])]


def load_game(path: Path | str) -> dict:
    """One Replay as a self-contained tagging context: the replay, its live Decision Telemetry and
    own-seat (ADR-0019), and the build identity read off the directory stem."""
    path = Path(path)
    log_path, live_seat = find_log_any(path)
    bid = build_identity(path)
    return {
        "replay": load_replay(path),
        "live_records": load_log(log_path) if log_path else None,
        "live_seat": live_seat,
        "agent": bid["agent"],              # deck/build name from dir stem (auto-fills own tags)
        "agent_build": bid["agent_build"],
        "agent_version": bid["agent_version"],
        "built_at": bid["built_at"],
    }

