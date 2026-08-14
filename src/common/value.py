"""One Bellman benefit/cost ledger over canonical board potentials."""
from __future__ import annotations

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
        self._need_coverage_cache = {}
        if refresh_evaluator is None and effects is not None and stats is not None:
            from .refresh import RefreshEvaluator
            refresh_evaluator = RefreshEvaluator(
                registry, family_evaluator, effects=effects, stats=stats)
        self._refresh = refresh_evaluator
        self.needs = refresh_evaluator.needs if refresh_evaluator is not None else None

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
        return Ledger(tuple(benefits), tuple(costs))

    def refresh_ledger(self, state: DecisionState, node):
        if self._refresh is None:
            raise ValueError("shuffle-refresh valuation requires effects and card facts")
        return self._refresh.evaluate(state, node)

    def reveal_choice_priority(self, before: DecisionState, after: DecisionState) -> float:
        if self._refresh is None:
            return 0.0
        from collections import Counter
        from .needs import best_assignment

        seat = before.root_seat
        before_players = (before.obs.get("current") or {}).get("players") or ()
        after_players = (after.obs.get("current") or {}).get("players") or ()
        before_hand = Counter(int(card["id"]) for card in (
            before_players[seat].get("hand") or ()) if card)
        after_hand = Counter(int(card["id"]) for card in (
            after_players[seat].get("hand") or ()) if card)
        added = list((after_hand - before_hand).elements())
        if not added:
            return 0.0
        needs = self._refresh.needs.immediate(before.obs, seat)
        targets = Counter(dict(before.deck_counts))

        def signatures(card_ids):
            rows = []
            for card_id in card_ids:
                rows.extend(self._refresh.needs.coverage_slots(
                    card_id, needs, supporter_available=before.budgets.supporter,
                    discard_capacity=max(0, sum(before_hand.values()) - 1),
                    available_targets=targets))
            return rows

        baseline = best_assignment(
            signatures(before_hand.elements()), len(needs), target_counts=targets).value
        expanded = best_assignment(
            signatures((*before_hand.elements(), *added)), len(needs), target_counts=targets).value
        return max(0.0, expanded - baseline)

    def reveal_node_priority(self, before: DecisionState, node) -> float:
        priorities = []
        for edge in getattr(node, "choices", ()):
            state = getattr(edge.node, "state", None)
            if state is not None:
                priorities.append(self.reveal_choice_priority(before, state))
        return max(priorities, default=0.0)

    def need_coverage_ledger(self, state: DecisionState, action) -> tuple[str, Ledger] | None:
        covered = self._played_need_coverage(state, action)
        if covered is None:
            return None
        needs, assignment = covered
        keys = [need.key for index, need in enumerate(needs)
                if assignment.covered_mask & (1 << index)]
        families = {
            "deployment" if key.startswith("deploy_line:") else
            "evolution" if key.startswith("evolve:") else
            "attachment" if key == "fund_attack" else ""
            for key in keys
        } - {""}
        if assignment.value <= 0.0 or len(families) != 1:
            return None
        family = families.pop()
        ledger_name = {"deployment": "board", "evolution": "development",
                       "attachment": "energy_position"}[family]
        return family, Ledger(((ledger_name, assignment.value),), ())

    def need_coverage_value(self, state: DecisionState, action) -> float:
        covered = self._played_need_coverage(state, action)
        return covered[1].value if covered is not None else 0.0

    def heal_need_value(self, state: DecisionState, action) -> float | None:
        if self._refresh is None:
            return None
        from .refresh import played_card_id

        card_id = played_card_id(state, action)
        if card_id is None or not any(
                clause.get("kind") == "heal"
                for clause in self._refresh.effects.clauses(card_id)):
            return None
        return self.need_coverage_value(state, action)

    def heal_repositions_energy(self, state: DecisionState, action) -> bool:
        if self._refresh is None:
            return False
        from .refresh import played_card_id

        card_id = played_card_id(state, action)
        return bool(card_id is not None and any(
            clause.get("kind") == "heal" and clause.get("rider") == "bounce_energy_to_hand"
            for clause in self._refresh.effects.clauses(card_id)
        ))

    def recovery_need_value(self, state: DecisionState, action) -> float:
        if self._refresh is None:
            return 0.0
        from collections import Counter
        from .fetch import REACH, fetch_target_matches
        from .refresh import played_card_id

        card_id = played_card_id(state, action)
        if card_id is None:
            return 0.0
        clauses = tuple(
            clause for clause in self._refresh.effects.clauses(card_id)
            if clause.get("kind") == "fetch" and clause.get("zone") == "discard"
        )
        if not clauses:
            return 0.0
        players = (state.obs.get("current") or {}).get("players") or ()
        mine = players[state.root_seat] if len(players) > state.root_seat else {}
        needs = self._refresh.needs.immediate(state.obs, state.root_seat)
        hand_ids = tuple(int(card["id"]) for card in mine.get("hand") or () if card)
        available = Counter(dict(state.deck_counts))
        uncovered = self._refresh.needs.uncovered_by_hand(
            needs, hand_ids, supporter_available=state.budgets.supporter,
            discard_capacity=max(0, len(hand_ids) - 1), available_targets=available,
        )
        best = 0.0
        for target in mine.get("discard") or ():
            if not target or target.get("id") is None:
                continue
            target_id = int(target["id"])
            if not any(fetch_target_matches(
                    clause, self._refresh.needs.stat(target_id), reading=REACH)
                       for clause in clauses):
                continue
            best = max(best, max(
                (dict(need.direct).get(target_id, 0.0) for need in uncovered), default=0.0))
        return best

    def _played_need_coverage(self, state: DecisionState, action):
        if self._refresh is None:
            return None
        from collections import Counter
        from .needs import best_assignment
        from .refresh import played_card_id

        card_id = played_card_id(state, action)
        if card_id is None:
            return None
        key = state.semantic_key, action.identity
        if key in self._need_coverage_cache:
            return self._need_coverage_cache[key]
        players = (state.obs.get("current") or {}).get("players") or ()
        mine = players[state.root_seat] if len(players) > state.root_seat else {}
        needs = self._refresh.needs.immediate(state.obs, state.root_seat)
        targets = Counter(dict(state.deck_counts))
        signatures = self._refresh.needs.coverage_slots(
            card_id, needs, supporter_available=state.budgets.supporter,
            discard_capacity=max(0, len(mine.get("hand") or ()) - 1),
            available_targets=targets)
        assignment = best_assignment(signatures, len(needs), target_counts=targets)
        result = needs, assignment
        self._need_coverage_cache[key] = result
        return result


__all__ = (
    "CardFacts", "Potential", "ValueOracle",
    "ValueRegistry", "WorthSeeds", "FAMILY_OWNERS",
)
