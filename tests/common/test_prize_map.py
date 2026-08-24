from ledger_helpers import ScriptedProvider, action, body, player, printout

from common.algebra import Deterministic
from common.ledger import PrizeMap, ValuationConfiguration
from common.ledger.chance import _average
from common.ledger.evaluate import Valuation
from common.opponent import OpponentSnapshot
from common.runtime import AgentRuntime
from common.strategy import PrizePlan, Roles, Strategy
from deprecated.bellman.state import DecisionState


CINDERACE, STARYU, MEGA_STARMIE = 666, 1030, 1031
DECK = (CINDERACE, MEGA_STARMIE) * 30


class _OpponentModel:
    def update(self, evidence):
        return OpponentSnapshot(evidence, {}, (), 1.0)


def _state(observation):
    return DecisionState.from_observation(
        observation, deck=DECK, deck_name="prize-map-test",
        value_registry_identity="prize-map-test")


def test_runtime_prefers_forcing_the_opponent_to_overrun_its_last_three_prizes(monkeypatch):
    monkeypatch.setenv("AGENT_BRAIN_STRICT", "1")
    select = {"context": 0, "minCount": 1, "maxCount": 1,
              "option": [{"type": 1, "number": 1}, {"type": 1, "number": 2}]}
    root = printout(
        me=player(active=body(MEGA_STARMIE, 1), bench=(body(CINDERACE, 2),)),
        them=player(own=False, prizes=3), select=select)
    forced_four = _state(printout(
        me=player(active=body(CINDERACE, 2), bench=(body(MEGA_STARMIE, 1),)),
        them=player(own=False, prizes=3), select=select))
    exact_three = _state(root)
    offer, protect = action("promote", (0,)), action("hold", (1,))
    provider = ScriptedProvider(
        menus={"root": (offer, protect)},
        nodes={("root", offer.identity): Deterministic(forced_four),
               ("root", protect.identity): Deterministic(exact_three)})
    general = ValuationConfiguration.general()
    prize_only = general.with_values({key: (1.0 if key == "prize.race" else 0.0)
                                      for key in general})
    strategy = Strategy(
        name="prize-map-test", roles=Roles({MEGA_STARMIE: ["primary_attacker"]}),
        prize_plan=PrizePlan(protect=(MEGA_STARMIE,), offer=(CINDERACE,)))
    runtime = AgentRuntime(
        strategy, DECK, stats=None, knowledge_base=object(),
        opponent_model_factory=lambda *_args, **_kwargs: _OpponentModel(),
        provider_factory=lambda _state, **_kwargs: provider,
        valuation_configuration=prize_only)

    decision = runtime.decide(root)

    assert decision.action == offer.identity
    assert decision.value == 1.0
    assert decision.diagnostics["prize_map"] == {
        "remaining": 3, "route": [CINDERACE, MEGA_STARMIE],
        "printed_prizes": 4, "overrun": 1,
    }
    assert decision.diagnostics["prize_plan"] == strategy.prize_plan.identity
    activations = {
        item["feature"]: item["activation"]
        for row in decision.diagnostics["prices"]
        if row["action"] == str(offer.identity)
        for item in row["continuation"]["contributions"]
    }
    assert activations["prize.race"] == 1.0


def test_prize_plan_breaks_only_an_equal_structural_tie(monkeypatch):
    monkeypatch.setenv("AGENT_BRAIN_STRICT", "1")
    select = {"context": 0, "minCount": 1, "maxCount": 1,
              "option": [{"type": 1, "number": 1}, {"type": 1, "number": 2}]}
    offered = _state(printout(
        me=player(active=body(CINDERACE, 2),
                  bench=(body(STARYU, 3), body(MEGA_STARMIE, 1))),
        them=player(own=False, prizes=3), select=select))
    protected = _state(printout(
        me=player(active=body(STARYU, 3),
                  bench=(body(CINDERACE, 2), body(MEGA_STARMIE, 1))),
        them=player(own=False, prizes=3), select=select))
    offer, protect = action("promote", (0,)), action("hold", (1,))
    provider = ScriptedProvider(
        menus={"root": (offer, protect)},
        nodes={("root", offer.identity): Deterministic(offered),
               ("root", protect.identity): Deterministic(protected)})
    zero = ValuationConfiguration.general()
    zero = zero.with_values({key: 0.0 for key in zero})
    strategy = Strategy(
        name="prize-map-test", prize_plan=PrizePlan(offer=(CINDERACE,)))
    runtime = AgentRuntime(
        strategy, DECK, stats=None, knowledge_base=object(),
        opponent_model_factory=lambda *_args, **_kwargs: _OpponentModel(),
        provider_factory=lambda _state, **_kwargs: provider,
        valuation_configuration=zero)
    root = printout(
        me=player(active=body(STARYU, 3),
                  bench=(body(CINDERACE, 2), body(MEGA_STARMIE, 1))),
        them=player(own=False, prizes=3), select=select)

    assert runtime.decide(root).action == offer.identity


def test_prize_plan_cannot_override_superior_ledger_value(monkeypatch):
    monkeypatch.setenv("AGENT_BRAIN_STRICT", "1")
    select = {"context": 0, "minCount": 1, "maxCount": 1,
              "option": [{"type": 1, "number": 1}, {"type": 1, "number": 2}]}
    offered = _state(printout(
        me=player(active=body(CINDERACE, 2),
                  bench=(body(STARYU, 3), body(MEGA_STARMIE, 1))),
        them=player(own=False, prizes=3), select=select))
    funded = _state(printout(
        me=player(active=body(STARYU, 3, energies=(3,)),
                  bench=(body(CINDERACE, 2), body(MEGA_STARMIE, 1))),
        them=player(own=False, prizes=3), select=select))
    offer, fund = action("promote", (0,)), action("attach", (1,))
    provider = ScriptedProvider(
        menus={"root": (offer, fund)},
        nodes={("root", offer.identity): Deterministic(offered),
               ("root", fund.identity): Deterministic(funded)})
    general = ValuationConfiguration.general()
    funded_only = general.with_values({
        key: (1.0 if key == "zone.attached_usable" else 0.0) for key in general})
    strategy = Strategy(
        name="prize-map-test", prize_plan=PrizePlan(offer=(CINDERACE,)))
    runtime = AgentRuntime(
        strategy, DECK, stats=None, knowledge_base=object(),
        opponent_model_factory=lambda *_args, **_kwargs: _OpponentModel(),
        provider_factory=lambda _state, **_kwargs: provider,
        valuation_configuration=funded_only)
    root = printout(
        me=player(active=body(STARYU, 3),
                  bench=(body(CINDERACE, 2), body(MEGA_STARMIE, 1))),
        them=player(own=False, prizes=3), select=select)

    assert runtime.decide(root).action == fund.identity


def test_refresh_average_preserves_a_prize_map_shared_by_every_sample():
    prize_map = PrizeMap(3, (CINDERACE, MEGA_STARMIE), 4, 1, (1,))
    valuation = Valuation(1.0, (), (), prize_map=prize_map)

    averaged, _gaps = _average(((valuation, object(), object()),
                                (valuation, object(), object())), ())

    assert averaged.prize_map == prize_map
