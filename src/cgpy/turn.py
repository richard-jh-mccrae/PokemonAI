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
        if gs.turn_markers.pop("end_turn_after_play", None):   # Boxed Order: "Your
            _end_turn(gs, seat)                                # turn ends." (seeded)
            return
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
    gs.energy_attached = False    # native resets AT TURN_END — observable False during a
    # between-turns promotion select (pinned micro_onboard780a1128 f54). The sibling
    # flags (supporterPlayed/stadiumPlayed/retreated) stay reset-at-TURN_START until a
    # trace pins them.
    _eot_energy_discards(gs, seat)
    _checkup(gs, seat)
    if gs.result != -1 or gs.pending is not None:
        return                       # checkup KO'd something: the claims machine owns flow
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
    """Pokémon Checkup between turns, per seat in (ending, other) order, conditions in
    Poisoned -> Burned -> Asleep -> Paralyzed order (docs/rules.md §8): poison ticks 1
    counter, burn ticks 2 then flips (heads removes), asleep flips (heads wakes),
    paralysis auto-recovers after the owner's turn. Condition-damage HP_CHANGEs log
    putDamageCounter=FALSE (poison tick pinned micro_onboard780a1128 f13; burn by
    analogy, seeded) — True is reserved for counter-PLACEMENT effects (Risky Ruins,
    distribute-counters, both pinned). A checkup KO runs the standard claims flow."""
    for seat in (ending_seat, 1 - ending_seat):
        b = gs.players[seat]
        if b.active is None:
            continue
        me = b.active
        if b.poisoned:
            me.hp = max(0, me.hp - 10)
            gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": seat,
                     "cardId": gs.card_id(me.top), "serial": me.top,
                     "value": -10, "putDamageCounter": False})
        if b.burned:
            me.hp = max(0, me.hp - 20)
            gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": seat,
                     "cardId": gs.card_id(me.top), "serial": me.top,
                     "value": -20, "putDamageCounter": False})
            if gs.coin_flip(seat):
                b.burned = False
                gs.emit({"type": int(LogType.BURNED), "playerIndex": seat,
                         "isRecover": True, "cardId": gs.card_id(me.top),
                         "serial": me.top})
        if b.asleep:
            if gs.coin_flip(seat):
                b.asleep = False
                gs.emit({"type": int(LogType.ASLEEP), "playerIndex": seat,
                         "isRecover": True, "cardId": gs.card_id(me.top),
                         "serial": me.top})
        if b.paralyzed and seat == ending_seat and b.paralyzed_since_turn < gs.turn:
            b.paralyzed = False
            gs.emit({"type": int(LogType.PARALYZED), "playerIndex": seat,
                     "isRecover": True, "cardId": gs.card_id(b.active.top),
                     "serial": b.active.top})
    _sweep_kos(gs, credited=ending_seat, then=("begin_turn", 1 - ending_seat))


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
    """A claimant picks prizes ONE SELECT PER KO'd Pokémon, min=max=that Pokémon's prize
    value (pinned: a mega KO poses min 3 — ms_mirror_1001 f69 — while two 1-prize KOs
    pose two min-1 selects — ms_mirror_1002 f26/f33)."""
    b = gs.players[seat]
    n = min(gs.phase_data["claims"][0][1], len(b.prize))
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
    from .chain import UnsupportedCard, def_for, is_deferred, start_program

    b = gs.players[seat]
    attacker = b.active
    adef = def_for(f"attack:{attack_id}")
    if adef is None or is_deferred(adef):
        raise UnsupportedCard(
            f"attack {attack_id} is {'deferred' if adef else 'undefined'}: "
            f"{(adef or {}).get('deferred', 'no ChainDef')}")
    gs.emit({"type": int(LogType.ATTACK), "playerIndex": seat,
             "cardId": gs.card_id(attacker.top), "serial": attacker.top,
             "attackId": attack_id})
    if adef.get("selfLockNextTurn"):        # Accelerating Stab / Mega Brave: this attack
        attacker.attack_locks[str(attack_id)] = gs.turn + 2   # is barred next own turn
    if adef.get("selfLockAllNextTurn"):     # "can't attack" locks the whole menu (seeded)
        for aid in gs.stat(attacker.top).attacks:
            attacker.attack_locks[str(aid)] = gs.turn + 2
    if b.confused:
        # Confusion gate (docs/rules.md §8, seeded shape): flip before attacking —
        # tails: the attack fails and the attacker takes 3 damage counters.
        if not gs.coin_flip(seat):
            attacker.hp = max(0, attacker.hp - 30)
            gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": seat,
                     "cardId": gs.card_id(attacker.top), "serial": attacker.top,
                     "value": -30, "putDamageCounter": False})  # poison-tick analogy (seeded)
            if not _sweep_kos(gs, credited=seat, then=("end_turn", seat)):
                _end_turn(gs, seat)
            return
    if attacker.attack_gate_turn == gs.turn:
        # Sand-Attack gate: "if the Defending Pokémon tries to use an attack, your
        # opponent flips a coin. If tails, that attack doesn't happen." The gated
        # mover owns the flip (the confusion-channel convention); the fire path is
        # unpinned — no captured defender attack under the gate yet (cn139/971/1513
        # pin only the arming turn).
        if not gs.coin_flip(seat):
            _end_turn(gs, seat)
            return
    pre = adef.get("pre")
    if pre:
        from .state import EffectFrame
        gs.frames.append(EffectFrame(program=list(pre), pc=0,
                                     vars={"attack_id": attack_id},
                                     seat=seat, source=attacker.top, kind="attack_pre"))
        from .chain import run_frames
        run_frames(gs)
        return
    _attack_damage_apply(gs, seat, attack_id, {})


def _attack_damage_apply(gs: GameState, seat: int, attack_id: int,
                         pre_vars: dict) -> None:
    """The damage step: runs directly, or as the continuation of a finished `pre`
    program (whose frame vars carry coin outcomes / cancellation)."""
    from .chain import def_for, start_program
    from .damage import attack_damage

    b, ob = gs.players[seat], gs.players[1 - seat]
    attacker, defender = b.active, ob.active
    adef = def_for(f"attack:{attack_id}") or {}
    req = adef.get("requiresBenchNamed")
    if req is not None:
        names = [req] if isinstance(req, str) else list(req)
        if not all(any(gs.stat(p.top).name == n for p in b.bench) for n in names):
            _end_turn(gs, seat)     # Cosmic Beam without Lunatone: silent nothing
            return                  # (pinned v2_ml_mirror_5100 f178)
    if pre_vars.get("cancel"):      # "If tails, this attack does nothing." — no damage,
        _end_turn(gs, seat)         # no rider (seeded shape)
        return
    dmg = attack_damage(gs, attacker, gs.db.attacks[attack_id], defender,
                        adef=adef, pre_vars=pre_vars)
    # An attack WITH a damage component logs HP_CHANGE even when it computes 0 (pinned
    # perheads_9200 f61: Ball Roll all-tails logs value 0); a component-less status
    # attack logs nothing.
    has_damage = (gs.db.attacks[attack_id].damage > 0 or "scale" in adef
                  or "damage_override" in pre_vars)
    if defender is not None and (dmg > 0 or has_damage):
        defender.hp = max(0, defender.hp - dmg)
        gs.emit({"type": int(LogType.HP_CHANGE), "playerIndex": 1 - seat,
                 "cardId": gs.card_id(defender.top), "serial": defender.top,
                 "value": -dmg, "putDamageCounter": False})
    if adef.get("lockDefenderRetreat") and defender is not None:
        defender.retreat_lock_turn = gs.turn + 1   # "Defending Pokémon can't retreat"
    if adef.get("lockOpponentItems"):              # Itchy Pollen: no ITEM plays for the
        ob.items_locked_turn = gs.turn + 1         # opponent's next turn (menu-enforced)
    rider = adef.get("rider")
    if rider:                       # rider runs BEFORE KO processing (pinned ms_mirror_1002
        # The rider frame inherits the PRE program's coin state (Magical Leaf: the
        # pre flip both boosts the damage AND gates the rider heal). Coin-count ops
        # reset their own tallies, so inherited keys never skew a fresh flip set.
        from .state import EffectFrame
        inherited = {k: pre_vars[k] for k in ("heads", "heads_count", "flips_total")
                     if k in pre_vars}
        gs.frames.append(EffectFrame(program=list(rider), pc=0, vars=inherited,
                                     seat=seat, source=attacker.top, kind="attack"))
        from .chain import run_frames
        run_frames(gs)
        return
    _after_attack(gs, seat)


def _after_attack(gs: GameState, seat: int) -> None:
    """Post-attack KO sweep + prize flow, both sides (recoil riders can KO the attacker).
    A side left with NO Pokémon by a non-KO departure (Tuck Tail's self-return with an
    empty bench — pinned tucktail_9521) loses by NO_POKEMON immediately."""
    if _sweep_kos(gs, credited=seat, then=("end_turn", seat)):
        return
    gone = [s for s in (0, 1)
            if gs.players[s].active is None and not gs.players[s].bench]
    if gone:
        if len(gone) == 2:
            gs.set_result(2, ResultReason.NO_POKEMON)     # simultaneous = DRAW
        else:
            gs.set_result(1 - gone[0], ResultReason.NO_POKEMON)
        return
    _end_turn(gs, seat)


def _sweep_kos(gs: GameState, *, credited: int, then: tuple) -> bool:
    """Sweep BOTH sides for KOs — the credited seat's opponent first (the pinned
    defender-side order: active, then bench) — queue one prize claim per KO for the KO'd
    side's opponent, then start the claims flow. Returns False when nothing was KO'd
    (the caller continues normally). KO thresholds use stadium-adjusted effective HP."""
    from .chain import stadium_hp_delta
    claims: list[list[int]] = []              # [claimant seat, prize value] per KO
    # Side order: the CREDITED side's own deaths sweep (and claim) first — pinned
    # cn364_9001 f18: Thump-Thump's recoil self-KO discards before the effect-KO'd
    # defender, and the opponent's 1-prize claim poses before the attacker's 3.
    for side in (credited, 1 - credited):
        b = gs.players[side]
        koed = False
        if b.active is not None and b.active.hp + stadium_hp_delta(gs, b.active) <= 0:
            claims.append([1 - side, _prize_value(gs, b.active)])
            _discard_in_play(gs, side, b.active)
            b.active = None
            koed = True
        for p in [x for x in b.bench if x.hp + stadium_hp_delta(gs, x) <= 0]:
            claims.append([1 - side, _prize_value(gs, p)])
            _discard_in_play(gs, side, p)
            b.bench.remove(p)
            koed = True
        if koed:
            gs.ko_turn[side] = gs.turn        # Unfair Stamp's gate looks back one turn
    if not claims:
        return False
    gs.phase_data = {"await": "prize", "claims": claims, "then": list(then)}
    _pose_prize_pick(gs, claims[0][0])
    return True


def _after_prizes_taken(gs: GameState) -> None:
    """Post-KO adjudication once every claim is settled: NO_POKEMON outranks the prize
    win (pinned ms_mirror_1001 f121); simultaneous win = DRAW (result 2, rulebook delta);
    then promotions (KO'd side(s) pick a new Active), then the stored continuation."""
    d = gs.phase_data
    winners: list[tuple[int, int]] = []
    for s in (0, 1):
        if gs.players[1 - s].active is None and not gs.players[1 - s].bench:
            winners.append((s, int(ResultReason.NO_POKEMON)))
    if not winners:
        for s in (0, 1):
            if not gs.players[s].prize:
                winners.append((s, int(ResultReason.PRIZES)))
    if len(winners) == 2:
        gs.set_result(2, winners[0][1])       # simultaneous win = DRAW (rulebook delta)
        return
    if winners:
        gs.set_result(*winners[0])
        return
    promote = [s for s in (0, 1)
               if gs.players[s].active is None and gs.players[s].bench]
    # The attacked side promotes first when both lost their Active (seeded order).
    credited = d["then"][1] if d["then"][0] == "end_turn" else 1 - d["then"][1]
    promote.sort(key=lambda s: 0 if s != credited else 1)
    if promote:
        d["await"] = "promote"
        d["promote_queue"] = promote
        _pose_promotion(gs)
        return
    _run_continuation(gs)


def _pose_promotion(gs: GameState) -> None:
    s = gs.phase_data["promote_queue"][0]
    opts = [opt_card(AreaType.BENCH, i, s) for i in range(len(gs.players[s].bench))]
    pose(gs, s, type=SelectType.CARD, context=SelectContext.TO_ACTIVE, options=opts)


def _run_continuation(gs: GameState) -> None:
    kind, seat = gs.phase_data["then"]
    gs.phase_data = {"seat": seat}
    if kind == "end_turn":
        _end_turn(gs, seat)
    else:                                     # "begin_turn": a checkup KO resolved
        begin_turn(gs, seat)


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
            if o["area"] == int(AreaType.STADIUM):
                # Levincia-class per-turn stadium effect (pinned lev_9000 f51-f53:
                # ABILITY option area 7, once per player-turn)
                serial = gs.stadium[0]
                sdef = (def_for(gs.card_id(serial)) or {}).get("stadiumAbility")
                if sdef is None or "program" not in sdef:
                    raise UnsupportedCard(
                        f"stadium {gs.card_id(serial)} ability program unpinned")
                gs.turn_markers["stadium_ability"] = True
                start_program(gs, seat, serial, sdef["program"], kind="ability")
                return
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
        take = getattr(gs.rng, "prize_take", None)
        for serial in serials:                                   # take in answer order
            if take is not None:      # god-free replay: bind identity at take time
                live = serial if serial in b.prize else b.prize[0]
                serial = take(seat, live, deck=b.deck, prize=b.prize)
            b.prize.remove(serial)
            b.hand.append(serial)
            gs.move_card(serial, AreaType.PRIZE, AreaType.HAND, seat=seat,
                         visible_to_owner=True, visible_to_opponent=False)
        gs.phase_data["claims"].pop(0)
        nxt = next((c for c in gs.phase_data["claims"]
                    if gs.players[c[0]].prize), None)
        if nxt is not None:
            gs.phase_data["claims"] = [c for c in gs.phase_data["claims"]
                                       if gs.players[c[0]].prize]
            _pose_prize_pick(gs, nxt[0])
        else:
            gs.phase_data["claims"] = []
            _after_prizes_taken(gs)

    elif ctx == SelectContext.TO_ACTIVE:
        o = opts[indices[0]]
        ob = gs.players[seat]
        p = ob.bench.pop(o["index"])
        ob.active = p
        p.moved_active_turn = gs.turn
        gs.move_card(p.top, AreaType.BENCH, AreaType.ACTIVE, seat=seat,
                     visible_to_owner=True, visible_to_opponent=True)
        q = gs.phase_data.get("promote_queue")
        if q is not None:
            q.pop(0)
            if q:
                _pose_promotion(gs)
            else:
                _run_continuation(gs)
        else:   # legacy single-promotion path (kept for chain-op promotions)
            _end_turn(gs, gs.phase_data.get("seat", 1 - seat))

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
    new_active.moved_active_turn = gs.turn
    cleared = [(flag, lt) for flag, lt in
               (("confused", LogType.CONFUSED), ("paralyzed", LogType.PARALYZED),
                ("asleep", LogType.ASLEEP), ("burned", LogType.BURNED),
                ("poisoned", LogType.POISONED)) if getattr(b, flag)]
    b.poisoned = b.burned = b.asleep = b.paralyzed = b.confused = False
    gs.emit({"type": int(LogType.SWITCH), "playerIndex": seat,
             "cardIdActive": gs.card_id(old_active.top), "serialActive": old_active.top,
             "cardIdBench": gs.card_id(new_active.top), "serialBench": new_active.top})
    for _flag, lt in cleared:
        # Leaving the Active Spot clears conditions WITH isRecover logs after the
        # SWITCH log (pinned micro_onboard780a1128 f28), in REVERSE enum order —
        # CONFUSED before BURNED (pinned micro_onboard409a573_9901 f41), the mirror
        # of the inflict logs' ascending order.
        gs.emit({"type": int(lt), "playerIndex": seat,
                 "isRecover": True, "cardId": gs.card_id(old_active.top),
                 "serial": old_active.top})


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
