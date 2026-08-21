from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import copy
import json

import pytest

from common.opponent import OpponentEvidence, OpponentKnowledgeBase, OpponentModel
from common.scouting.artifact import Artifact
from common.scouting.briefs import Brief
from common.scouting.provider import CardStat, DictCardStatProvider
from common.api import RootDecision
from common.telemetry import to_record
from common.observation import ObservationStateBuilder
from ledger_helpers import player, printout
from scouting_helpers import MEGA_LUCARIO, RIOLU, SOLROCK, make_obs, tiny_artifact


def _provider():
    return DictCardStatProvider({
        MEGA_LUCARIO: CardStat(
            MEGA_LUCARIO, name="Mega Lucario ex", hp=220, megaEx=True, maxDamage=270),
        RIOLU: CardStat(RIOLU, name="Riolu", hp=70, maxDamage=20),
        SOLROCK: CardStat(SOLROCK, name="Solrock", hp=90, maxDamage=30),
    })


def test_model_emits_one_immutable_full_posterior_snapshot():
    provider = _provider()
    knowledge = OpponentKnowledgeBase.compile(tiny_artifact(), (), provider)
    model = OpponentModel(knowledge, provider=provider)

    snapshot = model.update(OpponentEvidence.from_state(
        make_obs(opp_active=RIOLU, opp_bench=[SOLROCK])))

    assert snapshot.evidence.resources.hand_count == 0
    assert snapshot.candidates[0].archetype == "Mega Lucario ex"
    assert len(snapshot.candidates) == 2
    assert snapshot.unknown_mass + sum(
        candidate.probability for candidate in snapshot.candidates) == pytest.approx(1.0)
    assert snapshot.observed_roles[RIOLU] == ("support_pokemon", "primary_attacker")
    assert snapshot.identity
    with pytest.raises(FrozenInstanceError):
        snapshot.unknown_mass = 0.0


def test_knowledge_compiles_candidate_roles_traits_and_card_mechanics():
    budew, unfair_stamp = 235, 1080
    provider = DictCardStatProvider({
        budew: CardStat(budew, name="Budew", hp=30, maxDamage=10),
        unfair_stamp: CardStat(unfair_stamp, name="Unfair Stamp", cardType=1),
    })
    artifact = Artifact(
        priors={"Lock": 1.0},
        card_inclusion={"Lock": {budew: 0.8, unfair_stamp: 0.6}},
        background={budew: 0.1, unfair_stamp: 0.1},
    )
    brief = Brief(
        slug="lock", label="Lock", covers=["Lock"],
        traits={"tempo": "fast", "opening_fragility": True},
        pokemon=[{"card": "Budew", "roles": ["item_locker"]}],
    )
    model = OpponentModel(OpponentKnowledgeBase.compile(
        artifact, (brief,), provider), provider=provider)

    candidate = model.update(OpponentEvidence.from_state(make_obs(
        opp_active=budew))).candidates[0]

    assert "item_locker" in candidate.roles[budew]
    assert {(trait.name, trait.value) for trait in candidate.traits} == {
        ("opening_fragility", True), ("tempo", "fast")}
    mechanics = {mechanic.name: mechanic.probability for mechanic in candidate.mechanics}
    assert mechanics["item_lock"] == 0.8
    assert mechanics["comeback_disruption"] == 0.6


def test_unknown_profile_claim_fails_at_knowledge_construction():
    brief = Brief(
        slug="bad", label="Bad", covers=["Mega Lucario ex"],
        traits={"typo": True})

    with pytest.raises(KeyError, match="unknown opponent Trait"):
        OpponentKnowledgeBase.compile(tiny_artifact(), (brief,), _provider())


def test_timeline_deduplicates_batches_and_keeps_current_and_previous_turns():
    model = OpponentModel(OpponentKnowledgeBase.compile(
        tiny_artifact(), (), _provider()), provider=_provider())
    turn_two = OpponentEvidence.from_state(make_obs(
        turn=2, logs=[{"type": 4, "playerIndex": 1, "cardId": RIOLU}]))

    first = model.update(turn_two)
    duplicate = model.update(turn_two)
    turn_three = model.update(replace(
        turn_two, turn=3,
        resources=replace(turn_two.resources, hand_count=2),
        events=OpponentEvidence.from_state(make_obs(
            turn=3, logs=[{"type": 6, "playerIndex": 1,
                           "cardId": SOLROCK}])).events))
    turn_four = model.update(replace(turn_two, turn=4, events=()))

    assert len(first.timeline) == len(duplicate.timeline) == 1
    assert tuple(event.turn for event in turn_three.timeline) == (2, 3)
    assert turn_three.resource_delta.hand_count == 2
    assert tuple(event.turn for event in turn_four.timeline) == (3,)


def test_inference_failure_is_typed_degradation_and_strict_mode_reraises():
    def broken(*_args):
        raise RuntimeError("broken scorer")

    evidence = OpponentEvidence.from_state(make_obs(opp_active=RIOLU))
    knowledge = OpponentKnowledgeBase.compile(tiny_artifact(), (), _provider())
    degraded = OpponentModel(knowledge, provider=_provider(), scorer=broken).update(evidence)

    assert degraded.degraded
    assert degraded.failures == ("inference:RuntimeError",)
    assert degraded.evidence == evidence
    with pytest.raises(RuntimeError, match="broken scorer"):
        OpponentModel(knowledge, provider=_provider(), scorer=broken, strict=True).update(evidence)


def test_telemetry_adapter_consumes_the_snapshot_canonical_surface():
    model = OpponentModel(OpponentKnowledgeBase.compile(
        tiny_artifact(), (), _provider()), provider=_provider())
    snapshot = model.update(OpponentEvidence.from_state(make_obs(opp_active=RIOLU)))

    record = to_record(RootDecision((), None, 0.0, True, {}), opponent=snapshot)

    assert record["belief"]["identity"] == snapshot.identity
    assert record["belief"]["snapshot"]["unknown_mass"] == snapshot.unknown_mass
    assert "hand" not in record["belief"]["snapshot"]["evidence"]


def test_hidden_truth_cannot_change_evidence_snapshot_or_identity():
    legal = printout(them=player(own=False, hand_count=1))
    hostile = copy.deepcopy(legal)
    hostile["current"]["players"][1]["hand"] = [
        {"id": 777_777, "serial": 99, "playerIndex": 1}]
    legal_evidence = OpponentEvidence.from_state(ObservationStateBuilder().root(legal))
    hostile_evidence = OpponentEvidence.from_state(ObservationStateBuilder().root(hostile))
    knowledge = OpponentKnowledgeBase.compile(tiny_artifact(), (), _provider())

    legal_snapshot = OpponentModel(knowledge, provider=_provider()).update(legal_evidence)
    hostile_snapshot = OpponentModel(knowledge, provider=_provider()).update(hostile_evidence)

    assert hostile_evidence == legal_evidence
    assert hostile_snapshot.canonical_data() == legal_snapshot.canonical_data()
    assert hostile_snapshot.identity == legal_snapshot.identity
    assert "777777" not in json.dumps(hostile_snapshot.canonical_data())


def test_source_order_does_not_change_knowledge_or_snapshot_identity():
    artifact = tiny_artifact()
    reversed_artifact = Artifact(
        priors=dict(reversed(tuple(artifact.priors.items()))),
        card_inclusion={name: dict(reversed(tuple(cards.items())))
                        for name, cards in reversed(tuple(artifact.card_inclusion.items()))},
        background=dict(reversed(tuple(artifact.background.items()))),
        dossiers=artifact.dossiers,
    )
    first = OpponentKnowledgeBase.compile(artifact, (), _provider())
    second = OpponentKnowledgeBase.compile(reversed_artifact, (), _provider())
    evidence = OpponentEvidence.from_state(make_obs(opp_active=RIOLU))

    assert first.identity == second.identity
    assert (OpponentModel(first, provider=_provider()).update(evidence).identity
            == OpponentModel(second, provider=_provider()).update(evidence).identity)


@pytest.mark.parametrize(("mechanic", "cards"), (
    ("effect_immunity", {11: 1.0}),
    ("damage_cap", {158: 1.0}),
    ("piercing", {117: 1.0}),
    ("hand_size_attack", {743: 1.0}),
    ("single_prize", {158: 1.0}),
    ("special_energy_only", {11: 1.0}),
    ("no_pivot", {158: 1.0}),
    ("spread", {121: 1.0}),
    ("item_lock", {235: 1.0}),
    ("comeback_disruption", {1080: 1.0}),
))
def test_candidate_mechanics_derive_from_card_records(mechanic, cards):
    artifact = Artifact(
        priors={"candidate": 1.0}, card_inclusion={"candidate": cards},
        background={card_id: 0.1 for card_id in cards})
    knowledge = OpponentKnowledgeBase.compile(artifact, (), _provider())
    snapshot = OpponentModel(knowledge, provider=_provider()).update(
        OpponentEvidence.from_state(make_obs()))

    assert mechanic in {item.name for item in snapshot.candidates[0].mechanics}


def test_composition_and_absence_mechanics_have_negative_controls():
    artifact = Artifact(
        priors={"candidate": 1.0},
        card_inclusion={"candidate": {3: 1.0, 11: 1.0, 1174: 1.0, 121: 1.0}},
        background={3: 0.1, 11: 0.1, 1174: 0.1, 121: 0.1})
    knowledge = OpponentKnowledgeBase.compile(artifact, (), _provider())
    snapshot = OpponentModel(knowledge, provider=_provider()).update(
        OpponentEvidence.from_state(make_obs()))
    mechanics = {item.name for item in snapshot.candidates[0].mechanics}

    assert "special_energy_only" not in mechanics
    assert "single_prize" not in mechanics
    assert "no_pivot" not in mechanics


def test_candidate_bound_folds_omitted_probability_into_unknown_mass():
    artifact = Artifact(
        priors={f"candidate-{index}": 0.2 for index in range(5)},
        card_inclusion={f"candidate-{index}": {} for index in range(5)},
        background={})
    snapshot = OpponentModel(
        OpponentKnowledgeBase.compile(artifact, (), _provider()),
        provider=_provider(), candidate_limit=3).update(
            OpponentEvidence.from_state(make_obs()))

    assert len(snapshot.candidates) == 3
    assert snapshot.unknown_mass == pytest.approx(3 / 7)
