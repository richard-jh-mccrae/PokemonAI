"""The Bellman teacher runtime: the pre-Ledger brain, kept callable for pins and offline
corpus replay (ADR-0145/0149). It extends the live shell; nothing live imports it back."""
from __future__ import annotations

import json
import os
from pathlib import Path

from common.api import PlanRequest, RootDecision
from .card_worth import role_value
from common.runtime import AgentRuntime, _int_field, _last_resort_selection
from common.scouting.artifact import load_artifact
from common.scouting.pokemon_roles import general_pokemon_roles
from common.strategy import Roles
from .scouting import (LegacyRead, LegacyScout, evolution_line, load_legacy_briefs,
                       match_legacy_brief, resolve_brief_cards)
from .state import DecisionState

from .belief import BellmanDeckProfile, opponent_belief
from .budget_prototype import DecisionClock
from .effects import CardEffects
from .dragapult_potential import DragapultPotential
from .pilot_profile import PilotProfile
from .planner import BellmanTurnPlanner
from .potential import BoardPotential
from .providers import bellman_provider_factory
from .terminal import proof_lock_step
from .value import ValueRegistry


_STAGE_RANK = {"basic": 0, "stage1": 1, "stage2": 2}


def resolve_scouted_role_worth(read, artifact, stats, *, briefs=(), functions=None,
                               line_decay: float = 1.0):
    """Frozen matched-Brief valuation retained only inside the Bellman teacher."""
    expected = {}
    dossiers = getattr(artifact, "dossiers", {}) if artifact is not None else {}
    for candidate, probability in (read.candidates if read is not None else ()):
        brief = next((item for item in briefs if candidate in item.covers), None)
        ids_for_name = getattr(stats, "ids_for_name", None)
        if brief is not None and ids_for_name is not None:
            _threat_ids, target_roles = resolve_brief_cards(
                brief, ids_for_name, stat_for_id=getattr(stats, "get", None),
                forward_ids=getattr(stats, "forward_card_ids", None))
            candidate_worth = {}
            for row in brief.pokemon or ():
                roles = tuple(row.get("roles") or ())
                row_ids = {int(card_id) for card_id in ids_for_name(row.get("card", "")) or ()}
                generic = general_pokemon_roles(row_ids, stats)
                worth = role_value(roles)
                for card_id in row_ids:
                    combined = tuple(dict.fromkeys((*generic.get(card_id, ()), *roles)))
                    candidate_worth[card_id] = max(
                        candidate_worth.get(card_id, 0.0), role_value(combined))
                if "primary_attacker" in roles:
                    line_ids = evolution_line(
                        row_ids, ids_for_name, getattr(stats, "get", None),
                        getattr(stats, "forward_card_ids", None))
                    payoff_rank = max((_stage_rank(stats, card_id) for card_id in line_ids),
                                      default=0)
                    payoff_prizes = max((int(getattr(stats.get(card_id), "prize_value", 1) or 1)
                                         for card_id in line_ids), default=1)
                    for card_id in line_ids:
                        owed = max(0, payoff_rank - _stage_rank(stats, card_id))
                        candidate_worth[card_id] = max(candidate_worth.get(card_id, 0.0),
                                                       worth * payoff_prizes
                                                       * line_decay ** owed)
            primary_worth = role_value(("primary_attacker",))
            for card_id, role in target_roles.items():
                if role == "primary_attacker":
                    candidate_worth[card_id] = max(candidate_worth.get(card_id, 0.0),
                                                   primary_worth)
            for card_id, worth in candidate_worth.items():
                expected[card_id] = expected.get(card_id, 0.0) + probability * worth
            continue
        dossier = dossiers.get(candidate) or {}
        roles_by_card = {}
        for row in dossier.get("targets") or ():
            roles_by_card.setdefault(int(row["cardId"]), set()).add(str(row["role"]))
        for card_id, roles in roles_by_card.items():
            stat = stats.get(card_id) if stats is not None else None
            if "fragile_preevo" in roles and getattr(stat, "stage", None) not in (None, "basic"):
                roles = {*roles, "primary_attacker"}
            expected[card_id] = expected.get(card_id, 0.0) + probability * role_value(roles)
    return expected


def _stage_rank(stats, card_id):
    stat = stats.get(card_id) if stats is not None else None
    return _STAGE_RANK.get(str(getattr(stat, "stage", "") or "").lower(), 0)


def legacy_roles_resolve(declared: Roles, deck, stats, functions=None) -> Roles:
    """The pre-store resolution the teacher shipped with: stats-name evolution inference plus
    tag-inferred roles, deck declarations EXTENDING rather than replacing."""
    card_ids = tuple(sorted(set(int(card_id) for card_id in deck)))
    names = {}
    for card_id in card_ids:
        stat = stats.get(card_id) if stats is not None else None
        name = getattr(stat, "name", None)
        if name:
            names.setdefault(str(name), []).append(card_id)
    evolves = dict(declared.evolves)
    if not evolves:
        for target in card_ids:
            stat = stats.get(target) if stats is not None else None
            parents = names.get(str(getattr(stat, "evolvesFrom", "")), ())
            if len(parents) == 1:
                evolves[int(parents[0])] = target
    cards = general_pokemon_roles(card_ids, stats)
    for card_id, card_roles in declared.items():
        resolved = cards.setdefault(int(card_id), [])
        resolved.extend(role for role in card_roles if role not in resolved)
    relevant = {
        card_id for card_id, card_roles in cards.items()
        if any(role in card_roles for role in Roles._LINE_ROLE_PRIORITY)
    }
    changed = True
    while changed:
        changed = False
        for source, target in evolves.items():
            if target in relevant and source not in relevant:
                relevant.add(source)
                changed = True
    evolves = {
        source: target for source, target in evolves.items()
        if source in relevant and target in relevant
    }
    return Roles(cards, evolves=evolves, ready=declared.ready)


#: Deck-specific potential subclasses, keyed by strategy name (Strategy.potential_factory
#: left the live dataclass with the brain that consumed it).
DECK_POTENTIALS = {"dragapult_ex": DragapultPotential}


def _pilot_overlay() -> tuple[dict[str, float], str]:
    values = {}
    provenance = ""
    path = os.environ.get("AGENT_OVERLAY")
    if path:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        overrides = payload.get("pilot", {})
        if not isinstance(overrides, dict):
            raise ValueError("AGENT_OVERLAY.pilot must be an object")
        values = {**values, **overrides}
        provenance = str(Path(path).resolve())
    return {str(name): float(value) for name, value in values.items()}, provenance


class BellmanTeacherRuntime(AgentRuntime):
    """The deployment shell with the Bellman planner as its brain, exactly as it shipped."""

    fallback_backend = "bellman-fallback"
    fallback_action = "bellman_fallback"

    def __init__(self, strategy, deck, **kwargs):
        teacher_functions = kwargs.pop("functions", None)
        legacy_scout = kwargs.pop("scout", "default")
        legacy_briefs = kwargs.pop("briefs", "default")
        super().__init__(strategy, deck, **kwargs)
        self.scout = (LegacyScout(load_artifact(strict=True))
                      if legacy_scout == "default" else legacy_scout)
        self.briefs = (load_legacy_briefs()
                       if legacy_briefs == "default" else list(legacy_briefs or ()))
        self.last_read = LegacyRead()
        self.last_brief = None
        self.functions = teacher_functions
        self.effects = CardEffects.load()
        # The teacher's frozen contract predates the store-based resolution (ADR-0149):
        # re-resolve with the inference it shipped with before anything reads self.roles.
        self.roles = legacy_roles_resolve(strategy.roles, self.deck, self.stats, self.functions)
        self.potential_type = DECK_POTENTIALS.get(strategy.name, BoardPotential)
        self.registry = ValueRegistry.from_strategy(
            strategy=self.strategy, functions=self.functions, deck=self.deck,
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
        self.opponent_role_worth = {}
        self._plan_suffix = ()
        self._proof_suffix = ()
        self._proof_id = ""
        self._plan_reuse_stats = {"hits": 0, "planner_calls": 0, "invalidations": {}}

    def _reset_for_pregame(self) -> None:
        super()._reset_for_pregame()
        self.last_read = LegacyRead()
        self.last_brief = None
        self._plan_suffix = ()
        self._proof_suffix = ()
        self._proof_id = ""

    def _invalidate_plans(self) -> None:
        self._plan_suffix = ()
        self._proof_suffix = ()
        self._proof_id = ""

    def _observe_matchup(self, state):
        self.last_read = self.scout.observe(state) if self.scout is not None else LegacyRead()
        self.last_brief = match_legacy_brief(self.briefs, self.last_read)

    def _planner(self, observation):
        self._observe_matchup(observation)
        brief = self.last_brief
        current = observation.get("current") or {}
        seat = int(current.get("yourIndex", 0))
        belief = opponent_belief(
            observation, candidates=self.last_read.candidates,
            properties=(brief.opponent_properties if brief is not None else None))
        self.opponent_role_worth = resolve_scouted_role_worth(
            self.last_read, getattr(self.scout, "artifact", None), self.stats,
            briefs=self.briefs, functions=self.functions,
            line_decay=self.pilot_profile.get("scouting.line_distance_decay"))
        players = current.get("players") or ()
        opponent = (players[1 - seat] if len(players) == 2 and players[1 - seat] else {})
        bodies = tuple(body for body in
                       tuple(opponent.get("active") or ()) + tuple(opponent.get("bench") or ())
                       if body)                          # a facedown Active renders as [None]
        generic_roles = general_pokemon_roles(
            (body["id"] for body in bodies if body.get("id") is not None),
            self.stats)
        for card_id, card_roles in generic_roles.items():
            self.opponent_role_worth[card_id] = max(
                self.opponent_role_worth.get(card_id, 0.0), role_value(card_roles))
        potential = self.potential_type(
            registry=self.registry, profile=self.profile, root_seat=seat,
            opponent_role_worth=self.opponent_role_worth,
            isolated_selection=int((observation.get("select") or {}).get("context", 0)) != 0,
            opponent_hand_share=self.pilot_profile.get("value.opponent_hand_share"),
            root_observation=observation)
        planner_kwargs = {}
        if self.provider_factory is not None:
            planner_kwargs["provider_factory"] = bellman_provider_factory(self.provider_factory)
        if self.limits is not None:
            planner_kwargs["limits"] = self.limits
        return BellmanTurnPlanner(
            registry=self.registry, family_evaluator=potential,
            effects=self.effects, stats=self.stats, belief=belief,
            profile=self.pilot_profile, **planner_kwargs)

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

    def _decide_core(self, state, observation: dict) -> RootDecision:
        planner = self._planner(observation)
        request = PlanRequest(observation, self.deck, self.strategy.name)
        try:
            return self._planner_epoch(planner, request, observation, state)
        except Exception:
            planner.discard_precheck()               # release the retained native session
            raise

    def _planner_epoch(self, planner, request, observation, state) -> RootDecision:
        self.last_decision_limit = (
            self.decision_clock.external_seconds if self.decision_clock is not None
            else planner._epoch_seconds(request))
        proof_cached, _proof_invalidation = self._cached_proof_decision(planner, request)
        if proof_cached is not None:
            return proof_cached
        forced = self._forced_selection(state)
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

    def _fallback_selection(self, observation: dict) -> list[int]:
        return _last_resort_selection(observation)


def build_teacher_runtime(strategy, deck, **kwargs) -> BellmanTeacherRuntime:
    """Construct the teacher; the drop-in for the old ``build_runtime(..., brain="bellman")``."""

    return BellmanTeacherRuntime(strategy, deck, **kwargs)


__all__ = ["BellmanTeacherRuntime", "DECK_POTENTIALS", "build_teacher_runtime"]
