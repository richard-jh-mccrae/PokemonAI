"""Agent History: the committed, append-only record of what each agent was (ADR-0019).

One immutable JSON row per Submission at `data/agent_history.jsonl` — the durable spine the
Performance Log and the Strategy Writeup join against (by `submission_id` / `artifact`).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def read_history(path: Path | str) -> list[dict]:
    """Every Submission row, in append order (missing log -> [])."""
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def next_submission_id(path: Path | str) -> int:
    """The next monotonic Submission Id (max recorded + 1, or 1 for an empty/absent log)."""
    return max((r.get("submission_id", 0) for r in read_history(path)), default=0) + 1


def append_history(path: Path | str, row: dict) -> None:
    """Append one Submission row; never rewrites prior lines (the record is immutable)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def manifest_digest(manifest: dict) -> str:
    """A stable digest of a Manifest, so two Submissions reveal at a glance whether the agent
    actually changed (vs. a mere rebuild)."""
    blob = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()[:16]


def summary(manifest: dict) -> dict:
    """The compact state summary carried in the history row for quick diffing/charting."""
    caps = manifest["capabilities"]
    return {
        "system": manifest["system"],
        "deck_size": manifest["deck"]["size"],
        "roles": len(manifest["strategy"]["roles"]),
        "prize_selectors": sum(len(values) for values in
                               manifest["strategy"]["prize_plan"].values()),
        "scouting": caps["scouting"],
    }
