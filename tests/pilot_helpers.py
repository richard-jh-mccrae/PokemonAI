"""Lib-free builders for Pilot tests.

Build the raw observation *dict* the engine hands the agent (the same shape
`to_observation_class` consumes), so Pilot tests never import `cg` and never load the
native lib. Mirrors `scouting_helpers`.
"""
from __future__ import annotations

import gzip as _gzip
import json as _json
from pathlib import Path as _Path

# AreaType / OptionType / SelectContext values (see src/cg/api.py).
DECK, HAND, DISCARD, ACTIVE, BENCH = 1, 2, 3, 4, 5
CARD, PLAY, ATTACH, ATTACK = 3, 7, 8, 13
YES, NO = 1, 2
MAIN, SETUP_ACTIVE, ATTACH_FROM, MULLIGAN = 0, 1, 21, 42
SWITCH = 3  # SelectContext.SWITCH — swap a Pokémon into the Active Spot (own retreat OR a Boss's gust)
DAMAGE = 15  # SelectContext.DAMAGE — choose which Pokémon an attack deals damage to (bench snipe)
TO_HAND = 7  # SelectContext.TO_HAND — search: choose which card to add to your hand


# `_search_deck_set` reads a search's FETCH clauses from `card_effects.json` (ADR-0032), but test
# fetchers carry TAGS only — so pass `fetch_effects(...)` as `Pilot(effects=...)` to mirror them.
_TAG_FETCH_CLAUSE = {
    "tutor_pokemon": {"kind": "fetch", "target": "pokemon", "zone": "deck"},
    "tutor_mega": {"kind": "fetch", "target": "mega", "zone": "deck"},
    "bench_fill": {"kind": "fetch", "target": "basic_pokemon", "zone": "deck", "hp_max": 70},
    "rush_evolve": {"kind": "fetch", "target": "evolution", "zone": "deck", "no_ability": True},
}


#: The `cost` a `cost_discard`-tagged fetcher carries in the real compendium. The tag says the
#: search is PAID FOR and the clause says WHAT: a fixture must mirror both or it builds a fake card.
_TAG_FETCH_COST = {"cost_discard": {"cost": "discard_2", "cost_required": True}}


def fetch_effects(funcs_map: dict):
    """Mirrors the standard fetcher TAGS to their FETCH clauses. A cost tag is a MODIFIER on the
    fetch clause, never a clause of its own — a separate entry builds two effects, not one paid one."""
    from common.effects import CardEffects
    table = {}
    for cid, tags in funcs_map.items():
        clauses = [dict(_TAG_FETCH_CLAUSE[t]) for t in tags if t in _TAG_FETCH_CLAUSE]
        if not clauses:
            continue
        for tag in tags:
            if tag in _TAG_FETCH_COST:
                for clause in clauses:
                    clause.update(_TAG_FETCH_COST[tag])
        table[cid] = clauses
    return CardEffects(table)


def opt(type: int = PLAY, **kw) -> dict:
    """A generic option (only `type` matters to most callers)."""
    return {"type": type, **kw}


def card_opt(area: int, index: int, player: int = 0) -> dict:
    """A CARD option pointing at a card in `area` at `index`."""
    return {"type": CARD, "area": area, "index": index, "playerIndex": player}


def attack_opt(attack_id: int) -> dict:
    return {"type": ATTACK, "attackId": attack_id}


def poke(cid: int, *, energy: int = 0, hp: int = 0, max_hp: int = 0,
         energy_card: int = 0, attached_energy=None) -> dict:
    """``energies`` are UNITS and ``energyCards`` are CARDS — Basic Energy makes them coincide and
    Ignition does not. ⚠️ `energy_card=0` means COLORLESS, so `poke(x, energy=3)` cannot pay {W}{C}{C}."""
    if attached_energy is None:
        attached_energy = [(energy_card, (energy_card,))] * max(0, int(energy))
    units, cards = [], []
    for card, provides in attached_energy:
        units.extend(provides)
        if card:                       # 0 == the card-less placeholder: a unit with no card
            cards.append({"id": card, "serial": 0})
    return {"id": cid, "serial": 0, "energies": units, "energyCards": cards,
            "tools": [], "preEvolution": [], "hp": hp, "maxHp": max_hp}


def _hand_card(cid: int) -> dict:
    return {"id": cid, "serial": 0, "playerIndex": 0}


_CONDITIONS = ("poisoned", "burned", "asleep", "paralyzed", "confused")


def state(*, your_index: int = 0, active=None, bench=(), hand=(), discard=(),
          opp_active=None, opp_bench=(), opp_discard=(), turn: int = 2, prizes: int = 0,
          opp_prizes: int = 0, opp_conditions=(), opp_hand_count: int = 0,
          deck_count: int | None = None) -> dict:
    """`prizes`/`opp_prizes` are remaining prize COUNTS, 0 meaning an empty list; `deck_count` is
    left UNSET by default so the deck-odds signal (ADR-0029) stays silent unless a test opts in."""
    players = [None, None]
    players[your_index] = {"active": [active] if active else [], "bench": list(bench),
                           "hand": [_hand_card(c) for c in hand], "handCount": len(hand),
                           "discard": [_hand_card(c) for c in discard], "prize": [None] * prizes}
    if deck_count is not None:
        players[your_index]["deckCount"] = deck_count
    opp = {"active": [opp_active] if opp_active else [],
           "bench": list(opp_bench), "hand": None, "handCount": opp_hand_count,
           "discard": [_hand_card(c) for c in opp_discard], "prize": [None] * opp_prizes}
    opp.update({k: (k in opp_conditions) for k in _CONDITIONS})
    players[1 - your_index] = opp
    return {"turn": turn, "yourIndex": your_index, "players": players}


def make_select(options, *, min_count: int = 1, max_count: int = 1,
                context: int = 0, type: int = 0, current=None, deck=None,
                remain_counters: int = 0, effect=None) -> dict:
    """`deck` supplies the revealed search candidates a DECK (area 1) option indexes into;
    `remain_counters` is the DAMAGE_COUNTER_ANY budget; `effect` is `{id: sourceCardId, …}`."""
    return {
        "select": {
            "type": type, "context": context,
            "minCount": min_count, "maxCount": max_count,
            "option": list(options),
            "remainDamageCounter": remain_counters, "remainEnergyCost": 0,
            "deck": deck, "contextCard": None, "effect": effect,
        },
        "logs": [],
        "current": current if current is not None else state(),
    }


# ── the committed parity corpus ────────────────────────────────────────────────────────────────
#: The ONE reader of it, for the reason ADR-0087/ADR-0089 gave the corrections corpus one.
_PARITY = _Path(__file__).resolve().parent / "fixtures" / "parity"


def parity_frame(trace: str, index: int) -> dict:
    """One frame of one committed parity trace, by name and position."""
    with _gzip.open(_PARITY / f"{trace}.trace.json.gz", "rt", encoding="utf-8") as fh:
        return _json.load(fh)["frames"][index]


def parity_selects(context: int, *, effect_id: int | None = None) -> list:
    """``[(trace_name, frame_index, select)]`` at `context`, optionally narrowed to one resolving
    card. Ordered by trace filename then frame index, so a census on it is platform-stable."""
    out = []
    for path in sorted(_PARITY.glob("*.trace.json.gz")):
        with _gzip.open(path, "rt", encoding="utf-8") as fh:
            frames = _json.load(fh)["frames"]
        for index, frame in enumerate(frames):
            select = (frame.get("obs") or {}).get("select") or {}
            if select.get("context") != context:
                continue
            if effect_id is not None and (select.get("effect") or {}).get("id") != effect_id:
                continue
            out.append((path.name.replace(".trace.json.gz", ""), index, select))
    return out
