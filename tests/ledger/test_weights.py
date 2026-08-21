"""The configured Feature Catalog: complete vectors, residual overlays, loud typos."""
from __future__ import annotations

import pytest

from common.ledger import DeckOverlay, ValuationConfiguration


def test_absolute_training_values_and_deck_residuals_are_distinct():
    general = ValuationConfiguration.general().with_values({"zone.in_hand": 0.5})
    configured = general.resolve(DeckOverlay({"zone.in_hand": 0.2}))

    assert general["zone.in_hand"] == 0.5
    assert configured["zone.in_hand"] == 0.7


def test_unknown_feature_raises():
    for typo in ("zone.in_pocket", "role.primary_atacker", "kind.itme", "tag.draw"):
        with pytest.raises(KeyError):
            ValuationConfiguration.general().with_values({typo: 1.0})


def test_identity_tracks_complete_resolved_vector():
    base = ValuationConfiguration.general()
    assert base.identity == ValuationConfiguration.general().identity
    assert base.identity != base.with_values({"prize.race": 2.0}).identity
