"""Damage pipeline (ADR-0050): base -> attacker mods -> xWeakness -> -Resistance ->
defender mods -> counters. Base and attacker-side stages are ChainDef-driven (M4): coin
pre-programs feed `pre_vars` (override/bonus), `scale` adds a visible-state scaler,
`condBonus` adds deterministic board-condition bonuses. Defender-side: the take-less
transient applies after W/R (card text: "(after applying Weakness and Resistance)").
"""
from __future__ import annotations

from .cards import Attack
from .state import GameState, PokemonInPlay

WEAKNESS_MULTIPLIER = 2
RESISTANCE_REDUCTION = 30


def apply_weakness_resistance(gs: GameState, attacker: PokemonInPlay,
                              defender: PokemonInPlay, dmg: int) -> int:
    """Weakness x2 then Resistance -30 for the defending ACTIVE (shared by the base
    pipeline and Cruel Arrow-class riders that hit the Active)."""
    atk_type = gs.stat(attacker.top).energyType
    dstat = gs.stat(defender.top)
    if dstat.weakness is not None and dstat.weakness == atk_type:
        dmg *= WEAKNESS_MULTIPLIER
    if dstat.resistance is not None and dstat.resistance == atk_type:
        dmg = max(0, dmg - RESISTANCE_REDUCTION)
    return dmg


def scale_count(gs: GameState, seat: int, var: str, energy_type: int | None = None) -> int:
    """Unit count for a `scale` var — attacker-relative names (ADR-0032 vocabulary)."""
    from .options import provided_energy
    b, ob = gs.players[seat], gs.players[1 - seat]
    if var == "atk_hand":
        return len(b.hand)
    if var == "def_hand":
        return len(ob.hand)
    if var == "atk_bench":
        return len(b.bench)
    if var == "def_bench":
        return len(ob.bench)
    if var == "atk_active_energy":
        if b.active is None:
            return 0
        units = provided_energy(gs, b.active)
        return len([u for u in units if energy_type is None or u == energy_type])
    if var == "def_active_energy":
        if ob.active is None:
            return 0
        return len(provided_energy(gs, ob.active))
    if var == "atk_self_counters":
        return (b.active.max_hp - b.active.hp) // 10 if b.active else 0
    if var == "def_counters":
        return (ob.active.max_hp - ob.active.hp) // 10 if ob.active else 0
    if var == "atk_prizes_taken":
        return 6 - len(b.prize)
    if var == "def_prizes_taken":
        return 6 - len(ob.prize)
    if var == "atk_discard_energy":
        return len([s for s in b.discard
                    if gs.db.is_energy(gs.card_id(s))
                    and (energy_type is None
                         or int(gs.stat(s).energyType) == energy_type)])
    raise ValueError(f"unknown scale var {var!r}")


def _cond_holds(gs: GameState, seat: int, cond: str, attack_cost: int = 0) -> bool:
    b, ob = gs.players[seat], gs.players[1 - seat]
    if cond == "def_active_ex":
        return ob.active is not None and (gs.stat(ob.active.top).ex
                                          or gs.stat(ob.active.top).megaEx)
    if cond == "def_active_damaged":
        return ob.active is not None and ob.active.hp < ob.active.max_hp
    if cond == "stadium_in_play":
        return bool(gs.stadium)
    if cond == "self_moved_this_turn":
        return b.active is not None and b.active.moved_active_turn == gs.turn
    if cond == "own_ko_last_turn":
        return gs.ko_turn[seat] == gs.turn - 1
    raise ValueError(f"unknown condBonus cond {cond!r}")


def attack_damage(gs: GameState, attacker: PokemonInPlay, attack: Attack,
                  defender: PokemonInPlay, *, defender_is_active: bool = True,
                  adef: dict | None = None, pre_vars: dict | None = None) -> int:
    adef = adef or {}
    pre_vars = pre_vars or {}
    seat = gs.owner(attacker.top)

    dmg = attack.damage
    if "damage_override" in pre_vars:            # "does N damage for each heads" family
        dmg = pre_vars["damage_override"]
    scale = adef.get("scale")
    if scale:
        units = scale_count(gs, seat, scale["var"], scale.get("energyType"))
        if scale.get("add"):
            dmg += scale["per"] * units
        else:
            dmg = scale["per"] * units
    dmg += pre_vars.get("damage_bonus", 0)       # coin "If heads, +N" family
    for cb in adef.get("condBonus", []):
        if _cond_holds(gs, seat, cb["cond"], attack_cost=len(attack.energies)):
            dmg += cb["n"]
    if dmg <= 0:
        return 0

    dstat = gs.stat(defender.top)
    # This-turn damage-bonus markers (Premium Power Pro / Black Belt's Training) apply
    # before Weakness/Resistance, opponent's Active only (card texts).
    if defender_is_active:
        for mod in gs.turn_markers.get("damage_bonus", []):
            if "attackerEnergyType" in mod and \
                    gs.stat(attacker.top).energyType != mod["attackerEnergyType"]:
                continue
            if mod.get("defenderExOnly") and not (dstat.ex or dstat.megaEx):
                continue
            dmg += mod["bonus"]

    joint_ignore = adef.get("ignoreWeaknessResistance", False)
    if defender_is_active:
        atk_type = gs.stat(attacker.top).energyType
        if dstat.weakness is not None and dstat.weakness == atk_type \
                and not joint_ignore and not adef.get("ignoreWeakness"):
            dmg *= WEAKNESS_MULTIPLIER
        if dstat.resistance is not None and dstat.resistance == atk_type \
                and not joint_ignore and not adef.get("ignoreResistance"):
            dmg = max(0, dmg - RESISTANCE_REDUCTION)

    # Defender-side transient: "takes N less damage" granted last turn (after W/R).
    if defender.take_less_turn == gs.turn and defender.take_less > 0:
        dmg = max(0, dmg - defender.take_less)
    return dmg
