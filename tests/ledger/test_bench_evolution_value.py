from __future__ import annotations

from dataclasses import replace

from ledger_helpers import (DRAGAPULT, DRAKLOAK, DREEPY, LUNATONE, MAKUHITA,
                            body, player, printout)

from common.ledger import EvaluationModel, evaluate
from common.observation import ObservationStateBuilder


SOLROCK = 676
BUDEW = 235
MUNKIDORI = 112


def board(**kwargs):
    return ObservationStateBuilder().root(printout(**kwargs))


def activation(state, feature):
    return next((item.value for item in evaluate(
        state, EvaluationModel.build()).activations if item.feature == feature), 0.0)


def full_bench():
    return [body(MAKUHITA, 10 + index) for index in range(5)]


def test_full_bench_pressure_does_not_revalue_blocked_cards_outside_the_portfolio():
    wincon_blocked = board(me=player(
        active=body(DRAGAPULT, 1), bench=full_bench(), hand=[DREEPY]))
    filler_blocked = board(me=player(
        active=body(DRAGAPULT, 1), bench=full_bench(), hand=[LUNATONE]))

    assert activation(wincon_blocked, "bench.full") == activation(
        filler_blocked, "bench.full")


def test_live_wincon_in_the_last_slot_beats_redundant_occupancy():
    occupied = [body(MAKUHITA, 10 + index) for index in range(4)]
    wincon = board(me=player(
        active=body(DRAGAPULT, 1), bench=[*occupied, body(DREEPY, 20)],
        hand=[LUNATONE]))
    redundant = board(me=player(
        active=body(DRAGAPULT, 1), bench=[*occupied, body(LUNATONE, 20)],
        hand=[DREEPY]))
    context = EvaluationModel.build()

    assert evaluate(wincon, context).total > evaluate(redundant, context).total


def test_deck_only_base_needs_an_open_bench_route_for_evolution_setup():
    open_route = replace(board(me=player(
        active=body(MAKUHITA, 1), bench=full_bench()[:-1], hand=[DRAKLOAK])),
        deck_counts=((DREEPY, 1),))
    blocked_route = replace(board(me=player(
        active=body(MAKUHITA, 1), bench=full_bench(), hand=[DRAKLOAK])),
        deck_counts=((DREEPY, 1),))

    assert activation(open_route, "demand.setup") == 1
    assert activation(blocked_route, "demand.setup") == 0
    assert activation(blocked_route, "demand.dead") == 1


def test_mature_matching_base_keeps_evolution_live_on_a_full_bench():
    state = board(me=player(
        active=body(DREEPY, 1), bench=full_bench(), hand=[DRAKLOAK]))

    assert activation(state, "demand.setup") == 0
    assert activation(state, "demand.dead") == 0
    assert activation(state, "development.ready_evolution") == 1


def test_duplicate_evolutions_share_one_ready_target():
    state = replace(board(me=player(
        active=body(DREEPY, 1), hand=[DRAKLOAK, DRAKLOAK, DRAKLOAK])),
        deck_counts=((DREEPY, 4), (DRAKLOAK, 4), (DRAGAPULT, 3)))

    assert activation(state, "development.ready_evolution") == 1


def test_newly_appeared_matching_base_is_setup_not_ready():
    appeared = {**body(DREEPY, 1), "appearThisTurn": True}
    state = board(me=player(
        active=appeared, bench=full_bench(), hand=[DRAKLOAK]))

    assert activation(state, "demand.setup") == 1
    assert activation(state, "demand.dead") == 0
    assert activation(state, "development.ready_evolution") == 0


def test_stage_one_in_hand_is_not_a_deployable_stage_two_base():
    stranded = board(me=player(
        active=body(MAKUHITA, 1), hand=[DRAKLOAK, DRAGAPULT]))
    ready = board(me=player(
        active=body(DRAKLOAK, 1), hand=[DRAGAPULT]))

    assert activation(stranded, "demand.setup") == 0
    assert activation(stranded, "demand.dead") == 2
    assert activation(ready, "demand.dead") == 0
    assert activation(ready, "development.ready_evolution") > 0


def test_stage_two_in_hand_is_setup_when_stage_one_can_evolve_a_fielded_basic():
    routed = board(me=player(
        active=body(DREEPY, 1), hand=[DRAKLOAK, DRAGAPULT]))

    assert activation(routed, "demand.setup") == 1
    assert activation(routed, "demand.dead") == 0
    assert activation(routed, "development.ready_evolution") == 1


def test_third_terminal_basic_is_surplus_after_two_are_deployed():
    redundant = board(me=player(
        active=body(SOLROCK, 1), bench=[body(SOLROCK, 2)], hand=[SOLROCK]))

    assert activation(redundant, "copy.surplus") == 1
