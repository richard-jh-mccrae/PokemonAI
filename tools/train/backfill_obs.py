"""Backfill the `obs` field on Corrections saved before it existed (ADR-0017).

For each Correction lacking `obs`, find its replay by episode id, read the aligned agent
observation (the film records it one frame after the prompt -> `film[frame+1].obs`), and
rewrite the log. Repeatable; writes a `.bak` first.

    python tools/train/backfill_obs.py [--store <log>] [--replays <dir> ...]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from meta_tracker.parse import load_replay  # noqa: E402
from train.blunder.decisions import _film  # noqa: E402
from train.blunder.provenance import build_identity  # noqa: E402
from train.blunder.store import DEFAULT_ROOT, _jsonl_files, load_corrections  # noqa: E402
from train.blunder.telemetry_log import find_log_any, load_log, record_for  # noqa: E402


def _find_replay(episode_id, dirs) -> Path | None:
    # accept both the inspector layout (<id>.json) and collect's naming (episode-<id>-replay.json[.gz])
    patterns = (f"{episode_id}.json", f"{episode_id}.json.gz",
                f"episode-{episode_id}-replay.json", f"episode-{episode_id}-replay.json.gz")
    for d in dirs:
        for pat in patterns:
            for p in Path(d).rglob(pat):
                return p
    return None


def _obs_for(replay: dict, frame: int):
    film = _film(replay)
    return film[frame + 1].get("obs") if 0 <= frame + 1 < len(film) else None


def _fill(c, dirs, cache, logcache, missing):
    """Return ``c`` with any derivable missing field filled (obs / build identity / live trace)."""
    if c.obs is not None and c.agent_build is not None and c.live_trace is not None:
        return c
    if c.episode_id not in cache:
        rp = _find_replay(c.episode_id, dirs)
        cache[c.episode_id] = (rp, load_replay(rp) if rp else None)
    replay_path, replay = cache[c.episode_id]
    if replay is None:
        missing.add(c.episode_id)
        return c
    updates = {}
    if c.obs is None and (obs := _obs_for(replay, c.decision.get("frame"))) is not None:
        updates["obs"] = obs
    if c.agent_build is None and (bid := build_identity(replay_path))["agent_build"]:
        updates.update(agent_build=bid["agent_build"], built_at=bid["built_at"],
                       agent_version=c.agent_version or bid["agent_version"])
    if c.live_trace is None:                                  # live Decision Telemetry (ADR-0019)
        if c.episode_id not in logcache:
            lp, _seat = find_log_any(replay_path)
            logcache[c.episode_id] = load_log(lp) if lp else None
        records = logcache[c.episode_id]
        if records and (lt := record_for(replay, records, seat=c.seat,
                                         frame=c.decision.get("frame"))) is not None:
            updates["live_trace"] = lt
    return replace(c, **updates) if updates else c


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backfill obs + build identity + live trace on Corrections")
    ap.add_argument("--store", default=str(DEFAULT_ROOT), help="a correction tree root or a single .jsonl")
    ap.add_argument("--replays", nargs="*", default=[str(REPO / "submissions"), str(REPO / "data" / "replays")])
    args = ap.parse_args(argv)

    cache, logcache, missing, total, filled = {}, {}, set(), 0, 0
    for f in _jsonl_files(Path(args.store)):                  # one log file per build (or one file)
        corrections = load_corrections(f, dedup=False)
        total += len(corrections)
        out = [_fill(c, args.replays, cache, logcache, missing) for c in corrections]
        changed = sum(1 for a, b in zip(corrections, out) if a is not b)
        if changed:
            shutil.copyfile(f, f.with_suffix(".jsonl.bak"))
            with f.open("w", encoding="utf-8") as fh:
                for c in out:
                    fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
            filled += changed
    print(f"backfilled {filled}/{total} corrections (obs + build identity + live trace)"
          + (f"; replay not found for episodes {sorted(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
