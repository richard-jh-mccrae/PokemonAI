"""Physically compact the Correction log: collapse exact-duplicate Corrections.

Reads are already deduplicated in memory (``store.load_corrections``); this rewrites the file so
the on-disk log is tidy too (smaller git diffs, honest counts). Keeps the LATEST of each exact
duplicate (same episode/seat/frame/chosen/correct/category) and reports any *conflicts* -- one
decision tagged with two different judgments -- for you to resolve by hand. Writes a ``.bak`` first.

    python tools/train/dedup_corrections.py [--store <tree-or-file>] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.blunder.store import (DEFAULT_ROOT, jsonl_files, dedup_corrections,  # noqa: E402
                                 find_conflicts, load_corrections)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Collapse exact-duplicate Corrections in the log tree")
    ap.add_argument("--store", default=str(DEFAULT_ROOT), help="a correction tree root or a single .jsonl")
    ap.add_argument("--dry-run", action="store_true", help="report only; don't rewrite")
    args = ap.parse_args(argv)

    union, removed = [], 0
    for f in jsonl_files(Path(args.store)):         # dedup within each build's file
        raw = load_corrections(f, dedup=False)
        union += raw
        kept = dedup_corrections(raw)
        if len(kept) != len(raw):
            removed += len(raw) - len(kept)
            if not args.dry_run:
                shutil.copyfile(f, f.with_suffix(".jsonl.bak"))
                with f.open("w", encoding="utf-8") as fh:
                    for c in kept:
                        fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")

    conflicts = find_conflicts(union)
    for (ep, seat, frame), members in conflicts:
        cats = ", ".join(sorted(f"{m.category}->{m.correct}" for m in members))
        print(f"  CONFLICT ep {ep} seat {seat} frame {frame}: {cats}  (resolve by hand)")

    verb = "would remove" if args.dry_run else "removed"
    print(f"{verb} {removed} exact duplicate(s); {len(union) - removed} kept; {len(conflicts)} conflict(s)")


if __name__ == "__main__":
    main()
