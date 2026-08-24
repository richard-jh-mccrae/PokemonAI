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


__all__ = ("ENERGY_COLORLESS", "ENERGY_GRASS", "ENERGY_FIRE", "ENERGY_WATER", "ENERGY_LIGHTNING",
           "ENERGY_PSYCHIC", "ENERGY_FIGHTING", "ENERGY_DARKNESS", "ENERGY_METAL", "ENERGY_DRAGON",
           "ENERGY_WILDCARD", "provision_units")
