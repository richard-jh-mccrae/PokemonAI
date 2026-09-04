from copy import deepcopy

import pytest

from common.observation import ObservationRecord, ObservationStateBuilder
from common.observation.projection import ProjectionError, SelectionVisibility, project_successor
from ledger_helpers import body, player, printout


def transition(*, context=0):
    parent = printout(me=player(hand=(3,)), them=player(own=False, hand_count=2))
    child = deepcopy(parent)
    child["current"]["yourIndex"] = 1
    child["current"]["players"][0]["hand"] = None
    child["select"] = {"context": context, "type": 0, "minCount": 1, "maxCount": 1,
                       "option": [{"type": 14}]}
    child["logs"] = [{"type": 3, "playerIndex": 0}]
    return parent, child


def project(parent, child, **kwargs):
    return project_successor(child, parent, 0, source_seat=1, actor_seat=1, **kwargs)


def test_projection_is_pure_and_masks_every_opponent_prompt_field():
    parent, child = transition(context=7)
    child["select"].update(deck=[{"id": 6, "serial": 999}],
                           contextCard={"id": 6}, effect={"id": 6})
    child["current"]["looking"] = [{"id": 6, "serial": 999}]
    original = deepcopy(child)
    raw, control = project(parent, child)
    view = ObservationStateBuilder().root(raw)

    assert control.visibility is SelectionVisibility.PRIVATE
    assert control.actions == ()
    assert view.select is None and view.legal_actions == ()
    assert view.looking.cards is None and view.looking.count == 1
    assert "999" not in ObservationRecord.from_state(view).dumps()
    assert child == original
    assert parent["current"]["players"][0]["hand"][0]["id"] == 3


def test_public_promotion_keeps_control_outside_the_focal_observation():
    parent, child = transition(context=4)
    child["current"]["players"][1]["bench"] = [body(119, 20), body(1030, 21)]
    child["select"] = {"context": 4, "type": 1, "minCount": 1, "maxCount": 1,
                       "option": [{"type": 3, "area": 5, "index": i, "playerIndex": 1}
                                  for i in (1, 0)]}
    raw, control = project(parent, child)
    assert control.visibility is SelectionVisibility.PUBLIC
    assert len(control.actions) == 2
    assert {action.selection for action in control.actions} == {(0,), (1,)}
    assert ObservationStateBuilder().root(raw).legal_actions == ()


def test_promotion_subset_is_not_assumed_public():
    parent, child = transition(context=4)
    child["current"]["players"][1]["bench"] = [body(119, 20), body(1030, 21)]
    child["select"]["option"] = [{"type": 3, "area": 5, "index": 0, "playerIndex": 1}]
    assert project(parent, child)[1].visibility is SelectionVisibility.PRIVATE


@pytest.mark.parametrize("logs", [
    [{"type": 5, "playerIndex": 0}, {"type": 7, "playerIndex": 0, "fromArea": 2, "toArea": 0}],
    [{"type": 100, "playerIndex": 0}],
    [],
])
def test_equal_hand_count_does_not_authorize_unproven_hand_reuse(logs):
    parent, child = transition()
    child["logs"] = logs
    with pytest.raises(ProjectionError, match="hand"):
        project(parent, child)


def test_known_prize_recovery_requires_complete_remaining_identity_and_an_acquisition_event():
    parent, child = transition()
    parent["current"]["players"][0]["prize"] = [None, None]
    child["current"]["players"][0].update(prize=[{"id": 6}], handCount=2)
    child["logs"] = [{"type": 7, "playerIndex": 0, "fromArea": 6, "toArea": 2}]
    raw, _ = project(parent, child, known_prizes=((3, 1), (6, 1)))
    assert [card["id"] for card in raw["current"]["players"][0]["hand"]] == [3, 3]
    child["current"]["players"][0]["prize"] = [None]
    with pytest.raises(ProjectionError):
        project(parent, child, known_prizes=((3, 1), (6, 1)))


def test_cross_view_hidden_movement_is_unavailable_but_public_discard_survives():
    parent, child = transition()
    child["logs"].append({"type": 6, "playerIndex": 1, "fromArea": 0, "toArea": 2,
                          "cardId": 6, "serial": 90})
    with pytest.raises(ProjectionError, match="movement visibility"):
        project(parent, child)
    child["logs"][-1]["toArea"] = 3
    child["current"]["players"][1]["discard"] = [{"id": 6, "serial": 90}]
    raw, _ = project(parent, child)
    assert raw["logs"][-1]["cardId"] == 6


def test_focal_view_public_deck_search_reveal_is_preserved():
    parent, child = transition()
    child["current"]["yourIndex"] = 0
    child["current"]["players"][0]["hand"] = deepcopy(parent["current"]["players"][0]["hand"])
    child["logs"] = [{"type": 6, "playerIndex": 1, "fromArea": 0, "toArea": 2,
                      "cardId": 119, "serial": 90}]
    raw, _ = project_successor(child, parent, 0, source_seat=0, actor_seat=0)
    assert raw["logs"][0]["cardId"] == 119


def test_cross_view_old_public_logs_are_not_reapplied_to_the_focal_hand():
    parent, child = transition()
    past = {"type": 10, "playerIndex": 0, "cardId": 1121, "serial": 88}
    parent["logs"] = [past]
    child["logs"] = [past, *child["logs"]]
    raw, _ = project(parent, child)
    assert raw["logs"] == [{"type": 3, "playerIndex": 0}]
    assert raw["current"]["players"][0]["hand"] == parent["current"]["players"][0]["hand"]


def test_formerly_public_card_is_not_visible_after_shuffle_into_a_hidden_zone():
    parent, child = transition()
    parent["current"]["players"][1]["discard"] = [{"id": 6, "serial": 90}]
    child["logs"] = [{"type": 6, "playerIndex": 1, "cardId": 6, "serial": 90,
                      "fromArea": 3, "toArea": 0}, {"type": 0, "playerIndex": 1},
                     {"type": 6, "playerIndex": 1, "cardId": 6, "serial": 90,
                      "fromArea": 0, "toArea": 2}]
    with pytest.raises(ProjectionError, match="movement visibility"):
        project(parent, child)
