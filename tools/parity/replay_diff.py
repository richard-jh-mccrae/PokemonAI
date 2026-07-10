"""Replay parity traces through cgpy and report divergences — the dev loop (ADR-0050).

    python tools/parity/replay_diff.py data/parity/*.trace.json.gz
    python tools/parity/replay_diff.py --all          # everything under data/parity + fixtures
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from cgpy.verify.replayer import replay  # noqa: E402
from cgpy.verify.trace import Trace  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Replay parity traces through cgpy.")
    ap.add_argument("traces", nargs="*", help="trace files")
    ap.add_argument("--all", action="store_true",
                    help="all traces under data/parity/ and tests/fixtures/parity/")
    args = ap.parse_args(argv)

    paths = [Path(t) for t in args.traces]
    if args.all or not paths:
        for root in (REPO / "data" / "parity", REPO / "tests" / "fixtures" / "parity"):
            if root.exists():
                paths += sorted(root.glob("*.trace.json.gz"))
    if not paths:
        print("no traces found")
        return 1

    clean = 0
    for p in paths:
        rep = replay(Trace.load(p))
        rep.trace_path = str(p)
        status = str(rep).replace("\n", "\n    ")
        print(f"{p.name}: {status}")
        clean += rep.clean
    print(f"\n{clean}/{len(paths)} traces clean")
    return 0 if clean == len(paths) else 1


if __name__ == "__main__":
    raise SystemExit(main())
