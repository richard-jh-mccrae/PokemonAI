"""One Bellman benefit/cost ledger over canonical board potentials."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from typing import Callable, Mapping

from common.card_worth import (
    ACE_SPEC_TIER, ATTACKER_LINE_BASE_TIER, ENERGY_TIER, FUNCTION_TIER, KNOWN_CARD_FLOOR,
    ROLE_TIER, TAG_TIER, role_value,
)

from .algebra import Ledger
from .api import ActionIdentity
from .fetch import DEADNESS, fetch_target_matches
from .option_equivalence import fingerprint_source_card_id
from .state import DecisionState


WORTH_PER_PRIZE = 120.0
MIN_EVOLUTION_LINE_LENGTH = 2


def worth_to_prizes(worth: float) -> float:
    """Cross portable card Worth into Bellman's prize-denominated currency."""
    return float(worth) / WORTH_PER_PRIZE


def held_card_worth(registry, effects, stats, state: DecisionState, card_id: int, *,
                    discount_redundant: bool = False) -> float:
    worth = registry.worth(card_id)
    if effects is None or stats is None:
        return worth
    clauses = tuple(effects.clauses(card_id))
    fetches = tuple(clause for clause in clauses
                    if clause.get("kind") == "fetch" and clause.get("zone") == "deck")
    if not fetches or len(fetches) != len(clauses):
        return worth

    def matches(clause, target_id):
        stat = stats.get(target_id)
        return (fetch_target_matches(clause, stat, reading=DEADNESS)
                and (not clause.get("name_family") or clause["name_family"] in
                     str(getattr(stat, "name", ""))))

    available = tuple(target_id for target_id, count in state.deck_counts if count > 0)
    if not any(matches(clause, target_id)
               for clause in fetches for target_id in available):
        return min(worth, KNOWN_CARD_FLOOR)
    if not discount_redundant:
        return worth
    players = (state.obs.get("current") or {}).get("players") or ()
    mine = players[state.root_seat] if state.root_seat < len(players) else {}
    bodies = tuple(mine.get("active") or ()) + tuple(mine.get("bench") or ())
    hand_ids = Counter(int(card["id"]) for card in (mine.get("hand") or ()) if card)
    for clause in fetches:
        targets = tuple(target_id for target_id in available if matches(clause, target_id))
        parents = {int(target_id): registry.line_parents.get(int(target_id))
                   for target_id in targets}
        if not targets or any(parent is None for parent in parents.values()):
            return worth
        recipients = sum(1 for body in bodies if body and int(body.get("id", -1)) in {
            int(parent) for parent in parents.values() if parent is not None
        })
        held = sum(count for held_id, count in hand_ids.items()
                   if matches(clause, held_id))
        if held < recipients:
            return worth
    return min(worth, KNOWN_CARD_FLOOR)

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
    "opponent_hand": ("opponent accessible resources",),
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
    attacker_line_base: float = ATTACKER_LINE_BASE_TIER
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
    def from_strategy(cls, *, strategy, stats, functions, deck, roles=None) -> "ValueRegistry":
        card_ids = set(int(card_id) for card_id in deck)
        roles = roles or getattr(strategy, "roles", {}) or {}
        role_rows = {card_id: tuple(roles.get(card_id, ())) for card_id in card_ids}
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
        declarations = tuple(line for line in getattr(roles, "lines", ()) if line.path)
        lines = tuple(tuple(line.path) for line in declarations)
        line_bases = tuple(line.path[0] for line in declarations
                           if getattr(line, "role", "primary_attacker") == "primary_attacker")
        line_pairs = tuple((line[0], line[-1]) for line in lines
                           if len(line) >= MIN_EVOLUTION_LINE_LENGTH)
        prize_plan = getattr(strategy, "prize_plan", None)
        return cls(roles=role_rows, functions=tags, facts=facts,
                   overrides=getattr(strategy, "worth_overrides", {}) or {},
                   line_bases=line_bases, line_pairs=line_pairs, lines=lines,
                   partners=getattr(strategy, "partners", {}) or {},
                   prize_routes=(getattr(prize_plan, "routes", ()) if prize_plan else ()),
                   prizes_to_win=(getattr(prize_plan, "prizes_to_win", None)
                                  if prize_plan else None))

    def worth(self, card_id: int) -> float:
        card_id = int(card_id)
        facts = self.facts.get(card_id, CardFacts(known=False))
        intrinsic_line = self.seeds.attacker_line_base if any(
            line and card_id == line[0] for line in self.lines) else 0.0
        return float(max(intrinsic_line, role_value(
            self.roles.get(card_id, ()), is_ace_spec=facts.ace_spec,
            is_typed_basic_energy=facts.typed_basic_energy,
            tags=self.functions.get(card_id, ()), is_known_card=facts.known,
            worth_override=self.overrides.get(card_id, 0.0),
        )))

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
    """Differences state utility and charges irreversible action opportunity costs once."""

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
        discard_cost = self._spent_option_cost(before, after, action)
        represented = sum(value for family, value in costs
                          if family in {"hand", "hand_demand"})
        if discard_cost > represented:
            costs.append(("discarded_options", discard_cost - represented))
        dead_fetch_release = self._dead_fetch_release(before, after, action)
        if dead_fetch_release > 0.0:
            benefits.append(("dead_fetch_release", dead_fetch_release))
        stranded = self._stranded_fetch_cost(before, after, action)
        if stranded > 0.0:
            costs.append(("stranded_fetch", stranded))
        unresolved = self._unresolved_fetch_cost(before, after, action)
        if unresolved > 0.0:
            costs.append(("unresolved_fetch", unresolved))
        return Ledger(tuple(benefits), tuple(costs))

    def _unresolved_fetch_cost(self, before: DecisionState, after: DecisionState,
                               action: ActionIdentity) -> float:
        if action.kind != "play" or self.effects is None:
            return 0.0
        if int((after.obs.get("select") or {}).get("context", 0)) != 0:
            return 0.0
        moved = self._spent_cards(before, after, action)
        card_ids = {card_id for (card_id, _serial), count in moved.items() if count > 0}
        if len(card_ids) != 1:
            return 0.0
        card_id = next(iter(card_ids))
        clauses = tuple(self.effects.clauses(card_id))
        if not clauses or any(clause.get("kind") != "fetch" for clause in clauses):
            return 0.0

        def board(state):
            players = (state.obs.get("current") or {}).get("players") or ()
            player = players[state.root_seat] if state.root_seat < len(players) else {}
            return tuple(
                (body.get("serial"), body.get("id"),
                 tuple(card.get("id") for card in body.get("preEvolution") or ()))
                for body in tuple(player.get("active") or ()) + tuple(player.get("bench") or ())
                if body)

        if board(before) != board(after):
            return 0.0

        def hand(state):
            players = (state.obs.get("current") or {}).get("players") or ()
            player = players[state.root_seat] if state.root_seat < len(players) else {}
            return Counter(
                (int(card["id"]), card.get("serial"))
                for card in (player.get("hand") or ()) if card)

        retained = hand(before) - moved
        if hand(after) - retained:
            return 0.0
        return worth_to_prizes(KNOWN_CARD_FLOOR)

    def _stranded_fetch_cost(self, state: DecisionState, after: DecisionState,
                             action: ActionIdentity) -> float:
        if (action.kind not in {"play", "ability", "skill"}
                or self.effects is None or self.stats is None):
            return 0.0

        def card_ids(value):
            if isinstance(value, dict):
                if value.get("id") is not None:
                    yield int(value["id"])
                for child in value.values():
                    yield from card_ids(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    yield from card_ids(child)

        try:
            decoded = tuple(json.loads(part) for part in action.parts if isinstance(part, str))
        except (TypeError, ValueError, json.JSONDecodeError):
            return 0.0
        card_id = next(card_ids(decoded), None) if action.kind == "play" else None
        if card_id is None and action.kind in {"ability", "skill"}:
            card_id = next((found for part in action.parts
                            if (found := fingerprint_source_card_id(part, state.obs)) is not None),
                           None)
        clauses = tuple(self.effects.clauses(card_id)) if card_id is not None else ()
        fetches = tuple(clause for clause in clauses
                        if clause.get("kind") == "fetch" and clause.get("zone") == "deck")
        if not fetches or len(fetches) != len(clauses):
            return 0.0
        players = (state.obs.get("current") or {}).get("players") or ()
        mine = players[state.root_seat] if state.root_seat < len(players) else {}
        bodies = tuple(mine.get("active") or ()) + tuple(mine.get("bench") or ())
        body_ids = {int(body["id"]) for body in bodies if body and body.get("id") is not None}
        available = dict(state.deck_counts)

        def hand_ids(value):
            players = (value.obs.get("current") or {}).get("players") or ()
            player = players[value.root_seat] if value.root_seat < len(players) else {}
            return Counter(int(card["id"]) for card in (player.get("hand") or ()) if card)

        held_before = hand_ids(state)
        acquired = hand_ids(after) - held_before
        stranded = []
        redundant_fetch = False
        for clause in fetches:
            targets = tuple(acquired) if acquired else tuple(
                    int(target_id) for target_id, count in available.items()
                    if count > 0 and fetch_target_matches(
                        clause, self.stats.get(target_id), reading=DEADNESS)
                    and (not clause.get("name_family") or clause["name_family"] in
                         str(getattr(self.stats.get(target_id), "name", ""))))
            if not targets:
                continue
            if any(not getattr(self.stats.get(target_id), "evolvesFrom", None)
                   for target_id in targets):
                return 0.0
            playable = {
                int(top): int(base) for top, base in self.registry.line_parents.items()
                if int(top) in targets
            }
            recipients = sum(body_id in set(playable.values()) for body_id in body_ids)
            held_targets = sum(held_before.get(top, 0) for top in playable)
            redundant = bool(playable) and recipients > 0 and held_targets >= recipients
            redundant_fetch = redundant_fetch or redundant
            if not redundant and any(base in body_ids for base in playable.values()):
                return 0.0
            for target_id in targets:
                line = next((line for line in self.registry.lines if target_id in line), ())
                cards = line[:line.index(target_id) + 1] if line else (target_id,)
                stranded.append(sum(self.registry.prizes(value) for value in cards))
        return (max(stranded, default=0.0)
                + (self.registry.prizes(card_id)
                   if stranded and action.kind == "play" else 0.0)
                + (worth_to_prizes(KNOWN_CARD_FLOOR) if redundant_fetch else 0.0))

    def _spent_option_cost(self, before: DecisionState, after: DecisionState,
                           action: ActionIdentity) -> float:
        moved = self._spent_cards(before, after, action)
        worth = sum(self._held_card_worth(
            before, card_id, discount_redundant=action.kind == "card") * count
                    for (card_id, _serial), count in moved.items())
        return worth_to_prizes(worth)

    @staticmethod
    def _spent_cards(before: DecisionState, after: DecisionState,
                     action: ActionIdentity) -> Counter:
        def zones(state):
            players = ((state.obs.get("current") or {}).get("players") or ())
            player = players[state.root_seat] if len(players) > state.root_seat else {}

            def keys(cards):
                return Counter(
                    (int(card["id"]), card.get("serial"))
                    for card in cards or () if card and card.get("id") is not None)

            return keys(player.get("hand")), keys(player.get("discard"))

        before_hand, before_discard = zones(before)
        after_hand, after_discard = zones(after)
        return ((before_hand - after_hand) if action.kind == "play" else
                (after_discard - before_discard) & before_hand)

    def _dead_fetch_release(self, before: DecisionState, after: DecisionState,
                            action: ActionIdentity) -> float:
        if action.kind != "card":
            return 0.0
        released = sum(
            (self.registry.worth(card_id) - self._held_card_worth(
                before, card_id, discount_redundant=action.kind == "card")) * count
            for (card_id, _serial), count in self._spent_cards(before, after, action).items()
        )
        return worth_to_prizes(released)

    def _held_card_worth(self, state: DecisionState, card_id: int, *,
                         discount_redundant: bool = False) -> float:
        return held_card_worth(
            self.registry, self.effects, self.stats, state, card_id,
            discount_redundant=discount_redundant)

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
