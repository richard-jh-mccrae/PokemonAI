"""Shared printout builders for the Ledger suites: real store ids, synthetic serials."""
from __future__ import annotations

from common.algebra import Actor
from common.api import ActionIdentity
from common.options import LegalAction

DREEPY, DRAKLOAK, DRAGAPULT = 119, 120, 121
LUNATONE, MAKUHITA = 675, 673
STARYU, MEGA_STARMIE, IGNITION = 1030, 1031, 17
ULTRA_BALL = 1121
LILLIES = 1227
HARLEQUIN = 1223
AIR_BALLOON = 1174
FIRE_E, WATER_E, PSYCHIC_E, DARK_E = 2, 3, 5, 7
# Engine wire codes, straight from common.cards.card_facts — 6/8 would be Fighting/Metal.
FIRE, WATER, PSYCHIC, DARKNESS = 2, 3, 5, 7
UNKNOWN = 999_999


def body(card_id, serial, *, hp=100, max_hp=100, energies=(), tools=(), under=()):
    return {"id": card_id, "serial": serial, "playerIndex": 0, "hp": hp, "maxHp": max_hp,
            "appearThisTurn": False, "energies": list(energies),
            "energyCards": [{"id": _energy_card(t), "serial": 700 + i}
                            for i, t in enumerate(energies)],
            "tools": [{"id": c, "serial": 750 + i} for i, c in enumerate(tools)],
            "preEvolution": [{"id": c, "serial": 770 + i} for i, c in enumerate(under)]}


def _energy_card(unit):
    return {FIRE: FIRE_E, WATER: WATER_E, PSYCHIC: PSYCHIC_E, DARKNESS: DARK_E}.get(unit,
                                                                                    FIRE_E)


def player(*, active=None, bench=(), hand=(), discard=(), deck_count=30, prizes=6, own=True,
           hand_count=None, poisoned=False, burned=False, asleep=False, paralyzed=False,
           confused=False):
    return {"active": [active] if active else [], "bench": list(bench), "benchMax": 5,
            "deckCount": deck_count, "prize": [None] * prizes,
            "discard": [{"id": c, "serial": 900 + i, "playerIndex": 0}
                        for i, c in enumerate(discard)],
            "handCount": len(hand) if hand_count is None else hand_count,
            "hand": ([{"id": c, "serial": 800 + i, "playerIndex": 0}
                      for i, c in enumerate(hand)] if own else None),
            "poisoned": poisoned, "burned": burned, "asleep": asleep,
            "paralyzed": paralyzed, "confused": confused}


def printout(*, me=None, them=None, turn=2, select=None):
    return {"select": select, "logs": [], "current": {
        "turn": turn, "yourIndex": 0, "firstPlayer": 0, "supporterPlayed": False,
        "stadiumPlayed": False, "energyAttached": False, "retreated": False, "result": None,
        "stadium": [], "looking": None,
        "players": [me if me is not None else player(),
                    them if them is not None else player(own=False)]}}


def action(kind: str, selection: tuple[int, ...]) -> LegalAction:
    return LegalAction(ActionIdentity(kind, (selection,)), selection, (selection,), ())


class ScriptedProvider:
    """actions/transition/actor from a prepared script keyed by (semantic_key, identity)."""

    available = True

    def __init__(self, menus, nodes, actors=None):
        self._menus = menus            # semantic_key -> tuple[LegalAction, ...]
        self._nodes = nodes            # (semantic_key, identity) -> node
        self._actors = actors or {}    # semantic_key -> Actor (default OURS)

    def actions(self, state):
        return self._menus[state.semantic_key]

    def transition(self, state, act):
        return self._nodes[(state.semantic_key, act.identity)]

    def actor(self, state):
        return self._actors.get(state.semantic_key, Actor.OURS)

    def close(self):
        pass
