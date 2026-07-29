"""Currency — the exchange rates between the value scales, DERIVED and never tuned (ADR-0077).

The codebase speaks **three** value scales, and until ADR-0077 only one pair of them had a bridge:

  * **damage / tactical** — the `score` the doctrines and rungs compete on. `KO_SCORE = 1000` is its
    dominance band; `_DENIAL_PLAY_W = 1.0` is "points per damage point denied"; `ENERGY_RECOVER = 75`
    is labelled chip-scale. The attach (ADR-0069) and evolve (ADR-0070) marginals live here.
  * **prizes / prize-equivalents** — `combat.prize_value` (Mega ex 3, ex 2, else 1; rules.md §6) and
    the opponent-target marginal `needs.opponent_target_value` (0 – 3.9).
  * **card-worth points** — what the Needs DP *sums* (`card_worth.ROLE_TIER` ≤ 30, `ENERGY_TIER` 8,
    `TAG_TIER` 10–30). `needs.py`'s "ONE currency" claim scopes to this scale alone.

This module owns the conversions. A prize-denominated value must never be consumed raw by a
consumer that counts in another scale (ADR-0077 decision 2) — that is how `_PRIZE_UNIT = 12` came to
assert roughly an eighth of honest value and made the promote/retreat equation endorse feeding a
3-prize body to save a 40-point band.
"""
from __future__ import annotations

#: The **Prize Damage Rate** — damage per prize, bridging prizes ↔ damage.
#:
#: DERIVED, not tuned: the MEDIAN HP-per-prize over every body in the set — 1061 bodies in
#: `data/EN_Card_Data.csv` at the `docs/rules.md` §6 prize values, median **100.0** (mean 101.5; per
#: band 90 / 130 / 110). Recomputable and falsifiable, which is the whole point —
#: `tests/strategy/test_currency.py` recomputes it from the CSV rather than pinning the literal, so a
#: future set re-derives it instead of inheriting it. The superseded `_PRIZE_UNIT = 12` asserted
#: roughly an eighth of this, which is why the shipped equation endorsed feeding a 3-prize body to
#: save a 40-point band.
#:
#: Ratified by ADR-0073 (promote/retreat, its first consumer) and HOISTED here by ADR-0077 (#187
#: grill) once three more consumers arrived — the deny / snipe / gust marginals of the
#: opponent-target family, each of which must convert its prize-denominated slice before it can meet
#: a damage-scale score. It deliberately does NOT reach `KO_SCORE` (the KO's dominance band is
#: unbounded by this rate) or Worth (see below).
PRIZE_DAMAGE_RATE = 100.0


# ── The Worth Damage Rate — the MISSING third leg (ADR-0077 decision 2/3) ─────────────────────────
#
# There is deliberately NO `WORTH_DAMAGE_RATE` constant in this module yet, and adding one without
# the derivation below is the exact fudge ADR-0065 forbids.
#
# The missing bridge is **damage per card-worth point**, from which prize → worth composes as
# `PRIZE_DAMAGE_RATE / WORTH_DAMAGE_RATE`. It cannot be read off the shipped constants, because two
# pairs price the SAME object on both scales and disagree by ~6.7x:
#
#     keeping a gust/denial Trainer   TAG_TIER["gust"] 10.0   vs  _DENIAL_ITEM_COST 10     =>  ~1
#     one Energy                      ENERGY_TIER      8.0    vs  ENERGY_RECOVER   160/3   =>  ~6.7
#
# The gap was ~9x until Issue #172 DERIVED `ENERGY_RECOVER` from the card set (75 -> 160/3). That it
# moved without closing is the point: deriving one leg honestly did not reveal a hidden worth rate,
# which is evidence the bridge has to come from a corpus ruling rather than from the tiers.
#
# So it needs a corpus anchor, and the corpus does not currently hold one: every committed deny
# fixture is a play/hold frame (`select.context = 0`), none a DISCARD select, and the one keep-side
# Hammer ruling (`86091435-68`) is REFUTED-AS-LABELED and directional. Capturing that anchor is
# issue #199's build-shape step 1 — an adjudication with the user, not a computation.
#
# Until it lands, consumers that would need this rate stay on their incumbent scale and say so.


def prize_to_damage(prize_equivalents: float) -> float:
    """Convert a prize-denominated value into the damage/tactical scale at the derived rate.

    The one legitimate way for a prize-equivalent marginal (`needs.opponent_target_value`) to enter a
    `score` the damage-scale rungs also write to. Callers that hold a *card-worth* value want the
    Worth Damage Rate instead — which does not exist yet, on purpose (see above)."""
    return float(prize_equivalents) * PRIZE_DAMAGE_RATE
