"""Pure Mega Starmie Bellman runtime; neutral facts enter through constructor adapters."""
from __future__ import annotations

from .api import BellmanUnavailable, PlanRequest, RootDecision
from .engine import CgpyTransitionProvider
from .information import CausalNeeds
from .solver import ProductionLimits, ProductionSolver
from .state import DecisionState, OpponentBelief
from .value import ValueOracle, ValueRegistry


class MegaStarmieTurnPlanner:
    """Production boundary over the same engine, ledger, and recursion used by the reference solver."""

    def __init__(self, *, registry: ValueRegistry, family_evaluator,
                 belief: OpponentBelief | None = None,
                 limits: ProductionLimits = ProductionLimits(4, 300, 2, 0, 24)):
        self.registry = registry
        self.family_evaluator = family_evaluator
        self.belief = belief
        self.limits = limits

    def decide(self, request: PlanRequest) -> RootDecision:
        state = DecisionState.from_observation(
            request.observation, deck=request.deck, deck_name=request.deck_name,
            belief=self.belief, value_registry_identity=self.registry.identity)
        provider = CgpyTransitionProvider(
            state, registry=self.registry, needs=CausalNeeds(), production_chance=True)
        if not provider.available:
            raise BellmanUnavailable(provider._error)  # exact adapter failure; never legacy fallback
        solver = ProductionSolver(
            provider, ValueOracle(self.registry, self.family_evaluator), limits=self.limits)
        try:
            decision = solver.decide(state)
        except RuntimeError as exc:
            raise BellmanUnavailable(str(exc)) from exc
        if not decision.complete:
            raise BellmanUnavailable("bounded Bellman result is incomplete")
        return decision


__all__ = ("MegaStarmieTurnPlanner",)
