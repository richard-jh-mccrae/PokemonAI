from __future__ import annotations

from ledger_helpers import (DARKNESS, DARK_E, FIRE_E, LILLIES, LUNATONE, body, player,
                            printout)

from common.ledger import EvaluationModel, evaluate
from common.ledger.capabilities import card_option_value
from common.observation import ObservationStateBuilder


DUNSPARCE = 65
ENERGY_RETRIEVAL = 1118
MUNKIDORI = 112
SOLROCK = 676


def board(**kwargs):
    return ObservationStateBuilder().root(printout(**kwargs))


def value(state, context=None):
    return evaluate(state, context or EvaluationModel.build()).total


def test_declared_strategy_roles_do_not_change_board_value():
    state = board(me=player(active=body(DUNSPARCE, 1)))
    attacker = EvaluationModel.build(roles={DUNSPARCE: ("primary_attacker",)})
    support = EvaluationModel.build(roles={DUNSPARCE: ("draw_engine", "retreat_assist")})

    assert value(state, attacker) == value(state, support)
    assert not any(item.feature.startswith("role.")
                   for item in evaluate(state, attacker).activations)


def test_solrock_attack_is_live_only_with_lunatone_on_the_bench():
    alone = board(me=player(active=body(SOLROCK, 1, energies=(6,))))
    paired = board(me=player(active=body(SOLROCK, 1, energies=(6,)),
                             bench=[body(LUNATONE, 2)]))

    assert value(paired) > value(alone) + 0.1


def test_dark_energy_prefers_munkidori_damage_transfer_over_dunsparce_gnaw():
    before = board(
        me=player(active=body(119, 1, hp=40, max_hp=70),
                  bench=[body(DUNSPARCE, 2), body(MUNKIDORI, 3)], hand=[DARK_E]),
        them=player(own=False, active=body(119, 4, hp=70, max_hp=70)))
    dunsparce = board(
        me=player(active=body(119, 1, hp=40, max_hp=70),
                  bench=[body(DUNSPARCE, 2, energies=(DARKNESS,)), body(MUNKIDORI, 3)]),
        them=player(own=False, active=body(119, 4, hp=70, max_hp=70)))
    munkidori = board(
        me=player(active=body(119, 1, hp=40, max_hp=70),
                  bench=[body(DUNSPARCE, 2), body(MUNKIDORI, 3, energies=(DARKNESS,))]),
        them=player(own=False, active=body(119, 4, hp=70, max_hp=70)))

    context = EvaluationModel.build()
    assert value(munkidori, context) - value(before, context) \
        > value(dunsparce, context) - value(before, context) + 0.05


def test_discarded_energy_has_more_value_when_retrieval_is_available():
    empty = board(me=player(active=body(119, 1)))
    stranded = board(me=player(active=body(119, 1), discard=[FIRE_E]))
    retrieval = board(me=player(active=body(119, 1), hand=[ENERGY_RETRIEVAL]))
    recoverable = board(me=player(active=body(119, 1), hand=[ENERGY_RETRIEVAL],
                               discard=[FIRE_E]))

    assert value(recoverable) - value(retrieval) > value(stranded) - value(empty) + 0.02


def test_opponent_hidden_zones_are_board_liabilities():
    thin = board(them=player(own=False, hand_count=1, deck_count=5))
    deep = board(them=player(own=False, hand_count=7, deck_count=30))
    valuation = evaluate(deep, EvaluationModel.build())

    assert value(thin) > value(deep)
    assert any(item.feature == "resource.opponent_hidden_option" and item.value < 0
               for item in valuation.activations)
    assert any(item.feature == "resource.opponent_hidden_deck" and item.value < 0
               for item in valuation.activations)


def test_known_valuable_prize_is_an_explicit_locked_option():
    unknown = board(me=player(active=body(119, 1)))
    printed = printout(me=player(active=body(119, 1)))
    printed["own_prizes"] = {str(LILLIES): 1}
    locked = ObservationStateBuilder().root(printed)
    valuation = evaluate(locked, EvaluationModel.build())

    assert value(unknown) > valuation.total
    assert any(item.feature == "resource.prize_locked" and item.value > 0
               for item in valuation.activations)


def test_basic_pokemon_option_includes_its_complete_evolution_line():
    state = board(me=player(active=body(DUNSPARCE, 1)))
    context = EvaluationModel.build()

    assert card_option_value(context.facts(119), state.me, state.them, state, context) \
        > card_option_value(context.facts(DUNSPARCE), state.me, state.them, state, context)


def test_energy_option_has_diminishing_value_for_interchangeable_hand_copies():
    one = board(me=player(active=body(119, 1), hand=[FIRE_E]))
    two = board(me=player(active=body(119, 1), hand=[FIRE_E, FIRE_E]))
    context = EvaluationModel.build()
    facts = context.facts(FIRE_E)

    assert card_option_value(facts, one.me, one.them, one, context) \
        > card_option_value(facts, two.me, two.them, two, context)


def test_spent_supporter_allowance_discounts_instead_of_erasing_next_turn_option():
    printed = printout(me=player(active=body(119, 1), hand=[LILLIES]))
    printed["current"]["supporterPlayed"] = True
    state = ObservationStateBuilder().root(printed)
    context = EvaluationModel.build()

    assert card_option_value(
        context.facts(LILLIES), state.me, state.them, state, context) > 0
