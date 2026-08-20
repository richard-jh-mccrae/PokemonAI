"""Card worth and demand: what a card is worth, given what THIS board is asking for.

Base worth resolves deck pin > Role tier > tag tier > class default > floor, always in prizes.
Demand then scales the hand/deck reading: an evolution without its base in play, an energy no
body can use, a fetch with no wanted target all decay toward `demand_dead`, and copies beyond
what the board can consume decay by `surplus_copy` each. Energy usability is MARGINAL: a unit
counts only if it fills a still-unfilled slot of some attack — typed slots match through the
forward evolution line (the unit can ride the body up), colorless slots only through the body's
own printed attacks (speculative colorless value through future evolutions is not paid)."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Mapping

from common.cards import card_store, pokemon_default_roles
from common.cards.card_facts import COLORLESS, EnergyCard, PokemonCard, TrainerCard

from .weights import LedgerWeights


@dataclass(frozen=True)
class LedgerContext:
    """Everything deck-scoped the evaluator needs: weights, Roles, and the store itself."""

    weights: LedgerWeights
    roles: Mapping[int, tuple[str, ...]]
    store: Mapping[int, object] = field(repr=False)

    @classmethod
    def build(cls, *, weights: LedgerWeights | None = None,
              roles: Mapping[int, tuple[str, ...]] | None = None,
              overrides: Mapping[str, float] | None = None) -> "LedgerContext":
        resolved = (weights or LedgerWeights()).resolve(overrides)
        merged = dict(pokemon_default_roles())
        for card_id, declared in (roles or {}).items():
            if declared:
                merged[int(card_id)] = tuple(declared)
        return cls(weights=resolved, roles=merged, store=card_store())

    def facts(self, card_id: int):
        return self.store.get(int(card_id))

    def card_roles(self, card_id: int) -> tuple[str, ...]:
        return self.roles.get(int(card_id), ())


def base_worth(card_id: int, facts, ctx: LedgerContext) -> tuple[float, str | None]:
    """A card's standing worth in prizes, plus a coverage gap when the store cannot see it."""
    weights = ctx.weights
    pinned = weights.card_worth_map.get(int(card_id))
    if pinned is not None:
        return pinned, None
    if facts is None:
        return weights.unknown_card_worth, f"unknown card {int(card_id)}"
    role_read = max((weights.role_worth.get(role, 0.0)
                     for role in ctx.card_roles(card_id) or getattr(facts, "default_roles", ())),
                    default=0.0)
    tag_read = max((weights.tag_worth.get(tag, 0.0)
                    for tag in getattr(facts, "tags", ()) or ()), default=0.0)
    if isinstance(facts, PokemonCard):
        kind = "pokemon"
    elif isinstance(facts, EnergyCard):
        kind = "energy"
    else:
        kind = getattr(facts, "kind", "item")
    kind_read = weights.kind_worth.get(kind, weights.unknown_card_worth)
    return max(role_read, tag_read, kind_read), None


# --- energy usability -------------------------------------------------------------------

@lru_cache(maxsize=1)
def _forward_lines() -> Mapping[str, tuple[int, ...]]:
    """name -> ids of every card in the store that evolves (transitively) from that name."""
    store = card_store()
    by_name = {card.name: card_id for card_id, card in store.items()
               if isinstance(card, PokemonCard)}
    forward: dict[str, list[int]] = {}
    for card_id, card in store.items():
        if not isinstance(card, PokemonCard):
            continue
        base = card.evolves_from
        seen = 0
        while base is not None and seen < 4:
            forward.setdefault(base, []).append(card_id)
            parent = by_name.get(base)
            base = store[parent].evolves_from if parent is not None else None
            seen += 1
    return {name: tuple(ids) for name, ids in forward.items()}


def _line_attacks(body_facts, ctx: LedgerContext, *, own_only: bool = False):
    attacks = list(getattr(body_facts, "attacks", ()) or ())
    if own_only or body_facts is None:
        return attacks
    for evo_id in _forward_lines().get(body_facts.name, ()):
        evo = ctx.facts(evo_id)
        attacks.extend(getattr(evo, "attacks", ()) or ())
    return attacks


def _unfilled(cost, attached: Counter) -> tuple[Counter, int]:
    """Typed slots still open after the attached units fill their own colors, and colorless
    slots still open after the leftovers spill into them."""
    need = Counter(unit for unit in cost if unit != COLORLESS)
    colorless = sum(1 for unit in cost if unit == COLORLESS)
    spent = 0
    open_typed = Counter()
    for unit, count in need.items():
        used = min(count, attached.get(unit, 0))
        spent += used
        if count > used:
            open_typed[unit] = count - used
    leftovers = sum(attached.values()) - spent
    return open_typed, max(0, colorless - leftovers)


def unit_fills_a_slot(unit: int, body_facts, attached, ctx: LedgerContext) -> bool:
    """Marginal usability of one MORE unit of this color on this body."""
    counts = Counter(attached)
    for attack in _line_attacks(body_facts, ctx):
        open_typed, _ = _unfilled(attack.cost, counts)
        if open_typed.get(unit, 0) > 0:
            return True
    for attack in _line_attacks(body_facts, ctx, own_only=True):
        open_typed, open_colorless = _unfilled(attack.cost, counts)
        if open_colorless > 0 or open_typed.get(unit, 0) > 0:
            return True
    return False


def usable_units(body_facts, attached, ctx: LedgerContext) -> int:
    """How many of the attached units are pulling weight: the largest count any single attack
    can absorb — typed and colorless slots for the body's own attacks, typed only for the
    forward line's."""
    counts = Counter(attached)
    total = sum(counts.values())
    if total == 0 or body_facts is None:
        return 0
    own = tuple(getattr(body_facts, "attacks", ()) or ())
    best = 0
    for attack in _line_attacks(body_facts, ctx):
        typed = sum(min(count, counts.get(unit, 0))
                    for unit, count in Counter(u for u in attack.cost if u != COLORLESS).items())
        colorless = (min(sum(1 for u in attack.cost if u == COLORLESS), total - typed)
                     if attack in own else 0)
        best = max(best, typed + colorless)
        if best >= total:
            return total
    return best


# --- demand -----------------------------------------------------------------------------

@dataclass(frozen=True)
class Demand:
    """What my side of the board is currently asking for, read once per evaluation."""

    body_names: tuple[str, ...]
    body_name_counts: Mapping[str, int]
    body_id_counts: Mapping[int, int]
    bodies: tuple = ()
    free_bench: int = 0

    @classmethod
    def read(cls, side, ctx: LedgerContext) -> "Demand":
        bodies = side.bodies
        names = tuple(body.card.facts.name for body in bodies
                      if body.card.facts is not None)
        return cls(body_names=names, body_name_counts=Counter(names),
                   body_id_counts=Counter(body.card.card_id for body in bodies),
                   bodies=bodies, free_bench=max(0, side.bench_max - len(side.bench)))


def demand_scale(card_id: int, facts, demand: Demand, copies_before: int,
                 ctx: LedgerContext, deck_counts) -> float:
    """The multiplier demand puts on this copy's hand/deck worth (1.0 = fully live)."""
    weights = ctx.weights
    live, capacity = _liveness(card_id, facts, demand, ctx, deck_counts)
    scale = 1.0 if live else weights.demand_dead
    if capacity is not None and copies_before >= capacity:
        scale *= weights.surplus_copy ** (copies_before - capacity + 1)
    return scale


def _liveness(card_id, facts, demand: Demand, ctx: LedgerContext, deck_counts):
    """(is the card's enabling condition on the board, how many copies can the board consume)."""
    if facts is None:
        return True, None
    if isinstance(facts, PokemonCard):
        if facts.evolves_from is None:
            return demand.free_bench > 0, max(1, demand.free_bench)
        targets = demand.body_name_counts.get(facts.evolves_from, 0)
        return targets > 0, max(1, targets) if targets else 1
    if isinstance(facts, EnergyCard):
        for body in demand.bodies:
            if unit_fills_a_slot(facts.provides, body.card.facts, body.energies, ctx):
                return True, None
        return False, None
    if isinstance(facts, TrainerCard):
        clauses = tuple(getattr(facts, "clauses", ()) or ())
        fetches = tuple(c for c in clauses if c.kind == "fetch" and c.zone == "deck")
        if fetches and len(fetches) == len(clauses):
            return _fetch_is_live(fetches, demand, ctx, deck_counts), None
    return True, None


def _fetch_is_live(fetches, demand: Demand, ctx: LedgerContext, deck_counts) -> bool:
    """A deck fetch is live when some reachable target is itself demanded right now."""
    if deck_counts is None:
        return True
    for target_id, count in deck_counts:
        if count <= 0:
            continue
        target = ctx.facts(target_id)
        if not _fetchable(fetches, target):
            continue
        live, _ = _liveness(target_id, target, demand, ctx, None)
        if live:
            return True
    return False


def _fetchable(fetches, target) -> bool:
    if target is None:
        return False
    for clause in fetches:
        wants = clause.target
        if wants in (None, "card"):
            return True
        if wants == "pokemon" and isinstance(target, PokemonCard):
            return True
        if wants == "energy" and isinstance(target, EnergyCard):
            return True
        if wants == "trainer" and isinstance(target, TrainerCard):
            return True
    return False


__all__ = ("Demand", "LedgerContext", "base_worth", "demand_scale", "unit_fills_a_slot",
           "usable_units")
