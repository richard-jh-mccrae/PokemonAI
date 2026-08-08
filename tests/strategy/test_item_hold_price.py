"""The general free-Item HOLD price (`common/hold_value.py` + `Pilot._item_hold_price`) — Issue #261
item 2f, old Issue #212.

`_finish_turn_last` tiers a free Item ahead of everything, so a purely positive term can never
decline one — which is why the price exists at all.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

from common import currency, hold_value                            # noqa: E402
from common.hold_value import ITEM_HOLD_FLOOR, hold_price          # noqa: E402

FIXTURES = REPO / "tests" / "fixtures" / "corrections"

HAMMER = 1120                              # `energy_denial`, no ROLE / TAG tier
IGNITION = 17                              # `discard_eot`, TAG_TIER 30
MAIN, PLAY = 0, 7


# ── the pure equation ────────────────────────────────────────────────────────────────────────────

@pytest.mark.req("REQ-HOLD-0001")
def test_the_price_is_strictly_positive_whatever_the_assignment_says():
    """A decider subtracts this to reach a NEGATIVE score, the only thing `_finish_turn_last` accepts
    as a decline: a hold price of 0 is not "free", it is "played" (ADR-0093 decision 4)."""
    for keep in (-50.0, 0.0, 0.0001, 9.99):
        assert hold_price(keep) > 0.0, f"a hold price must never reach 0 (keep={keep})"


@pytest.mark.req("REQ-HOLD-0001")
def test_a_negative_or_absent_marginal_never_reads_as_a_gain():
    assert hold_price(-100.0) == hold_price(0.0) == pytest.approx(ITEM_HOLD_FLOOR)


@pytest.mark.req("REQ-HOLD-0002")
def test_the_floor_is_a_lower_bound_and_never_a_surcharge():
    """`max`, not `+`: the floor and the assignment are two readings of the same loss, so adding them
    charges a live card twice (ADR-0063)."""
    assert hold_price(ITEM_HOLD_FLOOR + 15.0) == pytest.approx(ITEM_HOLD_FLOOR + 15.0)
    assert hold_price(ITEM_HOLD_FLOOR + 15.0) < ITEM_HOLD_FLOOR + (ITEM_HOLD_FLOOR + 15.0)


@pytest.mark.req("REQ-HOLD-0001")
def test_the_worth_to_damage_crossing_goes_through_currency_and_is_named():
    """The crossing has units — damage per worth point — and `currency.py` is where every such rate
    is catalogued so a disagreement between two of them is visible (ADR-0078)."""
    assert hold_price(42.0) == pytest.approx(currency.item_hold_to_damage(42.0))
    assert currency.item_hold_to_damage(1.0) == pytest.approx(currency.ITEM_HOLD_WORTH_RATE)


# ── the Pilot resolver, on real boards ───────────────────────────────────────────────────────────

def _pilot(deck="mega_starmie"):
    from train.tune import _build_pilot          # `tools/` is on the path via tests/conftest.py
    p = _build_pilot(deck)[0]
    p._planning = False
    return p


def _body(cid, energies=()):
    return {"id": cid, "serial": 0, "energies": list(energies),
            "energyCards": [{"id": e} for e in energies],
            "tools": [], "preEvolution": [], "hp": 200, "maxHp": 200}


def _obs(hand):
    return {"select": {"type": 0, "context": MAIN, "minCount": 1, "maxCount": 1,
                       "option": [{"type": PLAY, "index": 0}], "deck": None,
                       "remainDamageCounter": 0, "remainEnergyCost": 0,
                       "contextCard": None, "effect": None},
            "logs": [], "current": {"turn": 4, "yourIndex": 0, "players": [
                {"active": [_body(999999)], "bench": [], "hand": [{"id": c} for c in hand],
                 "handCount": len(hand), "discard": [], "prize": [None] * 3},
                {"active": [], "bench": [], "hand": None, "handCount": 0,
                 "discard": [], "prize": [None] * 3},
            ]}}


@pytest.fixture(scope="module")
def f11():
    """Hand: 2x Pokegear 3.0, 2x Crushing Hammer, Ignition Energy, Hero's Cape, against a Riolu
    carrying the opponent's only Energy."""
    fx = json.loads((FIXTURES / "ms_information_before_commitment_f11.json")
                    .read_text(encoding="utf-8"))
    p = _pilot()
    return fx["obs"], p, p._board(fx["obs"], fx["obs"]["select"])


@pytest.mark.req("REQ-HOLD-0003")
def test_a_role_less_item_takes_the_floor_when_the_opponent_has_nothing_to_strip():
    """Without the floor the fire rung prices 0.0 on exactly the board where the strip whiffs, lands
    in the last tier tied with End, and is played by option index — ADR-0093 decision 4's defect."""
    p = _pilot()
    obs = _obs((HAMMER,))
    board = p._board(obs, obs["select"])
    assert p._item_hold_price(obs, board, HAMMER) == pytest.approx(ITEM_HOLD_FLOOR)


@pytest.mark.req("REQ-HOLD-0003")
def test_the_floor_also_carries_the_duplicate_copy_the_assignment_prices_at_zero(f11):
    """Two Hammers solo-price 0 each because the sibling covers the one live `deny` slot: the copy
    being spent looks free exactly when the hand is richest in it."""
    obs, p, board = f11
    assert p._item_hold_price(obs, board, HAMMER) == pytest.approx(ITEM_HOLD_FLOOR)


@pytest.mark.req("REQ-HOLD-0004")
def test_a_card_covering_a_live_need_costs_MORE_than_the_floor(f11):
    """An inequality, not a number: re-pinning the number would make this a second opinion about the
    keep machinery — the drift ADR-0103 amendment A had to unwind on the shed predictor."""
    obs, p, board = f11
    assert p._item_hold_price(obs, board, IGNITION) > ITEM_HOLD_FLOOR, (
        "a card the assignment says is covering something must cost more than one that covers "
        "nothing — otherwise the keep machinery is wired in but not consulted")
    assert p._item_hold_price(obs, board, HAMMER) == pytest.approx(ITEM_HOLD_FLOOR), (
        "and the role-less Item on the SAME board still takes the floor, so the two are separated "
        "by the assignment rather than by one of them happening to be an Item")


@pytest.mark.req("REQ-HOLD-0005")
def test_a_card_that_is_not_in_hand_takes_the_bare_floor_rather_than_raising():
    p = _pilot()
    obs = _obs((IGNITION,))
    board = p._board(obs, obs["select"])
    assert p._item_hold_price(obs, board, HAMMER) == pytest.approx(ITEM_HOLD_FLOOR)
    assert p._item_hold_price(obs, board, None) == pytest.approx(ITEM_HOLD_FLOOR)


@pytest.mark.req("REQ-HOLD-0005")
def test_the_price_is_resolved_once_per_decision_and_reset_by_the_board_build():
    """The memo is per DECISION, not per Pilot: a rollout step re-runs `_evaluate` on its own
    SearchState, and serving it the root's answer is the split ADR-0093 decision 3 refused."""
    p = _pilot()
    obs = _obs((HAMMER, IGNITION))
    board = p._board(obs, obs["select"])
    p._item_hold_price(obs, board, HAMMER)
    assert HAMMER in p._item_hold_cache
    p._board(obs, obs["select"])
    assert p._item_hold_cache == {}, "the board build must clear the per-decision memo"


@pytest.mark.req("REQ-HOLD-0006")
def test_the_deleted_constant_is_really_gone():
    from common import pilot
    assert not hasattr(pilot, "_DENIAL_ITEM_COST")
    assert hold_value.ITEM_HOLD_FLOOR == 10.0, (
        "the value is re-homed, deliberately NOT re-derived — Issue #212 scoped that out, and "
        "keeping it is what makes the swap behaviour-preserving where the corpus already ruled")
