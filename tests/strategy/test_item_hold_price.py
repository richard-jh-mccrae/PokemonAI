"""The general free-Item HOLD price (`common/hold_value.py` + `Pilot._item_hold_price`) — Issue #261
item 2f, old Issue #212.

`_DENIAL_ITEM_COST = 10` priced *"an Item is finite"* for Crushing / Enhanced Hammer and for nothing
else in the pool, because its only consumer was gated shut for every card outside `energy_denial`.
The reason it existed is a property of the SEQUENCER, not of Hammers: `_finish_turn_last` tiers a
free Item ahead of everything, so a purely positive term can never decline one. This file pins the
generalisation onto the keep machinery, and pins the two properties that make it correct rather than
merely general:

  * the FLOOR is load-bearing (REQ-HOLD-0002/0003) — a role-less Item's Needs marginal collapses to 0
    on exactly the boards where its play whiffs, so a keep-machinery reading ALONE would re-open
    ADR-0093 decision 4's defect;
  * the ASSIGNMENT is load-bearing too (REQ-HOLD-0004) — a card covering a live need costs MORE than
    the floor, which is the whole content of "generalize into the keep machinery" and the half a
    re-homed constant would not have delivered.

`test_deny_relevance_consumer.py` carries the behaviour-preservation side: every deny fixture in the
suite prices identically before and after, because the floor binds on all of them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

from common import currency, hold_value                            # noqa: E402
from common.hold_value import ITEM_HOLD_FLOOR, hold_price          # noqa: E402

FIXTURES = REPO / "tests" / "fixtures" / "corrections"

HAMMER = 1120                              # Crushing Hammer — `energy_denial`, no ROLE / TAG tier
IGNITION = 17                              # Ignition Energy — `discard_eot`, TAG_TIER 30
MAIN, PLAY = 0, 7


# ── the pure equation ────────────────────────────────────────────────────────────────────────────

@pytest.mark.req("REQ-HOLD-0001")
def test_the_price_is_strictly_positive_whatever_the_assignment_says():
    """The contract the sequencer needs, and the reason a bare `keep_v2` cannot be the whole answer.

    A decider subtracts this to reach a NEGATIVE score, which is the only thing `_finish_turn_last`
    accepts as a decline — `score > 0` promotes, and `score == 0` lands in the last tier TIED with
    End where stable score order plays it by option index (ADR-0093 decision 4, measured on
    `83686860-13`). So a hold price of 0 is not "free", it is "played"."""
    for keep in (-50.0, 0.0, 0.0001, 9.99):
        assert hold_price(keep) > 0.0, f"a hold price must never reach 0 (keep={keep})"


@pytest.mark.req("REQ-HOLD-0001")
def test_a_negative_or_absent_marginal_never_reads_as_a_gain():
    """An assignment marginal can only be >= 0 by construction, but the resolver hands this whatever
    it computes and a defensive floor at 0 is cheaper than a proof. Spending a card is never a
    profit, so the equation must not let one arrive that way."""
    assert hold_price(-100.0) == hold_price(0.0) == pytest.approx(ITEM_HOLD_FLOOR)


@pytest.mark.req("REQ-HOLD-0002")
def test_the_floor_is_a_lower_bound_and_never_a_surcharge():
    """`max`, not `+`. The floor says *a card spent is a card gone*; the assignment says *and this
    card was covering something*. They are two readings of the same loss, so adding them charges a
    live card twice — the ADR-0063 "a booster must scale, never add" discipline pointed at a cost."""
    assert hold_price(ITEM_HOLD_FLOOR + 15.0) == pytest.approx(ITEM_HOLD_FLOOR + 15.0)
    assert hold_price(ITEM_HOLD_FLOOR + 15.0) < ITEM_HOLD_FLOOR + (ITEM_HOLD_FLOOR + 15.0)


@pytest.mark.req("REQ-HOLD-0001")
def test_the_worth_to_damage_crossing_goes_through_currency_and_is_named():
    """The crossing is the reason this is not just `max(...)` inlined at the call site. It has units
    — damage per worth point — and `currency.py` is where every such rate is catalogued so a
    disagreement between two of them is visible (ADR-0078's founding complaint).

    Pinned as an identity against the module rather than as the literal 1.0, so a deliberate re-point
    of the rate carries the equation with it instead of silently disagreeing with it."""
    assert hold_price(42.0) == pytest.approx(currency.item_hold_to_damage(42.0))
    assert currency.item_hold_to_damage(1.0) == pytest.approx(currency.ITEM_HOLD_WORTH_RATE)


# ── the Pilot resolver, on real boards ───────────────────────────────────────────────────────────

def _pilot(deck="mega_starmie"):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    p = _build_pilot(deck)[0]
    p._planning = False
    return p


def _body(cid, energies=()):
    return {"id": cid, "serial": 0, "energies": list(energies),
            "energyCards": [{"id": e} for e in energies],
            "tools": [], "preEvolution": [], "hp": 200, "maxHp": 200}


def _obs(hand):
    """A MAIN menu over a bare board — the hand is what this seam reads."""
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
    """A REAL captured board — ep82225643 f11, ADR-0095's anchor. Hand: 2x Pokegear 3.0, 2x Crushing
    Hammer, Ignition Energy, Hero's Cape, against a Riolu carrying the opponent's only Energy."""
    fx = json.loads((FIXTURES / "ms_information_before_commitment_f11.json")
                    .read_text(encoding="utf-8"))
    p = _pilot()
    return fx["obs"], p, p._board(fx["obs"], fx["obs"]["select"])


@pytest.mark.req("REQ-HOLD-0003")
def test_a_role_less_item_takes_the_floor_when_the_opponent_has_nothing_to_strip():
    """**Why the floor exists rather than being decoration.** A Crushing Hammer carries no ROLE and no
    `TAG_TIER` entry (`card_worth`: *"A role-less Hammer still prices its global worth 0; only its
    live-strip DENY slot earns the band"*), so against an opponent with nothing to strip its Needs
    marginal is exactly 0.

    That is the same board on which the strip whiffs. Without the floor the fire rung would price
    `odds x weight x 0 - 0` = **0.0**, land in the last tier tied with End, and be played by option
    index — precisely the defect ADR-0093 decision 4 closed."""
    p = _pilot()
    obs = _obs((HAMMER,))
    board = p._board(obs, obs["select"])
    assert p._item_hold_price(obs, board, HAMMER) == pytest.approx(ITEM_HOLD_FLOOR)


@pytest.mark.req("REQ-HOLD-0003")
def test_the_floor_also_carries_the_duplicate_copy_the_assignment_prices_at_zero(f11):
    """The sharper half of the same finding, on a real board where the strip does NOT whiff. f11's
    opponent holds one Energy, so a live `deny` slot exists — and the hand holds TWO Hammers, which
    solo-price 0 each because the sibling covers that one slot (sets-not-sums, and correct as an
    assignment).

    So the copy being SPENT looks free exactly when the hand is richest in it. A card spent is a card
    gone whatever the assignment covers, and the floor is the only thing in the equation that says
    so."""
    obs, p, board = f11
    assert p._item_hold_price(obs, board, HAMMER) == pytest.approx(ITEM_HOLD_FLOOR)


@pytest.mark.req("REQ-HOLD-0004")
def test_a_card_covering_a_live_need_costs_MORE_than_the_floor(f11):
    """The generalisation's actual content, and the half a re-homed constant could not deliver: the
    price is BOARD-DERIVED. On f11 the Ignition Energy is `discard_eot` at `TAG_TIER` 30 and covers a
    live need the assignment can see, so spending it costs strictly MORE than the finiteness floor
    the Hammer beside it pays.

    Asserted as an inequality against the floor rather than as its number, because the number is the
    Needs assignment's and re-pinning it here would make this test a second opinion about the keep
    machinery — the drift ADR-0103 amendment A had to unwind on the shed predictor."""
    obs, p, board = f11
    assert p._item_hold_price(obs, board, IGNITION) > ITEM_HOLD_FLOOR, (
        "a card the assignment says is covering something must cost more than one that covers "
        "nothing — otherwise the keep machinery is wired in but not consulted")
    assert p._item_hold_price(obs, board, HAMMER) == pytest.approx(ITEM_HOLD_FLOOR), (
        "and the role-less Item on the SAME board still takes the floor, so the two are separated "
        "by the assignment rather than by one of them happening to be an Item")


@pytest.mark.req("REQ-HOLD-0005")
def test_a_card_that_is_not_in_hand_takes_the_bare_floor_rather_than_raising():
    """Fail-toward-the-incumbent. A hand-built board, a fetched option, or a card already spent
    resolves to no row in the hand; the honest answer is then the finiteness price alone, which is
    exactly what the deleted constant charged unconditionally."""
    p = _pilot()
    obs = _obs((IGNITION,))
    board = p._board(obs, obs["select"])
    assert p._item_hold_price(obs, board, HAMMER) == pytest.approx(ITEM_HOLD_FLOOR)
    assert p._item_hold_price(obs, board, None) == pytest.approx(ITEM_HOLD_FLOOR)


@pytest.mark.req("REQ-HOLD-0005")
def test_the_price_is_resolved_once_per_decision_and_reset_by_the_board_build():
    """`_denial_play_tactical` runs per OPTION, a hand routinely holds two copies of the same Item,
    and resolving this walks the whole hand through `_resolve_needs`. The memo is per DECISION, not
    per Pilot: a rollout step re-runs `_evaluate` on its own SearchState, and serving it the root's
    answer would be the sim/live policy split ADR-0093 decision 3 refused."""
    p = _pilot()
    obs = _obs((HAMMER, IGNITION))
    board = p._board(obs, obs["select"])
    p._item_hold_price(obs, board, HAMMER)
    assert HAMMER in p._item_hold_cache
    p._board(obs, obs["select"])
    assert p._item_hold_cache == {}, "the board build must clear the per-decision memo"


@pytest.mark.req("REQ-HOLD-0006")
def test_the_deleted_constant_is_really_gone():
    """Directive 1: *"rungs an equation replaces are DELETED, not suppressed."* A surviving
    `_DENIAL_ITEM_COST` would let a future edit quietly re-point deny at the deny-scoped price while
    the seam sat unread beside it."""
    from common import pilot
    assert not hasattr(pilot, "_DENIAL_ITEM_COST")
    assert hold_value.ITEM_HOLD_FLOOR == 10.0, (
        "the value is re-homed, deliberately NOT re-derived — Issue #212 scoped that out, and "
        "keeping it is what makes the swap behaviour-preserving where the corpus already ruled")
