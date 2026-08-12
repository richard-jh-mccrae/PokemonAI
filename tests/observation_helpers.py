"""Library-free observation builders shared by UI/runtime tests."""
from __future__ import annotations


DECK, HAND, DISCARD, ACTIVE, BENCH = 1, 2, 3, 4, 5
CARD, PLAY, ATTACH, ATTACK = 3, 7, 8, 13
DAMAGE, TO_HAND = 15, 7


def opt(type: int = PLAY, **values) -> dict:
    return {"type": type, **values}


def card_opt(area: int, index: int, player: int = 0) -> dict:
    return {"type": CARD, "area": area, "index": index, "playerIndex": player}


def attack_opt(attack_id: int) -> dict:
    return {"type": ATTACK, "attackId": attack_id}


def poke(card_id: int, *, energy: int = 0, hp: int = 0, max_hp: int = 0,
         energy_card: int = 0, attached_energy=None) -> dict:
    attached_energy = ([(energy_card, (energy_card,))] * max(0, int(energy))
                       if attached_energy is None else attached_energy)
    units, cards = [], []
    for card, provides in attached_energy:
        units.extend(provides)
        if card:
            cards.append({"id": card, "serial": 0})
    return {"id": card_id, "serial": 0, "energies": units, "energyCards": cards,
            "tools": [], "preEvolution": [], "hp": hp, "maxHp": max_hp}


def _hand_card(card_id: int) -> dict:
    return {"id": card_id, "serial": 0, "playerIndex": 0}


def state(*, your_index: int = 0, active=None, bench=(), hand=(), discard=(),
          opp_active=None, opp_bench=(), opp_discard=(), turn: int = 2, prizes: int = 0,
          opp_prizes: int = 0, opp_conditions=(), opp_hand_count: int = 0,
          deck_count: int | None = None) -> dict:
    players = [None, None]
    players[your_index] = {
        "active": [active] if active else [], "bench": list(bench),
        "hand": [_hand_card(card) for card in hand], "handCount": len(hand),
        "discard": [_hand_card(card) for card in discard], "prize": [None] * prizes,
    }
    if deck_count is not None:
        players[your_index]["deckCount"] = deck_count
    opponent = {
        "active": [opp_active] if opp_active else [], "bench": list(opp_bench),
        "hand": None, "handCount": opp_hand_count,
        "discard": [_hand_card(card) for card in opp_discard], "prize": [None] * opp_prizes,
    }
    for condition in ("poisoned", "burned", "asleep", "paralyzed", "confused"):
        opponent[condition] = condition in opp_conditions
    players[1 - your_index] = opponent
    return {"turn": turn, "yourIndex": your_index, "players": players}


def make_select(options, *, min_count: int = 1, max_count: int = 1,
                context: int = 0, type: int = 0, current=None, deck=None,
                remain_counters: int = 0, effect=None) -> dict:
    return {
        "select": {"type": type, "context": context, "minCount": min_count,
                   "maxCount": max_count, "option": list(options),
                   "remainDamageCounter": remain_counters, "remainEnergyCost": 0,
                   "deck": deck, "contextCard": None, "effect": effect},
        "logs": [], "current": current if current is not None else state(),
    }
