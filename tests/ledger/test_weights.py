"""The weight vector: overrides bend named entries, typos refuse to train nothing."""
from __future__ import annotations

import pytest

from common.ledger import LedgerWeights


def test_scalar_and_tier_overrides_resolve():
    weights = LedgerWeights().resolve({
        "zone_in_hand": 0.5, "prize_race": 1.2,
        "role.primary_attacker": 0.8, "tag.draw": 0.3, "kind.item": 0.2, "card.121": 0.9})
    assert weights.zone_in_hand == 0.5
    assert weights.prize_race == 1.2
    assert weights.role_worth["primary_attacker"] == 0.8
    assert weights.tag_worth["draw"] == 0.3
    assert weights.kind_worth["item"] == 0.2
    assert weights.card_worth_map[121] == 0.9


def test_unknown_override_key_raises():
    with pytest.raises(KeyError):
        LedgerWeights().resolve({"zone_in_pocket": 1.0})


def test_identity_tracks_the_resolved_vector():
    base = LedgerWeights()
    assert base.identity == LedgerWeights().identity
    assert base.identity != base.resolve({"prize_race": 2.0}).identity
    assert base.resolve(None) is base
