"""Read and partition the reviewed-corrections set-aside ledger."""
from __future__ import annotations

import json
from pathlib import Path

from .store import DEFAULT_ROOT

DEFAULT_REVIEWED = DEFAULT_ROOT / "reviewed.json"

DISPOSITIONS = ("refuted", "transposition", "deferred", "deferred-multi-turn",
                "off-policy", "covered", "fixed")


def review_key(correction) -> str:
    """The Scope subject (ADR-0049), so disposing of a Turn Correction never retires the Decision
    Corrections inside it. Turn keys need the seat: turn 0 is the shared setup phase."""
    scope = getattr(correction, "scope", "decision")
    if scope == "turn":
        return f"{correction.episode_id}-t{correction.subject}s{correction.seat}"
    return f"{correction.episode_id}-{correction.decision.get('frame')}"


def load_reviewed(path: Path | str = DEFAULT_REVIEWED) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def partition_reviewed(corrections, reviewed: dict):
    """``(active, dispositioned)``: `active` routes this round, `dispositioned` is
    ``[(correction, entry)]`` already assessed."""
    active, dispositioned = [], []
    for c in corrections:
        entry = reviewed.get(review_key(c))
        if entry:
            dispositioned.append((c, entry))
        else:
            active.append(c)
    return active, dispositioned
