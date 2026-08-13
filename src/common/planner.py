"""Deck-neutral production boundary for full-turn Bellman search."""
from __future__ import annotations

from dataclasses import replace

from .api import BellmanUnavailable, PlanRequest, RootDecision
from .native_engine import NativeCgTransitionProvider
from .solver import ProductionLimits, ProductionSolver
from .pilot_profile import DEFAULT_PILOT_PROFILE, PilotProfile
from .state import DecisionState, OpponentBelief
from .value import ValueOracle, ValueRegistry


def _limits_from_profile(profile: PilotProfile) -> ProductionLimits:
    return ProductionLimits(
        max_nodes=int(profile.get("search.runtime_nodes_per_root")),
        beam_width=int(profile.get("search.beam_width")),
        root_beam_width=int(profile.get("search.root_beam_width")),
        effect_choice_width=int(profile.get("search.effect_choice_width")),
        root_probe_nodes=int(profile.get("search.shallow_nodes")),
        root_refinement_width=int(profile.get("search.refinement_width")),
        chance_max_nodes=int(profile.get("search.chance_max_nodes")),
        reveal_max_nodes=int(profile.get("search.reveal_max_nodes")),
        max_seconds=profile.get("clock.remaining_200_seconds"),
    )


DEFAULT_PRODUCTION_LIMITS = _limits_from_profile(DEFAULT_PILOT_PROFILE)


class BellmanTurnPlanner:
    """Production boundary over the same engine, ledger, and recursion used by the reference solver."""

    def __init__(self, *, registry: ValueRegistry, family_evaluator, effects=None, stats=None,
                 belief: OpponentBelief | None = None,
                 limits: ProductionLimits | None = None,
                 profile: PilotProfile = DEFAULT_PILOT_PROFILE,
                 provider_factory=NativeCgTransitionProvider):
        self.registry = registry
        self.family_evaluator = family_evaluator
        self.effects = effects
        self.stats = stats
        self.belief = belief
        self.limits = limits or _limits_from_profile(profile)
        self.profile = profile
        self.provider_factory = provider_factory

    def state_for(self, request: PlanRequest) -> DecisionState:
        return DecisionState.from_observation(
            request.observation, deck=request.deck, deck_name=request.deck_name,
            belief=self.belief,
            value_registry_identity=f"{self.registry.identity}:{self.profile.hash}")

    def decide(self, request: PlanRequest) -> RootDecision:
        state = self.state_for(request)
        provider = self.provider_factory(
            state, registry=self.registry, effects=self.effects, stats=self.stats)
        backend = getattr(provider, "backend", "bellman")
        if not provider.available:
            if hasattr(provider, "close"):
                provider.close()
            raise BellmanUnavailable(provider._error)  # exact adapter failure; never legacy fallback
        remaining = request.observation.get("remainingOverageTime")
        epoch_seconds = (self.profile.planning_seconds(remaining)
                         if self.profile.get("clock.adaptive_enabled") >= 0.5
                         else self.limits.max_seconds)
        epoch_limits = replace(
            self.limits,
            max_seconds=epoch_seconds,
        )
        solver = ProductionSolver(
            provider, ValueOracle(
                self.registry, self.family_evaluator, effects=self.effects, stats=self.stats),
            limits=epoch_limits, profile=self.profile)
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
