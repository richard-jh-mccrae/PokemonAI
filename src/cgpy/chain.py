"""The effect-DSL interpreter: ChainDef programs over a small op vocabulary (ADR-0050 M2).

A card's behavior is DATA — a list of ops (`defs/chain_overrides.json`, later also
`generated_chains.json`) executed on a resumable frame stack. One executor per op; ops that
need a player decision pose a select and the frame resumes on the answer. Op names follow the
recovered native `Chain` vocabulary where the mapping is direct (`effectDraw`,
`effectDeckToHandAndShuffle`, `costHandTrash`, …); composite convenience ops are marked `x`
(`xLookTopMayTakeThenShuffle`). Frames are plain data → `clone()` stays a deep copy.

M2 scope: trainer play programs + play-legality conditions. Ability/attack-rider programs
join incrementally behind the same interpreter.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .options import opt_card, pose
from .schema import (AreaType, CardType, LogType, OptionType, SelectContext, SelectType)
from .state import EffectFrame, GameState

_DEFS = Path(__file__).resolve().parent / "defs"


@lru_cache(maxsize=1)
def load_chain_defs() -> dict:
    """{cardId(str): {"play": [...ops], "legal": [...conds], ...}} — overrides layer only
    for now (generated seeds arrive with the pool-wide fan-out)."""
    path = _DEFS / "chain_overrides.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def def_for(card_id: int) -> dict | None:
    return load_chain_defs().get(str(card_id))


class UnsupportedCard(NotImplementedError):
    """A card without a ChainDef was exercised — fail loud, never guess (ADR-0050)."""


# ---------------------------------------------------------------------------- filters

def _card_matches(gs: GameState, serial: int, flt: dict) -> bool:
    stat = gs.stat(serial)
    if "cardType" in flt and stat.cardType not in flt["cardType"]:
        return False
    if flt.get("basic") is not None and stat.basic != flt["basic"]:
        return False
    if flt.get("pokemon") and stat.cardType != CardType.POKEMON:
        return False
    if flt.get("energy") and stat.cardType not in (CardType.BASIC_ENERGY,
                                                   CardType.SPECIAL_ENERGY):
        return False
    if flt.get("basicEnergy") and stat.cardType != CardType.BASIC_ENERGY:
        return False
    if flt.get("pokemonOrBasicEnergy") and stat.cardType not in (
            CardType.POKEMON, CardType.BASIC_ENERGY):
        return False
    if "hpMax" in flt and (stat.cardType != CardType.POKEMON or stat.hp > flt["hpMax"]):
        return False
    if "nameNot" in flt and stat.name == flt["nameNot"]:
        return False
    if flt.get("megaEx") and not stat.megaEx:
        return False
    if flt.get("evolution") and not stat.evolvesFrom:
        return False
    if flt.get("noRuleBox") and (stat.ex or stat.megaEx):
        return False
    if flt.get("hasAbility") is not None and bool(stat.skills) != flt["hasAbility"]:
        return False
    return True


# ---------------------------------------------------------------------------- conditions

def check_legal(gs: GameState, seat: int, conds: list) -> bool:
    """Play-legality: every condition must hold (the engine offers PLAY only then)."""
    b = gs.players[seat]
    for c in conds:
        op = c["op"]
        if op == "benchSpace":
            if len(b.bench) >= b.bench_max:
                return False
        elif op == "handOthers":                   # discard-cost needs n OTHER hand cards
            if len(b.hand) - 1 < c["n"]:
                return False
        elif op == "deckNotEmpty":
            if not b.deck:
                return False
        elif op == "oppBenchExists":
            if not gs.players[1 - seat].bench:
                return False
        elif op == "oppEnergyExists":
            if not any(p.energy for p in gs.in_play(1 - seat)):
                return False
        elif op == "discardHas":
            if not any(_card_matches(gs, s, c["filter"]) for s in b.discard):
                return False
        elif op == "deckHas":                      # NOTE: peeks; used only where pinned
            if not any(_card_matches(gs, s, c["filter"]) for s in b.deck):
                return False
        elif op == "selfDamaged":
            if not any(p.hp < p.max_hp for p in gs.in_play(seat)):
                return False
        elif op == "handNotEmptyBesides":
            if len(b.hand) <= 1:
                return False
        else:
            raise UnsupportedCard(f"unknown legality op {op!r}")
    return True


# ---------------------------------------------------------------------------- interpreter

def start_program(gs: GameState, seat: int, source_serial: int, ops: list,
                  *, kind: str = "play") -> None:
    gs.frames.append(EffectFrame(program=list(ops), pc=0, vars={},
                                 seat=seat, source=source_serial, kind=kind))
    run_frames(gs)


def run_frames(gs: GameState) -> None:
    """Execute the top frame until it poses a select, finishes, or the game ends."""
    while gs.frames and gs.pending is None and gs.result == -1:
        fr = gs.frames[-1]
        if fr.pc >= len(fr.program):
            gs.frames.pop()
            _after_program(gs, fr)
            continue
        op = fr.program[fr.pc]
        handler = OPS.get(op["op"])
        if handler is None:
            raise UnsupportedCard(f"unknown chain op {op['op']!r} (card serial {fr.source})")
        advanced = handler(gs, fr, op)
        if advanced:
            fr.pc += 1


def _after_program(gs: GameState, fr: EffectFrame) -> None:
    """A finished play-program returns control to the turn loop (re-pose MAIN)."""
    if gs.frames or gs.pending is not None or gs.result != -1:
        return
    if fr.kind in ("play", "ability"):
        from .options import pose_main
        pose_main(gs, fr.seat)


def resume(gs: GameState, indices: list[int]) -> None:
    """Route a select answer into the top frame and continue."""
    fr = gs.frames[-1]
    fr.vars["answer"] = indices
    fr.vars["answered_options"] = [gs.pending.options[i] for i in indices]
    fr.vars["answered_listing"] = gs.pending.deck_listing
    gs.pending = None
    run_frames(gs)


# ---------------------------------------------------------------------------- op helpers

def _zone_options(gs: GameState, seat: int, zone: list[int], area: int,
                  flt: dict) -> list[dict]:
    return [opt_card(area, i, seat) for i, s in enumerate(zone)
            if _card_matches(gs, s, flt)]


def _shuffle(gs: GameState, seat: int) -> None:
    gs.shuffle_deck(seat)


def _select_from_deck(gs: GameState, fr: EffectFrame, args: dict, context: int) -> bool:
    """Two-phase deck search: pose (reveal the deck listing) then act on the answer."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        opts = _zone_options(gs, seat, b.deck, AreaType.DECK, args.get("filter", {}))
        pose(gs, seat, type=SelectType.CARD, context=context, options=opts,
             min_count=args.get("min", 0), max_count=min(args.get("max", 1), len(opts)),
             deck_listing=list(b.deck), effect_card=fr.source)
        return False
    fr.vars["picked"] = [b.deck[o["index"]] for o in fr.vars.pop("answered_options")]
    fr.vars.pop("answer")
    return True


# ---------------------------------------------------------------------------- ops

def op_effect_draw(gs, fr, args) -> bool:
    for _ in range(args.get("n", 1)):
        gs.draw(fr.seat)
    return True


def op_effect_draw_until(gs, fr, args) -> bool:
    b = gs.players[fr.seat]
    while len(b.hand) < args["n"] and b.deck:
        gs.draw(fr.seat)
    return True


def op_cost_hand_trash(gs, fr, args) -> bool:
    """Discard n OTHER cards from hand as a cost (Ultra Ball)."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        opts = [opt_card(AreaType.HAND, i, seat) for i in range(len(b.hand))]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.DISCARD,
             options=opts, min_count=args["n"], max_count=args["n"],
             effect_card=fr.source)
        return False
    serials = [b.hand[o["index"]] for o in fr.vars.pop("answered_options")]
    fr.vars.pop("answer")
    for s in serials:
        b.hand.remove(s)
        b.discard.append(s)
        gs.move_card(s, AreaType.HAND, AreaType.DISCARD, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    return True


def op_deck_to_hand_and_shuffle(gs, fr, args) -> bool:
    if not _select_from_deck(gs, fr, args, SelectContext.TO_HAND):
        return False
    seat = fr.seat
    b = gs.players[seat]
    for s in fr.vars.pop("picked"):
        b.deck.remove(s)
        b.hand.append(s)
        gs.move_card(s, AreaType.DECK, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    _shuffle(gs, seat)
    return True


def op_deck_to_bench_and_shuffle(gs, fr, args) -> bool:
    if not _select_from_deck(gs, fr, args, SelectContext.TO_BENCH):
        return False
    seat = fr.seat
    b = gs.players[seat]
    from .turn import _new_in_play
    for s in fr.vars.pop("picked"):
        b.deck.remove(s)
        b.bench.append(_new_in_play(gs, s))
        gs.move_card(s, AreaType.DECK, AreaType.BENCH, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    _shuffle(gs, seat)
    return True


def op_effect_switch_me(gs, fr, args) -> bool:
    """Switch own Active with a chosen benched Pokémon (Switch / Dunsparce class)."""
    seat = fr.seat
    b = gs.players[seat]
    if not b.bench:
        return True
    if "answer" not in fr.vars:
        opts = [opt_card(AreaType.BENCH, i, seat) for i in range(len(b.bench))]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.SWITCH,
             options=opts, effect_card=fr.source)
        return False
    idx = fr.vars.pop("answered_options")[0]["index"]
    fr.vars.pop("answer")
    from .turn import _do_switch
    _do_switch(gs, seat, idx, retreat=False)
    return True


def op_effect_switch_enemy(gs, fr, args) -> bool:
    """Gust: choose an opponent benched Pokémon into their Active (Boss's Orders)."""
    seat = fr.seat
    opp = 1 - seat
    ob = gs.players[opp]
    if not ob.bench:
        return True
    if "answer" not in fr.vars:
        opts = [opt_card(AreaType.BENCH, i, opp) for i in range(len(ob.bench))]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.SWITCH,
             options=opts, effect_card=fr.source)
        return False
    idx = fr.vars.pop("answered_options")[0]["index"]
    fr.vars.pop("answer")
    from .turn import _do_switch
    _do_switch(gs, opp, idx, retreat=False)
    return True


def op_coin(gs, fr, args) -> bool:
    fr.vars["heads"] = gs.coin_flip(fr.seat)
    return True


def op_if_heads(gs, fr, args) -> bool:
    """Skip the next `skip` ops when the last flip was tails."""
    if not fr.vars.get("heads"):
        fr.pc += args.get("skip", 1)
    return True


def op_trash_energy_enemy(gs, fr, args) -> bool:
    """Discard one energy from any opponent Pokémon (Crushing Hammer, post-heads)."""
    seat = fr.seat
    opp = 1 - seat
    targets: list[tuple[int, int, int]] = []      # (area, in-play index, energy index)
    ob = gs.players[opp]
    plist = ([(int(AreaType.ACTIVE), 0, ob.active)] if ob.active else []) + \
        [(int(AreaType.BENCH), i, p) for i, p in enumerate(ob.bench)]
    options = []
    for area, idx, p in plist:
        for k, _s in enumerate(p.energy):
            options.append({"type": int(OptionType.ENERGY), "area": area, "index": idx,
                            "playerIndex": opp, "energyIndex": k, "count": 1})
            targets.append((area, idx, k))
    if not options:
        return True
    if "answer" not in fr.vars:
        fr.vars["targets"] = targets
        pose(gs, seat, type=SelectType.ENERGY, context=SelectContext.DISCARD_ENERGY,
             options=options, effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    fr.vars.pop("targets", None)
    p = ob.active if o["area"] == int(AreaType.ACTIVE) else ob.bench[o["index"]]
    serial = p.energy[o["energyIndex"]]
    p.energy.remove(serial)
    ob.discard.append(serial)
    gs.move_card(serial, AreaType.ENERGY, AreaType.DISCARD, seat=opp,
                 visible_to_owner=True, visible_to_opponent=True)
    return True


def op_trash_to_hand(gs, fr, args) -> bool:
    """Recover matching card(s) from own discard to hand (Night Stretcher)."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        opts = _zone_options(gs, seat, b.discard, AreaType.DISCARD,
                             args.get("filter", {}))
        if not opts:
            return True
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_HAND,
             options=opts, min_count=args.get("min", 1),
             max_count=min(args.get("max", 1), len(opts)), effect_card=fr.source)
        return False
    serials = [b.discard[o["index"]] for o in fr.vars.pop("answered_options")]
    fr.vars.pop("answer")
    for s in serials:
        b.discard.remove(s)
        b.hand.append(s)
        gs.move_card(s, AreaType.DISCARD, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    return True


def op_hand_to_deck_shuffle_draw(gs, fr, args) -> bool:
    """Judge class: EACH player shuffles hand into deck and draws n (opponent first per
    pin-to-come; start with actor first and let the differ decide)."""
    for seat in (fr.seat, 1 - fr.seat):
        b = gs.players[seat]
        for s in list(reversed(b.hand)):
            b.hand.remove(s)
            b.deck.append(s)
            gs.move_card(s, AreaType.HAND, AreaType.DECK, seat=seat,
                         visible_to_owner=True, visible_to_opponent=False)
        _shuffle(gs, seat)
        for _ in range(args.get("n", 4)):
            gs.draw(seat)
    return True


def op_own_hand_to_deck_shuffle_draw(gs, fr, args) -> bool:
    """Lillie's class: shuffle own hand into deck, draw n."""
    seat = fr.seat
    b = gs.players[seat]
    for s in list(reversed(b.hand)):
        b.hand.remove(s)
        b.deck.append(s)
        gs.move_card(s, AreaType.HAND, AreaType.DECK, seat=seat,
                     visible_to_owner=True, visible_to_opponent=False)
    _shuffle(gs, seat)
    for _ in range(args.get("n", 6)):
        gs.draw(seat)
    return True


OPS = {
    "effectDraw": op_effect_draw,
    "effectDrawUntil": op_effect_draw_until,
    "costHandTrash": op_cost_hand_trash,
    "effectDeckToHandAndShuffle": op_deck_to_hand_and_shuffle,
    "effectDeckToBenchAndShuffle": op_deck_to_bench_and_shuffle,
    "effectSwitchMe": op_effect_switch_me,
    "effectSwitchEnemy": op_effect_switch_enemy,
    "coin": op_coin,
    "ifHeads": op_if_heads,
    "trashEnergyEnemy": op_trash_energy_enemy,
    "effectTrashToHand": op_trash_to_hand,
    "xBothShuffleHandDraw": op_hand_to_deck_shuffle_draw,
    "xOwnShuffleHandDraw": op_own_hand_to_deck_shuffle_draw,
}
