"""Opponent valuation consumes the complete posterior, not a matched posture."""
from __future__ import annotations

import pytest

from ledger_helpers import DRAGAPULT, body, player, printout

from common.observation import LegalKnowledge, ObservationStateBuilder, OpponentBelief
from common.ledger import DeckOverlay, EvaluationModel, OpponentProfile, evaluate
from common.opponent import ArchetypeBelief, OpponentEvidence, OpponentSnapshot

UNKNOWN_ID = 424242


def _activation(valuation, feature):
    return next(item.value for item in valuation.activations if item.feature == feature)


def _snapshot(*, observed_roles=None, candidates=(), unknown_mass=1.0):
    state = ObservationStateBuilder().root(printout())
    return OpponentSnapshot(
        OpponentEvidence.from_state(state), observed_roles or {}, candidates, unknown_mass)


def _profiles(snapshot):
    return {candidate.archetype: OpponentProfile(
        candidate.roles, candidate.traits, candidate.mechanics, candidate.resources)
            for candidate in snapshot.candidates}


def _board(observation, snapshot):
    knowledge = LegalKnowledge(opponent=OpponentBelief.from_snapshot(snapshot))
    return ObservationStateBuilder().root(observation, knowledge=knowledge)


def test_compiled_snapshot_roles_do_not_enter_board_value():
    beliefs = _snapshot(
        observed_roles={UNKNOWN_ID: ("support_pokemon",)},
        candidates=(ArchetypeBelief(
            0.5, {UNKNOWN_ID: ("primary_attacker",)}, archetype="candidate"),),
        unknown_mass=0.5,
    )
    context = EvaluationModel.build(
        opponent_profiles=_profiles(beliefs))
    valuation = evaluate(_board(printout(
        them=player(own=False, active=body(UNKNOWN_ID, 1))), beliefs), context)

    assert not any(item.feature.startswith("role.") for item in valuation.activations)
    assert _activation(valuation, "coverage.unknown_card") > 0
    assert next(item.value for item in valuation.contributions
                if item.feature == "coverage.unknown_card") < 0
    assert any("unknown card" in gap for gap in valuation.gaps)


def test_opponent_role_evidence_cannot_create_valuation_contributions():
    beliefs = _snapshot(
        candidates=(ArchetypeBelief(
            1.0, {UNKNOWN_ID: ("primary_attacker",)}, archetype="candidate"),),
        unknown_mass=0.0,
    )
    context = EvaluationModel.build(opponent_profiles=_profiles(beliefs))
    valuation = evaluate(_board(printout(
        them=player(own=False, active=body(UNKNOWN_ID, 1))), beliefs), context)
    assert not any(item.feature.startswith("role.") for item in valuation.contributions)


def test_our_evaluation_model_has_no_role_values_for_opponent_cards():
    context = EvaluationModel.build()
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
    expected_board = _board(printout(
        them=player(own=False, active=body(1030, 1, energies=(3,)))), beliefs)
    expected = evaluate(expected_board, EvaluationModel.build(
        opponent_profiles=_profiles(beliefs)))

    assert not any(item.feature == "development.next_turn_reach"
                   for item in absent.activations)
    assert _activation(expected, "development.next_turn_reach") < 0


def test_missing_static_opponent_profile_is_explicitly_estimated():
    beliefs = _snapshot(candidates=(ArchetypeBelief(
        1.0, archetype="missing-profile"),), unknown_mass=0.0)

    valuation = evaluate(_board(printout(), beliefs), EvaluationModel.build())

    assert "missing opponent profile: missing-profile" in valuation.gaps
