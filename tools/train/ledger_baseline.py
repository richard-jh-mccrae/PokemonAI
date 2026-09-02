"""Freeze the manually corrected one-ply Ledger as an immutable Baseline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO / "data" / "ledger-baselines"


def main(argv=None) -> int:
    sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
    from common.ledger.baseline import load_baseline
    from sim.correction_run import _git_source_identity
    from train.baseline import build_baseline
    from train.blunder.store import jsonl_files

    parser = argparse.ArgumentParser(description="Freeze a certified one-ply Ledger Baseline")
    parser.add_argument("--run", action="append", type=Path, required=True,
                        help="completed Correction Run directory; repeatable")
    parser.add_argument("--corpus", action="append", type=Path, required=True,
                        help="historical Correction JSONL or directory; repeatable")
    parser.add_argument("--reviewed-corrections", type=Path, required=True)
    parser.add_argument("--tuning-correction", action="append", type=Path, default=[])
    parser.add_argument("--certification", type=Path, required=True,
                        help="passed review JSON bound to run, bundle, source, and behavior IDs")
    parser.add_argument("--known-weakness", action="append", default=[])
    parser.add_argument("--created-at")
    parser.add_argument("--out-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)

    correction_files = [path for source in args.corpus for path in jsonl_files(source)]
    if not correction_files:
        raise ValueError("no Correction JSONL files found")
    baseline = build_baseline(
        correction_runs=args.run, correction_corpus=args.corpus,
        reviewed_corrections=args.reviewed_corrections,
        tuning_corrections=args.tuning_correction,
        certification=args.certification, known_weaknesses=args.known_weakness,
        current_source_identity=_git_source_identity(
            REPO, allow_dirty=False,
            exclude_paths=(*args.run, *correction_files, args.reviewed_corrections,
                           args.certification, args.out_root)),
        created_at=args.created_at or datetime.now(timezone.utc).isoformat())
    output = args.out_root / baseline["baseline_id"] / "manifest.json"
    if output.exists():
        existing = load_baseline(output)
        if existing != baseline:
            raise ValueError(f"immutable Ledger Baseline already exists: {output}")
        print(f"already frozen {existing['baseline_id']} -> {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=False)
    output.write_text(json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"froze {baseline['baseline_id']} -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
