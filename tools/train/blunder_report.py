"""Rebuild the offline blunder trend report from the Correction log.

    python tools/train/blunder_report.py [out.html]

Reads data/corrections/corrections.jsonl and writes a self-contained HTML report
(default: reports/blunders.html). See docs/blunder-inspector.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO / "my_submissions"))

from train.blunder.report import build_report  # noqa: E402
from train.blunder.store import DEFAULT_PATH  # noqa: E402


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    out = Path(argv[0]) if argv else (REPO / "reports" / "blunders.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    print("wrote", build_report(DEFAULT_PATH, out))


if __name__ == "__main__":
    main()
