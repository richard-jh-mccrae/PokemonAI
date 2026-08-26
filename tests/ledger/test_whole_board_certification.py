from __future__ import annotations

from ledger_helpers import DARKNESS, DRAGAPULT, body, player, printout

from common.ledger import EvaluationModel
from common.ledger.certification import certify_contract, certify_incremental
from common.observation import ObservationStateBuilder


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
