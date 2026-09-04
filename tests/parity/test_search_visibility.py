from copy import deepcopy

import pytest

from common.algebra import Deterministic
from common.engine import LedgerCgpyProvider
from common.ledger.seam import LedgerNativeProvider, PreviewState
from common.observation import ObservationRecord, ObservationStateBuilder
from sim.scenario import BodySpec, observation, scenario


@pytest.mark.parametrize("seat", (0, 1))
@pytest.mark.parametrize("backend", ("direct", "compat"))
def test_cgpy_end_uses_the_same_focal_visibility_in_both_adapters(seat, backend):
    engine, _runtime = scenario("mega_starmie", me_active=BodySpec((1030,)),
                               me_hand=(3,), them_active=BodySpec((1030,)))
    if seat:
        initial = ObservationStateBuilder().root(observation(engine, 0))
        end = next(action for action in initial.legal_actions if action.identity.kind == "end")
        engine.step(list(end.selection))
    raw = observation(engine, seat)
    board = ObservationStateBuilder((3,) * 60).root(raw)
    root = PreviewState(raw, board, "root", deck=(3,) * 60)
    if backend == "direct":
        provider = LedgerCgpyProvider(root, engine=engine.fork())
    else:
        from cgpy.compat import api
        provider = LedgerNativeProvider(root, api_module=api)
    try:
        end = next(action for action in root.legal_actions if action.identity.kind == "end")
        node = provider.transition(root, end)
        assert isinstance(node, Deterministic), node
        view = node.state.observation
        assert view.seat == seat and view.select is None and view.legal_actions == ()
        assert view.them.hand_count == board.them.hand_count + 1
        assert view.them.deck_count == board.them.deck_count - 1
        assert [(event.kind, dict(event.public_fields)) for event in view.events if event.kind in (4, 5)] == [
            (5, {"playerIndex": 1 - seat})]
        assert ObservationRecord.loads(ObservationRecord.from_state(view).dumps()).to_state() == view
        assert board == ObservationStateBuilder((3,) * 60).root(deepcopy(raw))
    finally:
        if backend == "compat":
            provider.close()
