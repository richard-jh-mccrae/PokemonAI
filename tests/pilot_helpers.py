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
# `_FETCH_FILTERS`. test fetchers carry TAGS only, so mirror the standard fetcher tags to
# their clauses. Import `fetch_effects` and pass its result as `Pilot(effects=...)`.
_TAG_FETCH_CLAUSE = {
    "tutor_pokemon": {"kind": "fetch", "target": "pokemon", "zone": "deck"},
    "tutor_mega": {"kind": "fetch", "target": "mega", "zone": "deck"},
    "bench_fill": {"kind": "fetch", "target": "basic_pokemon", "zone": "deck", "hp_max": 70},
    "rush_evolve": {"kind": "fetch", "target": "evolution", "zone": "deck", "no_ability": True},
}


def fetch_effects(funcs_map: dict):
    """A `CardEffects` mirroring the standard fetcher TAGS in a test's `CardFunctions` map to
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


def poke(cid: int, *, energy: int = 0, hp: int = 0, max_hp: int = 0,
         energy_card: int = 0, attached_energy=None) -> dict:
    """A Pokémon on the board with Energy attached, in the engine's REAL two-field shape.

    The engine gives a body TWO Energy fields and they are different facts (`cg/api.py`
    `Pokemon`)::

        energies:    list[EnergyType]   the UNITS the attached cards provide
        energyCards: list[Card]         the attached CARDS themselves

    Count-shaped reads take `energies` (`len(...)` is the Energy on the body, and a cost shape is
    paid in units); identity-shaped reads take `energyCards` (`deck_tracker`, `MySide.visible_counts`
    and `Pilot._visible_card_counts` all derive *decklist − visible*, and a `DISCARD_ENERGY` option's
    `energyIndex` indexes the cards). Never conflate them even though Basic Energy makes them
    coincide (Basic {F} Energy is card id 6 and EnergyType.FIGHTING is 6, per `data/EN_Card_Data.csv`
    and `cg.api`): the coincidence fails on the very next Energy a test reaches for — **Ignition
    Energy is card id 17 and renders as `[0, 0, 0]`, three COLORLESS units; Rock Fighting Energy is
    card id 20 and renders as `[6]`**. Believing the coincidence is exactly the defect Issue #297
    fixed in `MySide._count_in_play`, and this helper could not express the counter-example.

    Two ways in, and they build the same shape:

    * `energy` / `energy_card` — the uniform sugar: `energy` copies of one card, each providing ONE
      unit of its own id. Right for the eight Basic Energies, and for the default `energy_card=0`
      the units are **COLORLESS** and no card is added (so no test gains a phantom card-0
      attachment). ⚠️ Colourless is a real, specific answer, not a blank: a colourless unit pays a
      colourless slot and NOTHING else, so `poke(x, energy=3)` against a `{W}{C}{C}` attack is
      **unpayable** — it is the board two Mist Energy make, not "3 Energy of unspecified type".
      A test that means "enough Energy to pay THIS attack" must name the colour: pass the Basic
      Energy's card id and register that card in the test's `DictCardStatProvider`. (Deny Relevance
      needs the same, for the same reason — it asks *which* Energy is doing the work, matching the
      body's attached types against the attack's `energyTypes`.)
    * `attached_energy` — the general form for anything Special: a sequence of `(card_id, units)`
      pairs, `units` being the EnergyType codes that ONE copy of that card provides. An Ignition
      plus a Rock Fighting on one body is `[(17, (0, 0, 0)), (20, (6,))]`. Overrides the sugar.
      Deliberately not spelled `energy_cards` — one character from `energy_card` and a different
      shape entirely is a typo the reader cannot see.
    """
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
                remain_counters: int = 0, effect=None, context_card=None) -> dict:
    """An observation whose `select` offers `options` — i.e. a decision menu. `deck` supplies the
    revealed search candidates a DECK (area 1) option indexes into (a TO_HAND/search select).
    `remain_counters` sets `remainDamageCounter` (the budget at a DAMAGE_COUNTER_ANY spread-placement
    select); `effect` sets the resolving-effect record (`{id: sourceCardId, …}`).

    `context_card` sets `select.contextCard` — the card the select is ABOUT, which is a different
    fact from the option's own card and is the only place some selects carry theirs. At
    `_EVOLVES_FROM` (ctx 18) the options name my in-play bodies and the evolution being put down
    rides here (`{"id": …, "serial": …, "playerIndex": …}`); `_attach_value`'s `is_from` branch reads
    the same field. Defaults to None, which is what every other select shape actually carries."""
    return {
        "select": {
            "type": type, "context": context,
            "minCount": min_count, "maxCount": max_count,
            "option": list(options),
            "remainDamageCounter": remain_counters, "remainEnergyCost": 0,
            "deck": deck, "contextCard": context_card, "effect": effect,
        },
        "logs": [],
        "current": current if current is not None else state(),
    }
