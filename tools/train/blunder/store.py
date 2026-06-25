"""Append-only JSONL store for Corrections -- the "correction log" (ADR-0009).

Default location: ``data/corrections/corrections.jsonl`` (committed -- this is gold,
hand-authored training data). One JSON object per line; appends never rewrite
existing lines, so the log is a stable, diff-friendly history.
"""
from __future__ import annotations

import json
from pathlib import Path

from .correction import Correction

DEFAULT_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "corrections" / "corrections.jsonl"
)


def append_correction(correction: Correction, path: Path | str = DEFAULT_PATH) -> Path:
    """Append one Correction as a JSONL line, creating the log dir if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(correction.to_dict(), ensure_ascii=False) + "\n")
    return path


def load_corrections(path: Path | str = DEFAULT_PATH) -> list[Correction]:
    """Load all Corrections from the log, in append order. Missing log -> []."""
    path = Path(path)
    if not path.exists():
        return []
    out: list[Correction] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(Correction.from_dict(json.loads(line)))
    return out
