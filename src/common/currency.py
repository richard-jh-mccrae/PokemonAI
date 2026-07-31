"""Currency — the exchange rates between the value scales, DERIVED and never tuned (ADR-0078).

The codebase speaks **three** value scales, and until ADR-0078 only one pair of them had a bridge:

  * **damage / tactical** — the `score` the doctrines and rungs compete on. `KO_SCORE = 1000` is its
    dominance band; `_DENIAL_PLAY_W = 1.0` is "points per damage point denied"; `ENERGY_RECOVER = 75`
    is labelled chip-scale. The attach (ADR-0069) and evolve (ADR-0070) marginals live here.
  * **prizes / prize-equivalents** — `combat.prize_value` (Mega ex 3, ex 2, else 1; rules.md §6) and
    the opponent-target marginal `needs.opponent_target_value` (0 – 3.9).
  * **card-worth points** — what the Needs DP *sums* (`card_worth.ROLE_TIER` ≤ 30, `ENERGY_TIER` 8,
    `TAG_TIER` 10–30). `needs.py`'s "ONE currency" claim scopes to this scale alone.

This module owns the conversions. A prize-denominated value must never be consumed raw by a
consumer that counts in another scale (ADR-0078 decision 2) — that is how `_PRIZE_UNIT = 12` came to
assert roughly an eighth of honest value and made the promote/retreat equation endorse feeding a
3-prize body to save a 40-point band.
"""
from __future__ import annotations

# The Worth scale itself, for the deploy yardstick at the foot of this module. `card_worth` is a
# leaf (it imports nothing from `common`), so this cannot cycle.
from common.card_worth import ROLE_TIER as _ROLE_TIER

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
#: Ratified by ADR-0073 (promote/retreat, its first consumer) and HOISTED here by ADR-0078 (#187
#: grill) once three more consumers arrived — the deny / snipe / gust marginals of the
#: opponent-target family, each of which must convert its prize-denominated slice before it can meet
#: a damage-scale score. It deliberately does NOT reach `KO_SCORE` (the KO's dominance band is
#: unbounded by this rate) or Worth (see below).
PRIZE_DAMAGE_RATE = 100.0


# ── The Worth Damage Rate — the MISSING third leg (ADR-0078 decision 2/3) ─────────────────────────
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
# Hammer ruling (`86091435-68`) is REFUTED-AS-LABELED and directional.
#
# **That anchor gate has now been RUN, and it FAILED — the constant is absent BY DESIGN, not
# pending** (ADR-0080, Issue #199). Corpus-wide there are 12 `Discard`-context frames; exactly one
# holds a Hammer, and on that board the opponent's Archaludon ex carries one {M} against a {M}{M}{M}
# attack, so both instruments price the strip at 0.000 — with `m = 0` the rate DIVIDES OUT and no
# value is derivable from it under any policy. ADR-0080 then made the question moot for deny
# entirely, by reformulating deny as a CATEGORICAL RELEVANCE instrument that never crosses a scale
# boundary. Deny was the last consumer asking for the rate.
#
# ADR-0086 (Issue #197) asked the same question of the DEPLOY seam, which ADR-0078 decision 3 had
# nominated as more promising because its frames are natively play-side. `deploy_anchor_sweep.py`
# answers no, and for a STRUCTURAL reason rather than a corpus gap: a deploy is never exclusive with
# a damage-denominated option (benching consumes no attach, no Supporter slot, and does not end the
# turn), so it cannot TRADE against one, and the only genuine competitor for a Bench slot is another
# deploy — worth versus worth, carrying no rate information.
#
# Consumers that would need this rate stay on their incumbent scale and say so.


# ── The DEPLOY band — a SEAM-SCOPED rate, honestly labelled (ADR-0086 amendment C, Issue #197) ────
#
# The Deploy Marginal's two Worth-denominated legs are dimensionless RATIOS — a marginal over the
# `needs.py` assignment divided by `DEPLOY_WORTH_SCALE` — so the Worth points cancel and the Worth
# scale never escapes the assignment. That is what lets the equation exist without the constant
# above.
#
# **Stated plainly rather than buried: `DEPLOY_BAND / DEPLOY_WORTH_SCALE` has units of
# damage-per-worth-point. It IS a worth<->damage rate, scoped to one seam.** Amendment B made the
# rate local, small and honestly labelled — it did not make it unnecessary. This is a THIRD entry in
# the catalogue two paragraphs up (trainer ~1.0, energy ~6.7, deploy ~`DEPLOY_BAND / 30`).
#
# The one honest mitigation, not oversold: ADR-0078's complaint was that two constants priced the
# SAME object differently. Nothing else in this codebase prices a bench deployment, so this constant
# contradicts nothing today.
#
# RECONCILIATION DEBT, recorded here so it is tripped over rather than discovered: if a general
# Worth Damage Rate is ever derived, `DEPLOY_BAND / DEPLOY_WORTH_SCALE` must be checked against it,
# and a disagreement is evidence about ONE of the two rather than automatically about this one.

#: The yardstick the deploy relevance ratios divide by — the ceiling on what a SINGLE card can
#: contribute to the Needs assignment, i.e. the top `ROLE_TIER` band. **Derived, not invented**: an
#: arbitrary divisor would be the ADR-0065 fudge wearing a different hat. Read off `card_worth` at
#: import so a re-band of the tiers moves the yardstick with it rather than silently re-scaling every
#: deploy score.
#:
#: It is deliberately FIXED and board-independent. Normalising per decision instead (dividing by the
#: best candidate at THIS decision) was rejected on correctness: the marginal competes against `End`
#: (0) and against attacks, so the ratio must mean the same thing on every board — a per-decision
#: normaliser would make the best available deploy read 1.0 whether it is excellent or merely
#: least-bad, and the agent would deploy every turn.
DEPLOY_WORTH_SCALE = max(_ROLE_TIER.values())     # == 30.0 (win_condition / primary_attacker)

#: What a FULL-relevance deploy is worth on the damage scale.
#:
#: **A PRESERVATION CHOICE, never a derivation** (ADR-0080 decision 3's discipline for its `K`,
#: applied verbatim). It is pinned so the equation reproduces the incumbent range of the rungs it
#: replaces — `develop-a-basic-in-setup` +12, `develop-the-wincon-base-first` +6 riding on it,
#: `develop-the-accel-recipient` +20, `pre-position-attacker` +25, `bench-the-supporter-tutor` +25 —
#: so the swap starts behaviour-preserving and the Decision Gate can then rule every flip.
#:
#: That gate is the whole difference between this constant and ADR-0073's `_PRIZE_UNIT = 12`, which
#: was wrong by ~8x and endorsed feeding a 3-prize body to save a 40-point band: same species of
#: number, but this one is checked against recorded frames rather than asserted.
#:
#: One bound the corpus supplies directly (ADR-0086 amendment D, frame `85709280|1|match|`): the
#: human ruled Lillie's Determination (`dig-before-commit`, +20) OVER a redundant second Solrock
#: into the last Bench slot, so `DEPLOY_BAND x relevance(that Solrock) < 20`. Weak — the relevance
#: should be ~0 on that board anyway — but real, and gated.
DEPLOY_BAND = 25.0


def deploy_relevance_to_damage(relevance: float) -> float:
    """Convert a dimensionless deploy relevance in [0, 1] into the damage/tactical scale.

    The ONE place the Deploy Marginal's Worth-derived legs enter a `score` the damage-scale rungs
    also write to. Callers hand a RATIO (a Needs-assignment marginal already divided by
    `DEPLOY_WORTH_SCALE`), never a raw worth value — handing this a worth magnitude would be
    exactly the scale-boundary crossing ADR-0078 decision 2 forbids."""
    return float(relevance) * DEPLOY_BAND


def prize_to_damage(prize_equivalents: float) -> float:
    """Convert a prize-denominated value into the damage/tactical scale at the derived rate.

    The one legitimate way for a prize-equivalent marginal (`needs.opponent_target_value`) to enter a
    `score` the damage-scale rungs also write to. Callers that hold a *card-worth* value want the
    Worth Damage Rate instead — which does not exist yet, on purpose (see above)."""
    return float(prize_equivalents) * PRIZE_DAMAGE_RATE


def tiebreak_bonus(relevances, k: float) -> float:
    """Half the finest distinction a menu of ``[0,1]`` relevance values actually draws, in SCORE units.

    The shared arithmetic behind BOTH relevance instruments' lexicographic tiebreaks — deny's
    (ADR-0084, Issue #217 decision 2) and snipe's (ADR-0085 Amendment H, Issue #188). The two keep
    their OWN guards, which differ on purpose: deny declines to order a zero because its ordering
    signal is derived from the same board, snipe orders one because the Brief is independent authored
    scouting. Only this quantum is common, and it lives here because it is the piece most likely to
    drift apart unnoticed — the two copies had already grown a stale cross-reference between them by
    the time it was extracted.

    ``k`` is the instrument's normalizer, so ``k x relevance`` is its score and two distinct relevance
    values differ by at least ``1 / k``. Half the smallest REAL gap on the menu therefore can never
    overtake a difference relevance itself settled; ``1 / k`` — one damage unit — is the fallback when
    the menu draws no distinction at all, which is exactly the all-zero case snipe must still order.

    Deriving it beats fixing it: a hardcoded epsilon is sized against the arithmetic in front of it
    and rots silently the first time a term changes that arithmetic — the ADR-0063 failure mode, where
    a new positive term voided every guard calibrated against the previous scale with nothing failing
    loudly.
    """
    distinct = sorted(set(relevances))
    gaps = [b - a for a, b in zip(distinct, distinct[1:]) if b > a]
    return 0.5 * float(k) * (min(gaps) if gaps else (1.0 / float(k)))
