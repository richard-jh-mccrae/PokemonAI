"""The ONE tuned currency: shared card-function and deck-role Worth (ADR-0065, Issue #507).

Everything else about a card's worth is DERIVED at the decision point. A LEAF module — it imports
nothing from `common` — anchored so a typed Basic Energy sits at the retired ADR-0060 flat shed (−8).
"""
from __future__ import annotations

from typing import NewType


#: Card-worth points. A distinct annotation keeps the Worth scale visible at public seams while
#: retaining float arithmetic at runtime.
Worth = NewType("Worth", float)

WIN_CONDITION_TIER = 30.0
WIN_CONDITION_BASE_TIER = 25.0
WIN_CONDITION_STAGE_TIER = WIN_CONDITION_TIER

ROLE_TIER: dict[str, float] = {
    "win_condition": WIN_CONDITION_TIER,
    "primary_attacker": WIN_CONDITION_TIER,
    "secondary_attacker": 20.0,
    "win_condition_base": WIN_CONDITION_BASE_TIER,
    "win_condition_stage": WIN_CONDITION_STAGE_TIER,
    "evolution_base": 20.0,
    "engine": 12.0,
    "support_pokemon": 12.0,
    "accel_source": 12.0,
    "counter_mover": 12.0,        # a damage-relay Ability body (Munkidori) — the engine band
}

# Scouting Brief vocabulary aliases into the same semantic Worth currency. These translate role
# names only; they do not identify cards or prescribe an action.
ROLE_ALIASES: dict[str, str] = {
    "wincon": "win_condition",
    "wincon_base": "win_condition_base",
    "wincon_stage": "win_condition_stage",
    "prize_liability": "win_condition",
    "fragile_preevo": "win_condition_base",
    "attacker": "secondary_attacker",
    "backup_attacker": "secondary_attacker",
    "threat": "primary_attacker",
    "draw_engine": "engine",
    "energy_accel": "accel_source",
}
ENERGY_TIER = 8.0                  # a typed Basic Energy — the mid card, the old flat-shed anchor
ACE_SPEC_TIER = 25.0              # one-per-deck, unrecoverable — high floor, closure-discounted
KNOWN_CARD_FLOOR = 5.0            # every finite, known card retains at least one future option

# Universal card-function -> Worth defaults (Issue #507). These are CARD facts, not deck doctrine:
# the same Ultra Ball or Crushing Hammer therefore starts at the same value in every deck. A deck's
# declared role or explicit override may raise this amount; neither may erase the shared floor.
FUNCTION_TIER: dict[str, float] = {
    "energy_accel": 12.0,
    "search": 10.0,
    "dig": 10.0,
    "bench_fill": 10.0,
    "item_lock": 10.0,
    "tutor_energy": 10.0,
    "tutor_pokemon": 10.0,
    "tutor_mega": 10.0,
    "tutor_trainer": 10.0,
    "supporter_tutor": 10.0,
    "draw": 8.0,
    "shuffle_hand": 8.0,
    "energy_denial": 6.0,
    "switch": 5.0,
    "stall": 5.0,
}

# behavioural tag → worth points (ADR-0065): mirrors the DISCARD ladder's keep bands into the ONE
# currency, scaled to ROLE_TIER (wincon 30 ↔ keep-key −30), for cards the worth oracle could not see.
TAG_TIER: dict[str, float] = {
    "discard_eot": 30.0,          # a burst Energy (Ignition)
    "clutch_heal": 20.0,          # answers a specific incoming KO
    "gust": 10.0,                 # ALSO the DENY-slot band: a strip is worth this, NOT the ADR-0062
                                  # damage swing. Hammer's portable denial function is 6 below.
    "recycle": 10.0,
}


def role_value(roles, is_ace_spec: bool = False, is_typed_basic_energy: bool = False,
               tags=(), is_known_card: bool = False, worth_override: float = 0.0) -> float:
    """MAX, not sum — worth is the card's best job. Function defaults are shared across decks;
    ``worth_override`` is upward-only by construction. Only an unknown card may resolve to zero."""
    return max(
        max((ROLE_TIER.get(ROLE_ALIASES.get(r, r), 0.0) for r in roles), default=0.0),
        max((TAG_TIER.get(t, 0.0) for t in tags), default=0.0),
        max((FUNCTION_TIER.get(t, 0.0) for t in tags), default=0.0),
        ACE_SPEC_TIER if is_ace_spec else 0.0,
        ENERGY_TIER if is_typed_basic_energy else 0.0,
        KNOWN_CARD_FLOOR if is_known_card else 0.0,
        max(0.0, float(worth_override or 0.0)),
    )


def keep_cost(role_value: float, reaccess_odds: float, deadline_odds: float = 1.0) -> float:
    """The one primitive behind every keep-value site: ``role_value × [P(met | keep) − P(met |
    shuffle)]``, where the ``deadline_odds`` factors out of the bracket."""
    if role_value <= 0:
        return 0.0
    return role_value * max(0.0, min(1.0, deadline_odds)) * max(0.0, min(1.0, 1.0 - reaccess_odds))
