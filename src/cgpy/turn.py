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


def _after_benched(gs: GameState, seat: int, p: PokemonInPlay) -> None:
    """QUEUE stadium bench triggers (Risky Ruins: 2 damage counters on a Basic non-{D}
    Pokémon benched during a turn) — triggers resolve at flush_triggers: one auto-runs,
    several pose a SKILL_ORDER select first (pinned ml_dx_2000 f28 vs f30). Called from
    turn-scoped bench entries only — setup benching predates any stadium."""
    from .chain import def_for
    if not gs.stadium:
        return
    stadium_serial = gs.stadium[0]
    trig = (def_for(gs.card_id(stadium_serial)) or {}).get("stadium", {}).get("onBench")
    if not trig:
        return
    stat = gs.stat(p.top)
    if not stat.basic or int(stat.energyType) in trig.get("unlessEnergyType", []):
        return
    gs.pending_triggers.append({
        "cardId": gs.card_id(stadium_serial), "serial": stadium_serial,
        "source": stadium_serial,
        "ops": [{"op": "xBenchCounterDamage", "serial": p.top,
                 "damage": trig["damage"]}]})


def flush_triggers(gs: GameState, seat: int) -> None:
    """Resolve queued triggers: none -> MAIN; one -> run it; several -> the SKILL_ORDER
    select decides execution order (pinned ml_dx_2000 f30 / ml_dx_2001 f46)."""
    from .chain import start_program
    trigs = gs.pending_triggers
    gs.pending_triggers = []
    if not trigs:
        pose_main(gs, seat)
        return
    if len(trigs) == 1:
        t = trigs[0]
        start_program(gs, seat, t["source"], t["ops"], kind="ability")
        return
    start_program(gs, seat, trigs[0]["source"],
                  [{"op": "xOrderTriggers", "triggers": trigs}], kind="ability")


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
            picks = d.get("bench_picks", {})
            for s in order:                 # deferred bench placements, fp order (pinned)
                b = gs.players[s]
                for serial in picks.get(s, []):
                    b.hand.remove(serial)
                    b.bench.append(_new_in_play(gs, serial))
                    gs.move_card(serial, AreaType.HAND, AreaType.BENCH, seat=s,
                                 visible_to_owner=True, visible_to_opponent=False)
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
            # Keep the hand and start the Explosiveness card: the check logs TRUE even
            # though no real Basic is held (pinned v2_ms_mirror_5000 f2).
            gs.emit({"type": int(LogType.HAS_BASIC_POKEMON), "playerIndex": s,
                     "hasBasicPokemon": True})
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
        # Placement is DEFERRED: picks stay in hand until the reveal stage, where both
        # players' benches land in fp order right before TURN_START (pinned
        # v2_ms_dx_5400 f6-f8: the picked card is still in hand during the opponent's
        # bench ask).
        b = gs.players[seat]
        d.setdefault("bench_picks", {})[seat] = [b.hand[opts[i]["index"]]
                                                 for i in indices]

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
    gs.turn_markers = {}
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
    _eot_energy_discards(gs, seat)
    _checkup(gs, seat)
    if gs.result == -1:
        begin_turn(gs, 1 - seat)


def _eot_energy_discards(gs: GameState, seat: int) -> None:
    """Ignition-class self-discard at the owner's end of turn: the move lands between
    TURN_END and the next TURN_START (pinned ms_mirror_1002 f10 log 35), full-visible to
    both. Sweep active first then bench order; within a Pokémon, attach order."""
    from .chain import def_for
    b = gs.players[seat]
    for p in gs.in_play(seat):
        for s in list(p.energy):
            if (def_for(gs.card_id(s)) or {}).get("eotSelfDiscard"):
                p.energy.remove(s)
                b.discard.append(s)
                gs.move_card(s, AreaType.ENERGY, AreaType.DISCARD, seat=seat,
                             visible_to_owner=True, visible_to_opponent=True)


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
    """KO discard order (pinned): the Pokémon stack (top first) from its zone — lower
    stack cards log fromArea PRE_EVOLUTION (pinned ml_dx_2001 f65) — then the attached
    energies in attach order, then tools."""
    b = gs.players[seat]
    from_pokemon = AreaType.ACTIVE if p is b.active else AreaType.BENCH
    if p is b.active:                   # conditions leave play with the Active (pinned
        b.poisoned = b.burned = False   # v2_ml_dx_5501 f22: confused KO renders False)
        b.asleep = b.paralyzed = b.confused = False
    for k, serial in enumerate(reversed(p.stack)):
        area = from_pokemon if k == 0 else AreaType.PRE_EVOLUTION
        b.discard.append(serial)
        gs.move_card(serial, area, AreaType.DISCARD, seat=seat,
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
    """The winner picks prizes ONE SELECT PER KO'd Pokémon, min=max=that Pokémon's prize
    value (pinned: a mega KO poses min 3 — ms_mirror_1001 f69 — while two 1-prize KOs
    pose two min-1 selects — ms_mirror_1002 f26/f33)."""
    b = gs.players[seat]
    claims = gs.phase_data["prize_claims"]
    n = min(claims[0], len(b.prize))
    opts = [opt_card(AreaType.PRIZE, i, seat) for i in range(len(b.prize))]
    pose(gs, seat, type=SelectType.CARD, context=SelectContext.TO_HAND, options=opts,
         min_count=n, max_count=n)


def _prize_value(gs: GameState, p: PokemonInPlay) -> int:
    stat = gs.stat(p.top)
    if stat.megaEx:
        return 3
    if stat.ex:
        return 2
    return 1


def _resolve_attack(gs: GameState, seat: int, attack_id: int) -> None:
    from .chain import def_for, start_program
    from .damage import attack_damage

    b, ob = gs.players[seat], gs.players[1 - seat]
    attacker, defender = b.active, ob.active
    gs.emit({"type": int(LogType.ATTACK), "playerIndex": seat,
             "cardId": gs.card_id(attacker.top), "serial": attacker.top,
             "attackId": attack_id})
    adef_full = def_for(f"attack:{attack_id}") or {}
    if adef_full.get("selfLockNextTurn"):   # Accelerating Stab / Mega Brave: this attack
        attacker.attack_locks[str(attack_id)] = gs.turn + 2   # is barred next own turn
    req = adef_full.get("requiresBenchNamed")
    does_nothing = req is not None and not any(
        gs.stat(p.top).name == req for p in b.bench)   # Cosmic Beam without Lunatone:
    if does_nothing:                                   # no damage, no log (pinned
        dmg = 0                                        # v2_ml_mirror_5100 f178)
    else:
        dmg = attack_damage(gs, attacker, gs.db.attacks[attack_id], defender,
                            ignore_wr=adef_full.get("ignoreWeaknessResistance", False))
    if dmg > 0:
        defender.hp = max(0, defender.hp - dmg)
        gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": 1 - seat,
                 "cardId": gs.card_id(defender.top), "serial": defender.top,
                 "value": -dmg, "putDamageCounter": False})

    rider = adef_full.get("rider")
    if rider:                       # rider runs BEFORE KO processing (pinned ms_mirror_1002
        start_program(gs, seat, attacker.top, rider, kind="attack")  # f25-f26)
        return
    _after_attack(gs, seat)


def _after_attack(gs: GameState, seat: int) -> None:
    """Post-attack KO sweep (defender's side; active first, then bench), prize flow.
    KO thresholds use the stadium-adjusted effective HP (Gravity Mountain)."""
    from .chain import stadium_hp_delta
    ob = gs.players[1 - seat]
    claims: list[int] = []                        # one prize claim per KO'd Pokémon
    if ob.active is not None and ob.active.hp + stadium_hp_delta(gs, ob.active) <= 0:
        claims.append(_prize_value(gs, ob.active))
        _discard_in_play(gs, 1 - seat, ob.active)
        ob.active = None
    for p in [x for x in ob.bench if x.hp + stadium_hp_delta(gs, x) <= 0]:
        claims.append(_prize_value(gs, p))
        _discard_in_play(gs, 1 - seat, p)
        ob.bench.remove(p)
    if not claims:
        _end_turn(gs, seat)
        return
    gs.ko_turn[1 - seat] = gs.turn                # Unfair Stamp's gate looks back one turn
    gs.phase_data = {"seat": seat, "prize_claims": claims, "await": "prize"}
    _pose_prize_pick(gs, seat)


def _after_prizes_taken(gs: GameState, seat: int) -> None:
    """Post-KO adjudication once the winner finished picking prizes (pinned: reason 3
    outranks the prize win when the defender also cannot promote)."""
    b, ob = gs.players[seat], gs.players[1 - seat]
    i_won = not b.prize
    they_cant = ob.active is None and not ob.bench
    if they_cant:                # NO_POKEMON outranks the prize win even when both hold
        gs.set_result(seat, ResultReason.NO_POKEMON)   # (pinned ms_mirror_1001 f121:
        return                                         # result=1 reason=3, NOT a draw)
    if i_won:
        gs.set_result(seat, ResultReason.PRIZES)
        return
    if ob.active is not None:                          # bench-only KO: nothing to promote
        _end_turn(gs, seat)
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
                from .chain import def_for
                b.hand.remove(serial)
                p = _new_in_play(gs, serial)
                b.bench.append(p)
                gs.emit({"type": int(LogType.PLAY), "playerIndex": seat,
                         "cardId": gs.card_id(serial), "serial": serial})
                _after_benched(gs, seat, p)
                hook = (def_for(gs.card_id(serial)) or {}).get("onBench")
                if hook:                                  # Meowth ex-class triggered ask
                    gs.pending_triggers.append({
                        "cardId": gs.card_id(serial), "serial": serial,
                        "source": serial,
                        "ops": [{"op": "xActivateAsk", "program": hook["program"]}]})
                flush_triggers(gs, seat)
            elif stat.cardType == 4:                      # a stadium: replace-and-place
                b.hand.remove(serial)
                gs.emit({"type": int(LogType.PLAY), "playerIndex": seat,
                         "cardId": gs.card_id(serial), "serial": serial})
                for old in gs.stadium:                    # old stadium -> OWNER's discard
                    owner = gs.owner(old)                 # (pinned ml_dx_2001 f77: PLAY
                    gs.players[owner].discard.append(old)  # log first, then the move)
                    gs.move_card(old, AreaType.STADIUM, AreaType.DISCARD, seat=owner,
                                 visible_to_owner=True, visible_to_opponent=True)
                gs.stadium = [serial]                     # placement itself is unlogged
                gs.stadium_played = True
                pose_main(gs, seat)
            else:                                         # a trainer: run its chain program
                from .chain import UnsupportedCard, def_for, start_program
                cdef = def_for(gs.card_id(serial))
                if cdef is None or "play" not in cdef:
                    raise UnsupportedCard(f"card {gs.card_id(serial)} has no play program")
                b.hand.remove(serial)
                # NOT discarded here: the card sits outside every zone during its own
                # selects and lands in the discard at program completion (chain.py
                # _after_program) — pinned ms_mirror_1000 f10-f12.
                gs.emit({"type": int(LogType.PLAY), "playerIndex": seat,
                         "cardId": gs.card_id(serial), "serial": serial})
                if stat.cardType == 3:
                    gs.supporter_played = True
                start_program(gs, seat, serial, cdef["play"])
        elif t == OptionType.ATTACH:
            serial = b.hand[o["index"]]
            target = _target_of(gs, seat, o["inPlayArea"], o["inPlayIndex"])
            b.hand.remove(serial)
            if gs.stat(serial).cardType == 2:             # a TOOL: no per-turn limit
                from .chain import def_for
                target.tools.append(serial)
                bonus = (def_for(gs.card_id(serial)) or {}).get("tool", {}) \
                    .get("hpBonus", 0)
                target.max_hp += bonus                    # Hero's Cape: +100 HP
                target.hp += bonus
            else:
                target.energy.append(serial)
                gs.note_attach(serial)
                gs.energy_attached = True
            gs.emit({"type": int(LogType.ATTACH), "playerIndex": seat,
                     "cardId": gs.card_id(serial), "serial": serial,
                     "cardIdTarget": gs.card_id(target.top), "serialTarget": target.top})
            pose_main(gs, seat)
        elif t == OptionType.EVOLVE:
            from .chain import def_for
            serial = b.hand[o["index"]]
            target = _target_of(gs, seat, o["inPlayArea"], o["inPlayIndex"])
            b.hand.remove(serial)
            _apply_evolution(gs, seat, serial, target)
            hook = (def_for(gs.card_id(serial)) or {}).get("onEvolve")
            if hook:                                # Hariyama-class triggered ask
                gs.pending_triggers.append({        # (pinned ml_dx_2001 f29-f30)
                    "cardId": gs.card_id(serial), "serial": serial, "source": serial,
                    "ops": [{"op": "xActivateAsk", "program": hook["program"]}]})
            flush_triggers(gs, seat)
        elif t == OptionType.RETREAT:
            from .options import effective_retreat_cost
            gs.retreated = True                 # set at choice time, not completion (pinned)
            cost = effective_retreat_cost(gs, b.active)
            if cost <= 0:
                _pose_retreat_switch(gs, seat)
            else:
                gs.phase_data = {"seat": seat, "retreat_cost": cost}
                _pose_retreat_energy(gs, seat, cost)
        elif t == OptionType.ABILITY:
            from .chain import UnsupportedCard, def_for, start_program
            p = _target_of(gs, seat, o["area"], o["index"])
            cid = gs.card_id(p.top)
            adef = (def_for(cid) or {}).get("ability")
            if adef is None or "program" not in adef:
                raise UnsupportedCard(f"card {cid} ability program unpinned")
            p.ability_used_turn = gs.turn           # no log for the activation itself
            if adef.get("oncePerTurnGlobal"):       # (pinned ml_dx_2000 f26-f27)
                gs.turn_markers[f"ability:{cid}"] = True
            start_program(gs, seat, p.top, adef["program"], kind="ability")
        elif t == OptionType.ATTACK:
            _resolve_attack(gs, seat, o["attackId"])
        else:
            raise AssertionError(f"MAIN option type {t} not implemented (M1 scope)")

    elif ctx == SelectContext.DISCARD_ENERGY:
        from .options import provided_units_of
        o = opts[indices[0]]
        serial = b.active.energy[o["energyIndex"]]
        units = provided_units_of(gs, b.active, serial)
        b.active.energy.remove(serial)
        b.discard.append(serial)
        gs.move_card(serial, AreaType.ENERGY, AreaType.DISCARD, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
        remaining = gs.phase_data.get("retreat_cost", 1) - units
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
        serials = [b.prize[opts[i]["index"]] for i in indices]   # resolve pre-removal
        for serial in serials:                                   # take in answer order
            b.prize.remove(serial)
            b.hand.append(serial)
            gs.move_card(serial, AreaType.PRIZE, AreaType.HAND, seat=seat,
                         visible_to_owner=True, visible_to_opponent=False)
        gs.phase_data["prize_claims"].pop(0)
        if gs.phase_data["prize_claims"] and b.prize:
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


def _apply_evolution(gs: GameState, seat: int, serial: int, target: PokemonInPlay) -> None:
    """Stack `serial` onto `target` (source zone already vacated by the caller): HP delta
    carries over, entered_turn resets, Active conditions clear; emits the EVOLVE log (the
    only log — deck-sourced evolution emits no MOVE_CARD, pinned ms_mirror_1001 f16)."""
    from .chain import def_for
    b = gs.players[seat]
    old_top, old_max = target.top, target.max_hp
    target.stack.append(serial)
    new_max = gs.stat(serial).hp                   # attached-tool HP bonuses carry over
    for s in target.tools:                         # (Hero's Cape survives evolution —
        new_max += (def_for(gs.card_id(s)) or {}).get("tool", {}).get("hpBonus", 0)
    target.max_hp = new_max                        # pinned ms_mirror_1000 f21: 310+100)
    target.hp += new_max - old_max
    target.entered_turn = gs.turn
    if target is b.active:                  # evolving clears special conditions
        b.poisoned = b.burned = b.asleep = b.paralyzed = b.confused = False
    gs.emit({"type": int(LogType.EVOLVE), "playerIndex": seat,
             "cardId": gs.card_id(serial), "serial": serial,
             "cardIdTarget": gs.card_id(old_top), "serialTarget": old_top})


def _pose_retreat_energy(gs: GameState, seat: int, remaining: int) -> None:
    from .options import provided_units_of
    b = gs.players[seat]
    opts = [{"type": int(OptionType.ENERGY), "area": int(AreaType.ACTIVE), "index": 0,
             "playerIndex": seat, "energyIndex": k,
             "count": provided_units_of(gs, b.active, s)}   # units, not 1 (pinned
            for k, s in enumerate(b.active.energy)]         # v2_ms_mirror_5001 f128)
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
