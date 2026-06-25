"""Lib-free builders for Pilot tests.

Build the raw observation *dict* the engine hands the agent (the same shape
`to_observation_class` consumes), so Pilot tests never import `cg` and never load the
native lib. Mirrors `scouting_helpers`.
"""
from __future__ import annotations

# AreaType / OptionType / SelectContext values (see src/cg/api.py).
HAND, ACTIVE, BENCH = 2, 4, 5
CARD, PLAY, ATTACH, ATTACK = 3, 7, 8, 13
YES, NO = 1, 2
MAIN, SETUP_ACTIVE, ATTACH_FROM, MULLIGAN = 0, 1, 21, 42


def opt(type: int = PLAY, **kw) -> dict:
    """A generic option (only `type` matters to most callers)."""
    return {"type": type, **kw}


def card_opt(area: int, index: int, player: int = 0) -> dict:
    """A CARD option pointing at a card in `area` at `index`."""
    return {"type": CARD, "area": area, "index": index, "playerIndex": player}


def attack_opt(attack_id: int) -> dict:
    return {"type": ATTACK, "attackId": attack_id}


def poke(cid: int, *, energy: int = 0, hp: int = 0, max_hp: int = 0) -> dict:
    """A Pokémon on the board with `energy` energies attached."""
    return {"id": cid, "serial": 0, "energies": [0] * energy, "energyCards": [],
            "tools": [], "preEvolution": [], "hp": hp, "maxHp": max_hp}


def _hand_card(cid: int) -> dict:
    return {"id": cid, "serial": 0, "playerIndex": 0}


def state(*, your_index: int = 0, active=None, bench=(), hand=(),
          opp_active=None, opp_bench=(), turn: int = 2) -> dict:
    """A minimal `current` state with my board/hand (and optionally the opponent's)."""
    players = [None, None]
    players[your_index] = {"active": [active] if active else [], "bench": list(bench),
                           "hand": [_hand_card(c) for c in hand], "handCount": len(hand),
                           "discard": [], "prize": []}
    players[1 - your_index] = {"active": [opp_active] if opp_active else [],
                               "bench": list(opp_bench), "hand": None,
                               "discard": [], "prize": []}
    return {"turn": turn, "yourIndex": your_index, "players": players}


def make_select(options, *, min_count: int = 1, max_count: int = 1,
                context: int = 0, type: int = 0, current=None) -> dict:
    """An observation whose `select` offers `options` — i.e. a decision menu."""
    return {
        "select": {
            "type": type, "context": context,
            "minCount": min_count, "maxCount": max_count,
            "option": list(options),
            "remainDamageCounter": 0, "remainEnergyCost": 0,
            "deck": None, "contextCard": None, "effect": None,
        },
        "logs": [],
        "current": current if current is not None else state(),
    }
