"""Deck-neutral production boundary for full-turn Bellman search."""
from __future__ import annotations

from dataclasses import dataclass, replace
from time import monotonic

from common.api import BellmanUnavailable, PlanRequest, RootDecision
from .providers import BellmanNativeProvider
from .solver import ProductionLimits, ProductionSolver
from .pilot_profile import DEFAULT_PILOT_PROFILE, PilotProfile
from common.state import DecisionState, OpponentBelief
from .terminal import TerminalLimits, TerminalProver
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


@dataclass
class _Precheck:
    state_key: str
    provider: object
    state: DecisionState
    remaining_seconds: float

    def consume(self):
        provider, self.provider = self.provider, None
        return provider, self.state, self.remaining_seconds

    def close(self):
        if self.provider is not None and hasattr(self.provider, "close"):
            self.provider.close()
        self.provider = None


class BellmanTurnPlanner:
    """Production boundary over the same engine, ledger, and recursion used by the reference solver."""

    def __init__(self, *, registry: ValueRegistry, family_evaluator, effects=None, stats=None,
                 belief: OpponentBelief | None = None,
                 limits: ProductionLimits | None = None,
                 profile: PilotProfile = DEFAULT_PILOT_PROFILE,
                 provider_factory=BellmanNativeProvider, strategy_snapshot=None):
        self.registry = registry
        self.family_evaluator = family_evaluator
        self.effects = effects
        self.stats = stats
        self.belief = belief
        self.limits = limits or _limits_from_profile(profile)
        self.profile = profile
        self.provider_factory = provider_factory
        self.strategy_snapshot = strategy_snapshot
        self.last_terminal_diagnostics = {
            "attempted": False, "result": "skipped", "reason": "not_run"}
        self._prechecked = None

    def state_for(self, request: PlanRequest) -> DecisionState:
        return DecisionState.from_observation(
            request.observation, deck=request.deck, deck_name=request.deck_name,
            belief=self.belief,
            value_registry_identity=f"{self.registry.identity}:{self.profile.hash}")

    def _provider(self, state: DecisionState):
        provider = self.provider_factory(
            state, registry=self.registry, effects=self.effects, stats=self.stats)
        if not provider.available:
            if hasattr(provider, "close"):
                provider.close()
            raise BellmanUnavailable(provider._error)  # exact adapter failure; never legacy fallback
        return provider

    def _epoch_seconds(self, request: PlanRequest) -> float:
        remaining = request.observation.get("remainingOverageTime")
        return (self.profile.planning_seconds(remaining)
                if self.profile.get("clock.adaptive_enabled") >= 0.5
                else self.limits.max_seconds)

    def _terminal_decision(self, state: DecisionState, provider, epoch_seconds: float):
        if self.profile.get("terminal.enabled") < 0.5:
            return None, None
        prover = TerminalProver(
            provider,
            limits=TerminalLimits(
                int(self.profile.get("terminal.max_nodes")),
                min(epoch_seconds, self.profile.get("terminal.max_seconds")),
                int(self.profile.get("terminal.max_decisions"))),
            profile_hash=self.profile.hash,
        )
        proof = prover.prove(state)
        if proof is None:
            return None, prover
        backend = getattr(provider, "backend", "bellman")
        decision = RootDecision(
            proof.first_action.selection, proof.first_action.identity, 0.0, True,
            {"backend": backend, "terminal_proof": prover.diagnostics(proof)},
            proof.continuation)
        return decision, prover

    def prove(self, request: PlanRequest) -> RootDecision | None:
        self.discard_precheck()
        state = self.state_for(request)
        provider = self._provider(state)
        epoch_seconds = self._epoch_seconds(request)
        started = monotonic()
        retained = False
        try:
            decision, prover = self._terminal_decision(state, provider, epoch_seconds)
            self.last_terminal_diagnostics = (
                dict(decision.diagnostics["terminal_proof"]) if decision is not None else
                prover.diagnostics(None) if prover is not None else {
                    "attempted": False, "result": "skipped", "reason": "disabled"})
            if decision is None:
                self._prechecked = _Precheck(
                    state.plan_key, provider, state,
                    max(0.01, epoch_seconds - (monotonic() - started)))
                retained = True
            return decision
        finally:
            if not retained and hasattr(provider, "close"):
                provider.close()

    def discard_precheck(self) -> None:
        if self._prechecked is not None:
            self._prechecked.close()
            self._prechecked = None

    def decide(self, request: PlanRequest, *, terminal_checked: bool = False) -> RootDecision:
        state = self.state_for(request)
        prechecked = self._prechecked if terminal_checked else None
        if prechecked is not None and prechecked.state_key == state.plan_key:
            provider, state, epoch_seconds = prechecked.consume()
            self._prechecked = None
        else:
            self.discard_precheck()
            provider = self._provider(state)
            epoch_seconds = self._epoch_seconds(request)
        backend = getattr(provider, "backend", "bellman")
        epoch_limits = replace(
            self.limits,
            max_seconds=epoch_seconds,
        )
        proof = None
        prover = None
        proof_started = monotonic()
        if not terminal_checked:
            proof, prover = self._terminal_decision(state, provider, epoch_seconds)
        if proof is not None:
            if hasattr(provider, "close"):
                provider.close()
            return proof
        proof_seconds = monotonic() - proof_started
        epoch_limits = replace(epoch_limits, max_seconds=max(0.01, epoch_seconds - proof_seconds))
        solver = ProductionSolver(
            provider, ValueOracle(
                self.registry, self.family_evaluator, effects=self.effects, stats=self.stats),
            limits=epoch_limits, profile=self.profile, strategy_snapshot=self.strategy_snapshot)
        try:
            decision = solver.decide(state)
        except RuntimeError as exc:
            raise BellmanUnavailable(str(exc)) from exc
        finally:
            if hasattr(provider, "close"):
                provider.close()
        diagnostics = dict(decision.diagnostics)
        diagnostics["backend"] = backend
        diagnostics["terminal_proof"] = (
            prover.diagnostics(None) if prover is not None else {
                **self.last_terminal_diagnostics,
                "reason": (self.last_terminal_diagnostics.get("reason", "prechecked")
                           if terminal_checked else "disabled")})
        return RootDecision(decision.chosen, decision.action, decision.value,
                            decision.complete, diagnostics, decision.plan_suffix)


__all__ = ("BellmanTurnPlanner",)
