"""ADR-0133 — ONE spelling of a held card's LATENT worth.

`NeedsMixin._latent_row_worth` is the single formula behind the Pilot's `general` slot and the leaf's
`hand_worth`. The leaf used to carry an UNDISCOUNTED copy of it, so a card that could not be played
priced at full `_GENERAL_WORTH_W` tier — which is what paid for the composer's ruled-against searches
(Issue #444).
"""
import sys
from pathlib import Path

import pytest

from common.deciders.needs import _GENERAL_ILLIQUID_FLOOR, _GENERAL_WORTH_W, NeedsMixin

REPO = Path(__file__).resolve().parents[2]


class _Latent(NeedsMixin):
    """The mixin with only what the latent formula reads — no board, no engine, no obs."""

    def __init__(self, worth: dict, liquidity: float = 1.0):
        self._worth, self._liquidity = worth, liquidity

    def _role_value(self, cid):
        return self._worth.get(cid, 0.0)

    def _general_liquidity(self, cid, board, me):
        return self._liquidity


def _rows(*specs):
    return [{"i": i, "cid": cid, "deploy": deploy} for i, (cid, deploy) in enumerate(specs)]


@pytest.mark.req("REQ-NEEDS-0011")
def test_an_undeployable_card_carries_no_latent_worth():
    """`deploy` is P(this card ever reaches the board). At 0 its latent worth is 0, not 45% of tier —
    the `82522698|62` witness, where a Buddy-Buddy Poffin and a Cinderace priced +9.9 Worth unplayed."""
    mixin = _Latent({1086: 10.0, 666: 12.0})
    rows = _rows((1086, 0.0), (666, 0.0))
    assert mixin._latent_holdings(rows, None, {}) == 0.0
    assert list(mixin._general_worth_classes(rows, None, {})) == []
    assert mixin._latent_holdings(_rows((1086, 1.0)), None, {}) == pytest.approx(10.0 * _GENERAL_WORTH_W)


@pytest.mark.req("REQ-NEEDS-0011")
def test_the_holdings_total_is_per_ROW_and_the_slot_view_is_per_CLASS():
    """A spare copy is a second CARD to the supply total and the same SLOT to the assignment — the two
    aggregations of one formula, and reading either off the other is the defect this seam exists for."""
    mixin = _Latent({3: 8.0})
    rows = _rows((3, 1.0), (3, 1.0), (3, 1.0))
    assert mixin._latent_holdings(rows, None, {}) == pytest.approx(3 * 8.0 * _GENERAL_WORTH_W)
    (cid, live, base, latent), = mixin._general_worth_classes(rows, None, {})
    assert (cid, live, base) == (3, [0, 1, 2], 8.0)
    assert latent == pytest.approx(8.0 * _GENERAL_WORTH_W)


@pytest.mark.req("REQ-NEEDS-0011")
def test_liquidity_and_deploy_both_multiply_into_the_latent_worth():
    """The formula is `worth x deploy x _GENERAL_WORTH_W x liquidity`, and `base` is the pre-discount
    half the INSURANCE branch takes at full tier (ADR-0101) — both are returned, neither re-derived."""
    mixin = _Latent({666: 12.0}, liquidity=_GENERAL_ILLIQUID_FLOOR)
    base, latent = mixin._latent_row_worth(_rows((666, 0.5)), 0, None, {})
    assert base == pytest.approx(12.0 * 0.5)
    assert latent == pytest.approx(12.0 * 0.5 * _GENERAL_WORTH_W * _GENERAL_ILLIQUID_FLOOR)


@pytest.mark.req("REQ-NEEDS-0011")
def test_a_pitch_dead_row_carries_no_latent_worth():
    """A row the PITCH term flags as fodder NOW has no future worth — else general worth resurrects a
    spent burst. The rule lives in the shared formula, so both aggregations inherit it."""
    mixin = _Latent({17: 30.0})
    rows = _rows((17, 1.0))
    rows[0]["pitch"] = 1
    assert mixin._latent_row_worth(rows, 0, None, {}) == (0.0, 0.0)
    assert mixin._latent_holdings(rows, None, {}) == 0.0


@pytest.mark.req("REQ-NEEDS-0011")
def test_skip_cids_is_the_callers_own_exclusion_and_drops_the_whole_class():
    """The Pilot skips engine-saturated classes, the leaf skips classes that already cover a slot. One
    covering copy silences the class, so coverage and latent worth can never both price the same card."""
    mixin = _Latent({3: 8.0, 666: 12.0})
    rows = _rows((3, 1.0), (666, 1.0), (3, 1.0))
    assert mixin._latent_holdings(rows, None, {}, skip_cids={3}) == pytest.approx(12.0 * _GENERAL_WORTH_W)
    kept = [cid for cid, _l, _b, _v in mixin._general_worth_classes(rows, None, {}, skip_cids={3})]
    assert kept == [666]


def _shipped_pilot(agent):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(agent)[0]


@pytest.mark.req("REQ-NEEDS-0011")
def test_82752045_18_the_discount_lands_and_the_ruling_still_does_not(capsys):
    """Issue #444's frame. The discount reaches the leaf — and does NOT reach the decision: the
    composer still commits the ruled-against Hilda, which is the measurement ADR-0133 reverts on."""
    from corpus_helpers import corpus_record
    rec = corpus_record("82752045", 18)
    pilot = _shipped_pilot(rec.agent)
    obs = rec.obs
    my_index = int((obs.get("current") or {}).get("yourIndex") or 0)
    board = pilot._board_hypothetical(obs)
    rows = pilot._needs_hand_rows(obs, board)
    _slots, elig = pilot._resolve_needs(obs, board, rows, include_general=False)
    undiscounted = sum(_GENERAL_WORTH_W * pilot._role_value(r["cid"])
                       for i, r in enumerate(rows) if not elig[i])
    resolution = pilot._leaf_needs_resolution(obs, my_index)
    assert resolution.latent_worth < undiscounted, (
        f"the discounted latent {resolution.latent_worth} did not fall below the undiscounted "
        f"{undiscounted} — this frame is what paid for Hilda")
    options = ((obs.get("select") or {}).get("option")) or []
    hilda = next(i for i, o in enumerate(options) if o.get("type") == 7 and o.get("index") == 5)
    line = pilot._composer_line(obs, obs.get("select") or {}, None, options, ())
    assert line is not None and line.next_step == [hilda], (
        "the composer no longer commits Hilda here — that is a RULING for the developer and the "
        "reason ADR-0133 reverted, not a test to make green")
