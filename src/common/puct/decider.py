from __future__ import annotations

from dataclasses import asdict

from common.api import RootDecision
from common.decision.turn import EngineBackendDescriptor

from .configuration import PuctConfiguration
from .native import NativeTurnSearchProvider
from .runtime import build_puct_coordinator
from .search import PuctSearch


class PuctUnavailable(RuntimeError):
    pass


class PuctDecider:
    def __init__(self, deck, deck_name: str, evaluation_model, *,
                 backend: EngineBackendDescriptor, configuration: PuctConfiguration):
        self.deck = tuple(int(card_id) for card_id in deck)
        self.deck_name = str(deck_name)
        self.ctx = evaluation_model
        self.backend = backend
        self.compute = configuration
        self._search = PuctSearch()
        self.coordinator = build_puct_coordinator(
            evaluation_model, prior_mode="uniform", configuration=configuration,
            provider_identity=NativeTurnSearchProvider.identity_for(backend),
            search=self._search)
        self.last_valuation = None

    @property
    def provider_configuration(self) -> dict:
        return {
            "identity": NativeTurnSearchProvider.identity_for(self.backend),
            "backend": self.backend.name,
            "factory": (f"{NativeTurnSearchProvider.__module__}."
                        f"{NativeTurnSearchProvider.__qualname__}"),
            "version": 2,
            "kwargs": {"implementation_identity": self.backend.implementation_identity},
            "factory_kwargs": {},
        }

    def reset_turn(self) -> None:
        self.last_valuation = None
        self._search.reset()

    close = reset_turn

    def decide(self, observation: dict, *, state, parent_valuation=None,
               observation_delta=None, execution_guard=None) -> RootDecision:
        provider = NativeTurnSearchProvider.from_observation(
            observation, state, backend=self.backend)
        result = self.coordinator.decide(
            provider.root, provider=provider, parent_valuation=parent_valuation,
            observation_delta=observation_delta, execution_guard=execution_guard,
            strict=True)
        chosen = result.chosen_candidate
        if chosen is None:
            evidence = result.search.puct
            outcome = None if evidence is None else evidence.outcome.value
            failure = result.search.failure
            detail = ("" if failure is None else
                      f" ({failure.stage.value}: {failure.error_type}: {failure.message})")
            raise PuctUnavailable(
                f"{self.backend.name} PUCT produced no action: "
                f"{outcome or 'unknown'}/{result.search.stop_reason}{detail}")
        self.last_valuation = result.baseline
        value = (chosen.search_value.total if chosen.search_value is not None
                 else chosen.delta.total if chosen.delta is not None else 0.0)
        return RootDecision(
            tuple(chosen.action.selection), chosen.action.identity, value,
            chosen.search_value is not None or len(result.roster.candidates) == 1,
            {
                "backend": self.backend.name,
                "engine_backend": self.backend.name,
                "pilot": "puct",
                "configuration": asdict(self.compute),
                "behavior": result.behavior_identity,
                "stop_reason": result.search.stop_reason,
            },
            decision_result=result)


__all__ = ("PuctDecider", "PuctUnavailable")
