"""Hand-refresh swing oracle (ADR-0060) — the closed-form value of a shuffle-refresh.

Judge and Harlequin are SYMMETRIC REFILLS, not strips: both players shuffle their hand away and
redraw, so the whole value of playing one is the net card swing

    swing = my_net - opp_net,  where  my_net  = my_draw  - my_hand
                                      opp_net = opp_draw - opp_hand   (0 if they don't shuffle)

Every expected value below is derived from the PRINTED CARD TEXT (data/EN_Card_Data.csv), never by
re-running the implementation:

- Judge (1213)                "Each player shuffles their hand into their deck and draws 4 cards."
- Harlequin (1223)            "...flip a coin. If heads, you draw 5 and your opponent draws 3.
                               If tails, you draw 3 and your opponent draws 5."
- Unfair Stamp (1080)         "...you draw 5 cards, and your opponent draws 2 cards."
- Lillie's Determination (1227) "Shuffle YOUR hand into YOUR deck. Then, draw 6 cards. If you have
                               exactly 6 Prize cards remaining, draw 8 cards instead."
- Lacey (1199)                "Shuffle your hand into your deck. Then, draw 4 cards. If your
                               opponent has 3 or fewer Prize cards remaining, draw 8 cards instead."
"""
import pytest

from common.strategy.refresh import (fresh_cards, hand_swing, net_change, own_draw_count,
                                     refills_opponent, refresh_branches)

FULL_PRIZES = 6          # nobody has taken a prize yet


# --- the card facts themselves -------------------------------------------------------------------

def test_judge_is_a_symmetric_four_four_refill():
    assert refresh_branches(1213, my_prizes_remaining=6, opp_prizes_remaining=6) == ((4, 4),)


def test_harlequin_is_a_coin_between_five_three_and_three_five():
    assert refresh_branches(1223, my_prizes_remaining=6, opp_prizes_remaining=6) == ((5, 3), (3, 5))


def test_unfair_stamp_is_asymmetric_five_two():
    assert refresh_branches(1080, my_prizes_remaining=6, opp_prizes_remaining=6) == ((5, 2),)


def test_lillies_draws_eight_at_exactly_six_prizes_and_six_otherwise():
    assert refresh_branches(1227, my_prizes_remaining=6, opp_prizes_remaining=6) == ((8, 0),)
    assert refresh_branches(1227, my_prizes_remaining=5, opp_prizes_remaining=6) == ((6, 0),)


def test_lacey_draws_eight_once_the_opponent_is_at_three_prizes_or_fewer():
    assert refresh_branches(1199, my_prizes_remaining=6, opp_prizes_remaining=3) == ((8, 0),)
    assert refresh_branches(1199, my_prizes_remaining=6, opp_prizes_remaining=4) == ((4, 0),)


def test_a_card_with_no_refresh_facts_is_silent():
    assert refresh_branches(9999, my_prizes_remaining=6, opp_prizes_remaining=6) is None
    assert hand_swing(9999, my_hand=5, opp_hand=5,
                      my_prizes_remaining=6, opp_prizes_remaining=6) is None


# --- the swing, on the boards the human actually corrected ----------------------------------------

def _swing(card_id, my_hand, opp_hand, my_prizes=FULL_PRIZES, opp_prizes=FULL_PRIZES):
    return hand_swing(card_id, my_hand=my_hand, opp_hand=opp_hand,
                      my_prizes_remaining=my_prizes, opp_prizes_remaining=opp_prizes)


def test_judging_away_the_bigger_hand_is_a_deeply_negative_swing():
    """ml ep85709280 f111 (CRITICAL): 'played Judge when we have a hand of 8 good cards and
    opponent has a hand of 1. such an enormous blunder.'  We shed 8 for 4; they trade 1 for 4."""
    assert _swing(1213, my_hand=8, opp_hand=1) == -7      # (4-8) - (4-1)


def test_harlequin_into_our_own_huge_hand_is_worse_still():
    """ms ep82750161 f60: 'We have 11 cards in our hand, opponent has 2 ... a terrible deal.'"""
    assert _swing(1223, my_hand=11, opp_hand=2) == -9     # EV: (4-11) - (4-2)


def test_disrupting_a_stacked_opponent_hand_is_positive():
    """ms f43 (opp 8) / f100 (opp 9) / f45 (opp 7): 'a perfect time to play Harlequin'."""
    assert _swing(1223, my_hand=4, opp_hand=8) == 4
    assert _swing(1213, my_hand=3, opp_hand=9) == 6
    assert _swing(1223, my_hand=4, opp_hand=7) == 3


def test_unfair_stamp_is_always_three_better_than_judge():
    """Same board, 5/2 vs 4/4 -> a flat +3 edge for the ACE SPEC Item."""
    for my_hand, opp_hand in [(3, 4), (8, 1), (2, 9)]:
        assert (_swing(1080, my_hand, opp_hand) - _swing(1213, my_hand, opp_hand)) == 3


def test_lillies_break_even_is_its_own_draw_count_not_a_constant():
    """ms ep82752045 f94: 'probably never shuffle back hand greater than 7'. Lillie's draws 6 --
    so the break-even is 6, and 8 at exactly six prizes. The opponent's hand is untouched."""
    assert _swing(1227, my_hand=6, opp_hand=99, my_prizes=5) == 0     # break-even, opp irrelevant
    assert _swing(1227, my_hand=8, opp_hand=99, my_prizes=5) == -2
    assert _swing(1227, my_hand=8, opp_hand=99, my_prizes=6) == 0     # 8-card draw at six prizes


def test_lillies_beats_harlequin_on_a_big_early_hand():
    """ms 83116081 f17 / 82754241 f11 -- the ledger closed these as 'a Base-Value-Model call, not a
    weight gap'. They are closed-form: at six prizes with 8 in hand, Lillie's is neutral and
    Harlequin is negative."""
    assert _swing(1227, my_hand=8, opp_hand=5) > _swing(1223, my_hand=8, opp_hand=5)


def test_a_self_only_refresh_never_reads_the_opponents_hand():
    """Lillie's/Lacey shuffle only MY hand, so their swing is independent of opp_hand."""
    assert _swing(1227, 4, 1) == _swing(1227, 4, 12)
    assert _swing(1199, 4, 1) == _swing(1199, 4, 12)


def test_a_symmetric_refresh_does_read_the_opponents_hand():
    assert _swing(1213, 4, 1) != _swing(1213, 4, 12)


# --- the two halves, which the scorer prices differently ------------------------------------------

def test_net_change_splits_the_swing_into_its_two_directions():
    """Judge, my 8 / opp 1: I shed 8 and redraw 4 (-4); they trade 1 for 4 (+3). Both are certain,
    and their SUM is the swing (-7) -- but a card I shed is one I chose to keep, while a card I draw
    is unseen, so the scorer must be able to price them apart."""
    my_net, opp_net = net_change(1213, my_hand=8, opp_hand=1,
                                 my_prizes_remaining=6, opp_prizes_remaining=6)
    assert (my_net, opp_net) == (-4, 3)
    assert my_net - opp_net == _swing(1213, 8, 1)


def test_a_self_only_refresh_leaves_the_opponent_net_untouched():
    """Lillie's shuffles only MY hand -- their net is 0, NOT `0 - opp_hand`. Getting this wrong
    would price Lillie's as if it stripped the opponent's whole hand."""
    _my, opp_net = net_change(1227, my_hand=4, opp_hand=9,
                              my_prizes_remaining=6, opp_prizes_remaining=6)
    assert opp_net == 0


def test_fresh_counts_only_the_stripped_cards_they_just_drew():
    """`opp_hand_size_delta` > 0 means they GREW their hand -- it is fresh. Capped by the hand we
    actually strip, zero for a self-only refresh, and zero until a prior turn is known."""
    assert fresh_cards(1213, opp_hand=9, opp_hand_size_delta=4) == 4
    assert fresh_cards(1213, opp_hand=3, opp_hand_size_delta=9) == 3     # capped by their hand
    assert fresh_cards(1213, opp_hand=9, opp_hand_size_delta=-5) == 0    # they SHRANK: stale
    assert fresh_cards(1213, opp_hand=9, opp_hand_size_delta=None) == 0  # no prior turn yet
    assert fresh_cards(1227, opp_hand=9, opp_hand_size_delta=4) == 0     # self-only: strips nothing


# --- own draw count: the grab-time tie-break input (build item 1) ---------------------------------

def test_own_draw_count_is_the_cards_averaged_self_draw():
    """The card's OWN redraw count, averaged over its coin branches — the quantity that ranks a
    bigger-ceiling refresh above a smaller one at a TO_HAND grab. Read from the printed card text,
    never the implementation."""
    assert own_draw_count(1213, my_prizes_remaining=6, opp_prizes_remaining=6) == 4   # Judge 4/4
    assert own_draw_count(1223, my_prizes_remaining=6, opp_prizes_remaining=6) == 4   # Harlequin EV (5+3)/2
    assert own_draw_count(1080, my_prizes_remaining=6, opp_prizes_remaining=6) == 5   # Unfair Stamp 5/2


def test_own_draw_count_reads_the_prize_conditional_windows():
    """Lillie's draws 8 at exactly six prizes, 6 otherwise; Lacey 8 once the opponent is at 3 prizes
    or fewer — so a grab-time tie-break sees the same conditional window `hand_swing` does."""
    assert own_draw_count(1227, my_prizes_remaining=6, opp_prizes_remaining=6) == 8   # Lillie's @ 6
    assert own_draw_count(1227, my_prizes_remaining=5, opp_prizes_remaining=6) == 6   # Lillie's otherwise
    assert own_draw_count(1199, my_prizes_remaining=6, opp_prizes_remaining=3) == 8   # Lacey @ opp≤3
    assert own_draw_count(1199, my_prizes_remaining=6, opp_prizes_remaining=4) == 4


def test_own_draw_count_is_none_for_a_non_refresh():
    assert own_draw_count(9999, my_prizes_remaining=6, opp_prizes_remaining=6) is None


def test_lillies_out_draws_judge_at_the_grab():
    """The 86088989-29 claim, at the oracle: early (six prizes) Lillie's redraws 8 to Judge's 4, so
    a grab-time tie-break that reads own-draw prefers Lillie's."""
    assert (own_draw_count(1227, my_prizes_remaining=6, opp_prizes_remaining=6)
            > own_draw_count(1213, my_prizes_remaining=6, opp_prizes_remaining=6))


# --- refills_opponent: the dont-gift sign gate (build item 2) -------------------------------------

def test_refills_opponent_is_true_only_when_the_symmetric_refresh_grows_their_hand():
    """Judge redraws the opponent to 4: a GIFT when their hand is below 4, a STRIP at or above it.
    The `dont-gift-a-refresh-when-favored` tax must fire only on the gift."""
    assert refills_opponent(1213, opp_hand=1, my_prizes_remaining=6, opp_prizes_remaining=6) is True
    assert refills_opponent(1213, opp_hand=3, my_prizes_remaining=6, opp_prizes_remaining=6) is True
    assert refills_opponent(1213, opp_hand=4, my_prizes_remaining=6, opp_prizes_remaining=6) is False
    assert refills_opponent(1213, opp_hand=8, my_prizes_remaining=6, opp_prizes_remaining=6) is False


def test_refills_opponent_is_false_for_a_self_only_refresh():
    """Lillie's / Lacey never touch the opponent's hand — they can never gift, whatever their hand."""
    assert refills_opponent(1227, opp_hand=1, my_prizes_remaining=6, opp_prizes_remaining=6) is False
    assert refills_opponent(1199, opp_hand=1, my_prizes_remaining=6, opp_prizes_remaining=6) is False


def test_refills_opponent_is_false_for_an_unknown_card():
    """Fail toward NOT taxing: an unknown card makes no gift claim (never over-suppress a strip)."""
    assert refills_opponent(9999, opp_hand=1, my_prizes_remaining=6, opp_prizes_remaining=6) is False


# --- one fact, two stores (Issue #302) -----------------------------------------------------------

def test_the_compendium_and_this_oracle_state_the_same_draw_counts():
    """**Two stores hold the refresh draw counts and they must agree.**

    This module's `_REFRESH` table is the ADR-0060 oracle the live scorer reads
    (`pilot._refresh_cycle` → `net_change`). `card_effects.json` is the compendium the apply seam
    reads. Until Issue #302 they disagreed on four of these five cards — the compendium stated
    Lillie's maximum (8) as its base and Lacey's likewise, and carried no coin branch at all for
    Harlequin — and nothing checked, because the two are read by different consumers on different
    tracks. This is that check.

    The comparison is deliberately over the OWN-side count only: the compendium's clause set is
    ruled `partial` for exactly the opponent leg on the three symmetric cards, so asserting the
    opponent's number would assert a fact one of the two stores honestly does not claim."""
    from pathlib import Path
    from common.effects import CardEffects
    eff = CardEffects.load(Path(__file__).resolve().parents[2] / "src" / "common" / "card_effects.json")

    def compendium_own_draw(cid, my_prizes, opp_prizes, tails):
        """The own-side count the compendium states, on this board and this coin face."""
        clause, = eff.clauses(cid)
        branch = clause.get("amount_if") or {}
        fires = {"exactly_6_prizes_remaining": my_prizes == 6,
                 "opp_3_or_fewer_prizes": 0 < opp_prizes <= 3,
                 "coin_tails": tails}[branch["condition"]] if branch else False
        return branch["amount"] if fires else clause["amount"]

    boards = [(6, 6), (5, 6), (6, 3), (4, 2), (1, 1)]
    for cid in (1213, 1080, 1227, 1199):                       # the four with no coin
        for mp, op in boards:
            assert compendium_own_draw(cid, mp, op, tails=False) == \
                own_draw_count(cid, mp, op), (cid, mp, op)
    # Harlequin's two coin faces average to the oracle's EV — 5 heads / 3 tails is 4, which is what
    # `own_draw_count` returns after averaging its equally-likely branches.
    faces = [compendium_own_draw(1223, 6, 6, tails=t) for t in (False, True)]
    assert faces == [5, 3]
    assert sum(faces) / 2 == own_draw_count(1223, 6, 6)
    # Positive control: the helper is reading the compendium, not echoing the oracle. A card the
    # oracle has never heard of still yields a number here — Billy & O'Nare draws 2, and its own
    # `amount_if` predicate is one this board-reader deliberately does not evaluate (the hand size
    # is not a refresh input), so the base is the honest answer.
    billy, = eff.clauses(1181)
    assert billy["amount"] == 2 and own_draw_count(1181, 6, 6) is None
