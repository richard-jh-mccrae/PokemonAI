"""Composition-aware Worth for blind draws (Issue #467).

The hidden pool includes the live deck and unresolved prizes. Uniform hidden prize placement leaves
the expected card mean unchanged, so the pool mean is the sound value of one blind deck draw. Deck
size still caps how many cards may be drawn.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from common.card_worth import Worth

if TYPE_CHECKING:
    from common.state_model import StateModel


def deck_card_worth(model: "StateModel") -> Worth:
    """Copy-weighted mean Worth of one unknown card in my hidden pool."""
    unseen = model.mine.unseen_counts
    total = sum(int(count) for count in unseen.values())
    if total <= 0:
        return Worth(0.0)
    weighted = sum(float(model.mine.role_worth(card_id)) * int(count)
                   for card_id, count in unseen.items())
    return Worth(weighted / total)


def deck_draw_worth(model: "StateModel", count: int) -> Worth:
    """Expected Worth of ``count`` blind draws, capped by cards left in deck."""
    draws = max(0, min(int(count), int(model.mine.deck_count)))
    return Worth(draws * float(deck_card_worth(model)))


__all__ = ("deck_card_worth", "deck_draw_worth")
