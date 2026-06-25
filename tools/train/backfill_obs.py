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
from train.blunder.store import DEFAULT_PATH, load_corrections  # noqa: E402


def _find_replay(episode_id, dirs) -> Path | None:
    for d in dirs:
        for p in Path(d).rglob(f"{episode_id}.json"):
            return p
    return None


def _obs_for(replay: dict, frame: int):
    film = _film(replay)
    return film[frame + 1].get("obs") if 0 <= frame + 1 < len(film) else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Backfill obs + build identity on Corrections from their replays")
    ap.add_argument("--store", default=str(DEFAULT_PATH))
    ap.add_argument("--replays", nargs="*", default=[str(REPO / "submissions"), str(REPO / "data" / "replays")])
    args = ap.parse_args(argv)

    log = Path(args.store)
    corrections = load_corrections(log)
    cache, out, filled, missing = {}, [], 0, set()
    for c in corrections:
        if c.obs is not None and c.agent_build is not None:   # already complete
            out.append(c)
            continue
        if c.episode_id not in cache:
            rp = _find_replay(c.episode_id, args.replays)
            cache[c.episode_id] = (rp, load_replay(rp) if rp else None)
        replay_path, replay = cache[c.episode_id]
        if replay is None:
            missing.add(c.episode_id)
            out.append(c)
            continue
        updates = {}
        if c.obs is None and (obs := _obs_for(replay, c.decision.get("frame"))) is not None:
            updates["obs"] = obs
        if c.agent_build is None and (bid := build_identity(replay_path))["agent_build"]:
            updates.update(agent_build=bid["agent_build"], built_at=bid["built_at"],
                           agent_version=c.agent_version or bid["agent_version"])
        out.append(replace(c, **updates) if updates else c)
        filled += bool(updates)

    if filled:
        shutil.copyfile(log, log.with_suffix(".jsonl.bak"))
        with log.open("w", encoding="utf-8") as fh:
            for c in out:
                fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    print(f"backfilled {filled}/{len(corrections)} corrections (obs + build identity)"
          + (f"; replay not found for episodes {sorted(missing)}" if missing else ""))


if __name__ == "__main__":
    main()
