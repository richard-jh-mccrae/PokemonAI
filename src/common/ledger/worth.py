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
from common.cards.functions.energy import provision_units

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


def any_attack_payable(body_facts, attached) -> bool:
    """Can the body pay some printed attack of its own with what is already attached?"""
    counts = Counter(attached)
    for attack in getattr(body_facts, "attacks", ()) or ():
        open_typed, open_colorless = _unfilled(attack.cost, counts)
        if not open_typed and open_colorless == 0:
            return True
    return False


def _slot_fill(unit: int, body_facts, attached, ctx: LedgerContext) -> str:
    """What one MORE unit of this color would fill on this body: a typed slot (through the
    forward line), only a colorless slot (own attacks), or nothing."""
    counts = Counter(attached)
    for attack in _line_attacks(body_facts, ctx):
        open_typed, _ = _unfilled(attack.cost, counts)
        if open_typed.get(unit, 0) > 0:
            return "typed"
    for attack in _line_attacks(body_facts, ctx, own_only=True):
        _, open_colorless = _unfilled(attack.cost, counts)
        if open_colorless > 0:
            return "colorless"
    return "dead"


def unit_fills_a_slot(unit: int, body_facts, attached, ctx: LedgerContext) -> bool:
    """Marginal usability of one MORE unit of this color on this body."""
    return _slot_fill(unit, body_facts, attached, ctx) != "dead"


def usable_units(body_facts, attached, ctx: LedgerContext) -> int:
    """The largest attached-unit count any single attack absorbs — typed and colorless slots
    for the body's own attacks, typed only for the forward line's."""
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

    body_name_counts: Mapping[str, int]
    body_id_counts: Mapping[int, int]
    hand_name_counts: Mapping[str, int]
    bodies: tuple = ()
    free_bench: int = 0

    @classmethod
    def read(cls, side, ctx: LedgerContext) -> "Demand":
        bodies = side.bodies
        names = Counter(body.card.facts.name for body in bodies
                        if body.card.facts is not None)
        hand_names = Counter(card.facts.name for card in (side.hand or ())
                             if card.facts is not None)
        return cls(body_name_counts=names,
                   body_id_counts=Counter(body.card.card_id for body in bodies),
                   hand_name_counts=hand_names, bodies=bodies,
                   free_bench=max(0, side.bench_max - len(side.bench)))


def demand_scale(card_id: int, facts, demand: Demand, copies_before: int,
                 ctx: LedgerContext, deck_counts) -> float:
    """The multiplier demand puts on this copy's hand/deck worth (1.0 = fully live)."""
    weights = ctx.weights
    scale, capacity = _liveness(card_id, facts, demand, ctx, deck_counts)
    if capacity is not None and copies_before >= capacity:
        scale *= weights.surplus_copy ** (copies_before - capacity + 1)
    return scale


def _liveness(card_id, facts, demand: Demand, ctx: LedgerContext, deck_counts):
    """(demand multiplier for the card's enabling condition, copies the board can consume);
    colorless-only energy is a lesser want than one filling a typed slot."""
    weights = ctx.weights
    if facts is None:
        return 1.0, None
    if isinstance(facts, PokemonCard):
        if facts.evolves_from is None:
            live = demand.free_bench > 0
            return (1.0 if live else weights.demand_dead), max(1, demand.free_bench)
        targets = demand.body_name_counts.get(facts.evolves_from, 0)
        if targets:
            return 1.0, max(1, targets)
        # The pair term: base in HAND is setup pending — worth more together than apart.
        if demand.hand_name_counts.get(facts.evolves_from, 0):
            return weights.demand_setup, 1
        return weights.demand_dead, 1
    if isinstance(facts, EnergyCard):
        colorless_only = False
        for body in demand.bodies:
            fills = _slot_fill(facts.provides, body.card.facts, body.energies, ctx)
            if fills == "typed" or _multi_provision_live(facts, body):
                return 1.0, None
            colorless_only = colorless_only or fills == "colorless"
        return (weights.demand_colorless_only if colorless_only
                else weights.demand_dead), None
    if isinstance(facts, TrainerCard):
        clauses = tuple(getattr(facts, "clauses", ()) or ())
        fetches = tuple(c for c in clauses if c.kind == "fetch" and c.zone == "deck")
        if fetches and len(fetches) == len(clauses):
            return _fetch_liveness(fetches, demand, ctx, deck_counts), None
    return 1.0, None


def _multi_provision_live(facts, body) -> bool:
    """A special energy whose record provides several units to THIS body (Ignition's
    `energy_provide` clause: one, or three on an evolution) reads fully live when the body can
    absorb at least two of them at once — one card doing two basics' work. Bodies are read as
    they stand: multi-provision on a future evolution is the speculative colorless value the
    marginal model refuses to pay (module docstring)."""
    body_facts = body.card.facts
    if body_facts is None:
        return False
    provided = provision_units(facts, evolved=body_facts.evolves_from is not None)
    if provided < 2:
        return False
    counts = Counter(body.energies)
    for attack in getattr(body_facts, "attacks", ()) or ():
        _, open_colorless = _unfilled(attack.cost, counts)
        if open_colorless >= 2:
            return True
    return False


def _fetch_liveness(fetches, demand: Demand, ctx: LedgerContext, deck_counts) -> float:
    """A deck fetch is exactly as live as its BEST reachable target — a multiplier compare,
    never a truthiness read (a dead multiplier is still truthy)."""
    if deck_counts is None:
        return 1.0
    best = ctx.weights.demand_dead
    for target_id, count in deck_counts:
        if count <= 0:
            continue
        target = ctx.facts(target_id)
        if not _fetchable(fetches, target):
            continue
        scale, _ = _liveness(target_id, target, demand, ctx, None)
        best = max(best, scale)
        if best >= 1.0:
            break
    return best


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


__all__ = ("Demand", "LedgerContext", "any_attack_payable", "base_worth", "demand_scale",
           "unit_fills_a_slot", "usable_units")
