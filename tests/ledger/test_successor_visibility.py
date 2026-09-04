from copy import deepcopy
from types import SimpleNamespace

import pytest

from common.algebra import Actor, Deterministic, Unknown
from common.ledger.seam import LedgerNativeProvider, PreviewState
from common.observation import ObservationRecord, ObservationStateBuilder
from ledger_helpers import body, player, printout


def prompt(context=0, options=None):
    return {"type": 0 if context == 0 else 1, "context": context,
            "minCount": 1, "maxCount": 1,
            "option": [{"type": 14}] if options is None else options}


class SearchApi:
    identity = "visibility-fixture"

    def __init__(self, child):
        self.child = child
        self.closed = False

    def to_observation_class(self, raw):
        return raw

    def search_begin(self, raw, *args, **kwargs):
        return SimpleNamespace(searchId=0, observation=deepcopy(raw))

    def search_step(self, search_id, selection):
        return SimpleNamespace(searchId=1, observation=deepcopy(self.child))

    def search_end(self):
        self.closed = True


def root_and_child(seat=0):
    raw = printout(me=player(hand=(3,)), select=prompt())
    raw["current"]["result"] = -1
    raw["current"]["yourIndex"] = seat
    if seat:
        raw["current"]["players"].reverse()
    board = ObservationStateBuilder((3,) * 60).root(raw)
    root = PreviewState(raw, board, "root", deck=(3,) * 60)
    child = deepcopy(raw)
    child["current"]["yourIndex"] = 1 - seat
    child["current"]["turn"] += 1
    child["current"]["players"][seat]["hand"] = None
    opponent = child["current"]["players"][1 - seat]
    opponent["handCount"] = 1
    opponent["deckCount"] -= 1
    opponent["hand"] = [{"id": 6, "serial": 987, "playerIndex": 1 - seat}]
    child["logs"] = [{"type": 3, "playerIndex": seat},
                     {"type": 2, "playerIndex": 1 - seat},
                     {"type": 4, "playerIndex": 1 - seat, "cardId": 6, "serial": 987}]
    return root, child


@pytest.mark.parametrize("seat", (0, 1))
def test_native_end_exposes_only_the_focal_observation(seat):
    root, child = root_and_child(seat)
    api = SearchApi(child)
    provider = LedgerNativeProvider(root, api_module=api)
    try:
        node = provider.transition(root, root.legal_actions[0])
        assert isinstance(node, Deterministic)
        view = node.state.observation
        assert view.seat == seat
        assert view.select is None and view.legal_actions == ()
        assert provider.actions(node.state) == ()
        assert provider.actor(node.state) is Actor.OPPONENT
        assert tuple(card.card_id for card in view.me.hand) == (3,)
        assert dict(view.events[-1].public_fields) == {"playerIndex": 1 - seat}
        assert view.events[-1].kind == 5
        assert "987" not in ObservationRecord.from_state(view).dumps()
    finally:
        provider.close()
    assert api.closed


def test_private_opponent_forced_prompt_is_unavailable():
    root, child = root_and_child()
    child["select"] = prompt(7, [{"type": 3, "area": 4, "index": 0, "playerIndex": 1}])
    child["select"]["deck"] = [{"id": 6, "serial": 987}]
    provider = LedgerNativeProvider(root, api_module=SearchApi(child))
    try:
        result = provider.transition(root, root.legal_actions[0])
        assert isinstance(result, Unknown)
        assert "private" in result.reason
        assert "987" not in str(result)
    finally:
        provider.close()


def test_focal_choice_targeting_an_opponent_card_keeps_the_focal_actor():
    root, child = root_and_child()
    child["current"]["yourIndex"] = 0
    child["current"]["players"][0]["hand"] = [{"id": 3, "serial": 800}]
    child["current"]["players"][1]["bench"] = [body(119, 22)]
    child["select"] = prompt(5, [{"type": 3, "area": 1, "index": 0, "playerIndex": 1}])
    provider = LedgerNativeProvider(root, api_module=SearchApi(child))
    try:
        node = provider.transition(root, root.legal_actions[0])
        assert isinstance(node, Deterministic)
        assert provider.actor(node.state) is Actor.OURS
        assert node.state.observation.select is not None
        assert provider.actions(node.state)
    finally:
        provider.close()


def test_hidden_draw_does_not_change_the_decision_or_serialized_successor():
    from functools import partial
    from common.ledger import EvaluationModel, LedgerDecider
    from common.telemetry import build_decision_record

    records = []
    for card_id in (3, 6):
        root, child = root_and_child()
        raw = deepcopy(root._provider_payload)
        raw["select"]["option"].append({"type": 8, "area": 2, "index": 0,
                                         "inPlayArea": 4, "inPlayIndex": 0})
        raw["current"]["players"][0]["active"] = [body(1030, 12)]
        child["current"]["players"][0]["active"] = [body(1030, 12)]
        board = ObservationStateBuilder((3,) * 60).root(raw)
        child["logs"][-1].update(cardId=card_id, serial=900 + card_id)
        child["current"]["players"][1]["hand"] = [{"id": card_id, "serial": 900 + card_id}]
        model = EvaluationModel.build()
        decider = LedgerDecider((3,) * 60, "visibility-test", model,
                                provider_factory=partial(LedgerNativeProvider, api_module=SearchApi(child)))
        decision = decider.decide(raw)
        records.append(build_decision_record(
            decision.decision_result, board,
            episode_key="visibility", decision_index=0, parent_decision_id=None,
            selection=decision.chosen, evaluation_model=model, compute_configuration=decider.compute,
            provider_configuration=decider.provider_configuration,
            provenance={"agent": "test", "artifact": "fixture", "code": "visibility",
                        "data": {"cards": "fixture"}}, decision_seconds=0.0))
    for record in records:
        assert record["candidates"][0]["successors"]
        assert "903" not in str(record["candidates"][0]["successors"])
        assert "906" not in str(record["candidates"][0]["successors"])
    assert records[0]["candidates"] == records[1]["candidates"]
    assert records[0]["observation"] == records[1]["observation"]


def test_privacy_failure_remains_unavailable_at_the_search_budget_boundary():
    from common.decision import EvaluationStatus, SearchConfiguration
    from common.ledger import EvaluationModel
    from common.ledger.evaluate import evaluate
    from common.ledger.preview import price_actions

    root, child = root_and_child()
    child["select"] = prompt(7, [{"type": 3, "area": 0, "index": 0, "playerIndex": 1}])
    provider = LedgerNativeProvider(root, api_module=SearchApi(child))
    model = EvaluationModel.build()
    try:
        prices = price_actions(root, root.observation, evaluate(root.observation, model).total,
                                provider, model, compute=SearchConfiguration(
                                    depth_budget=1, path_node_budget=1))
        assert prices[0].status is EvaluationStatus.UNAVAILABLE
        assert prices[0].successors == ()
    finally:
        provider.close()


def test_privacy_failure_consumes_the_global_node_budget():
    from common.decision import SearchConfiguration
    from common.decision.configuration import BudgetController
    from common.ledger import EvaluationModel
    from common.ledger.evaluate import evaluate
    from common.ledger.preview import _Walk

    root, _child = root_and_child()
    model = EvaluationModel.build()
    compute = SearchConfiguration(node_budget=1)
    budget = BudgetController(compute)
    walk = _Walk(None, model, (), compute, budget, lambda board: evaluate(board, model))
    walk.node(root, root.observation, Unknown("private opponent selection", "visibility"), 1)
    assert budget.nodes == 1
    assert budget.check()
    assert walk.unavailable
    walk.node(root, root.observation, Unknown("private opponent selection", "visibility"), 1)
    assert walk.path_stopped and walk.unavailable


def test_public_opponent_promotion_uses_focal_values_without_a_focal_continuation_policy():
    from common.ledger import EvaluationModel
    from common.ledger.evaluate import evaluate
    from common.ledger.preview import price_actions

    root, child = root_and_child()
    child["current"]["players"][1]["bench"] = [body(119, 20), body(1030, 21)]
    child["select"] = prompt(4, [{"type": 3, "area": 5, "index": i, "playerIndex": 1}
                                 for i in range(2)])

    class PromotionApi(SearchApi):
        def search_step(self, search_id, selection):
            result = deepcopy(self.child)
            if search_id:
                result["current"]["result"] = selection[0]
                result["select"] = None
            return SimpleNamespace(searchId=search_id + 1, observation=result)

    provider = LedgerNativeProvider(root, api_module=PromotionApi(child))
    model = EvaluationModel.build()
    try:
        price, = price_actions(root, root.observation, evaluate(root.observation, model).total, provider, model)
        assert price.successors and price.successors[0].state.turn.result == 1
        assert price.successors[0].state.select is None
        assert price.continuation_policy == ()
        assert len(price.successors[0].action_path) == 2
    finally:
        provider.close()


def test_manual_coin_is_resolved_before_hiding_the_opponent_prompt():
    from common.algebra import Chance

    root, child = root_and_child()

    class CoinApi(SearchApi):
        def search_step(self, search_id, selection):
            result = deepcopy(self.child)
            if not search_id:
                result["select"] = prompt(46, [{"type": 1}, {"type": 2}])
            else:
                result["logs"].append({"type": 22, "playerIndex": 1, "head": selection == [0]})
            return SimpleNamespace(searchId=search_id + 1, observation=result)

    provider = LedgerNativeProvider(root, api_module=CoinApi(child))
    try:
        node = provider.transition(root, root.legal_actions[0])
        assert isinstance(node, Chance)
        assert [edge.probability for edge in node.children] == [0.5, 0.5]
        assert all(edge.node.state.observation.select is None for edge in node.children)
        assert all(edge.node.state.observation.legal_actions == () for edge in node.children)
    finally:
        provider.close()
