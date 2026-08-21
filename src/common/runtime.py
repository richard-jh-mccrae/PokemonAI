"""Agent runtime shared by every deck: declarative pregame plus the Ledger decider."""
from __future__ import annotations

import gc
import os
import sys
import traceback
from time import perf_counter

from common import telemetry
from common.api import ActionIdentity, RootDecision
from common.cards.functions.attack_lock import fold_attack_locks
from common.cards import CardFunctions
from common.deck_tracker import OwnCardModel
from common.ledger import LedgerContext, LedgerDecider, preview_provider_factory
from common.scouting.artifact import load_artifact
from common.scouting.briefs import load_briefs
from common.scouting.provider import EngineCardStatProvider
from common.scouting.read import Read
from common.scouting.scout import Scout
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


class AgentRuntime:
    """Deployment shell: declarative pregame, forced selections, and the Ledger (ADR-0145/0149);
    the Bellman teacher extends this shell from ``deprecated/bellman/runtime.py``."""

    def __init__(self, strategy, deck, *, stats=_ENGINE, functions=_ENGINE,
                 scout=_ENGINE, briefs=_ENGINE, provider_factory=None, limits=None):
        self.strategy = strategy
        self.deck = tuple(int(card_id) for card_id in deck)
        if stats is _ENGINE:
            stats = EngineCardStatProvider()
            stats.warm()
        self.stats = stats
        self.functions = CardFunctions.load() if functions is _ENGINE else functions
        self.roles = strategy.roles.resolve(self.deck)
        if scout is _ENGINE:
            scout = Scout(load_artifact(), provider=self.stats)
        self.scout = scout
        self.briefs = load_briefs() if briefs is _ENGINE else list(briefs or ())
        self.provider_factory = provider_factory
        self.limits = limits
        self.last_brief = None
        self.last_read = Read()
        self.last_decision_limit = None
        self.last_deadline_hit = False
        self._fallback_scope = None
        self._fallback_effect = None
        self._fallback_pending = False
        # Match-scoped: `logs` is a DELTA, so a lock spent two selections ago is no longer in the
        # observation. On the runtime so replay and test callers see the deployed board state.
        self._attack_locks: dict = {}
        self.ledger = LedgerDecider(
            self.deck, strategy.name,
            LedgerContext.build(
                roles={card_id: tuple(self.roles.get(card_id, ()) or ())
                       for card_id in self.deck},
                overrides=getattr(strategy, "ledger_overrides", None)),
            provider_factory=preview_provider_factory(self.provider_factory))

    @staticmethod
    def _player(observation, seat):
        players = ((observation.get("current") or {}).get("players") or ())
        return players[seat] if 0 <= seat < len(players) and players[seat] else {}

    def _option_card_id(self, observation, option, seat: int) -> int | None:
        option_type = option.get("type")             # 0 is a legal type; `or` would eat it
        if option_type is None or int(option_type) != _CARD or option.get("area") != _HAND:
            return None
        owner = option.get("playerIndex")                # present-but-None on the engine shape
        owner = seat if owner is None else int(owner)
        hand = self._player(observation, owner).get("hand") or ()
        index = option.get("index")
        if not isinstance(index, int) or not 0 <= index < len(hand) or not hand[index]:
            return None
        card_id = hand[index].get("id")
        return int(card_id) if card_id is not None else None

    @staticmethod
    def _option_of_type(options, option_type: int) -> int | None:
        return next((index for index, option in enumerate(options)
                     if int(option.get("type", -1)) == option_type), None)

    def _hand_has_setup_starter(self, observation, seat: int) -> bool:
        """Whether the hand can legally supply the setup Active.

        Printed setup abilities are represented by the portable ``opener`` function tag.  They are
        legal starters even when the card's ordinary evolution stage is not Basic.
        """
        for card in self._player(observation, seat).get("hand") or ():
            stat = self.stats.get(card.get("id")) if card and self.stats else None
            card_id = int(card["id"]) if card and card.get("id") is not None else None
            tags = self.functions.tags(card_id) if card_id is not None and self.functions else ()
            if (stat is not None and stat.is_pokemon
                    and (stat.stage == "basic" or "opener" in tags)):
                return True
        return False

    def _pregame(self, observation) -> RootDecision:
        current = observation.get("current") or {}
        seat = int(current.get("yourIndex", 0))
        select = observation.get("select") or {}
        options = select.get("option") or ()
        context = int(select.get("context", -1))
        chosen: tuple[int, ...]
        action = "pregame"
        if context == _SETUP_ACTIVE:
            offered = {card_id: index for index, option in enumerate(options)
                       if (card_id := self._option_card_id(observation, option, seat)) is not None}
            pick = next((offered[card_id] for card_id in self.strategy.starter_priority
                         if card_id in offered), None)
            chosen = (pick if pick is not None else 0,) if options else ()
            action = "setup_active"
        elif context == _SETUP_BENCH and int(select.get("minCount", 0)) == 0:
            chosen, action = (), "setup_bench_decline"
        elif context == _IS_FIRST:
            preferred = str(self.strategy.params.get("preferred_start", "second"))
            option_type = _YES if preferred == "first" else _NO
            pick = self._option_of_type(options, option_type)
            chosen, action = ((pick if pick is not None else 0,), "choose_start")
        elif context == _MULLIGAN:
            option_type = _NO if self._hand_has_setup_starter(observation, seat) else _YES
            pick = self._option_of_type(options, option_type)
            chosen, action = ((pick if pick is not None else 0,), "mulligan")
        elif context == _DRAW_COUNT:
            # Taking a free mulligan draw cannot remove information or a held option.  The
            # numerically largest offered count therefore dominates every smaller count.
            pick = max(range(len(options)),
                       key=lambda index: int(options[index].get("number") or 0), default=None)
            chosen, action = ((pick,) if pick is not None else (), "free_draw_count")
        else:
            minimum = min(int(select.get("minCount", 0)), len(options))
            chosen = tuple(range(minimum))
        return RootDecision(
            chosen, ActionIdentity(action, (context,)), 0.0, True,
            {"backend": "declarative-pregame", "context": context},
        )

    def _reset_for_pregame(self) -> None:
        """Match-boundary state clearing; the teacher extends this with its plan caches."""
        self.last_read = Read()
        self._attack_locks = {}

    def _invalidate_plans(self) -> None:
        """The Ledger holds no cross-decision plan state; the Bellman teacher overrides."""

    def _forced_selection(self, observation):
        select = observation.get("select") or {}
        options = tuple(select.get("option") or ())
        minimum = _int_field(select, "minCount", 0)
        maximum = _int_field(select, "maxCount", len(options))
        if len(options) > 1 or minimum != maximum or minimum != len(options):
            return None
        self._invalidate_plans()
        return RootDecision(
            tuple(range(len(options))), ActionIdentity(
                "forced_selection", (int(select.get("context", -1)),)),
            0.0, True, {"backend": "forced-selection", "context": select.get("context"),
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
        current = observation.get("current") or {}
        if _int_field(current, "turn", 0) <= 0:
            self._reset_for_pregame()
            return self._pregame(observation)
        # Above every early return: a selection answered by the fallback still has to
        # contribute its ATTACK rows, or the delta carries them away for good.
        self._attack_locks = fold_attack_locks(
            self._attack_locks, observation.get("logs"),
            turn=_int_field(current, "turn", 0))
        if self._attack_locks:
            observation["attack_locks"] = self._attack_locks
        scope = (_int_field(current, "turn", 0), _int_field(current, "yourIndex", 0))
        select = observation.get("select") or {}
        context = _int_field(select, "context", -1)
        effect = select.get("effect") or {}
        effect_key = tuple(effect.get(key) for key in ("playerIndex", "id", "serial")) \
            if effect else None
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
            decision = self._decide_core(observation)
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

    def _decide_core(self, observation: dict) -> RootDecision:
        forced = self._forced_selection(observation)
        if forced is not None:
            return forced
        return self.ledger.decide(observation)

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
            own_cards.observe(observation)
            observation["own_prizes"] = own_cards.prize_export()
            observation["known_top"] = own_cards.known_top_export()
            decision = runtime.decide(observation)
        except Exception:                            # an uncaught raise forfeits the match
            traceback.print_exc(file=sys.stderr)
            chosen = _last_resort_selection(observation)
            print(f"last-resort submission after planning failure: {chosen}",
                  file=sys.stderr, flush=True)
            return chosen
        if telemetry_on:
            try:
                seat = int((observation.get("current") or {}).get("yourIndex", 0))
                telemetry.emit(decision, read=runtime.last_read, seat=seat,
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
