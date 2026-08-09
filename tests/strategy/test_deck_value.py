"""Blind-draw composition Worth (Issue #467)."""
from __future__ import annotations

from types import SimpleNamespace
from typing import get_type_hints

import pytest


class _Mine:
    def __init__(self, unseen_counts, deck_count, worths):
        self.unseen_counts = unseen_counts
        self.deck_count = deck_count
        self._worths = worths
        self.asked = []

    def role_worth(self, card_id):
        self.asked.append(card_id)
        return self._worths[card_id]


def _model(*, unseen_counts, deck_count, worths):
    return SimpleNamespace(mine=_Mine(unseen_counts, deck_count, worths))


def test_deck_card_worth_is_the_copy_weighted_hidden_pool_mean():
    from common import deck_value

    model = _model(unseen_counts={11: 2, 22: 1}, deck_count=2,
                   worths={11: 10.0, 22: 30.0})

    assert deck_value.deck_card_worth(model) == pytest.approx(50.0 / 3.0)
    assert model.mine.asked == [11, 22]


@pytest.mark.parametrize(("count", "expected"), [
    (-3, 0.0),
    (0, 0.0),
    (1, 50.0 / 3.0),
    (99, 100.0 / 3.0),
])
def test_deck_draw_worth_clamps_draws_to_the_live_deck(count, expected):
    from common import deck_value

    model = _model(unseen_counts={11: 2, 22: 1}, deck_count=2,
                   worths={11: 10.0, 22: 30.0})

    assert deck_value.deck_draw_worth(model, count) == pytest.approx(expected)


def test_empty_hidden_pool_and_empty_deck_have_zero_draw_worth():
    from common import deck_value

    empty_pool = _model(unseen_counts={}, deck_count=0, worths={})
    all_prized = _model(unseen_counts={11: 2}, deck_count=0, worths={11: 10.0})

    assert deck_value.deck_card_worth(empty_pool) == 0.0
    assert deck_value.deck_draw_worth(empty_pool, 3) == 0.0
    assert deck_value.deck_draw_worth(all_prized, 3) == 0.0


def test_deck_helpers_publish_worth_units():
    from common import deck_value
    from common.card_worth import Worth

    namespace = {"StateModel": object}
    assert get_type_hints(deck_value.deck_card_worth, localns=namespace)["return"] is Worth
    assert get_type_hints(deck_value.deck_draw_worth, localns=namespace)["return"] is Worth
