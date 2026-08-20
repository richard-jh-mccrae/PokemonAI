"""Shared typed-Energy affordability primitives; the wire codes live on the ground layer."""
from __future__ import annotations

from ..card_facts import (
    COLORLESS as ENERGY_COLORLESS, GRASS as ENERGY_GRASS, FIRE as ENERGY_FIRE,
    WATER as ENERGY_WATER, LIGHTNING as ENERGY_LIGHTNING, PSYCHIC as ENERGY_PSYCHIC,
    FIGHTING as ENERGY_FIGHTING, DARKNESS as ENERGY_DARKNESS, METAL as ENERGY_METAL,
    DRAGON as ENERGY_DRAGON, WILDCARD as ENERGY_WILDCARD)

MINIMUM_ENERGY_UNITS = 1


def provision_units(card, *, evolved: bool = False) -> int:
    """Units one attached Energy card supplies: its record's `energy_provide` clause, else one."""
    clause = card.clause("energy_provide") if card is not None else None
    if clause is None:
        return MINIMUM_ENERGY_UNITS
    evolution = int(clause.amount_on_evolution or 0) if evolved else 0
    return max(MINIMUM_ENERGY_UNITS, int(clause.amount or 0), evolution)


def pays_energy_type(provision: int, required: int) -> bool:
    return int(required) == ENERGY_COLORLESS or int(provision) in (
        int(required), ENERGY_WILDCARD)


def unmet_cost_slots(provisions, requirements) -> tuple[tuple[int, int], ...]:
    remaining = [int(code) for code in provisions]
    required = tuple(int(code) for code in requirements)
    paid = set()
    for slot, energy_type in enumerate(required):
        if energy_type == ENERGY_COLORLESS:
            continue
        # Exact colour first: a wildcard spent where an exact could pay starves a later slot.
        index = next((index for index, code in enumerate(remaining)
                      if code == energy_type), None)
        if index is None:
            index = next((index for index, code in enumerate(remaining)
                          if pays_energy_type(code, energy_type)), None)
        if index is not None:
            remaining.pop(index)
            paid.add(slot)
    for slot, energy_type in enumerate(required):
        if energy_type == ENERGY_COLORLESS and remaining:
            remaining.pop()
            paid.add(slot)
    return tuple((slot, energy_type) for slot, energy_type in enumerate(required)
                 if slot not in paid)


def payment_fraction(provisions, requirements) -> float:
    required = tuple(requirements)
    return (1.0 if not required else
            (len(required) - len(unmet_cost_slots(provisions, required))) / len(required))


__all__ = ("ENERGY_COLORLESS", "ENERGY_GRASS", "ENERGY_FIRE", "ENERGY_WATER", "ENERGY_LIGHTNING",
           "ENERGY_PSYCHIC", "ENERGY_FIGHTING", "ENERGY_DARKNESS", "ENERGY_METAL", "ENERGY_DRAGON",
           "ENERGY_WILDCARD", "pays_energy_type",
           "payment_fraction", "provision_units", "unmet_cost_slots")
