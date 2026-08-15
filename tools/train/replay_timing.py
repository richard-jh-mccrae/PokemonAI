"""Aggregate explicit match and decision timing from a replay directory."""
from __future__ import annotations

import gzip
import json
import math
from pathlib import Path
from statistics import fmean
import sys


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "src"))

from train.blunder.decisions import iter_decisions
from train.blunder.telemetry_log import decision_seconds, find_logs, load_log, record_for


def _finite(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0.0 else None


def _summary(values, *, total: int) -> dict:
    values = tuple(values)
    return {
        "count": len(values),
        "missing": max(0, int(total) - len(values)),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "avg": fmean(values) if values else None,
    }


def _load_json(path: Path) -> dict:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def _replays(root: Path):
    for path in sorted((*root.rglob("*.json"), *root.rglob("*.json.gz"))):
        if "-logs." in path.name or "-timing." in path.name:
            continue
        try:
            replay = _load_json(path)
        except (OSError, ValueError, gzip.BadGzipFile):
            continue
        if isinstance(replay, dict) and replay.get("steps"):
            yield path, replay


def _match_seconds(path: Path, replay: dict) -> float | None:
    direct = _finite((replay.get("info") or {}).get("MatchWallSeconds"))
    if direct is not None:
        return direct
    episode_id = (replay.get("info") or {}).get("EpisodeId")
    replay_stem = path.name[:-8] if path.name.endswith(".json.gz") else path.stem
    candidates = [path.with_name(f"{replay_stem}-timing.json")]
    if episode_id is not None:
        candidates.append(path.with_name(f"episode-{episode_id}-timing.json"))
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            value = _finite(json.loads(candidate.read_text(encoding="utf-8")).get(
                "match_wall_seconds"))
        except (OSError, ValueError):
            continue
        if value is not None:
            return value
    return None


def analyze_directory(directory: Path | str) -> dict:
    root = Path(directory)
    match_times = []
    decision_times = []
    limit_hits = []
    match_count = 0
    decision_count = 0
    for replay_path, replay in _replays(root):
        match_count += 1
        elapsed = _match_seconds(replay_path, replay)
        if elapsed is not None:
            match_times.append(elapsed)
        info = replay.get("info") or {}
        match_id = str(info.get("EpisodeId", replay_path.stem))
        records_by_seat = {
            seat: load_log(path) for seat, path in find_logs(replay_path).items()
        }
        for decision in iter_decisions(replay):
            decision_count += 1
            record = record_for(
                replay, records_by_seat.get(decision.seat, ()),
                seat=decision.seat, frame=decision.frame)
            sample = decision_seconds(record)
            if sample is None:
                sample = _finite(decision.decision_seconds)
            if sample is not None:
                decision_times.append(sample)
            if not isinstance(record, dict) or record.get("deadline_hit") is not True:
                continue
            limit_hits.append({
                "match_id": match_id,
                "frame_id": int(decision.frame),
                "seat": int(decision.seat),
                "decision_seconds": sample,
                "decision_limit_seconds": _finite(record.get("decision_limit_seconds")),
            })
    return {
        "match_count": match_count,
        "decision_count": decision_count,
        "match_time": _summary(match_times, total=match_count),
        "decision_time": _summary(decision_times, total=decision_count),
        "decision_limit_hits": len(limit_hits),
        "limit_hits": limit_hits,
    }


def _format_summary(summary: dict) -> str:
    values = (summary["min"], summary["max"], summary["avg"])
    return ", ".join("unavailable" if value is None else f"{value:.3f}s" for value in values)


def _format_seconds(value) -> str:
    return "unavailable" if value is None else f"{value:.3f}s"


def format_report(report: dict) -> str:
    hits = ", ".join(
        f"{row['match_id']}-{row['frame_id']} (seat {row['seat']}, "
        f"{_format_seconds(row['decision_seconds'])}/"
        f"{_format_seconds(row['decision_limit_seconds'])})"
        for row in report["limit_hits"]
    ) or "none"
    return "\n".join((
        f"matches: {report['match_count']} "
        f"(timed {report['match_time']['count']}, missing {report['match_time']['missing']})",
        f"decisions: {report['decision_count']} "
        f"(timed {report['decision_time']['count']}, missing {report['decision_time']['missing']})",
        f"match time: {_format_summary(report['match_time'])}",
        f"decision time: {_format_summary(report['decision_time'])}",
        f"decision time limits hit: {report['decision_limit_hits']}",
        f"limit hits: {hits}",
    ))


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    report = analyze_directory(args.directory)
    print(json.dumps(report, indent=2, sort_keys=True) if args.as_json else format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
