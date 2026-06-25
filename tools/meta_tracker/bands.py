"""Rating -> rank band.

Bands are contiguous percentile tiers over the top of the ladder (config.BANDS);
ratings below the last band are the dropped "lower rated" tier. An episode is
banded by its participants' current leaderboard rating (matchmaking pairs similar
ratings, so the two are close).
"""
from __future__ import annotations

from . import config

Row = dict  # {"rank": int, "teamId": int, "teamName": str, "score": float}


def rating_cutoffs(leaderboard: list[Row], bands=config.BANDS) -> list[tuple[str, float]]:
    """Min score for each (contiguous) band, derived from the score distribution.

    Returns [(band, min_score)] ordered top->down; a score below the last band's
    min is outside the kept range (the dropped lower tier).
    """
    scores = sorted((r["score"] for r in leaderboard), reverse=True)
    n = len(scores)
    out = []
    for name, _lo, hi in bands:
        idx = min(int(hi / 100 * n), n - 1) if n else 0
        out.append((name, scores[idx] if scores else 0.0))
    return out


def band_of_rating(score: float, cutoffs: list[tuple[str, float]]) -> str | None:
    """Map a participant rating to a band, or None if below the kept range."""
    for name, min_score in cutoffs:
        if score >= min_score:
            return name
    return None
