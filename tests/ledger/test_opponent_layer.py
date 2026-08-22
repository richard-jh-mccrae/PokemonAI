"""Opponent valuation consumes the complete posterior, not a matched posture."""
from __future__ import annotations

import pytest

from ledger_helpers import DRAGAPULT, body, player, printout

from common.observation import ObservationStateBuilder
from common.ledger import DeckOverlay, EvaluationModel, evaluate
from common.opponent import ArchetypeBelief, OpponentEvidence, OpponentSnapshot

UNKNOWN_ID = 424242


def _activation(valuation, feature):
    return next(item.value for item in valuation.activations if item.feature == feature)


def _snapshot(*, observed_roles=None, candidates=(), unknown_mass=1.0):
    state = ObservationStateBuilder().root(printout())
    return OpponentSnapshot(
        OpponentEvidence.from_state(state), observed_roles or {}, candidates, unknown_mass)


def test_observed_claims_activate_fully_and_candidates_by_probability():
    beliefs = _snapshot(
        observed_roles={UNKNOWN_ID: ("support_pokemon",)},
        candidates=(ArchetypeBelief(
            0.5, {UNKNOWN_ID: ("primary_attacker",)}, archetype="candidate"),),
        unknown_mass=0.5,
    )
    context = EvaluationModel.build().with_opponent(beliefs)
    valuation = evaluate(ObservationStateBuilder().root(printout(
        them=player(own=False, active=body(UNKNOWN_ID, 1)))), context)

    assert _activation(valuation, "role.support_pokemon") == -1.0
    assert _activation(valuation, "role.primary_attacker") == -0.5
    assert _activation(valuation, "coverage.unknown_card") < 0
    assert any("unknown card" in gap for gap in valuation.gaps)


def test_opponent_evidence_cannot_change_valuation_coefficients():
    beliefs = _snapshot(
        candidates=(ArchetypeBelief(
            1.0, {UNKNOWN_ID: ("primary_attacker",)}, archetype="candidate"),),
        unknown_mass=0.0,
    )
    context = EvaluationModel.build(
        overlay=DeckOverlay({"role.primary_attacker": 0.4})).with_opponent(beliefs)
    valuation = evaluate(ObservationStateBuilder().root(printout(
        them=player(own=False, active=body(UNKNOWN_ID, 1)))), context)
    contribution = next(item for item in valuation.contributions
                        if item.feature == "role.primary_attacker")

    assert contribution.coefficient == pytest.approx(0.9)
    assert contribution.value == pytest.approx(-0.9)


def test_our_deck_role_declarations_do_not_leak_onto_opponent_cards():
    context = EvaluationModel.build(roles={DRAGAPULT: ("healer",)})
    valuation = evaluate(ObservationStateBuilder().root(printout(
        them=player(own=False, active=body(DRAGAPULT, 1)))), context)

    assert not any(item.feature == "role.healer" for item in valuation.activations)


def test_special_energy_prices_through_its_kind_feature():
    context = EvaluationModel.build(
        overlay=DeckOverlay({"kind.special_energy": 0.37}))
    valuation = evaluate(ObservationStateBuilder().root(printout(me=player(hand=[17]))), context)
    contribution = next(item for item in valuation.contributions
                        if item.feature == "kind.special_energy")

    assert contribution.activation == 1.0
    assert contribution.coefficient == pytest.approx(0.42)


def test_opponent_development_reach_is_candidate_resource_conditioned():
    board = ObservationStateBuilder().root(printout(
        them=player(own=False, active=body(1030, 1, energies=(3,)))))
    absent = evaluate(board, EvaluationModel.build())
    beliefs = _snapshot(candidates=(ArchetypeBelief(
        1.0, archetype="starmie", resources={1031: 1.0}),), unknown_mass=0.0)
    expected = evaluate(board, EvaluationModel.build().with_opponent(beliefs))

    assert not any(item.feature == "development.next_turn_reach"
                   for item in absent.activations)
    assert _activation(expected, "development.next_turn_reach") < 0
