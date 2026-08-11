"""ORACLE: Energy denial — ADR-0062. What discarding one Energy actually takes away.

The MAGNITUDE half of this module is DELETED (Issue #228): `common/deny_relevance.py` owns the scoring
end to end. What survives is the **COIN**, derived from the card's declared effect rather than identity.
"""
from __future__ import annotations


def coin_odds(tags=()) -> float:
    """P(the declared denial lands): 0.5 for a ``coin`` Function Tag, otherwise 1.0."""
    return 0.5 if "coin" in (tags or ()) else 1.0
