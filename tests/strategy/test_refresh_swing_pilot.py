"""Hand-refresh swing (ADR-0060) through the SHIPPED Pilot — real captured boards, full option
menu, shipped weights.

We assert the refresh option's SCORE, not the argmax, wherever `_finish_turn_last` tiering governs
the pick: an attack is deferred to last and an Item outranks a Supporter by TIER regardless of
score, so the argmax can mask a badly-scored refresh in both directions.
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
    """`(pilot, obs, board, ctx)` for a named fixture file OR a corpus frame. The ctx carries only
    what the shed/swing readers use, so no test re-runs the heavyweight per-option `_context`."""
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
    """The refresh stays out even when a modelled choice can precede the later terminal action."""
    fx = _fx("ms_dont_lillies_away_the_bigger_hand_f94.json")
    pilot = _shipped_pilot("mega_starmie")
    dec, lillies = _refresh_traces(pilot, fx, LILLIES)
    assert all(t.index not in dec.chosen for t in lillies), "still shuffling away the 10-card hand"
    assert all(dec.options[i].card_id != LILLIES for i in dec.chosen)


@pytest.mark.parametrize("fixture,label", [
    ("ms_harlequin_the_stacked_hand_f45.json", "opp 7"),
    ("ms_harlequin_the_stacked_hand_f100.json", "opp 9"),
    ("ms_harlequin_vs_stacked_hand_f64.json", "opp 21"),
])
def test_disrupt_the_stacked_hand(fixture, label):
    """A positive swing must keep the refresh POSITIVE — the regression half of the gate: killing
    the blunders must not kill these."""
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


# A test whose ONLY assertion was `"<deleted-rung>" not in _fired(...)` is DELETED here (Issue #386):
# once the rung is gone that is true of every board, so it went GREEN while checking nothing.
@pytest.mark.req("REQ-NEEDS-0007")
def test_the_shed_leg_is_the_v2_assignment_set_marginal(refresh_ctx):
    """ADR-0101: the SHED leg IS `needs.set_keep_v2` over the whole shuffled hand — the same
    resolver/resupply the discard decider reads, so `swing == CYCLE − shed + opponent-side legs`."""
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
    """The v2 shed is the SET marginal `V(hand) − V(∅)`. Each duplicate solo-prices 0 (its sibling
    covers the slot) while shuffling BOTH loses the class, which a per-copy sum reads as free."""
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
    """Per-slot P(the closure re-supplies it in the refresh draw window). Closing-edge kinds, pitch
    fuel, `general` and an uncovered slot all stay 0.0; a live slot lands strictly inside (0, 1]."""
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
    """The resupply leg reaches the DECIDER: a shed with live per-slot re-supply odds is cheaper than
    the same assignment frozen at 0.0, so the swing it feeds is correspondingly higher."""
    pilot, obs, board, ctx = refresh_ctx("ms_dont_lillies_away_the_bigger_hand_f94.json", LILLIES)
    live_shed = pilot._refresh_shed_keepcost(obs, board, ctx)
    live_swing = pilot._refresh_swing_tactical(obs, board, ctx)
    pilot._refresh_slot_resupply = (
        lambda slots, elig, rows, obs, board, draws: [0.0] * len(slots))
    assert live_shed < pilot._refresh_shed_keepcost(obs, board, ctx)
    assert live_swing > pilot._refresh_swing_tactical(obs, board, ctx)
