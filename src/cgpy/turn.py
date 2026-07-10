"""Game flow: setup/mulligan machine, turn loop, attack/KO/promotion (ADR-0050, M1 scope).

The setup protocol implements exactly the sequences decoded from native traces
(docs/pyeng/determinism.md §5):

- silent pre-game shuffle; IS_FIRST to seat 0 before dealing
- deal 7/7 in firstPlayer order
- PAIRED check-redraw cycles while both players lack a Basic (checks logged as a round in fp
  order, then redraws in fp order); a player checking True is posed SetupActive immediately
- when exactly one player remains unresolved, they enter the SOLO cycle: ONE Mulligan YesNo
  posed BEFORE their next check, then automatic check/redraw rounds until True
- prizes: dealt right after a player's active placement if the other is still unresolved,
  else batched fp-order once both actives are placed
- mulligan compensation: net difference only — the player with fewer mulligans is posed
  DrawCount 0..diff (nobody on a tie); compensation draws precede TURN_START
- SetupBench per seat (fp order) only when the hand holds a benchable Basic
- actives reveal (render-state only, no log) at first TURN_START

Turn loop (M1 vanilla): MAIN dispatch for PLAY-basic / ATTACH / EVOLVE / RETREAT (energy
discards then switch) / ATTACK (damage → KO → prizes → promotion) / END; deck-out at turn
start; win/draw adjudication incl. simultaneous-win=DRAW.
"""
from __future__ import annotations

from .options import (main_options, numbers, opt_card, pose, pose_main,
                      setup_active_options, setup_bench_options, yes_no)
from .schema import (AreaType, LogType, OptionType, ResultReason, SelectContext,
                     SelectType)
from .state import GameState, PokemonInPlay


# ---------------------------------------------------------------------------- helpers

def _order(gs: GameState) -> list[int]:
    fp = gs.first_player if gs.first_player >= 0 else 0
    return [fp, 1 - fp]


def _check(gs: GameState, seat: int) -> bool:
    """The HasBasicPokemon check counts BASICS ONLY (pinned: a hand holding just an
    Explosiveness starter still mulligans — trace ms_mirror_1001 f2), even though such
    starters ARE offered at SETUP_ACTIVE."""
    has = any(gs.db.is_basic_pokemon(gs.card_id(s)) for s in gs.players[seat].hand)
    gs.emit({"type": int(LogType.HAS_BASIC_POKEMON), "playerIndex": seat,
             "hasBasicPokemon": has})
    return has


def _redraw(gs: GameState, seat: int) -> None:
    """One mulligan round: reveal hand back to deck, shuffle, draw 7."""
    b = gs.players[seat]
    for serial in list(reversed(b.hand)):          # returned LIFO (pinned); revealed to both
        b.hand.remove(serial)
        b.deck.append(serial)
        gs.move_card(serial, AreaType.HAND, AreaType.DECK, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    gs.shuffle_deck(seat)
    for _ in range(7):
        gs.draw(seat)
    b.mulligans += 1


def _new_in_play(gs: GameState, serial: int) -> PokemonInPlay:
    hp = gs.stat(serial).hp
    return PokemonInPlay(stack=[serial], hp=hp, max_hp=hp,
                         entered_turn=max(gs.turn, 1))


def _deal_prizes(gs: GameState, seat: int) -> None:
    b = gs.players[seat]
    serials = gs.rng.prize_bind(seat, b.deck, 6)   # facedown: identity bound by the rng/oracle
    for serial in serials:
        b.deck.remove(serial)
        b.prize.append(serial)
        gs.move_card(serial, AreaType.DECK, AreaType.PRIZE, seat=seat,
                     visible_to_owner=False, visible_to_opponent=False)


# ---------------------------------------------------------------------------- setup

def start_game(gs: GameState) -> None:
    """Pre-game: silent shuffles, then IS_FIRST to seat 0 (pre-deal)."""
    for seat in (0, 1):
        gs.shuffle_deck(seat, log=False)           # frame-0 decks are already shuffled, unlogged
    gs.phase = "SETUP"
    gs.phase_data = {
        "stage": "is_first",
        "resolved": [None, None],       # None=unknown, True/False=last check outcome
        "checked_ever": [False, False],
        "placed": [False, False],
        "prized": [False, False],
        "bench_served": [False, False],
        "drawcount_done": False,
        "asked": [False, False],        # the one-time Mulligan YesNo per seat
    }
    pose(gs, 0, type=SelectType.YES_NO, context=SelectContext.IS_FIRST, options=yes_no())


def _setup_advance(gs: GameState) -> None:
    """The setup pass loop, reproducing the pinned native sequences exactly:

    per pass — (1) check each status-unknown player fp-order, posing the one-time Mulligan
    YesNo BEFORE a never-checked player's check when the other player is already True/placed;
    (2) pose SetupActive for checked-True unplaced players (prizes dealt on answer only if
    the other player is still unresolved); (3) redraw known-False players — and when such a
    player is the sole unresolved one with the other PLACED and they were never asked, the
    redraw happens FIRST and the Mulligan YesNo is posed right after it (before their next
    check). Once everyone is placed: batch undealt prizes fp-order, then DrawCount (net
    mulligan difference to the lower-count player), then SetupBench, then reveal + turn 1.
    """
    d = gs.phase_data
    order = _order(gs)

    while gs.pending is None and gs.result == -1:
        stage = d["stage"]

        if stage == "deal":
            for s in order:
                for _ in range(7):
                    gs.draw(s)
            d["stage"] = "cycle"

        elif stage == "cycle":
            # (1) checks for status-unknown players, with the never-checked ask gate.
            unknown = [s for s in order if not d["placed"][s] and d["resolved"][s] is None]
            progressed = False
            for s in unknown:
                hand_ids = [gs.card_id(x) for x in gs.players[s].hand]
                no_basic = not any(gs.db.is_basic_pokemon(c) for c in hand_ids)
                has_starter = any(gs.db.is_setup_starter(c) and not gs.db.is_basic_pokemon(c)
                                  for c in hand_ids)
                # The MULLIGAN YesNo is the keep-or-redraw choice for a basic-less hand
                # holding an Explosiveness-class starter (pinned: fires exactly then —
                # vanilla decks are never asked). YES = mulligan anyway; NO = keep the hand
                # and start the starter.
                if no_basic and has_starter:
                    d["mulligan_choice_seat"] = s
                    pose(gs, s, type=SelectType.YES_NO, context=SelectContext.MULLIGAN,
                         options=yes_no())
                    return
                d["resolved"][s] = _check(gs, s)
                progressed = True
            if progressed:
                continue

            # (2) placements for checked-True players.
            for s in order:
                if d["resolved"][s] is True and not d["placed"][s]:
                    pose(gs, s, type=SelectType.CARD,
                         context=SelectContext.SETUP_ACTIVE_POKEMON,
                         options=setup_active_options(gs, s))
                    return

            # (3) redraws for known-False players (with the post-redraw ask gate).
            falses = [s for s in order if d["resolved"][s] is False and not d["placed"][s]]
            if falses:
                for s in falses:
                    _redraw(gs, s)
                    d["resolved"][s] = None
                continue

            d["stage"] = "prizes"

        elif stage == "prizes":
            for s in order:
                if d["placed"][s] and not d["prized"][s]:
                    _deal_prizes(gs, s)
                    d["prized"][s] = True
            d["stage"] = "drawcount"

        elif stage == "drawcount":
            d["stage"] = "bench"
            if not d["drawcount_done"]:
                d["drawcount_done"] = True
                m0, m1 = gs.players[0].mulligans, gs.players[1].mulligans
                if m0 != m1:
                    low = 0 if m0 < m1 else 1
                    diff = abs(m0 - m1)
                    d["stage"] = "drawcount_wait"
                    pose(gs, low, type=SelectType.COUNT, context=SelectContext.DRAW_COUNT,
                         options=numbers(diff))
                    return

        elif stage == "bench":
            for s in order:
                if d["bench_served"][s]:
                    continue
                d["bench_served"][s] = True
                opts = setup_bench_options(gs, s)
                if opts:
                    room = gs.players[s].bench_max
                    pose(gs, s, type=SelectType.CARD,
                         context=SelectContext.SETUP_BENCH_POKEMON,
                         options=opts, min_count=0, max_count=min(len(opts), room))
                    return
                gs.turn_action_count += 1   # the skipped empty ask still bumps tac (pinned)
            d["stage"] = "reveal"

        elif stage == "reveal":
            for s in (0, 1):
                gs.players[s].active_facedown = False
            gs.phase = "TURN"
            begin_turn(gs, _order(gs)[0])
            return

        else:  # pragma: no cover - guarded stages pose selects and return
            raise AssertionError(f"unknown setup stage {stage}")


def _setup_apply(gs: GameState, indices: list[int]) -> None:
    d = gs.phase_data
    ctx = gs.pending.context
    seat = gs.pending.seat
    opts = gs.pending.options
    gs.pending = None

    if ctx == SelectContext.IS_FIRST:
        gs.first_player = seat if opts[indices[0]]["type"] == OptionType.YES else 1 - seat
        d["stage"] = "deal"

    elif ctx == SelectContext.MULLIGAN:
        s = d.get("mulligan_choice_seat", seat)
        if opts[indices[0]]["type"] == OptionType.YES:
            d["resolved"][s] = _check(gs, s)   # logs the failing check; the cycle redraws
        else:
            _check(gs, s)                      # keep the hand: start the Explosiveness card
            d["resolved"][s] = True

    elif ctx == SelectContext.SETUP_ACTIVE_POKEMON:
        b = gs.players[seat]
        serial = b.hand[opts[indices[0]]["index"]]
        b.hand.remove(serial)
        b.active = _new_in_play(gs, serial)
        b.active_facedown = True
        gs.move_card(serial, AreaType.HAND, AreaType.ACTIVE, seat=seat,
                     visible_to_owner=True, visible_to_opponent=False)
        d["placed"][seat] = True
        # Other player still unresolved -> this player's prizes go out now (pinned).
        other = 1 - seat
        if not (d["placed"][other] or d["resolved"][other]):
            _deal_prizes(gs, seat)
            d["prized"][seat] = True

    elif ctx == SelectContext.DRAW_COUNT:
        n = opts[indices[0]]["number"]
        for _ in range(n):
            gs.draw(seat)
        d["stage"] = "bench"

    elif ctx == SelectContext.SETUP_BENCH_POKEMON:
        b = gs.players[seat]
        serials = [b.hand[opts[i]["index"]] for i in indices]
        for serial in serials:
            b.hand.remove(serial)
            b.bench.append(_new_in_play(gs, serial))
            gs.move_card(serial, AreaType.HAND, AreaType.BENCH, seat=seat,
                         visible_to_owner=True, visible_to_opponent=False)

    else:
        raise AssertionError(f"setup got answer for unexpected context {ctx}")


# ---------------------------------------------------------------------------- turns

def begin_turn(gs: GameState, seat: int) -> None:
    gs.turn += 1
    gs.turn_action_count = 0
    gs.supporter_played = False
    gs.stadium_played = False
    gs.energy_attached = False
    gs.retreated = False
    # appearThisTurn derives from entered_turn vs the turn counter — nothing to clear.
    gs.emit({"type": int(LogType.TURN_START), "playerIndex": seat})
    if not gs.players[seat].deck:                  # deck-out: cannot draw at turn start
        gs.set_result(1 - seat, ResultReason.DECK_OUT)
        return
    gs.draw(seat)
    gs.phase = "TURN"
    gs.phase_data = {"seat": seat}
    pose_main(gs, seat)


def _end_turn(gs: GameState, seat: int) -> None:
    gs.emit({"type": int(LogType.TURN_END), "playerIndex": seat})
    _checkup(gs, seat)
    if gs.result == -1:
        begin_turn(gs, 1 - seat)


def _checkup(gs: GameState, ending_seat: int) -> None:
    """Pokemon Checkup skeleton (Poison -> Burn -> Asleep -> Paralyze). Vanilla M1: only the
    paralysis auto-recovery is live; condition sources arrive with the chain interpreter."""
    for seat in (ending_seat, 1 - ending_seat):
        b = gs.players[seat]
        if b.paralyzed and seat == ending_seat and b.paralyzed_since_turn < gs.turn:
            b.paralyzed = False
            if b.active:
                gs.emit({"type": int(LogType.PARALYZED), "playerIndex": seat,
                         "isRecover": True, "cardId": gs.card_id(b.active.top),
                         "serial": b.active.top})


def _discard_in_play(gs: GameState, seat: int, p: PokemonInPlay) -> None:
    """KO discard order (pinned): the Pokémon stack (top first) from its zone, then the
    attached energies in attach order, then tools."""
    b = gs.players[seat]
    from_pokemon = AreaType.ACTIVE if p is b.active else AreaType.BENCH
    for serial in list(reversed(p.stack)):
        b.discard.append(serial)
        gs.move_card(serial, from_pokemon, AreaType.DISCARD, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    for serial in list(reversed(p.energy)):    # LIFO, like the mulligan return (pinned)
        b.discard.append(serial)
        gs.move_card(serial, AreaType.ENERGY, AreaType.DISCARD, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
    for serial in p.tools:
        b.discard.append(serial)
        gs.move_card(serial, AreaType.TOOL, AreaType.DISCARD, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)


def _pose_prize_pick(gs: GameState, seat: int) -> None:
    """The winner of a KO picks facedown prize slot(s): CARD options over the PRIZE row."""
    b = gs.players[seat]
    opts = [opt_card(AreaType.PRIZE, i, seat) for i in range(len(b.prize))]
    pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_HAND, options=opts)


def _prize_value(gs: GameState, p: PokemonInPlay) -> int:
    stat = gs.stat(p.top)
    if stat.megaEx:
        return 3
    if stat.ex:
        return 2
    return 1


def _resolve_attack(gs: GameState, seat: int, attack_id: int) -> None:
    from .damage import attack_damage

    b, ob = gs.players[seat], gs.players[1 - seat]
    attacker, defender = b.active, ob.active
    gs.emit({"type": int(LogType.ATTACK), "playerIndex": seat,
             "cardId": gs.card_id(attacker.top), "serial": attacker.top,
             "attackId": attack_id})
    dmg = attack_damage(gs, attacker, gs.db.attacks[attack_id], defender)
    if dmg > 0:
        defender.hp = max(0, defender.hp - dmg)
        gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": 1 - seat,
                 "cardId": gs.card_id(defender.top), "serial": defender.top,
                 "value": -dmg, "putDamageCounter": False})

    if defender.hp <= 0:
        prizes = _prize_value(gs, defender)
        _discard_in_play(gs, 1 - seat, defender)
        ob.active = None
        gs.phase_data = {"seat": seat, "prizes_left": prizes, "await": "prize"}
        _pose_prize_pick(gs, seat)
        return

    _end_turn(gs, seat)


def _after_prizes_taken(gs: GameState, seat: int) -> None:
    """Post-KO adjudication once the winner finished picking prizes (pinned: reason 3
    outranks the prize win when the defender also cannot promote)."""
    b, ob = gs.players[seat], gs.players[1 - seat]
    i_won = not b.prize
    they_cant = ob.active is None and not ob.bench
    if i_won and they_cant:
        gs.set_result(2, ResultReason.PRIZES)          # simultaneous win = DRAW (SIM-DELTA)
        return
    if they_cant:
        gs.set_result(seat, ResultReason.NO_POKEMON)
        return
    if i_won:
        gs.set_result(seat, ResultReason.PRIZES)
        return
    gs.phase_data = {"seat": seat, "await": "promote"}
    opts = [opt_card(AreaType.BENCH, i, 1 - seat) for i in range(len(ob.bench))]
    pose(gs, 1 - seat, type=SelectType.CARD, context=SelectContext.TO_ACTIVE,
         options=opts)


def _turn_apply(gs: GameState, indices: list[int]) -> None:
    seat = gs.pending.seat
    ctx = gs.pending.context
    opts = gs.pending.options
    gs.pending = None
    b = gs.players[seat]

    if ctx == SelectContext.MAIN:
        o = opts[indices[0]]
        t = o["type"]
        if t == OptionType.END:
            _end_turn(gs, seat)
        elif t == OptionType.PLAY:
            serial = b.hand[o["index"]]
            stat = gs.stat(serial)
            if stat.cardType == 0:                        # a Basic to the bench
                b.hand.remove(serial)
                b.bench.append(_new_in_play(gs, serial))
                gs.emit({"type": int(LogType.PLAY), "playerIndex": seat,
                         "cardId": gs.card_id(serial), "serial": serial})
                pose_main(gs, seat)
            else:                                         # a trainer: run its chain program
                from .chain import UnsupportedCard, def_for, start_program
                cdef = def_for(gs.card_id(serial))
                if cdef is None or "play" not in cdef:
                    raise UnsupportedCard(f"card {gs.card_id(serial)} has no play program")
                b.hand.remove(serial)
                b.discard.append(serial)                  # trainers discard on play (pinned)
                gs.emit({"type": int(LogType.PLAY), "playerIndex": seat,
                         "cardId": gs.card_id(serial), "serial": serial})
                if stat.cardType == 3:
                    gs.supporter_played = True
                start_program(gs, seat, serial, cdef["play"])
        elif t == OptionType.ATTACH:
            serial = b.hand[o["index"]]
            target = _target_of(gs, seat, o["inPlayArea"], o["inPlayIndex"])
            b.hand.remove(serial)
            target.energy.append(serial)
            gs.energy_attached = True
            gs.emit({"type": int(LogType.ATTACH), "playerIndex": seat,
                     "cardId": gs.card_id(serial), "serial": serial,
                     "cardIdTarget": gs.card_id(target.top), "serialTarget": target.top})
            pose_main(gs, seat)
        elif t == OptionType.EVOLVE:
            serial = b.hand[o["index"]]
            target = _target_of(gs, seat, o["inPlayArea"], o["inPlayIndex"])
            old_top, old_max = target.top, target.max_hp
            b.hand.remove(serial)
            target.stack.append(serial)
            new_max = gs.stat(serial).hp
            target.max_hp = new_max
            target.hp += new_max - old_max
            target.entered_turn = gs.turn
            if target is b.active:                  # evolving clears special conditions
                b.poisoned = b.burned = b.asleep = b.paralyzed = b.confused = False
            gs.emit({"type": int(LogType.EVOLVE), "playerIndex": seat,
                     "cardId": gs.card_id(serial), "serial": serial,
                     "cardIdTarget": gs.card_id(old_top), "serialTarget": old_top})
            pose_main(gs, seat)
        elif t == OptionType.RETREAT:
            gs.retreated = True                 # set at choice time, not completion (pinned)
            cost = gs.stat(b.active.top).retreatCost
            if cost <= 0:
                _pose_retreat_switch(gs, seat)
            else:
                gs.phase_data = {"seat": seat, "retreat_cost": cost}
                _pose_retreat_energy(gs, seat, cost)
        elif t == OptionType.ATTACK:
            _resolve_attack(gs, seat, o["attackId"])
        else:
            raise AssertionError(f"MAIN option type {t} not implemented (M1 scope)")

    elif ctx == SelectContext.DISCARD_ENERGY:
        o = opts[indices[0]]
        serial = b.active.energy[o["energyIndex"]]
        b.active.energy.remove(serial)
        b.discard.append(serial)
        gs.move_card(serial, AreaType.ENERGY, AreaType.DISCARD, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
        remaining = gs.phase_data.get("retreat_cost", 1) - 1
        gs.phase_data["retreat_cost"] = remaining
        if remaining > 0:
            _pose_retreat_energy(gs, seat, remaining)
        else:
            _pose_retreat_switch(gs, seat)

    elif ctx == SelectContext.SWITCH:
        o = opts[indices[0]]
        _do_switch(gs, seat, o["index"], retreat=True)
        pose_main(gs, seat)

    elif ctx == SelectContext.TO_HAND and gs.phase_data.get("await") == "prize":
        o = opts[indices[0]]
        serial = b.prize[o["index"]]
        b.prize.pop(o["index"])
        b.hand.append(serial)
        gs.move_card(serial, AreaType.PRIZE, AreaType.HAND, seat=seat,
                     visible_to_owner=True, visible_to_opponent=False)
        gs.phase_data["prizes_left"] -= 1
        if gs.phase_data["prizes_left"] > 0 and b.prize:
            _pose_prize_pick(gs, seat)
        else:
            _after_prizes_taken(gs, seat)

    elif ctx == SelectContext.TO_ACTIVE:
        o = opts[indices[0]]
        promoted_by = gs.phase_data.get("seat", 1 - seat)
        ob = gs.players[seat]
        p = ob.bench.pop(o["index"])
        ob.active = p
        gs.move_card(p.top, AreaType.BENCH, AreaType.ACTIVE, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
        _end_turn(gs, promoted_by)

    else:
        raise AssertionError(f"turn got answer for unexpected context {ctx}")


def _target_of(gs: GameState, seat: int, area: int, index: int) -> PokemonInPlay:
    b = gs.players[seat]
    if area == AreaType.ACTIVE:
        return b.active
    return b.bench[index]


def _pose_retreat_energy(gs: GameState, seat: int, remaining: int) -> None:
    b = gs.players[seat]
    opts = [{"type": int(OptionType.ENERGY), "area": int(AreaType.ACTIVE), "index": 0,
             "playerIndex": seat, "energyIndex": k, "count": 1}
            for k in range(len(b.active.energy))]
    pose(gs, seat, type=SelectType.ENERGY, context=SelectContext.DISCARD_ENERGY,
         options=opts, remain_energy_cost=remaining)


def _pose_retreat_switch(gs: GameState, seat: int) -> None:
    b = gs.players[seat]
    opts = [opt_card(AreaType.BENCH, i, seat) for i in range(len(b.bench))]
    pose(gs, seat, type=SelectType.CARD, context=SelectContext.SWITCH, options=opts)


def _do_switch(gs: GameState, seat: int, bench_index: int, *, retreat: bool) -> None:
    b = gs.players[seat]
    old_active = b.active
    new_active = b.bench[bench_index]
    b.bench[bench_index] = old_active
    b.active = new_active
    b.poisoned = b.burned = b.asleep = b.paralyzed = b.confused = False
    gs.emit({"type": int(LogType.SWITCH), "playerIndex": seat,
             "cardIdActive": gs.card_id(old_active.top), "serialActive": old_active.top,
             "cardIdBench": gs.card_id(new_active.top), "serialBench": new_active.top})


# ---------------------------------------------------------------------------- dispatch

def advance(gs: GameState) -> None:
    if gs.phase == "SETUP":
        _setup_advance(gs)


def apply_answer(gs: GameState, indices: list[int]) -> None:
    if gs.frames:                      # a chain program owns the pending select
        from .chain import resume
        resume(gs, indices)
    elif gs.phase == "SETUP":
        _setup_apply(gs, indices)
        _setup_advance(gs)
    elif gs.phase == "TURN":
        _turn_apply(gs, indices)
    else:
        raise AssertionError(f"no answer expected in phase {gs.phase}")
