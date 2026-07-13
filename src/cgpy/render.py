"""Observation rendering: per-seat masking identical to native GetBattleData (ADR-0050).

The live-obs contract (pinned from raw native dumps, see docs/pyeng/determinism.md §7):
- top level {select, logs, current, search_begin_input}
- select always carries all ten keys; absent deck/contextCard/effect are null
- options are SPARSE dicts (only the keys that apply), int enums
- players carry the full key set; own hand = list (possibly empty), opponent hand = null;
  facedown prize slots = null entries; a facedown active renders [null] EVEN TO ITS OWNER;
  discard/bench/stadium fully visible both ways
- logs are the drained per-seat outbox (REVERSE variants already substituted at emission)
"""
from __future__ import annotations

from .state import GameState, PokemonInPlay


def card_dict(gs: GameState, serial: int) -> dict:
    return {"id": gs.card_id(serial), "serial": serial, "playerIndex": gs.owner(serial)}


def pokemon_dict(gs: GameState, p: PokemonInPlay) -> dict:
    from .chain import stadium_hp_delta
    from .options import provided_energy

    energies: list[int] = list(provided_energy(gs, p))
    delta = stadium_hp_delta(gs, p)
    # A negative stadium/energy delta (Gravity Mountain −30) floors the RENDERED hp
    # at 0 — a KO'd Stage-2 renders 0, not −30 (kaggle 85050368: Aura Jab into a
    # Gravity-Mountain Dragapult ex). Raw damage-counter overkill (stored hp already
    # negative, delta 0) is unaffected — native renders that raw.
    return {
        "id": gs.card_id(p.top),
        "serial": p.top,
        "playerIndex": gs.owner(p.top),
        "hp": max(0, p.hp + delta) if delta < 0 else p.hp + delta,
        "maxHp": p.max_hp + delta,
        "appearThisTurn": p.entered_turn >= gs.turn,
        "energies": energies,
        "energyCards": [card_dict(gs, s) for s in p.energy],
        "tools": [card_dict(gs, s) for s in p.tools],
        "preEvolution": [card_dict(gs, s) for s in p.stack[:-1]],
    }


def player_dict(gs: GameState, seat: int, viewer: int) -> dict:
    b = gs.players[seat]
    if b.active is None:
        active = []
    elif b.active_facedown:
        active = [None]                       # facedown: null even to the owner (pinned)
    else:
        active = [pokemon_dict(gs, b.active)]
    return {
        "active": active,
        "bench": [pokemon_dict(gs, p) for p in b.bench],
        "benchMax": b.bench_max,
        "deckCount": len(b.deck),
        "discard": [card_dict(gs, s) for s in b.discard],
        "prize": [None] * len(b.prize),       # facedown until taken
        "handCount": len(b.hand),
        "hand": [card_dict(gs, s) for s in b.hand] if viewer == seat else None,
        "poisoned": b.poisoned,
        "burned": b.burned,
        "asleep": b.asleep,
        "paralyzed": b.paralyzed,
        "confused": b.confused,
    }


def current_dict(gs: GameState, viewer: int) -> dict:
    if gs.looking is None:
        looking = None
    elif viewer == gs.looking_owner:
        looking = [card_dict(gs, s) for s in gs.looking]
    else:
        looking = [None] * len(gs.looking)
    return {
        "turn": gs.turn,
        "turnActionCount": gs.turn_action_count,
        "yourIndex": viewer,
        "firstPlayer": gs.first_player,
        "supporterPlayed": gs.supporter_played,
        "stadiumPlayed": gs.stadium_played,
        "energyAttached": gs.energy_attached,
        "retreated": gs.retreated,
        "result": gs.result,
        "stadium": [card_dict(gs, s) for s in gs.stadium],
        "looking": looking,
        "players": [player_dict(gs, s, viewer) for s in (0, 1)],
    }


def select_dict(gs: GameState) -> dict | None:
    p = gs.pending
    if p is None:
        return None
    return {
        "type": p.type,
        "context": p.context,
        "minCount": p.min_count,
        "maxCount": p.max_count,
        "remainDamageCounter": p.remain_damage_counter,
        "remainEnergyCost": p.remain_energy_cost,
        "option": [dict(o) for o in p.options],
        "deck": ([card_dict(gs, s) for s in p.deck_listing]
                 if p.deck_listing is not None else None),
        "contextCard": card_dict(gs, p.context_card) if p.context_card is not None else None,
        "effect": card_dict(gs, p.effect_card) if p.effect_card is not None else None,
    }


def observation(gs: GameState, viewer: int, *, sbi_token: str = "") -> dict:
    """The full live obs for `viewer`, draining that seat's log outbox."""
    logs, gs.outbox[viewer] = gs.outbox[viewer], []
    return {
        "select": select_dict(gs),
        "logs": logs,
        "current": current_dict(gs, viewer),
        "search_begin_input": sbi_token,
    }


def god_frame(gs: GameState) -> dict:
    """Full-information state projection (both decks/hands revealed) for the differ."""
    def board(seat: int) -> dict:
        b = gs.players[seat]
        d = player_dict(gs, seat, viewer=seat)          # own view: hand visible
        d["hand"] = [card_dict(gs, s) for s in b.hand]  # force-visible for god
        d["deck"] = [card_dict(gs, s) for s in b.deck]
        d["prize"] = [card_dict(gs, s) for s in b.prize]
        if b.active is not None and b.active_facedown:
            d["active"] = [pokemon_dict(gs, b.active)]  # god sees facedown cards
        return d

    cur = current_dict(gs, viewer=0)
    cur["players"] = [board(0), board(1)]
    if gs.looking is not None:
        cur["looking"] = [card_dict(gs, s) for s in gs.looking]
    return cur
