"""Shared printout builders for the Ledger suites: real store ids, synthetic serials."""
from __future__ import annotations

DREEPY, DRAKLOAK, DRAGAPULT = 119, 120, 121
LUNATONE, MAKUHITA = 675, 673
ULTRA_BALL = 1121
LILLIES = 1227
HARLEQUIN = 1223
FIRE_E, PSYCHIC_E, DARK_E = 2, 5, 7
FIRE, PSYCHIC, DARKNESS = 2, 6, 8
UNKNOWN = 999_999


def body(card_id, serial, *, hp=100, max_hp=100, energies=(), tools=()):
    return {"id": card_id, "serial": serial, "playerIndex": 0, "hp": hp, "maxHp": max_hp,
            "appearThisTurn": False, "energies": list(energies),
            "energyCards": [{"id": _energy_card(t), "serial": 700 + i}
                            for i, t in enumerate(energies)],
            "tools": [{"id": c, "serial": 750 + i} for i, c in enumerate(tools)],
            "preEvolution": []}


def _energy_card(unit):
    return {FIRE: FIRE_E, PSYCHIC: PSYCHIC_E, DARKNESS: DARK_E}.get(unit, FIRE_E)


def player(*, active=None, bench=(), hand=(), discard=(), deck_count=30, prizes=6, own=True,
           hand_count=None):
    return {"active": [active] if active else [], "bench": list(bench), "benchMax": 5,
            "deckCount": deck_count, "prize": [None] * prizes,
            "discard": [{"id": c, "serial": 900 + i, "playerIndex": 0}
                        for i, c in enumerate(discard)],
            "handCount": len(hand) if hand_count is None else hand_count,
            "hand": ([{"id": c, "serial": 800 + i, "playerIndex": 0}
                      for i, c in enumerate(hand)] if own else None),
            "poisoned": False, "burned": False, "asleep": False, "paralyzed": False,
            "confused": False}


def printout(*, me=None, them=None, turn=2, select=None):
    return {"select": select, "logs": [], "current": {
        "turn": turn, "yourIndex": 0, "firstPlayer": 0, "supporterPlayed": False,
        "stadiumPlayed": False, "energyAttached": False, "retreated": False, "result": None,
        "stadium": [], "looking": None,
        "players": [me if me is not None else player(),
                    them if them is not None else player(own=False)]}}
