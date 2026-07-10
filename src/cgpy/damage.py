"""Damage pipeline (ADR-0050): base -> attacker mods -> xWeakness -> -Resistance ->
defender mods -> counters. M1 scope: printed damage + Weakness x2 + Resistance -30 on the
defending Active (docs/rules.md §5); rider/scaler/ignore-flag stages arrive with the chain
interpreter (M2) and slot into the marked seams.
"""
from __future__ import annotations

from .cards import Attack
from .state import GameState, PokemonInPlay

WEAKNESS_MULTIPLIER = 2
RESISTANCE_REDUCTION = 30


def attack_damage(gs: GameState, attacker: PokemonInPlay, attack: Attack,
                  defender: PokemonInPlay, *, defender_is_active: bool = True) -> int:
    dmg = attack.damage
    if dmg <= 0:
        return 0
    # (M2 seam: attacker-side modifiers / scalers computed by the attack's chain program)
    if defender_is_active:
        atk_type = gs.stat(attacker.top).energyType
        dstat = gs.stat(defender.top)
        if dstat.weakness is not None and dstat.weakness == atk_type:
            dmg *= WEAKNESS_MULTIPLIER
        if dstat.resistance is not None and dstat.resistance == atk_type:
            dmg = max(0, dmg - RESISTANCE_REDUCTION)
    # (M2 seam: defender-side modifiers; bench immunity for bench targets)
    return dmg
