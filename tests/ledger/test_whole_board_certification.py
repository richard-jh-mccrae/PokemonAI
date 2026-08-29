from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ledger_helpers import (AIR_BALLOON, DARKNESS, DARK_E, DRAKLOAK, DRAGAPULT, DREEPY,
                            body, player, printout)

from common.decision import EvaluationRequest
from common.ledger import DeckOverlay, EvaluationModel
from common.ledger.certification import certify_contract, certify_incremental
from common.ledger.decision import LedgerValueEvaluator
from common.ledger.evaluate import evaluate_snapshot
from common.observation import (LegalKnowledge, ObservationDelta, ObservationStateBuilder,
                                OpponentBelief)
from common.observation.knowledge import (KnownDeckTop, OpponentCandidatePosterior,
                                          OpponentDecisionEvidence)
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


def test_incremental_shadow_invalidates_public_events():
    builder = ObservationStateBuilder()
    parent_raw = printout(me=player(active=body(226, 1)))
    child_raw = printout(me=player(active=body(226, 1)))
    child_raw["logs"] = [{"type": 15, "cardId": 62, "playerIndex": 0}]
    parent = builder.root(parent_raw)
    child, delta = builder.advance(parent, child_raw)

    report = certify_incremental(parent, child, delta, EvaluationModel.build())

    assert ("events",) in delta.parts
    assert report.incremental_parity is True


def test_incremental_shadow_invalidates_opponent_belief():
    builder = ObservationStateBuilder()
    raw = printout(me=player(active=body(DRAGAPULT, 1)))
    parent = builder.root(raw)
    evidence = OpponentDecisionEvidence(
        "probe", (OpponentCandidatePosterior("missing", "1.0"),), (), (),
        (0, 0, 0, 0, 0, 0), "0.0")
    knowledge = LegalKnowledge(opponent=OpponentBelief(decision_evidence=evidence))
    child, delta = builder.advance(parent, raw, knowledge=knowledge)

    report = certify_incremental(parent, child, delta, EvaluationModel.build())

    assert ("knowledge", "opponent_belief") in delta.parts
    assert report.incremental_parity is True


def _transition(parent_raw, update):
    child_raw = deepcopy(parent_raw)
    update(child_raw)
    return parent_raw, child_raw


BASE = printout(
    me=player(active=body(DREEPY, 1), hand=[DARK_E]),
    them=player(own=False, active=body(DREEPY, 2), hand_count=2))


TRANSITIONS = (
    ("own-zones", *_transition(BASE, lambda raw: raw["current"]["players"][0].update(
        hand=[], handCount=0,
        discard=[{"id": DARK_E, "serial": 800, "playerIndex": 0}]))),
    ("opponent-zones", *_transition(BASE, lambda raw: raw["current"]["players"][1].update(
        handCount=4, deckCount=28,
        discard=[{"id": DARK_E, "serial": 901, "playerIndex": 1}]))),
    ("active-stack", *_transition(BASE, lambda raw: raw["current"]["players"][0].update(
        active=[body(DRAKLOAK, 1, hp=80, energies=(DARKNESS,),
                     tools=(AIR_BALLOON,), under=(DREEPY,))], poisoned=True))),
    ("bench", *_transition(BASE, lambda raw: raw["current"]["players"][0].update(
        bench=[body(DREEPY, 3)]))),
    ("opponent-combat", *_transition(BASE, lambda raw: raw["current"]["players"][1].update(
        active=[body(DRAKLOAK, 2, hp=40, under=(DREEPY,))], confused=True))),
    ("prizes", *_transition(BASE, lambda raw: raw["current"]["players"][0].update(
        prize=[None] * 5))),
    ("turn-allowances", *_transition(BASE, lambda raw: raw["current"].update(
        supporterPlayed=True, stadiumPlayed=True, energyAttached=True, retreated=True))),
    ("terminal-result", *_transition(BASE, lambda raw: raw["current"].update(result=0))),
    ("stadium", *_transition(BASE, lambda raw: raw["current"].update(
        stadium=[{"id": 1248, "serial": 42, "playerIndex": 0}]))),
    ("events", *_transition(BASE, lambda raw: raw.update(
        logs=[{"type": 15, "cardId": DARK_E, "playerIndex": 0}]))),
)


@pytest.mark.parametrize("_name,parent_raw,child_raw", TRANSITIONS,
                         ids=[row[0] for row in TRANSITIONS])
def test_incremental_shadow_matches_full_across_transition_families(
        _name, parent_raw, child_raw):
    builder = ObservationStateBuilder()
    parent = builder.root(parent_raw)
    child, delta = builder.advance(parent, child_raw)

    assert delta.parts
    assert certify_incremental(
        parent, child, delta, EvaluationModel.build()).incremental_parity is True


def test_incremental_shadow_remains_exact_across_chained_reuse():
    builder = ObservationStateBuilder()
    parent = builder.root(BASE)
    attached_raw = deepcopy(BASE)
    attached_raw["current"]["players"][0] = player(
        active=body(DREEPY, 1, energies=(DARKNESS,)), hand=())
    attached, attached_delta = builder.advance(parent, attached_raw)
    retreated_raw = deepcopy(attached_raw)
    retreated_raw["current"]["players"][0] = player(
        active=body(DREEPY, 3), bench=(body(DREEPY, 1, energies=(DARKNESS,)),))
    retreated_raw["current"]["retreated"] = True
    retreated, retreated_delta = builder.advance(attached, retreated_raw)
    model = EvaluationModel.build()

    root = evaluate_snapshot(parent, model)
    attached_incremental = evaluate_snapshot(
        attached, model, parent=root, delta=attached_delta)
    retreated_incremental = evaluate_snapshot(
        retreated, model, parent=attached_incremental, delta=retreated_delta)

    assert retreated_incremental.valuation == evaluate_snapshot(retreated, model).valuation


def test_incremental_shadow_never_reuses_groups_across_models():
    builder = ObservationStateBuilder()
    parent = builder.root(BASE)
    child_raw = deepcopy(BASE)
    child_raw["current"]["players"][0] = player(
        active=body(DREEPY, 1, energies=(DARKNESS,)), hand=())
    child, delta = builder.advance(parent, child_raw)
    first_model = EvaluationModel.build()
    second_model = EvaluationModel.build(
        overlay=DeckOverlay({"kind.energy": 7.0}))

    incremental = evaluate_snapshot(
        child, second_model, parent=evaluate_snapshot(parent, first_model), delta=delta)

    assert incremental.reused_groups == ()
    assert incremental.valuation == evaluate_snapshot(child, second_model).valuation


def test_runtime_incremental_shadow_compares_the_complete_valuation(monkeypatch):
    builder = ObservationStateBuilder()
    parent = builder.root(BASE)
    child_raw = deepcopy(BASE)
    child_raw["current"]["players"][0].update(hand=[], handCount=0)
    child, delta = builder.advance(parent, child_raw)
    model = EvaluationModel.build()
    snapshot = evaluate_snapshot(parent, model)
    groups = dict(snapshot.groups)
    groups["context"] = replace(
        groups["context"], parts=(*groups["context"].parts, ("corrupt", 0.0)))
    corrupt = replace(snapshot, groups=tuple(groups.items()))
    monkeypatch.setenv("LEDGER_INCREMENTAL_PARITY", "1")

    with pytest.raises(AssertionError, match="differs from full"):
        LedgerValueEvaluator().evaluate_with_state(
            EvaluationRequest(child, model, observation_delta=delta), corrupt)
