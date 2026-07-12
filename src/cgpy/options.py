"""Option-list builders — ALL option generation and ordering lives here (ADR-0050).

Ordering is the highest-risk parity surface (agents choose by index), so every builder
encodes the pinned rules from docs/pyeng/determinism.md §3 and nothing else builds options:

- MAIN: hand-indexed options ascending (PLAY / ATTACH / EVOLVE interleaved by the source
  card's hand index; one ATTACH/EVOLVE option per in-play target, active first then bench
  order), then ABILITY (in-play order), then ATTACK (card's attack order), RETREAT, END.
- CARD selects over a zone list the zone's order, filtered.
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
    """The energy units the attached cards provide, in attach order. Special energies
    with a ChainDef "provides" list use it; Ignition provides {C}{C}{C} on an Evolution
    Pokémon ("providesOnEvolution")."""
    from .chain import def_for

    units: list[int] = []
    holder_is_evolution = bool(gs.stat(p.top).evolvesFrom)
    holder_is_stage2 = gs.stat(p.top).stage2
    for s in p.energy:
        cdef = def_for(gs.card_id(s)) or {}
        if holder_is_stage2 and "providesOnStage2" in cdef:
            units.extend(cdef["providesOnStage2"])   # Neo Upper: 2 all-type on a S2
        elif holder_is_evolution and "providesOnEvolution" in cdef:
            units.extend(cdef["providesOnEvolution"])
        elif "provides" in cdef:
            units.extend(cdef["provides"])
        else:
            units.append(int(gs.stat(s).energyType))
    return units


def provided_units_of(gs: GameState, p: PokemonInPlay, serial: int) -> int:
    """How many energy units one attached card provides on this holder."""
    from .chain import def_for

    cdef = def_for(gs.card_id(serial)) or {}
    if gs.stat(p.top).stage2 and "providesOnStage2" in cdef:
        return len(cdef["providesOnStage2"])
    if bool(gs.stat(p.top).evolvesFrom) and "providesOnEvolution" in cdef:
        return len(cdef["providesOnEvolution"])
    if "provides" in cdef:
        return len(cdef["provides"])
    return 1


def effective_retreat_cost(gs: GameState, p: PokemonInPlay) -> int:
    """Printed retreat cost adjusted by attached-tool modifiers (Air Balloon −2) and
    card passives (Melt Away: free when NO energy cards attached — pinned
    cnt_lavaburst_9980 f32: RETREAT offered on a bare Ethan's Magcargo, cost 3)."""
    from .chain import def_for

    cdef = def_for(gs.card_id(p.top)) or {}
    if cdef.get("retreat", {}).get("freeIfNoEnergy") and not p.energy:
        return 0
    # Passive retreat-zeroing abilities on an in-play holder (Latias ex "Skyliner":
    # "Your Basic Pokémon in play have no Retreat Cost") — an un-suppressed holder on
    # the retreating mon's own side (pinned episode-83688149 f47: a benched Latias ex
    # lets a bare Dreepy retreat).
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
    # Gravity Gemstone: "the Retreat Cost of BOTH Active Pokémon is {C} more" while its
    # holder is Active — a field effect keyed on either active holding one (this fn is
    # only ever called for an Active, so it applies to whichever side is retreating).
    for seat in (0, 1):
        act = gs.players[seat].active
        if act is not None:
            for s in act.tools:
                cost += (def_for(gs.card_id(s)) or {}).get("tool", {}) \
                    .get("retreatBonusBothActive", 0)
    return max(0, cost)


def available_attack_ids(gs: GameState, seat: int, active: PokemonInPlay) -> list[int]:
    """The active's usable attacks. Normally just the top card's. Relicanth's Memory
    Dive ("Each of your evolved Pokémon can use any attack from its previous
    Evolutions") appends every pre-evolution's attacks — own attacks FIRST, then
    pre-evos top-adjacent-first (pinned episode-85046764 f76: an Archaludon ex over a
    Duraludon offers [Metal Defender, Hammer In, Raging Hammer])."""
    from .chain import def_for as _def_for
    from .chain import stadium_def as _stadium_def
    ids = list(gs.stat(active.top).attacks)
    if len(active.stack) <= 1:
        return ids                                  # a Basic: no previous Evolutions
    sup_type = _stadium_def(gs).get("suppressAbilitiesType")
    has_memory_dive = any(
        (_def_for(gs.card_id(p.top)) or {}).get("grantsPreEvoAttacks")
        and not (sup_type is not None
                 and int(gs.stat(p.top).energyType) == sup_type)
        for p in gs.in_play(seat))
    if has_memory_dive:
        for serial in reversed(active.stack[:-1]):  # pre-evolutions, top-adjacent first
            ids += list(gs.stat(serial).attacks)
    return ids


def attack_cost_after_tools(gs: GameState, p: PokemonInPlay, cost: tuple) -> tuple:
    """`cost` reduced by attached-tool discounts: Hop's Choice Band ({C} less for a
    Hop's Pokémon) removes a Colorless requirement; Sparkling Crystal (1 Energy less
    for a Tera holder, "any type") removes one unit, preferring Colorless."""
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
        for _ in range(red_any):        # any-type: drop a Colorless if present, else any
            if int(EnergyType.COLORLESS) in reduced:
                reduced.remove(int(EnergyType.COLORLESS))
            elif reduced:
                reduced.pop()
    return tuple(reduced)


def energy_payable(gs: GameState, p: PokemonInPlay, cost: tuple) -> bool:
    """Whether the attached energy can pay `cost` (colorless-flexible)."""
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

    # Hand-indexed sweep: PLAY / ATTACH / EVOLVE interleaved by hand index (pinned).
    for i, serial in enumerate(b.hand):
        cid = gs.card_id(serial)
        stat = gs.db.card(cid)
        if stat.cardType == CardType.POKEMON and stat.basic:
            if len(b.bench) < b.bench_max:
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
                # Fighting-Roar-class passive on the TARGET: "can evolve during your
                # first turn or the turn you play it" while the opponent's Active is
                # a Pokémon {ex} — megaEx qualifies (pinned rvl1371_9000 f8: Luxray ex
                # EVOLVE offered onto a this-turn Luxio vs Mega Latias ex).
                waived = opp_active_ex and (_cdef_for(gs.card_id(p.top)) or {}).get(
                    "evolve", {}).get("immediateIfOppActiveEx", False)
                # Forest of Vitality: "{G} Pokémon can evolve into {G} Pokémon during
                # the turn they play those Pokémon, except during their first turn" —
                # waives entered_turn only, NOT the turn<=2 ban (UNPINNED shape;
                # kaggle episodes verify).
                forest = (ev_type is not None
                          and int(gs.stat(p.top).energyType) == ev_type
                          and int(stat.energyType) == ev_type)
                if not waived and gs.turn <= 2:
                    continue  # neither player evolves on their own first turn
                if not (waived or forest) and p.entered_turn >= gs.turn:
                    continue  # can't evolve the turn it entered play / evolved
                if gs.stat(p.top).name == stat.evolvesFrom:
                    opts.append({"type": int(OptionType.EVOLVE),
                                 "area": int(AreaType.HAND), "index": i,
                                 "inPlayArea": area, "inPlayIndex": idx})
        elif stat.cardType in (CardType.ITEM, CardType.SUPPORTER):
            from .chain import check_legal, def_for
            cdef = def_for(cid)
            if cdef is None or "play" not in cdef:
                continue  # no/deferred ChainDef: option absent -> visible trace divergence
            if stat.cardType == CardType.SUPPORTER and (
                    gs.supporter_played
                    or (going_first_t1 and not cdef.get("allowedFirstTurn"))):
                continue   # Carmine's "If you go first, you may use this card during
                           # your first turn" waives the T1 supporter ban (pinned
                           # carmine_9000 f4: PLAY offered and taken at t1)
            if stat.cardType == CardType.ITEM and b.items_locked_turn == gs.turn:
                continue  # Itchy-Pollen item lock: PLAY options omitted for one turn
            if check_legal(gs, seat, cdef.get("legal", [])):
                opts.append({"type": int(OptionType.PLAY), "index": i})
        elif stat.cardType == CardType.TOOL:
            from .chain import def_for
            if "tool" not in (def_for(cid) or {}):
                continue  # un-def'd/deferred tool: option absent -> visible divergence
            for area, idx, p in _targets(gs, seat):
                if not p.tools:                    # one tool per Pokémon
                    opts.append({"type": int(OptionType.ATTACH),
                                 "area": int(AreaType.HAND), "index": i,
                                 "inPlayArea": area, "inPlayIndex": idx})
        elif stat.cardType == CardType.STADIUM:
            from .chain import def_for
            if "stadium" not in (def_for(cid) or {}):
                continue  # un-def'd/deferred stadium: option absent -> visible divergence
            if gs.stadium_played:                  # one stadium play per turn
                continue
            if gs.stadium and gs.card_id(gs.stadium[0]) == cid:
                continue                           # same stadium already in play
            opts.append({"type": int(OptionType.PLAY), "index": i})

    # ABILITY options: in-play order (active first, bench order); data-driven opt-in via
    # a def "ability" entry, once per turn per Pokémon (+ optional global-name limit).
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
            continue   # Team Rocket's Watchtower: "{C} Pokémon in play have no
                       # Abilities" — MAIN options suppressed both sides (UNPINNED
                       # shape; triggered/passive abilities of typed mons stay
                       # un-suppressed until a trace demands it)
        if adef.get("oncePerTurnGlobal") and gs.turn_markers.get(f"ability:{cid}"):
            continue
        if not _check_legal(gs, seat, adef.get("legal", []), pokemon=p):
            continue
        opts.append({"type": int(OptionType.ABILITY), "area": area, "index": idx})

    # Stadium per-turn activated effect (Levincia class): ABILITY option on area 7,
    # once per player-turn, gated by the def's legal conds (pinned lev_9000 f40/f51:
    # {type 10, area 7, index 0}; absent after use and without discard targets).
    if gs.stadium and not gs.turn_markers.get("stadium_ability"):
        sdef = (_def_for(gs.card_id(gs.stadium[0])) or {}).get("stadiumAbility")
        if sdef is not None and _check_legal(gs, seat, sdef.get("legal", [])):
            opts.append({"type": int(OptionType.ABILITY),
                         "area": int(AreaType.STADIUM), "index": 0})

    # ATTACK tail (not for the first player's first turn unless the attack's text exempts
    # it — "If you go first, you can use this attack during your first turn"); self-locked
    # attacks (Accelerating Stab / Mega Brave class) are omitted on the owner's next turn
    # (pinned v2_ml_mirror_5100 f130 / 5101 f21).
    if (b.active is not None and not b.asleep and not b.paralyzed
            and b.active.no_attack_turn != gs.turn):   # Snotted-Up lock (seeded)
        from .chain import check_legal, def_for as _adef_for, is_deferred
        for attack_id in available_attack_ids(gs, seat, b.active):
            atk = gs.db.attacks[attack_id]
            adef = _adef_for(f"attack:{attack_id}") or {}
            if is_deferred(adef) and not adef.get("menuOffer", True):
                continue   # engine menu-gates this conditional attack (Terminal-Period
                           # pin, mill_9200 f33); other deferred attacks stay OFFERED
                           # (Phantom-Dive class pin) and raise UnsupportedCard on use
            if going_first_t1 and not adef.get("allowedFirstTurn"):
                continue
            if b.active.attack_locks.get(str(attack_id)) == gs.turn:
                continue
            if adef.get("legal") and not check_legal(gs, seat, adef["legal"],
                                                     pokemon=b.active):
                continue  # engine menu-gates conditional attacks (pinned mill_9200 f33:
            cost = attack_cost_after_tools(gs, b.active, atk.energies)
            if energy_payable(gs, b.active, cost):   # Terminal Period unoffered)
                opts.append({"type": int(OptionType.ATTACK), "attackId": attack_id})

    # RETREAT: once per turn, needs a bench, blocked by sleep/paralysis and a
    # can't-retreat attack effect (engine-enforced by omission, probed 2026-07-02 —
    # tests/sim/test_retreat_lock_engine.py), cost payable in provided-energy UNITS
    # (Ignition on an evolution pays 3 with one card, pinned ms_mirror_1001 f22).
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
