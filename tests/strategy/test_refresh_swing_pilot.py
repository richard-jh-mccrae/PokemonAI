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


@pytest.fixture
def refresh_ctx():
    """The one seam the SHED tests price a refresh through: `(pilot, obs, board, ctx)` for a named
    fixture file OR a corpus frame (`episode, n`). The ctx carries only what
    `_refresh_swing_tactical` / `_refresh_shed_keepcost` read — `card_id` and `option_type` — so a
    test never re-runs the heavyweight per-option `_context` just to price one card."""
    from types import SimpleNamespace

    from common.strategy.context import _PLAY

    def build(locator, card, agent="mega_starmie"):
        if isinstance(locator, str):
            obs = _fx(locator)["obs"]
        else:
            sys.path.insert(0, str(REPO / "tests"))
            from corpus_helpers import corpus_record
            obs = corpus_record(*locator).obs
        pilot = _shipped_pilot(agent)
        board = pilot._board_hypothetical(obs)
        return pilot, obs, board, SimpleNamespace(card_id=card, option_type=_PLAY)

    return build


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
def test_the_shed_leg_is_the_v2_assignment_set_marginal(refresh_ctx):
    """ADR-0101: the SHED leg of the live swing IS `needs.set_keep_v2` over the whole shuffled hand —
    the same resolver/resupply the discard decider reads, not a second summation. The shadow that
    used to carry this number is gone; the equation carries it. Asserted as a seam identity (the
    decider equals the module call over the resolved rows) plus the swing identity: the SHED is the
    only hand-side term, so `swing == CYCLE − shed + (the opponent-side legs)`."""
    from common import needs
    from common.pilot import _REFRESH_CYCLE, _REFRESH_OPPONENT_HAND_FRESH, _REFRESH_OPPONENT_HAND_GIFT, _REFRESH_OPPONENT_HAND_STRIP
    from common.strategy.refresh import fresh_cards, net_change
    pilot, obs, board, ctx = refresh_ctx("ms_dont_lillies_away_the_bigger_hand_f94.json", LILLIES)
    rows = pilot._needs_hand_rows(obs, board, exclude_cid=LILLIES)
    slots, elig = pilot._resolve_needs(obs, board, rows)
    resupply = pilot._refresh_slot_resupply(slots, elig, rows, obs, board, draws=6)
    shed = pilot._refresh_shed_keepcost(obs, board, ctx)
    assert shed == pytest.approx(needs.set_keep_v2(slots, elig, resupply, range(len(rows))), abs=0.05)
    assert shed > 0.0                       # this hand holds live plan pieces — shuffling it is not free
    _my_net, opp_net = net_change(LILLIES, my_hand=board.my_hand_size, opp_hand=board.opp_hand_size,
                                  my_prizes_remaining=board.my_prizes_remaining,
                                  opp_prizes_remaining=board.opp_prizes_remaining)
    stripped = max(-opp_net, 0.0)
    fresh = fresh_cards(LILLIES, board.opp_hand_size, board.opp_hand_size_delta)
    expected = (_REFRESH_CYCLE - shed + _REFRESH_OPPONENT_HAND_STRIP * stripped
                + (_REFRESH_OPPONENT_HAND_FRESH * fresh if stripped > 0 else 0.0)
                - _REFRESH_OPPONENT_HAND_GIFT * max(opp_net, 0.0))
    assert pilot._refresh_swing_tactical(obs, board, ctx) == pytest.approx(expected, abs=0.05)


@pytest.mark.req("REQ-NEEDS-0007")
def test_the_shed_prices_the_hand_as_a_set_not_a_sum(refresh_ctx):
    """The swap's whole substance (ep82522698 f36, two Wally's Compassion): v1 summed the copies, so a
    duplicate plan piece was charged TWICE and the refresh looked too costly. The v2 shed is the SET
    marginal `V(hand) − V(∅)`, and the assignment is submodular, so it is never below the sum of the
    per-copy marginals — on this frame STRICTLY above, because each Wally's solo-prices 0 (its sibling
    covers the one de-duplicated slot) while shuffling BOTH really does lose the class.

    A per-copy sum cannot express that: it reads the pair as free. This is the frame the keep-value
    handoff named as a v2 scope gap, and it is the one the set marginal exists for."""
    from common import needs
    pilot, obs, board, ctx = refresh_ctx(("82522698", 36), HARLEQUIN)
    rows = pilot._needs_hand_rows(obs, board, exclude_cid=HARLEQUIN)
    wally = [k for k, r in enumerate(rows) if r["cid"] == 1229]
    assert len(wally) == 2, "the frame holds two Wally's Compassion"
    slots, elig = pilot._resolve_needs(obs, board, rows)
    resupply = pilot._refresh_slot_resupply(slots, elig, rows, obs, board, draws=4)
    solo = [needs.keep_v2(slots, elig, resupply, k) for k in wally]
    pair = needs.set_keep_v2(slots, elig, resupply, wally)
    assert max(solo) == pytest.approx(0.0), "a duplicate must solo-price 0 — the sibling covers"
    assert pair > sum(solo), "the PAIR must cost what the class is worth, not twice nothing"
    shed = pilot._refresh_shed_keepcost(obs, board, ctx)
    assert shed >= needs.set_keep_v2(slots, elig, resupply, range(len(rows))) - 0.05


@pytest.mark.req("REQ-NEEDS-0008")
def test_refresh_slot_resupply_discounts_by_kind_and_window():
    """`_refresh_slot_resupply` (the WP-N5 residual's fix): per-slot P(the closure re-supplies it in
    the refresh draw window). Closing-edge kinds (deploy_now / answer_doom) stay 0.0 — re-access is
    not bankable against a this-turn deadline (`closing_gate_reaccess` re-derived); pitch-side fuel
    never enters the keep DP; `general` keeps 0.0 (its 0.45 W already carries the site's re-access
    discount — measured, see the helper's docstring); an uncovered slot has no supplier classes to
    point backwards; a live slot lands strictly inside (0, 1]; a `fund_attack` unit's window widens
    with its quota deadline (`quota_window` re-derived), so a later unit re-supplies no less."""
    from common import needs
    fx = _fx("ms_dont_lillies_away_the_bigger_hand_f94.json")
    pilot = _shipped_pilot("mega_starmie")
    obs = fx["obs"]
    board = pilot._board_hypothetical(obs)
    rows = pilot._needs_hand_rows(obs, board)
    assert rows, "fixture hand resolved to no rows"
    slots = [needs.deploy_now_slot("deploy:x", value=30.0),
             needs.answer_doom_slot(value=25.0),
             needs.fuel_slot("fuel", value=10.0),
             needs.general_worth_slot("general:x", value=10.0),
             needs.Slot("line", 30.0, 99, "line:x"),
             needs.Slot("fund_attack", 10.0, 0, "active:unit0"),
             needs.Slot("fund_attack", 10.0, 2, "active:unit2"),
             needs.Slot("line", 30.0, 99, "line:uncovered")]
    elig = [set(range(7)) if k == 0 else set() for k in range(len(rows))]
    r = pilot._refresh_slot_resupply(slots, elig, rows, obs, board, draws=6)
    assert r[0] == r[1] == r[2] == r[3] == 0.0, "closing/pitch/general slots must not discount"
    assert 0.0 < r[4] <= 1.0, "a live no-deadline slot banks the plain refresh window"
    assert 0.0 < r[5] <= r[6] <= 1.0, "the quota-widened window re-supplies no less"
    assert r[7] == 0.0, "no eligible supplier class -> nothing to point backwards"


@pytest.mark.req("REQ-NEEDS-0008")
def test_the_live_shed_is_resupply_discounted(refresh_ctx):
    """The resupply leg reaches the DECIDER now, not a shadow column: the shed with the live
    per-slot re-supply odds is cheaper than the same assignment frozen at 0.0 (the retired v0
    pricing), so the swing it feeds is correspondingly higher. Strict on this fixture — its
    resolver finds a live draw-engine slot the closure can point backwards at."""
    pilot, obs, board, ctx = refresh_ctx("ms_dont_lillies_away_the_bigger_hand_f94.json", LILLIES)
    live_shed = pilot._refresh_shed_keepcost(obs, board, ctx)
    live_swing = pilot._refresh_swing_tactical(obs, board, ctx)
    pilot._refresh_slot_resupply = (
        lambda slots, elig, rows, obs, board, draws: [0.0] * len(slots))
    assert live_shed < pilot._refresh_shed_keepcost(obs, board, ctx)
    assert live_swing > pilot._refresh_swing_tactical(obs, board, ctx)
