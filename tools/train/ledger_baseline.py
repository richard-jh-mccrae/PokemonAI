"""Freeze the manually corrected one-ply Ledger as an immutable Baseline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "data" / "ledger-baselines" / "one-ply.json"


def main(argv=None) -> int:
    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    from common.ledger.baseline import load_baseline
    from sim.correction_run import _git_source_identity
    from train.baseline import build_baseline
    from train.blunder.store import jsonl_files

    parser = argparse.ArgumentParser(description="Freeze a certified one-ply Ledger Baseline")
    parser.add_argument("--run", action="append", type=Path, required=True,
                        help="completed Correction Run directory; repeatable")
    parser.add_argument("--corrections", action="append", type=Path, default=[],
                        help="Correction JSONL or directory; repeatable")
    parser.add_argument("--certification", type=Path, required=True,
                        help="passed review JSON bound to run, bundle, source, and behavior IDs")
    parser.add_argument("--known-weakness", action="append", default=[])
    parser.add_argument("--created-at")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    correction_files = [path for source in args.corrections for path in jsonl_files(source)]
    if not correction_files:
        raise ValueError("no Correction JSONL files found")
    baseline = build_baseline(
        correction_runs=args.run, corrections=args.corrections,
        certification=args.certification, known_weaknesses=args.known_weakness,
        current_source_identity=_git_source_identity(
            REPO, allow_dirty=False,
            exclude_paths=(*args.run, *correction_files, args.certification, args.out)),
        created_at=args.created_at or datetime.now(timezone.utc).isoformat())
    if args.out.exists():
        existing = load_baseline(args.out)
        if existing != baseline:
            raise ValueError(f"immutable Ledger Baseline already exists: {args.out}")
        print(f"already frozen {existing['baseline_id']} -> {args.out}")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"froze {baseline['baseline_id']} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
