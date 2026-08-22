"""Every shipped deck constructs the live runtime with the Ledger armed."""
from __future__ import annotations

import pytest

from agent_helpers import deck, strategy
from common.runtime import AgentRuntime, build_runtime


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
    assert runtime.ledger.ctx.compute.identity
