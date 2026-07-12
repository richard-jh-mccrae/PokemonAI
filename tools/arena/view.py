"""The board view-model: one raw seat observation -> everything the browser renders.

The single place obs decoding lives for the Arena. The server builds this; the
frontend is a dumb renderer of it. Hidden information never enters the view — the
obs is already seat-filtered by the engine, and the view only carries counts for
the opponent's hidden zones.

Enum values are the engine ints (src/cg/api.py); card/attack names resolve through
the shared provider (loads the native card table once per process).
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for p in (_REPO / "src", _REPO / "tools"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common.scouting.provider import EngineCardStatProvider  # noqa: E402

# OptionType values (src/cg/api.py) — ints, as the env serializes them.
_NUMBER, _YES, _NO, _CARD, _TOOL_CARD, _ENERGY_CARD, _ENERGY = 0, 1, 2, 3, 4, 5, 6
_PLAY, _ATTACH, _EVOLVE, _ABILITY, _DISCARD, _RETREAT, _ATTACK = 7, 8, 9, 10, 11, 12, 13
_END, _SKILL, _SPECIAL_CONDITION = 14, 15, 16

# AreaType values.
_A_DECK, _A_HAND, _A_DISCARD, _A_ACTIVE, _A_BENCH = 1, 2, 3, 4, 5

_PROVIDER = EngineCardStatProvider()


def _name(card_id: int | None) -> str:
    if card_id is None:
        return "?"
    stat = _PROVIDER.get(card_id)
    return stat.name if stat and stat.name else f"Card #{card_id}"


@lru_cache(maxsize=1)
def _attack_index() -> dict[int, tuple[str, int]]:
    from cg.api import all_attack
    return {a.attackId: (a.name, a.damage) for a in all_attack()}


def _attack_label(attack_id: int | None) -> str:
    name, damage = _attack_index().get(attack_id, (None, 0))
    if name is None:
        return f"Attack #{attack_id}" if attack_id is not None else "Attack"
    return f"Attack: {name}" + (f" ({damage})" if damage else "")


# --- board ------------------------------------------------------------------

def _mon(entry: dict | None) -> dict | None:
    if entry is None:
        return None
    return {
        "id": entry.get("id"),
        "name": _name(entry.get("id")),
        "hp": entry.get("hp"),
        "max_hp": entry.get("maxHp"),
        # attached energy UNITS as EnergyType ints — public info, typed so the
        # board can render real symbols, not a generic count
        "energies": list(entry.get("energies") or ()),
        "tools": [_name(t.get("id")) for t in entry.get("tools") or ()],
    }


_CONDITIONS = ("poisoned", "burned", "asleep", "paralyzed", "confused")


def _side(player: dict, *, own: bool) -> dict:
    active = player.get("active") or []
    side = {
        "active": _mon(active[0]) if active else None,
        "bench": [_mon(m) for m in player.get("bench") or ()],
        "hand_count": player.get("handCount", 0),
        "deck_count": player.get("deckCount", 0),
        "prizes": len(player.get("prize") or ()),
        "discard": [{"id": c.get("id"), "name": _name(c.get("id"))}
                    for c in player.get("discard") or ()],
        "conditions": [c for c in _CONDITIONS if player.get(c)],
    }
    if own:
        side["hand"] = [{"i": i, "id": c.get("id"), "name": _name(c.get("id"))}
                        for i, c in enumerate(player.get("hand") or ())]
    return side


# --- options ------------------------------------------------------------------

_ZONE = {_A_DECK: "deck", _A_HAND: "hand", _A_DISCARD: "discard",
         _A_ACTIVE: "active", _A_BENCH: "bench"}

# SelectContext -> the sentence above the choices (fallback below covers the rest).
_PROMPTS = {
    0: "Your move",
    1: "Choose your starting Active Pokémon",
    2: "Choose Pokémon to put on your Bench",
    3: "Choose the Pokémon to swap into the Active Spot",
    4: "Choose the Pokémon to put into the Active Spot",
    5: "Choose the Pokémon to put onto your Bench",
    7: "Choose a card to take",
    8: "Choose a card to discard",
    9: "Choose a card to return to your deck",
    13: "Choose the Pokémon to place damage counters on",
    15: "Choose the Pokémon to deal damage to",
    17: "Choose the Pokémon to heal",
    21: "Choose the Pokémon to attach to",
    26: "Choose the Energy card to discard",
    35: "Choose the Attack to use",
    38: "Choose how many cards to draw",
    41: "Go first?",
    42: "Redraw your starting hand?",
    43: "Activate the effect?",
    46: "Heads or tails?",
}


# EnergyType / SpecialConditionType value names (src/cg/api.py).
_ENERGY_NAME = {0: "Colorless", 1: "Grass", 2: "Fire", 3: "Water", 4: "Lightning",
                5: "Psychic", 6: "Fighting", 7: "Darkness", 8: "Metal", 9: "Dragon",
                10: "Rainbow", 11: "Team Rocket"}
_CONDITION_NAME = {0: "Poison", 1: "Burn", 2: "Sleep", 3: "Paralysis", 4: "Confusion"}


def _hand_name(me: dict, index: int | None) -> str:
    hand = me.get("hand") or []
    if index is not None and 0 <= index < len(hand):
        return _name(hand[index].get("id"))
    return "?"


def _attached_name(entry: dict | None, key: str, index: int | None) -> str:
    cards = (entry or {}).get(key) or []
    if index is not None and 0 <= index < len(cards):
        return _name(cards[index].get("id"))
    return "?"


def _board_entry(current: dict, area: int | None, index: int | None,
                 player_index: int) -> dict | None:
    players = current.get("players") or []
    if not (0 <= player_index < len(players)):
        return None
    player = players[player_index]
    if area == _A_ACTIVE:
        active = player.get("active") or []
        return active[0] if active else None
    if area == _A_BENCH:
        bench = player.get("bench") or []
        return bench[index] if index is not None and 0 <= index < len(bench) else None
    return None


def _place(opt_area: int | None, index: int | None, *, opp: bool | None = None) -> dict | None:
    zone = _ZONE.get(opt_area)
    if zone is None:
        return None
    place = {"zone": zone, "index": index}
    if opp is not None:
        place["opp"] = opp
    return place


def _board_label(current: dict, opt: dict, seat: int, player_index: int) -> str:
    entry = _board_entry(current, opt.get("area"), opt.get("index"), player_index)
    if entry is None:
        return "?"
    bits = []
    zone = _ZONE.get(opt.get("area"), "?")
    bits.append(f"opp {zone}" if player_index != seat else zone)
    hp, mx = entry.get("hp"), entry.get("maxHp")
    if isinstance(hp, int) and isinstance(mx, int) and mx:
        bits.append(f"{hp}/{mx}")
    return f"{_name(entry.get('id'))} ({' · '.join(bits)})"


def _option(i: int, opt: dict, current: dict, seat: int,
            deck: list | None = None) -> dict:
    me = current["players"][seat]
    kind = opt.get("type")
    player_index = opt.get("playerIndex", seat)
    label, source, target = "Select", None, None
    pile_card = pile_kind = None    # revealed-pile picks carry the card for the carousel

    if kind == _PLAY:
        label = f"Play {_hand_name(me, opt.get('index'))}"
        source = _place(_A_HAND, opt.get("index"))
    elif kind in (_ATTACH, _EVOLVE):
        card = _hand_name(me, opt.get("index")) if opt.get("area") == _A_HAND else "?"
        tgt_label = _board_label(
            current, {"area": opt.get("inPlayArea"), "index": opt.get("inPlayIndex")},
            seat, player_index)
        label = (f"Attach {card} → {tgt_label}" if kind == _ATTACH
                 else f"Evolve {tgt_label} into {card}")
        source = _place(opt.get("area"), opt.get("index"))
        target = _place(opt.get("inPlayArea"), opt.get("inPlayIndex"),
                        opp=player_index != seat)
    elif kind == _CARD:
        area, index = opt.get("area"), opt.get("index")
        if area in (_A_ACTIVE, _A_BENCH):
            label = _board_label(current, opt, seat, player_index)
            target = _place(area, index, opp=player_index != seat)
        elif area == _A_DECK and deck and index is not None and 0 <= index < len(deck):
            pile_card = deck[index].get("id")          # a revealed search candidate
            label = _name(pile_card)
            pile_kind = "deck" if pile_card is not None else None
        elif area == _A_HAND:
            label = _hand_name(me, index)
            source = _place(area, index)
        elif area == _A_DISCARD:
            players = current.get("players") or []
            cards = (players[player_index].get("discard") or []
                     if 0 <= player_index < len(players) else [])
            entry = cards[index] if index is not None and 0 <= index < len(cards) else None
            pile_card = entry.get("id") if entry else None
            pile_kind = "discard" if pile_card is not None else None
            label = _name(pile_card) if entry else "?"
            if player_index != seat:
                label = f"{label} (opp discard)"
        elif area == 12:                               # LOOKING — a revealed card
            looking = current.get("looking") or []
            entry = looking[index] if index is not None and 0 <= index < len(looking) else None
            label = _name(entry.get("id")) if entry else "Face-down card"
            pile_card = entry.get("id") if entry else None
            pile_kind = "looking" if pile_card is not None else None
        elif area == 6:                                # PRIZE — face-down by rule
            label = "Face-down prize"
        else:
            label = "?"
    elif kind in (_TOOL_CARD, _ENERGY_CARD, _ENERGY):
        entry = _board_entry(current, opt.get("area"), opt.get("index"), player_index)
        mon = _name(entry.get("id")) if entry else "?"
        if kind == _TOOL_CARD:
            attached = _attached_name(entry, "tools", opt.get("toolIndex"))
        elif kind == _ENERGY_CARD:
            attached = _attached_name(entry, "energyCards", opt.get("energyIndex"))
        else:                                          # ENERGY: a unit, not a card
            energies = (entry or {}).get("energies") or []
            e_idx = opt.get("energyIndex")
            e_type = (energies[e_idx] if e_idx is not None and 0 <= e_idx < len(energies)
                      else None)
            attached = f"{_ENERGY_NAME.get(e_type, 'Unknown')} energy"
        label = f"{attached} (on {mon})"
        source = _place(opt.get("area"), opt.get("index"), opp=player_index != seat)
    elif kind == _DISCARD:
        entry = _board_entry(current, opt.get("area"), opt.get("index"), player_index)
        label = f"Discard {_name(entry.get('id'))}" if entry else "Discard"
        source = _place(opt.get("area"), opt.get("index"), opp=player_index != seat)
    elif kind == _SKILL:
        card_id = opt.get("cardId")
        label = ("Special Condition" if not card_id    # cardId 0 = condition handling
                 else f"Effect: {_name(card_id)}")
    elif kind == _SPECIAL_CONDITION:
        label = _CONDITION_NAME.get(opt.get("specialConditionType"), "Condition")
    elif kind == _ATTACK:
        label = _attack_label(opt.get("attackId"))
    elif kind == _RETREAT:
        label = "Retreat"
    elif kind == _ABILITY:
        entry = _board_entry(current, opt.get("area"), opt.get("index"), player_index)
        label = f"Use Ability: {_name(entry.get('id'))}" if entry else "Use Ability"
        source = _place(opt.get("area"), opt.get("index"), opp=player_index != seat)
    elif kind == _END:
        label = "End turn"
    elif kind == _YES:
        label = "Yes"
    elif kind == _NO:
        label = "No"
    elif kind == _NUMBER:
        label = str(opt.get("number"))

    out = {"i": i, "kind": kind, "label": label}
    if source:
        out["source"] = source
    if target:
        out["target"] = target
    if pile_card is not None and pile_kind:
        out["card"] = pile_card
        out["pile"] = pile_kind
    return out


def _select(select: dict, current: dict, seat: int) -> dict:
    context = select.get("context")
    return {
        "context": context,
        "prompt": _PROMPTS.get(context, "Make a selection"),
        "min": select.get("minCount", 1),
        "max": select.get("maxCount", 1),
        "options": [_option(i, o, current, seat, deck=select.get("deck"))
                    for i, o in enumerate(select.get("option") or ())],
    }


# --- events -------------------------------------------------------------------
# LogType values (src/cg/api.py) rendered as one-line ticker items, seat-relative.

def _event(log: dict, seat: int) -> str | None:
    kind = log.get("type")
    mine = log.get("playerIndex") == seat
    who = "You" if mine else "Opponent"
    name = _name(log.get("cardId")) if log.get("cardId") is not None else "?"
    if kind == 4:    # DRAW (own draws only — the engine never logs the opponent's card)
        return f"{who} drew {name}"
    if kind == 5:    # DRAW_REVERSE
        return f"{who} drew a card"
    if kind == 8:    # SWITCH
        return f"{who} switched the Active Pokémon"
    if kind == 10:   # PLAY
        return f"{who} played {name}"
    if kind == 11:   # ATTACH
        return f"{who} attached {name} to {_name(log.get('cardIdTarget'))}"
    if kind == 12:   # EVOLVE
        return f"{who} evolved {_name(log.get('cardIdTarget'))} into {name}"
    if kind == 15:   # ATTACK
        atk_name, _dmg = _attack_index().get(log.get("attackId"), (None, 0))
        return f"{who}'s {name} used {atk_name or 'an attack'}"
    if kind == 16:   # HP_CHANGE
        value = log.get("value") or 0
        whose = "Your" if mine else "Opponent's"
        if value < 0:
            return f"{whose} {name} took {-value} damage"
        return f"{whose} {name} healed {value}" if value else None
    if kind == 22:   # COIN
        return f"Coin: {'heads' if log.get('head') else 'tails'}"
    if kind in (17, 18, 19, 20, 21):  # special conditions
        cond = {17: "Poisoned", 18: "Burned", 19: "Asleep", 20: "Paralyzed",
                21: "Confused"}[kind]
        whose = "Your" if mine else "Opponent's"
        if log.get("isRecover"):
            return f"{whose} {name} recovered from {cond}"
        return f"{whose} {name} is {cond}"
    if kind == 2 and not mine:   # TURN_START
        return "Opponent's turn"
    return None


# --- entry ------------------------------------------------------------------

def build_view(obs: dict) -> dict:
    """One seat observation -> the full render model for that seat's browser."""
    current = obs.get("current")
    select = obs.get("select")
    if current is None:
        return {"phase": "setup"}
    seat = current.get("yourIndex", 0)
    result = current.get("result", -1)
    over = result is not None and result >= 0
    me, opp = current["players"][seat], current["players"][1 - seat]
    return {
        "phase": "over" if over else "play",
        "turn": current.get("turn"),
        "you": _side(me, own=True),
        "opp": _side(opp, own=False),
        "select": _select(select, current, seat) if select else None,
        "events": [e for e in (_event(l, seat) for l in obs.get("logs") or ())
                   if e is not None],
        "result": None if not over else {
            "winner_seat": result if result in (0, 1) else None,
            "you_won": result == seat,
            "draw": result == 2,                     # simultaneous win is a draw (rulebook delta)
        },
    }
