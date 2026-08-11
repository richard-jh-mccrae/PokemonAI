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
from common.state_value import worth_to_prizes

from .algebra import Ledger
from .api import ActionIdentity
from .state import DecisionState


ALLOWANCE_COST_WORTH = 0.01
DECISION_COST_PRIZES = 1e-12

FAMILY_OWNERS = {
    "prize_race": ("game", "prizes", "prize proximity"),
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


@dataclass(frozen=True)
class WorthSeeds:
    roles: tuple[tuple[str, float], ...] = tuple(sorted(ROLE_TIER.items()))
    functions: tuple[tuple[str, float], ...] = tuple(sorted(FUNCTION_TIER.items()))
    behavioural: tuple[tuple[str, float], ...] = tuple(sorted(TAG_TIER.items()))
    energy: float = ENERGY_TIER
    ace_spec: float = ACE_SPEC_TIER
    known_floor: float = KNOWN_CARD_FLOOR
    prize_rate: float = 1.0 / 120.0
    allowance: float = ALLOWANCE_COST_WORTH


class ValueRegistry:
    """Portable card Worth plus upward-only deck declarations."""

    def __init__(self, *, roles: Mapping[int, tuple[str, ...]] | None = None,
                 functions: Mapping[int, tuple[str, ...]] | None = None,
                 facts: Mapping[int, CardFacts] | None = None,
                 overrides: Mapping[int, float] | None = None,
                 line_bases=(), seeds: WorthSeeds = WorthSeeds()):
        self.roles = {int(key): tuple(value) for key, value in (roles or {}).items()}
        for card_id in line_bases:
            self.roles[int(card_id)] = (*self.roles.get(int(card_id), ()), "win_condition_base")
        self.functions = {int(key): tuple(value) for key, value in (functions or {}).items()}
        self.facts = {int(key): value for key, value in (facts or {}).items()}
        self.overrides = {int(key): max(0.0, float(value)) for key, value in (overrides or {}).items()}
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
            )
        line_bases = tuple(line.path[0] for line in getattr(strategy, "lines", ()) if line.path)
        return cls(roles=roles, functions=tags, facts=facts,
                   overrides=getattr(strategy, "worth_overrides", {}) or {},
                   line_bases=line_bases)

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

    @property
    def identity(self) -> str:
        payload = json.dumps({
            "roles": self.roles, "functions": self.functions,
            "facts": {key: vars(value) for key, value in self.facts.items()},
            "overrides": self.overrides, "seeds": vars(self.seeds),
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


class ValueOracle:
    """Converts one neutral family evaluator into the conserved Bellman ledger.

    ``family_evaluator`` returns legacy-neutral board families.  Its hand term is replaced by the
    portable Worth sum, making the card's shared opportunity cost explicit and deck-transferable.
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
        hand = sum(self.registry.prizes(card_id)
                   for card_id in _hand_ids(state.obs, state.root_seat))
        families.append(("hand", hand))
        families.extend(state.value_adjustments)
        return Potential(sum(value for _name, value in families), tuple(families), base.unknowns)

    def transition_ledger(self, before: DecisionState, after: DecisionState,
                          action: ActionIdentity, *, before_model=None, after_model=None) -> Ledger:
        if action.kind == "end":
            return Ledger()
        left = dict(self.potential(before, model=before_model).families)
        right = dict(self.potential(after, model=after_model).families)
        benefits, costs = [], []
        for family in tuple(left) + tuple(key for key in right if key not in left):
            delta = float(right.get(family, 0.0) - left.get(family, 0.0))
            if delta > 0.0:
                benefits.append((family, delta))
            elif delta < 0.0:
                costs.append((family, -delta))
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
