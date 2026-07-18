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
DAMAGE = 15  # SelectContext.DAMAGE — choose which Pokémon an attack deals damage to (bench snipe)
TO_HAND = 7  # SelectContext.TO_HAND — search: choose which card to add to your hand


# The fetch doctrine's whiff/redundancy/confirmed-hit signals (`_search_deck_set`) read a search's
# FETCH clauses from `card_effects.json` (ADR-0032) — the tier that replaced the tag-keyed
# `_FETCH_FILTERS`. Synthetic test fetchers carry TAGS only, so mirror the standard fetcher tags to
# their clauses. Import `fetch_effects` and pass its result as `Pilot(effects=...)`.
_TAG_FETCH_CLAUSE = {
    "tutor_pokemon": {"kind": "fetch", "target": "pokemon", "zone": "deck"},
    "tutor_mega": {"kind": "fetch", "target": "mega", "zone": "deck"},
    "bench_fill": {"kind": "fetch", "target": "basic_pokemon", "zone": "deck", "hp_max": 70},
    "rush_evolve": {"kind": "fetch", "target": "evolution", "zone": "deck", "no_ability": True},
}


def fetch_effects(funcs_map: dict):
    """A synthetic `CardEffects` mirroring the standard fetcher TAGS in a test's `CardFunctions` map to
    their `card_effects.json` FETCH clauses, so a clause-driven `_search_deck_set` sees the fetch-set."""
    from common.effects import CardEffects
    table = {cid: [_TAG_FETCH_CLAUSE[t] for t in tags if t in _TAG_FETCH_CLAUSE]
             for cid, tags in funcs_map.items()}
    return CardEffects({cid: cls for cid, cls in table.items() if cls})


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
          opp_active=None, opp_bench=(), opp_discard=(), turn: int = 2, prizes: int = 0,
          opp_prizes: int = 0, opp_conditions=(), opp_hand_count: int = 0,
          deck_count: int | None = None) -> dict:
    """A minimal `current` state with my board/hand (and optionally the opponent's). `prizes` /
    `opp_prizes` set each player's remaining prize count (length of the `prize` list); 0 leaves it
    empty (the prior default — no rule read prizes), so a lethal check only fires when a test sets it.
    `opp_conditions` sets the opponent's Active special-condition flags (e.g. ("poisoned",)) — they
    ride as booleans on the player dict (PlayerState.poisoned/burned/asleep/paralyzed/confused).
    `opp_hand_count` sets the opponent's hand size (the obs exposes the count, not the cards) — the
    magnitude behind a hand-size attacker's forward-doom threat (Alakazam). `deck_count` sets my
    remaining deck size (`deckCount`); left UNSET by default so the probabilistic deck-odds signal
    (ADR-0029) stays silent unless a test opts in — keeping every prior test behaviour-neutral."""
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
    """An observation whose `select` offers `options` — i.e. a decision menu. `deck` supplies the
    revealed search candidates a DECK (area 1) option indexes into (a TO_HAND/search select).
    `remain_counters` sets `remainDamageCounter` (the budget at a DAMAGE_COUNTER_ANY spread-placement
    select); `effect` sets the resolving-effect record (`{id: sourceCardId, …}`)."""
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
