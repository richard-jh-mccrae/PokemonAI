"""The ONE tuned currency: the general ``role → points`` keep-value tier table (ADR-0065).

Everything else about a card's worth is DERIVED at the decision point. A LEAF module — it imports
nothing from `common` — anchored so a typed Basic Energy sits at the retired ADR-0060 flat shed (−8).
"""
from __future__ import annotations

from typing import NewType


#: Card-worth points. A distinct annotation keeps the Worth scale visible at public seams while
#: retaining float arithmetic at runtime.
Worth = NewType("Worth", float)

ROLE_TIER: dict[str, float] = {
    "win_condition": 30.0,
    "primary_attacker": 30.0,
    "secondary_attacker": 20.0,
    "win_condition_base": 20.0,   # a Line pre-evolution — a 2nd Dreepy is a 2nd LINE, not junk
    "evolution_base": 20.0,
    "engine": 12.0,
    "accel_source": 12.0,
    "counter_mover": 12.0,        # a damage-relay Ability body (Munkidori) — the engine band
    "tutor": 10.0,
}
ENERGY_TIER = 8.0                  # a typed Basic Energy — the mid card, the old flat-shed anchor
ACE_SPEC_TIER = 25.0              # one-per-deck, unrecoverable — high floor, closure-discounted

# behavioural tag → worth points (ADR-0065): mirrors the DISCARD ladder's keep bands into the ONE
# currency, scaled to ROLE_TIER (wincon 30 ↔ keep-key −30), for cards the worth oracle could not see.
TAG_TIER: dict[str, float] = {
    "discard_eot": 30.0,          # a burst Energy (Ignition)
    "clutch_heal": 20.0,          # answers a specific incoming KO
    "gust": 10.0,                 # ALSO the DENY-slot band: a strip is worth this, NOT the ADR-0062
                                  # damage swing. A role-less Hammer still prices its global worth 0.
    "recycle": 10.0,
}


def role_value(roles, is_ace_spec: bool = False, is_typed_basic_energy: bool = False,
               tags=()) -> float:
    """MAX, not sum — worth is the card's best job, so a declared modest role never CAPS a higher
    tag/fallback claim. 0 means no claim, which is not the same as worthless."""
    return max(
        max((ROLE_TIER.get(r, 0.0) for r in roles), default=0.0),
        max((TAG_TIER.get(t, 0.0) for t in tags), default=0.0),
        ACE_SPEC_TIER if is_ace_spec else 0.0,
        ENERGY_TIER if is_typed_basic_energy else 0.0,
    )


def keep_cost(role_value: float, reaccess_odds: float, deadline_odds: float = 1.0) -> float:
    """The one primitive behind every keep-value site: ``role_value × [P(met | keep) − P(met |
    shuffle)]``, where the ``deadline_odds`` factors out of the bracket."""
    if role_value <= 0:
        return 0.0
    return role_value * max(0.0, min(1.0, deadline_odds)) * max(0.0, min(1.0, 1.0 - reaccess_odds))
