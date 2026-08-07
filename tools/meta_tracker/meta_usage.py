"""Rank cards by real usage across stored meta episodes — "what actually shows up".

Pure & lib-free: the caller passes the episode dicts (from ``store.load_episodes``). Used to
prioritise the function-tag verification toward the cards that decide games (see
``tools/verify_meta_cards.py``).
"""
from __future__ import annotations

from collections import Counter


def rank_card_usage(episodes, *, band_weights=None, exclude_ids=frozenset()) -> Counter:
    """``Counter{cardId: weighted_count}`` over both decklists of every episode. ``band_weights`` maps a
    band name → weight (default 1); ``exclude_ids`` drops cards you do not want ranked."""
    weights = band_weights or {}
    exclude = set(exclude_ids)
    counts: Counter = Counter()
    for ep in episodes:
        w = weights.get(ep.get("band"), 1)
        for side in ("deck0", "deck1"):
            for cid in ep.get(side) or []:
                if cid not in exclude:
                    counts[cid] += w
    return counts
