"""`draw_branches`: supported draw shapes yield (mine, theirs) branches; anything else refuses."""
from __future__ import annotations

from common.cards.card_facts import Clause
from common.cards.functions.draw import draw_branches


def test_a_plain_draw_is_one_branch():
    assert draw_branches(Clause("draw", amount=3), 6, 6) == ((3, 0),)


def test_a_coin_flip_yields_both_branches_base_first():
    clause = Clause("draw", amount=3,
                    amount_if={"condition": "coin_tails", "amount": 6})
    assert draw_branches(clause, 6, 6) == ((3, 0), (6, 0))


def test_exactly_six_prizes_condition_switches_on_the_board():
    clause = Clause("draw", amount=3,
                    amount_if={"condition": "exactly_6_prizes_remaining", "amount": 6})
    assert draw_branches(clause, 6, 6) == ((6, 0),)
    assert draw_branches(clause, 5, 6) == ((3, 0),)


def test_opponent_low_prize_condition_excludes_zero_and_four():
    clause = Clause("draw", amount=2,
                    amount_if={"condition": "opp_3_or_fewer_prizes", "amount": 5})
    assert draw_branches(clause, 6, 3) == ((5, 0),)
    assert draw_branches(clause, 6, 4) == ((2, 0),)
    assert draw_branches(clause, 6, 0) == ((2, 0),)     # a finished game is not "3 or fewer"


def test_hand_size_condition_counts_the_card_being_played():
    clause = Clause("draw", amount=1,
                    amount_if={"condition": "hand_size_10_plus_after_draw", "amount": 3})
    assert draw_branches(clause, 6, 6, my_hand_size=10) == ((3, 0),)   # 9 left + 1 drawn = 10
    assert draw_branches(clause, 6, 6, my_hand_size=9) == ((1, 0),)
    assert draw_branches(clause, 6, 6) == ((1, 0),)                    # unknown hand: base


def test_symmetric_shuffle_and_opponent_draw_travel_together():
    both = Clause("draw", amount=5, opponent_amount=5, rider="shuffle_both_hands")
    assert draw_branches(both, 6, 6) == ((5, 5),)
    assert draw_branches(Clause("draw", amount=5, rider="shuffle_both_hands"), 6, 6) is None
    assert draw_branches(Clause("draw", amount=5, opponent_amount=5), 6, 6) is None


def test_unsupported_shapes_refuse_rather_than_guess():
    assert draw_branches(Clause("fetch", amount=3), 6, 6) is None
    assert draw_branches(Clause("draw"), 6, 6) is None
    assert draw_branches(Clause("draw", amount=0), 6, 6) is None
    assert draw_branches(Clause("draw", amount=True), 6, 6) is None
    assert draw_branches(Clause("draw", amount=3, rider="mill_own_deck"), 6, 6) is None
    assert draw_branches(Clause("draw", amount=3, condition="opponent_agrees"), 6, 6) is None
    assert draw_branches(
        Clause("draw", amount=3, amount_if={"condition": "coin_heads", "amount": 6}),
        6, 6) is None
    assert draw_branches(
        Clause("draw", amount=3,
               amount_if={"condition": "coin_tails", "amount": 6, "extra": 1}),
        6, 6) is None


def test_fezandipiti_flip_the_script_prices_through_the_ko_condition_gate():
    """Keep the real gated condition and unmodelled allowance priceable."""
    from common.cards import pokemon_card_store
    clause = pokemon_card_store()[140].abilities[0].clauses[0]
    assert clause == Clause("draw", amount=3, condition="pokemon_ko_last_turn",
                            allowance="card")
    assert draw_branches(clause, 6, 6) == ((3, 0),)


def test_unfair_stamp_prices_its_symmetric_shuffle_draw_through_the_ko_gate():
    from common.cards import trainer_card_store
    clause = trainer_card_store()[1080].clauses[0]
    assert clause == Clause("draw", amount=5, condition="pokemon_ko_last_turn",
                            opponent_amount=2, rider="shuffle_both_hands")
    assert draw_branches(clause, 6, 6) == ((5, 2),)


def test_disagreeing_own_and_opponent_conditions_refuse():
    clause = Clause("draw", amount=3, opponent_amount=3, rider="shuffle_both_hands",
                    amount_if={"condition": "coin_tails", "amount": 6},
                    opponent_amount_if={"condition": "exactly_6_prizes_remaining", "amount": 6})
    assert draw_branches(clause, 6, 6) is None


def test_a_shared_condition_moves_both_counts():
    clause = Clause("draw", amount=3, opponent_amount=3, rider="shuffle_both_hands",
                    amount_if={"condition": "coin_tails", "amount": 6},
                    opponent_amount_if={"condition": "coin_tails", "amount": 1})
    assert draw_branches(clause, 6, 6) == ((3, 3), (6, 1))
