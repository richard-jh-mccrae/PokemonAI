"""Option-list builders — ALL option generation and ordering lives here (ADR-0059).

Ordering is the highest-risk parity surface — agents choose by INDEX — so every builder encodes the
pinned rules from docs/pyeng/determinism.md §3. NOT the only builder: `chain.py` builds sub-select
option lists at a dozen sites.
"""
from __future__ import annotations

from .schema import AreaType, CardType, OptionType, SelectContext, SelectType
from .state import GameState, PendingSelect, PokemonInPlay


def _targets(gs: GameState, seat: int) -> list[tuple[int, int, PokemonInPlay]]:
    """(inPlayArea, inPlayIndex, pokemon) for the seat's board: active first, bench order."""
    b = gs.players[seat]
    out = []
    if b.active is not None:
        out.append((int(AreaType.ACTIVE), 0, b.active))
    for i, p in enumerate(b.bench):
        out.append((int(AreaType.BENCH), i, p))
    return out


def opt_card(area: int, index: int, player: int) -> dict:
    return {"type": int(OptionType.CARD), "area": int(area), "index": index,
            "playerIndex": player}


def yes_no() -> list[dict]:
    return [{"type": int(OptionType.YES)}, {"type": int(OptionType.NO)}]


def numbers(n_max: int) -> list[dict]:
    return [{"type": int(OptionType.NUMBER), "number": k} for k in range(n_max + 1)]


def setup_active_options(gs: GameState, seat: int) -> list[dict]:
    hand = gs.players[seat].hand
    return [opt_card(AreaType.HAND, i, seat) for i, s in enumerate(hand)
            if gs.db.is_setup_starter(gs.card_id(s))]


def setup_bench_options(gs: GameState, seat: int) -> list[dict]:
    hand = gs.players[seat].hand
    return [opt_card(AreaType.HAND, i, seat) for i, s in enumerate(hand)
            if gs.db.is_basic_pokemon(gs.card_id(s))]


def provided_energy(gs: GameState, p: PokemonInPlay) -> list[int]:
    """The energy UNITS, in attach order — a special energy's yield can depend on the holder's stage."""
    from .chain import def_for

    units: list[int] = []
    holder_is_evolution = bool(gs.stat(p.top).evolvesFrom)
    holder_is_stage2 = gs.stat(p.top).stage2
    holder_is_basic = gs.stat(p.top).basic
    for s in p.energy:
        cdef = def_for(gs.card_id(s)) or {}
        if holder_is_basic and "providesOnBasic" in cdef:
            units.extend(cdef["providesOnBasic"])
        elif holder_is_stage2 and "providesOnStage2" in cdef:
            units.extend(cdef["providesOnStage2"])
        elif holder_is_evolution and "providesOnEvolution" in cdef:
            units.extend(cdef["providesOnEvolution"])
        elif "provides" in cdef:
            units.extend(cdef["provides"])
        else:
            units.append(int(gs.stat(s).energyType))
    return units


def provided_units_of(gs: GameState, p: PokemonInPlay, serial: int) -> int:
    from .chain import def_for

    cdef = def_for(gs.card_id(serial)) or {}
    if gs.stat(p.top).basic and "providesOnBasic" in cdef:
        return len(cdef["providesOnBasic"])
    if gs.stat(p.top).stage2 and "providesOnStage2" in cdef:
        return len(cdef["providesOnStage2"])
    if bool(gs.stat(p.top).evolvesFrom) and "providesOnEvolution" in cdef:
        return len(cdef["providesOnEvolution"])
    if "provides" in cdef:
        return len(cdef["provides"])
    return 1


def effective_bench_max(gs: GameState, seat: int) -> int:
    """The discard-to-5 when the last Tera or the stadium LEAVES is NOT modeled."""
    from .chain import stadium_def
    b = gs.players[seat]
    bm = stadium_def(gs).get("benchMaxIfTera")
    if bm and any(gs.stat(p.top).tera for p in gs.in_play(seat)):
        return bm
    return b.bench_max


def effective_retreat_cost(gs: GameState, p: PokemonInPlay) -> int:
    from .chain import def_for

    cdef = def_for(gs.card_id(p.top)) or {}
    if cdef.get("retreat", {}).get("freeIfNoEnergy") and not p.energy:
        return 0
    # Passive retreat-zeroing abilities need only an UN-SUPPRESSED holder on the retreating mon's
    # own side — the holder itself does not have to be Active.
    from .chain import stadium_def as _stadium_def
    p_seat = gs.owner(p.top)
    sup_type = _stadium_def(gs).get("suppressAbilitiesType")
    for h in gs.in_play(p_seat):
        hdef = def_for(gs.card_id(h.top)) or {}
        if not hdef.get("zeroRetreatBasics"):
            continue
        if sup_type is not None and int(gs.stat(h.top).energyType) == sup_type:
            continue
        if gs.stat(p.top).basic:
            return 0
    cost = gs.stat(p.top).retreatCost
    for s in p.tools:
        cost += (def_for(gs.card_id(s)) or {}).get("tool", {}).get("retreatBonus", 0)
    # A both-Actives field effect keyed on EITHER Active holding the tool; this function is only
    # ever called for an Active, so it applies to whichever side is retreating.
    for seat in (0, 1):
        act = gs.players[seat].active
        if act is not None:
            for s in act.tools:
                cost += (def_for(gs.card_id(s)) or {}).get("tool", {}) \
                    .get("retreatBonusBothActive", 0)
    return max(0, cost)


def available_attack_ids(gs: GameState, seat: int, active: PokemonInPlay) -> list[int]:
    """A Memory-Dive holder appends pre-evo attacks: OWN first, then pre-evos top-adjacent-first."""
    from .chain import def_for as _def_for
    from .chain import stadium_def as _stadium_def
    ids = list(gs.stat(active.top).attacks)
    if len(active.stack) <= 1:
        return ids
    sup_type = _stadium_def(gs).get("suppressAbilitiesType")
    has_memory_dive = any(
        (_def_for(gs.card_id(p.top)) or {}).get("grantsPreEvoAttacks")
        and not (sup_type is not None
                 and int(gs.stat(p.top).energyType) == sup_type)
        for p in gs.in_play(seat))
    if has_memory_dive:
        for serial in reversed(active.stack[:-1]):
            ids += list(gs.stat(serial).attacks)
    return ids


def attack_cost_after_tools(gs: GameState, p: PokemonInPlay, cost: tuple) -> tuple:
    """An any-type discount removes one unit, PREFERRING Colorless."""
    from .chain import _card_matches, def_for
    from .schema import EnergyType
    reduced = list(cost)
    for s in p.tools:
        tdef = (def_for(gs.card_id(s)) or {}).get("tool", {})
        red_c = tdef.get("attackCostReduceColorless", 0)
        red_any = tdef.get("attackCostReduce", 0)
        if not (red_c or red_any):
            continue
        hf = tdef.get("attackCostHolder")
        if hf is not None and not _card_matches(gs, p.top, hf):
            continue
        for _ in range(red_c):
            if int(EnergyType.COLORLESS) in reduced:
                reduced.remove(int(EnergyType.COLORLESS))
        for _ in range(red_any):
            if int(EnergyType.COLORLESS) in reduced:
                reduced.remove(int(EnergyType.COLORLESS))
            elif reduced:
                reduced.pop()
    return tuple(reduced)


def energy_payable(gs: GameState, p: PokemonInPlay, cost: tuple) -> bool:
    from .schema import EnergyType

    pool: list[int] = list(provided_energy(gs, p))
    typed = [c for c in cost if c != int(EnergyType.COLORLESS)]
    remaining = list(pool)
    for need in typed:
        if need in remaining:
            remaining.remove(need)
        elif int(EnergyType.RAINBOW) in remaining:
            remaining.remove(int(EnergyType.RAINBOW))
        else:
            return False
    return len(remaining) >= len(cost) - len(typed)


def main_options(gs: GameState, seat: int) -> list[dict]:
    b = gs.players[seat]
    opts: list[dict] = []
    going_first_t1 = (gs.turn == 1 and gs.first_player == seat)

    for i, serial in enumerate(b.hand):
        cid = gs.card_id(serial)
        stat = gs.db.card(cid)
        if stat.cardType == CardType.POKEMON and stat.basic:
            if len(b.bench) < effective_bench_max(gs, seat):
                opts.append({"type": int(OptionType.PLAY), "index": i})
        elif stat.cardType in (CardType.BASIC_ENERGY, CardType.SPECIAL_ENERGY):
            if stat.cardType == CardType.SPECIAL_ENERGY:
                from .chain import def_for, is_deferred
                if is_deferred(def_for(cid)):
                    continue   # unmodeled special energy: option absent -> loud divergence
            if not gs.energy_attached:
                for area, idx, _p in _targets(gs, seat):
                    opts.append({"type": int(OptionType.ATTACH), "area": int(AreaType.HAND),
                                 "index": i, "inPlayArea": area, "inPlayIndex": idx})
        elif stat.cardType == CardType.POKEMON and stat.evolvesFrom:
            from .chain import def_for as _cdef_for
            ob = gs.players[1 - seat]
            opp_active_ex = (ob.active is not None and not ob.active_facedown
                             and (gs.stat(ob.active.top).ex
                                  or gs.stat(ob.active.top).megaEx))
            from .chain import stadium_def as _sd
            ev_type = _sd(gs).get("evolveImmediateType")
            for area, idx, p in _targets(gs, seat):
                # Fighting-Roar-class passive on the TARGET, gated on the opponent's Active being
                # an ex — megaEx qualifies.
                waived = opp_active_ex and (_cdef_for(gs.card_id(p.top)) or {}).get(
                    "evolve", {}).get("immediateIfOppActiveEx", False)
                # Forest of Vitality waives entered_turn ONLY, never the turn<=2 ban. UNPINNED
                # shape.
                forest = (ev_type is not None
                          and int(gs.stat(p.top).energyType) == ev_type
                          and int(stat.energyType) == ev_type)
                if not waived and gs.turn <= 2:
                    continue
                if not (waived or forest) and p.entered_turn >= gs.turn:
                    continue
                if gs.stat(p.top).name == stat.evolvesFrom:
                    opts.append({"type": int(OptionType.EVOLVE),
                                 "area": int(AreaType.HAND), "index": i,
                                 "inPlayArea": area, "inPlayIndex": idx})
        elif stat.cardType in (CardType.ITEM, CardType.SUPPORTER):
            from .chain import check_legal, def_for
            cdef = def_for(cid)
            if cdef is None or "play" not in cdef:
                continue
            if stat.cardType == CardType.SUPPORTER and (
                    gs.supporter_played
                    or (going_first_t1 and not cdef.get("allowedFirstTurn"))):
                continue  # a go-first exemption waives the T1 supporter ban
            if stat.cardType == CardType.ITEM and b.items_locked_turn == gs.turn:
                continue
            if check_legal(gs, seat, cdef.get("legal", [])):
                opts.append({"type": int(OptionType.PLAY), "index": i})
        elif stat.cardType == CardType.TOOL:
            from .chain import def_for
            if "tool" not in (def_for(cid) or {}):
                continue
            for area, idx, p in _targets(gs, seat):
                if not p.tools:
                    opts.append({"type": int(OptionType.ATTACH),
                                 "area": int(AreaType.HAND), "index": i,
                                 "inPlayArea": area, "inPlayIndex": idx})
        elif stat.cardType == CardType.STADIUM:
            from .chain import def_for
            if "stadium" not in (def_for(cid) or {}):
                continue
            if gs.stadium_played:
                continue
            if gs.stadium and gs.card_id(gs.stadium[0]) == cid:
                continue
            opts.append({"type": int(OptionType.PLAY), "index": i})

    # ABILITY options in board order, once per turn per Pokémon, plus an optional global-name limit
    from .chain import check_legal as _check_legal
    from .chain import def_for as _def_for
    from .chain import stadium_def as _stadium_def
    sup_type = _stadium_def(gs).get("suppressAbilitiesType")
    for area, idx, p in _targets(gs, seat):
        cid = gs.card_id(p.top)
        adef = (_def_for(cid) or {}).get("ability")
        if adef is None or p.ability_used_turn >= gs.turn:
            continue
        if sup_type is not None and int(gs.stat(p.top).energyType) == sup_type:
            continue   # a type-suppressing stadium removes MAIN ability options BOTH sides.
                       # Triggered/passive abilities stay un-suppressed (UNPINNED).
        if adef.get("oncePerTurnGlobal") and gs.turn_markers.get(f"ability:{cid}"):
            continue
        if not _check_legal(gs, seat, adef.get("legal", []), pokemon=p):
            continue
        opts.append({"type": int(OptionType.ABILITY), "area": area, "index": idx})

    # Stadium per-turn activated effect: an ABILITY option on the STADIUM area, once per
    # player-turn, gated by the def's legal conds.
    if gs.stadium and not gs.turn_markers.get("stadium_ability"):
        sdef = (_def_for(gs.card_id(gs.stadium[0])) or {}).get("stadiumAbility")
        if sdef is not None and _check_legal(gs, seat, sdef.get("legal", [])):
            opts.append({"type": int(OptionType.ABILITY),
                         "area": int(AreaType.STADIUM), "index": 0})

    # ATTACK tail: barred on the first player's first turn unless the attack text exempts it, and
    # a self-locking attack is OMITTED on the owner's next turn.
    if (b.active is not None and not b.asleep and not b.paralyzed
            and b.active.no_attack_turn != gs.turn):
        from .chain import check_legal, def_for as _adef_for, is_deferred
        for attack_id in available_attack_ids(gs, seat, b.active):
            atk = gs.db.attacks[attack_id]
            adef = _adef_for(f"attack:{attack_id}") or {}
            if is_deferred(adef) and not adef.get("menuOffer", True):
                continue  # the engine menu-gates this attack; other deferred attacks stay OFFERED and raise on use
            if going_first_t1 and not adef.get("allowedFirstTurn"):
                continue
            if b.active.attack_locks.get(str(attack_id)) == gs.turn:
                continue
            if adef.get("legal") and not check_legal(gs, seat, adef["legal"],
                                                     pokemon=b.active):
                continue  # the engine menu-gates conditional attacks
            cost = attack_cost_after_tools(gs, b.active, atk.energies)
            if energy_payable(gs, b.active, cost):
                opts.append({"type": int(OptionType.ATTACK), "attackId": attack_id})

    # RETREAT: once per turn, needs a bench, blocked by sleep/paralysis and a can't-retreat effect
    # (enforced by OMISSION). Cost is payable in provided-energy UNITS, not cards.
    if (b.active is not None and b.bench and not gs.retreated
            and not b.asleep and not b.paralyzed
            and b.active.retreat_lock_turn != gs.turn
            and len(provided_energy(gs, b.active))
            >= effective_retreat_cost(gs, b.active)):
        opts.append({"type": int(OptionType.RETREAT)})

    opts.append({"type": int(OptionType.END)})
    return opts


def pose(gs: GameState, seat: int, *, type: int, context: int, options: list[dict],
         min_count: int = 1, max_count: int = 1, deck_listing=None,
         context_card=None, effect_card=None,
         remain_damage_counter: int = 0, remain_energy_cost: int = 0) -> None:
    gs.turn_action_count += 1
    gs.last_posed = (seat, int(context), min_count, max_count)
    gs.pending = PendingSelect(
        seat=seat, type=int(type), context=int(context), min_count=min_count,
        max_count=max_count, options=options, deck_listing=deck_listing,
        context_card=context_card, effect_card=effect_card,
        remain_damage_counter=remain_damage_counter, remain_energy_cost=remain_energy_cost)


def pose_main(gs: GameState, seat: int) -> None:
    pose(gs, seat, type=SelectType.MAIN, context=SelectContext.MAIN,
         options=main_options(gs, seat))
