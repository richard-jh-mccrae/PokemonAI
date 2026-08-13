"""Bellman-only agent runtime shared by every deck."""
from __future__ import annotations

import os

from common import telemetry
from common.api import ActionIdentity, PlanRequest, RootDecision
from common.cards import CardFunctions
from common.deck_tracker import OwnCardModel
from common.effects import CardEffects
from common.information import BellmanDeckProfile, opponent_belief
from common.planner import BellmanTurnPlanner
from common.potential import BoardPotential
from common.pilot_profile import PilotProfile
from common.scouting.artifact import load_artifact
from common.scouting.briefs import load_briefs, match_brief, resolve_scouted_role_worth
from common.scouting.provider import EngineCardStatProvider
from common.scouting.read import Read, posture_gamma
from common.scouting.scout import Scout
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
from common.value import ValueRegistry


_ENGINE = object()


class BellmanRuntime:
    """Deployment shell: declarative pregame handling plus one Bellman planner."""

    def __init__(self, strategy, deck, *, stats=_ENGINE, functions=_ENGINE,
                 scout=_ENGINE, briefs=_ENGINE, provider_factory=None, limits=None):
        self.strategy = strategy
        self.deck = tuple(int(card_id) for card_id in deck)
        if stats is _ENGINE:
            stats = EngineCardStatProvider()
            stats.warm()
        self.stats = stats
        self.functions = CardFunctions.load() if functions is _ENGINE else functions
        self.effects = CardEffects.load()
        if scout is _ENGINE:
            scout = Scout(load_artifact(), provider=self.stats)
        self.scout = scout
        self.briefs = load_briefs() if briefs is _ENGINE else list(briefs or ())
        self.provider_factory = provider_factory
        self.limits = limits
        self.registry = ValueRegistry.from_strategy(
            strategy=self.strategy, stats=self.stats, functions=self.functions, deck=self.deck)
        self.profile = BellmanDeckProfile.from_registry(self.registry)
        self.pilot_profile = PilotProfile.resolve(
            authored_deck=getattr(strategy, "pilot_adjustments", {}),
            provenance=f"strategy:{strategy.name}",
        )
        self._plan_suffix = ()
        self.last_read = Read()

    @staticmethod
    def _player(observation, seat):
        players = ((observation.get("current") or {}).get("players") or ())
        return players[seat] if 0 <= seat < len(players) and players[seat] else {}

    def _option_card_id(self, observation, option, seat: int) -> int | None:
        if int(option.get("type", -1)) != _CARD or option.get("area") != _HAND:
            return None
        owner = int(option.get("playerIndex", seat))
        hand = self._player(observation, owner).get("hand") or ()
        index = option.get("index")
        if not isinstance(index, int) or not 0 <= index < len(hand) or not hand[index]:
            return None
        return int(hand[index]["id"])

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
                       key=lambda index: int(options[index].get("number", 0)), default=None)
            chosen, action = ((pick,) if pick is not None else (), "free_draw_count")
        else:
            minimum = min(int(select.get("minCount", 0)), len(options))
            chosen = tuple(range(minimum))
        return RootDecision(
            chosen, ActionIdentity(action, (context,)), 0.0, True,
            {"backend": "declarative-pregame", "context": context},
        )

    def _planner(self, observation):
        self.last_read = self.scout.observe(observation) if self.scout is not None else Read()
        gamma = posture_gamma(self.last_read)
        brief = match_brief(self.briefs, self.last_read) if gamma > 0.0 else None
        current = observation.get("current") or {}
        seat = int(current.get("yourIndex", 0))
        belief = opponent_belief(
            observation, candidates=self.last_read.candidates,
            properties=(brief.opponent_properties if brief is not None else None))
        potential = BoardPotential(
            self.stats, registry=self.registry, profile=self.profile, root_seat=seat,
            opponent_role_worth=resolve_scouted_role_worth(
                self.last_read, getattr(self.scout, "artifact", None), self.stats,
                briefs=self.briefs),
            isolated_selection=int((observation.get("select") or {}).get("context", 0)) != 0)
        planner_kwargs = {}
        if self.provider_factory is not None:
            planner_kwargs["provider_factory"] = self.provider_factory
        if self.limits is not None:
            planner_kwargs["limits"] = self.limits
        return BellmanTurnPlanner(
            registry=self.registry, family_evaluator=potential,
            effects=self.effects, stats=self.stats, belief=belief,
            profile=self.pilot_profile, **planner_kwargs)

    def _cached_decision(self, planner, request):
        if not self._plan_suffix or self.pilot_profile.get("plan_reuse.enabled") < 0.5:
            return None, "empty"
        step = self._plan_suffix[0]
        state = planner.state_for(request)
        current = state.obs.get("current") or {}
        guards = (
            (step.profile_hash == self.pilot_profile.hash, "profile_changed"),
            (step.turn == int(current.get("turn", 0)), "turn_changed"),
            (step.seat == int(current.get("yourIndex", 0)), "seat_changed"),
            (step.legal_menu_digest == state.legal_menu_digest, "legal_menu_changed"),
            (step.expected_state_key == state.semantic_key, "semantic_state_changed"),
        )
        failure = next((reason for valid, reason in guards if not valid), None)
        if failure is not None:
            self._plan_suffix = ()
            return None, failure
        self._plan_suffix = self._plan_suffix[1:]
        return RootDecision(
            step.chosen, step.action, 0.0, True,
            {"backend": "plan-suffix", "profile_hash": self.pilot_profile.hash,
             "plan_suffix": {"hit": True, "remaining": len(self._plan_suffix)}},
            self._plan_suffix,
        ), "hit"

    def decide(self, observation: dict) -> RootDecision:
        current = observation.get("current") or {}
        if int(current.get("turn", 0)) <= 0:
            self._plan_suffix = ()
            self.last_read = Read()
            return self._pregame(observation)
        planner = self._planner(observation)
        request = PlanRequest(observation, self.deck, self.strategy.name)
        cached, invalidation = self._cached_decision(planner, request)
        if cached is not None:
            return cached
        decision = planner.decide(request)
        self._plan_suffix = decision.plan_suffix
        diagnostics = dict(decision.diagnostics)
        diagnostics["plan_suffix"] = {
            "hit": False, "invalidation": invalidation,
            "cached_steps": len(self._plan_suffix),
        }
        return RootDecision(decision.chosen, decision.action, decision.value,
                            decision.complete, diagnostics, decision.plan_suffix)


def build_runtime(strategy, deck, **kwargs) -> BellmanRuntime:
    """Construct the one shared runtime; injectable seams keep tests engine-independent."""

    return BellmanRuntime(strategy, deck, **kwargs)


def _read_deck() -> list[int]:
    path = "deck.csv" if os.path.exists("deck.csv") else "/kaggle_simulations/agent/deck.csv"
    with open(path, encoding="utf-8") as handle:
        return [int(value) for value in handle.read().splitlines()[:60] if value.strip()]


def make_agent(strategy):
    """Create the Kaggle ``agent(observation)`` hook."""

    runtime = build_runtime(strategy, _read_deck())
    own_cards = OwnCardModel(runtime.deck)
    telemetry_on = os.environ.get("AGENT_NO_TELEMETRY") != "1"

    def agent(observation: dict) -> list[int]:
        if observation.get("select") is None:
            return list(runtime.deck)
        own_cards.observe(observation)
        observation["own_prizes"] = own_cards.prize_export()
        decision = runtime.decide(observation)
        if telemetry_on:
            telemetry.emit(decision, read=runtime.last_read)
        return list(decision.chosen)

    agent.runtime = runtime
    return agent


__all__ = ["BellmanRuntime", "build_runtime", "make_agent"]
