"""Batch mode for the blunder inspector: tag Corrections across a directory of Replays.

``blunder_correction`` accepts a single Replay file (one Episode) or a directory of collected
Replays (e.g. ``data/replays/<build_stem>/``). The shell steps across them in episode-id order
without leaving the tool; each Replay carries its own own-seat + live trace (ADR-0019), while the
build identity comes from the shared directory stem.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from meta_tracker.parse import load_replay
from train.corpus import load_episode_bundle

from .provenance import build_identity
from .telemetry_log import find_log_any, find_logs, load_log

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
    manifest_path = path / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema") == "ledger.episode-bundle":
            _reject_heldout_bundle(path, manifest["bundle_id"])
            return [path]
        if manifest.get("schema") == "ledger.correction-run":
            games = []
            for slot in manifest.get("slots") or ():
                if slot.get("status", "complete") != "complete" \
                        or slot.get("partition") != "tuning" or not slot.get("bundle_id"):
                    continue
                relative = slot.get("bundle_path")
                bundle = (path / relative if relative else
                          path / "bundles" / "tuning" / slot["bundle_id"])
                if (bundle / "manifest.json").is_file():
                    games.append((int(slot.get("index", len(games))), bundle))
            return [bundle for _index, bundle in sorted(games)]
    found = [(eid, p) for p in path.iterdir() if (eid := _episode_id(p)) is not None]
    return [p for _, p in sorted(found, key=lambda t: t[0])]


def _correction_run(path: Path, bundle_id: str) -> tuple[dict | None, dict | None]:
    partition = path.parent.name
    for parent in path.parents:
        manifest_path = parent / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema") != "ledger.correction-run":
            continue
        slot = next((item for item in manifest.get("slots") or ()
                     if item.get("bundle_id") == bundle_id
                     and item.get("partition") == partition), None)
        return manifest, slot
    return None, None


def _reject_heldout_bundle(path: Path, bundle_id: str) -> None:
    _run, slot = _correction_run(path, bundle_id)
    if slot is not None and slot.get("partition") == "heldout":
        raise ValueError("held-out Correction Run evidence is hidden from correction tools")


def load_game(path: Path | str) -> dict:
    """One Replay as a self-contained tagging context: the replay, its live Decision Telemetry and
    own-seat (ADR-0019), and the build identity read off the directory stem."""
    path = Path(path)
    if path.is_dir() and (path / "manifest.json").is_file():
        manifest, decisions, _receipt, _outcome, replay = load_episode_bundle(path)
        _reject_heldout_bundle(path, manifest["bundle_id"])
        records_by_seat = {}
        for record in decisions:
            seat = int(record["decision"]["seat"])
            records_by_seat.setdefault(seat, []).append(record)
        run, slot = _correction_run(path, manifest["bundle_id"])
        focal_seat = None if slot is None else int(slot["focal_seat"])
        source = (run or {}).get("source_identity") or {}
        return {
            "replay": replay,
            "live_records": records_by_seat.get(focal_seat),
            "live_seat": focal_seat,
            "live_records_by_seat": records_by_seat,
            "agent": (run or {}).get("focal"),
            "agent_build": (run or {}).get("run_id"),
            "agent_version": source.get("commit"),
            "built_at": (run or {}).get("created_at"),
        }
    log_path, live_seat = find_log_any(path)
    live_records_by_seat = {seat: load_log(log) for seat, log in find_logs(path).items()}
    bid = build_identity(path)
    return {
        "replay": load_replay(path),
        "live_records": load_log(log_path) if log_path else None,
        "live_seat": live_seat,
        "live_records_by_seat": live_records_by_seat,
        "agent": bid["agent"],              # deck/build name from dir stem (auto-fills own tags)
        "agent_build": bid["agent_build"],
        "agent_version": bid["agent_version"],
        "built_at": bid["built_at"],
    }
