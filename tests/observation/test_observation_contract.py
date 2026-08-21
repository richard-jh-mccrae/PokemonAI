from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError

import pytest

from common.observation import (
    HiddenHand,
    KnownAttackLocks,
    KnownDeckTop,
    KnownOwnPrizes,
    LegalKnowledge,
    ObservationConstructionError,
    ObservationRecord,
    ObservationStateBuilder,
    OpponentBelief,
    UnknownAttackLocks,
    UnknownDeckTop,
    UnknownOwnPrizes,
    VisibleHand,
)


DECK = (66,) * 3 + (112,) * 2 + (119,) * 4 + (120,) * 2


def body(card_id, serial):
    return {"id": card_id, "serial": serial, "playerIndex": 0, "hp": 100,
            "maxHp": 100, "appearThisTurn": False, "energies": [],
            "energyCards": [], "tools": [], "preEvolution": []}


def player(*, active=None, hand=(), own=True, hand_count=None):
    cards = [{"id": card_id, "serial": 800 + index, "playerIndex": 0}
             for index, card_id in enumerate(hand)]
    return {"active": [active] if active else [], "bench": [], "benchMax": 5,
            "deckCount": 10, "prize": [None] * 3, "discard": [],
            "handCount": len(hand) if hand_count is None else hand_count,
            "hand": cards if own else None, "poisoned": False, "burned": False,
            "asleep": False, "paralyzed": False, "confused": False}


def printout(*, me=None, them=None, select=None):
    return {"select": select, "logs": [], "current": {
        "turn": 2, "yourIndex": 0, "firstPlayer": 0, "supporterPlayed": False,
        "stadiumPlayed": False, "energyAttached": False, "retreated": False,
        "result": None, "stadium": [], "looking": None,
        "players": [me or player(), them or player(own=False)]}}


def _prompt(options):
    return {
        "type": 1,
        "context": 0,
        "minCount": 1,
        "maxCount": 1,
        "remainDamageCounter": 0,
        "remainEnergyCost": 0,
        "option": options,
        "deck": None,
        "contextCard": None,
        "effect": None,
    }


def test_builder_produces_deeply_immutable_hidden_safe_state():
    hostile = player(own=False, hand_count=1)
    hostile["hand"] = [{"id": 66, "serial": 900, "playerIndex": 1}]
    hostile["deck"] = [{"id": 112, "serial": 901, "playerIndex": 1}]
    state = ObservationStateBuilder(DECK).root(printout(
        me=player(hand=[119]), them=hostile))

    assert isinstance(state.me.hand, VisibleHand)
    assert isinstance(state.them.hand, HiddenHand)
    assert state.them.hand.count == 1
    assert not hasattr(state, "raw") and not hasattr(state, "digests")
    with pytest.raises(FrozenInstanceError):
        state.seat = 1
    with pytest.raises(AttributeError):
        state.me.hand.cards.append(66)


def test_knowledge_variants_copy_mutable_inputs():
    source = []
    knowledge = LegalKnowledge(own_prizes=KnownOwnPrizes(source))
    source.append((66, 1))

    assert knowledge.own_prizes.cards == ()
    with pytest.raises(TypeError, match="OpponentBelief"):
        LegalKnowledge(opponent={})


def test_builder_rejects_missing_required_zone_scalar():
    raw = printout()
    del raw["current"]["players"][0]["deckCount"]

    with pytest.raises(ObservationConstructionError, match="deckCount"):
        ObservationStateBuilder().root(raw)


def test_position_key_excludes_question_while_decision_key_includes_canonical_menu():
    first = printout(select=_prompt([{"type": 7, "index": 0}]))
    second = copy.deepcopy(first)
    second["select"]["option"].append({"type": 7, "index": 1})

    a = ObservationStateBuilder().root(first)
    b = ObservationStateBuilder().root(second)

    assert a.position_key == b.position_key
    assert a.decision_key != b.decision_key
    assert a.legal_actions
    assert tuple(action.identity for action in a.legal_actions) == tuple(
        sorted(action.identity for action in a.legal_actions))


def test_advance_returns_parent_relative_typed_delta_and_reuses_nodes():
    initial = printout(me=player(active=body(66, 1), hand=[119]))
    builder = ObservationStateBuilder(DECK)
    root = builder.root(initial)
    successor = copy.deepcopy(initial)
    successor["current"]["players"][0]["active"][0]["hp"] = 40

    child, delta = builder.advance(root, successor)

    assert delta.parts == (("me", "active"),)
    assert child.me.hand is root.me.hand
    assert not hasattr(child, "changed")


def test_record_round_trip_preserves_keys_without_tracking_serial_identity():
    initial = printout(me=player(active=body(66, 1), hand=[119]),
                       select=_prompt([{"type": 7, "index": 0}]))
    state = ObservationStateBuilder(DECK).root(initial)
    record = ObservationRecord.from_state(state)
    restored = ObservationRecord.loads(record.dumps()).to_state()

    assert restored == state
    assert restored.position_key == state.position_key
    assert restored.decision_key == state.decision_key
    assert record.schema_version == 1


def test_tracking_serials_do_not_change_keys_but_lock_consequences_do():
    initial = printout(me=player(active=body(66, 1)))
    renumbered = copy.deepcopy(initial)
    renumbered["current"]["players"][0]["active"][0]["serial"] = 99
    a = ObservationStateBuilder().root(initial)
    b = ObservationStateBuilder().root(renumbered)
    assert a.position_key == b.position_key

    locked_a = ObservationStateBuilder().root(
        initial, knowledge=LegalKnowledge(
            attack_locks=KnownAttackLocks((("1", (("983", 4),)),))))
    locked_b = ObservationStateBuilder().root(
        renumbered, knowledge=LegalKnowledge(
            attack_locks=KnownAttackLocks((("99", (("983", 4),)),))))
    assert locked_a.position_key == locked_b.position_key
    assert locked_a.position_key != a.position_key


def test_opponent_belief_is_fixed_point_validated_and_changes_position_key():
    raw = printout()
    plain = ObservationStateBuilder().root(raw)
    informed = ObservationStateBuilder().root(raw, knowledge=LegalKnowledge(
        opponent=OpponentBelief(evidence=(("seen", {"cards": [66]}),),
                                probabilities=((66, 250_000),))))

    assert informed.position_key != plain.position_key
    assert informed.knowledge.opponent.evidence == (("seen", (("cards", (66,)),)),)
    with pytest.raises(ValueError, match="fixed-point"):
        OpponentBelief(probabilities=((66, 1_000_001),))


def test_unknown_future_event_fails_closed_without_retaining_payload():
    raw = printout(me=player(hand=[119]))
    raw["logs"] = [{"type": 999, "playerIndex": 0, "deck": [{"id": 777_777}],
                    "privateFutureField": "discarded"}]
    state = ObservationStateBuilder().root(raw, knowledge=LegalKnowledge(
        own_prizes=KnownOwnPrizes(((66, 2),)),
        known_top=KnownDeckTop(((41, 119),)),
        attack_locks=KnownAttackLocks((("1", (("983", 4),)),))))

    assert isinstance(state.knowledge.own_prizes, UnknownOwnPrizes)
    assert isinstance(state.knowledge.known_top, UnknownDeckTop)
    assert isinstance(state.knowledge.attack_locks, UnknownAttackLocks)
    assert state.events[0].recognized is False
    assert "privateFutureField" not in dict(state.events[0].public_fields)
    assert "777777" not in ObservationRecord.from_state(state).dumps()


def test_record_strips_unknown_nested_provider_fields_and_known_event_fields():
    raw = printout(me=player(active=body(66, 1)))
    raw["current"]["players"][0]["active"][0]["private"] = {"deck": [777_777]}
    raw["logs"] = [{"type": 4, "playerIndex": 0,
                    "privateFutureField": {"deck": [777_777]}}]

    encoded = ObservationRecord.from_state(ObservationStateBuilder().root(raw)).dumps()

    assert "private" not in encoded
    assert "777777" not in encoded


def test_record_decoder_rejects_opponent_visible_hand():
    state = ObservationStateBuilder().root(printout())
    record = ObservationRecord.from_state(state)
    payload = copy.deepcopy(record.payload)
    fields = payload["fields"]
    fields["them"]["fields"]["hand"] = fields["me"]["fields"]["hand"]

    with pytest.raises(ValueError, match="opponent hand"):
        ObservationRecord(record.schema_version, payload).to_state()
