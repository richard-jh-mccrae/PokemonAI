"""Hand-refresh swing (ADR-0060) through the SHIPPED Pilot — real captured boards, full option
menu, shipped weights. The strict retest bar.

Six human corrections, all on the same axis and none of them previously gated:

  MUST NOT play the refresh (we would shed the bigger hand)
    ml f111  Judge,     my 8  / opp 1   swing -7   "such an enormous blunder"          (CRITICAL)
    ms f60   Harlequin, my 11 / opp 2   swing -9   "a HUGE blunder, HUGE!"
    ms f94   Lillie's,  my 10 / opp 3   swing -4   "never shuffle back hand > 7"

  MUST play the refresh (their hand is stacked, ours is not)
    ms f45   Harlequin, my 6  / opp 7   swing +1   "harlequin would have done well here"
    ms f100  Harlequin, my 5  / opp 9   swing +4   "a great time to disrupt"
    ms f64   Harlequin, my 8  / opp 21  swing +13  "play harlequin to reduce their handsize"

We assert the refresh option's SCORE, not the argmax, wherever `_finish_turn_last` tiering governs
the pick: an attack is deferred to last and an Item outranks a Supporter by TIER regardless of
score, so the argmax can mask a badly-scored refresh in both directions. That masking is exactly why
f111's own fixture sat in the tree ungated -- the KO dominated and hid a Judge scored at -5 on a
-7 board. f94 is the one frame where the blunder reaches the argmax, so it gets both assertions.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

JUDGE, HARLEQUIN, LILLIES = 1213, 1223, 1227


def _shipped_pilot(agent):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(agent)[0]


def _fx(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / name).read_text(encoding="utf-8"))


def _refresh_traces(pilot, fx, card_id):
    dec = pilot.explain(fx["obs"])
    return dec, [t for t in dec.options if t.card_id == card_id]


@pytest.mark.parametrize("agent,fixture,card,label", [
    ("mega_lucario", "ml_dont_judge_away_the_bigger_hand_f111.json", JUDGE, "Judge my8/opp1"),
    ("mega_starmie", "ms_dont_harlequin_away_the_bigger_hand_f60.json", HARLEQUIN, "Harlequin my11/opp2"),
    ("mega_starmie", "ms_dont_lillies_away_the_bigger_hand_f94.json", LILLIES, "Lillie's my10/opp3"),
])
def test_never_shuffle_away_the_bigger_hand(agent, fixture, card, label):
    """A negative swing must score the refresh NEGATIVE — it can then never win a PLAY tier."""
    fx = _fx(fixture)
    dec, traces = _refresh_traces(_shipped_pilot(agent), fx, card)
    assert traces, f"{fixture}: no {label} option on the menu"
    for t in traces:
        assert t.score < 0, f"{fixture}: {label} scored {t.score:+.1f}, must be negative"
        assert t.index not in dec.chosen, f"{fixture}: played {label} anyway"


def test_lillies_big_hand_blunder_is_not_merely_masked():
    """ms f94 is the ONE frame where the blunder reaches the ARGMAX: the shipped Pilot played
    Lillie's (10 cards in hand, redrawing 6) INSTEAD OF ATTACKING. `dont-shuffle-away-the-bigger-
    hand` could never reach it -- Lillie's carries no `hand_disruption` tag -- so only the swing
    catches it.

    We assert the correction's actual claim: we attack rather than shed the hand. We do NOT pin the
    human's labelled attack ([14] Nebula Beam 210) over the Pilot's ([13] Jetting Blow 120 + its
    bench-snipe rider), because that is a SECOND, already-adjudicated axis -- the KO Race ranks
    Jetting above Nebula on captured states like this one (reviewed.json ep83661649 f30 'fixed',
    ep83116501 f60 'covered'). Pinning it here would smuggle a settled combat question into a
    hand-economy test.
    """
    fx = _fx("ms_dont_lillies_away_the_bigger_hand_f94.json")
    pilot = _shipped_pilot("mega_starmie")
    dec, lillies = _refresh_traces(pilot, fx, LILLIES)
    options = fx["obs"]["select"]["option"]
    assert all(t.index not in dec.chosen for t in lillies), "still shuffling away the 10-card hand"
    assert all(options[i].get("attackId") for i in dec.chosen), (
        f"chose {dec.chosen}, expected an attack instead of the refresh")


@pytest.mark.parametrize("fixture,label", [
    ("ms_harlequin_the_stacked_hand_f45.json", "opp 7"),
    ("ms_harlequin_the_stacked_hand_f100.json", "opp 9"),
    ("ms_harlequin_vs_stacked_hand_f64.json", "opp 21"),
])
def test_disrupt_the_stacked_hand(fixture, label):
    """A positive swing must keep the refresh POSITIVE. These three pass today only by
    `dig-before-commit`'s hand-blind +20 -- the same flat pull that causes f111/f60/f94 -- so they
    are the regression half of the gate: killing the blunders must not kill these."""
    fx = _fx(fixture)
    _, traces = _refresh_traces(_shipped_pilot("mega_starmie"), fx, HARLEQUIN)
    assert traces, f"{fixture}: no Harlequin option"
    assert max(t.score for t in traces) > 0, f"{fixture} ({label}): Harlequin must stay positive"


def test_harlequin_outranks_lillies_when_the_opponent_is_the_one_holding_cards():
    """ms f100: opp 9 / my 5. Harlequin's swing is +4, Lillie's is +1 -- but today both score a flat
    +20 and Harlequin wins only on index order. The disruption must be preferred on merit."""
    fx = _fx("ms_harlequin_the_stacked_hand_f100.json")
    dec = _shipped_pilot("mega_starmie").explain(fx["obs"])
    harlequin = max(t.score for t in dec.options if t.card_id == HARLEQUIN)
    lillies = max(t.score for t in dec.options if t.card_id == LILLIES)
    assert harlequin > lillies, f"Harlequin {harlequin:+.1f} must beat Lillie's {lillies:+.1f}"


def test_the_refresh_oracle_owns_the_shuffle_refresh_value():
    """`dig-before-commit` is hand-size-blind and must no longer endorse a shuffle-refresh -- the
    swing oracle is the single owner. It keeps endorsing genuine digs (tutors, Ball search)."""
    fx = _fx("ms_dont_harlequin_away_the_bigger_hand_f60.json")
    _, traces = _refresh_traces(_shipped_pilot("mega_starmie"), fx, HARLEQUIN)
    fired = {h.id for t in traces for h, _ in t.fired}
    assert "dig-before-commit" not in fired, "dig-before-commit still endorses a shuffle-refresh"


@pytest.mark.req("REQ-NEEDS-0007")
def test_refresh_shed_v2_shadow_rides_the_decision_with_the_swing_identity():
    """WP-N4b: at a real shuffle-refresh the keep-value v2 MAGNITUDE shadow rides the Decision — v1's
    Σ keep_cost (`_refresh_shed_keepcost`) beside v2's whole-hand assignment marginal
    (`needs.set_keep_v2`), the two refresh swings, and the SIGN-agreement bit. Deciding NOTHING: the
    shed still uses v1. The swing identity `swing_v2 = swing_v1 + (v1_shed − v2_shed)` holds exactly
    (the shed is the only term that changes), and every held row carries its `keep_v2`."""
    fx = _fx("ms_dont_lillies_away_the_bigger_hand_f94.json")
    s = _shipped_pilot("mega_starmie").explain(fx["obs"]).refresh_shadow
    assert s is not None and isinstance(s["sign_agree"], bool)
    assert s["swing_v2"] == pytest.approx(s["swing_v1"] + s["v1_shed"] - s["v2_shed"], abs=0.05)
    assert s["cid"] == LILLIES and all("keep_v2" in r for r in s["eq"])
    # The two magnitudes measure different things by v0 scope: v1 discounts each copy by its
    # re-access odds; v2 (resupply 0.0 — WP-N3 deferred) does not, but prices the hand as an
    # ASSIGNMENT (sets-not-sums). So a divergence in EITHER direction is real telemetry — v2 < v1 is
    # over-counted duplicates, v2 > v1 is the missing resupply leg (WP-N5). Both are non-negative.
    assert s["v1_shed"] >= 0.0 and s["v2_shed"] >= 0.0
