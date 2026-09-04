from dataclasses import replace

import pytest

from common.observation import DrawEvent, ObservationRecord, ObservationStateBuilder
from ledger_helpers import printout


@pytest.mark.parametrize("seat", (0, 1))
def test_unseen_opponent_draw_does_not_change_the_legal_record_or_keys(seat):
    views = []
    for card_id in (3, 6):
        raw = printout()
        raw["current"]["yourIndex"] = seat
        raw["logs"] = [{"type": 4, "playerIndex": 1 - seat,
                        "cardId": card_id, "serial": card_id + 90}]
        views.append(ObservationStateBuilder().root(raw))

    first, second = views
    assert first.events == (DrawEvent(5, (("playerIndex", 1 - seat),), True),)
    assert first == second
    assert first.position_key == second.position_key
    assert first.decision_key == second.decision_key
    assert first.valuation_key == second.valuation_key
    assert ObservationRecord.from_state(first).dumps() == ObservationRecord.from_state(second).dumps()


def test_focal_draw_and_public_opponent_play_keep_their_identity():
    raw = printout()
    raw["logs"] = [{"type": 4, "playerIndex": 0, "cardId": 3, "serial": 80},
                   {"type": 10, "playerIndex": 1, "cardId": 1121, "serial": 90}]
    view = ObservationStateBuilder().root(raw)

    assert dict(view.events[0].public_fields)["cardId"] == 3
    assert dict(view.events[1].public_fields)["cardId"] == 1121
    assert ObservationRecord.loads(ObservationRecord.from_state(view).dumps()).to_state() == view


def test_record_writer_rejects_a_typed_foreign_draw():
    view = ObservationStateBuilder().root(printout())
    hostile = replace(view, events=(DrawEvent(
        4, (("cardId", 3), ("playerIndex", 1), ("serial", 90)), True),))

    with pytest.raises(ValueError, match="event visibility"):
        ObservationRecord.from_state(hostile)


def test_record_reader_rejects_a_legacy_foreign_draw_without_rewriting_it():
    raw = printout()
    raw["logs"] = [{"type": 4, "playerIndex": 0, "cardId": 3, "serial": 90}]
    record = ObservationRecord.from_state(ObservationStateBuilder().root(raw))
    event_fields = record.payload["fields"]["events"]["$tuple"][0]["fields"]["public_fields"]["$tuple"]
    entry = next(row["$tuple"] for row in event_fields if row["$tuple"][0] == "playerIndex")
    entry[1] = 1
    encoded = record.dumps()
    with pytest.raises(ValueError, match="event visibility"):
        ObservationRecord.loads(encoded).to_state()
    assert record.dumps() == encoded


@pytest.mark.parametrize("kind", (5, 7, 90))
def test_reverse_and_unknown_events_do_not_retain_hostile_identity_fields(kind):
    raw = printout()
    raw["logs"] = [{"type": kind, "playerIndex": 1, "cardId": 6, "serial": 900,
                    "cardIdTarget": 3, "private": {"deck": [6]}}]
    view = ObservationStateBuilder().root(raw)
    assert not any(key.startswith("cardId") or key.startswith("serial")
                   for key, _ in view.events[0].public_fields)
    assert "900" not in ObservationRecord.from_state(view).dumps()


@pytest.mark.parametrize("value", (("private-card", 98765), "98765", 98765))
def test_record_rejects_hidden_payload_disguised_as_player_identity(value):
    view = ObservationStateBuilder().root(printout())
    hostile = replace(view, events=(DrawEvent(5, (("playerIndex", value),), True),))
    with pytest.raises(ValueError, match="event visibility"):
        ObservationRecord.from_state(hostile)
