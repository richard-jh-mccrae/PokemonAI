"""Scouting priced into the Ledger: the opponent's worth reads through role claims.

Card-generic claims (`layer.roles`) price at full strength — card knowledge needs no
recognition. Brief/Read claims (`layer.brief_roles`) and the Brief's weight overrides blend
in by the Read's gamma, so a shaky recognition fades to the general read (fail-open)."""
from __future__ import annotations

import pytest

from common.cards import card_store
from common.ledger import LedgerContext, LedgerWeights, OpponentLayer
from common.ledger.worth import base_worth

#: A card id no store record covers — the shape of every scouted-but-unauthored opponent.
UNKNOWN_ID = 424242


def layer(*, roles=None, brief_roles=None, weights=None, gamma=0.0):
    return OpponentLayer(roles=roles or {}, brief_roles=brief_roles or {},
                         weights=weights or LedgerWeights(), gamma=gamma)


def test_generic_role_claims_price_a_store_unknown_opponent_card():
    ctx = LedgerContext.build().with_opponent(
        layer(roles={UNKNOWN_ID: ("primary_attacker",)}))
    worth, gap = base_worth(UNKNOWN_ID, None, ctx, own=False)
    assert worth == ctx.weights.role_worth["primary_attacker"]
    assert gap                                   # store coverage stays honestly reported
    # The same id on OUR side never reads the opponent layer.
    assert base_worth(UNKNOWN_ID, None, ctx, own=True)[0] == ctx.weights.unknown_card_worth


def test_brief_claims_blend_by_gamma():
    floor = LedgerWeights().unknown_card_worth
    tier = LedgerWeights().role_worth["primary_attacker"]
    for gamma, expected in ((0.0, floor), (0.5, floor + 0.5 * (tier - floor)), (1.0, tier)):
        ctx = LedgerContext.build().with_opponent(
            layer(brief_roles={UNKNOWN_ID: ("primary_attacker",)}, gamma=gamma))
        assert base_worth(UNKNOWN_ID, None, ctx, own=False)[0] == pytest.approx(expected)


def test_brief_ledger_overrides_scope_to_their_side_only():
    bent = LedgerWeights().resolve({"role.primary_attacker": 0.9})
    ctx = LedgerContext.build().with_opponent(
        layer(brief_roles={UNKNOWN_ID: ("primary_attacker",)}, weights=bent, gamma=1.0))
    assert base_worth(UNKNOWN_ID, None, ctx, own=False)[0] == pytest.approx(0.9)
    # Our own general tier is untouched by the Brief's bend.
    assert ctx.weights.role_worth["primary_attacker"] == pytest.approx(0.5)


def test_without_a_layer_the_opponent_reads_exactly_as_before():
    ctx = LedgerContext.build()
    assert base_worth(UNKNOWN_ID, None, ctx, own=False) == \
        base_worth(UNKNOWN_ID, None, ctx, own=True)


def test_special_energy_prices_through_its_own_kind_lever():
    ignition = card_store()[17]
    basic = card_store()[3]
    ctx = LedgerContext.build(overrides={"kind.special_energy": 0.42})
    assert base_worth(17, ignition, ctx)[0] == pytest.approx(0.42)
    assert base_worth(3, basic, ctx)[0] == pytest.approx(ctx.weights.kind_worth["energy"])
