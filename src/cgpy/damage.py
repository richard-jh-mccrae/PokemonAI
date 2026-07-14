"""Damage pipeline (ADR-0059): base -> attacker mods -> xWeakness -> -Resistance ->
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
    if var == "all_bench":                      # Full Moon Rondo: both benches
        return len(b.bench) + len(ob.bench)
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
    if var == "atk_discard_basic_energy":        # Riptide: Basic {type} only, in discard
        from .schema import CardType
        return len([s for s in b.discard
                    if gs.stat(s).cardType == CardType.BASIC_ENERGY
                    and (energy_type is None
                         or int(gs.stat(s).energyType) == energy_type)])
    if var == "atk_tools_in_play":              # Gadget Show: tools on ALL own mons
        return sum(len(p.tools) for p in gs.in_play(seat))
    if var == "atk_in_play":                    # Sweet Circle: own in-play mons
        return len(list(gs.in_play(seat)))
    if var == "atk_in_play_type":               # Ruffians Attack: own typed mons
        return len([p for p in gs.in_play(seat)
                    if int(gs.stat(p.top).energyType) == energy_type])
    raise ValueError(f"unknown scale var {var!r}")


def _cond_holds(gs: GameState, seat: int, cond: str, attack_cost: int = 0,
                cb: dict | None = None) -> bool:
    from .options import provided_energy
    cb = cb or {}
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
    if cond == "def_active_type":               # Mirror-Attack class: typed defender
        return ob.active is not None and \
            int(gs.stat(ob.active.top).energyType) == cb["energyType"]
    if cond == "def_active_burned":             # Roasting Heat
        return ob.active is not None and ob.burned
    if cond == "atk_energy_in_play_min":        # Electro Fall: >= min {X} in play
        n = sum(1 for p in gs.in_play(seat) for u in provided_energy(gs, p)
                if cb.get("energyType") is None or u == cb["energyType"])
        return n >= cb["min"]
    if cond == "self_extra_energy_min":         # High-Voltage Press: extra beyond cost
        if b.active is None:
            return False
        return len(provided_energy(gs, b.active)) - attack_cost >= cb["min"]
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
        if scale["var"] == "atk_named_attack":   # Round: own mons having the attack
            units = sum(1 for p in gs.in_play(seat)
                        for aid in gs.stat(p.top).attacks
                        if gs.db.attacks[aid].name == scale["attackName"])
        elif scale["var"] == "milled_basic_energy":   # Hammer-lanche: "for each Basic
            from .schema import CardType                # {W} Energy you discarded this way"
            et = scale.get("energyType")
            units = len([s for s in pre_vars.get("milled", [])
                         if gs.stat(s).cardType == CardType.BASIC_ENERGY
                         and (et is None or int(gs.stat(s).energyType) == et)])
        else:
            units = scale_count(gs, seat, scale["var"], scale.get("energyType"))
        if scale.get("add"):
            dmg += scale["per"] * units
        else:
            dmg = scale["per"] * units
    dmg += pre_vars.get("damage_bonus", 0)       # coin "If heads, +N" family
    cbs = adef.get("condBonus") or []
    if isinstance(cbs, dict):                    # the seed layer emits a single dict
        cbs = [cbs]
    for cb in cbs:
        if _cond_holds(gs, seat, cb["cond"], attack_cost=len(attack.energies), cb=cb):
            dmg += cb["n"]
    # Intimidating-Stare transient riding the attacker: its attacks do N less this
    # turn, applied before Weakness/Resistance (card text).
    if attacker.outgoing_less_turn == gs.turn and attacker.outgoing_less > 0:
        dmg -= attacker.outgoing_less
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

    # Attached-tool attacker bonus, pre-W/R, opponent's Active only (Hop's Choice Band
    # +30 for a Hop's Pokémon; Maximum Belt +50 vs an ex; Brave Bangle +30 for a
    # Rule-Box-less holder — all "before applying Weakness and Resistance").
    if defender_is_active:
        from .chain import _card_matches, def_for as _tdef_for
        for s in attacker.tools:
            ab = (_tdef_for(gs.card_id(s)) or {}).get("tool", {}).get("attackBonus")
            if not ab:
                continue
            if ab.get("defenderEx") and not (dstat.ex or dstat.megaEx):
                continue
            hf = ab.get("holder")
            if hf is not None and not _card_matches(gs, attacker.top, hf):
                continue
            dmg += ab["n"]

    # Stadium blanket, pre-W/R side (Postwick: "Attacks used by Hop's Pokémon do 30
    # more damage to the opponent's Active Pokémon (before applying Weakness and
    # Resistance)") — both players' attackers, opposing Active only.
    if defender_is_active and gs.stadium and gs.owner(defender.top) != seat:
        from .chain import def_for as _sdef_for
        sb = ((_sdef_for(gs.card_id(gs.stadium[0])) or {})
              .get("stadium", {}).get("activeBonus"))
        if sb and sb["attackerNameContains"] in gs.stat(attacker.top).name:
            dmg += sb["n"]

    joint_ignore = adef.get("ignoreWeaknessResistance", False)
    if defender_is_active:
        atk_type = gs.stat(attacker.top).energyType
        if dstat.weakness is not None and dstat.weakness == atk_type \
                and not joint_ignore and not adef.get("ignoreWeakness") \
                and defender.no_weakness_turn != gs.turn:   # Metal-Defender transient
            dmg *= WEAKNESS_MULTIPLIER
        if dstat.resistance is not None and dstat.resistance == atk_type \
                and not joint_ignore and not adef.get("ignoreResistance"):
            dmg = max(0, dmg - RESISTANCE_REDUCTION)

    return apply_defender_mods(gs, attacker, defender, dmg,
                               is_active=defender_is_active,
                               ignore_effects=adef.get("ignoreDefenderEffects", False))


def apply_defender_mods(gs: GameState, attacker: PokemonInPlay,
                        defender: PokemonInPlay, dmg: int, *, is_active: bool,
                        ignore_effects: bool) -> int:
    """The defender-side reductions/preventions shared by the Active-damage path AND
    flat bench snipes (`chain._bench_hit`) — everything AFTER Weakness/Resistance
    (which is Active-only). Passive prevention (Crustle ex-immune), Dig protect, the
    take-less transient AND the stadium blanket (Full Metal Lab) are pierced by an
    ignores-effects attack (pinned episode-83391727 f42: Nebula Beam — "damage isn't
    affected by ... any effects on your opponent's Active Pokémon" — does its full 210
    to a Metal Duraludon despite Full Metal Lab). Only benched-Tera prevention is a
    print effect that is NOT pierced."""
    from .chain import def_for
    dstat = gs.stat(defender.top)
    if not is_active and dstat.tera:
        return 0                        # benched Tera takes 0 (pinned v2_ms_dx_5401)
    if not ignore_effects:
        # Crustle's Mysterious Rock Inn: "Prevent all damage done to this Pokémon by
        # attacks from your opponent's Pokémon {ex}" (ADR-0032 prevent_ex panel) —
        # applies to benched targets too (kaggle 82229122: Jetting Blow snipe into a
        # benched Crustle does 0).
        ddef = (def_for(dstat.cardId) or {}).get("defense") or {}
        astat = gs.stat(attacker.top)
        if ddef.get("preventDamageFromEx") and (astat.ex or astat.megaEx):
            return 0
        if defender.protect_turn == gs.turn:       # Dig-family transient
            return 0
        if defender.take_less_turn == gs.turn and defender.take_less > 0:
            dmg = max(0, dmg - defender.take_less)
        # Stadium blanket (Full Metal Lab: {M} mons take 30 less, both sides, Active or
        # benched) — an on-the-Pokémon effect an ignores-effects attack pierces.
        if gs.stadium and gs.owner(defender.top) != gs.owner(attacker.top):
            tl = ((def_for(gs.card_id(gs.stadium[0])) or {})
                  .get("stadium", {}).get("takeLess"))
            if tl and int(dstat.energyType) == tl["defenderType"]:
                dmg = max(0, dmg - tl["n"])
    return dmg
