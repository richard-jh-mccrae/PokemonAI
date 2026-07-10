"""The **reviewed-corrections ledger** — blunders already assessed in blunder-busting, excluded
from fresh work so each round only surfaces *new* patterns.

The Tuner's auto-reconciliation (ADR-0018) drops a blunder once a new Hypothesis *satisfies* it.
But a blunder that was assessed and **consciously set aside** — refuted (a bad correction, e.g. it
forgoes a Knock Out), deferred (valid but needs new infrastructure), or covered (already handled by
an existing rule) — keeps re-surfacing as a proposal / unsatisfied constraint every run. This ledger
records those dispositions so `tune.py` and `/blunder-buster` skip them.

The file is a single hand-editable JSON map at ``data/corrections/reviewed.json``, keyed by the
Correction's **Scope subject** (the same id the reports print, ``review_key``). One entry per
dispositioned subject::

    {
      "_note": "...",
      "81904451-37":     {"disposition": "refuted",  "reason": "forgoes a KO",   "round": "2026-06-27"},
      "81904451-t12s1":  {"disposition": "covered",  "reason": "plan_turn rung", "round": "2026-07-10"},
      "81904451-m1":     {"disposition": "deferred", "reason": "multi-turn",     "round": "2026-07-10"}
    }

Keys starting with ``_`` are comments. Append entries with ``tools/train/review_correction.py``.
"""
from __future__ import annotations

import json
from pathlib import Path

from .store import DEFAULT_ROOT

DEFAULT_REVIEWED = DEFAULT_ROOT / "reviewed.json"

# The disposition vocabulary. `refuted` also drops from the weight fit (bad label must not
# pressure weights); `deferred` / `covered` just held off the fresh-work surfaces.
# `deferred` = evidenced CAPABILITY-GAP only (/blunder-buster mandate): fix is a designed-but-unbuilt
# roadmap layer, recorded w/ real-Pilot re-measure + fixture + docs/todo definition-of-done.
# A merely-missing signal/tag/enum is never deferred -> it is built (step 4b).
DISPOSITIONS = ("refuted", "deferred", "covered")


def review_key(correction) -> str:
    """The ledger key for a Correction — its Scope's subject, matching the report ids (ADR-0049):

    - ``decision`` → ``"<episode_id>-<frame>"``   (unchanged; the pre-Scope key)
    - ``turn``     → ``"<episode_id>-t<turn>s<seat>"``  (seat needed: turn 0 is the shared setup phase)
    - ``match``    → ``"<episode_id>-m<seat>"``   (both seats can be `own` in self-play)

    So disposing of a Turn Correction never retires the Decision Corrections inside that Turn.
    """
    scope = getattr(correction, "scope", "decision")
    if scope == "turn":
        return f"{correction.episode_id}-t{correction.subject}s{correction.seat}"
    if scope == "match":
        return f"{correction.episode_id}-m{correction.seat}"
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
