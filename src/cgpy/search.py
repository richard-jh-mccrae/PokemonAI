"""Search / verification API: fixture-seedable, clonable engine sessions (ADR-0059 M3).

The cgpy twin of ``cg.api``'s search surface minus the opaque blob: where the native engine
reconstructs a search fork from its serialized instance state (``search_begin_input``), cgpy
reconstructs from the STRUCTURED observation plus the caller's hidden-zone predictions
(`state_from_obs`) — or, for god-view/fixture work, from a full-information visualize frame
(`state_from_visualize`). Validation order and error strings mirror ``cg.api.search_begin``
verbatim; fork semantics follow docs/pyeng/determinism.md §4:

- predicted hidden zones are RESHUFFLED by the fork (deterministically: same call + same
  steps = same outcome); callers must never trust order-dependent verdicts. A deck REVEALED
  by the select (``select.deck``) keeps its true recorded order — options index into it.
- ``manual_coin=True``: every coin flip poses a COIN_HEAD YesNo instead of consuming rng.
- sessions are CLONE-PER-STEP: `session_step(id)` never mutates the state behind `id`
  (natively that is why SearchRelease exists); `session_end` clears the whole table.

What a structured rebuild CANNOT recover from a single observation (the native blob carries
these; all are refute-safe approximations for the planner's win verdicts):

- once-per-turn ability gates / attack self-locks already spent this turn (seeded unspent),
- this-turn effect markers (damage bonuses, global once-per-name ability locks, item locks),
- the global energy ATTACH ORDER across Pokémon (seeded in board-scan order),
- an ambiguous mid-effect chain: token-less seeding accepts a MAIN select, or a select posed
  by a TRAINER play program whose posing op is unambiguous (`_OP_POSES` — the fetch-class
  selects correction fixtures capture); anything else (abilities, attack riders, multi-pose
  sequences, LOOKING) raises.

Observations rendered by the live cgpy engine (`cgpy.game`) carry all of the above exactly,
in the ``search_begin_input`` token (`export_token`/`parse_token`) — the cgpy analogue of
the native blob. The token holds ONLY state derivable from public logs (turn markers, gates,
attach order, chain frames whose contents are serials/indices) — never hidden card
identities, so it grants the searcher nothing a log-reading agent could not know.
"""
from __future__ import annotations

import json
from typing import Any

from .cards import CardDB
from .engine import Engine
from .rng import SeededRng
from .schema import SelectContext, SelectType
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
    """Approximate the global attach order by board scan (seat 0 then 1, active first,
    bench order, per-Pokémon attach order) — exact order is engine-internal; the token
    path overrides this with the true sequence."""
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


# (SelectType, SelectContext) pairs an op can pose on its FIRST activation (vars empty).
# Only ops whose act-phase needs nothing but the answer are listed — locating one of these
# uniquely in a trainer's play program pins (pc, vars={}) and the frame resumes exactly.
_OP_POSES = {
    "effectDeckToHandAndShuffle": {(int(SelectType.CARD), int(SelectContext.TO_HAND))},
    "effectTrashToHand": {(int(SelectType.CARD), int(SelectContext.TO_HAND))},
    "costHandTrash": {(int(SelectType.CARD), int(SelectContext.DISCARD))},
    "effectDeckToBenchAndShuffle": {(int(SelectType.CARD), int(SelectContext.TO_BENCH))},
    "effectSwitchMe": {(int(SelectType.CARD), int(SelectContext.SWITCH))},
    "effectSwitchEnemy": {(int(SelectType.CARD), int(SelectContext.SWITCH))},
    "trashEnergyEnemy": {(int(SelectType.ENERGY), int(SelectContext.DISCARD_ENERGY))},
    "xHealMegaBounceEnergy": {(int(SelectType.CARD), int(SelectContext.HEAL))},
}


def _reconstruct_trainer_frame(gs: GameState, select: dict, seat: int) -> None:
    """Rebuild the EffectFrame stack for a select posed mid-trainer: the effect card names
    the program, the (type, context) pair locates the single posing op, and the observation
    already reflects every earlier op's side effects — so ``pc`` at that op with empty vars
    resumes identically. Raises when the posing op cannot be located unambiguously."""
    from .chain import def_for
    eff = gs.pending.effect_card
    if eff is None:
        raise ValueError(
            f"state_from_obs: cannot seed a non-MAIN select with no effect card "
            f"(context {select['context']})")
    for s in (0, 1):
        for p in gs.in_play(s):
            if p.top == eff:
                raise ValueError(
                    "state_from_obs: only trainer play programs can seed mid-effect "
                    "(the effect card is in play — an ability or attack rider)")
    cdef = def_for(gs.card_id(eff)) or {}
    program = cdef.get("play")
    if not program:
        raise ValueError(f"state_from_obs: card {gs.card_id(eff)} has no play program "
                         f"to reconstruct")
    key = (int(select["type"]), int(select["context"]))
    pcs = [i for i, op in enumerate(program) if key in _OP_POSES.get(op["op"], ())]
    if len(pcs) != 1:
        raise ValueError(
            f"state_from_obs: cannot locate the posing op unambiguously for card "
            f"{gs.card_id(eff)} (context {select['context']}: {len(pcs)} candidates)")
    gs.frames = [EffectFrame(program=list(program), pc=pcs[0], vars={}, seat=seat,
                             source=eff, kind="play")]


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
    """An Engine seeded from a live observation dict plus hidden-zone predictions — the
    ``cg.api.search_begin`` contract with the opaque blob replaced by structured rebuild.

    Validation (order and error strings) mirrors the native shim. Prediction lists longer
    than the zone are truncated to the first N entries. Without a cgpy state token on the
    obs, the select must be MAIN — or a trainer-play select whose posing op is unambiguous
    (`_reconstruct_trainer_frame`); other mid-effect states are not reconstructible."""
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
        prize_n = len(pdict["prize"] or [])
        deck_n = pdict["deckCount"]
        hand_n = pdict["handCount"] if hand_ids is not None else 0
        facedown_n = 1 if (seat != yi and opp_facedown) else 0
        deck_from_listing = seat == yi and revealed_deck
        need = prize_n + hand_n + facedown_n + (0 if deck_from_listing else deck_n)
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
            b.deck = unseen[cursor:cursor + deck_n]
            cursor += deck_n
            for s, cid in zip(b.deck, deck_ids):
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
            _reconstruct_trainer_frame(gs, select, yi)
    return Engine(gs)


def state_from_visualize(frame: dict, decks: tuple[list[int], list[int]], *, seat: int,
                         select: dict | None = None, manual_coin: bool = False,
                         db: CardDB | None = None, rng=None) -> Engine:
    """An Engine seeded from a god-view frame (`visualize_data`-style ``current``): full
    information, no predictions — the differential/fixture seeding path.

    ``seat`` is the mover (god frames render yourIndex=0 regardless). When ``select`` is
    given (the paired live-obs select) the pending select is ingested verbatim; otherwise
    the state must be at MAIN and the menu is REBUILT by the engine's own option builder."""
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
