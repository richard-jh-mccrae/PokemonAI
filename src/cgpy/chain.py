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


def stadium_hp_delta(gs: GameState, p) -> int:
    """The in-play stadium's HP modifier for this Pokémon (Gravity Mountain: Stage 2s
    −30 both sides, pinned ml_dx_2001 f112: 320-HP Dragapult ex renders 290). Damage
    counters live on stored hp/max_hp; the delta floats with the stadium."""
    if not gs.stadium:
        return 0
    sdef = (def_for(gs.card_id(gs.stadium[0])) or {}).get("stadium", {})
    if "stage2HpDelta" in sdef and gs.stat(p.top).stage2:
        return sdef["stage2HpDelta"]
    return 0


# ---------------------------------------------------------------------------- filters

def _card_matches(gs: GameState, serial: int, flt: dict) -> bool:
    stat = gs.stat(serial)
    if "anyOf" in flt:
        return any(_card_matches(gs, serial, sub) for sub in flt["anyOf"])
    if "cardType" in flt and stat.cardType not in flt["cardType"]:
        return False
    if "energyType" in flt and int(stat.energyType) not in flt["energyType"]:
        return False   # NB: for Pokémon, energyType IS the elemental type (pinned)
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
    if flt.get("stage2") and not stat.stage2:
        return False
    if flt.get("evolution") and not stat.evolvesFrom:
        return False
    if flt.get("noRuleBox") and (stat.ex or stat.megaEx):
        return False
    if flt.get("hasAbility") is not None and bool(stat.skills) != flt["hasAbility"]:
        return False
    return True


# ---------------------------------------------------------------------------- conditions

def check_legal(gs: GameState, seat: int, conds: list, pokemon=None) -> bool:
    """Play/ability-legality: every condition must hold (the engine offers the option
    only then). `pokemon` is the in-play holder for ability conditions."""
    b = gs.players[seat]
    for c in conds:
        op = c["op"]
        if op == "benchSpace":
            if len(b.bench) >= b.bench_max:
                return False
        elif op == "benchExists":                  # Switch: needs a benched Pokémon
            if not b.bench:                        # (pinned v2_ml_mirror_5101 f22)
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
        elif op == "megaExDamagedInPlay":     # Wally's: the engine peeks for DAMAGE
            if not any(gs.stat(p.top).megaEx and p.hp < p.max_hp
                       for p in gs.in_play(seat)):   # (pinned ms_mirror_1001 f33:
                return False                         # undamaged mega -> not offered)
        elif op == "prizesMoreThanOpp":       # Rosa's: MORE prizes remaining = behind
            if len(b.prize) <= len(gs.players[1 - seat].prize):
                return False
        elif op == "koLastTurn":              # Unfair Stamp: own KO on opp's last turn
            if gs.ko_turn[seat] != gs.turn - 1:
                return False
        elif op == "handHas":
            if not any(_card_matches(gs, s, c["filter"]) for s in b.hand):
                return False
        elif op == "inPlayNamed":
            if not any(gs.stat(p.top).name == c["name"] for p in gs.in_play(seat)):
                return False
        elif op == "inPlayHas":
            if not any(_card_matches(gs, p.top, c["filter"])
                       for p in gs.in_play(seat)):
                return False
        elif op == "selfHasEnergyType":       # ability holder has an energy of this type
            if pokemon is None or not any(
                    int(gs.stat(s).energyType) == c["energyType"]
                    for s in pokemon.energy):
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
    """A finished play-program: the trainer lands in the discard NOW — at resolution, not
    on play, and silently (no MOVE_CARD log) — pinned ms_mirror_1000 f10/f11 (Pokégear
    absent from discard during its select, present after, no move entry) and f16
    (Salvatore same). Then queued triggers flush (they pose after the discard — pinned
    ml_dx_2000 f30), an attack proceeds to its KO sweep, or control returns to MAIN."""
    if fr.kind == "play":
        gs.players[fr.seat].discard.append(fr.source)
    if gs.frames or gs.pending is not None or gs.result != -1:
        return
    if fr.kind == "attack":
        from .turn import _after_attack
        _after_attack(gs, fr.seat)
    elif fr.kind in ("play", "ability"):
        from .turn import flush_triggers
        flush_triggers(gs, fr.seat)


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
    """Two-phase deck search: pose (reveal the deck listing) then act on the answer.
    A zero-option optional search is NEVER posed — the engine auto-resolves it as a
    no-pick (pinned ms_mirror_1001 f9: Poffin with no matching basics logs PLAY+SHUFFLE
    only, no select)."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        opts = _zone_options(gs, seat, b.deck, AreaType.DECK, args.get("filter", {}))
        if not opts and args.get("min", 0) == 0:
            gs.turn_action_count += 1     # the skipped ask still bumps tac (pinned
            fr.vars["picked"] = []        # ms_mirror_1001 f9, same as the setup rule)
            return True
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
    """Discard n (filter-matching) cards from hand as a cost (Ultra Ball, Lunar Cycle)."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        flt = args.get("filter")
        opts = [opt_card(AreaType.HAND, i, seat) for i, s in enumerate(b.hand)
                if flt is None or _card_matches(gs, s, flt)]
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
    seat = fr.seat
    b = gs.players[seat]
    room = b.bench_max - len(b.bench)
    args = dict(args, max=min(args.get("max", 1), room))   # maxCount clamps by bench
    if not _select_from_deck(gs, fr, args, SelectContext.TO_BENCH):   # room (pinned
        return False                                                  # v2_ml_dx_5501 f14)
    from .turn import _after_benched, _new_in_play
    for s in fr.vars.pop("picked"):
        b.deck.remove(s)
        p = _new_in_play(gs, s)
        b.bench.append(p)
        gs.move_card(s, AreaType.DECK, AreaType.BENCH, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
        _after_benched(gs, seat, p)
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
    """Discard one energy from any opponent Pokémon (Crushing Hammer, post-heads).
    Options list the opponent's energies in GLOBAL ATTACH ORDER, oldest first (pinned
    ml_dx_2001 f175 / ml_dx_2000 f95 / ms_mirror_1001 f83)."""
    seat = fr.seat
    opp = 1 - seat
    ob = gs.players[opp]
    plist = ([(int(AreaType.ACTIVE), 0, ob.active)] if ob.active else []) + \
        [(int(AreaType.BENCH), i, p) for i, p in enumerate(ob.bench)]
    from .options import provided_units_of
    entries = []                                  # (attach tick, option dict)
    for area, idx, p in plist:
        for k, s in enumerate(p.energy):
            entries.append((gs.attach_seq.get(s, 0),
                            {"type": int(OptionType.ENERGY), "area": area, "index": idx,
                             "playerIndex": opp, "energyIndex": k,
                             "count": provided_units_of(gs, p, s)}))
    entries.sort(key=lambda e: e[0])
    options = [o for _tick, o in entries]
    if not options:
        return True
    if "answer" not in fr.vars:
        pose(gs, seat, type=SelectType.ENERGY, context=SelectContext.DISCARD_ENERGY,
             options=options, effect_card=fr.source,
             remain_energy_cost=1)     # pinned ms_mirror_1002 f14 (Crushing Hammer)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
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


def _both_shuffle_hands(gs, actor: int) -> None:
    """Both players return hands to deck and shuffle — actor's moves+shuffle first, then
    the opponent's, BEFORE any draws (pinned ml_dx_2000 f44/f45 Judge windows). Per-player
    return order is front-to-back hand order (pinned ms_mirror_1000 f9)."""
    for seat in (actor, 1 - actor):
        b = gs.players[seat]
        for s in list(b.hand):
            b.hand.remove(s)
            b.deck.append(s)
            gs.move_card(s, AreaType.HAND, AreaType.DECK, seat=seat,
                         visible_to_owner=True, visible_to_opponent=False)
        _shuffle(gs, seat)


def op_hand_to_deck_shuffle_draw(gs, fr, args) -> bool:
    """Judge / Unfair Stamp class: both shuffle hands in (actor first), THEN actor draws
    n and opponent draws nOpp (default n) — draws after both shuffles (pinned f44/f45)."""
    _both_shuffle_hands(gs, fr.seat)
    for seat, count in ((fr.seat, args.get("n", 4)),
                        (1 - fr.seat, args.get("nOpp", args.get("n", 4)))):
        for _ in range(count):
            gs.draw(seat)
    return True


def op_both_shuffle_coin_draw(gs, fr, args) -> bool:
    """Harlequin: both shuffle hands in (actor first), flip a coin, then actor/opponent
    draw [heads] or [tails] counts (actor's count first in each pair)."""
    _both_shuffle_hands(gs, fr.seat)
    heads = gs.coin_flip(fr.seat)
    n_actor, n_opp = args["heads"] if heads else args["tails"]
    for seat, count in ((fr.seat, n_actor), (1 - fr.seat, n_opp)):
        for _ in range(count):
            gs.draw(seat)
    return True


def op_own_hand_to_deck_shuffle_draw(gs, fr, args) -> bool:
    """Lillie's class: shuffle own hand into deck, draw n — nIfExactPrizes overrides n by
    own remaining-prize count ("draw 8 instead if exactly 6 Prize cards remaining", pinned
    ms_mirror_1000 f9: 8 drawn at 6 prizes). Return moves run front-to-back in hand order
    (pinned f9 — NOT the mulligan's LIFO)."""
    seat = fr.seat
    b = gs.players[seat]
    for s in list(b.hand):
        b.hand.remove(s)
        b.deck.append(s)
        gs.move_card(s, AreaType.HAND, AreaType.DECK, seat=seat,
                     visible_to_owner=True, visible_to_opponent=False)
    _shuffle(gs, seat)
    n = args.get("n", 6)
    n = args.get("nIfExactPrizes", {}).get(str(len(b.prize)), n)
    for _ in range(n):
        gs.draw(seat)
    return True


AREA_DECK_BOTTOM = 14   # wire value in MOVE logs for bottom-of-deck (beyond the AreaType
                        # snapshot; pinned ml_dx_2000 f28, Drakloak's Recon Directive)


def op_order_triggers(gs, fr, args) -> bool:
    """Several simultaneous triggers: pose SKILL_ORDER (one SKILL option per trigger,
    min=max=count; pinned ml_dx_2000 f30, ml_dx_2001 f46), then run them as their own
    frames in the answered order (each keeps its own source for contextCard rendering)."""
    trigs = args["triggers"]
    if "answer" not in fr.vars:
        opts = [{"type": int(OptionType.SKILL), "cardId": t["cardId"],
                 "serial": t["serial"]} for t in trigs]
        pose(gs, fr.seat, type=SelectType.SKILL, context=SelectContext.SKILL_ORDER,
             options=opts, min_count=len(trigs), max_count=len(trigs))
        return False
    order = fr.vars.pop("answer")
    fr.vars.pop("answered_options")
    for i in reversed(order):                      # stack: last pushed runs first
        t = trigs[i]
        gs.frames.append(EffectFrame(program=list(t["ops"]), pc=0, vars={},
                                     seat=fr.seat, source=t["source"], kind="ability"))
    return True


def op_bench_counter_damage(gs, fr, args) -> bool:
    """A stadium bench trigger's payload: damage counters on the just-benched Pokémon
    (Risky Ruins; pinned ml_dx_2001 f28: HP_CHANGE putDamageCounter=true, owner seat)."""
    for p in gs.in_play(fr.seat):
        if p.top == args["serial"]:
            p.hp = max(0, p.hp - args["damage"])
            gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": fr.seat,
                     "cardId": gs.card_id(p.top), "serial": p.top,
                     "value": -args["damage"], "putDamageCounter": True})
            break
    return True


def op_choose_bench_damage(gs, fr, args) -> bool:
    """Attack rider: choose one opponent benched Pokémon, deal flat damage (no W/R on
    bench). Pinned ms_mirror_1002 f25-f26 (Jetting Blow): DAMAGE ctx, effect=attacker,
    options over the defender's bench, HP_CHANGE putDamageCounter=false."""
    seat = fr.seat
    opp = 1 - seat
    ob = gs.players[opp]
    if not ob.bench:
        return True
    if "answer" not in fr.vars:
        opts = [opt_card(AreaType.BENCH, i, opp) for i in range(len(ob.bench))]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.DAMAGE,
             options=opts, min_count=1, max_count=1, effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    target = ob.bench[o["index"]]
    dmg = args["damage"]
    if gs.stat(target.top).tera:
        dmg = 0        # benched Tera Pokémon take no attack damage; the HP_CHANGE still
    target.hp = max(0, target.hp - dmg)   # logs with value 0 (pinned v2_ms_dx_5401 f100)
    gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": opp,
             "cardId": gs.card_id(target.top), "serial": target.top,
             "value": -dmg, "putDamageCounter": False})
    return True


def op_choose_any_damage(gs, fr, args) -> bool:
    """Cruel Arrow (pinned v2_dx_mirror_5201 f54): choose ANY one opponent Pokémon
    (ctx DAMAGE, active first then bench, effect=attacker); flat damage on the bench
    (no W/R, Tera-bench prevention), W/R-adjusted on the Active (card text)."""
    seat = fr.seat
    opp = 1 - seat
    ob = gs.players[opp]
    if "answer" not in fr.vars:
        from .options import _targets
        opts = [opt_card(area, idx, opp) for area, idx, _p in _targets(gs, opp)]
        if not opts:
            return True
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.DAMAGE,
             options=opts, min_count=1, max_count=1, effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    dmg = args["damage"]
    if o["area"] == int(AreaType.ACTIVE):
        from .damage import apply_weakness_resistance
        target = ob.active
        dmg = apply_weakness_resistance(gs, gs.players[seat].active, target, dmg)
    else:
        target = ob.bench[o["index"]]
        if gs.stat(target.top).tera:
            dmg = 0                    # benched Tera Pokémon take no attack damage
    target.hp = max(0, target.hp - dmg)
    gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": opp,
             "cardId": gs.card_id(target.top), "serial": target.top,
             "value": -dmg, "putDamageCounter": False})
    return True


def op_inflict_condition_active(gs, fr, args) -> bool:
    """Attack rider: inflict a special condition on the defending Active (pinned
    v2_ml_dx_5501 f22: Mind Bend logs CONFUSED isRecover=false after the damage)."""
    opp = 1 - fr.seat
    ob = gs.players[opp]
    if ob.active is None:
        return True
    cond = args["condition"]
    log_type = {0: LogType.POISONED, 1: LogType.BURNED, 2: LogType.ASLEEP,
                3: LogType.PARALYZED, 4: LogType.CONFUSED}[cond]
    flag = {0: "poisoned", 1: "burned", 2: "asleep", 3: "paralyzed", 4: "confused"}[cond]
    setattr(ob, flag, True)
    if cond == 3:
        ob.paralyzed_since_turn = gs.turn
    gs.emit({"type": int(log_type), "playerIndex": opp, "isRecover": False,
             "cardId": gs.card_id(ob.active.top), "serial": ob.active.top})
    return True


def op_discard_energy_attach_bench(gs, fr, args) -> bool:
    """Aura Jab (pinned ml_dx_2000 f168-f170): pick up to `max` filter-matching energies
    from OWN discard (ctx 22, min 0), then per energy pick a benched target (ctx 21,
    min 1, contextCard = that energy); each attach emits the plain ATTACH log."""
    seat = fr.seat
    b = gs.players[seat]
    if "picked" not in fr.vars:
        if "answer" not in fr.vars:
            opts = _zone_options(gs, seat, b.discard, AreaType.DISCARD,
                                 args.get("filter", {}))
            if not opts:                # skipped rider: NO tac bump (pinned v2_ms_ml_5300
                return True             # f25 — unlike the deck-search family)
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_TO,
                 options=opts, min_count=0,
                 max_count=min(args.get("max", 3), len(opts)), effect_card=fr.source)
            return False
        fr.vars["picked"] = [b.discard[o["index"]]
                             for o in fr.vars.pop("answered_options")]
        fr.vars.pop("answer")
    while fr.vars["picked"]:
        energy = fr.vars["picked"][0]
        if "answer" not in fr.vars:
            opts = [opt_card(AreaType.BENCH, i, seat) for i in range(len(b.bench))]
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_FROM,
                 options=opts, min_count=1, max_count=1,
                 context_card=energy, effect_card=fr.source)
            return False
        o = fr.vars.pop("answered_options")[0]
        fr.vars.pop("answer")
        target = b.bench[o["index"]]
        b.discard.remove(energy)
        target.energy.append(energy)
        gs.note_attach(energy)
        gs.emit({"type": int(LogType.ATTACH), "playerIndex": seat,
                 "cardId": gs.card_id(energy), "serial": energy,
                 "cardIdTarget": gs.card_id(target.top), "serialTarget": target.top})
        fr.vars["picked"].pop(0)
    fr.vars.pop("picked")
    return True


def op_discard_energy_attach_one_target(gs, fr, args) -> bool:
    """Rosa's Encouragement (pinned v2_ms_dx_5401 f144-f146): pick min..max matching
    energies from OWN discard (ctx 22), then ONE in-play target matching targetFilter
    (ctx 21, no contextCard); all picks attach to it in answer order (ATTACH logs)."""
    seat = fr.seat
    b = gs.players[seat]
    if "picked" not in fr.vars:
        if "answer" not in fr.vars:
            opts = _zone_options(gs, seat, b.discard, AreaType.DISCARD,
                                 args.get("filter", {}))
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_TO,
                 options=opts, min_count=args.get("min", 1),
                 max_count=min(args.get("max", 2), len(opts)), effect_card=fr.source)
            return False
        fr.vars["picked"] = [b.discard[o["index"]]
                             for o in fr.vars.pop("answered_options")]
        fr.vars.pop("answer")
    if "answer" not in fr.vars:
        from .options import _targets
        opts = [opt_card(area, idx, seat) for area, idx, p in _targets(gs, seat)
                if _card_matches(gs, p.top, args.get("targetFilter", {}))]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_FROM,
             options=opts, min_count=1, max_count=1, effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    from .turn import _target_of
    target = _target_of(gs, seat, o["area"], o["index"])
    for s in fr.vars.pop("picked"):
        b.discard.remove(s)
        target.energy.append(s)
        gs.note_attach(s)
        gs.emit({"type": int(LogType.ATTACH), "playerIndex": seat,
                 "cardId": gs.card_id(s), "serial": s,
                 "cardIdTarget": gs.card_id(target.top), "serialTarget": target.top})
    return True


def op_move_damage_counters(gs, fr, args) -> bool:
    """Munkidori's Adrena-Brain (pinned ml_dx_2000 f120-f123): pick a damaged own
    Pokémon (ctx REMOVE_DAMAGE_COUNTER), pick 1..min(max, its damage) counters (COUNT
    select, ctx REMOVE_DAMAGE_COUNTER_COUNT, contextCard = the source; the heal lands on
    this answer), then pick any opponent Pokémon (ctx DAMAGE_COUNTER) to take them."""
    from .options import _targets, numbers
    seat = fr.seat
    opp = 1 - seat
    if "src" not in fr.vars:
        if "answer" not in fr.vars:
            opts = [opt_card(area, idx, seat) for area, idx, p in _targets(gs, seat)
                    if p.hp < p.max_hp]
            pose(gs, seat, type=SelectType.CARD,
                 context=SelectContext.REMOVE_DAMAGE_COUNTER,
                 options=opts, min_count=1, max_count=1, effect_card=fr.source)
            return False
        o = fr.vars.pop("answered_options")[0]
        fr.vars.pop("answer")
        from .turn import _target_of
        fr.vars["src"] = _target_of(gs, seat, o["area"], o["index"]).top
    src = None
    for p in gs.in_play(seat):
        if p.top == fr.vars["src"]:
            src = p
            break
    if "count" not in fr.vars:
        n = None
        n_max = min(args.get("max", 3), (src.max_hp - src.hp) // 10)
        if "answer" not in fr.vars:
            if n_max <= 1:                        # a FORCED count is never posed AND does
                n = n_max                         # not bump tac (pinned ml_dx_2000
            else:                                 # f161-f162)
                opts = [{"type": int(OptionType.NUMBER), "number": k}
                        for k in range(1, n_max + 1)]
                pose(gs, seat, type=SelectType.COUNT,
                     context=SelectContext.REMOVE_DAMAGE_COUNTER_COUNT,
                     options=opts, min_count=1, max_count=1,
                     context_card=src.top, effect_card=fr.source)
                return False
        if n is None:
            n = fr.vars.pop("answered_options")[0]["number"]
            fr.vars.pop("answer")
        fr.vars["count"] = n
        src.hp += n * 10                          # heal on the count answer (f123 log)
        gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": seat,
                 "cardId": gs.card_id(src.top), "serial": src.top,
                 "value": n * 10, "putDamageCounter": False})
    if "answer" not in fr.vars:
        opts = [opt_card(area, idx, opp) for area, idx, _p in _targets(gs, opp)]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.DAMAGE_COUNTER,
             options=opts, min_count=1, max_count=1, effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    n = fr.vars.pop("count")
    fr.vars.pop("src")
    ob = gs.players[opp]
    dest = ob.active if o["area"] == int(AreaType.ACTIVE) else ob.bench[o["index"]]
    dest.hp = max(0, dest.hp - n * 10)
    gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": opp,
             "cardId": gs.card_id(dest.top), "serial": dest.top,
             "value": -n * 10, "putDamageCounter": True})
    return True


def op_activate_ask(gs, fr, args) -> bool:
    """An optional triggered ability: YES_NO (ctx ACTIVATE, contextCard = the Pokémon,
    pinned ml_dx_2001 f29); YES splices the ability program into this frame."""
    from .options import yes_no
    if "answer" not in fr.vars:
        pose(gs, fr.seat, type=SelectType.YES_NO, context=SelectContext.ACTIVATE,
             options=yes_no(), context_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    if o["type"] == int(OptionType.YES):
        fr.program = fr.program[:fr.pc + 1] + list(args["program"])
    return True


def op_look_top_take_rest_bottom(gs, fr, args) -> bool:
    """Drakloak's Recon Directive class: top n to LOOKING, take `take` to hand (min=take,
    unfiltered), the rest to the BOTTOM of the deck in looking order, no shuffle
    (pinned ml_dx_2000 f26-f28)."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        n = min(args.get("n", 2), len(b.deck))
        gs.looking = []
        gs.looking_owner = seat
        for _ in range(n):
            s = b.deck.pop()
            gs.looking.append(s)
            gs.move_card(s, AreaType.DECK, AreaType.LOOKING, seat=seat,
                         visible_to_owner=True, visible_to_opponent=False)
        take = min(args.get("take", 1), len(gs.looking))
        opts = [opt_card(AreaType.LOOKING, k, seat) for k in range(len(gs.looking))]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_HAND,
             options=opts, min_count=take, max_count=take, effect_card=fr.source)
        return False
    picked = [gs.looking[o["index"]] for o in fr.vars.pop("answered_options")]
    fr.vars.pop("answer")
    for s in picked:                               # pick to hand first (no reveal)
        gs.looking.remove(s)
        b.hand.append(s)
        gs.move_card(s, AreaType.LOOKING, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=False)
    for s in list(gs.looking):                     # rest to deck BOTTOM, looking order
        gs.looking.remove(s)
        b.deck.insert(0, s)
        gs.move_card(s, AreaType.LOOKING, AREA_DECK_BOTTOM, seat=seat,
                     visible_to_owner=True, visible_to_opponent=False)
    gs.looking = None
    gs.looking_owner = -1
    return True


def op_draw_then_shuffle_self_in(gs, fr, args) -> bool:
    """Dudunsparce's Run Away Draw: draw n; if any were drawn, shuffle this Pokémon and
    all attached cards into the deck (stack top-first, lower cards from PRE_EVOLUTION —
    pinned ml_dx_2001 f65 — energies LIFO, pinned f174). If it left the ACTIVE spot, the
    owner promotes immediately (ctx TO_ACTIVE, effect=None; pinned v2_dx_mirror_5200
    f101-f102) and the turn continues."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" in fr.vars:                        # the promotion answer
        o = fr.vars.pop("answered_options")[0]
        fr.vars.pop("answer")
        p = b.bench.pop(o["index"])
        b.active = p
        gs.move_card(p.top, AreaType.BENCH, AreaType.ACTIVE, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
        return True
    drew = 0
    for _ in range(args.get("n", 3)):
        if gs.draw(seat) is not None:
            drew += 1
    if not drew:
        return True
    me = None
    for p in gs.in_play(seat):
        if p.top == fr.source:
            me = p
            break
    if me is None:                                 # already left play somehow
        return True
    was_active = me is b.active
    from_area = AreaType.ACTIVE if was_active else AreaType.BENCH
    if was_active:
        b.active = None
    else:
        b.bench.remove(me)
    for k, s in enumerate(reversed(me.stack)):     # top from its zone, lower stack cards
        area = from_area if k == 0 else AreaType.PRE_EVOLUTION   # (pinned 2001 f65)
        b.deck.append(s)
        gs.move_card(s, area, AreaType.DECK, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    for s in list(reversed(me.energy)):            # LIFO (pinned ml_dx_2001 f174)
        b.deck.append(s)
        gs.move_card(s, AreaType.ENERGY, AreaType.DECK, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    for s in me.tools:
        b.deck.append(s)
        gs.move_card(s, AreaType.TOOL, AreaType.DECK, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    _shuffle(gs, seat)
    if was_active and b.bench:
        opts = [opt_card(AreaType.BENCH, i, seat) for i in range(len(b.bench))]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_ACTIVE,
             options=opts, min_count=1, max_count=1)
        return False
    return True


def op_turn_damage_bonus(gs, fr, args) -> bool:
    """Premium Power Pro / Black Belt's Training: a silent this-turn damage marker
    (pinned ml_dx_2000 f14: the play logs nothing but PLAY); damage.py applies it."""
    mod = {"bonus": args["bonus"]}
    if "attackerEnergyType" in args:
        mod["attackerEnergyType"] = args["attackerEnergyType"]
    if args.get("defenderExOnly"):
        mod["defenderExOnly"] = True
    gs.turn_markers.setdefault("damage_bonus", []).append(mod)
    return True


def op_deck_take_sequence_and_shuffle(gs, fr, args) -> bool:
    """Hilda class: a SEQUENCE of deck picks (each its own TO_HAND select over a fresh
    deck listing, each picked card moving to hand immediately), ONE shuffle at the end
    (pinned ms_mirror_1000 f22-f24)."""
    seat = fr.seat
    b = gs.players[seat]
    picks = args["picks"]
    stage = fr.vars.get("stage", 0)
    if "answer" in fr.vars:
        for s in [b.deck[o["index"]] for o in fr.vars.pop("answered_options")]:
            b.deck.remove(s)
            b.hand.append(s)
            gs.move_card(s, AreaType.DECK, AreaType.HAND, seat=seat,
                         visible_to_owner=True, visible_to_opponent=True)  # "reveal"
        fr.vars.pop("answer")
        stage = fr.vars["stage"] = stage + 1
    while stage < len(picks):
        p = picks[stage]
        opts = _zone_options(gs, seat, b.deck, AreaType.DECK, p.get("filter", {}))
        if not opts and p.get("min", 0) == 0:      # empty optional stage: never posed
            gs.turn_action_count += 1              # (skipped ask still bumps tac)
            stage = fr.vars["stage"] = stage + 1
            continue
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_HAND, options=opts,
             min_count=p.get("min", 0), max_count=min(p.get("max", 1), len(opts)),
             deck_listing=list(b.deck), effect_card=fr.source)
        return False
    fr.vars.pop("stage", None)
    _shuffle(gs, seat)
    return True


def op_deck_distinct_basic_energy_take_attach(gs, fr, args) -> bool:
    """Crispin: TWO sequential max-1 deck picks (native never poses max 2 — pinned
    v2_ml_dx_5501 f14 with 6 candidates), the first to HAND, the second restricted to a
    DIFFERENT energy type and ATTACHED via a target select. A whiffed first pick ends
    the effect (+1 tac, pinned ml_dx_2000 f125-f126); a skipped second pick still bumps
    tac (f132-f133 +2). The attach stages are shape-guesses until a trace reaches them."""
    seat = fr.seat
    b = gs.players[seat]
    stage = fr.vars.get("cstage", 0)
    if stage == 0:
        if "answer" not in fr.vars:
            opts = _zone_options(gs, seat, b.deck, AreaType.DECK,
                                 {"cardType": [int(CardType.BASIC_ENERGY)]})
            if not opts:                           # empty optional search: never posed
                gs.turn_action_count += 1
                _shuffle(gs, seat)
                return True
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_HAND,
                 options=opts, min_count=0, max_count=1,
                 deck_listing=list(b.deck), effect_card=fr.source)
            return False
        picked = [b.deck[o["index"]] for o in fr.vars.pop("answered_options")]
        fr.vars.pop("answer")
        if not picked:                             # whiff: no second stage at all
            _shuffle(gs, seat)
            return True
        s = picked[0]
        b.deck.remove(s)
        b.hand.append(s)
        gs.move_card(s, AreaType.DECK, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
        fr.vars["first_type"] = int(gs.stat(s).energyType)
        stage = fr.vars["cstage"] = 1
    if stage == 1:
        if "answer" not in fr.vars:
            flt = {"cardType": [int(CardType.BASIC_ENERGY)]}
            opts = [o for o in _zone_options(gs, seat, b.deck, AreaType.DECK, flt)
                    if int(gs.stat(b.deck[o["index"]]).energyType)
                    != fr.vars["first_type"]]
            if not opts:                           # skipped ask still bumps tac
                gs.turn_action_count += 1
                _shuffle(gs, seat)
                return True
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_TO,
                 options=opts, min_count=0, max_count=1,
                 deck_listing=list(b.deck), effect_card=fr.source)
            return False
        picked = [b.deck[o["index"]] for o in fr.vars.pop("answered_options")]
        fr.vars.pop("answer")
        if not picked:
            _shuffle(gs, seat)
            return True
        fr.vars["attach_energy"] = picked[0]
        stage = fr.vars["cstage"] = 2
    energy = fr.vars["attach_energy"]
    if "answer" not in fr.vars:
        from .options import _targets
        opts = [opt_card(area, idx, seat) for area, idx, _p in _targets(gs, seat)]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_FROM,
             options=opts, min_count=1, max_count=1, deck_listing=list(b.deck),
             context_card=energy, effect_card=fr.source)   # listing persists (f16 pin)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    from .turn import _target_of
    target = _target_of(gs, seat, o["area"], o["index"])
    b.deck.remove(energy)
    target.energy.append(energy)
    gs.note_attach(energy)
    gs.emit({"type": int(LogType.ATTACH), "playerIndex": seat,
             "cardId": gs.card_id(energy), "serial": energy,
             "cardIdTarget": gs.card_id(target.top), "serialTarget": target.top})
    _shuffle(gs, seat)
    return True


def op_heal_mega_bounce_energy(gs, fr, args) -> bool:
    """Wally's Compassion: pick one of your Mega Evolution ex (ctx HEAL, min 1); heal all
    its damage (HP_CHANGE +value log); if any healed, ALL its attached energy returns to
    hand in attach order (pinned ml_dx_2000 f180-f181)."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        from .options import _targets
        opts = [opt_card(area, idx, seat) for area, idx, p in _targets(gs, seat)
                if gs.stat(p.top).megaEx and p.hp < p.max_hp]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.HEAL,
             options=opts, min_count=1, max_count=1, effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    from .turn import _target_of
    target = _target_of(gs, seat, o["area"], o["index"])
    healed = target.max_hp - target.hp
    if healed > 0:
        target.hp = target.max_hp
        gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": seat,
                 "cardId": gs.card_id(target.top), "serial": target.top,
                 "value": healed, "putDamageCounter": False})
        for s in list(target.energy):
            target.energy.remove(s)
            b.hand.append(s)
            gs.move_card(s, AreaType.ENERGY, AreaType.HAND, seat=seat,
                         visible_to_owner=True, visible_to_opponent=True)
    return True


def op_look_top_may_take_then_shuffle(gs, fr, args) -> bool:
    """Pokégear class: move the top n deck cards to LOOKING (pop order — top of deck
    first, pinned ms_mirror_1000 f9→f10), may take up to `max` filter-matches to hand,
    the rest return to deck in looking order, then shuffle (pinned f11)."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        n = min(args.get("n", 7), len(b.deck))
        gs.looking = []
        gs.looking_owner = seat
        for _ in range(n):
            s = b.deck.pop()                       # top of deck = list end (pinned)
            gs.looking.append(s)
            gs.move_card(s, AreaType.DECK, AreaType.LOOKING, seat=seat,
                         visible_to_owner=True, visible_to_opponent=False)
        opts = _zone_options(gs, seat, gs.looking, AreaType.LOOKING,
                             args.get("filter", {}))
        if not opts:                     # no match among the looked cards: the select is
            gs.turn_action_count += 1    # never posed; everything returns and shuffles
            for s in list(gs.looking):   # (pinned v2_ms_mirror_5001 f74)
                gs.looking.remove(s)
                b.deck.append(s)
                gs.move_card(s, AreaType.LOOKING, AreaType.DECK, seat=seat,
                             visible_to_owner=True, visible_to_opponent=False)
            gs.looking = None
            gs.looking_owner = -1
            _shuffle(gs, seat)
            return True
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_HAND,
             options=opts, min_count=args.get("min", 0),
             max_count=min(args.get("max", 1), len(opts)), effect_card=fr.source)
        return False
    picked = [gs.looking[o["index"]] for o in fr.vars.pop("answered_options")]
    fr.vars.pop("answer")
    for s in picked:                               # pick(s) to hand FIRST (pinned f11)
        gs.looking.remove(s)
        b.hand.append(s)
        gs.move_card(s, AreaType.LOOKING, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)  # "reveal"
    for s in list(gs.looking):                     # rest back in looking order (pinned)
        gs.looking.remove(s)
        b.deck.append(s)
        gs.move_card(s, AreaType.LOOKING, AreaType.DECK, seat=seat,
                     visible_to_owner=True, visible_to_opponent=False)
    gs.looking = None
    gs.looking_owner = -1
    _shuffle(gs, seat)
    return True


def op_deck_evolve_in_play_and_shuffle(gs, fr, args) -> bool:
    """Salvatore class: two selects (pinned ms_mirror_1001 f14-f16) — pick a no-ability
    evolution of an in-play Pokémon from the revealed deck (ctx EVOLVES_TO, may whiff),
    then the in-play target (ctx EVOLVES_FROM, contextCard = the pick, targets INCLUDE
    Pokémon that entered play this turn); evolve (EVOLVE log only, no move log), shuffle."""
    seat = fr.seat
    b = gs.players[seat]
    if "evo" not in fr.vars:
        if "answer" not in fr.vars:
            names = {gs.stat(p.top).name for p in gs.in_play(seat)}
            opts = [opt_card(AreaType.DECK, i, seat) for i, s in enumerate(b.deck)
                    if gs.stat(s).cardType == CardType.POKEMON
                    and not gs.stat(s).skills
                    and gs.stat(s).evolvesFrom in names]
            if not opts:                           # empty optional search: never posed
                gs.turn_action_count += 1          # (skipped ask still bumps tac)
                _shuffle(gs, seat)
                return True
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.EVOLVES_TO,
                 options=opts, min_count=0, max_count=min(1, len(opts)),
                 deck_listing=list(b.deck), effect_card=fr.source)
            return False
        picked = [b.deck[o["index"]] for o in fr.vars.pop("answered_options")]
        fr.vars.pop("answer")
        if not picked:                             # whiff: the reveal still shuffles
            _shuffle(gs, seat)
            return True
        fr.vars["evo"] = picked[0]                 # fall through: pose the target pick
    evo = fr.vars["evo"]
    if "answer" not in fr.vars:
        from .options import _targets
        target_name = gs.stat(evo).evolvesFrom
        opts = [opt_card(area, idx, seat) for area, idx, p in _targets(gs, seat)
                if gs.stat(p.top).name == target_name]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.EVOLVES_FROM,
             options=opts, min_count=1, max_count=1,
             context_card=evo, effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    fr.vars.pop("evo")
    from .turn import _apply_evolution, _target_of
    target = _target_of(gs, seat, o["area"], o["index"])
    b.deck.remove(evo)
    _apply_evolution(gs, seat, evo, target)
    _shuffle(gs, seat)
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
    "xBothShuffleCoinDraw": op_both_shuffle_coin_draw,
    "xOwnShuffleHandDraw": op_own_hand_to_deck_shuffle_draw,
    "xLookTopMayTakeThenShuffle": op_look_top_may_take_then_shuffle,
    "xDeckEvolveInPlayAndShuffle": op_deck_evolve_in_play_and_shuffle,
    "xTurnDamageBonus": op_turn_damage_bonus,
    "xDeckTakeSequenceAndShuffle": op_deck_take_sequence_and_shuffle,
    "xDeckDistinctBasicEnergyTakeAttach": op_deck_distinct_basic_energy_take_attach,
    "xHealMegaBounceEnergy": op_heal_mega_bounce_energy,
    "xActivateAsk": op_activate_ask,
    "xLookTopTakeRestBottom": op_look_top_take_rest_bottom,
    "xDrawThenShuffleSelfIn": op_draw_then_shuffle_self_in,
    "xOrderTriggers": op_order_triggers,
    "xBenchCounterDamage": op_bench_counter_damage,
    "xChooseBenchDamage": op_choose_bench_damage,
    "xMoveDamageCounters": op_move_damage_counters,
    "xDiscardEnergyAttachBench": op_discard_energy_attach_bench,
    "xInflictConditionActive": op_inflict_condition_active,
    "xDiscardEnergyAttachOneTarget": op_discard_energy_attach_one_target,
    "xChooseAnyDamage": op_choose_any_damage,
}
