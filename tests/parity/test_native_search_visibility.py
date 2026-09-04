from copy import deepcopy
import os
from pathlib import Path
import random
from types import SimpleNamespace

import pytest

from common.algebra import Deterministic
from common.ledger.seam import LedgerNativeProvider, PreviewState
from common.observation import ObservationRecord, ObservationStateBuilder


@pytest.fixture(scope="module")
def native_roots():
    required = os.environ.get("REQUIRE_NATIVE_VISIBILITY") == "1"
    if os.environ.get("CG_ENGINE") == "py":
        if required:
            pytest.fail("native visibility lane must load the native engine")
        pytest.skip("native engine lane")
    try:
        from cg import api
        from cg.game import battle_finish, battle_select, battle_start
    except (ImportError, OSError):
        if required:
            raise
        pytest.skip("native binary unavailable")
    assert "cgpy" not in str(api.__file__)
    deck = tuple(map(int, (Path(__file__).resolve().parents[2] /
                           "src/agents/mega_starmie/deck.csv").read_text().split()))
    raw, start = battle_start(list(deck), list(deck))
    roots = {}
    rng = random.Random(7)
    try:
        assert start.errorPlayer == -1
        for _ in range(200):
            menu = raw.get("select") or {}
            if raw["current"]["turn"] > 0 and menu.get("context") == 0:
                roots[raw["current"]["yourIndex"]] = deepcopy(raw)
                if len(roots) == 2:
                    break
                selection = [next(i for i, option in enumerate(menu["option"]) if option["type"] == 14)]
            else:
                minimum = menu.get("minCount", 0)
                selection = rng.sample(range(len(menu.get("option") or ())), minimum)
            raw = battle_select(selection)
        assert len(roots) == 2, "native setup did not reach both turn owners"
    finally:
        battle_finish()
    return roots, deck


@pytest.mark.parametrize("seat", (0, 1))
def test_native_end_hides_opponent_draw_and_entire_menu(native_roots, seat):
    roots, deck = native_roots
    raw = deepcopy(roots[seat])
    board = ObservationStateBuilder(deck).root(raw)
    root = PreviewState(raw, board, "root", deck=deck, deck_counts=board.deck_counts or ())
    provider = LedgerNativeProvider(root)
    try:
        assert provider.available, provider._error
        end = next(action for action in root.legal_actions if action.identity.kind == "end")
        node = provider.transition(root, end)
        assert isinstance(node, Deterministic), node
        view = node.state.observation
        assert view.seat == seat and view.select is None and view.legal_actions == ()
        assert view.them.hand_count == board.them.hand_count + 1
        assert view.them.deck_count == board.them.deck_count - 1
        assert view.me.hand == board.me.hand
        draws = [event for event in view.events if event.kind in (4, 5)]
        assert draws and all(event.kind == 5 for event in draws)
        assert all(dict(event.public_fields) == {"playerIndex": 1 - seat} for event in draws)
        assert ObservationRecord.loads(ObservationRecord.from_state(view).dumps()).to_state() == view
    finally:
        provider.close()


def test_native_predicted_draw_changes_neither_focal_record_nor_valuation(native_roots):
    from cg import api
    from common.decision import EvaluationRequest
    from common.ledger import EvaluationModel, LedgerValueEvaluator

    roots, deck = native_roots
    raw = deepcopy(roots[0])
    board = ObservationStateBuilder(deck).root(raw)
    root = PreviewState(raw, board, "root", deck=deck, deck_counts=board.deck_counts or ())
    views, values = [], []
    model = EvaluationModel.build()
    for card_id in (3, 6):
        def begin(observation, mine, prizes, opponent, *args, _card=card_id, **kwargs):
            return api.search_begin(observation, mine, prizes, [_card] * len(opponent), *args, **kwargs)

        controlled = SimpleNamespace(to_observation_class=api.to_observation_class,
                                     search_begin=begin, search_step=api.search_step, search_end=api.search_end)
        provider = LedgerNativeProvider(root, api_module=controlled)
        try:
            assert provider.available, provider._error
            end = next(action for action in root.legal_actions if action.identity.kind == "end")
            node = provider.transition(root, end)
            assert isinstance(node, Deterministic), node
            view = node.state.observation
            views.append(view)
            values.append(LedgerValueEvaluator().evaluate(EvaluationRequest(view, model)))
        finally:
            provider.close()
    assert views[0] == views[1]
    assert views[0].valuation_key == views[1].valuation_key
    assert views[0].decision_key == views[1].decision_key
    assert values[0] == values[1]
    assert ObservationRecord.from_state(views[0]).dumps() == ObservationRecord.from_state(views[1]).dumps()
