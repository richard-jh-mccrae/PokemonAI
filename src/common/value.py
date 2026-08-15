"""One Bellman benefit/cost ledger over canonical board potentials."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Callable, Mapping

from common.card_worth import (
    ACE_SPEC_TIER, ENERGY_TIER, FUNCTION_TIER, KNOWN_CARD_FLOOR, ROLE_TIER, TAG_TIER, role_value,
)

from .algebra import Ledger
from .api import ActionIdentity
from .state import DecisionState


WORTH_PER_PRIZE = 120.0
MIN_EVOLUTION_LINE_LENGTH = 2


def worth_to_prizes(worth: float) -> float:
    """Cross portable card Worth into Bellman's prize-denominated currency."""
    return float(worth) / WORTH_PER_PRIZE

FAMILY_OWNERS = {
    "prize_race": ("game", "prizes", "prize proximity"),
    "prize_plan": ("own KO ordering", "prize-route availability"),
    "damage": ("damage progress",),
    "readiness": ("reachable attack value",),
    "multi_target_ko": ("simultaneous Active and Bench knockout readiness",),
    "board": ("in-play resource value",),
    "energy_position": ("usable attached resources", "survival", "saturation"),
    "development": ("completed evolution development",),
    "hand": ("accessible future-turn resources",),
    "hand_demand": ("visible missing board jobs", "prospective hand access"),
    "opponent_roles": ("scouted opponent role pressure",),
}


@dataclass(frozen=True)
class CardFacts:
    known: bool = True
    ace_spec: bool = False
    typed_basic_energy: bool = False
    pokemon: bool = False
    stage: str | None = None
    prize_value: int = 1
    energy_type: int | None = None
    bench_damage: int = 0


@dataclass(frozen=True)
class WorthSeeds:
    roles: tuple[tuple[str, float], ...] = tuple(sorted(ROLE_TIER.items()))
    functions: tuple[tuple[str, float], ...] = tuple(sorted(FUNCTION_TIER.items()))
    behavioural: tuple[tuple[str, float], ...] = tuple(sorted(TAG_TIER.items()))
    energy: float = ENERGY_TIER
    ace_spec: float = ACE_SPEC_TIER
    known_floor: float = KNOWN_CARD_FLOOR
    prize_rate: float = 1.0 / WORTH_PER_PRIZE


class ValueRegistry:
    """Portable card Worth plus upward-only deck declarations."""

    def __init__(self, *, roles: Mapping[int, tuple[str, ...]] | None = None,
                 functions: Mapping[int, tuple[str, ...]] | None = None,
                 facts: Mapping[int, CardFacts] | None = None,
                 overrides: Mapping[int, float] | None = None,
                 line_bases=(), line_pairs=(), lines=(), partners=None,
                 prize_routes=(), prizes_to_win=None,
                 seeds: WorthSeeds = WorthSeeds()):
        self.roles = {int(key): tuple(value) for key, value in (roles or {}).items()}
        for card_id in line_bases:
            card_roles = self.roles.get(int(card_id), ())
            if "win_condition_base" not in card_roles:
                self.roles[int(card_id)] = (*card_roles, "win_condition_base")
        self.functions = {int(key): tuple(value) for key, value in (functions or {}).items()}
        self.facts = {int(key): value for key, value in (facts or {}).items()}
        self.overrides = {int(key): max(0.0, float(value)) for key, value in (overrides or {}).items()}
        self.line_parents = {int(top): int(base) for base, top in line_pairs}
        self.lines = tuple(tuple(int(card_id) for card_id in line) for line in lines)
        self.partners = {int(card_id): tuple(int(partner) for partner in values)
                         for card_id, values in (partners or {}).items()}
        self.prize_routes = tuple(tuple(int(card_id) for card_id in route)
                                  for route in prize_routes)
        self.prizes_to_win = None if prizes_to_win is None else int(prizes_to_win)
        self.seeds = seeds

    @classmethod
    def from_strategy(cls, *, strategy, stats, functions, deck) -> "ValueRegistry":
        card_ids = set(int(card_id) for card_id in deck)
        roles = {card_id: tuple((getattr(strategy, "roles", {}) or {}).get(card_id, ()))
                 for card_id in card_ids}
        tags = {card_id: tuple(functions.tags(card_id)) if functions else () for card_id in card_ids}
        facts = {}
        for card_id in card_ids:
            stat = stats.get(card_id) if stats else None
            attacks = (tuple(stats.attack(attack_id) for attack_id in getattr(stat, "attacks", ()) or ())
                       if stat is not None and hasattr(stats, "attack") else ())
            facts[card_id] = CardFacts(
                known=stat is not None,
                ace_spec=bool(stat is not None and getattr(stat, "aceSpec", False)),
                typed_basic_energy=bool(stat is not None and
                                        getattr(stat, "is_typed_basic_energy", False)),
                pokemon=bool(stat is not None and getattr(stat, "is_pokemon", False)),
                stage=(getattr(stat, "stage", None) if stat is not None else None),
                prize_value=(getattr(stat, "prize_value", 1) if stat is not None else 1),
                energy_type=(getattr(stat, "energyType", None) if stat is not None else None),
                bench_damage=max((int(getattr(attack, "benchSnipe", 0) or 0)
                                  for attack in attacks if attack is not None), default=0),
            )
        declarations = tuple(line for line in getattr(strategy, "lines", ()) if line.path)
        lines = tuple(tuple(line.path) for line in declarations)
        line_bases = tuple(line.path[0] for line in declarations
                           if getattr(line, "role", "win_condition") == "win_condition")
        line_pairs = tuple((line[0], line[-1]) for line in lines
                           if len(line) >= MIN_EVOLUTION_LINE_LENGTH)
        prize_plan = getattr(strategy, "prize_plan", None)
        return cls(roles=roles, functions=tags, facts=facts,
                   overrides=getattr(strategy, "worth_overrides", {}) or {},
                   line_bases=line_bases, line_pairs=line_pairs, lines=lines,
                   partners=getattr(strategy, "partners", {}) or {},
                   prize_routes=(getattr(prize_plan, "routes", ()) if prize_plan else ()),
                   prizes_to_win=(getattr(prize_plan, "prizes_to_win", None)
                                  if prize_plan else None))

    def worth(self, card_id: int) -> float:
        card_id = int(card_id)
        facts = self.facts.get(card_id, CardFacts(known=False))
        return float(role_value(
            self.roles.get(card_id, ()), is_ace_spec=facts.ace_spec,
            is_typed_basic_energy=facts.typed_basic_energy,
            tags=self.functions.get(card_id, ()), is_known_card=facts.known,
            worth_override=self.overrides.get(card_id, 0.0),
        ))

    def prizes(self, card_id: int) -> float:
        return float(worth_to_prizes(self.worth(card_id)))

    def held_worth(self, card_id: int, observation: Mapping) -> float:
        return self.worth(card_id)

    def hand_worth(self, card_ids, observation: Mapping) -> float:
        """Linear accessible-resource value; interaction value comes from Bellman continuation."""
        return sum(self.held_worth(int(card_id), observation) for card_id in card_ids)

    @property
    def identity(self) -> str:
        payload = json.dumps({
            "roles": self.roles, "functions": self.functions,
            "facts": {key: vars(value) for key, value in self.facts.items()},
            "overrides": self.overrides, "seeds": vars(self.seeds),
            "line_parents": self.line_parents, "lines": self.lines,
            "partners": self.partners,
            "prize_routes": self.prize_routes, "prizes_to_win": self.prizes_to_win,
        }, sort_keys=True, separators=(",", ":"), default=list).encode("utf-8")
        return "bellman-worth/1:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class Potential:
    total: float
    families: tuple[tuple[str, float], ...]
    unknowns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.total)):
            raise ValueError("potential must be finite")


class ValueOracle:
    """Differences a state utility once per transition; it never inspects action semantics."""

    def __init__(self, registry: ValueRegistry,
                 family_evaluator: Callable[[Mapping], Potential], *, effects=None, stats=None,
                 refresh_evaluator=None):
        self.registry = registry
        self.effects = effects
        self.stats = stats
        if family_evaluator is None:
            raise ValueError("Bellman requires an explicit board-potential evaluator")
        self._families = family_evaluator
        self._potential_cache: dict[str, Potential] = {}
        self._reveal_priority_cache = {}
        if refresh_evaluator is None and effects is not None and stats is not None:
            from .refresh import RefreshEvaluator
            refresh_evaluator = RefreshEvaluator(
                registry, family_evaluator, effects=effects, stats=stats)
        self._refresh = refresh_evaluator

    def potential(self, state: DecisionState, *, model=None) -> Potential:
        if model is None and state.semantic_key in self._potential_cache:
            return self._potential_cache[state.semantic_key]
        base = self._families(model if model is not None else state.obs)
        families = [(name, float(value)) for name, value in base.families]
        result = Potential(sum(value for _name, value in families), tuple(families), base.unknowns)
        if model is None:
            self._potential_cache[state.semantic_key] = result
        return result

    def transition_ledger(self, before: DecisionState, after: DecisionState,
                          action: ActionIdentity, *, before_model=None, after_model=None) -> Ledger:
        left = dict(self.potential(before, model=before_model).families)
        right = dict(self.potential(after, model=after_model).families)
        benefits, costs = [], []
        for family in tuple(left) + tuple(key for key in right if key not in left):
            delta = float(right.get(family, 0.0) - left.get(family, 0.0))
            if delta > 0.0:
                benefits.append((family, delta))
            elif delta < 0.0:
                costs.append((family, -delta))
        discard_cost = self._discarded_option_cost(before, after)
        represented = sum(value for family, value in costs
                          if family in {"hand", "hand_demand"})
        if discard_cost > represented:
            costs.append(("discarded_options", discard_cost - represented))
        return Ledger(tuple(benefits), tuple(costs))

    def _discarded_option_cost(self, before: DecisionState, after: DecisionState) -> float:
        def zones(state):
            players = ((state.obs.get("current") or {}).get("players") or ())
            player = players[state.root_seat] if len(players) > state.root_seat else {}

            def keys(cards):
                return Counter(
                    (int(card["id"]), card.get("serial"))
                    for card in cards or () if card and card.get("id") is not None)

            return keys(player.get("hand")), keys(player.get("discard"))

        before_hand, before_discard = zones(before)
        _after_hand, after_discard = zones(after)
        moved = (after_discard - before_discard) & before_hand
        worth = sum(self.registry.worth(card_id) * count
                    for (card_id, _serial), count in moved.items())
        return worth_to_prizes(worth)

    def continuation_upper_bound(self, state: DecisionState) -> float:
        potential = self.potential(state)
        ceiling = getattr(self._families, "optimistic_ceiling", None)
        if potential.unknowns or ceiling is None:
            return math.inf
        absolute = float(ceiling(state.obs, deck=state.deck, registry=self.registry))
        if not math.isfinite(absolute) or absolute < potential.total:
            return math.inf
        return absolute - potential.total

    def refresh_ledger(self, state: DecisionState, node, *, include_next_turn=True):
        if self._refresh is None:
            raise ValueError("shuffle-refresh valuation requires effects and card facts")
        return self._refresh.evaluate(state, node, include_next_turn=include_next_turn)

    def refresh_attack_independent(self, state: DecisionState, action) -> bool:
        if self.stats is None or not hasattr(self.stats, "attack") or len(action.selection) != 1:
            return False
        options = tuple((state.obs.get("select") or {}).get("option") or ())
        index = action.selection[0]
        option = options[index] if 0 <= index < len(options) else {}
        attack_id = option.get("attackId")
        attack = self.stats.attack(attack_id) if attack_id is not None else None
        return bool(attack is not None and getattr(attack, "scaleVar", None) != "atk_hand"
                    and not getattr(attack, "hiddenPerUnit", 0))

    def reveal_choice_priority(self, before: DecisionState, after: DecisionState) -> float:
        key = before.semantic_key, after.semantic_key
        if key in self._reveal_priority_cache:
            return self._reveal_priority_cache[key]
        left = self.potential(before).total
        right = self.potential(after).total
        result = max(0.0, right - left)
        self._reveal_priority_cache[key] = result
        return result

    def reveal_node_priority(self, before: DecisionState, node) -> float:
        priorities = []
        for edge in getattr(node, "choices", ()):
            state = getattr(edge.node, "state", None)
            if state is not None:
                priorities.append(self.reveal_choice_priority(before, state))
        return max(priorities, default=0.0)

    def heal_repositions_energy(self, state: DecisionState, action) -> bool:
        if self._refresh is None:
            return False
        from .refresh import played_card_id

        card_id = played_card_id(state, action)
        return bool(card_id is not None and any(
            clause.get("kind") == "heal" and clause.get("rider") == "bounce_energy_to_hand"
            for clause in self._refresh.effects.clauses(card_id)
        ))

__all__ = (
    "CardFacts", "Potential", "ValueOracle",
    "ValueRegistry", "WorthSeeds", "FAMILY_OWNERS",
)
