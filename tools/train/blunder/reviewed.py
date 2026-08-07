"""The **reviewed-corrections ledger** — blunders consciously set aside in blunder-busting, so
`tune.py` and `/blunder-buster` stop re-surfacing them every round.

A hand-editable JSON map at ``data/corrections/reviewed.json``, keyed by the Correction's Scope
subject (``review_key``); keys starting with ``_`` are comments. Append with
``tools/train/review_correction.py``.

A locator the operator holds may be any of four spellings (ADR-0090, Issue #250); only
`review_key` is canonical, and `gates.orphan_rulings` asserts no entry is unreachable.
"""
from __future__ import annotations

import json
from pathlib import Path

from .store import DEFAULT_ROOT

DEFAULT_REVIEWED = DEFAULT_ROOT / "reviewed.json"

# Kept in step with `gates.RECOGNISED_DISPOSITIONS` by a test: a word this writer accepts that the
# graders do not recognise silently drops those rulings (ADR-0088 decisions 3 and 6, Issue #239).
DISPOSITIONS = ("refuted", "transposition", "deferred", "deferred-multi-turn", "covered", "fixed")


def anchor_form(correction) -> str:
    """The **Anchor** frame spelling, for ANY scope. On decision scope it IS the `review_key`; off
    decision scope the two diverge (Issue #250)."""
    return f"{correction.episode_id}-{correction.decision.get('frame')}"


def review_key(correction) -> str:
    """The Scope subject (ADR-0049), so disposing of a Turn Correction never retires the Decision
    Corrections inside it. Turn keys need the seat: turn 0 is the shared setup phase."""
    scope = getattr(correction, "scope", "decision")
    if scope == "turn":
        return f"{correction.episode_id}-t{correction.subject}s{correction.seat}"
    return anchor_form(correction)          # decision scope: the key IS the Anchor form


def _locator_maps(keyed) -> dict:
    """``keyed`` is `gates.keyed_corrections()`'s ``[(Frame Key, Correction), ...]``; the Frame Key is
    READ from the pair, never re-derived — a second naming authority is ADR-0087 decision 2's defect."""
    maps = {"key": {}, "frame_key": {}, "id": {}, "anchor": {}}
    for frame_key, c in keyed:
        canonical = review_key(c)
        maps["key"][canonical] = canonical
        maps["frame_key"][frame_key] = canonical
        if getattr(c, "id", None):
            maps["id"][c.id] = canonical
        maps["anchor"].setdefault(anchor_form(c), canonical)
    return maps


#: MOST authoritative first: a string that is one record's `review_key` and another's anchor form
#: must resolve to the canonical key, or a ruling silently re-points at a record nobody named.
_LOCATOR_FORMS = ("key", "frame_key", "id", "anchor")


def resolve_locator(locator: str, keyed) -> str | None:
    """The one canonical `review_key` a Ruling Locator names, or ``None`` (ADR-0090 decision 2).
    The corpus is INJECTED: `blunder/` must never import `gates`."""
    if not locator:
        return None
    maps = _locator_maps(keyed)
    for form in _LOCATOR_FORMS:
        hit = maps[form].get(locator)
        if hit:
            return hit
    return None


def near_misses(locator: str, keyed) -> list[str]:
    """Two rules, UNIONED never chained — chained, rule 1 suppresses rule 2 and hides the operator's
    own episode. No edit distance, ever: a wrong-but-well-formed entry is invisible to the gates."""
    if not locator or resolve_locator(locator, keyed):
        return []
    episode, _, subject = locator.partition("-")
    if not subject:
        return []

    same_frame, same_episode = set(), set()
    for _frame_key, c in keyed:
        if subject == str(c.decision.get("frame")) and str(c.episode_id) != episode:
            same_frame.add(review_key(c))                          # rule 1
        if str(c.episode_id) == episode:
            same_episode.add(review_key(c))                        # rule 2
    return sorted(same_episode) + sorted(same_frame - same_episode)


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
