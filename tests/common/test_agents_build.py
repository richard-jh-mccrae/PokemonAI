"""Every shipped deck constructs the live runtime with the Ledger armed."""
from __future__ import annotations

import pytest

from agent_helpers import deck, strategy
from common.runtime import (AgentRuntime, DecisionPilot, build_runtime,
                            _decision_configuration_from_environment)


AGENTS = ("dragapult_ex", "mega_lucario", "mega_starmie")


@pytest.mark.parametrize("name", AGENTS)
def test_every_deck_builds_the_shared_ledger_runtime(name):
    runtime = build_runtime(strategy(name), deck(name), stats=None)
    assert isinstance(runtime, AgentRuntime)
    assert runtime.strategy.name == name
    assert not hasattr(runtime.strategy, "strategies")
    assert not hasattr(runtime.strategy, "strategy_overrides")
    assert len(runtime.deck) == 60
    assert runtime.ledger is not None
    assert runtime.ledger.ctx.configuration.identity
    assert runtime.ledger.compute.search.identity
    assert runtime.ledger.compute.policy.identity


def test_environment_selects_pilot_and_registered_backend_independently(monkeypatch):
    from cgpy.puct import ENGINE_BACKEND, register_backend

    register_backend()
    monkeypatch.setenv("AGENT_DECISION_PILOT", "puct")
    monkeypatch.setenv("AGENT_ENGINE_BACKEND", ENGINE_BACKEND.name)
    monkeypatch.setenv("CG_ENGINE", "native")

    configuration = _decision_configuration_from_environment(strategy("mega_starmie"))

    assert configuration.pilot is DecisionPilot.PUCT
    assert configuration.engine_backend == ENGINE_BACKEND
    assert configuration.puct.profile == "play"


def test_unregistered_backend_fails_at_configuration(monkeypatch):
    monkeypatch.setenv("AGENT_ENGINE_BACKEND", "missing")

    with pytest.raises(ValueError, match="unavailable"):
        _decision_configuration_from_environment(strategy("mega_starmie"))


def test_backend_descriptor_rejects_the_wrong_loaded_implementation():
    import sys
    from types import ModuleType
    from common.decision.turn import EngineBackendDescriptor, SearchContractError

    module = ModuleType("fixture_engine_api")
    module.ENGINE_IMPLEMENTATION_IDENTITY = "actual"
    sys.modules[module.__name__] = module
    backend = EngineBackendDescriptor(
        "impostor", module.__name__, "expected", "fixture_engine")

    try:
        with pytest.raises(SearchContractError, match="expected 'expected'"):
            backend.resolve()
    finally:
        sys.modules.pop(module.__name__, None)
