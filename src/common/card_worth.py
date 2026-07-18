"""Card-worth: the replaceability-floor keep-value tier table (WP6 —
hypergeometric-fetch-closure §Rounds 6-9).

This module owns the ONE tuned currency: the general ``role → points`` tier the
keep-cost is measured in. Everything ELSE about a card's worth is DERIVED at the
decision point — the re-access odds (the fetch/draw closure pointed backwards)
and the gate deadlines live on the Pilot, which reads this table. deck-genie
never invents numbers (spec §Round 9); corrections arbitrate the tiers.

The seed calibration anchors a mid card (a typed Basic Energy) near the retired
ADR-0060 flat shed (−8), scaling UP for the plan pieces a shuffle must not
casually lose — so a graded keep-cost REPLACES the flat shed rather than bolting
on beside it (the currency-zone rule).
"""
from __future__ import annotations

# role → base worth points. Max over a card's declared/derived Roles; the energy / ACE-SPEC
# fallbacks below cover cards a deck leaves un-Roled. Tuned under the correction corpus.
ROLE_TIER: dict[str, float] = {
    "win_condition": 30.0,        # the payoff — losing it stalls the whole plan
    "primary_attacker": 30.0,
    "secondary_attacker": 20.0,
    "win_condition_base": 20.0,   # a Line pre-evolution — a 2nd Dreepy is a 2nd LINE, not junk
    "evolution_base": 20.0,
    "engine": 12.0,               # a draw/accel engine body
    "accel_source": 12.0,
    "tutor": 10.0,                # a wincon tutor (deck-relative — the closure discounts it)
}
ENERGY_TIER = 8.0                  # a typed Basic Energy — the mid card, the old flat-shed anchor
ACE_SPEC_TIER = 25.0              # a one-per-deck, unrecoverable ACE SPEC — high floor, closure-discounted


def role_value(roles, is_ace_spec: bool = False, is_typed_basic_energy: bool = False) -> float:
    """A card's BASE worth = the tuned `ROLE_TIER` max over its declared / derived ``roles``, with the
    ACE-SPEC and typed-Basic-Energy fallbacks for a card a deck leaves un-Roled (WP7, ADR-0065). The
    ONE currency zone; deck-genie never invents numbers, the closure supplies the redundancy discount
    (`keep_cost`). 0 for a role-less non-energy, non-ACE-SPEC card (priced by tag/CardStat rules, not
    the worth oracle). Pure over card FACTS — the Pilot supplies ``roles`` / the two flags."""
    base = max((ROLE_TIER.get(r, 0.0) for r in roles), default=0.0)
    if base <= 0:
        if is_ace_spec:
            return ACE_SPEC_TIER                  # a one-per-deck, unrecoverable ACE SPEC
        if is_typed_basic_energy:
            return ENERGY_TIER
    return base


def keep_cost(role_value: float, reaccess_odds: float, deadline_odds: float = 1.0) -> float:
    """The cost of shuffling a card away = its role worth × how UN-recoverable it is
    (``1 − re-access odds``) × how realisable its role is by its deadline (``deadline_odds``, the gate
    library's factor — 1.0 for a card whose role is live, →0 for a dead one such as an undeployable
    evolution). 0 for a worthless card; capped at the role value (fully irreplaceable, role live). The
    one primitive behind every keep-value site (spec §Round 8): ``role_value × [P(met | keep) − P(met |
    shuffle)]`` with ``P(met | keep) = deadline_odds`` and ``P(met | shuffle) = deadline_odds ×
    reaccess`` — the ``deadline_odds`` factors out."""
    if role_value <= 0:
        return 0.0
    return role_value * max(0.0, min(1.0, deadline_odds)) * max(0.0, min(1.0, 1.0 - reaccess_odds))
