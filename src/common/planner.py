"""Deck-neutral production boundary for full-turn Bellman search."""
from __future__ import annotations

from .api import BellmanUnavailable, PlanRequest, RootDecision
from .native_engine import NativeCgTransitionProvider
from .solver import ProductionLimits, ProductionSolver
from .state import DecisionState, OpponentBelief
from .value import ValueOracle, ValueRegistry


# Deployment bounds branching, never depth. Every root action receives an equal probe; the strongest
# incomplete Bellman continuations receive the expensive refinement pass.
RUNTIME_MAX_NODES_PER_ROOT_ACTION = 256
RUNTIME_BEAM_WIDTH = 16
RUNTIME_ROOT_BEAM_WIDTH = 16

DEFAULT_PRODUCTION_LIMITS = ProductionLimits(
    max_nodes=RUNTIME_MAX_NODES_PER_ROOT_ACTION, beam_width=RUNTIME_BEAM_WIDTH,
    root_beam_width=RUNTIME_ROOT_BEAM_WIDTH,
)


class BellmanTurnPlanner:
    """Production boundary over the same engine, ledger, and recursion used by the reference solver."""

    def __init__(self, *, registry: ValueRegistry, family_evaluator, effects=None, stats=None,
                 belief: OpponentBelief | None = None,
                 limits: ProductionLimits = DEFAULT_PRODUCTION_LIMITS,
                 provider_factory=NativeCgTransitionProvider):
        self.registry = registry
        self.family_evaluator = family_evaluator
        self.effects = effects
        self.stats = stats
        self.belief = belief
        self.limits = limits
        self.provider_factory = provider_factory

    def decide(self, request: PlanRequest) -> RootDecision:
        state = DecisionState.from_observation(
            request.observation, deck=request.deck, deck_name=request.deck_name,
            belief=self.belief, value_registry_identity=self.registry.identity)
        provider = self.provider_factory(
            state, registry=self.registry, effects=self.effects, stats=self.stats)
        backend = getattr(provider, "backend", "bellman")
        if not provider.available:
            if hasattr(provider, "close"):
                provider.close()
            raise BellmanUnavailable(provider._error)  # exact adapter failure; never legacy fallback
        solver = ProductionSolver(
            provider, ValueOracle(
                self.registry, self.family_evaluator, effects=self.effects, stats=self.stats),
            limits=self.limits)
        try:
            decision = solver.decide(state)
        except RuntimeError as exc:
            raise BellmanUnavailable(str(exc)) from exc
        finally:
            if hasattr(provider, "close"):
                provider.close()
        diagnostics = dict(decision.diagnostics)
        diagnostics["backend"] = backend
        return RootDecision(decision.chosen, decision.action, decision.value,
                            decision.complete, diagnostics)


__all__ = ("BellmanTurnPlanner",)
