"""One Bellman benefit/cost ledger over canonical board potentials."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from collections import Counter
import math
from typing import Callable, Mapping

from common.card_worth import (
    ACE_SPEC_TIER, ENERGY_TIER, FUNCTION_TIER, KNOWN_CARD_FLOOR, ROLE_TIER, TAG_TIER, role_value,
)
from common.state_value import worth_to_prizes

from .algebra import Ledger
from .api import ActionIdentity
from .state import DecisionState
from common.strategy.context import _HEAL


ALLOWANCE_COST_WORTH = 0.01
DECISION_COST_PRIZES = 1e-12
WORTH_PER_PRIZE = 120.0
TYPED_ENERGY_HAND_MULTIPLIERS = (1.0, 1.0, 1.0)
TYPED_ENERGY_DUPLICATE_MULTIPLIER = 0.60
CARD_HAND_MULTIPLIERS = (1.0, 0.55, 0.25)
CARD_DUPLICATE_MULTIPLIER = 0.15

FAMILY_OWNERS = {
    "prize_race": ("game", "prizes", "prize proximity"),
    "prize_plan": ("own KO ordering", "prize-route availability"),
    "survival": ("post-attack safety", "incoming KO exposure"),
    "threat": ("opponent threat removal", "denial counterfactual"),
    "readiness": ("typed attack readiness", "mobility", "retreat option"),
    "development": ("evolution dependencies", "persistent Energy", "Bench capacity"),
    "hand": ("portable card Worth", "future access"),
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


@dataclass(frozen=True)
class WorthSeeds:
    roles: tuple[tuple[str, float], ...] = tuple(sorted(ROLE_TIER.items()))
    functions: tuple[tuple[str, float], ...] = tuple(sorted(FUNCTION_TIER.items()))
    behavioural: tuple[tuple[str, float], ...] = tuple(sorted(TAG_TIER.items()))
    energy: float = ENERGY_TIER
    ace_spec: float = ACE_SPEC_TIER
    known_floor: float = KNOWN_CARD_FLOOR
    prize_rate: float = 1.0 / WORTH_PER_PRIZE
    allowance: float = ALLOWANCE_COST_WORTH


class ValueRegistry:
    """Portable card Worth plus upward-only deck declarations."""

    def __init__(self, *, roles: Mapping[int, tuple[str, ...]] | None = None,
                 functions: Mapping[int, tuple[str, ...]] | None = None,
                 facts: Mapping[int, CardFacts] | None = None,
                 overrides: Mapping[int, float] | None = None,
                 line_bases=(), line_pairs=(), lines=(), prize_routes=(), prizes_to_win=None,
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
            facts[card_id] = CardFacts(
                known=stat is not None,
                ace_spec=bool(stat is not None and getattr(stat, "aceSpec", False)),
                typed_basic_energy=bool(stat is not None and
                                        getattr(stat, "is_typed_basic_energy", False)),
                pokemon=bool(stat is not None and getattr(stat, "is_pokemon", False)),
                stage=(getattr(stat, "stage", None) if stat is not None else None),
                prize_value=(getattr(stat, "prize_value", 1) if stat is not None else 1),
                energy_type=(getattr(stat, "energyType", None) if stat is not None else None),
            )
        declarations = tuple(line for line in getattr(strategy, "lines", ()) if line.path)
        lines = tuple(tuple(line.path) for line in declarations)
        line_bases = tuple(line.path[0] for line in declarations
                           if getattr(line, "role", "win_condition") == "win_condition")
        line_pairs = tuple((line[0], line[-1]) for line in lines if len(line) >= 2)
        prize_plan = getattr(strategy, "prize_plan", None)
        return cls(roles=roles, functions=tags, facts=facts,
                   overrides=getattr(strategy, "worth_overrides", {}) or {},
                   line_bases=line_bases, line_pairs=line_pairs, lines=lines,
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
        facts = self.facts.get(int(card_id), CardFacts(known=False))
        if (facts.pokemon and facts.stage not in (None, "basic")
                and int(card_id) not in self.line_parents):
            return self.seeds.known_floor
        return self.worth(card_id)

    def hand_worth(self, card_ids, observation: Mapping) -> float:
        """Marginal option value of a hand; every duplicate stays positive, never free."""
        total = 0.0
        for card_id, count in Counter(int(card_id) for card_id in card_ids).items():
            facts = self.facts.get(card_id, CardFacts(known=False))
            if facts.typed_basic_energy:
                multipliers = TYPED_ENERGY_HAND_MULTIPLIERS
                tail = TYPED_ENERGY_DUPLICATE_MULTIPLIER
            else:
                multipliers = CARD_HAND_MULTIPLIERS
                tail = CARD_DUPLICATE_MULTIPLIER
            worth = self.held_worth(card_id, observation)
            total += worth * (sum(multipliers[:count]) + max(0, count - len(multipliers)) * tail)
        return total

    @property
    def identity(self) -> str:
        payload = json.dumps({
            "roles": self.roles, "functions": self.functions,
            "facts": {key: vars(value) for key, value in self.facts.items()},
            "overrides": self.overrides, "seeds": vars(self.seeds),
            "line_parents": self.line_parents, "lines": self.lines,
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


def _hand_ids(observation: Mapping, seat: int) -> tuple[int, ...]:
    players = ((observation.get("current") or {}).get("players") or ())
    player = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    return tuple(int(card["id"]) for card in (player.get("hand") or ()) if card)


def _consumed_hand_ids(before: Mapping, after: Mapping, seat: int) -> tuple[int, ...]:
    """Cards that ceased to be held, matched by physical serial when observations expose it."""
    players_before = ((before.get("current") or {}).get("players") or ())
    players_after = ((after.get("current") or {}).get("players") or ())
    left = list((players_before[seat] if 0 <= seat < len(players_before) else {}).get("hand") or ())
    right = list((players_after[seat] if 0 <= seat < len(players_after) else {}).get("hand") or ())
    right_serials = Counter((int(card.get("id", 0)), int(card["serial"]))
                            for card in right if card and card.get("serial") is not None)
    right_unserialled = Counter(int(card.get("id", 0)) for card in right
                                if card and card.get("serial") is None)
    removed = []
    for card in left:
        if not card:
            continue
        card_id = int(card.get("id", 0))
        if card.get("serial") is not None:
            token = (card_id, int(card["serial"]))
            if right_serials[token]:
                right_serials[token] -= 1
                continue
        elif right_unserialled[card_id]:
            right_unserialled[card_id] -= 1
            continue
        removed.append(card_id)
    return tuple(removed)


class ValueOracle:
    """Converts one neutral family evaluator into the conserved Bellman ledger.

    ``family_evaluator`` returns legacy-neutral board families. Portable Worth is charged when a
    held card is actually consumed; merely moving a higher-Worth card into hand is not a benefit.
    """

    def __init__(self, registry: ValueRegistry,
                 family_evaluator: Callable[[Mapping], Potential] | None = None):
        self.registry = registry
        self._families = family_evaluator or self._state_model_families

    @staticmethod
    def _state_model_families(model) -> Potential:
        from common.state_value import value_breakdown

        breakdown = value_breakdown(model)
        return Potential(breakdown.total,
                         tuple((family.family, family.value_prizes)
                               for family in breakdown.families),
                         tuple(breakdown.unknowns))

    def potential(self, state: DecisionState, *, model=None) -> Potential:
        base = self._families(model if model is not None else state.obs)
        families = [(name, float(value)) for name, value in base.families if name != "hand"]
        families.append(("hand", 0.0))
        families.extend(state.value_adjustments)
        return Potential(sum(value for _name, value in families), tuple(families), base.unknowns)

    def transition_ledger(self, before: DecisionState, after: DecisionState,
                          action: ActionIdentity, *, before_model=None, after_model=None) -> Ledger:
        if action.kind == "end":
            return Ledger()
        left = dict(self.potential(before, model=before_model).families)
        right = dict(self.potential(after, model=after_model).families)
        benefits, costs = [], []
        context = int(((before.obs.get("select") or {}).get("context", -1)))
        for family in tuple(left) + tuple(key for key in right if key not in left):
            delta = float(right.get(family, 0.0) - left.get(family, 0.0))
            if family == "pressure" and context == _HEAL:
                # Heal-target selection owns HP and returned-Energy consequences. The reachable
                # attack is priced by its continuation; charging its temporary disappearance here
                # makes healing the exposed Active lose to healing a safe Bench body.
                continue
            if delta > 0.0:
                benefits.append((family, delta))
            elif delta < 0.0:
                costs.append((family, -delta))
        # Passive potential values the standing board.  A resolved attack additionally removes
        # opponent capacity in proportion to the attacks it makes unreachable; attaching,
        # promoting and nested target menus must not collect that credit pre-emptively.
        attack_threat = getattr(self._families, "attack_threat", None)
        if action.kind == "attack" and callable(attack_threat):
            removed_threat = float(attack_threat(before.obs) - attack_threat(after.obs))
            if removed_threat > 0.0:
                benefits.append(("attack_threat", removed_threat))
        removed = _consumed_hand_ids(before.obs, after.obs, before.root_seat)
        if removed:
            held = list(_hand_ids(before.obs, before.root_seat))
            remaining = list(held)
            for card_id in removed:
                remaining.remove(card_id)
            consumed = (self.registry.hand_worth(held, before.obs)
                        - self.registry.hand_worth(remaining, before.obs))
            if consumed > 0.0:
                costs.append(("hand", worth_to_prizes(consumed)))
        for name, available in vars(before.budgets).items():
            if name == "ability":
                spent = len(after.budgets.ability) > len(available)
            else:
                spent = bool(available) and not bool(getattr(after.budgets, name))
            if spent:
                costs.append((f"allowance.{name}", self.registry.seeds.allowance *
                              self.registry.seeds.prize_rate))
        charged = {key for key, _value in costs}
        implicit_allowance = {
            "attack": "attack", "ability": "ability", "retreat": "retreat",
            "attach": "manual_attach",
        }.get(action.kind)
        if implicit_allowance and f"allowance.{implicit_allowance}" not in charged:
            costs.append((f"allowance.{implicit_allowance}", self.registry.seeds.allowance *
                          self.registry.seeds.prize_rate))
        costs.append(("decision", DECISION_COST_PRIZES))
        return Ledger(tuple(benefits), tuple(costs))


__all__ = (
    "ALLOWANCE_COST_WORTH", "DECISION_COST_PRIZES", "CardFacts", "Potential", "ValueOracle",
    "ValueRegistry", "WorthSeeds", "FAMILY_OWNERS",
)
