"""Bellman-only agent runtime shared by every deck."""
from __future__ import annotations

import gc
import json
import os
import sys
import traceback
from pathlib import Path
from time import perf_counter

from common import telemetry
from common.api import ActionIdentity, PlanRequest, RootDecision
from common.attack_locks import fold_attack_locks
from common.budget_prototype import DecisionClock
from common.cards import CardFunctions
from common.card_worth import role_value
from common.deck_tracker import OwnCardModel
from common.demand import StrategyBeamBuilder, semantic_action_key
from common.effects import CardEffects
from common.information import BellmanDeckProfile, opponent_belief
from common.planner import BellmanTurnPlanner
from common.potential import BoardPotential
from common.options import enumerate_legal_actions
from common.pilot_profile import PilotProfile
from common.pokemon_roles import general_pokemon_roles
from common.scouting.artifact import load_artifact
from common.scouting.briefs import load_briefs, match_brief, resolve_scouted_role_worth
from common.scouting.provider import EngineCardStatProvider
from common.scouting.read import Read, posture_gamma
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
from common.strategy.strategies import (
    GENERAL_STRATEGIES, activate_strategies, general_card_strategies, resolve_strategies,
)
from common.state import DecisionState
from common.value import ValueRegistry
from common.terminal import proof_lock_step


_ENGINE = object()


def _pilot_overlay() -> tuple[dict[str, float], str]:
    packaged = Path(__file__).resolve().parent.parent / "runtime_config.json"
    values = {}
    provenance = ""
    if packaged.exists():
        payload = json.loads(packaged.read_text(encoding="utf-8"))
        values = payload.get("pilot", {})
        if not isinstance(values, dict):
            raise ValueError("runtime_config.pilot must be an object")
        provenance = str(packaged)
    path = os.environ.get("AGENT_OVERLAY")
    if path:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        overrides = payload.get("pilot", {})
        if not isinstance(overrides, dict):
            raise ValueError("AGENT_OVERLAY.pilot must be an object")
        values = {**values, **overrides}
        provenance = str(Path(path).resolve())
    strategy_enabled = os.environ.get("AGENT_STRATEGY_ENABLED")
    if strategy_enabled is not None:
        if strategy_enabled not in {"0", "1"}:
            raise ValueError("AGENT_STRATEGY_ENABLED must be 0 or 1")
        values = {**values, "strategy.focus_enabled": float(strategy_enabled)}
        marker = f"strategy:{strategy_enabled}"
        provenance = f"{provenance};{marker}" if provenance else marker
    return {str(name): float(value) for name, value in values.items()}, provenance


class BellmanRuntime:
    """Deployment shell: declarative pregame handling plus one Bellman planner."""

    def __init__(self, strategy, deck, *, stats=_ENGINE, functions=_ENGINE,
                 scout=_ENGINE, briefs=_ENGINE, provider_factory=None, limits=None):
        self.strategy = strategy
        self.potential_type = strategy.potential_factory or BoardPotential
        self.deck = tuple(int(card_id) for card_id in deck)
        if stats is _ENGINE:
            stats = EngineCardStatProvider()
            stats.warm()
        self.stats = stats
        self.functions = CardFunctions.load() if functions is _ENGINE else functions
        self.effects = CardEffects.load()
        self.roles = strategy.roles.resolve(self.deck, self.stats, self.functions)
        if scout is _ENGINE:
            scout = Scout(load_artifact(), provider=self.stats)
        self.scout = scout
        self.briefs = load_briefs() if briefs is _ENGINE else list(briefs or ())
        self.provider_factory = provider_factory
        self.limits = limits
        self.registry = ValueRegistry.from_strategy(
            strategy=self.strategy, stats=self.stats, functions=self.functions, deck=self.deck,
            roles=self.roles)
        self.profile = BellmanDeckProfile.from_registry(self.registry)
        experiment, experiment_path = _pilot_overlay()
        pilot_overrides = dict(getattr(strategy, "pilot_overrides", {}))
        decision_seconds = os.environ.get("AGENT_DECISION_SECONDS")
        self.decision_clock = DecisionClock(float(decision_seconds)) \
            if decision_seconds is not None else None
        if decision_seconds is not None:
            pilot_overrides.update({
                "clock.adaptive_enabled": 0.0,
                "clock.remaining_200_seconds": self.decision_clock.bellman_seconds,
                # No `terminal.max_seconds` override: lifting it to 60s here let one abstention
                # eat 9s of a 10s decision and forfeit a match (ADR-0142).
            })
        self.pilot_profile = PilotProfile.resolve(
            global_values=experiment,
            authored_deck_overrides=pilot_overrides,
            provenance=(f"overlay:{experiment_path}" if experiment_path
                        else f"strategy:{strategy.name}"),
        )
        self.strategies = None
        self._strategy_snapshot = None
        self._strategy_history = ()
        self._strategy_ko_window_turn = -1
        self._strategy_previous_turn = -1
        self._strategy_previous_bodies = frozenset()
        self.last_brief = None
        self.opponent_role_worth = {}
        self._plan_suffix = ()
        self._proof_suffix = ()
        self._proof_id = ""
        self._plan_reuse_stats = {"hits": 0, "planner_calls": 0, "invalidations": {}}
        self.last_read = Read()
        self.last_decision_limit = None
        self.last_deadline_hit = False
        self._fallback_scope = None
        self._fallback_effect = None
        self._fallback_pending = False
        # Match-scoped: `logs` is a DELTA, so a lock spent two selections ago is no longer in the
        # observation. On the runtime so replay and test callers see the deployed board state.
        self._attack_locks: dict = {}

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

    def _planner(self, observation):
        self.last_read = self.scout.observe(observation) if self.scout is not None else Read()
        gamma = posture_gamma(self.last_read)
        brief = match_brief(self.briefs, self.last_read) if gamma > 0.0 else None
        self.last_brief = brief
        current = observation.get("current") or {}
        seat = int(current.get("yourIndex", 0))
        belief = opponent_belief(
            observation, candidates=self.last_read.candidates,
            properties=(brief.opponent_properties if brief is not None else None))
        self.opponent_role_worth = resolve_scouted_role_worth(
            self.last_read, getattr(self.scout, "artifact", None), self.stats,
            briefs=self.briefs, functions=self.functions)
        players = current.get("players") or ()
        opponent = (players[1 - seat] if len(players) == 2 and players[1 - seat] else {})
        bodies = tuple(body for body in
                       tuple(opponent.get("active") or ()) + tuple(opponent.get("bench") or ())
                       if body)                          # a facedown Active renders as [None]
        generic_roles = general_pokemon_roles(
            (body["id"] for body in bodies if body.get("id") is not None),
            self.stats, self.functions)
        for card_id, card_roles in generic_roles.items():
            self.opponent_role_worth[card_id] = max(
                self.opponent_role_worth.get(card_id, 0.0), role_value(card_roles))
        potential = self.potential_type(
            self.stats, registry=self.registry, profile=self.profile, root_seat=seat,
            opponent_role_worth=self.opponent_role_worth,
            isolated_selection=int((observation.get("select") or {}).get("context", 0)) != 0,
            opponent_hand_share=self.pilot_profile.get("value.opponent_hand_share"),
            root_observation=observation)
        planner_kwargs = {}
        if self.provider_factory is not None:
            planner_kwargs["provider_factory"] = self.provider_factory
        if self.limits is not None:
            planner_kwargs["limits"] = self.limits
        return BellmanTurnPlanner(
            registry=self.registry, family_evaluator=potential,
            effects=self.effects, stats=self.stats, belief=belief,
            profile=self.pilot_profile, **planner_kwargs)

    def _planning_epoch_strategy(self, observation):
        current = observation.get("current") or {}
        turn = int(current.get("turn", 0))
        seat = int(current.get("yourIndex", 0))
        players = current.get("players") or ()
        player = players[seat] if 0 <= seat < len(players) else {}
        bodies = tuple(player.get("active") or ()) + tuple(player.get("bench") or ())
        serials = frozenset(int(body.get("serial", -1)) for body in bodies if body)
        lost_between_turns = (
            self._strategy_previous_turn >= 0
            and turn > self._strategy_previous_turn
            and bool(self._strategy_previous_bodies - serials)
        )
        if lost_between_turns:
            self._strategy_ko_window_turn = turn
        self._strategy_previous_turn = turn
        self._strategy_previous_bodies = serials
        if self._strategy_ko_window_turn == turn:
            observation["strategyPokemonKoWindow"] = True
        card_strategies = general_card_strategies(
            self.deck, self.roles, self.functions, self.stats, self.effects
        ) if self.strategy.params.get("use_general_card_strategies") else ()
        self.strategies = resolve_strategies(
            (*GENERAL_STRATEGIES, *card_strategies),
            getattr(self.strategy, "strategies", ()),
            getattr(self.last_brief, "strategies", ()) if self.last_brief is not None else (),
            getattr(self.strategy, "strategy_overrides", ()),
        )
        candidate = activate_strategies(
            observation, self.strategies, roles=self.roles, stats=self.stats,
            effects=self.effects,
            opponent_role_worth=self.opponent_role_worth)
        if any(hint.strategy_id.endswith(".deploy_after_ko") for hint in candidate.hints):
            self._strategy_ko_window_turn = turn
        history = tuple(json.dumps(row, sort_keys=True, separators=(",", ":"))
                        for row in observation.get("logs") or ())
        same_history = (len(history) >= len(self._strategy_history)
                        and history[:len(self._strategy_history)] == self._strategy_history)
        if (self._strategy_snapshot is not None
                and self._strategy_snapshot.snapshot_id == candidate.snapshot_id
                and same_history):
            return self._strategy_snapshot
        self._strategy_snapshot = candidate
        self._strategy_history = history
        return candidate

    def _cached_decision(self, planner, request):
        stats = getattr(self, "_plan_reuse_stats", None)
        if stats is None:
            stats = self._plan_reuse_stats = {"hits": 0, "planner_calls": 0, "invalidations": {}}
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
            (step.expected_state_key == state.plan_key, "semantic_state_changed"),
        )
        failure = next((reason for valid, reason in guards if not valid), None)
        if failure is not None:
            self._plan_suffix = ()
            invalidations = stats["invalidations"]
            invalidations[failure] = invalidations.get(failure, 0) + 1
            return None, failure
        action = next((candidate for candidate in state.legal_actions
                       if candidate.identity == step.action), None)
        if action is None:
            self._plan_suffix = ()
            failure = "planned_action_missing"
            invalidations = stats["invalidations"]
            invalidations[failure] = invalidations.get(failure, 0) + 1
            return None, failure
        self._plan_suffix = self._plan_suffix[1:]
        stats["hits"] += 1
        return RootDecision(
            action.selection, action.identity, step.value, True,
            {"backend": "plan-suffix", "profile_hash": self.pilot_profile.hash,
             "terminal_proof": getattr(planner, "last_terminal_diagnostics", {
                 "attempted": False, "result": "skipped", "reason": "unavailable"}),
             "plan_suffix": {"hit": True, "remaining": len(self._plan_suffix),
                             "hits": stats["hits"],
                             "planner_calls_avoided": stats["hits"]}},
            self._plan_suffix,
        ), "hit"

    def _cached_proof_decision(self, planner, request):
        suffix = getattr(self, "_proof_suffix", ())
        if not suffix:
            return None, "empty"
        state = planner.state_for(request)
        step, failure = proof_lock_step(
            suffix, state, profile_hash=self.pilot_profile.hash,
            proof_id=getattr(self, "_proof_id", ""))
        if failure is not None:
            self._proof_suffix = ()
            self._proof_id = ""
            return None, failure
        action = next((candidate for candidate in state.legal_actions
                       if candidate.identity == step.action), None)
        if action is None:
            self._proof_suffix = ()
            self._proof_id = ""
            return None, "planned_action_missing"
        self._proof_suffix = tuple(candidate for candidate in suffix if candidate is not step)
        return RootDecision(
            action.selection, action.identity, 0.0, True,
            {"backend": "terminal-proof-lock", "terminal_proof": {
                "attempted": False, "result": "replayed", "reason": "lock_hit",
                "proof_id": step.proof_id, "remaining": len(self._proof_suffix),
                "lock_event": "replayed"}},
            self._proof_suffix,
        ), "hit"

    @staticmethod
    def _with_proof_invalidation(decision, reason):
        if reason in {"empty", "hit"}:
            return decision
        diagnostics = dict(decision.diagnostics)
        terminal = dict(diagnostics.get("terminal_proof", {}))
        terminal.update({"lock_event": "invalidated", "lock_reason": reason})
        diagnostics["terminal_proof"] = terminal
        return RootDecision(
            decision.chosen, decision.action, decision.value, decision.complete,
            diagnostics, decision.plan_suffix)

    def _forced_selection(self, observation):
        select = observation.get("select") or {}
        options = tuple(select.get("option") or ())
        minimum = int(select.get("minCount", 0))
        maximum = int(select.get("maxCount", len(options)))
        if len(options) > 1 or minimum != maximum or minimum != len(options):
            return None
        self._plan_suffix = ()
        self._proof_suffix = ()
        self._proof_id = ""
        return RootDecision(
            tuple(range(len(options))), ActionIdentity(
                "forced_selection", (int(select.get("context", -1)),)),
            0.0, True, {"backend": "forced-selection", "context": select.get("context"),
                        "option_count": len(options)})

    def decide(self, observation: dict) -> RootDecision:
        self.last_deadline_hit = False
        self.last_decision_limit = None
        current = observation.get("current") or {}
        if int(current.get("turn", 0)) <= 0:
            self._plan_suffix = ()
            self._proof_suffix = ()
            self._proof_id = ""
            self.last_read = Read()
            self._strategy_snapshot = None
            self._attack_locks = {}
            return self._pregame(observation)
        # Above every early return: a selection answered by the Strategy fallback still has to
        # contribute its ATTACK rows, or the delta carries them away for good.
        self._attack_locks = fold_attack_locks(
            self._attack_locks, observation.get("logs"), stats=self.stats,
            turn=int(current.get("turn", 0)))
        if self._attack_locks:
            observation["attack_locks"] = self._attack_locks
        scope = (int(current.get("turn", 0)), int(current.get("yourIndex", 0)))
        select = observation.get("select") or {}
        context = int(select.get("context", -1))
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
            decision = self._decide_with_planner(observation)
            production = (decision.diagnostics.get("production") or {})
            if bool(production.get("deadline_hit")):
                if context == 0:
                    self._fallback_pending = production.get("execution_tier") == "recoverable"
                else:
                    self._fallback_scope = scope
                    self._fallback_effect = effect_key
            return decision
        except Exception as exc:
            return self._fallback_decision(observation, f"exception:{type(exc).__name__}")
        finally:
            if collector_was_enabled:
                gc.enable()

    def _fallback_decision(self, observation: dict, cause: str) -> RootDecision:
        chosen = tuple(self._strategy_fallback_selection(observation))
        select = observation.get("select") or {}
        current = observation.get("current") or {}
        if int(select.get("context", -1)) != 0:
            self._fallback_scope = (
                int(current.get("turn", 0)), int(current.get("yourIndex", 0)))
            effect = select.get("effect") or {}
            self._fallback_effect = (tuple(effect.get(key) for key in (
                "playerIndex", "id", "serial")) if effect else self._fallback_effect)
        self._plan_suffix = ()
        self._proof_suffix = ()
        diagnostics = {
            "backend": "strategy-fallback",
            "fallback": {"cause": cause, "latched": self._fallback_scope is not None,
                         "context": int(select.get("context", -1)), "chosen": chosen},
        }
        return RootDecision(
            chosen, ActionIdentity("strategy_fallback", (int(select.get("context", -1)),)),
            0.0, False, diagnostics)

    def _strategy_fallback_selection(self, observation: dict) -> list[int]:
        default = _last_resort_selection(observation)
        try:
            snapshot = self._planning_epoch_strategy(observation)
            state = DecisionState.from_observation(
                observation, deck=self.deck, deck_name=self.strategy.name,
                value_registry_identity=self.registry.identity)
            actions = enumerate_legal_actions(observation)
            builder = StrategyBeamBuilder(
                snapshot, effects=self.effects, stats=self.stats, registry=self.registry,
                width=int(self.pilot_profile.get("strategy.focus_width")),
                information_partition=(self.pilot_profile.get(
                    "strategy.information_partition_enabled") >= 0.5))
            ranked = builder.rank_legal(state, actions)
            focused = builder.last_beam.focused if builder.last_beam is not None else ()
            if not focused:
                return default
            focused_keys = {row.action_key for row in focused}
            action = next((row for row in ranked
                           if semantic_action_key(row) in focused_keys), None)
            if action is None:
                return default
            select = observation.get("select") or {}
            context = int(select.get("context", -1))
            if context == _TO_HAND:
                maximum = min(len(select.get("option") or ()),
                              int(select.get("maxCount", len(action.selection))))
                remainder = [index for index in range(len(select.get("option") or ()))
                             if index not in action.selection]
                return list((*action.selection, *remainder)[:maximum])
            return list(action.selection) if action.selection else default
        except Exception:
            return default

    def _decide_with_planner(self, observation: dict) -> RootDecision:
        planner = self._planner(observation)
        request = PlanRequest(observation, self.deck, self.strategy.name)
        try:
            return self._planner_epoch(planner, request, observation)
        except Exception:
            planner.discard_precheck()               # release the retained native session
            raise

    def _planner_epoch(self, planner, request, observation) -> RootDecision:
        self.last_decision_limit = (
            self.decision_clock.external_seconds if self.decision_clock is not None
            else planner._epoch_seconds(request))
        proof_cached, _proof_invalidation = self._cached_proof_decision(planner, request)
        if proof_cached is not None:
            return proof_cached
        forced = self._forced_selection(observation)
        if forced is not None:
            return forced
        proof = planner.prove(request)
        if proof is not None:
            self._proof_suffix = proof.plan_suffix
            self._proof_id = str(proof.diagnostics["terminal_proof"]["proof_id"])
            self._plan_suffix = ()
            return self._with_proof_invalidation(proof, _proof_invalidation)
        cached, invalidation = self._cached_decision(planner, request)
        if cached is not None:
            planner.discard_precheck()
            return self._with_proof_invalidation(cached, _proof_invalidation)
        self._plan_reuse_stats["planner_calls"] += 1
        planner.strategy_snapshot = (
            self._planning_epoch_strategy(observation)
            if self.pilot_profile.get("strategy.focus_enabled") >= 0.5 else None)
        decision = planner.decide(request, terminal_checked=True)
        self._proof_suffix = ()
        self._proof_id = ""
        self._plan_suffix = decision.plan_suffix
        diagnostics = dict(decision.diagnostics)
        if _proof_invalidation not in {"empty", "hit"}:
            terminal = dict(diagnostics.get("terminal_proof", {}))
            terminal.update({"lock_event": "invalidated", "lock_reason": _proof_invalidation})
            diagnostics["terminal_proof"] = terminal
        diagnostics["plan_suffix"] = {
            "hit": False, "invalidation": invalidation,
            "cached_steps": len(self._plan_suffix),
            "hits": self._plan_reuse_stats["hits"],
            "planner_calls": self._plan_reuse_stats["planner_calls"],
            "planner_calls_avoided": self._plan_reuse_stats["hits"],
            "invalidations": dict(self._plan_reuse_stats["invalidations"]),
        }
        self.last_deadline_hit = bool(
            (diagnostics.get("production") or {}).get("deadline_hit", False))
        return RootDecision(decision.chosen, decision.action, decision.value,
                            decision.complete, diagnostics, decision.plan_suffix)


def build_runtime(strategy, deck, **kwargs) -> BellmanRuntime:
    """Construct the one shared runtime; injectable seams keep tests engine-independent."""

    return BellmanRuntime(strategy, deck, **kwargs)


def _read_deck() -> list[int]:
    path = "deck.csv" if os.path.exists("deck.csv") else "/kaggle_simulations/agent/deck.csv"
    with open(path, encoding="utf-8") as handle:
        return [int(value) for value in handle.read().splitlines()[:60] if value.strip()]


def _last_resort_selection(observation: dict) -> list[int]:
    """Deterministic legal choice when planning cannot return."""
    select = observation.get("select") or {}
    options = tuple(select.get("option") or ())
    context = int(select.get("context", -1))
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
            hp = max(0, int((body or {}).get("hp", 10 ** 9)))
            return (0 if hp <= counters * 10 else 1, hp, index)

        return [min(range(len(options)), key=target)]
    if context in {_DRAW_COUNT, _DAMAGE_COUNTER_COUNT}:
        return [max(range(len(options)), key=lambda index: (
            int(options[index].get("number", -1)), -index))]
    return list(range(minimum))


def make_agent(strategy):
    """Create the Kaggle ``agent(observation)`` hook."""

    runtime = build_runtime(strategy, _read_deck())
    own_cards = OwnCardModel(runtime.deck, effects=runtime.effects)
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


__all__ = ["BellmanRuntime", "build_runtime", "make_agent"]
