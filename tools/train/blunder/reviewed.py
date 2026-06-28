"""The **reviewed-corrections ledger** — blunders already assessed in blunder-busting, excluded
from fresh work so each round only surfaces *new* patterns.

The Tuner's auto-reconciliation (ADR-0018) drops a blunder once a new Hypothesis *satisfies* it.
But a blunder that was assessed and **consciously set aside** — refuted (a bad correction, e.g. it
forgoes a Knock Out), deferred (valid but needs new infrastructure), or covered (already handled by
an existing rule) — keeps re-surfacing as a proposal / unsatisfied constraint every run. This ledger
records those dispositions so `tune.py` and `/blunder-buster` skip them.

The file is a single hand-editable JSON map at ``data/corrections/reviewed.json``, keyed by
``"<episode_id>-<frame>"`` (the same id the reports print). One entry per dispositioned decision::

    {
      "_note": "...",
      "81904451-37": {"disposition": "refuted", "reason": "forgoes a KO", "round": "2026-06-27"}
    }

Keys starting with ``_`` are comments. Append entries with ``tools/train/review_correction.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

from .store import DEFAULT_ROOT

DEFAULT_REVIEWED = DEFAULT_ROOT / "reviewed.json"

# The disposition vocabulary. `refuted` is also dropped from the weight fit (a bad label must not
# pressure the weights); `deferred` / `covered` are merely held off the fresh-work surfaces.
DISPOSITIONS = ("refuted", "deferred", "covered")


def review_key(correction) -> str:
    """The ledger key for a Correction — ``"<episode_id>-<frame>"`` (matches the report ids)."""
    return f"{correction.episode_id}-{correction.decision.get('frame')}"


def load_reviewed(path: Path | str = DEFAULT_REVIEWED) -> dict:
    """Load the ledger as ``{key: entry}`` (comment keys starting with ``_`` dropped). Missing -> {}."""
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def partition_reviewed(corrections, reviewed: dict):
    """Split Corrections into ``(active, dispositioned)`` by the ledger. ``active`` are the ones to
    route this round; ``dispositioned`` is ``[(correction, entry)]`` already assessed (excluded)."""
    active, dispositioned = [], []
    for c in corrections:
        entry = reviewed.get(review_key(c))
        if entry:
            dispositioned.append((c, entry))
        else:
            active.append(c)
    return active, dispositioned
