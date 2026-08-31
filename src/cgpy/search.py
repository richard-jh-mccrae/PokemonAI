"""Search / verification API: fixture-seedable, clonable engine sessions (ADR-0059 M3).

cgpy rebuilds a fork from the STRUCTURED observation plus hidden-zone predictions, per
determinism.md §4. The traps: predicted hidden zones are RESHUFFLED by the fork, so an
order-dependent verdict is never trustworthy; ``manual_coin`` is honoured only by flips routed
through `chain._flip`; sessions are CLONE-PER-STEP.

A token-less rebuild cannot recover spent once-per-turn gates, this-turn markers, the true attach
order, or an ambiguous mid-effect chain — refute-safe approximations, and the last RAISES rather
than guess. The ``search_begin_input`` token holds ONLY log-derivable state, so it grants the
searcher nothing a log-reading agent could not know.
"""
from __future__ import annotations

import json
from typing import Any

from .cards import CardDB
from .engine import Engine
from .rng import SeededRng
from .schema import LogType, SelectContext, SelectType
from .state import (SERIAL_BASE, CardInstance, EffectFrame, GameState, PendingSelect,
                    PlayerBoard, PokemonInPlay)

_TOKEN_PREFIX = "cgpy/1:"


# ------------------------------------------------------------------ state token

def export_internals(gs: GameState) -> dict:
    """The engine internals a single observation cannot carry (JSON-safe, log-derivable)."""
    pokemon = {}
    for seat in (0, 1):
        for p in gs.in_play(seat):
            pokemon[str(p.top)] = {
                "entered_turn": p.entered_turn,
                "ability_used_turn": p.ability_used_turn,
                "attack_locks": dict(p.attack_locks),
            }
    return {
        "phase": gs.phase,
        "phase_data": gs.phase_data,
        "frames": [{"program": f.program, "pc": f.pc, "vars": f.vars, "seat": f.seat,
                    "source": f.source, "kind": f.kind} for f in gs.frames],
        "pending_triggers": gs.pending_triggers,
        "turn_markers": gs.turn_markers,
        "ko_turn": list(gs.ko_turn),
        "attach_seq": {str(k): v for k, v in gs.attach_seq.items()},
        "attach_tick": gs.attach_tick,
        "mulligans": [gs.players[0].mulligans, gs.players[1].mulligans],
        "paralyzed_since_turn": [gs.players[0].paralyzed_since_turn,
                                 gs.players[1].paralyzed_since_turn],
        "last_posed": list(gs.last_posed),
        "pokemon": pokemon,
    }


def export_token(gs: GameState) -> str:
    return _TOKEN_PREFIX + json.dumps(export_internals(gs), separators=(",", ":"),
                                      ensure_ascii=False)


def parse_token(sbi: Any) -> dict | None:
    """The internals dict when ``sbi`` is a cgpy state token; None for anything else
    (a native blob, a bare marker, absent)."""
    if not isinstance(sbi, str) or not sbi.startswith(_TOKEN_PREFIX):
        return None
    try:
        return json.loads(sbi[len(_TOKEN_PREFIX):])
    except ValueError:
        return None


# ------------------------------------------------------------------ reconstruction

def _register(gs: GameState, serial: int, card_id: int, owner: int) -> int:
    known = gs.cards.get(serial)
    if known is not None:
        if known.card_id != card_id:
            raise ValueError(f"serial {serial} appears with two card ids "
                             f"({known.card_id} vs {card_id})")
        return serial
    if card_id not in gs.db.cards:
        raise ValueError("Invalid Card ID.")
    gs.cards[serial] = CardInstance(serial=serial, card_id=card_id, owner=owner)
    return serial


def _note_card(gs: GameState, c: dict) -> int:
    return _register(gs, c["serial"], c["id"], c["playerIndex"])


def _in_play_from(gs: GameState, pd: dict, seat: int, turn: int) -> PokemonInPlay:
    top = _register(gs, pd["serial"], pd["id"], seat)
    stack = [_note_card(gs, c) for c in pd.get("preEvolution") or []] + [top]
    return PokemonInPlay(
        stack=stack,
        energy=[_note_card(gs, c) for c in pd.get("energyCards") or []],
        tools=[_note_card(gs, c) for c in pd.get("tools") or []],
        hp=pd["hp"], max_hp=pd["maxHp"],
        entered_turn=turn if pd.get("appearThisTurn") else turn - 1)


def _strip_option(o: dict) -> dict:
    return {k: v for k, v in o.items() if v is not None}


def _apply_scalars(gs: GameState, cur: dict) -> None:
    gs.turn = cur["turn"]
    gs.turn_action_count = cur["turnActionCount"]
    gs.first_player = cur["firstPlayer"]
    gs.supporter_played = bool(cur["supporterPlayed"])
    gs.stadium_played = bool(cur["stadiumPlayed"])
    gs.energy_attached = bool(cur["energyAttached"])
    gs.retreated = bool(cur["retreated"])
    gs.result = cur.get("result", -1)


def _apply_conditions(gs: GameState, seat: int, pdict: dict, mover: int) -> None:
    b = gs.players[seat]
    b.poisoned = bool(pdict["poisoned"])
    b.burned = bool(pdict["burned"])
    b.asleep = bool(pdict["asleep"])
    b.paralyzed = bool(pdict["paralyzed"])
    b.confused = bool(pdict["confused"])
    if b.paralyzed:
        # Recovery parity: the mover's paralysis was inflicted on the opponent's turn
        # (recovers at the mover's own turn end); the opponent's was inflicted this turn.
        b.paralyzed_since_turn = gs.turn - 1 if seat == mover else gs.turn


def _fix_stadium_deltas(gs: GameState) -> None:
    """Observed hp/maxHp include the floating stadium delta; stored values must not."""
    from .chain import stadium_hp_delta
    for seat in (0, 1):
        for p in gs.in_play(seat):
            delta = stadium_hp_delta(gs, p)
            p.hp -= delta
            p.max_hp -= delta


def _seed_attach_order(gs: GameState) -> None:
    """APPROXIMATE the global attach order by board scan — the true order is engine-internal, and
    the token path overrides this with the real sequence."""
    for seat in (0, 1):
        for p in gs.in_play(seat):
            for s in p.energy:
                gs.note_attach(s)


def _apply_internals(gs: GameState, internals: dict) -> None:
    gs.phase = internals.get("phase", gs.phase)
    if internals.get("phase_data") is not None:
        gs.phase_data = internals["phase_data"]
    gs.frames = [EffectFrame(**f) for f in internals.get("frames") or []]
    gs.pending_triggers = list(internals.get("pending_triggers") or [])
    gs.turn_markers = dict(internals.get("turn_markers") or {})
    if internals.get("ko_turn") is not None:
        gs.ko_turn = list(internals["ko_turn"])
    if internals.get("attach_seq") is not None:
        gs.attach_seq = {int(k): v for k, v in internals["attach_seq"].items()}
        gs.attach_tick = internals.get("attach_tick", gs.attach_tick)
    for seat, count in enumerate(internals.get("mulligans") or []):
        gs.players[seat].mulligans = count
    for seat, since in enumerate(internals.get("paralyzed_since_turn") or []):
        gs.players[seat].paralyzed_since_turn = since
    if internals.get("last_posed") is not None:
        gs.last_posed = tuple(internals["last_posed"])
    for serial_s, pi in (internals.get("pokemon") or {}).items():
        serial = int(serial_s)
        for seat in (0, 1):
            for p in gs.in_play(seat):
                if p.top == serial:
                    p.entered_turn = pi.get("entered_turn", p.entered_turn)
                    p.ability_used_turn = pi.get("ability_used_turn", p.ability_used_turn)
                    p.attack_locks = dict(pi.get("attack_locks") or {})


# (SelectType, SelectContext) pairs an op can pose on its FIRST activation (vars empty). ONLY ops
# whose act-phase needs nothing but the answer may be listed, or the resumed frame is wrong.
_OP_POSES = {
    "effectDeckToHandAndShuffle": {(int(SelectType.CARD), int(SelectContext.TO_HAND))},
    "effectTrashToHand": {(int(SelectType.CARD), int(SelectContext.TO_HAND))},
    "costHandTrash": {(int(SelectType.CARD), int(SelectContext.DISCARD))},
    "effectDeckToBenchAndShuffle": {(int(SelectType.CARD), int(SelectContext.TO_BENCH))},
    "effectSwitchMe": {(int(SelectType.CARD), int(SelectContext.SWITCH))},
    "effectSwitchEnemy": {(int(SelectType.CARD), int(SelectContext.SWITCH))},
    "trashEnergyEnemy": {(int(SelectType.ENERGY), int(SelectContext.DISCARD_ENERGY))},
    "xHealMegaBounceEnergy": {(int(SelectType.CARD), int(SelectContext.HEAL))},
    "xDistributeCounters": {
        (int(SelectType.CARD), int(SelectContext.DAMAGE_COUNTER_ANY))},
    # Turbo Flare asks for Basic Energies before targets. Native search tokens make that first ask
    # reconstructible only from the attack definition, before its public attack log exists.
    "xDeckEnergyAttachDistribute": {(int(SelectType.CARD), int(SelectContext.ATTACH_TO))},
    "xDiscardEnergyAttachBench": {(int(SelectType.CARD), int(SelectContext.ATTACH_TO))},
    "xDeckEvolveInPlayAndShuffle": {
        (int(SelectType.CARD), int(SelectContext.EVOLVES_TO)),
        (int(SelectType.CARD), int(SelectContext.EVOLVES_FROM)),
    },
}


def _reconstruct_effect_frame(gs: GameState, select: dict, seat: int, logs: list[dict]) -> None:
    """Rebuild a first-ask EffectFrame from an observation carrying a native token.
    Resume only an unambiguous first stateful posing operation; otherwise fail closed."""
    from .chain import def_for
    eff = gs.pending.effect_card
    if eff is None:
        raise ValueError(
            f"state_from_obs: cannot seed a non-MAIN select with no effect card "
            f"(context {select['context']})")
    in_play = any(p.top == eff for s in (0, 1) for p in gs.in_play(s))
    key = (int(select["type"]), int(select["context"]))
    kind = "play"
    if in_play:
        attacks = [entry for entry in reversed(logs or [])
                   if int(entry.get("type", -1)) == int(LogType.ATTACK)
                   and int(entry.get("playerIndex", -1)) == seat
                   and int(entry.get("serial", -1)) == eff
                   and entry.get("attackId") is not None]
        programs = []
        if len(attacks) == 1:
            attack_id = int(attacks[0]["attackId"])
            programs = [(attack_id, (def_for(f"attack:{attack_id}") or {}).get("rider"))]
        elif not attacks:
            for attack_id in gs.db.card(gs.card_id(eff)).attacks:
                rider = (def_for(f"attack:{attack_id}") or {}).get("rider")
                pcs = [i for i, op in enumerate(rider or ())
                       if key in _OP_POSES.get(op["op"], ())]
                if len(pcs) == 1:
                    programs.append((attack_id, rider))
        if len(programs) != 1:
            raise ValueError(
                "state_from_obs: cannot identify the attack that posed the mid-effect select")
        _, program = programs[0]
        kind = "attack"
    else:
        program = (def_for(gs.card_id(eff)) or {}).get("play")
    if not program:
        raise ValueError(f"state_from_obs: effect source {gs.card_id(eff)} has no {kind} program "
                         "to reconstruct")
    pcs = [i for i, op in enumerate(program) if key in _OP_POSES.get(op["op"], ())]
    if len(pcs) != 1:
        raise ValueError(
            f"state_from_obs: cannot locate the posing op unambiguously for effect source "
            f"{gs.card_id(eff)} (context {select['context']}: {len(pcs)} candidates)")
    frame_vars = {}
    op_name = program[pcs[0]]["op"]
    if (op_name == "xDeckEvolveInPlayAndShuffle"
            and int(select["context"]) == int(SelectContext.EVOLVES_FROM)):
        if gs.pending.context_card is None:
            raise ValueError("state_from_obs: evolution target ask has no chosen evolution card")
        frame_vars["evo"] = gs.pending.context_card
    if op_name == "xDistributeCounters":
        frame_vars["left"] = gs.pending.remain_damage_counter
    gs.frames = [EffectFrame(program=list(program), pc=pcs[0], vars=frame_vars, seat=seat,
                             source=eff, kind=kind)]


def _ingest_pending(gs: GameState, select: dict, seat: int) -> None:
    deck_listing = None
    if select.get("deck") is not None:
        deck_listing = [_note_card(gs, c) for c in select["deck"]]
    ctx_card = select.get("contextCard")
    eff_card = select.get("effect")
    gs.pending = PendingSelect(
        seat=seat, type=int(select["type"]), context=int(select["context"]),
        min_count=int(select["minCount"]), max_count=int(select["maxCount"]),
        options=[_strip_option(o) for o in select.get("option") or []],
        remain_damage_counter=select.get("remainDamageCounter") or 0,
        remain_energy_cost=select.get("remainEnergyCost") or 0,
        deck_listing=deck_listing,
        context_card=_note_card(gs, ctx_card) if ctx_card else None,
        effect_card=_note_card(gs, eff_card) if eff_card else None)
    gs.last_posed = (seat, int(select["context"]), int(select["minCount"]),
                     int(select["maxCount"]))


def state_from_obs(obs: dict,
                   your_deck: list[int],
                   your_prize: list[int],
                   opponent_deck: list[int],
                   opponent_prize: list[int],
                   opponent_hand: list[int],
                   opponent_active: list[int],
                   manual_coin: bool = False,
                   *, db: CardDB | None = None, rng=None) -> Engine:
    """An Engine seeded from a live obs plus hidden-zone predictions; over-long prediction lists
    truncate. Without a state token the select must be MAIN or an unambiguous trainer-play select."""
    select = obs.get("select")
    cur = obs.get("current")
    if select is None or cur is None:
        raise ValueError("Not agent observation.")

    yi = cur["yourIndex"]
    me = cur["players"][yi]
    opp = cur["players"][1 - yi]

    revealed_deck = select.get("deck") is not None
    if revealed_deck:
        your_deck = []
    elif len(your_deck) < me["deckCount"]:
        raise ValueError("your_deck does not match the number of cards in your deck.")

    if len(your_prize) < len(me["prize"] or []):
        raise ValueError("your_prize does not match the number of cards in your prize.")
    elif len(opponent_deck) < opp["deckCount"]:
        raise ValueError("opponent_deck does not match the number of cards in opponent's deck.")
    elif len(opponent_prize) < len(opp["prize"] or []):
        raise ValueError("opponent_prize does not match the number of cards in opponent's prize.")
    elif len(opponent_hand) < opp["handCount"]:
        raise ValueError("opponent_hand does not match the number of cards in opponent's hand.")

    opp_active_row = opp["active"] or []
    opp_facedown = len(opp_active_row) > 0 and opp_active_row[0] is None
    if opp_facedown:
        if len(opponent_active) == 0:
            raise ValueError("You need to predict the opponent's Active Pokémon.")
    else:
        opponent_active = []

    db = db or CardDB.load()
    for cid in (list(your_deck[:me["deckCount"]]) + list(your_prize[:len(me["prize"] or [])])
                + list(opponent_deck[:opp["deckCount"]])
                + list(opponent_prize[:len(opp["prize"] or [])])
                + list(opponent_hand[:opp["handCount"]]) + list(opponent_active[:1])):
        if cid not in db.cards:
            raise ValueError("Invalid Card ID.")
    if opponent_active and not db.is_pokemon(opponent_active[0]):
        raise ValueError("Active card must be the ID of a Pokémon card.")

    internals = parse_token(obs.get("search_begin_input"))
    rng = rng or SeededRng(0)
    gs = GameState(db=db, cards={}, players=[PlayerBoard(), PlayerBoard()], rng=rng)
    gs.manual_coin = bool(manual_coin)
    _apply_scalars(gs, cur)

    # --- visible zones (both seats), select-referenced cards, stadium, looking ---
    gs.stadium = [_note_card(gs, c) for c in cur.get("stadium") or []]
    looking = cur.get("looking")
    if looking is not None:
        if any(c is None for c in looking):
            raise ValueError("state_from_obs: cannot seed a state with facedown LOOKING cards")
        gs.looking = [_note_card(gs, c) for c in looking]
        gs.looking_owner = yi
    for seat, pdict in ((yi, me), (1 - yi, opp)):
        b = gs.players[seat]
        b.bench_max = pdict["benchMax"]
        b.discard = [_note_card(gs, c) for c in pdict.get("discard") or []]
        if seat == yi:
            if pdict.get("hand") is None:
                raise ValueError("state_from_obs: the mover's hand is not visible in obs")
            b.hand = [_note_card(gs, c) for c in pdict["hand"]]
        active_row = pdict.get("active") or []
        if active_row and active_row[0] is not None:
            b.active = _in_play_from(gs, active_row[0], seat, gs.turn)
        b.bench = [_in_play_from(gs, pd, seat, gs.turn) for pd in pdict.get("bench") or []]
        _apply_conditions(gs, seat, pdict, yi)
    _ingest_pending(gs, select, yi)   # registers deck-listing / effect / context serials

    # --- hidden zones: partition each seat's unseen serials, bind predicted ids ---
    for seat, pdict, deck_ids, prize_ids, hand_ids, active_ids in (
            (yi, me, list(your_deck), list(your_prize), None, ()),
            (1 - yi, opp, list(opponent_deck), list(opponent_prize),
             list(opponent_hand), tuple(opponent_active))):
        b = gs.players[seat]
        base = SERIAL_BASE[seat]
        unseen = [s for s in range(base, base + 60) if s not in gs.cards]
        visible_serials = set(b.hand) | set(b.discard)
        for pokemon in gs.in_play(seat):
            visible_serials.update(pokemon.stack)
            visible_serials.update(pokemon.energy)
            visible_serials.update(pokemon.tools)
        visible_serials.update(gs.stadium)
        visible_serials.update(gs.looking or ())
        # Multi-ask effects may expose a source-deck card as contextCard for the next target ask.
        # Reserve the registered serial's hidden slot instead of counting it as unseen.
        reserved_deck = []
        context_card = gs.pending.context_card if gs.pending is not None else None
        if (not revealed_deck and context_card is not None and gs.owner(context_card) == seat
                and context_card not in visible_serials):
            reserved_deck.append(context_card)
            context_id = gs.card_id(context_card)
            if context_id in deck_ids:
                deck_ids.remove(context_id)
        prize_n = len(pdict["prize"] or [])
        deck_n = pdict["deckCount"]
        hand_n = pdict["handCount"] if hand_ids is not None else 0
        facedown_n = 1 if (seat != yi and opp_facedown) else 0
        deck_from_listing = seat == yi and revealed_deck
        need = prize_n + hand_n + facedown_n + (0 if deck_from_listing
                                                 else deck_n - len(reserved_deck))
        if len(unseen) != need:
            raise ValueError(
                f"observation does not account for seat {seat}'s cards "
                f"({len(unseen)} unseen serials, {need} hidden slots)")
        cursor = 0
        if facedown_n:
            serial = unseen[cursor]
            cursor += 1
            _register(gs, serial, active_ids[0], seat)
            stat = gs.stat(serial)
            b.active = PokemonInPlay(stack=[serial], hp=stat.hp, max_hp=stat.hp,
                                     entered_turn=1)
            b.active_facedown = True
        b.prize = unseen[cursor:cursor + prize_n]
        cursor += prize_n
        for s, cid in zip(b.prize, prize_ids):
            _register(gs, s, cid, seat)
        rng.shuffle(b.prize, seat=seat)
        if hand_ids is not None:
            b.hand = unseen[cursor:cursor + hand_n]
            cursor += hand_n
            for s, cid in zip(b.hand, hand_ids):
                _register(gs, s, cid, seat)
            rng.shuffle(b.hand, seat=seat)
        if deck_from_listing:
            b.deck = list(gs.pending.deck_listing)   # revealed: true order, no reshuffle
        else:
            hidden_deck_n = deck_n - len(reserved_deck)
            b.deck = list(reserved_deck) + unseen[cursor:cursor + hidden_deck_n]
            cursor += hidden_deck_n
            for s, cid in zip(b.deck[len(reserved_deck):], deck_ids):
                _register(gs, s, cid, seat)
            rng.shuffle(b.deck, seat=seat)   # the fork reshuffles predictions (pin §4)

    _fix_stadium_deltas(gs)
    _seed_attach_order(gs)

    if internals is not None:
        _apply_internals(gs, internals)
    else:
        gs.phase = "TURN"
        gs.phase_data = {"seat": yi}
        if not (int(select["type"]) == int(SelectType.MAIN)
                and int(select["context"]) == int(SelectContext.MAIN)):
            _reconstruct_effect_frame(gs, select, yi, obs.get("logs") or [])
    return Engine(gs)


def state_from_visualize(frame: dict, decks: tuple[list[int], list[int]], *, seat: int,
                         select: dict | None = None, manual_coin: bool = False,
                         db: CardDB | None = None, rng=None) -> Engine:
    """An Engine seeded from a god-view frame: full information, no predictions. ``seat`` is the
    mover — god frames render yourIndex=0 regardless. Without ``select`` the state must be at MAIN."""
    db = db or CardDB.load()
    rng = rng or SeededRng(0)
    if len(decks) != 2 or any(len(d) != 60 for d in decks):
        raise ValueError("decks must be two 60-card id lists")

    gs = GameState(db=db, cards={}, players=[PlayerBoard(), PlayerBoard()], rng=rng)
    gs.manual_coin = bool(manual_coin)
    for s, deck in enumerate(decks):
        for i, cid in enumerate(deck):
            _register(gs, SERIAL_BASE[s] + i, cid, s)

    _apply_scalars(gs, frame)
    gs.stadium = [c["serial"] for c in frame.get("stadium") or []]
    if frame.get("looking") is not None:
        raise ValueError("state_from_visualize: cannot seed a state with LOOKING cards")

    def in_play(pd: dict, s: int) -> PokemonInPlay:
        return PokemonInPlay(
            stack=[c["serial"] for c in pd.get("preEvolution") or []] + [pd["serial"]],
            energy=[c["serial"] for c in pd.get("energyCards") or []],
            tools=[c["serial"] for c in pd.get("tools") or []],
            hp=pd["hp"], max_hp=pd["maxHp"],
            entered_turn=gs.turn if pd.get("appearThisTurn") else gs.turn - 1)

    for s in (0, 1):
        pdict = frame["players"][s]
        b = gs.players[s]
        b.bench_max = pdict["benchMax"]
        b.deck = [c["serial"] for c in pdict.get("deck") or []]
        b.hand = [c["serial"] for c in pdict.get("hand") or []]
        b.prize = [c["serial"] for c in pdict.get("prize") or []]
        b.discard = [c["serial"] for c in pdict.get("discard") or []]
        active_row = pdict.get("active") or []
        if active_row and active_row[0] is not None:
            b.active = in_play(active_row[0], s)
        b.bench = [in_play(pd, s) for pd in pdict.get("bench") or []]
        _apply_conditions(gs, s, pdict, seat)

    _fix_stadium_deltas(gs)
    _seed_attach_order(gs)
    gs.phase = "TURN"
    gs.phase_data = {"seat": seat}

    if select is not None:
        _ingest_pending(gs, select, seat)
    else:
        from .options import pose_main
        pose_main(gs, seat)
        gs.turn_action_count = frame["turnActionCount"]   # the pose bump is already counted
    return Engine(gs)


# ------------------------------------------------------------------ search sessions

_TABLE: dict[int, Engine] = {}
_RELEASED: set[int] = set()
_NEXT_ID = 1


def session_begin(engine: Engine) -> int:
    """Register a root search state; returns its searchId."""
    global _NEXT_ID
    sid = _NEXT_ID
    _NEXT_ID += 1
    _TABLE[sid] = engine
    return sid


def session_get(search_id: int) -> Engine:
    eng = _TABLE.get(search_id)
    if eng is None:
        if search_id in _RELEASED:
            raise ValueError("Released item.")
        raise ValueError("There is no element with the specified search_id.")
    return eng


def session_step(search_id: int, select: list[int]) -> tuple[int, Engine]:
    """Clone-per-step: fork the state behind ``search_id``, apply ``select`` to the fork,
    register and return it. Validation errors mirror native ``search_step`` verbatim."""
    eng = session_get(search_id)
    if eng.result != -1:
        raise ValueError("Cannot be selected because the battle has ended.")
    p = eng.gs.pending
    if p is None or not (p.min_count <= len(select) <= p.max_count):
        raise ValueError("Must be Observation.select.minCount <= len(select) "
                         "<= Observation.select.maxCount.")
    if any(not (0 <= i < len(p.options)) for i in select):
        raise ValueError("Must be 0 <= select elements < len(Observation.select.option).")
    if len(set(select)) != len(select):
        raise ValueError("Duplicate select elements.")
    twin = eng.fork()
    twin.step([int(i) for i in select])
    return session_begin(twin), twin


def session_release(search_id: int) -> None:
    if _TABLE.pop(search_id, None) is not None:
        _RELEASED.add(search_id)


def session_end() -> None:
    _TABLE.clear()
    _RELEASED.clear()
