from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from ledger_helpers import DARKNESS, DRAGAPULT, body, player, printout

from common.ledger import EvaluationModel
from common.ledger.certification import certify_contract, certify_incremental
from common.observation import ObservationDelta, ObservationStateBuilder
from common.observation.knowledge import KnownDeckTop
from common.observation.nodes import Card


def test_whole_board_static_contract_passes():
    report = certify_contract()

    assert report.passed


def test_incremental_shadow_is_exact_after_an_attachment():
    builder = ObservationStateBuilder()
    parent = builder.root(printout(me=player(active=body(DRAGAPULT, 1))))
    child, delta = builder.advance(parent, printout(
        me=player(active=body(DRAGAPULT, 1, energies=(DARKNESS,)))))

    report = certify_incremental(parent, child, delta, EvaluationModel.build())

    assert report.passed
    assert report.incremental_parity is True


def test_incremental_shadow_invalidates_known_deck_top_value():
    parent = ObservationStateBuilder().root(
        printout(me=player(active=body(DRAGAPULT, 1))))
    child = replace(parent, knowledge=replace(
        parent.knowledge, known_top=KnownDeckTop(((41, 1121),))))
    delta = ObservationDelta((("knowledge", "deck_top"),))

    assert certify_incremental(
        parent, child, delta, EvaluationModel.build()).incremental_parity is True


def test_incremental_shadow_invalidates_valued_legal_action_count():
    parent = ObservationStateBuilder().root(
        printout(me=player(active=body(DRAGAPULT, 1))))
    parent = replace(parent, stadium=(Card(1248, 42, parent.seat),))
    action = SimpleNamespace(identity=SimpleNamespace(kind="probe", parts=()))
    child = replace(parent, legal_actions=(action,))
    delta = ObservationDelta((("legal_actions",),))

    assert certify_incremental(
        parent, child, delta, EvaluationModel.build()).incremental_parity is True
