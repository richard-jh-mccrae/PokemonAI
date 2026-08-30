"""The effect-DSL interpreter: ChainDef programs over a small op vocabulary (ADR-0059 M2).

A card's behavior is DATA: a list of ops executed on a resumable frame stack, one executor per op.
An op needing a decision poses a select and the frame resumes on the answer. Op names follow the
recovered native `Chain` vocabulary; composite convenience ops are prefixed `x`. Frames are plain
data, so `clone()` stays a deep copy.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .options import opt_card, pose, yes_no
from .schema import (AreaType, CardType, LogType, OptionType, SelectContext, SelectType)
from .state import EffectFrame, GameState

_DEFS = Path(__file__).resolve().parent / "defs"


@lru_cache(maxsize=1)
def load_chain_defs() -> dict:
    """Overrides win whole-entry. A pool card or attack with no entry and no ``deferred`` is a LOAD error."""
    defs: dict = {}
    gen_path = _DEFS / "generated_chains.json"
    if gen_path.exists():
        defs.update(json.loads(gen_path.read_text(encoding="utf-8")))
    ov_path = _DEFS / "chain_overrides.json"
    if ov_path.exists():
        defs.update(json.loads(ov_path.read_text(encoding="utf-8")))
    defs = {k: v for k, v in defs.items() if not k.startswith("_")}

    if gen_path.exists():
        from .cards import CardDB
        db = CardDB.load()
        missing = [str(cid) for cid in db.cards if str(cid) not in defs]
        missing += [f"attack:{aid}" for aid in db.attacks
                    if f"attack:{aid}" not in defs]
        if missing:
            raise RuntimeError(
                f"chain defs incomplete: {len(missing)} pool chains have neither a def "
                f"nor an explicit deferral (first: {missing[:5]}) — regenerate with "
                f"tools/parity/seed_chains.py")
    return defs


def is_deferred(cdef: dict | None) -> bool:
    return cdef is not None and "deferred" in cdef


def def_for(card_id: int) -> dict | None:
    return load_chain_defs().get(str(card_id))


class UnsupportedCard(NotImplementedError):
    """A card without a ChainDef was exercised — fail loud, never guess."""


def stadium_def(gs: GameState) -> dict:
    if not gs.stadium:
        return {}
    return (def_for(gs.card_id(gs.stadium[0])) or {}).get("stadium") or {}


def stadium_hp_delta(gs: GameState, p) -> int:
    """FLOATING: computed live so it follows the holder across evolution. `board_delta` mirrors this."""
    delta = 0
    sdef = stadium_def(gs)
    hp_delta = sdef.get("hpDelta")
    if hp_delta and _card_matches(gs, p.top, hp_delta.get("filter", {})):
        delta += hp_delta["amount"]
    for s in p.energy:
        edef = def_for(gs.card_id(s)) or {}
        hb = edef.get("hpBonus", 0)
        if hb and _card_matches(gs, p.top, edef.get("hpBonusFilter", {})):
            delta += hb
    return delta


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
    if "name" in flt and stat.name != flt["name"]:
        return False
    if "cardIdIn" in flt and gs.card_id(serial) not in flt["cardIdIn"]:
        return False  # explicit id lists (Future/Ancient family) — no native table carries the Category
    if "resistanceType" in flt and (stat.cardType != CardType.POKEMON
                                    or stat.resistance not in flt["resistanceType"]):
        return False
    if flt.get("megaEx") and not stat.megaEx:
        return False
    if flt.get("ex") and not (stat.ex or stat.megaEx):
        return False   # "Pokémon {ex}" — megaEx counts as {ex} (Fighting-Roar pin)
    if flt.get("stage1") and not stat.stage1:
        return False
    if flt.get("stage2") and not stat.stage2:
        return False
    if flt.get("tera") and not stat.tera:
        return False
    if "nameContains" in flt and flt["nameContains"] not in stat.name:
        return False
    if "nameFamily" in flt:
        # The possessive apostrophe is INCONSISTENT in the card table (U+2019 vs ASCII 0x27), so match on
        # an apostrophe-normalized substring DERIVED from the table.
        fam = flt["nameFamily"].replace("’", "'")
        if fam not in stat.name.replace("’", "'"):
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
    """EVERY condition must hold. `pokemon` is the in-play holder for ability conditions."""
    b = gs.players[seat]
    for c in conds:
        op = c["op"]
        if op == "benchSpace":
            from .options import effective_bench_max
            if len(b.bench) >= effective_bench_max(gs, seat):
                return False
        elif op == "benchExists":
            if not b.bench:
                return False
        elif op == "handOthers":
            if len(b.hand) - 1 < c["n"]:
                return False
        elif op == "deckNotEmpty":
            if not b.deck:
                return False
        elif op == "oppBenchExists":
            if not gs.players[1 - seat].bench:
                return False
        elif op == "toolInPlay":
            if not any(p.tools for s2 in (seat, 1 - seat) for p in gs.in_play(s2)):
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
        elif op == "handBelow":  # draw-until riders: targetless once the hand already holds n
            if len(b.hand) >= c["n"]:
                return False
        elif op == "ownBasicEnergyExists":
            if not any(gs.stat(s).cardType == CardType.BASIC_ENERGY
                       for p in gs.in_play(seat) for s in p.energy):
                return False
        elif op == "oppEnergyHas":
            if not any(_card_matches(gs, s, c.get("filter", {}))
                       for p in gs.in_play(1 - seat) for s in p.energy):
                return False
        elif op == "activeDamaged":
            if b.active is None or b.active.hp >= b.active.max_hp:
                return False
        elif op == "activeIs":
            if b.active is None or not _card_matches(gs, b.active.top,
                                                     c.get("filter", {})):
                return False
        elif op == "activeEnergyMin":
            from .options import provided_energy
            if b.active is None or len(provided_energy(gs, b.active)) < c["n"]:
                return False
        elif op == "megaExDamagedInPlay":  # the engine peeks for DAMAGE: an undamaged mega is not offered
            if not any(gs.stat(p.top).megaEx and p.hp < p.max_hp
                       for p in gs.in_play(seat)):
                return False
        elif op == "prizesMoreThanOpp":       # Rosa's: MORE prizes remaining = behind
            if len(b.prize) <= len(gs.players[1 - seat].prize):
                return False
        elif op == "koLastTurn":
            if gs.ko_turn[seat] != gs.turn - 1:
                return False
        elif op == "rareCandyPairExists":  # menu-gated: never offered without a legal (basic, hand stage-2) pair
            if not _rare_candy_pairs(gs, seat):
                return False
        elif op == "anyHandAbove":  # hidden unless SOMEONE holds more than n; own hand counts WITHOUT this card
            n = c.get("n", 5)
            if not (len(b.hand) - 1 > n
                    or len(gs.players[1 - seat].hand) > n):
                return False
        elif op == "handHas":
            if not any(_card_matches(gs, s, c["filter"]) for s in b.hand):
                return False
        elif op == "oppHandAbove":  # menu-gated until the opponent holds MORE than n
            if len(gs.players[1 - seat].hand) <= c["n"]:
                return False
        elif op == "inPlayNamed":
            if not any(gs.stat(p.top).name == c["name"] for p in gs.in_play(seat)):
                return False
        elif op == "inPlayHas":
            if not any(_card_matches(gs, p.top, c["filter"])
                       for p in gs.in_play(seat)):
                return False
        elif op == "benchHas":
            if not any(_card_matches(gs, p.top, c["filter"]) for p in b.bench):
                return False
        elif op == "selfIsActive":
            if pokemon is None or pokemon is not b.active:
                return False
        elif op == "selfHasEnergyType":
            if pokemon is None or not any(
                    int(gs.stat(s).energyType) == c["energyType"]
                    and (not c.get("basic")
                         or gs.stat(s).cardType == CardType.BASIC_ENERGY)
                    for s in pokemon.energy):
                return False
        else:
            raise UnsupportedCard(f"unknown legality op {op!r}")
    return True


# ---------------------------------------------------------------------------- interpreter

def start_program(gs: GameState, seat: int, source_serial: int, ops: list,
                  *, kind: str = "play") -> None:
    if gs.execution_guard is not None:
        gs.execution_guard(str(gs.card_id(source_serial)))
    gs.frames.append(EffectFrame(program=list(ops), pc=0, vars={},
                                 seat=seat, source=source_serial, kind=kind))
    run_frames(gs)


def run_frames(gs: GameState) -> None:
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
    """The trainer discards AT RESOLUTION, not on play, and SILENTLY — no MOVE_CARD log."""
    if fr.kind == "play":
        gs.players[fr.seat].discard.append(fr.source)
    if gs.frames or gs.pending is not None or gs.result != -1:
        return
    if fr.kind == "attack":
        from .turn import _after_attack
        _after_attack(gs, fr.seat)
    elif fr.kind == "attack_pre":
        from .turn import _attack_damage_apply
        _attack_damage_apply(gs, fr.seat, fr.vars["attack_id"], fr.vars)
    elif fr.kind == "eot_tool":
        from .turn import _post_end_turn
        _post_end_turn(gs, fr.seat)
    elif fr.kind in ("play", "ability"):
        from .turn import _sweep_kos, flush_triggers
        # Item/Ability damage KOs sweep at resolution, exactly like attack damage — without this
        # a 0-HP body stayed in play (and rendered) until the end-of-turn checkup.
        if _sweep_kos(gs, credited=fr.seat, then=("main", fr.seat)):
            return
        flush_triggers(gs, fr.seat)


def resume(gs: GameState, indices: list[int]) -> None:
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
    """A zero-option OPTIONAL search is never posed — the engine auto-resolves it as a no-pick."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        opts = _zone_options(gs, seat, b.deck, AreaType.DECK, args.get("filter", {}))
        if not opts:  # a zero-option search is an UNPOSABLE ask: the skipped ask still bumps tac
            gs.turn_action_count += 1
            fr.vars["picked"] = []
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
    seat = fr.seat
    b = gs.players[seat]
    if "maxVar" in args and "answer" not in fr.vars:
        # Use-time caps ("up to the number of your Benched Pokémon" / "of heads"). A zero cap skips the
        # ask like a zero-option search — unpinned edge.
        cap = (len(b.bench) if args["maxVar"] == "atk_bench"
               else fr.vars.get("heads_count", 0))
        args = dict(args, max=cap)
        if args["max"] <= 0:
            gs.turn_action_count += 1
            _shuffle(gs, seat)
            return True
        fr.vars["_resolved_max"] = args["max"]
    elif "_resolved_max" in fr.vars:
        args = dict(args, max=fr.vars["_resolved_max"])
    if not _select_from_deck(gs, fr, args, SelectContext.TO_HAND):
        return False
    fr.vars.pop("_resolved_max", None)
    # Un-revealed prints hide the identity from the opponent (MOVE_CARD_REVERSE); reveal prints stay
    # visible both ways.
    vis_opp = args.get("reveal", True)
    for s in fr.vars.pop("picked"):
        b.deck.remove(s)
        b.hand.append(s)
        gs.move_card(s, AreaType.DECK, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=vis_opp)
    _shuffle(gs, seat)
    return True


def op_deck_to_bench_and_shuffle(gs, fr, args) -> bool:
    seat = fr.seat
    b = gs.players[seat]
    from .options import effective_bench_max
    room = effective_bench_max(gs, seat) - len(b.bench)
    args = dict(args, max=min(args.get("max", 1), room))  # maxCount clamps by bench room
    if not _select_from_deck(gs, fr, args, SelectContext.TO_BENCH):
        return False
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
    seat = fr.seat
    b = gs.players[seat]
    if not b.bench:
        return True
    flt = args.get("filter")
    if "answer" not in fr.vars:
        opts = [opt_card(AreaType.BENCH, i, seat) for i, p in enumerate(b.bench)
                if flt is None or _card_matches(gs, p.top, flt)]
        if not opts:
            return True
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.SWITCH,
             options=opts, effect_card=fr.source)
        return False
    idx = fr.vars.pop("answered_options")[0]["index"]
    fr.vars.pop("answer")
    from .turn import _do_switch
    _do_switch(gs, seat, idx, retreat=False)
    return True


def op_effect_switch_enemy(gs, fr, args) -> bool:
    """The select is posed to the ATTACKER; ``damageNew`` then hits the new Active FLAT, no W/R."""
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
    if args.get("damageNew") and ob.active is not None:
        target = ob.active
        target.hp = max(0, target.hp - args["damageNew"])
        gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": opp,
                 "cardId": gs.card_id(target.top), "serial": target.top,
                 "value": -args["damageNew"], "putDamageCounter": False})
    return True


def _flip(gs: GameState, fr: EffectFrame) -> bool | None:
    """None when a manual-coin select was posed and the frame will resume with the answer."""
    if not gs.manual_coin:
        return gs.coin_flip(fr.seat)
    if "answer" not in fr.vars:
        pose(gs, fr.seat, type=SelectType.YES_NO, context=SelectContext.COIN_HEAD,
             options=yes_no(), effect_card=fr.source)
        return None
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    head = o["type"] == int(OptionType.YES)
    gs.emit({"type": int(LogType.COIN), "playerIndex": fr.seat, "head": bool(head)})
    return head


def op_coin(gs, fr, args) -> bool:
    head = _flip(gs, fr)
    if head is None:
        return False
    fr.vars["heads"] = head
    return True


def op_if_heads(gs, fr, args) -> bool:
    if not fr.vars.get("heads"):
        fr.pc += args.get("skip", 1)
    return True


def op_trash_energy_enemy(gs, fr, args) -> bool:
    """Options list the opponent's energies in GLOBAL ATTACH ORDER, oldest first."""
    seat = fr.seat
    opp = 1 - seat
    ob = gs.players[opp]
    while True:
        if args.get("perHeads"):
            # One discard per recorded heads; zero-heads / zero-energy runs are SILENT, and each pick re-poses
            # over the remaining energies.
            left = fr.vars.setdefault("discards_left",
                                      fr.vars.get("heads_count", 0))
            if left <= 0:
                fr.vars.pop("discards_left", None)
                return True
        plist = ([(int(AreaType.ACTIVE), 0, ob.active)] if ob.active else []) + \
            ([] if args.get("activeOnly") else
             [(int(AreaType.BENCH), i, p) for i, p in enumerate(ob.bench)])
        from .options import provided_units_of
        flt = args.get("filter")
        entries = []                              # (attach tick, option dict)
        for area, idx, p in plist:
            for k, s in enumerate(p.energy):
                if flt is not None and not _card_matches(gs, s, flt):
                    continue
                entries.append((gs.attach_seq.get(s, 0),
                                {"type": int(OptionType.ENERGY), "area": area,
                                 "index": idx, "playerIndex": opp, "energyIndex": k,
                                 "count": provided_units_of(gs, p, s)}))
        entries.sort(key=lambda e: e[0])
        options = [o for _tick, o in entries]
        if not options:
            fr.vars.pop("discards_left", None)
            return True
        if "answer" not in fr.vars:
            pose(gs, seat, type=SelectType.ENERGY,
                 context=SelectContext.DISCARD_ENERGY,
                 options=options, effect_card=fr.source,
                 remain_energy_cost=1)
            return False
        o = fr.vars.pop("answered_options")[0]
        fr.vars.pop("answer")
        p = ob.active if o["area"] == int(AreaType.ACTIVE) else ob.bench[o["index"]]
        serial = p.energy[o["energyIndex"]]
        p.energy.remove(serial)
        ob.discard.append(serial)
        gs.move_card(serial, AreaType.ENERGY, AreaType.DISCARD, seat=opp,
                     visible_to_owner=True, visible_to_opponent=True)
        if not args.get("perHeads"):
            return True
        fr.vars["discards_left"] -= 1


def op_trash_to_hand(gs, fr, args) -> bool:
    seat = fr.seat
    b = gs.players[seat]
    if args.get("maxVar") == "heads_count":
        cap = fr.vars.get("heads_count", 0)
        if cap <= 0 and "answer" not in fr.vars:
            return True
        args = dict(args, max=cap)
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
    """Actor first, then the opponent, BEFORE any draws; the opponent's exits drain the replay feed."""
    for seat in (actor, 1 - actor):
        b = gs.players[seat]
        if seat != actor:
            gs.rng.hand_pick_expect(seat, list(b.hand))
        for s in list(b.hand):
            b.hand.remove(s)
            b.deck.append(s)
            gs.move_card(s, AreaType.HAND, AreaType.DECK, seat=seat,
                         visible_to_owner=True, visible_to_opponent=False)
        _shuffle(gs, seat)


def op_hand_to_deck_shuffle_draw(gs, fr, args) -> bool:
    """Both shuffle in (actor first) and only THEN do the draws happen."""
    _both_shuffle_hands(gs, fr.seat)
    for seat, count in ((fr.seat, args.get("n", 4)),
                        (1 - fr.seat, args.get("nOpp", args.get("n", 4)))):
        for _ in range(count):
            gs.draw(seat)
    return True


def op_both_shuffle_coin_draw(gs, fr, args) -> bool:
    """The shuffle-in runs ONCE even when a manual-coin select suspends the frame at the flip."""
    if "shuffled_in" not in fr.vars:
        _both_shuffle_hands(gs, fr.seat)
        fr.vars["shuffled_in"] = True
    heads = _flip(gs, fr)
    if heads is None:
        return False
    fr.vars.pop("shuffled_in")
    n_actor, n_opp = args["heads"] if heads else args["tails"]
    for seat, count in ((fr.seat, n_actor), (1 - fr.seat, n_opp)):
        for _ in range(count):
            gs.draw(seat)
    return True


def op_own_hand_to_deck_shuffle_draw(gs, fr, args) -> bool:
    """Return moves run front-to-back in hand order — NOT the mulligan's LIFO."""
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


AREA_DECK_BOTTOM = 14  # wire value in MOVE logs for bottom-of-deck, beyond the AreaType snapshot


def op_order_triggers(gs, fr, args) -> bool:
    """Each trigger runs as its OWN frame, keeping its own source for contextCard rendering."""
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
        if gs.execution_guard is not None:
            gs.execution_guard(str(gs.card_id(t["source"])))
        gs.frames.append(EffectFrame(program=list(t["ops"]), pc=0, vars={},
                                     seat=fr.seat, source=t["source"], kind="ability"))
    return True


def op_bench_counter_damage(gs, fr, args) -> bool:
    for p in gs.in_play(fr.seat):
        if p.top == args["serial"]:
            p.hp = max(0, p.hp - args["damage"])
            gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": fr.seat,
                     "cardId": gs.card_id(p.top), "serial": p.top,
                     "value": -args["damage"], "putDamageCounter": True})
            break
    return True


def _bench_hit(gs, opp: int, target, dmg: int, *, ignore_effects: bool = False) -> None:
    """Flat: no W/R, but the shared DEFENDER-side mods still apply."""
    from .damage import apply_defender_mods
    attacker = gs.players[1 - opp].active
    if attacker is not None:
        dmg = apply_defender_mods(gs, attacker, target, dmg, is_active=False,
                                  ignore_effects=ignore_effects)
    elif gs.stat(target.top).tera:
        dmg = 0
    target.hp = max(0, target.hp - dmg)
    gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": opp,
             "cardId": gs.card_id(target.top), "serial": target.top,
             "value": -dmg, "putDamageCounter": False})


def op_choose_bench_damage(gs, fr, args) -> bool:
    """No W/R on the bench; count>1 poses ONE select at min=max=min(count, bench)."""
    seat = fr.seat
    opp = 1 - seat
    ob = gs.players[opp]
    if not ob.bench:
        return True
    if "answer" not in fr.vars:
        n = min(args.get("count", 1), len(ob.bench))
        opts = [opt_card(AreaType.BENCH, i, opp) for i in range(len(ob.bench))]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.DAMAGE,
             options=opts, min_count=n, max_count=n, effect_card=fr.source)
        return False
    picked = [ob.bench[o["index"]] for o in fr.vars.pop("answered_options")]
    fr.vars.pop("answer")
    for target in picked:
        _bench_hit(gs, opp, target, args["damage"])
    return True


def op_choose_any_damage(gs, fr, args) -> bool:
    """Flat on the bench, W/R-adjusted on the Active."""
    seat = fr.seat
    opp = 1 - seat
    ob = gs.players[opp]
    if "answer" not in fr.vars:
        from .options import _targets
        opts = [opt_card(area, idx, opp) for area, idx, _p in _targets(gs, opp)]
        if not opts:
            return True
        n = min(args.get("count", 1), len(opts))
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.DAMAGE,
             options=opts, min_count=n, max_count=n, effect_card=fr.source)
        return False
    answered = fr.vars.pop("answered_options")
    fr.vars.pop("answer")
    for o in answered:
        dmg = args["damage"]
        if o["area"] == int(AreaType.ACTIVE):
            from .damage import apply_weakness_resistance
            target = ob.active
            dmg = apply_weakness_resistance(gs, gs.players[seat].active, target, dmg)
            target.hp = max(0, target.hp - dmg)
            gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": opp,
                     "cardId": gs.card_id(target.top), "serial": target.top,
                     "value": -dmg, "putDamageCounter": False})
        else:
            _bench_hit(gs, opp, ob.bench[o["index"]], dmg)
    return True


# ------------------------------------------------------------------- M4 pool-fan-out ops
# Shapes marked "seeded" are trace-UNPINNED until a micro-trace verifies them.

def op_damage_self(gs, fr, args) -> bool:
    b = gs.players[fr.seat]
    me = b.active
    if me is None:
        return True
    dmg = args["damage"]
    me.hp = max(0, me.hp - dmg)
    gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": fr.seat,
             "cardId": gs.card_id(me.top), "serial": me.top,
             "value": -dmg, "putDamageCounter": False})
    return True


def op_damage_own_bench_each(gs, fr, args) -> bool:
    for p in list(gs.players[fr.seat].bench):
        _bench_hit(gs, fr.seat, p, args["damage"])
    return True


def op_heal_self(gs, fr, args) -> bool:
    """The HP_CHANGE logs even at full HP, with value 0."""
    me = gs.players[fr.seat].active
    if me is None:
        return True
    healed = min(args["amount"], me.max_hp - me.hp)
    me.hp += healed
    gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": fr.seat,
             "cardId": gs.card_id(me.top), "serial": me.top,
             "value": healed, "putDamageCounter": False})
    return True


def op_heal_each(gs, fr, args) -> bool:
    """Active first, then bench order; each HP_CHANGE logs even at 0."""
    for p in gs.in_play(fr.seat):
        healed = min(args["amount"], p.max_hp - p.hp)
        p.hp += healed
        gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": fr.seat,
                 "cardId": gs.card_id(p.top), "serial": p.top,
                 "value": healed, "putDamageCounter": False})
    return True


def op_heal_choose(gs, fr, args) -> bool:
    seat = fr.seat
    if "answer" not in fr.vars:
        from .options import _targets
        opts = [opt_card(area, idx, seat) for area, idx, p in _targets(gs, seat)
                if p.hp < p.max_hp]
        if not opts:
            return True
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.HEAL,
             options=opts, min_count=1, max_count=1, effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    from .turn import _target_of
    target = _target_of(gs, seat, o["area"], o["index"])
    cap = (target.max_hp - target.hp) if args.get("all") else args["amount"]
    healed = min(cap, target.max_hp - target.hp)
    if healed > 0:
        target.hp += healed
        gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": seat,
                 "cardId": gs.card_id(target.top), "serial": target.top,
                 "value": healed, "putDamageCounter": False})
    return True


def op_if_heads_count_below(gs, fr, args) -> bool:
    if fr.vars.get("heads_count", 0) < args["n"]:
        fr.pc += args.get("skip", 1)
    return True


def op_choose_condition_inflict(gs, fr, args) -> bool:
    """Options are all five Special Conditions in ENUM order."""
    if "answer" not in fr.vars:
        opts = [{"type": int(OptionType.SPECIAL_CONDITION), "specialConditionType": k}
                for k in range(5)]
        pose(gs, fr.seat, type=SelectType.SPECIAL_CONDITION,
             context=SelectContext.AFFECT_SPECIAL_CONDITION,
             options=opts, effect_card=fr.source)
        return False
    cond = fr.vars.pop("answered_options")[0]["specialConditionType"]
    fr.vars.pop("answer")
    _set_condition(gs, 1 - fr.seat, cond)
    return True


def op_discard_own_energy(gs, fr, args) -> bool:
    """ONE select per unit with remainEnergyCost counting down — the retreat-cascade shape."""
    seat = fr.seat
    me = gs.players[seat].active
    if me is None:
        return True
    from .options import provided_units_of
    if "left" not in fr.vars:
        fr.vars["left"] = args.get("n", 1)
    while fr.vars["left"] > 0 and me.energy:
        if "answer" not in fr.vars:
            opts = [{"type": int(OptionType.ENERGY), "area": int(AreaType.ACTIVE),
                     "index": 0, "playerIndex": seat, "energyIndex": k,
                     "count": provided_units_of(gs, me, s)}
                    for k, s in enumerate(me.energy)]
            pose(gs, seat, type=SelectType.ENERGY, context=SelectContext.DISCARD_ENERGY,
                 options=opts, effect_card=fr.source,
                 remain_energy_cost=fr.vars["left"])
            return False
        o = fr.vars.pop("answered_options")[0]
        fr.vars.pop("answer")
        serial = me.energy[o["energyIndex"]]
        units = provided_units_of(gs, me, serial)
        me.energy.remove(serial)
        gs.players[seat].discard.append(serial)
        gs.move_card(serial, AreaType.ENERGY, AreaType.DISCARD, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
        fr.vars["left"] -= units
    fr.vars.pop("left")
    return True


def op_discard_all_own_energy(gs, fr, args) -> bool:
    """No select; discards in ATTACH order (forward), unlike the KO sweep's LIFO."""
    seat = fr.seat
    me = gs.players[seat].active
    if me is None:
        return True
    for serial in list(me.energy):
        me.energy.remove(serial)
        gs.players[seat].discard.append(serial)
        gs.move_card(serial, AreaType.ENERGY, AreaType.DISCARD, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    return True


def op_self_no_weakness_next_turn(gs, fr, args) -> bool:
    """UNPINNED shape, authored from card text."""
    me = gs.players[fr.seat].active
    if me is not None:
        me.no_weakness_turn = gs.turn + 1
    return True


def op_counter_opp_active_scaled(gs, fr, args) -> bool:
    """One HP_CHANGE, emitted EVEN AT 0 counters — the computed-0 convention."""
    seat = fr.seat
    ob = gs.players[1 - seat]
    if ob.active is None:
        return True
    n = args.get("per", 2) * len(gs.players[seat].hand)
    ob.active.hp = max(0, ob.active.hp - n * 10)
    gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": 1 - seat,
             "cardId": gs.card_id(ob.active.top), "serial": ob.active.top,
             "value": -n * 10, "putDamageCounter": True})
    return True


def op_inflict_condition_self(gs, fr, args) -> bool:
    seat = fr.seat
    b = gs.players[seat]
    if b.active is None:
        return True
    _set_condition(gs, seat, args["condition"])
    return True


def _set_condition(gs: GameState, seat: int, cond: int) -> None:
    """Rotating conditions overwrite each other, markers stack. Re-applying an existing one is SILENT."""
    b = gs.players[seat]
    log_type = {0: LogType.POISONED, 1: LogType.BURNED, 2: LogType.ASLEEP,
                3: LogType.PARALYZED, 4: LogType.CONFUSED}[cond]
    flag = {0: "poisoned", 1: "burned", 2: "asleep", 3: "paralyzed", 4: "confused"}[cond]
    already = getattr(b, flag)
    if cond in (2, 3, 4):
        b.asleep = b.paralyzed = b.confused = False
    setattr(b, flag, True)
    if cond == 3:
        b.paralyzed_since_turn = gs.turn
    if already:
        return
    gs.emit({"type": int(log_type), "playerIndex": seat, "isRecover": False,
             "cardId": gs.card_id(b.active.top), "serial": b.active.top})


def op_opponent_switches(gs, fr, args) -> bool:
    """The select goes to the OPPONENT."""
    opp = 1 - fr.seat
    ob = gs.players[opp]
    if not ob.bench:
        return True
    if "answer" not in fr.vars:
        opts = [opt_card(AreaType.BENCH, i, opp) for i in range(len(ob.bench))]
        pose(gs, opp, type=SelectType.CARD, context=SelectContext.SWITCH,
             options=opts, effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    from .turn import _do_switch
    _do_switch(gs, opp, o["index"], retreat=False)
    return True


def op_mill(gs, fr, args) -> bool:
    """Top of deck = list END. Serials bind from the recorded reveal so a replay mills native's top-N."""
    seat = fr.seat if args.get("who", "self") == "self" else 1 - fr.seat
    b = gs.players[seat]
    if args.get("nVar") == "heads_count":
        args = dict(args, n=fr.vars.get("heads_count", 0))
    n = min(args.get("n", 1), len(b.deck))
    milled = gs.rng.mill_bind(seat, b.deck, b.prize, n)
    for serial in milled:
        b.deck.remove(serial)
        b.discard.append(serial)
        gs.move_card(serial, AreaType.DECK, AreaType.DISCARD, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    if args.get("record"):
        fr.vars[args["record"]] = list(milled)
    return True


def op_shuffle_discard_energy_to_deck(gs, fr, args) -> bool:
    """Runs AFTER the scale-count damage read the same discard, so count and moved set agree."""
    seat = fr.seat
    b = gs.players[seat]
    moved = [s for s in list(b.discard) if _card_matches(gs, s, args.get("filter", {}))]
    for s in moved:
        b.discard.remove(s)
        b.deck.append(s)
        gs.move_card(s, AreaType.DISCARD, AreaType.DECK, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    if moved:
        _shuffle(gs, seat)
    return True


def op_discard_hand_draw(gs, fr, args) -> bool:
    seat = fr.seat
    b = gs.players[seat]
    for serial in list(b.hand):
        b.hand.remove(serial)
        b.discard.append(serial)
        gs.move_card(serial, AreaType.HAND, AreaType.DISCARD, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    for _ in range(args.get("n", 0)):
        gs.draw(seat)
    return True


def op_opp_hand_discard_random(gs, fr, args) -> bool:
    """No select, no reveal, one PUBLIC move per pick. ``untilLeft`` no-ops at or below N."""
    victim = 1 - fr.seat
    vb = gs.players[victim]
    count = max(0, len(vb.hand) - args["untilLeft"]) if "untilLeft" in args \
        else args.get("n", 1)
    for _ in range(count):
        if not vb.hand:
            break
        serial = gs.rng.hand_pick(victim, vb.hand)
        vb.hand.remove(serial)
        vb.discard.append(serial)
        gs.move_card(serial, AreaType.HAND, AreaType.DISCARD, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    return True


def op_opp_hand_shuffle_in_random(gs, fr, args) -> bool:
    """The reveal makes the exit public BOTH ways; ONE shuffle after all the moves."""
    victim = 1 - fr.seat
    vb = gs.players[victim]
    count = fr.vars.get("heads_count", 0) if args.get("perHeads") else args.get("n", 1)
    moved = False
    for _ in range(count):
        if not vb.hand:
            break
        serial = gs.rng.hand_pick(victim, vb.hand)
        vb.hand.remove(serial)
        vb.deck.append(serial)
        gs.move_card(serial, AreaType.HAND, AreaType.DECK, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
        moved = True
    # Shuffle semantics differ per native script: the plain variant shuffles only when a card actually
    # MOVED; the perHeads variant shuffles whenever picks were ATTEMPTED.
    if moved or (args.get("perHeads") and count > 0):
        _shuffle(gs, victim)
    return True


# The native logs a bottom-of-deck placement with a pseudo toArea beyond the AreaType enum.
# enum (pinned rvl401_9000 f14 / rvlitems401_9100 f11: MOVE_CARD LOOKING->14).
_AREA_DECK_BOTTOM = 14


def op_opp_hand_reveal(gs, fr, args) -> bool:
    """NO select and NO net state change, but the replay hand-pick FIFO must still be drained."""
    victim = 1 - fr.seat
    vb = gs.players[victim]
    serials = list(vb.hand)
    for s in serials:
        gs.move_card(s, AreaType.HAND, AreaType.LOOKING, seat=victim,
                     visible_to_owner=False, visible_to_opponent=True)
    gs.rng.hand_pick_expect(victim, serials)
    for s in serials:
        gs.move_card(s, AreaType.LOOKING, AreaType.HAND, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    flt = args.get("discardFilter")
    if flt is not None:
        matched = [s for s in serials if _card_matches(gs, s, flt)]
        for s in matched:
            vb.hand.remove(s)
            vb.discard.append(s)
            gs.move_card(s, AreaType.HAND, AreaType.DISCARD, seat=victim,
                         visible_to_owner=True, visible_to_opponent=True)
        gs.rng.hand_pick_expect(victim, matched)
    cf = args.get("countFilter")
    if cf is not None:
        fr.vars["revealed_match_count"] = sum(
            1 for s in serials if _card_matches(gs, s, cf))
    return True


def op_opp_hand_reveal_choose(gs, fr, args) -> bool:
    """The chosen exit logs FIRST, then the rest return in ORIGINAL order."""
    victim = 1 - fr.seat
    vb = gs.players[victim]
    if "answer" not in fr.vars:
        serials = list(vb.hand)
        if not serials:
            return True
        for s in serials:
            gs.move_card(s, AreaType.HAND, AreaType.LOOKING, seat=victim,
                         visible_to_owner=False, visible_to_opponent=True)
        gs.rng.hand_pick_expect(victim, serials)
        vb.hand.clear()
        gs.looking = list(serials)
        gs.looking_owner = fr.seat
        ctx = (SelectContext.TO_DECK_BOTTOM if args.get("to") == "deckBottom"
               else SelectContext.DISCARD)
        pose(gs, fr.seat, type=SelectType.CARD, context=ctx,
             options=[opt_card(AreaType.LOOKING, i, victim)
                      for i in range(len(serials))],
             effect_card=fr.source)
        return False
    idx = fr.vars.pop("answered_options")[0]["index"]
    fr.vars.pop("answer")
    serials = list(gs.looking or [])
    chosen = serials[idx]
    gs.looking = None
    gs.looking_owner = -1
    if args.get("to") == "deckBottom":
        vb.deck.insert(0, chosen)          # deck lists bottom-first: bottom = index 0
        gs.move_card(chosen, AreaType.LOOKING, _AREA_DECK_BOTTOM, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    else:
        vb.discard.append(chosen)
        gs.move_card(chosen, AreaType.LOOKING, AreaType.DISCARD, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    for s in serials:
        if s == chosen:
            continue
        vb.hand.append(s)
        gs.move_card(s, AreaType.LOOKING, AreaType.HAND, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    return True


def _attach_from_deck(gs, seat, energy, target, *, zone=None) -> None:
    (gs.players[seat].deck if zone is None else zone).remove(energy)
    target.energy.append(energy)
    gs.note_attach(energy)
    gs.emit({"type": int(LogType.ATTACH), "playerIndex": seat,
             "cardId": gs.card_id(energy), "serial": energy,
             "cardIdTarget": gs.card_id(target.top), "serialTarget": target.top})


def op_eot_attach_energy_from_discard(gs, fr, args) -> bool:
    """Optional (min 0); no matching discard energy or no Active means no pose at all."""
    seat = fr.seat
    b = gs.players[seat]
    holder = b.active
    if "answer" not in fr.vars:
        opts = [opt_card(AreaType.DISCARD, i, seat) for i, s in enumerate(b.discard)
                if _card_matches(gs, s, args.get("filter", {}))]
        if not opts or holder is None:
            return True
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_TO,
             options=opts, min_count=0, max_count=1, effect_card=fr.source)
        return False
    ans = fr.vars.pop("answered_options")
    fr.vars.pop("answer")
    if ans and holder is not None:
        _attach_from_deck(gs, seat, b.discard[ans[0]["index"]], holder, zone=b.discard)
    return True


def op_deck_energy_attach_distribute(gs, fr, args) -> bool:
    """NO legal target = the picked cards STAY IN THE DECK, silently."""
    seat = fr.seat
    b = gs.players[seat]
    v = fr.vars
    buckets = args["buckets"]
    mode = args.get("mode", "anyWay")
    # source "discard": picks pose over DISCARD positions with NO listing and min 1 (the may was the
    # ask), and no shuffle at the end. Default stays the deck-search shape.
    from_discard = args.get("source") == "discard"
    zone = b.discard if from_discard else b.deck
    zone_area = AreaType.DISCARD if from_discard else AreaType.DECK

    def targets_now():
        from .options import _targets
        flt = args.get("targets")
        out = []
        for area, idx, p in _targets(gs, seat):
            if args.get("benchOnly") and area != int(AreaType.BENCH):
                continue
            if flt and not _card_matches(gs, p.top, flt):
                continue
            out.append((area, idx, p))
        return out

    while True:
        bi = v.setdefault("bucket_i", 0)
        if "pending_cards" not in v:
            if bi >= len(buckets):
                v.pop("bucket_i", None)
                if b.deck and not from_discard:  # an empty deck logs no SHUFFLE
                    _shuffle(gs, seat)
                return True
            bk = buckets[bi]
            if "answer" not in v:
                bk_max = bk.get("max", 1)
                if "maxPerHeads" in bk:
                    bk_max = bk["maxPerHeads"] * v.get("heads_count", 0)
                opts = _zone_options(gs, seat, zone, zone_area,
                                     bk.get("filter", {}))
                if not opts or bk_max <= 0:
                    gs.turn_action_count += 1  # zero heads still shuffles at the end; the skipped ask still bumps tac
                    v["bucket_i"] = bi + 1
                    continue
                cap = min(bk_max, len(opts))
                if bk.get("distinctTypes"):
                    kinds = {int(gs.stat(zone[o["index"]]).energyType)
                             for o in opts}
                    cap = min(cap, len(kinds))
                pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_TO,
                     options=opts, min_count=1 if from_discard else 0,
                     max_count=cap,
                     deck_listing=None if from_discard else list(b.deck),
                     effect_card=fr.source)
                return False
            v["pending_cards"] = [zone[o["index"]]
                                  for o in v.pop("answered_options")]
            v.pop("answer")
        cards = v["pending_cards"]
        if not cards:
            v.pop("pending_cards")
            v["bucket_i"] = v["bucket_i"] + 1
            continue
        rows = targets_now()
        if not rows:                             # nowhere to place: cards stay in deck
            # the unposable placement asks still bump tac — one per remaining card (anyWay) or one for the
            # batch (oneTarget)
            gs.turn_action_count += len(cards) if mode != "oneTarget" else 1
            v["pending_cards"] = []
            continue
        from .turn import _target_of
        if mode == "oneTarget":
            if "answer" not in v:
                pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_FROM,
                     options=[opt_card(a, i, seat) for a, i, _p in rows],
                     min_count=1, max_count=1,
                     deck_listing=(list(b.deck) if args.get("targetListing", True)
                                   else None),
                     effect_card=fr.source)
                return False
            o = v.pop("answered_options")[0]
            v.pop("answer")
            target = _target_of(gs, seat, o["area"], o["index"])
            for s in list(cards):
                _attach_from_deck(gs, seat, s, target, zone=zone)
            v["pending_cards"] = []
            continue
        energy = cards[0]
        if "answer" not in v:
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_FROM,
                 options=[opt_card(a, i, seat) for a, i, _p in rows],
                 min_count=1, max_count=1,
                 deck_listing=(None if from_discard
                               or not args.get("targetListing", True)
                               else list(b.deck)),  # a per-script quirk: some prints drop the deck listing at placement
                 context_card=energy,
                 effect_card=fr.source)
            return False
        o = v.pop("answered_options")[0]
        v.pop("answer")
        _attach_from_deck(gs, seat, energy,
                          _target_of(gs, seat, o["area"], o["index"]), zone=zone)
        cards.pop(0)


def op_deck_attach_per_bench(gs, fr, args) -> bool:
    """One pick per benched mon in BENCH order; ONE shuffle after the whole loop."""
    seat = fr.seat
    b = gs.players[seat]
    v = fr.vars
    while True:
        k = v.setdefault("bench_i", 0)
        if k >= len(b.bench):
            v.pop("bench_i", None)
            _shuffle(gs, seat)
            return True
        mon = b.bench[k]
        if "answer" not in v:
            opts = _zone_options(gs, seat, b.deck, AreaType.DECK,
                                 args.get("filter", {}))
            if not opts:
                gs.turn_action_count += 1
                v["bench_i"] = k + 1
                continue
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_TO,
                 options=opts, min_count=0, max_count=1,
                 deck_listing=list(b.deck), context_card=mon.top,
                 effect_card=fr.source)
            return False
        picked = [b.deck[o["index"]] for o in v.pop("answered_options")]
        v.pop("answer")
        for s in picked:
            _attach_from_deck(gs, seat, s, mon)
        v["bench_i"] = k + 1


def op_deck_evolve_per_bench(gs, fr, args) -> bool:
    """One pick per benched mon in bench order; ONE shuffle after the whole loop."""
    seat = fr.seat
    b = gs.players[seat]
    v = fr.vars
    while True:
        k = v.setdefault("bench_i", 0)
        if k >= len(b.bench):
            v.pop("bench_i", None)
            _shuffle(gs, seat)
            return True
        mon = b.bench[k]
        if "answer" not in v:
            name = gs.stat(mon.top).name
            opts = [opt_card(AreaType.DECK, i, seat) for i, s in enumerate(b.deck)
                    if gs.stat(s).cardType == CardType.POKEMON
                    and gs.stat(s).evolvesFrom == name]
            if not opts:
                gs.turn_action_count += 1
                v["bench_i"] = k + 1
                continue
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.EVOLVES_TO,
                 options=opts, min_count=0, max_count=1,
                 deck_listing=list(b.deck), context_card=mon.top,
                 effect_card=fr.source)
            return False
        picked = [b.deck[o["index"]] for o in v.pop("answered_options")]
        v.pop("answer")
        if picked:
            from .turn import _apply_evolution
            b.deck.remove(picked[0])
            _apply_evolution(gs, seat, picked[0], mon)
        v["bench_i"] = k + 1


def op_deck_evolve_choose_and_shuffle(gs, fr, args) -> bool:
    """Target = the FIRST board-order mon the picked card evolves from. Posed shape UNPINNED."""
    seat = fr.seat
    b = gs.players[seat]
    from .options import _targets
    rows = _targets(gs, seat)
    if "answer" not in fr.vars:
        names = {gs.stat(p.top).name for _a, _i, p in rows}
        opts = [opt_card(AreaType.DECK, i, seat) for i, s in enumerate(b.deck)
                if gs.stat(s).cardType == CardType.POKEMON
                and gs.stat(s).evolvesFrom in names]
        if not opts:
            gs.turn_action_count += 1
            _shuffle(gs, seat)
            return True
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.EVOLVES_TO,
             options=opts, min_count=0, max_count=1,
             deck_listing=list(b.deck), effect_card=fr.source)
        return False
    picked = [b.deck[o["index"]] for o in fr.vars.pop("answered_options")]
    fr.vars.pop("answer")
    if picked:
        evo = picked[0]
        base = gs.stat(evo).evolvesFrom
        target = next((p for _a, _i, p in rows if gs.stat(p.top).name == base), None)
        if target is not None:
            from .turn import _apply_evolution
            b.deck.remove(evo)
            _apply_evolution(gs, seat, evo, target)
    _shuffle(gs, seat)
    return True


def op_deck_distinct_basic_energy_to_hand(gs, fr, args) -> bool:
    """Sequential max-1 picks — native never poses max N — and a whiff stops the sequence."""
    seat = fr.seat
    b = gs.players[seat]
    v = fr.vars
    while True:
        taken = v.setdefault("taken_types", [])
        if len(taken) >= args.get("n", 3):
            v.pop("taken_types", None)
            _shuffle(gs, seat)
            return True
        if "answer" not in v:
            opts = [opt_card(AreaType.DECK, i, seat) for i, s in enumerate(b.deck)
                    if gs.stat(s).cardType == CardType.BASIC_ENERGY
                    and int(gs.stat(s).energyType) not in taken]
            if not opts:
                gs.turn_action_count += 1
                v.pop("taken_types", None)
                _shuffle(gs, seat)
                return True
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_HAND,
                 options=opts, min_count=0, max_count=1,
                 deck_listing=list(b.deck), effect_card=fr.source)
            return False
        picked = [b.deck[o["index"]] for o in v.pop("answered_options")]
        v.pop("answer")
        if not picked:
            v.pop("taken_types", None)
            _shuffle(gs, seat)
            return True
        s = picked[0]
        b.deck.remove(s)
        b.hand.append(s)
        gs.move_card(s, AreaType.DECK, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
        taken.append(int(gs.stat(s).energyType))


def op_damage_per_revealed(gs, fr, args) -> bool:
    """OVERRIDE semantics; logs after the reveal moves and even at 0 matches."""
    fr.vars["damage_override"] = args["per"] * fr.vars.get("revealed_match_count", 0)
    return True


def op_discard_energy_count_scaled(gs, fr, args) -> bool:
    """``discarded_count`` scales the damage op that FOLLOWS. ``scope``: self | own | bench | holder."""
    seat = fr.seat
    b = gs.players[seat]
    flt = args.get("filter", {})
    scope = args.get("scope", "self")
    if scope == "self":
        holders = [(int(AreaType.ACTIVE), 0, b.active)] if b.active else []
    elif scope == "bench":
        holders = [(int(AreaType.BENCH), i, p) for i, p in enumerate(b.bench)]
    elif scope == "holder":
        holders = [(area, idx, p) for area, idx, p in
                   ([(int(AreaType.ACTIVE), 0, b.active)] if b.active else [])
                   + [(int(AreaType.BENCH), i, q) for i, q in enumerate(b.bench)]
                   if p.top == fr.source]
    else:
        holders = ([(int(AreaType.ACTIVE), 0, b.active)] if b.active else []) + \
            [(int(AreaType.BENCH), i, p) for i, p in enumerate(b.bench)]
    cands = [(area, idx, p, k, s) for area, idx, p in holders
             for k, s in enumerate(p.energy) if _card_matches(gs, s, flt)]

    def _discard(p, serial):
        p.energy.remove(serial)
        b.discard.append(serial)
        gs.move_card(serial, AreaType.ENERGY, AreaType.DISCARD, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)

    if args.get("all"):
        ordered = sorted(cands, key=lambda c: gs.attach_seq.get(c[4], 0))
        for _area, _idx, p, _k, s in ordered:
            _discard(p, s)
        fr.vars["discarded_count"] = len(ordered)
        return True
    if not cands:
        fr.vars["discarded_count"] = 0
        return True
    if "answer" not in fr.vars:
        opts = [{"type": int(OptionType.ENERGY_CARD), "area": area, "index": idx,
                 "playerIndex": seat, "energyIndex": k}
                for area, idx, _p, k, _s in cands]
        n = min(args.get("max", len(cands)), len(cands))
        pose(gs, seat, type=SelectType.ATTACHED_CARD,
             context=SelectContext.DISCARD_ENERGY_CARD, options=opts,
             min_count=min(args.get("min", 0), n), max_count=n,
             effect_card=fr.source)
        return False
    answered = fr.vars.pop("answered_options")
    fr.vars.pop("answer")
    picked = []
    for o in answered:
        p = b.active if o["area"] == int(AreaType.ACTIVE) else b.bench[o["index"]]
        picked.append((p, p.energy[o["energyIndex"]]))
    for p, s in picked:                    # resolve serials before any list mutates
        _discard(p, s)
    fr.vars["discarded_count"] = len(picked)
    return True


def op_discard_hand_count_scaled(gs, fr, args) -> bool:
    """``discarded_count`` scales the damage op that follows."""
    seat = fr.seat
    b = gs.players[seat]
    flt = args.get("filter", {})
    if "answer" not in fr.vars:
        opts = [opt_card(AreaType.HAND, i, seat) for i, s in enumerate(b.hand)
                if _card_matches(gs, s, flt)]
        if not opts:
            fr.vars["discarded_count"] = 0
            return True
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.DISCARD,
             options=opts, min_count=0,
             max_count=min(args.get("max", len(opts)), len(opts)),
             effect_card=fr.source)
        return False
    serials = [b.hand[o["index"]] for o in fr.vars.pop("answered_options")]
    fr.vars.pop("answer")
    for s in serials:
        b.hand.remove(s)
        b.discard.append(s)
        gs.move_card(s, AreaType.HAND, AreaType.DISCARD, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    fr.vars["discarded_count"] = len(serials)
    return True


def op_damage_per_discarded(gs, fr, args) -> bool:
    fr.vars["damage_override"] = args["per"] * fr.vars.get("discarded_count", 0)
    return True


def op_bonus_per_discarded(gs, fr, args) -> bool:
    fr.vars["damage_bonus"] = fr.vars.get("damage_bonus", 0) + \
        args["per"] * fr.vars.get("discarded_count", 0)
    return True


def op_discard_stadium(gs, fr, args) -> bool:
    """It goes to its OWNER's discard; no stadium in play = no-op."""
    for old in gs.stadium:
        owner = gs.owner(old)
        gs.players[owner].discard.append(old)
        gs.move_card(old, AreaType.STADIUM, AreaType.DISCARD, seat=owner,
                     visible_to_owner=True, visible_to_opponent=True)
    gs.stadium = []
    return True


def op_reduce_defender_next_turn(gs, fr, args) -> bool:
    """Rides the DEFENDING mon (the take-less convention). Seeded."""
    them = gs.players[1 - fr.seat].active
    if them is not None:
        them.outgoing_less_turn = gs.turn + 1
        them.outgoing_less = args["n"]
    return True


def op_lock_defender_attacks(gs, fr, args) -> bool:
    """Menu-enforced on the defender's next turn; rides the mon. Seeded."""
    them = gs.players[1 - fr.seat].active
    if them is not None:
        them.no_attack_turn = gs.turn + 1
    return True


def op_deck_evolve_self_and_shuffle(gs, fr, args) -> bool:
    """Target FIXED to the attack's own Active; may whiff. Seeded."""
    seat = fr.seat
    b = gs.players[seat]
    me = b.active
    if me is None:
        return True
    if "answer" not in fr.vars:
        name = gs.stat(me.top).name
        opts = [opt_card(AreaType.DECK, i, seat) for i, s in enumerate(b.deck)
                if gs.stat(s).cardType == CardType.POKEMON
                and gs.stat(s).evolvesFrom == name]
        if not opts:                               # empty optional search: never posed
            gs.turn_action_count += 1
            _shuffle(gs, seat)
            return True
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.EVOLVES_TO,
             options=opts, min_count=0, max_count=1,
             deck_listing=list(b.deck), effect_card=fr.source,
             context_card=me.top)
        return False
    picked = [b.deck[o["index"]] for o in fr.vars.pop("answered_options")]
    fr.vars.pop("answer")
    if not picked:                                 # whiff: the reveal still shuffles
        _shuffle(gs, seat)
        return True
    evo = picked[0]
    from .turn import _apply_evolution
    b.deck.remove(evo)
    _apply_evolution(gs, seat, evo, me)
    _shuffle(gs, seat)
    return True


def op_protect_next_turn(gs, fr, args) -> bool:
    """damage.py zeroes incoming attack damage. Effect suppression beyond damage is NOT modeled."""
    me = gs.players[fr.seat].active
    if me is not None:
        me.protect_turn = gs.turn + 1
    return True


def op_take_less_next_turn(gs, fr, args) -> bool:
    """Applied AFTER W/R, on the opponent's next turn only. Rides the Pokémon — seeded."""
    me = gs.players[fr.seat].active
    if me is not None:
        me.take_less_turn = gs.turn + 1
        me.take_less = args["n"]
    return True


def op_may_ask(gs, fr, args) -> bool:
    """SKIPPED entirely — no ask at all — when the optional effect has no live target."""
    if not check_legal(gs, fr.seat, args.get("requires", [])):
        return True
    if "answer" not in fr.vars:
        pose(gs, fr.seat, type=SelectType.YES_NO, context=SelectContext.ACTIVATE,
             options=yes_no(), effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    if o["type"] == int(OptionType.YES):
        fr.program = fr.program[:fr.pc + 1] + list(args["program"]) + \
            fr.program[fr.pc + 1:]
    return True


def op_deck_energy_attach(gs, fr, args) -> bool:
    """``maxVar: heads_count``: ZERO heads does NOTHING — no ask, no shuffle."""
    seat = fr.seat
    b = gs.players[seat]
    if args.get("maxVar") == "heads_count":
        cap = fr.vars.get("heads_count", 0)
        if cap <= 0 and "picked" not in fr.vars and "answer" not in fr.vars:
            return True
        args = dict(args, max=cap)
    if "picked" not in fr.vars:
        if "answer" not in fr.vars:
            opts = _zone_options(gs, seat, b.deck, AreaType.DECK, args.get("filter", {}))
            if not opts:
                gs.turn_action_count += 1
                _shuffle(gs, seat)
                return True
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_TO,
                 options=opts, min_count=0, max_count=min(args.get("max", 1), len(opts)),
                 deck_listing=list(b.deck), effect_card=fr.source)
            return False
        fr.vars["picked"] = [b.deck[o["index"]]
                             for o in fr.vars.pop("answered_options")]
        fr.vars.pop("answer")
        if not fr.vars["picked"]:
            fr.vars.pop("picked")
            _shuffle(gs, seat)
            return True
    if args.get("target", "self") == "self":
        target = b.active
        for s in fr.vars.pop("picked"):
            if target is None:
                break
            b.deck.remove(s)
            target.energy.append(s)
            gs.note_attach(s)
            gs.emit({"type": int(LogType.ATTACH), "playerIndex": seat,
                     "cardId": gs.card_id(s), "serial": s,
                     "cardIdTarget": gs.card_id(target.top), "serialTarget": target.top})
        _shuffle(gs, seat)
        return True
    energy = fr.vars["picked"][0]
    if "answer" not in fr.vars:
        from .options import _targets
        opts = [opt_card(area, idx, seat) for area, idx, _p in _targets(gs, seat)]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_FROM,
             options=opts, min_count=1, max_count=1, deck_listing=list(b.deck),
             context_card=energy, effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    fr.vars.pop("picked")
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


def op_discard_energy_attach_self(gs, fr, args) -> bool:
    """Imperative wording poses min=1; the carrier attack is menu-gated on the fuel."""
    seat = fr.seat
    b = gs.players[seat]
    me = b.active
    if me is None:
        return True
    if "answer" not in fr.vars:
        opts = _zone_options(gs, seat, b.discard, AreaType.DISCARD,
                             args.get("filter", {}))
        if not opts:
            return True                            # skipped rider: no tac bump (Aura Jab pin)
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_TO,
             options=opts, min_count=1,
             max_count=min(args.get("max", 1), len(opts)), effect_card=fr.source)
        return False
    picked = [b.discard[o["index"]] for o in fr.vars.pop("answered_options")]
    fr.vars.pop("answer")
    for s in picked:
        b.discard.remove(s)
        me.energy.append(s)
        gs.note_attach(s)
        gs.emit({"type": int(LogType.ATTACH), "playerIndex": seat,
                 "cardId": gs.card_id(s), "serial": s,
                 "cardIdTarget": gs.card_id(me.top), "serialTarget": me.top})
    return True


def op_self_return_to_hand(gs, fr, args) -> bool:
    """Stack top-first, energies LIFO, tools last — the KO/shuffle-in order. Seeded."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" in fr.vars:
        o = fr.vars.pop("answered_options")[0]
        fr.vars.pop("answer")
        p = b.bench.pop(o["index"])
        b.active = p
        p.moved_active_turn = gs.turn
        gs.move_card(p.top, AreaType.BENCH, AreaType.ACTIVE, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
        return True
    me = None
    for p in gs.in_play(seat):
        if p.top == fr.source:
            me = p
            break
    if me is None:
        return True
    was_active = me is b.active
    from_area = AreaType.ACTIVE if was_active else AreaType.BENCH
    if was_active:
        b.active = None
        b.poisoned = b.burned = False              # conditions leave play with the Active
        b.asleep = b.paralyzed = b.confused = False
    else:
        b.bench.remove(me)
    for k, s in enumerate(reversed(me.stack)):
        area = from_area if k == 0 else AreaType.PRE_EVOLUTION
        b.hand.append(s)
        gs.move_card(s, area, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    for s in list(reversed(me.energy)):
        b.hand.append(s)
        gs.move_card(s, AreaType.ENERGY, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    for s in me.tools:
        b.hand.append(s)
        gs.move_card(s, AreaType.TOOL, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    if was_active and b.bench:
        opts = [opt_card(AreaType.BENCH, i, seat) for i in range(len(b.bench))]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_ACTIVE,
             options=opts, min_count=1, max_count=1)
        return False
    return True


def op_distribute_counters(gs, fr, args) -> bool:
    """One select PER counter, with remainDamageCounter counting down."""
    seat = fr.seat
    opp = 1 - seat
    ob = gs.players[opp]
    if stadium_def(gs).get("benchCounterShield"):
        return True  # counters cannot land on benched mons: no legal targets, so nothing is placed (UNPINNED)
    if "left" not in fr.vars:
        fr.vars["left"] = args.get("counters", 1)
    while fr.vars["left"] > 0 and ob.bench:
        if "answer" not in fr.vars:
            opts = [opt_card(AreaType.BENCH, i, opp) for i in range(len(ob.bench))]
            pose(gs, seat, type=SelectType.CARD,
                 context=SelectContext.DAMAGE_COUNTER_ANY,
                 options=opts, min_count=1, max_count=1, effect_card=fr.source,
                 remain_damage_counter=fr.vars["left"])
            return False
        o = fr.vars.pop("answered_options")[0]
        fr.vars.pop("answer")
        target = ob.bench[o["index"]]
        target.hp -= 10  # damage COUNTERS stack raw past 0, unlike direct damage which floors the Active at 0
        gs.emit({"type": int(LogType.HP_CHANGE),
                 "playerIndex": opp,
                 "cardId": gs.card_id(target.top), "serial": target.top,
                 "value": -10, "putDamageCounter": True})
        fr.vars["left"] -= 1
    fr.vars.pop("left")
    return True


# --- coin pre-ops (the "pre" program runs after the ATTACK log, before damage) -----------

def op_fail_unless_heads(gs, fr, args) -> bool:
    """Cancels the damage AND the rider program."""
    if not fr.vars.get("heads"):
        fr.vars["cancel"] = True
    return True


def op_bonus_if_heads(gs, fr, args) -> bool:
    if fr.vars.get("heads"):
        fr.vars["damage_bonus"] = fr.vars.get("damage_bonus", 0) + args["n"]
    return True


def op_coins_count(gs, fr, args) -> bool:
    """The FLIP seat drives the replay coin channel; ``flips_total`` persists for tails math."""
    if "flips_left" not in fr.vars:
        n = args.get("n")
        if n is None:
            from .damage import scale_count
            n = scale_count(gs, fr.seat, args["var"], args.get("energyType"))
        fr.vars["flips_left"] = n
        fr.vars["flips_total"] = n
        fr.vars["heads_count"] = 0
    flip_seat = 1 - fr.seat if args.get("owner") == "opp" else fr.seat
    while fr.vars["flips_left"] > 0:
        if args.get("owner") == "opp":
            head = gs.coin_flip(flip_seat)     # opponent flips never go manual-coin
        else:
            head = _flip(gs, fr)
            if head is None:
                return False
        fr.vars["flips_left"] -= 1
        if head:
            fr.vars["heads_count"] += 1
    fr.vars.pop("flips_left")
    return True


def op_coins_until_tails(gs, fr, args) -> bool:
    # Guard on "flipping", not "heads_count": rider frames may inherit a PRE program's
    # heads_count (the Magical-Leaf threading), and this op always tallies afresh.
    if "flipping" not in fr.vars:
        fr.vars["heads_count"] = 0
        fr.vars["flipping"] = True
    while fr.vars.get("flipping"):
        head = _flip(gs, fr)
        if head is None:
            return False
        if head:
            fr.vars["heads_count"] += 1
        else:
            fr.vars.pop("flipping")
    return True


def op_damage_per_heads(gs, fr, args) -> bool:
    fr.vars["damage_override"] = args["per"] * fr.vars.get("heads_count", 0)
    return True


def op_bonus_per_heads(gs, fr, args) -> bool:
    fr.vars["damage_bonus"] = fr.vars.get("damage_bonus", 0) + \
        args["per"] * fr.vars.get("heads_count", 0)
    return True


def op_if_tails(gs, fr, args) -> bool:
    if fr.vars.get("heads"):
        fr.pc += args.get("skip", 1)
    return True


def op_skip(gs, fr, args) -> bool:
    fr.pc += args.get("n", 1)
    return True


def op_bonus_if_all_heads(gs, fr, args) -> bool:
    if fr.vars.get("heads_count", 0) == fr.vars.get("flips_total", -1):
        fr.vars["damage_bonus"] = fr.vars.get("damage_bonus", 0) + args["n"]
    return True


def op_damage_per_tails(gs, fr, args) -> bool:
    """A zero-tails run still logs an HP_CHANGE of value 0."""
    tails = fr.vars.get("flips_total", 0) - fr.vars.get("heads_count", 0)
    fr.vars["damage_override"] = args["per"] * tails
    return True


def op_damage_self_if_no_heads(gs, fr, args) -> bool:
    """The self-hit logs HP_CHANGE and the normal sweep buries the body."""
    if fr.vars.get("heads_count", 0) == 0 and fr.vars.get("flips_total", 0) > 0:
        me = gs.players[fr.seat].active
        if me is not None:
            me.hp = max(0, me.hp - args["damage"])
            gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": fr.seat,
                     "cardId": gs.card_id(me.top), "serial": me.top,
                     "value": -args["damage"], "putDamageCounter": False})
    return True


def op_self_lock_all_next_turn(gs, fr, args) -> bool:
    me = gs.players[fr.seat].active
    if me is not None:
        for aid in gs.stat(me.top).attacks:
            me.attack_locks[str(aid)] = gs.turn + 2
    return True


def _effect_ko(gs, p) -> None:
    """NO HP_CHANGE log; the normal sweep runs the prize/promotion flow. -1000 beats any HP bonus."""
    p.hp = -1000


def op_knock_out_active(gs, fr, args) -> bool:
    victim = gs.players[1 - fr.seat].active
    if victim is None:
        return True
    if args.get("basicOnly") and not gs.stat(victim.top).basic:
        return True
    _effect_ko(gs, victim)
    return True


def op_knock_out_choose(gs, fr, args) -> bool:
    """``scope``: bench | any (any = active first, then bench). Zero candidates = no-op."""
    seat = fr.seat
    ob = gs.players[1 - seat]
    rows = []
    if args.get("scope", "bench") != "bench" and ob.active is not None:
        rows.append((int(AreaType.ACTIVE), 0, ob.active))
    rows += [(int(AreaType.BENCH), i, p) for i, p in enumerate(ob.bench)]
    if args.get("basicOnly"):
        rows = [(a, i, p) for a, i, p in rows if gs.stat(p.top).basic]
    if not rows:
        return True
    if "answer" not in fr.vars:
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.DISCARD,
             options=[opt_card(a, i, 1 - seat) for a, i, _p in rows],
             effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    target = (ob.active if o["area"] == int(AreaType.ACTIVE)
              else ob.bench[o["index"]])
    _effect_ko(gs, target)
    return True


def op_coin_damage_each_opp(gs, fr, args) -> bool:
    """W/R on the Active only, never the bench; a MISS logs nothing at all."""
    seat = fr.seat
    ob = gs.players[1 - seat]
    from .damage import apply_weakness_resistance
    me = gs.players[seat].active
    rows = ([(True, ob.active)] if ob.active is not None else []) + \
        [(False, p) for p in ob.bench]
    for is_active, p in rows:
        head = gs.coin_flip(seat)
        if not head:
            continue
        dmg = args["damage"]
        if is_active and me is not None:
            dmg = apply_weakness_resistance(gs, me, p, dmg)
        p.hp = max(0, p.hp - dmg)
        gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": 1 - seat,
                 "cardId": gs.card_id(p.top), "serial": p.top,
                 "value": -dmg, "putDamageCounter": False})
    return True


def op_shuffle_in_play_into_deck_choose(gs, fr, args) -> bool:
    """Attachments follow the KO-sweep area order. Zero candidates = no-op."""
    seat = fr.seat
    victim = 1 - seat
    vb = gs.players[victim]
    if "shuffled_active" in fr.vars:
        o = fr.vars.pop("answered_options")[0]
        fr.vars.pop("answer")
        p = vb.bench.pop(o["index"])
        vb.active = p
        p.moved_active_turn = gs.turn
        gs.move_card(p.top, AreaType.BENCH, AreaType.ACTIVE, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
        return True
    rows = []
    if args.get("scope") == "any" and vb.active is not None:
        rows.append((int(AreaType.ACTIVE), 0, vb.active))
    rows += [(int(AreaType.BENCH), i, p) for i, p in enumerate(vb.bench)]
    if not rows:
        return True
    if "answer" not in fr.vars:
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_DECK,
             options=[opt_card(a, i, victim) for a, i, _p in rows],
             effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    was_active = o["area"] == int(AreaType.ACTIVE)
    if was_active:
        target = vb.active
        vb.active = None
        vb.poisoned = vb.burned = False            # conditions leave with the Active
        vb.asleep = vb.paralyzed = vb.confused = False
        from_area = AreaType.ACTIVE
    else:
        target = vb.bench.pop(o["index"])
        from_area = AreaType.BENCH
    for k, s in enumerate(reversed(target.stack)):
        area = from_area if k == 0 else AreaType.PRE_EVOLUTION
        vb.deck.append(s)
        gs.move_card(s, area, AreaType.DECK, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    for s in list(target.energy):
        vb.deck.append(s)
        gs.move_card(s, AreaType.ENERGY, AreaType.DECK, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    for s in target.tools:
        vb.deck.append(s)
        gs.move_card(s, AreaType.TOOL, AreaType.DECK, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    _shuffle(gs, victim)
    if was_active and vb.bench:
        fr.vars["shuffled_active"] = True
        pose(gs, victim, type=SelectType.CARD, context=SelectContext.TO_ACTIVE,
             options=[opt_card(AreaType.BENCH, i, victim)
                      for i in range(len(vb.bench))])
        return False
    return True


def _rare_candy_pairs(gs, seat):
    """An in-play Basic that did NOT enter this turn, plus a hand Stage 2 matching it BY NAME."""
    from .options import _targets
    b = gs.players[seat]
    if gs.turn <= 2:                     # "can't use this card during your first turn"
        return []
    stage1_from = {}                     # stage1 name -> its basic's name
    for cid in gs.db.cards:
        st = gs.db.card(cid)
        if st.cardType == CardType.POKEMON and st.stage1 and st.evolvesFrom:
            stage1_from[st.name] = st.evolvesFrom
    pairs = []
    for i, s in enumerate(b.hand):
        st = gs.stat(s)
        if st.cardType != CardType.POKEMON or not st.stage2:
            continue
        basic_name = stage1_from.get(st.evolvesFrom)
        if basic_name is None:
            continue
        for area, idx, p in _targets(gs, seat):
            if (gs.stat(p.top).basic and p.entered_turn < gs.turn
                    and gs.stat(p.top).name == basic_name):
                pairs.append((i, area, idx))
    return pairs


def op_rare_candy_evolve(gs, fr, args) -> bool:
    """The MAIN-menu evolve encoding; resolution is ONE evolve log with the Stage 1 skipped."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        opts = [{"type": int(OptionType.EVOLVE), "area": int(AreaType.HAND),
                 "index": i, "inPlayArea": area, "inPlayIndex": idx}
                for i, area, idx in _rare_candy_pairs(gs, seat)]
        if not opts:
            return True                  # unreachable behind the menu gate
        pose(gs, seat, type=SelectType.EVOLVE, context=SelectContext.EVOLVE,
             options=opts, effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    serial = b.hand[o["index"]]
    from .turn import _apply_evolution, _target_of
    target = _target_of(gs, seat, o["inPlayArea"], o["inPlayIndex"])
    b.hand.remove(serial)
    _apply_evolution(gs, seat, serial, target)
    # A skip-evolve still "plays this Pokémon from your hand to evolve", so the Stage 2's onEvolve
    # ability fires — the same trigger the MAIN evolve path queues, posed by _after_program's flush.
    hook = (def_for(gs.card_id(serial)) or {}).get("onEvolve")
    if hook and check_legal(gs, seat, hook.get("legal", [])):
        gs.pending_triggers.append({
            "cardId": gs.card_id(serial), "serial": serial, "source": serial,
            "ops": [{"op": "xActivateAsk", "program": hook["program"]}]})
    return True


def op_both_hand_trim_to(gs, fr, args) -> bool:
    """min = max = hand - N; the opponent's exits drain the replay hand-pick FIFO."""
    seat = fr.seat
    n = args.get("n", 5)
    while True:
        stage = fr.vars.setdefault("trim_stage", 0)    # 0 = opponent, 1 = self
        if stage > 1:
            fr.vars.pop("trim_stage", None)
            return True
        victim = 1 - seat if stage == 0 else seat
        vb = gs.players[victim]
        if "answer" in fr.vars:
            picked = [vb.hand[o["index"]] for o in fr.vars.pop("answered_options")]
            fr.vars.pop("answer")
            for s in picked:
                vb.hand.remove(s)
                vb.discard.append(s)
                gs.move_card(s, AreaType.HAND, AreaType.DISCARD, seat=victim,
                             visible_to_owner=True, visible_to_opponent=True)
            if victim != seat:
                gs.rng.hand_pick_expect(victim, picked)
            fr.vars["trim_stage"] = stage + 1
            continue
        k = len(vb.hand) - n
        if k <= 0:
            fr.vars["trim_stage"] = stage + 1
            continue
        pose(gs, victim, type=SelectType.CARD, context=SelectContext.DISCARD,
             options=[opt_card(AreaType.HAND, i, victim)
                      for i in range(len(vb.hand))],
             min_count=k, max_count=k, effect_card=fr.source)
        return False


def op_pick_discard(gs, fr, args) -> bool:
    """A `deck` dest shuffles after. Empty filter result = no pose."""
    seat = fr.seat
    b = gs.players[seat]
    to_deck = args.get("dest") == "deck"
    if "answer" in fr.vars:
        picked = [b.discard[o["index"]] for o in fr.vars.pop("answered_options")]
        fr.vars.pop("answer")
        dest = b.deck if to_deck else b.hand
        toarea = AreaType.DECK if to_deck else AreaType.HAND
        for s in picked:
            b.discard.remove(s)
            dest.append(s)
            gs.move_card(s, AreaType.DISCARD, toarea, seat=seat,
                         visible_to_owner=True, visible_to_opponent=True)
        if to_deck and picked:
            _shuffle(gs, seat)
        return True
    opts = _zone_options(gs, seat, b.discard, AreaType.DISCARD, args.get("filter", {}))
    if not opts:
        return True
    ctx = SelectContext.TO_DECK if to_deck else SelectContext.TO_HAND
    pose(gs, seat, type=SelectType.CARD, context=ctx, options=opts,
         min_count=1, max_count=min(args["n"], len(opts)), effect_card=fr.source)
    return False


def op_opp_hand_trim_to(gs, fr, args) -> bool:
    """The OPPONENT picks their own exits, so they drain the replay hand-pick FIFO."""
    seat = fr.seat
    n = args.get("n", 3)
    victim = 1 - seat
    vb = gs.players[victim]
    if "answer" in fr.vars:
        picked = [vb.hand[o["index"]] for o in fr.vars.pop("answered_options")]
        fr.vars.pop("answer")
        for s in picked:
            vb.hand.remove(s)
            vb.discard.append(s)
            gs.move_card(s, AreaType.HAND, AreaType.DISCARD, seat=victim,
                         visible_to_owner=True, visible_to_opponent=True)
        gs.rng.hand_pick_expect(victim, picked)
        return True
    k = len(vb.hand) - n
    if k <= 0:
        return True
    pose(gs, victim, type=SelectType.CARD, context=SelectContext.DISCARD,
         options=[opt_card(AreaType.HAND, i, victim) for i in range(len(vb.hand))],
         min_count=k, max_count=k, effect_card=fr.source)
    return False


def op_gate_defender_attacks_coin(gs, fr, args) -> bool:
    """The GATE TURN's mover owns the flip. The fire path is UNPINNED — only arming is exercised."""
    defender = gs.players[1 - fr.seat].active
    if defender is not None:
        defender.attack_gate_turn = gs.turn + 1
    return True


def op_inflict_condition_active(gs, fr, args) -> bool:
    opp = 1 - fr.seat
    ob = gs.players[opp]
    if ob.active is None:
        return True
    _set_condition(gs, opp, args["condition"])
    return True


def op_discard_energy_attach_bench(gs, fr, args) -> bool:
    """A benched target is picked PER energy."""
    seat = fr.seat
    b = gs.players[seat]
    if args.get("maxVar") == "heads_count":
        cap = fr.vars.get("heads_count", 0)
        if cap <= 0 and "picked" not in fr.vars and "answer" not in fr.vars:
            return True
        args = dict(args, max=cap)
    if "picked" not in fr.vars:
        if "answer" not in fr.vars:
            opts = _zone_options(gs, seat, b.discard, AreaType.DISCARD,
                                 args.get("filter", {}))
            if not opts:  # skipped rider: NO tac bump, unlike the deck-search family
                return True
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
            if not opts:                      # empty bench: min_count 1 over [] would deadlock
                fr.vars["picked"] = []
                break
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
    """ONE target for all the picks, attached in answer order."""
    seat = fr.seat
    b = gs.players[seat]
    if "picked" not in fr.vars:
        if "answer" not in fr.vars:
            opts = _zone_options(gs, seat, b.discard, AreaType.DISCARD,
                                 args.get("filter", {}))
            if not opts:                      # nothing matching: min_count 1 would deadlock
                return True
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
        if not opts:                          # no legal recipient: the picks stay in the discard
            fr.vars.pop("picked", None)
            return True
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
    """The heal lands on the COUNT answer, before the opponent's target is picked."""
    from .options import _targets, numbers
    seat = fr.seat
    opp = 1 - seat
    if "src" not in fr.vars:
        if "answer" not in fr.vars:
            opts = [opt_card(area, idx, seat) for area, idx, p in _targets(gs, seat)
                    if p.hp < p.max_hp]
            if not opts:                      # no damaged body: min_count 1 would deadlock
                return True
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
            if n_max <= 1:  # a FORCED count is never posed AND does not bump tac
                n = n_max
            else:
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
        opts = [opt_card(area, idx, opp) for area, idx, _p in _targets(gs, opp)
                if not (area == int(AreaType.BENCH)
                        and stadium_def(gs).get("benchCounterShield"))]
        # Battle Cage: benched destinations excluded (UNPINNED shape); Adrena-Brain's
        # move is ability-sourced counter placement, squarely in the shield's text
        if not opts:                          # no legal destination: the heal (already applied
            fr.vars.pop("count", None)        # on the count answer) stands, the move is skipped
            fr.vars.pop("src", None)
            return True
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
    """The rest go to the deck BOTTOM in looking order, with NO shuffle."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        n = min(args.get("n", 2), len(b.deck))
        gs.looking = []
        gs.looking_owner = seat
        for s in gs.rng.look_bind(seat, b.deck, n):
            b.deck.remove(s)
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
    for s in picked:
        gs.looking.remove(s)
        b.hand.append(s)
        gs.move_card(s, AreaType.LOOKING, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=False)
    for s in list(gs.looking):  # the rest in looking order to the deck BOTTOM, or to DISCARD; no shuffle either way
        gs.looking.remove(s)
        if args.get("rest") == "discard":
            b.discard.append(s)
            gs.move_card(s, AreaType.LOOKING, AreaType.DISCARD, seat=seat,
                         visible_to_owner=True,
                         visible_to_opponent=True)
        else:
            b.deck.insert(0, s)
            gs.move_card(s, AreaType.LOOKING, AREA_DECK_BOTTOM, seat=seat,
                         visible_to_owner=True, visible_to_opponent=False)
    gs.looking = None
    gs.looking_owner = -1
    return True


def op_deck_to_hand_buckets(gs, fr, args) -> bool:
    """A DECLINED bucket does NOT abort the rest. UNPINNED beyond bucket 1."""
    seat = fr.seat
    b = gs.players[seat]
    v = fr.vars
    while True:
        bi = v.setdefault("bucket_i", 0)
        if bi >= len(args["buckets"]):
            v.pop("bucket_i", None)
            if b.deck:
                _shuffle(gs, seat)
            return True
        if "answer" not in v:
            opts = _zone_options(gs, seat, b.deck, AreaType.DECK,
                                 args["buckets"][bi].get("filter", {}))
            if not opts:
                gs.turn_action_count += 1
                v["bucket_i"] = bi + 1
                continue
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_HAND,
                 options=opts, min_count=0, max_count=1,
                 deck_listing=list(b.deck), effect_card=fr.source)
            return False
        picked = [b.deck[o["index"]] for o in v.pop("answered_options")]
        v.pop("answer")
        for s in picked:
            b.deck.remove(s)
            b.hand.append(s)
            gs.move_card(s, AreaType.DECK, AreaType.HAND, seat=seat,
                         visible_to_owner=True, visible_to_opponent=True)
        v["bucket_i"] = bi + 1


def op_deck_to_hand_either_or(gs, fr, args) -> bool:
    """A b-match ends the search; an a-match re-poses over the a-filter only. UNPINNED."""
    seat = fr.seat
    b = gs.players[seat]
    v = fr.vars
    a, bb = args["a"], args["b"]
    while True:
        taken = v.setdefault("taken_a", 0)
        if v.get("done") or taken >= a.get("n", 2):
            v.pop("taken_a", None)
            v.pop("done", None)
            if b.deck:
                _shuffle(gs, seat)
            return True
        first = taken == 0
        flt = {"anyOf": [a["filter"], bb["filter"]]} if first else a["filter"]
        if "answer" not in v:
            opts = _zone_options(gs, seat, b.deck, AreaType.DECK, flt)
            if not opts:
                gs.turn_action_count += 1
                v["done"] = True
                continue
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_HAND,
                 options=opts, min_count=0, max_count=1,
                 deck_listing=list(b.deck), effect_card=fr.source)
            return False
        answered = v.pop("answered_options")
        v.pop("answer")
        if not answered:
            v["done"] = True
            continue
        s = b.deck[answered[0]["index"]]
        b.deck.remove(s)
        b.hand.append(s)
        gs.move_card(s, AreaType.DECK, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
        if first and _card_matches(gs, s, bb["filter"]) \
                and not _card_matches(gs, s, a["filter"]):
            v["done"] = True     # the 1-of-b branch consumes the whole search
        else:
            v["taken_a"] = taken + 1


def op_look_energy_attach_choose(gs, fr, args) -> bool:
    """The pick is over the LOOKING indexes only; the rest return in looking order."""
    from .options import _targets
    seat = fr.seat
    b = gs.players[seat]
    v = fr.vars

    def _finish():
        for s in list(gs.looking or []):
            gs.looking.remove(s)
            b.deck.append(s)
            gs.move_card(s, AreaType.LOOKING, AreaType.DECK, seat=seat,
                         visible_to_owner=True, visible_to_opponent=False)
        gs.looking = None
        gs.looking_owner = -1
        _shuffle(gs, seat)
        return True

    if "picked" not in v:
        if "answer" not in v:
            n = min(args.get("n", 6), len(b.deck))
            if n == 0:
                return True
            gs.looking = []
            gs.looking_owner = seat
            for s in gs.rng.look_bind(seat, b.deck, n):
                b.deck.remove(s)
                gs.looking.append(s)
                gs.move_card(s, AreaType.DECK, AreaType.LOOKING, seat=seat,
                             visible_to_owner=True, visible_to_opponent=False)
            opts = [opt_card(AreaType.LOOKING, k, seat)
                    for k, s in enumerate(gs.looking)
                    if _card_matches(gs, s, args.get("filter", {}))]
            if not opts:
                gs.turn_action_count += 1  # skipped ask, the deck-search convention (UNPINNED edge)
                return _finish()              # (UNPINNED edge — no matchless look
            pose(gs, seat, type=SelectType.CARD,
                 context=SelectContext.ATTACH_TO, options=opts,
                 min_count=0, max_count=1, effect_card=fr.source)
            return False
        answered = v.pop("answered_options")
        v.pop("answer")
        if not answered:                      # declined: everything returns
            return _finish()
        v["picked"] = gs.looking[answered[0]["index"]]
    energy = v["picked"]
    if "answer" not in v:
        opts = [opt_card(area, idx, seat) for area, idx, _p in _targets(gs, seat)]
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_FROM,
             options=opts, min_count=1, max_count=1,
             context_card=energy, effect_card=fr.source)
        return False
    t_o = v.pop("answered_options")[0]
    v.pop("answer")
    v.pop("picked")
    from .turn import _target_of
    target = _target_of(gs, seat, t_o["area"], t_o["index"])
    gs.looking.remove(energy)
    target.energy.append(energy)
    gs.note_attach(energy)
    gs.emit({"type": int(LogType.ATTACH), "playerIndex": seat,
             "cardId": gs.card_id(energy), "serial": energy,
             "cardIdTarget": gs.card_id(target.top), "serialTarget": target.top})
    return _finish()


def op_draw_then_shuffle_self_in(gs, fr, args) -> bool:
    """Stack top-first, energies LIFO. ``n: 0`` shuffles unconditionally."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" in fr.vars:
        o = fr.vars.pop("answered_options")[0]
        fr.vars.pop("answer")
        p = b.bench.pop(o["index"])
        b.active = p
        p.moved_active_turn = gs.turn
        gs.move_card(p.top, AreaType.BENCH, AreaType.ACTIVE, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
        return True
    n = args.get("n", 3)
    drew = 0
    for _ in range(n):
        if gs.draw(seat) is not None:
            drew += 1
    if n and not drew:
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
    for k, s in enumerate(reversed(me.stack)):  # top from its own zone, lower stack cards from PRE_EVOLUTION
        area = from_area if k == 0 else AreaType.PRE_EVOLUTION
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
    """A SILENT this-turn marker — the play logs nothing but PLAY; damage.py applies it."""
    mod = {"bonus": args["bonus"]}
    if "attackerEnergyType" in args:
        mod["attackerEnergyType"] = args["attackerEnergyType"]
    if args.get("defenderExOnly"):
        mod["defenderExOnly"] = True
    gs.turn_markers.setdefault("damage_bonus", []).append(mod)
    return True


def op_deck_take_sequence_and_shuffle(gs, fr, args) -> bool:
    """Each pick gets a FRESH deck listing; ONE shuffle at the end."""
    seat = fr.seat
    b = gs.players[seat]
    picks = args["picks"]
    stage = fr.vars.get("stage", 0)
    if "answer" in fr.vars:
        for s in [b.deck[o["index"]] for o in fr.vars.pop("answered_options")]:
            b.deck.remove(s)
            b.hand.append(s)
            gs.move_card(s, AreaType.DECK, AreaType.HAND, seat=seat,
                         visible_to_owner=True, visible_to_opponent=True)
        fr.vars.pop("answer")
        stage = fr.vars["stage"] = stage + 1
    while stage < len(picks):
        p = picks[stage]
        opts = _zone_options(gs, seat, b.deck, AreaType.DECK, p.get("filter", {}))
        if not opts and p.get("min", 0) == 0:  # empty optional stage: never posed, but the skipped ask still bumps tac
            gs.turn_action_count += 1
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
    """TWO sequential max-1 picks — native never poses max 2. A whiffed first pick ends the effect."""
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
            if not opts:
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
    """The energy bounce happens only if damage was ACTUALLY healed."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        from .options import _targets
        opts = [opt_card(area, idx, seat) for area, idx, p in _targets(gs, seat)
                if gs.stat(p.top).megaEx and p.hp < p.max_hp]
        if not opts:                          # no damaged mega: min_count 1 would deadlock
            return True
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
    """``fromBottom`` reads the BOTTOM n instead, bottom-most first."""
    seat = fr.seat
    b = gs.players[seat]
    if "answer" not in fr.vars:
        n = min(args.get("n", 7), len(b.deck))
        gs.looking = []
        gs.looking_owner = seat
        for s in gs.rng.look_bind(seat, b.deck, n,
                                  from_bottom=bool(args.get("fromBottom"))):
            b.deck.remove(s)
            gs.looking.append(s)
            gs.move_card(s, AreaType.DECK, AreaType.LOOKING, seat=seat,
                         visible_to_owner=True, visible_to_opponent=False)
        opts = _zone_options(gs, seat, gs.looking, AreaType.LOOKING,
                             args.get("filter", {}))
        if not opts:  # no match among the looked cards: never posed, everything returns and shuffles
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
    for s in picked:
        gs.looking.remove(s)
        b.hand.append(s)
        gs.move_card(s, AreaType.LOOKING, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
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
    """Targets INCLUDE mons that entered play this turn. Evolve log only, no move log."""
    seat = fr.seat
    b = gs.players[seat]
    if "evo" not in fr.vars:
        if "answer" not in fr.vars:
            names = {gs.stat(p.top).name for p in gs.in_play(seat)}
            opts = [opt_card(AreaType.DECK, i, seat) for i, s in enumerate(b.deck)
                    if gs.stat(s).cardType == CardType.POKEMON
                    and not gs.stat(s).skills
                    and gs.stat(s).evolvesFrom in names]
            if not opts:  # empty optional search: never posed, but the skipped ask still bumps tac
                gs.turn_action_count += 1
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


def op_heal_active(gs, fr, args) -> bool:
    seat = fr.seat
    me = gs.players[seat].active
    if me is None:
        return True
    healed = min(args["amount"], me.max_hp - me.hp)
    me.hp += healed
    gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": seat,
             "cardId": gs.card_id(me.top), "serial": me.top,
             "value": healed, "putDamageCounter": False})
    return True


def op_end_turn_after(gs, fr, args) -> bool:
    gs.turn_markers["end_turn_after_play"] = True
    return True


def op_hand_energy_attach_choose(gs, fr, args) -> bool:
    """Skips SILENTLY when the hand has no match."""
    from .options import _targets
    seat = fr.seat
    b = gs.players[seat]
    if "picked" not in fr.vars:
        if "answer" not in fr.vars:
            opts = _zone_options(gs, seat, b.hand, AreaType.HAND,
                                 args.get("filter", {}))
            if not opts:
                return True
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_TO,
                 options=opts, min_count=1, max_count=1, effect_card=fr.source)
            return False
        fr.vars["picked"] = b.hand[fr.vars.pop("answered_options")[0]["index"]]
        fr.vars.pop("answer")
    energy = fr.vars["picked"]
    if args.get("holderSelf"):
        # Teal Dance attaches to THIS Pokémon: no holder select, the ability's own mon (fr.source) is the
        # target.
        target = next(p for p in gs.in_play(seat) if p.top == fr.source)
    else:
        if "answer" not in fr.vars:
            opts = [opt_card(area, idx, seat) for area, idx, p in _targets(gs, seat)
                    if _card_matches(gs, p.top, args.get("targetFilter", {}))]
            if not opts:
                return True
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_FROM,
                 options=opts, min_count=1, max_count=1,
                 context_card=None if args.get("targetContextCard") is False else energy,
                 effect_card=fr.source)
            return False
        t_o = fr.vars.pop("answered_options")[0]
        fr.vars.pop("answer")
        from .turn import _target_of
        target = _target_of(gs, seat, t_o["area"], t_o["index"])
    fr.vars.pop("picked")
    b.hand.remove(energy)
    target.energy.append(energy)
    gs.note_attach(energy)
    gs.emit({"type": int(LogType.ATTACH), "playerIndex": seat,
             "cardId": gs.card_id(energy), "serial": energy,
             "cardIdTarget": gs.card_id(target.top), "serialTarget": target.top})
    for _ in range(args.get("thenDraw", 0)):
        gs.draw(seat)
    return True


def op_move_energy_own(gs, fr, args) -> bool:
    """Source EXCLUDED from the destinations; the moved energy KEEPS its attach tick. Seeded."""
    from .options import _targets
    seat = fr.seat
    if "moving" not in fr.vars:
        if "answer" not in fr.vars:
            entries = []
            for area, idx, p in _targets(gs, seat):
                for k, s in enumerate(p.energy):
                    if gs.stat(s).cardType != CardType.BASIC_ENERGY:
                        continue
                    entries.append((gs.attach_seq.get(s, 0),
                                    {"type": int(OptionType.ENERGY_CARD),
                                     "area": area, "index": idx,
                                     "playerIndex": seat, "energyIndex": k}))
            entries.sort(key=lambda e: e[0])
            opts = [o for _t, o in entries]
            if not opts:
                return True
            pose(gs, seat, type=SelectType.ATTACHED_CARD,
                 context=SelectContext.SWITCH_ENERGY_CARD, options=opts,
                 min_count=1, max_count=1, effect_card=fr.source)
            return False
        fr.vars["moving"] = fr.vars.pop("answered_options")[0]
        fr.vars.pop("answer")
    src_o = fr.vars["moving"]
    from .turn import _target_of
    if "answer" not in fr.vars:
        moving_serial = _target_of(gs, seat, src_o["area"],
                                   src_o["index"]).energy[src_o["energyIndex"]]
        opts = [opt_card(area, idx, seat) for area, idx, _p in _targets(gs, seat)
                if not (area == src_o["area"] and idx == src_o["index"])]
        if not opts:                          # lone body: min_count 1 over [] would deadlock
            fr.vars.pop("moving")
            return True
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_FROM,
             options=opts, min_count=1, max_count=1,
             context_card=moving_serial, effect_card=fr.source)
        return False
    t_o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    fr.vars.pop("moving")
    source = _target_of(gs, seat, src_o["area"], src_o["index"])
    target = _target_of(gs, seat, t_o["area"], t_o["index"])
    serial = source.energy[src_o["energyIndex"]]
    source.energy.remove(serial)
    # The move PRESERVES the original attach tick and the holder's list stays in global attach-tick
    # order, so the moved (older) energy lands BEFORE a newer pre-existing one.
    tick = gs.attach_seq.get(serial, 0)
    pos = next((k for k, s in enumerate(target.energy)
                if gs.attach_seq.get(s, 0) > tick), len(target.energy))
    target.energy.insert(pos, serial)
    gs.emit({"type": int(LogType.MOVE_ATTACHED), "playerIndex": seat,
             "cardId": gs.card_id(serial), "serial": serial,
             "cardIdBefore": gs.card_id(source.top), "serialBefore": source.top,
             "cardIdAfter": gs.card_id(target.top), "serialAfter": target.top})
    return True


def op_discard_energy_attach_choose(gs, fr, args) -> bool:
    """op_hand_energy_attach_choose from the DISCARD pile; a silent no-op when nothing matches."""
    from .options import _targets
    seat = fr.seat
    b = gs.players[seat]
    if "picked" not in fr.vars:
        if "answer" not in fr.vars:
            opts = _zone_options(gs, seat, b.discard, AreaType.DISCARD,
                                 args.get("filter", {}))
            if not opts:
                return True
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_TO,
                 options=opts, min_count=1, max_count=1, effect_card=fr.source)
            return False
        fr.vars["picked"] = b.discard[fr.vars.pop("answered_options")[0]["index"]]
        fr.vars.pop("answer")
    energy = fr.vars["picked"]
    if "answer" not in fr.vars:
        opts = [opt_card(area, idx, seat) for area, idx, p in _targets(gs, seat)
                if _card_matches(gs, p.top, args.get("targetFilter", {}))]
        if not opts:
            return True
        pose(gs, seat, type=SelectType.CARD, context=SelectContext.ATTACH_FROM,
             options=opts, min_count=1, max_count=1,
             context_card=energy, effect_card=fr.source)
        return False
    t_o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    fr.vars.pop("picked")
    from .turn import _target_of
    target = _target_of(gs, seat, t_o["area"], t_o["index"])
    b.discard.remove(energy)
    target.energy.append(energy)
    gs.note_attach(energy)
    gs.emit({"type": int(LogType.ATTACH), "playerIndex": seat,
             "cardId": gs.card_id(energy), "serial": energy,
             "cardIdTarget": gs.card_id(target.top), "serialTarget": target.top})
    return True

def op_discard_tools_in_play(gs, fr, args) -> bool:
    """Each pick moves the tool to its OWNER's discard, REVERSING any HP bonus exactly."""
    seat = fr.seat
    entries = []                                   # (owner, area, index, toolIndex)
    for owner in (seat, 1 - seat):
        b = gs.players[owner]
        rows = ([(int(AreaType.ACTIVE), 0, b.active)] if b.active is not None else []) + \
            [(int(AreaType.BENCH), i, p) for i, p in enumerate(b.bench)]
        for area, idx, p in rows:
            for ti in range(len(p.tools)):
                entries.append((owner, area, idx, ti))
    if not entries:                                # no tools -> silent no-op
        return True
    if "answer" not in fr.vars:
        options = [{"type": int(OptionType.TOOL_CARD), "area": area, "index": idx,
                    "playerIndex": owner, "toolIndex": ti}
                   for owner, area, idx, ti in entries]
        pose(gs, seat, type=SelectType.ATTACHED_CARD,
             context=SelectContext.DISCARD_TOOL_CARD, options=options,
             effect_card=fr.source, min_count=1, max_count=min(2, len(options)))
        return False
    answered = fr.vars.pop("answered_options")
    fr.vars.pop("answer")
    picks = []                                     # resolve serials before mutating
    for o in answered:
        b = gs.players[o["playerIndex"]]
        p = b.active if o["area"] == int(AreaType.ACTIVE) else b.bench[o["index"]]
        picks.append((o["playerIndex"], p, p.tools[o["toolIndex"]]))
    for owner, p, s in picks:
        tdef = (def_for(gs.card_id(s)) or {}).get("tool", {})
        bonus = tdef.get("hpBonus", 0)
        hb_flt = tdef.get("hpBonusHolder")
        if bonus and (hb_flt is None or _card_matches(gs, p.top, hb_flt)):
            p.max_hp -= bonus  # the exact inverse of the attach bonus; preserves current damage
            p.hp -= bonus
        p.tools.remove(s)
        gs.players[owner].discard.append(s)
        gs.move_card(s, AreaType.TOOL, AreaType.DISCARD, seat=owner,
                     visible_to_owner=True, visible_to_opponent=True)
    return True

def op_first_effect_choose(gs, fr, args) -> bool:
    """UNPINNED — no capture deck played a Choose-1 supporter."""
    if "answer" not in fr.vars:
        pose(gs, fr.seat, type=SelectType.YES_NO, context=SelectContext.FIRST_EFFECT,
             options=yes_no(), effect_card=fr.source)
        return False
    o = fr.vars.pop("answered_options")[0]
    fr.vars.pop("answer")
    branch = args["first"] if o["type"] == int(OptionType.YES) else args["second"]
    fr.program = fr.program[:fr.pc + 1] + list(branch) + fr.program[fr.pc + 1:]
    return True

def op_opp_hand_reveal_discard_multi(gs, fr, args) -> bool:
    """Chosen exits leave FIRST, then the rest return in ORIGINAL order. No match = reveal only."""
    victim = 1 - fr.seat
    vb = gs.players[victim]
    flt = args.get("filter", {})
    n = args.get("max", 2)
    if "answer" not in fr.vars:
        serials = list(vb.hand)
        if not serials:
            return True
        for s in serials:
            gs.move_card(s, AreaType.HAND, AreaType.LOOKING, seat=victim,
                         visible_to_owner=False, visible_to_opponent=True)
        gs.rng.hand_pick_expect(victim, serials)
        vb.hand.clear()
        gs.looking = list(serials)
        gs.looking_owner = fr.seat
        match_idx = [i for i, s in enumerate(serials) if _card_matches(gs, s, flt)]
        if match_idx:
            cap = min(n, len(match_idx))
            pose(gs, fr.seat, type=SelectType.CARD, context=SelectContext.DISCARD,
                 options=[opt_card(AreaType.LOOKING, i, victim) for i in match_idx],
                 min_count=1, max_count=cap, effect_card=fr.source)
            return False
        gs.looking = None
        gs.looking_owner = -1
        for s in serials:
            vb.hand.append(s)
            gs.move_card(s, AreaType.LOOKING, AreaType.HAND, seat=victim,
                         visible_to_owner=True, visible_to_opponent=True)
        return True
    idxs = [o["index"] for o in fr.vars.pop("answered_options")]
    fr.vars.pop("answer")
    serials = list(gs.looking or [])
    chosen = [serials[i] for i in idxs]
    gs.looking = None
    gs.looking_owner = -1
    for s in chosen:
        vb.discard.append(s)
        gs.move_card(s, AreaType.LOOKING, AreaType.DISCARD, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    for s in serials:
        if s in chosen:
            continue
        vb.hand.append(s)
        gs.move_card(s, AreaType.LOOKING, AreaType.HAND, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    return True

def op_both_bottom_hand_coin_draw(gs, fr, args) -> bool:
    """Coins bind PER OWNER, and the opponent's are recorded in the OPPONENT's own window."""
    if not fr.vars.get("bottomed"):
        moved = 0
        for seat in (fr.seat, 1 - fr.seat):
            b = gs.players[seat]
            for s in list(b.hand):
                b.hand.remove(s)
                b.deck.insert(0, s)
                gs.move_card(s, AreaType.HAND, AREA_DECK_BOTTOM, seat=seat,
                             visible_to_owner=False, visible_to_opponent=False)
                moved += 1
        fr.vars["bottomed"] = True
        fr.vars["any_moved"] = moved > 0
    if not fr.vars.get("any_moved"):
        return True
    heads_n = args.get("heads", 6)
    tails_n = args.get("tails", 3)
    for seat in (fr.seat, 1 - fr.seat):
        head = gs.coin_flip(seat)
        for _ in range(heads_n if head else tails_n):
            gs.draw(seat)
    return True

def op_opp_hand_reveal_choose_filtered(gs, fr, args) -> bool:
    """With NO match the ask is SKIPPED but still bumps tac."""
    victim = 1 - fr.seat
    vb = gs.players[victim]
    flt = args.get("filter", {"energy": True})
    to_bottom = args.get("to", "deckBottom") == "deckBottom"
    if "answer" not in fr.vars:
        serials = list(vb.hand)
        for s in serials:
            gs.move_card(s, AreaType.HAND, AreaType.LOOKING, seat=victim,
                         visible_to_owner=False, visible_to_opponent=True)
        gs.rng.hand_pick_expect(victim, serials)
        matches = [i for i, s in enumerate(serials) if _card_matches(gs, s, flt)]
        if not matches:                       # skipped ask still bumps tac; round-trip back
            for s in serials:
                gs.move_card(s, AreaType.LOOKING, AreaType.HAND, seat=victim,
                             visible_to_owner=True, visible_to_opponent=True)
            gs.turn_action_count += 1
            return True
        vb.hand.clear()
        gs.looking = list(serials)
        gs.looking_owner = fr.seat
        ctx = SelectContext.TO_DECK_BOTTOM if to_bottom else SelectContext.DISCARD
        pose(gs, fr.seat, type=SelectType.CARD, context=ctx,
             options=[opt_card(AreaType.LOOKING, i, victim) for i in matches],
             effect_card=fr.source)
        return False
    idx = fr.vars.pop("answered_options")[0]["index"]
    fr.vars.pop("answer")
    serials = list(gs.looking or [])
    chosen = serials[idx]
    gs.looking = None
    gs.looking_owner = -1
    if to_bottom:
        vb.deck.insert(0, chosen)             # deck lists bottom-first: bottom = index 0
        gs.move_card(chosen, AreaType.LOOKING, _AREA_DECK_BOTTOM, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    else:
        vb.discard.append(chosen)
        gs.move_card(chosen, AreaType.LOOKING, AreaType.DISCARD, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    for s in serials:
        if s == chosen:
            continue
        vb.hand.append(s)
        gs.move_card(s, AreaType.LOOKING, AreaType.HAND, seat=victim,
                     visible_to_owner=True, visible_to_opponent=True)
    return True

def op_curse_blast(gs, fr, args) -> bool:
    """The source is KO'd SILENTLY at activation; its frame stays alive across the prize pick."""
    from .options import _targets
    from .turn import _discard_in_play, _prize_value
    from .schema import ResultReason
    seat = fr.seat
    opp = 1 - seat
    ob = gs.players[opp]
    # phase 2: the opponent's prize pick for the self-KO (frame stays alive -> MAIN resumes)
    if fr.vars.get("await_prize"):
        o = fr.vars.pop("answered_options")[0]
        fr.vars.pop("answer")
        serial = ob.prize[o["index"]]
        take = getattr(gs.rng, "prize_take", None)
        if take is not None:
            live = serial if serial in ob.prize else ob.prize[0]
            serial = take(opp, live, deck=ob.deck, prize=ob.prize)
        ob.prize.remove(serial)
        ob.hand.append(serial)
        gs.move_card(serial, AreaType.PRIZE, AreaType.HAND, seat=opp,
                     visible_to_owner=True, visible_to_opponent=False)
        if not ob.prize:
            gs.set_result(opp, ResultReason.PRIZES)
        return True
    # phase 1: the source is Knocked Out on activation (hp 0, silent), then the target is chosen
    if "answer" not in fr.vars:
        src = next(p for p in gs.in_play(seat) if p.top == fr.source)
        src.hp = 0
        opts = [opt_card(area, idx, opp) for area, idx, _p in _targets(gs, opp)]
        if opts:
            pose(gs, seat, type=SelectType.CARD, context=SelectContext.DAMAGE_COUNTER,
                 options=opts, min_count=1, max_count=1, effect_card=fr.source)
            return False
        fr.vars["answer"] = []
        fr.vars["answered_options"] = []
    o_list = fr.vars.pop("answered_options")
    fr.vars.pop("answer")
    if o_list:
        o = o_list[0]
        n = args.get("counters", 1) * 10
        dest = ob.active if o["area"] == int(AreaType.ACTIVE) else ob.bench[o["index"]]
        dest.hp = max(0, dest.hp - n)
        gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": opp,
                 "cardId": gs.card_id(dest.top), "serial": dest.top,
                 "value": -n, "putDamageCounter": True})
    # self-KO: discard the source stack; the opponent claims its prize inline
    src = next(p for p in gs.in_play(seat) if p.top == fr.source)
    sb = gs.players[seat]
    from_bench = src is not sb.active
    pv = _prize_value(gs, src)
    _discard_in_play(gs, seat, src)
    if from_bench:
        sb.bench.remove(src)
    else:
        sb.active = None
    if ob.prize:
        nprize = min(pv, len(ob.prize))
        opts = [opt_card(AreaType.PRIZE, i, opp) for i in range(len(ob.prize))]
        fr.vars["await_prize"] = True
        pose(gs, opp, type=SelectType.CARD, context=SelectContext.TO_HAND,
             options=opts, min_count=nprize, max_count=nprize)
        return False
    return True


OPS = {
    "xDiscardEnergyAttachChoose": op_discard_energy_attach_choose,
    "xDiscardToolsInPlay": op_discard_tools_in_play,
    "xFirstEffectChoose": op_first_effect_choose,
    "xOppHandRevealDiscardMulti": op_opp_hand_reveal_discard_multi,
    "xBothBottomHandCoinDraw": op_both_bottom_hand_coin_draw,
    "xOppHandRevealChooseFiltered": op_opp_hand_reveal_choose_filtered,
    "xCurseBlast": op_curse_blast,
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
    "xDeckToHandBuckets": op_deck_to_hand_buckets,
    "xDeckToHandEitherOr": op_deck_to_hand_either_or,
    "xLookEnergyAttachChoose": op_look_energy_attach_choose,
    "xSelfNoWeaknessNextTurn": op_self_no_weakness_next_turn,
    "xCounterOppActiveScaled": op_counter_opp_active_scaled,
    "xDrawThenShuffleSelfIn": op_draw_then_shuffle_self_in,
    "xOrderTriggers": op_order_triggers,
    "xBenchCounterDamage": op_bench_counter_damage,
    "xChooseBenchDamage": op_choose_bench_damage,
    "xMoveDamageCounters": op_move_damage_counters,
    "xDiscardEnergyAttachBench": op_discard_energy_attach_bench,
    "xInflictConditionActive": op_inflict_condition_active,
    "xDiscardEnergyAttachOneTarget": op_discard_energy_attach_one_target,
    "xChooseAnyDamage": op_choose_any_damage,
    # M4 pool-fan-out ops (seeded; micro-trace verification flips them to pinned)
    "xDamageSelf": op_damage_self,
    "xDamageOwnBenchEach": op_damage_own_bench_each,
    "xHealSelf": op_heal_self,
    "xHealEach": op_heal_each,
    "xHealChoose": op_heal_choose,
    "xDiscardOwnEnergy": op_discard_own_energy,
    "xDiscardAllOwnEnergy": op_discard_all_own_energy,
    "xInflictConditionSelf": op_inflict_condition_self,
    "xOpponentSwitches": op_opponent_switches,
    "xMill": op_mill,
    "xEotAttachEnergyFromDiscard": op_eot_attach_energy_from_discard,
    "xShuffleDiscardEnergyToDeck": op_shuffle_discard_energy_to_deck,
    "xDiscardHandDraw": op_discard_hand_draw,
    "xTakeLessNextTurn": op_take_less_next_turn,
    "xProtectNextTurn": op_protect_next_turn,
    "xReduceDefenderNextTurn": op_reduce_defender_next_turn,
    "xLockDefenderAttacks": op_lock_defender_attacks,
    "xDeckEvolveSelfAndShuffle": op_deck_evolve_self_and_shuffle,
    "xMayAsk": op_may_ask,
    "xDeckEnergyAttach": op_deck_energy_attach,
    "xDiscardEnergyAttachSelf": op_discard_energy_attach_self,
    "xSelfReturnToHand": op_self_return_to_hand,
    "xDistributeCounters": op_distribute_counters,
    "xFailUnlessHeads": op_fail_unless_heads,
    "xBonusIfHeads": op_bonus_if_heads,
    "xCoinsCount": op_coins_count,
    "xCoinsUntilTails": op_coins_until_tails,
    "xDamagePerHeads": op_damage_per_heads,
    "xBonusPerHeads": op_bonus_per_heads,
    "xMoveEnergyOwn": op_move_energy_own,
    "xHandEnergyAttachChoose": op_hand_energy_attach_choose,
    "xHealActive": op_heal_active,
    "xEndTurnAfterPlay": op_end_turn_after,
    "xOppHandDiscardRandom": op_opp_hand_discard_random,
    "xOppHandShuffleInRandom": op_opp_hand_shuffle_in_random,
    "xOppHandReveal": op_opp_hand_reveal,
    "xOppHandRevealChoose": op_opp_hand_reveal_choose,
    "xDamagePerRevealed": op_damage_per_revealed,
    "xDeckEnergyAttachDistribute": op_deck_energy_attach_distribute,
    "ifTails": op_if_tails,
    "xSkip": op_skip,
    "xBonusIfAllHeads": op_bonus_if_all_heads,
    "xDamagePerTails": op_damage_per_tails,
    "xDamageSelfIfNoHeads": op_damage_self_if_no_heads,
    "xSelfLockAllNextTurn": op_self_lock_all_next_turn,
    "xKnockOutActive": op_knock_out_active,
    "xKnockOutChoose": op_knock_out_choose,
    "xCoinDamageEachOpp": op_coin_damage_each_opp,
    "xShuffleInPlayIntoDeckChoose": op_shuffle_in_play_into_deck_choose,
    "xGateDefenderAttacksCoin": op_gate_defender_attacks_coin,
    "xIfHeadsCountBelow": op_if_heads_count_below,
    "xChooseConditionInflict": op_choose_condition_inflict,
    "xRareCandyEvolve": op_rare_candy_evolve,
    "xBothHandTrimTo": op_both_hand_trim_to,
    "xOppHandTrimTo": op_opp_hand_trim_to,
    "xPickDiscard": op_pick_discard,
    "xDeckAttachPerBench": op_deck_attach_per_bench,
    "xDeckEvolvePerBench": op_deck_evolve_per_bench,
    "xDeckEvolveChooseAndShuffle": op_deck_evolve_choose_and_shuffle,
    "xDeckDistinctBasicEnergyToHand": op_deck_distinct_basic_energy_to_hand,
    "xDiscardEnergyCountScaled": op_discard_energy_count_scaled,
    "xDiscardHandCountScaled": op_discard_hand_count_scaled,
    "xDamagePerDiscarded": op_damage_per_discarded,
    "xBonusPerDiscarded": op_bonus_per_discarded,
    "xDiscardStadium": op_discard_stadium,
}
