"""Agent runtime shared by every deck: declarative pregame plus the Ledger decider."""
from __future__ import annotations

import gc
import math
import os
import sys
import traceback
from dataclasses import replace
from time import perf_counter

from common import telemetry
from common.api import ActionIdentity, RootDecision
from common.decision import (DecisionDeadlineExceeded, DecisionExecutionGuard,
                             DecisionFailure, DecisionFailureStage)
from common.observation import (HiddenHand, LegalKnowledge, ObservationState,
                                ObservationDelta, ObservationStateBuilder, OpponentBelief,
                                reduce_knowledge)
from common.cards import card_clauses, card_store
from common.cards.card_facts import EnergyCard
from common.cards.functions.damage import bench_reach
from common.deck_tracker import OwnCardModel
from common.ledger import (ComputeConfiguration, DeckOverlay, EvaluationModel,
                           LedgerDecider, OpponentProfile, ValuationConfiguration,
                           preview_provider_factory)
from common.ledger.worth import content_identity
from common.opponent import (OpponentEvidence, OpponentKnowledgeBase, OpponentModel,
                             OpponentSnapshot)
from common.scouting.artifact import load_artifact
from common.scouting.briefs import load_briefs
from common.scouting.provider import EngineCardStatProvider
from common.strategy.context import (
    _CARD,
    _DRAW_COUNT,
    _HAND,
    _IS_FIRST,
    _MULLIGAN,
    _NO,
    _SETUP_ACTIVE,
    _SETUP_BENCH,
    _YES,
)


_ENGINE = object()
PROTOCOL_BYPASS_ALLOWLIST = frozenset({"deck_submission"})


class _StoreFacts:
    """One card's numbers the engine adapters price mid-transition, read off its record."""

    __slots__ = ("bench_damage", "prize_value", "energy_type", "recycles_line")

    def __init__(self, record, store):
        self.bench_damage = max((bench_reach(attack)
                                 for attack in getattr(record, "attacks", ()) or ()), default=0)
        self.prize_value = getattr(record, "prize_value", 1)
        self.energy_type = (record.provides if isinstance(record, EnergyCard)
                            else getattr(record, "energy_type", None))
        line = (record, *(candidate for candidate in store.values()
                          if getattr(candidate, "evolves_from", None)
                          == getattr(record, "name", None)))
        self.recycles_line = any(
            clause.kind in {"self_return", "self_shuffle_in"}
            or clause.rider in {"shuffle_self_in", "return_self"}
            for candidate in line for clause in card_clauses(candidate))


class _FactsView:
    def __init__(self, store):
        self._store = store
        self._cache: dict = {}

    def get(self, card_id, default=None):
        card_id = int(card_id)
        if card_id not in self._cache:
            record = self._store.get(card_id)
            self._cache[card_id] = (_StoreFacts(record, self._store)
                                    if record is not None else None)
        found = self._cache[card_id]
        return found if found is not None else default


class _ProviderFactSources:
    """Typed card facts consumed by engine transition adapters."""

    def __init__(self, identity=None):
        store = card_store()
        self.facts = _FactsView(store)
        self.identity = content_identity(store) if identity is None else str(identity)


class AgentRuntime:
    """Deployment shell: declarative pregame followed by coordinated Ledger decisions."""

    def __init__(self, strategy, deck, *, stats=_ENGINE, knowledge_base=None,
                 opponent_model_factory=OpponentModel, provider_factory=None,
                 valuation_configuration=None, compute_configuration=None,
                 decision_parity_oracle=None, decision_containment_seconds=None):
        self.strategy = strategy
        self.deck = tuple(int(card_id) for card_id in deck)
        if stats is _ENGINE:
            stats = EngineCardStatProvider()
            stats.warm()
        self.stats = stats
        self.roles = strategy.roles.resolve(self.deck)
        profile_provider = self.stats
        if profile_provider is None:
            profile_provider = EngineCardStatProvider()
            profile_provider.warm()
        self.opponent_knowledge = (knowledge_base or OpponentKnowledgeBase.compile(
            load_artifact(strict=True), load_briefs(strict=True), profile_provider))
        self.opponent_model_factory = opponent_model_factory
        self.opponent_model = None
        self.opponent_snapshot: OpponentSnapshot | None = None
        self.last_state: ObservationState | None = None
        self._parent_valuation = None
        self._observation_delta = None
        self._in_pregame = False
        self.knowledge_enricher = None
        self.provider_factory = provider_factory
        self.decision_containment_seconds = decision_containment_seconds
        self.telemetry_session = telemetry.TelemetrySession()
        self.knowledge = LegalKnowledge()
        profiles = getattr(self.opponent_knowledge, "profiles", {})
        inclusion = getattr(self.opponent_knowledge, "card_inclusion", {})
        evaluation_model = EvaluationModel.build(
            configuration=valuation_configuration or ValuationConfiguration.general(),
            prize_plan=strategy.prize_plan,
            overlay=DeckOverlay(strategy.ledger_overlay),
            opponent_profiles={
                name: OpponentProfile(
                    profile.roles, profile.traits, profile.mechanics,
                    inclusion[name])
                for name, profile in profiles.items()
            })
        self.ledger = LedgerDecider(
            self.deck, strategy.name, evaluation_model,
            provider_factory=preview_provider_factory(self.provider_factory),
            provider_kwargs={
                "registry": _ProviderFactSources(evaluation_model.store_identity),
                "stats": self.stats,
            },
            compute=compute_configuration or ComputeConfiguration(),
            parity_oracle=decision_parity_oracle)

    def _option_card_id(self, state: ObservationState, option) -> int | None:
        option_type = option.type
        if option_type is None or int(option_type) != _CARD or option.area != _HAND:
            return None
        owner = state.seat if option.playerIndex is None else int(option.playerIndex)
        hand = state.me.hand if owner == state.seat else state.them.hand
        index = option.index
        if isinstance(hand, HiddenHand) or not isinstance(index, int) or not 0 <= index < len(hand):
            return None
        return hand.cards[index].card_id

    @staticmethod
    def _option_of_type(options, option_type: int) -> int | None:
        return next((index for index, option in enumerate(options)
                     if option.type is not None and int(option.type) == option_type), None)

    def _hand_has_setup_starter(self, state: ObservationState) -> bool:
        """Return whether the hand can legally supply the setup Active.
        Printed setup Functions remain legal starters when their ordinary stage is not Basic."""
        for card in state.me.hand:
            card_id = card.card_id
            stat = self.stats.get(card_id) if self.stats else None
            record = card_store().get(card_id) if card_id is not None else None
            setup_active = any(clause.kind == "setup_active"
                               for clause in card_clauses(record))
            if (stat is not None and stat.is_pokemon
                    and (stat.stage == "basic" or setup_active)):
                return True
        return False

    def _pregame(self, state: ObservationState) -> RootDecision:
        select = state.select
        options = () if select is None else select.options
        context = -1 if select is None or select.context is None else int(select.context)
        chosen: tuple[int, ...]
        action = "pregame"
        if context == _SETUP_ACTIVE:
            offered = {card_id: index for index, option in enumerate(options)
                       if (card_id := self._option_card_id(state, option)) is not None}
            pick = next((offered[card_id] for card_id in self.strategy.starter_priority
                         if card_id in offered), None)
            chosen = (pick if pick is not None else 0,) if options else ()
            action = "setup_active"
        elif context == _SETUP_BENCH and int(select.min_count or 0) == 0:
            chosen, action = (), "setup_bench_decline"
        elif context == _IS_FIRST:
            preferred = str(self.strategy.params.get("preferred_start", "second"))
            option_type = _YES if preferred == "first" else _NO
            pick = self._option_of_type(options, option_type)
            chosen, action = ((pick if pick is not None else 0,), "choose_start")
        elif context == _MULLIGAN:
            option_type = _NO if self._hand_has_setup_starter(state) else _YES
            pick = self._option_of_type(options, option_type)
            chosen, action = ((pick if pick is not None else 0,), "mulligan")
        elif context == _DRAW_COUNT:
            # Taking a free mulligan draw cannot remove information or a held option.  The
            # numerically largest offered count therefore dominates every smaller count.
            pick = max(range(len(options)),
                       key=lambda index: int(options[index].number or 0), default=None)
            chosen, action = ((pick,) if pick is not None else (), "free_draw_count")
        else:
            minimum = min(int(select.min_count or 0), len(options))
            chosen = tuple(range(minimum))
        return RootDecision(
            chosen, ActionIdentity(action, (context,)), 0.0, True,
            {"backend": "declarative-pregame", "context": context},
        )

    def _new_opponent_model(self):
        return self.opponent_model_factory(
            self.opponent_knowledge, provider=self.stats,
            strict=os.environ.get("AGENT_BRAIN_STRICT") == "1")

    def _observe_matchup(self, state: ObservationState) -> OpponentSnapshot:
        if self.opponent_model is None:
            self.opponent_model = self._new_opponent_model()
        self.opponent_snapshot = self.opponent_model.update(OpponentEvidence.from_state(state))
        return self.opponent_snapshot

    def _reset_for_pregame(self) -> None:
        """Clear match-scoped runtime state."""
        self.telemetry_session.begin_episode()
        self.opponent_model = self._new_opponent_model()
        self.opponent_snapshot = None
        self.knowledge = LegalKnowledge()
        self.last_state = None
        self.ledger.reset_turn()

    def decide(self, observation: dict) -> RootDecision:
        try:
            return self._decide(observation)
        except DecisionDeadlineExceeded:
            raise
        except Exception as exc:
            if os.environ.get("AGENT_BRAIN_STRICT") == "1":
                raise
            if getattr(exc, "coordinator_entered", False):
                raise
            failure = DecisionFailure.capture(DecisionFailureStage.RUNTIME, exc)
            return self.ledger.fail_safe(
                observation, failure, opponent=self.opponent_snapshot,
                knowledge=self.knowledge, state=getattr(self, "last_state", None))

    def _decide(self, observation: dict) -> RootDecision:
        turn_number = int(observation["current"]["turn"])
        if turn_number <= 0 and not self._in_pregame:
            self._reset_for_pregame()
        previous = self.last_state
        same_turn = previous is not None and previous.turn.number == turn_number
        builder = ObservationStateBuilder(self.deck)
        if same_turn:
            state, delta = builder.advance(previous, observation, knowledge=self.knowledge)
            parent_valuation = self.ledger.last_valuation
        else:
            self.ledger.reset_turn()
            state = builder.root(observation, knowledge=self.knowledge)
            delta = None
            parent_valuation = None
        if self.knowledge_enricher is not None:
            enriched = self.knowledge_enricher(state, state.knowledge)
            state, enrichment_delta = builder.rebind_knowledge(state, enriched)
            if same_turn:
                parts = set(() if delta is None else delta.parts)
                parts.update(enrichment_delta.parts)
                delta = ObservationDelta(tuple(sorted(parts)))
        self.last_state = state
        self.knowledge = state.knowledge
        if state.turn.number <= 0:
            self._in_pregame = True
            return self._pregame(state)
        self._in_pregame = False
        # Decision trees allocate heavily but rarely create cycles. Pause unproductive collector
        # scans until the decision ends; the next allocation resumes collection.
        collector_was_enabled = gc.isenabled()
        if collector_was_enabled:
            gc.disable()
        try:
            self._parent_valuation = parent_valuation
            self._observation_delta = delta
            execution_guard = (
                None if self.decision_containment_seconds is None
                else DecisionExecutionGuard(self.decision_containment_seconds))
            if execution_guard is None:
                return self._decide_core(state, observation)
            return self._decide_core(state, observation, execution_guard)
        finally:
            if collector_was_enabled:
                gc.enable()

    def _decide_core(self, state: ObservationState, observation: dict,
                     execution_guard=None) -> RootDecision:
        parent_valuation = self._parent_valuation
        delta = self._observation_delta
        snapshot = self._observe_matchup(state)
        self.knowledge = reduce_knowledge(
            self.knowledge, opponent=_belief_from_snapshot(snapshot))
        builder = ObservationStateBuilder(self.deck)
        state, knowledge_delta = builder.rebind_knowledge(state, self.knowledge)
        if parent_valuation is not None:
            parts = set(() if delta is None else delta.parts)
            parts.update(knowledge_delta.parts)
            delta = ObservationDelta(tuple(sorted(parts)))
        self.knowledge = state.knowledge
        self.last_state = state
        return self.ledger.decide(
            observation, opponent=snapshot,
            knowledge=self.knowledge, state=state,
            parent_valuation=parent_valuation, observation_delta=delta,
            execution_guard=execution_guard)

def build_runtime(strategy, deck, **kwargs) -> AgentRuntime:
    """Construct the one shared runtime; injectable seams keep tests engine-independent."""

    return AgentRuntime(strategy, deck, **kwargs)


def _belief_from_snapshot(snapshot: OpponentSnapshot) -> OpponentBelief:
    return OpponentBelief.from_snapshot(snapshot)


def _read_deck() -> list[int]:
    path = "deck.csv" if os.path.exists("deck.csv") else "/kaggle_simulations/agent/deck.csv"
    with open(path, encoding="utf-8") as handle:
        return [int(value) for value in handle.read().splitlines()[:60] if value.strip()]


def _compute_profile_from_environment() -> str:
    profile = os.environ.get("AGENT_LEDGER_COMPUTE_PROFILE", "deployment")
    if profile not in {"deployment", "correction"}:
        raise ValueError("AGENT_LEDGER_COMPUTE_PROFILE must be deployment or correction")
    return profile


def _external_decision_seconds_from_environment() -> float | None:
    raw_limit = os.environ.get("AGENT_DECISION_SECONDS")
    if raw_limit is None:
        return None
    seconds = float(raw_limit)
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("AGENT_DECISION_SECONDS must be positive and finite")
    if seconds <= 0.1:
        raise ValueError("AGENT_DECISION_SECONDS must be greater than 0.1")
    return seconds


def _decision_reserve_seconds(seconds: float) -> float:
    return min(5.0, max(1.0, seconds * 0.05))


def _decision_containment_seconds_from_environment() -> float | None:
    if _compute_profile_from_environment() != "correction":
        return None
    seconds = _external_decision_seconds_from_environment()
    if seconds is None:
        return None
    return max(0.1, seconds - _decision_reserve_seconds(seconds))


def _compute_configuration_from_environment() -> ComputeConfiguration:
    from common.decision import correction_compute_profile

    profile = _compute_profile_from_environment()
    compute = (correction_compute_profile()
               if profile == "correction" else ComputeConfiguration())
    seconds = _external_decision_seconds_from_environment()
    if seconds is None or profile == "correction":
        return compute
    budget_ms = max(1, round(max(
        0.1, seconds - _decision_reserve_seconds(seconds)) * 1000))
    return replace(compute, search=replace(compute.search, time_budget_ms=budget_ms))


def make_agent(strategy):
    """Create the Kaggle ``agent(observation)`` hook."""

    runtime = build_runtime(
        strategy, _read_deck(),
        compute_configuration=_compute_configuration_from_environment(),
        decision_containment_seconds=_decision_containment_seconds_from_environment())
    own_cards = OwnCardModel(runtime.deck)
    telemetry_on = os.environ.get("AGENT_NO_TELEMETRY") != "1"

    def enrich_knowledge(state, knowledge):
        own_cards.observe(state)
        return reduce_knowledge(
            knowledge,
            own_prizes=tuple(sorted((own_cards.prize_export() or {}).items())),
            known_top=own_cards.known_top_export() or ())

    runtime.knowledge_enricher = enrich_knowledge

    def agent(observation: dict) -> list[int]:
        protocol_operation = ("deck_submission"
                              if observation.get("select") is None
                              and "current" in observation
                              and observation["current"] is None else None)
        if observation.get("select") is None and protocol_operation is None:
            raise ValueError("non-decision observation is not an approved protocol bypass")
        if protocol_operation is not None:
            if protocol_operation not in PROTOCOL_BYPASS_ALLOWLIST:
                raise ValueError(f"unapproved protocol bypass {protocol_operation}")
            return list(runtime.deck)
        started = perf_counter()
        decision = runtime.decide(observation)
        if telemetry_on:
            try:
                state = runtime.last_state
                telemetry.emit(decision, opponent=runtime.opponent_snapshot,
                               seat=(int(observation["current"].get("yourIndex", 0))
                                     if state is None else state.seat),
                               state=state,
                               decision_seconds=perf_counter() - started,
                               session=runtime.telemetry_session,
                               evaluation_model=runtime.ledger.ctx,
                               compute_configuration=runtime.ledger.compute,
                               provider_configuration=runtime.ledger.provider_configuration,
                               provenance=telemetry.runtime_provenance(
                                   deck_name=runtime.ledger.deck_name,
                                   opponent_knowledge_identity=getattr(
                                       runtime.opponent_knowledge, "identity", "")))
            except Exception:                        # telemetry must never lose the match
                print("telemetry emit failed; decision preserved", file=sys.stderr, flush=True)
                traceback.print_exc(file=sys.stderr)
        return list(decision.chosen)

    agent.runtime = runtime
    return agent


__all__ = ["AgentRuntime", "build_runtime", "make_agent"]
