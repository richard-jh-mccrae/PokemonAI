"""Lib-free builders for Pilot tests.

Build the raw observation *dict* the engine hands the agent (the same shape
`to_observation_class` consumes), so Pilot tests never import `cg` and never load the
native lib. Mirrors `scouting_helpers`.
"""
from __future__ import annotations

# AreaType / OptionType / SelectContext values (see src/cg/api.py).
DECK, HAND, DISCARD, ACTIVE, BENCH = 1, 2, 3, 4, 5
CARD, PLAY, ATTACH, ATTACK = 3, 7, 8, 13
YES, NO = 1, 2
MAIN, SETUP_ACTIVE, ATTACH_FROM, MULLIGAN = 0, 1, 21, 42
SWITCH = 3  # SelectContext.SWITCH — swap a Pokémon into the Active Spot (own retreat OR a Boss's gust)
DAMAGE = 15  # SelectContext.DAMAGE — choose which Pokémon an attack deals damage to (a bench snipe)
TO_HAND = 7  # SelectContext.TO_HAND — a search: choose which card to add to your hand


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


_CONDITIONS = ("poisoned", "burned", "asleep", "paralyzed", "confused")


def state(*, your_index: int = 0, active=None, bench=(), hand=(), discard=(),
          opp_active=None, opp_bench=(), turn: int = 2, prizes: int = 0, opp_prizes: int = 0,
          opp_conditions=(), opp_hand_count: int = 0) -> dict:
    """A minimal `current` state with my board/hand (and optionally the opponent's). `prizes` /
    `opp_prizes` set each player's remaining prize count (length of the `prize` list); 0 leaves it
    empty (the prior default — no rule read prizes), so a lethal check only fires when a test sets it.
    `opp_conditions` sets the opponent's Active special-condition flags (e.g. ("poisoned",)) — they
    ride as booleans on the player dict (PlayerState.poisoned/burned/asleep/paralyzed/confused).
    `opp_hand_count` sets the opponent's hand size (the obs exposes the count, not the cards) — the
    magnitude behind a hand-size attacker's forward-doom threat (Alakazam)."""
    players = [None, None]
    players[your_index] = {"active": [active] if active else [], "bench": list(bench),
                           "hand": [_hand_card(c) for c in hand], "handCount": len(hand),
                           "discard": [_hand_card(c) for c in discard], "prize": [None] * prizes}
    opp = {"active": [opp_active] if opp_active else [],
           "bench": list(opp_bench), "hand": None, "handCount": opp_hand_count,
           "discard": [], "prize": [None] * opp_prizes}
    opp.update({k: (k in opp_conditions) for k in _CONDITIONS})
    players[1 - your_index] = opp
    return {"turn": turn, "yourIndex": your_index, "players": players}


def make_select(options, *, min_count: int = 1, max_count: int = 1,
                context: int = 0, type: int = 0, current=None, deck=None) -> dict:
    """An observation whose `select` offers `options` — i.e. a decision menu. `deck` supplies the
    revealed search candidates a DECK (area 1) option indexes into (a TO_HAND/search select)."""
    return {
        "select": {
            "type": type, "context": context,
            "minCount": min_count, "maxCount": max_count,
            "option": list(options),
            "remainDamageCounter": 0, "remainEnergyCost": 0,
            "deck": deck, "contextCard": None, "effect": None,
        },
        "logs": [],
        "current": current if current is not None else state(),
    }
