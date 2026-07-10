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
    for s in p.energy:
        cdef = def_for(gs.card_id(s)) or {}
        if holder_is_evolution and "providesOnEvolution" in cdef:
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
    if bool(gs.stat(p.top).evolvesFrom) and "providesOnEvolution" in cdef:
        return len(cdef["providesOnEvolution"])
    if "provides" in cdef:
        return len(cdef["provides"])
    return 1


def effective_retreat_cost(gs: GameState, p: PokemonInPlay) -> int:
    """Printed retreat cost adjusted by attached-tool modifiers (Air Balloon −2)."""
    from .chain import def_for

    cost = gs.stat(p.top).retreatCost
    for s in p.tools:
        cost += (def_for(gs.card_id(s)) or {}).get("tool", {}).get("retreatBonus", 0)
    return max(0, cost)


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
            if not gs.energy_attached:
                for area, idx, _p in _targets(gs, seat):
                    opts.append({"type": int(OptionType.ATTACH), "area": int(AreaType.HAND),
                                 "index": i, "inPlayArea": area, "inPlayIndex": idx})
        elif stat.cardType == CardType.POKEMON and stat.evolvesFrom:
            if gs.turn > 2:  # neither player evolves on their own first turn
                for area, idx, p in _targets(gs, seat):
                    if p.entered_turn >= gs.turn:
                        continue  # can't evolve the turn it entered play / evolved
                    if gs.stat(p.top).name == stat.evolvesFrom:
                        opts.append({"type": int(OptionType.EVOLVE),
                                     "area": int(AreaType.HAND), "index": i,
                                     "inPlayArea": area, "inPlayIndex": idx})
        elif stat.cardType in (CardType.ITEM, CardType.SUPPORTER):
            from .chain import check_legal, def_for
            cdef = def_for(cid)
            if cdef is None:
                continue  # no ChainDef yet: option absent -> visible trace divergence
            if stat.cardType == CardType.SUPPORTER and (gs.supporter_played or
                                                        going_first_t1):
                continue
            if check_legal(gs, seat, cdef.get("legal", [])):
                opts.append({"type": int(OptionType.PLAY), "index": i})
        elif stat.cardType == CardType.TOOL:
            from .chain import def_for
            if def_for(cid) is None:
                continue  # un-def'd tool: option absent -> visible trace divergence
            for area, idx, p in _targets(gs, seat):
                if not p.tools:                    # one tool per Pokémon
                    opts.append({"type": int(OptionType.ATTACH),
                                 "area": int(AreaType.HAND), "index": i,
                                 "inPlayArea": area, "inPlayIndex": idx})
        elif stat.cardType == CardType.STADIUM:
            from .chain import def_for
            if def_for(cid) is None:
                continue
            if gs.stadium_played:                  # one stadium play per turn
                continue
            if gs.stadium and gs.card_id(gs.stadium[0]) == cid:
                continue                           # same stadium already in play
            opts.append({"type": int(OptionType.PLAY), "index": i})

    # ABILITY options: in-play order (active first, bench order); data-driven opt-in via
    # a def "ability" entry, once per turn per Pokémon (+ optional global-name limit).
    from .chain import check_legal as _check_legal
    from .chain import def_for as _def_for
    for area, idx, p in _targets(gs, seat):
        cid = gs.card_id(p.top)
        adef = (_def_for(cid) or {}).get("ability")
        if adef is None or p.ability_used_turn >= gs.turn:
            continue
        if adef.get("oncePerTurnGlobal") and gs.turn_markers.get(f"ability:{cid}"):
            continue
        if not _check_legal(gs, seat, adef.get("legal", []), pokemon=p):
            continue
        opts.append({"type": int(OptionType.ABILITY), "area": area, "index": idx})

    # ATTACK tail (not for the first player's first turn); self-locked attacks
    # (Accelerating Stab / Mega Brave class) are omitted on the owner's next turn
    # (pinned v2_ml_mirror_5100 f130 / 5101 f21).
    if b.active is not None and not going_first_t1 and not b.asleep and not b.paralyzed:
        for attack_id in gs.stat(b.active.top).attacks:
            atk = gs.db.attacks[attack_id]
            if b.active.attack_locks.get(str(attack_id)) == gs.turn:
                continue
            if energy_payable(gs, b.active, atk.energies):
                opts.append({"type": int(OptionType.ATTACK), "attackId": attack_id})

    # RETREAT: once per turn, needs a bench, blocked by sleep/paralysis, cost payable —
    # in provided-energy UNITS (Ignition on an evolution pays 3 with one card, pinned
    # ms_mirror_1001 f22).
    if (b.active is not None and b.bench and not gs.retreated
            and not b.asleep and not b.paralyzed
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
