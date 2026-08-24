"""Bellman-only typed-Energy affordability."""
from __future__ import annotations

from common.cards.functions.energy import ENERGY_COLORLESS, ENERGY_WILDCARD


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
