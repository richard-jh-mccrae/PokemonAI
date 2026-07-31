"""Backfill a captured frame's engine seed + exact prize split (ADR-0050 Phase 2A).

A Correction stores the *film* observation (`film[frame+1].obs`, seed-stripped). Two fields make it
cascade-ready for the Lethal Solver's engine verify:

- ``search_begin_input`` — the forkable engine seed. It lives on the *step* observation
  (`steps[k][seat].observation`), not the film obs, but the two deep-equal on ``select``+``current``,
  so it's recovered by a **content-join**, not a `cg.api` re-derivation.
- ``own_prizes`` — the exact prize multiset, from replaying the seat's own observation history through
  ``OwnCardModel`` (the same match-scoped model ``main.py`` runs live). The exact seeding
  (``Pilot._exact_own_zones``) consumes it to seed ``search_begin`` with the true deck/prize split.

    python tools/train/backfill_seed.py [--store <log>] [--replays <dir> ...]

Repeatable; writes a ``.bak`` first. See docs/adr/0050-multi-step-lethal-verification-tool.md.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from common.deck_tracker import OwnCardModel  # noqa: E402
from meta_tracker.parse import extract_decks  # noqa: E402


def _key(o: dict) -> str:
    """The content-join key: an observation's select + board, index-free and seat-independent."""
    return json.dumps([o.get("select"), o.get("current")], sort_keys=True)


def join_seed(obs: dict, replay: dict) -> str | None:
    """The ``search_begin_input`` for ``obs``, recovered by joining it to the step observation with
    the same select+current. None when no seed-bearing frame matches (e.g. a mulligan/terminal frame
    the engine never emitted a seed for)."""
    want = _key(obs)
    for step in replay.get("steps", []):
        for a in step:
            o = a.get("observation")
            if isinstance(o, dict) and "current" in o and o.get("search_begin_input") and _key(o) == want:
                return o["search_begin_input"]
    return None


def own_prizes_for(replay: dict, target_obs: dict) -> dict | None:
    """The exact ``own_prizes`` at ``target_obs`` — replay the acting seat's observation stream through
    ``OwnCardModel`` (in chronological REPLAY-step order, up to and including the target frame) and
    export the anchored prize multiset. None until the tracker anchors (no positive claim without
    certainty), matching the runtime model.

    Ordered by replay-step index and cut off by content-key (``select``+``current``) rather than by
    ``obs['step']`` — the latter is only present on the first-seat's observations, so a second-seat
    fixture would otherwise reconstruct zero history."""
    cur = (target_obs or {}).get("current") or {}
    seat = cur.get("yourIndex", 0)
    decks = extract_decks(replay)
    if not (0 <= seat < len(decks)):
        return None
    want = _key(target_obs)
    model = OwnCardModel(decks[seat])
    for step in replay.get("steps", []):                # chronological: replay steps are in order
        for a in step:
            o = a.get("observation")
            if not (isinstance(o, dict) and isinstance(o.get("current"), dict)):
                continue
            if o["current"].get("yourIndex") != seat:
                continue
            model.observe(o)
            if _key(o) == want:                         # reached the target frame — stop, inclusive
                return model.prize_export()
    return model.prize_export()


def backfill_seed(obs: dict, replay: dict) -> dict:
    """Return a copy of ``obs`` with ``search_begin_input`` (content-joined) and ``own_prizes`` (exact
    split from the seat's history) attached. Either may be None when unrecoverable — the runtime and
    the engine verify already treat a missing seed / unanchored prizes as fail-safe."""
    out = copy.deepcopy(obs)
    out["search_begin_input"] = join_seed(obs, replay)
    out["own_prizes"] = own_prizes_for(replay, obs)
    return out


def _find_replay(episode_id, dirs) -> Path | None:
    patterns = (f"{episode_id}.json", f"{episode_id}.json.gz",
                f"episode-{episode_id}-replay.json", f"episode-{episode_id}-replay.json.gz")
    for d in dirs:
        for pat in patterns:
            for p in Path(d).rglob(pat):
                return p
    return None


def main(argv=None):
    from meta_tracker.parse import load_replay
    from train.blunder.store import DEFAULT_ROOT, jsonl_files, load_corrections

    ap = argparse.ArgumentParser(description="Backfill search_begin_input + own_prizes on Corrections")
    ap.add_argument("--store", default=str(DEFAULT_ROOT))
    ap.add_argument("--replays", nargs="*",
                    default=[str(REPO / "submissions"), str(REPO / "data" / "replays")])
    args = ap.parse_args(argv)

    cache: dict = {}
    total = filled = 0
    for f in jsonl_files(Path(args.store)):
        rows = [json.loads(line) for line in f.read_text("utf-8").splitlines() if line.strip()]
        changed = False
        for row in rows:
            obs = row.get("obs")
            if not obs or obs.get("search_begin_input"):
                continue
            total += 1
            ep = row.get("episode_id") or row.get("episode")
            if ep not in cache:
                rp = _find_replay(ep, args.replays)
                cache[ep] = load_replay(rp) if rp else None
            replay = cache[ep]
            if replay is None:
                continue
            row["obs"] = backfill_seed(obs, replay)
            filled += 1
            changed = True
        if changed:
            f.with_suffix(f.suffix + ".bak").write_text(f.read_text("utf-8"), encoding="utf-8")
            f.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    print(f"backfill_seed: {filled}/{total} obs seeded")


if __name__ == "__main__":
    main()
