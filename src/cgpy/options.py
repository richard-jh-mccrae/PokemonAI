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


def energy_payable(gs: GameState, p: PokemonInPlay, cost: tuple) -> bool:
    """Whether the attached energy can pay `cost` (colorless-flexible)."""
    from .schema import EnergyType

    pool: list[int] = []
    for s in p.energy:
        pool.append(int(gs.stat(s).energyType))
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
        # TOOL / STADIUM programs land with their trace divergences (M2 burn-down)

    # ATTACK tail (not for the first player's first turn).
    if b.active is not None and not going_first_t1 and not b.asleep and not b.paralyzed:
        for attack_id in gs.stat(b.active.top).attacks:
            atk = gs.db.attacks[attack_id]
            if energy_payable(gs, b.active, atk.energies):
                opts.append({"type": int(OptionType.ATTACK), "attackId": attack_id})

    # RETREAT: once per turn, needs a bench, blocked by sleep/paralysis, cost payable.
    if (b.active is not None and b.bench and not gs.retreated
            and not b.asleep and not b.paralyzed
            and len(b.active.energy) >= gs.stat(b.active.top).retreatCost):
        opts.append({"type": int(OptionType.RETREAT)})

    opts.append({"type": int(OptionType.END)})
    return opts


def pose(gs: GameState, seat: int, *, type: int, context: int, options: list[dict],
         min_count: int = 1, max_count: int = 1, deck_listing=None,
         context_card=None, effect_card=None,
         remain_damage_counter: int = 0, remain_energy_cost: int = 0) -> None:
    gs.turn_action_count += 1
    gs.last_posed = (seat, int(context))
    gs.pending = PendingSelect(
        seat=seat, type=int(type), context=int(context), min_count=min_count,
        max_count=max_count, options=options, deck_listing=deck_listing,
        context_card=context_card, effect_card=effect_card,
        remain_damage_counter=remain_damage_counter, remain_energy_cost=remain_energy_cost)


def pose_main(gs: GameState, seat: int) -> None:
    pose(gs, seat, type=SelectType.MAIN, context=SelectContext.MAIN,
         options=main_options(gs, seat))
