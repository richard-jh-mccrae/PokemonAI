from dataclasses import replace

from ledger_helpers import (DARK_E, DARKNESS, DRAGAPULT, DRAKLOAK, DREEPY, FIRE, FIRE_E,
                            IGNITION, MEGA_STARMIE, STARYU, body, player, printout)

from common.ledger import EvaluationModel, evaluate
from common.ledger.capabilities import OptionUnits
from common.ledger.portfolio import feasible_option_portfolio_result
from common.ledger.worth import payoff_usable_units
from common.observation import ObservationStateBuilder


MUNKIDORI = 112
DUNSPARCE = 65
ULTRA_BALL = 1121
ENERGY_RETRIEVAL = 1118
NIGHT_STRETCHER = 1097
DUDUNSPARCE = 66


def board(**kwargs):
    return ObservationStateBuilder().root(printout(**kwargs))


def value(state, context):
    return evaluate(state, context).total


def activation(state, feature, context):
    return sum(item.value for item in evaluate(state, context).activations
               if item.feature == feature)


def test_multi_provision_energy_is_live_for_a_reachable_evolution_line():
    context = EvaluationModel.build()
    state = replace(
        board(me=player(active=body(STARYU, 1), hand=[IGNITION])),
        deck_counts=((MEGA_STARMIE, 1),))

    assert activation(state, "demand.dead", context) == 0
    assert activation(state, "interaction.kind.special_energy.in_hand_setup", context) == 1


def portfolio_search(hand, deck_card):
    context = EvaluationModel.build()
    state = replace(
        board(me=player(active=body(DUNSPARCE, 1), hand=hand)),
        deck_counts=((deck_card, 1),))
    result = feasible_option_portfolio_result(
        [(context.facts(ULTRA_BALL), OptionUnits(search=1))],
        state.me, state, context, hand_size=len(hand))
    return result.units.search


def test_scarce_fire_attachment_beats_generic_colorless_absorption():
    context = EvaluationModel.build()
    before = board(me=player(
        active=body(DREEPY, 1), bench=[body(MUNKIDORI, 2)], hand=[FIRE_E]))
    typed = board(me=player(
        active=body(DREEPY, 1, energies=(FIRE,)), bench=[body(MUNKIDORI, 2)]))
    generic = board(me=player(
        active=body(DREEPY, 1), bench=[body(MUNKIDORI, 2, energies=(FIRE,))]))

    assert value(typed, context) - value(before, context) \
        > value(generic, context) - value(before, context) + 0.05


def test_unmet_typed_cost_blocks_premature_colorless_absorption():
    context = EvaluationModel.build()

    assert payoff_usable_units(context.facts(MUNKIDORI), (FIRE,), context) == 0
    assert payoff_usable_units(context.facts(DREEPY), (FIRE,), context) == 1

    generic = board(me=player(
        active=body(MUNKIDORI, 1, energies=(FIRE,)), bench=[body(DREEPY, 2)]))
    typed = board(me=player(
        active=body(MUNKIDORI, 1), bench=[body(DREEPY, 2, energies=(FIRE,))]))
    assert value(typed, context) > value(generic, context) + 0.05


def test_attachment_builds_the_line_payoff_not_its_cheaper_attack():
    context = EvaluationModel.build()
    before = replace(
        board(me=player(active=body(DRAKLOAK, 1), hand=[DARK_E])),
        deck_counts=((DRAGAPULT, 1),))
    dark = replace(
        board(me=player(active=body(DRAKLOAK, 1, energies=(DARKNESS,)))),
        deck_counts=((DRAGAPULT, 1),))
    fire = replace(
        board(me=player(active=body(DRAKLOAK, 1, energies=(FIRE,)))),
        deck_counts=((DRAGAPULT, 1),))

    assert value(dark, context) < value(before, context)
    assert value(fire, context) > value(before, context)


def test_fetch_cannot_discard_its_only_condition_energy():
    assert portfolio_search([ULTRA_BALL, DARK_E, DUNSPARCE], MUNKIDORI) == 0


def test_fetch_can_discard_a_duplicate_condition_energy():
    assert portfolio_search(
        [ULTRA_BALL, DARK_E, DARK_E, DUNSPARCE], MUNKIDORI) == 1


def test_fetch_cannot_discard_its_only_evolution_base():
    assert portfolio_search([ULTRA_BALL, DREEPY, DUNSPARCE], DRAKLOAK) == 0


def test_recovery_target_quality_is_owned_by_the_successor_state():
    context = EvaluationModel.build()
    state = board(me=player(
        active=body(DREEPY, 1), hand=[NIGHT_STRETCHER, DUDUNSPARCE],
        discard=[DUNSPARCE]))

    result = feasible_option_portfolio_result(
        [(context.facts(NIGHT_STRETCHER), OptionUnits(search=1))],
        state.me, state, context, hand_size=2)

    assert result.units.search == 1


def test_evolution_option_survives_when_its_parent_just_entered_play():
    context = EvaluationModel.build()
    fielded = body(DUNSPARCE, 1)
    fielded["appearThisTurn"] = True
    before = board(me=player(
        active=body(DREEPY, 2), hand=[DUNSPARCE, DUDUNSPARCE]))
    after = board(me=player(
        active=body(DREEPY, 2), bench=[fielded], hand=[DUDUNSPARCE]))

    def available_draw(state):
        return sum(item.activation for item in evaluate(state, context).contributions
                   if item.feature == "option.draw")

    assert available_draw(after) > 0


def test_duplicate_energy_has_lower_discard_opportunity_cost():
    context = EvaluationModel.build()
    empty = board(me=player(active=body(DREEPY, 1)))
    one = board(me=player(active=body(DREEPY, 1), hand=[FIRE_E]))
    two = board(me=player(active=body(DREEPY, 1), hand=[FIRE_E, FIRE_E]))

    assert value(one, context) - value(empty, context) \
        > value(two, context) - value(one, context)


def test_recovery_capacity_reduces_discard_opportunity_cost():
    context = EvaluationModel.build()
    empty = board(me=player(active=body(DREEPY, 1)))
    stranded = board(me=player(active=body(DREEPY, 1), discard=[FIRE_E]))
    retrieval = board(me=player(
        active=body(DREEPY, 1), hand=[ENERGY_RETRIEVAL]))
    recoverable = board(me=player(
        active=body(DREEPY, 1), hand=[ENERGY_RETRIEVAL], discard=[FIRE_E]))

    assert value(recoverable, context) - value(retrieval, context) \
        > value(stranded, context) - value(empty, context)
