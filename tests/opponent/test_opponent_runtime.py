from __future__ import annotations

from agent_helpers import deck, strategy
from common.api import ActionIdentity, RootDecision
from common.opponent import OpponentEvidence, OpponentSnapshot
from common.runtime import build_runtime
from common.strategy.context import _END
from ledger_helpers import DRAGAPULT, body, player, printout


def _select():
    return {
        "type": 1, "context": 0, "minCount": 1, "maxCount": 1,
        "option": [{"type": 3, "index": 0}, {"type": _END}],
        "deck": None, "contextCard": None, "effect": None,
        "remainDamageCounter": 0, "remainEnergyCost": 0,
    }


class _Model:
    def __init__(self):
        self.calls = []

    def update(self, evidence):
        self.calls.append(evidence)
        return OpponentSnapshot(evidence, {}, (), 1.0)


def test_runtime_constructs_one_snapshot_and_passes_that_instance_to_ledger():
    models = []

    def factory(*_args, **_kwargs):
        model = _Model()
        models.append(model)
        return model

    runtime = build_runtime(
        strategy("mega_starmie"), deck("mega_starmie"), stats=None,
        opponent_model_factory=factory)
    received = []
    runtime.ledger.decide = lambda _observation, **kwargs: (
        received.append(kwargs["opponent"])
        or RootDecision((1,), ActionIdentity("end"), 0.0, True, {"backend": "ledger"}))

    runtime.decide(printout(
        me=player(active=body(DRAGAPULT, 1), hand=[2]),
        them=player(own=False, active=body(DRAGAPULT, 2)), select=_select()))

    assert len(models) == 1
    assert len(models[0].calls) == 1
    assert isinstance(models[0].calls[0], OpponentEvidence)
    assert received == [runtime.opponent_snapshot]
    assert not hasattr(runtime, "last_read")


def test_protocol_pregame_boundary_constructs_one_fresh_model_per_match():
    models = []

    def factory(*_args, **_kwargs):
        model = _Model()
        models.append(model)
        return model

    runtime = build_runtime(
        strategy("mega_starmie"), deck("mega_starmie"), stats=None,
        opponent_model_factory=factory)
    pregame = printout(turn=0, select={**_select(), "context": 1, "option": []})

    runtime.decide(pregame)
    runtime.decide(pregame)
    runtime.ledger.decide = lambda _observation, **_kwargs: RootDecision(
        (1,), ActionIdentity("end"), 0.0, True, {"backend": "ledger"})
    runtime.decide(printout(select=_select()))
    runtime.decide(pregame)

    assert len(models) == 2


def test_real_search_successors_do_not_update_live_opponent_evidence():
    from common.engine import LedgerCgpyProvider
    from sim.scenario import BodySpec, observation, scenario

    model = _Model()
    engine, _ = scenario("mega_starmie", me_active=BodySpec((1030,)),
                         me_hand=(3,), them_active=BodySpec((1030,)))
    runtime = build_runtime(
        strategy("mega_starmie"), deck("mega_starmie"),
        provider_factory=LedgerCgpyProvider, opponent_model_factory=lambda *_args, **_kwargs: model)
    decision = runtime.decide(observation(engine, 0))

    assert decision.diagnostics["backend"] == "ledger"
    assert len(model.calls) == 1
    assert all(event.kind != 4 or dict(event.public_fields).get("playerIndex") == 0
               for event in model.calls[0].events)
    assert runtime.opponent_snapshot.evidence is model.calls[0]
