"""Agent runtime shared by every deck: declarative pregame plus the Ledger decider."""
from __future__ import annotations

import gc
import os
import sys
import traceback
from time import perf_counter

from common import telemetry
from common.api import ActionIdentity, RootDecision
from common.observation import (HiddenHand, LegalKnowledge, ObservationState,
                                ObservationStateBuilder, OpponentBelief, reduce_knowledge)
from common.cards import card_clauses, card_store
from common.cards.card_facts import EnergyCard
from common.cards.functions.damage import bench_reach
from common.deck_tracker import OwnCardModel
from common.ledger import (ComputeConfiguration, DeckOverlay, EvaluationModel,
                           LedgerDecider, ValuationConfiguration,
                           preview_provider_factory)
from common.opponent import (OpponentEvidence, OpponentKnowledgeBase, OpponentModel,
                             OpponentSnapshot)
from common.scouting.artifact import load_artifact
from common.scouting.briefs import load_briefs
from common.scouting.provider import EngineCardStatProvider
from common.strategy.context import (
    _CARD,
    _DRAW_COUNT,
    _DAMAGE,
    _DAMAGE_COUNTER,
    _DAMAGE_COUNTER_ANY,
    _DAMAGE_COUNTER_COUNT,
    _END,
    _HAND,
    _IS_FIRST,
    _MULLIGAN,
    _NO,
    _SETUP_ACTIVE,
    _SETUP_BENCH,
    _TO_BENCH,
    _TO_FIELD,
    _TO_HAND,
    _YES,
)


_ENGINE = object()


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

    def __init__(self):
        self.facts = _FactsView(card_store())


class AgentRuntime:
    """Deployment shell: declarative pregame, forced selections, and the Ledger (ADR-0145/0149);
    the Bellman teacher extends this shell from ``deprecated/bellman/runtime.py``."""

    def __init__(self, strategy, deck, *, stats=_ENGINE, knowledge_base=None,
                 opponent_model_factory=OpponentModel, provider_factory=None, limits=None,
                 valuation_configuration=None, compute_configuration=None):
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
        self._in_pregame = False
        self.provider_factory = provider_factory
        self.limits = limits
        self.last_decision_limit = None
        self.last_deadline_hit = False
        self._fallback_scope = None
        self._fallback_effect = None
        self._fallback_pending = False
        # Match-scoped: `logs` is a DELTA, so a lock spent two selections ago is no longer in the
        # observation. On the runtime so replay and test callers see the deployed board state.
        self._attack_locks: dict = {}
        self.knowledge = LegalKnowledge()
        self.ledger = LedgerDecider(
            self.deck, strategy.name,
            EvaluationModel.build(
                configuration=valuation_configuration or ValuationConfiguration.general(),
                compute=compute_configuration or ComputeConfiguration(),
                roles={card_id: tuple(self.roles.get(card_id, ()) or ())
                       for card_id in self.deck},
                prize_plan=strategy.prize_plan,
                overlay=DeckOverlay(strategy.ledger_overlay)),
            provider_factory=preview_provider_factory(self.provider_factory),
            provider_kwargs={"registry": _ProviderFactSources(),
                             "stats": self.stats})

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
        """Whether the hand can legally supply the setup Active.

        Printed setup Functions remain legal starters when the ordinary stage is not Basic.
        """
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
        """Match-boundary state clearing; the teacher extends this with its plan caches."""
        self.opponent_model = self._new_opponent_model()
        self.opponent_snapshot = None
        self._attack_locks = {}
        self.knowledge = LegalKnowledge()

    def _invalidate_plans(self) -> None:
        """The Ledger holds no cross-decision plan state; the Bellman teacher overrides."""

    def _forced_selection(self, state: ObservationState):
        select = state.select
        options = () if select is None else select.options
        minimum = 0 if select is None or select.min_count is None else int(select.min_count)
        maximum = len(options) if select is None or select.max_count is None else int(select.max_count)
        if len(options) > 1 or minimum != maximum or minimum != len(options):
            return None
        self._invalidate_plans()
        return RootDecision(
            tuple(range(len(options))), ActionIdentity(
                "forced_selection", (-1 if select is None or select.context is None
                                     else int(select.context),)),
            0.0, True, {"backend": "forced-selection",
                        "context": None if select is None else select.context,
                        "option_count": len(options)})

    def decide(self, observation: dict) -> RootDecision:
        self.last_deadline_hit = False
        self.last_decision_limit = None
        try:
            return self._decide(observation)
        except Exception as exc:
            # Hiding a brain crash breeds unfixable bugs: AGENT_BRAIN_STRICT=1 re-raises for
            # offline harnesses; deployment logs the full traceback (LEDGER-CRASH, greppable)
            # and carries a bounded report in diagnostics, THEN saves the match.
            if os.environ.get("AGENT_BRAIN_STRICT") == "1":
                raise
            report = self._crash_report(observation, exc)
            return self._fallback_decision(observation, f"exception:{type(exc).__name__}",
                                           error=report)

    def _decide(self, observation: dict) -> RootDecision:
        state = ObservationStateBuilder(self.deck).root(observation, knowledge=self.knowledge)
        self.knowledge = state.knowledge
        if state.turn.number <= 0:
            if not self._in_pregame:
                self._reset_for_pregame()
            self._in_pregame = True
            return self._pregame(state)
        self._in_pregame = False
        scope = (state.turn.number, state.seat)
        select = state.select
        context = -1 if select is None or select.context is None else int(select.context)
        effect = None if select is None else select.effect
        effect_key = ((effect.owner, effect.card_id, effect.serial) if effect is not None else None)
        new_effect = (self._fallback_effect is not None and effect_key is not None
                      and effect_key != self._fallback_effect)
        if (context == 0 or new_effect
                or (self._fallback_scope is not None and self._fallback_scope != scope)):
            self._fallback_scope = None
            self._fallback_effect = None
            self._fallback_pending = False
        elif self._fallback_scope == scope or self._fallback_pending:
            self._fallback_scope = scope
            self._fallback_effect = effect_key or self._fallback_effect
            self._fallback_pending = False
            return self._fallback_decision(observation, "effect_latch")
        # One decision allocates heavily but builds trees, so cyclic garbage is rare and the
        # collector's constant generational scans reclaim almost nothing until the search ends.
        # Pause it for the decision; collection resumes with the first allocation afterwards.
        collector_was_enabled = gc.isenabled()
        if collector_was_enabled:
            gc.disable()
        try:
            decision = self._decide_core(state, observation)
            production = (decision.diagnostics.get("production") or {})
            if bool(production.get("deadline_hit")):
                if context == 0:
                    self._fallback_pending = production.get("execution_tier") == "recoverable"
                else:
                    self._fallback_scope = scope
                    self._fallback_effect = effect_key
            return decision
        finally:
            if collector_was_enabled:
                gc.enable()

    def _decide_core(self, state: ObservationState, observation: dict) -> RootDecision:
        forced = self._forced_selection(state)
        if forced is not None:
            return forced
        snapshot = self._observe_matchup(state)
        self.knowledge = reduce_knowledge(
            self.knowledge, opponent=_belief_from_snapshot(snapshot))
        state = ObservationStateBuilder(self.deck).root(observation, knowledge=self.knowledge)
        self.last_state = state
        return self.ledger.decide(
            observation, opponent=snapshot,
            knowledge=self.knowledge, state=state)

    @staticmethod
    def _crash_report(observation: dict, exc: Exception) -> dict:
        select = observation.get("select") or {}
        current = observation.get("current") or {}
        trace = traceback.format_exc()
        print(f"LEDGER-CRASH turn={current.get('turn')} seat={current.get('yourIndex')} "
              f"context={select.get('context')} options={len(select.get('option') or ())}: "
              f"{type(exc).__name__}: {exc}\n{trace}", file=sys.stderr, flush=True)
        return {"type": type(exc).__name__, "message": str(exc)[:500],
                "traceback_tail": trace[-2000:]}

    #: Names the crash path in diagnostics and the dashboard; the teacher overrides both.
    fallback_backend = "last-resort-fallback"
    fallback_action = "last_resort_fallback"

    def _fallback_selection(self, observation: dict) -> list[int]:
        return _last_resort_selection(observation)

    def _fallback_decision(self, observation: dict, cause: str,
                           error: dict | None = None) -> RootDecision:
        chosen = tuple(self._fallback_selection(observation))
        select = observation.get("select") or {}
        current = observation.get("current") or {}
        context = _int_field(select, "context", -1)
        if context != 0:
            self._fallback_scope = (
                _int_field(current, "turn", 0), _int_field(current, "yourIndex", 0))
            effect = select.get("effect") or {}
            self._fallback_effect = (tuple(effect.get(key) for key in (
                "playerIndex", "id", "serial")) if effect else self._fallback_effect)
        self._invalidate_plans()
        diagnostics = {
            "backend": self.fallback_backend,
            "fallback": {"cause": cause, "latched": self._fallback_scope is not None,
                         "context": context, "chosen": chosen,
                         **({"error": error} if error else {})},
        }
        return RootDecision(
            chosen, ActionIdentity(self.fallback_action, (context,)), 0.0, False, diagnostics)


def build_runtime(strategy, deck, **kwargs) -> AgentRuntime:
    """Construct the one shared runtime; injectable seams keep tests engine-independent."""

    return AgentRuntime(strategy, deck, **kwargs)


def _belief_from_snapshot(snapshot: OpponentSnapshot) -> OpponentBelief:
    scale = 1_000_000
    candidates = tuple((candidate.archetype, round(candidate.probability * scale))
                       for candidate in snapshot.candidates)
    card_ids = {card_id for candidate in snapshot.candidates
                for card_id in candidate.resources}
    expected = tuple((card_id, round(sum(
        candidate.probability * candidate.resources.get(card_id, 0.0)
        for candidate in snapshot.candidates) * scale))
                     for card_id in sorted(card_ids))
    return OpponentBelief(
        evidence=(("snapshot", snapshot.identity), ("archetypes", candidates)),
        probabilities=expected)


def _read_deck() -> list[int]:
    path = "deck.csv" if os.path.exists("deck.csv") else "/kaggle_simulations/agent/deck.csv"
    with open(path, encoding="utf-8") as handle:
        return [int(value) for value in handle.read().splitlines()[:60] if value.strip()]


def _int_field(mapping, key, default: int) -> int:
    """`int(mapping.get(key, default))` that survives present-but-None: the deployed dialect
    pads absent fields with None, and `or` would eat a legal 0."""
    value = (mapping or {}).get(key, default)
    return default if value is None else int(value)


def _last_resort_selection(observation: dict) -> list[int]:
    """Deterministic legal choice when planning cannot return. TOTAL by contract: this is the
    last shell before a forfeit, so any malformed shape degrades to the first offered index
    rather than raising a second time."""
    select = observation.get("select") or {}
    options = tuple(select.get("option") or ())
    try:
        return _last_resort_ranked(select, options, observation)
    except Exception:
        return [0] if options else []


def _last_resort_ranked(select, options, observation: dict) -> list[int]:
    context = _int_field(select, "context", -1)
    end_index = next((index for index, option in enumerate(options)
                      if isinstance(option, dict) and option.get("type") is not None
                      and int(option["type"]) == _END),
                     None)
    if context == 0 and end_index is not None:
        return [end_index]
    minimum = min(max(0, int(select.get("minCount") or 0)), len(options))
    maximum = min(max(minimum, int(select.get("maxCount") or 0)), len(options))
    if not options:
        return []
    if context == _TO_HAND:
        return list(range(maximum))
    if context in {_TO_BENCH, _TO_FIELD}:
        return list(range(max(minimum, min(1, maximum))))
    if context in {_DAMAGE, _DAMAGE_COUNTER, _DAMAGE_COUNTER_ANY}:
        players = ((observation.get("current") or {}).get("players") or ())
        counters = max(1, int(select.get("remainDamageCounter") or 1))

        def target(index):
            option = options[index]
            seat = int(option.get("playerIndex", 1))
            area = int(option.get("area", -1))
            player = players[seat] if 0 <= seat < len(players) and players[seat] else {}
            bodies = ((player.get("active") or ()) if area == 4 else
                      (player.get("bench") or ()) if area == 5 else ())
            position = option.get("index")
            body = (bodies[position] if isinstance(position, int)
                    and 0 <= position < len(bodies) else {})
            hp = int((body or {}).get("hp", 10 ** 9))
            # An already-KO'd body (hp <= 0) must sort last: it is going to be discarded once
            # the attack finishes resolving, so any further counter placed on it is pure waste.
            if hp <= 0:
                return (2, 0, index)
            return (0 if hp <= counters * 10 else 1, hp, index)

        return [min(range(len(options)), key=target)]
    if context in {_DRAW_COUNT, _DAMAGE_COUNTER_COUNT}:
        return [max(range(len(options)), key=lambda index: (
            int(options[index].get("number", -1)), -index))]
    return list(range(minimum))


def make_agent(strategy):
    """Create the Kaggle ``agent(observation)`` hook."""

    runtime = build_runtime(strategy, _read_deck())
    own_cards = OwnCardModel(runtime.deck)
    telemetry_on = os.environ.get("AGENT_NO_TELEMETRY") != "1"

    def agent(observation: dict) -> list[int]:
        if observation.get("select") is None:
            return list(runtime.deck)
        started = perf_counter()
        try:
            provisional = ObservationStateBuilder(runtime.deck).root(
                observation, knowledge=getattr(runtime, "knowledge", LegalKnowledge()))
            own_cards.observe(provisional)
            runtime.knowledge = reduce_knowledge(
                getattr(runtime, "knowledge", LegalKnowledge()),
                own_prizes=tuple(sorted((own_cards.prize_export() or {}).items())),
                known_top=own_cards.known_top_export() or ())
            decision = runtime.decide(observation)
        except Exception:                            # an uncaught raise forfeits the match
            traceback.print_exc(file=sys.stderr)
            chosen = _last_resort_selection(observation)
            print(f"last-resort submission after planning failure: {chosen}",
                  file=sys.stderr, flush=True)
            return chosen
        if telemetry_on:
            try:
                telemetry.emit(decision, opponent=runtime.opponent_snapshot,
                               seat=provisional.seat,
                               state=getattr(runtime, "last_state", provisional),
                               decision_seconds=perf_counter() - started,
                               decision_limit_seconds=runtime.last_decision_limit,
                               deadline_hit=runtime.last_deadline_hit)
            except Exception:                        # telemetry must never lose the match
                print("telemetry emit failed; decision preserved", file=sys.stderr, flush=True)
                traceback.print_exc(file=sys.stderr)
        return list(decision.chosen)

    agent.runtime = runtime
    return agent


__all__ = ["AgentRuntime", "build_runtime", "make_agent"]
