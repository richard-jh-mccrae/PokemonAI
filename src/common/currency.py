"""Exchange rates between the three value scales — damage/tactical, prize-equivalents, card-worth —
DERIVED and never tuned (ADR-0078). A value in one scale is never consumed raw by another."""
from __future__ import annotations

# `card_worth` is a leaf, so this cannot cycle.
from common.card_worth import ROLE_TIER as _ROLE_TIER, TAG_TIER as _TAG_TIER
# `needs` imports only leaves and never this module, so this cannot cycle either — but every importer
# of `currency` now pulls `needs` transitively.
from common.needs import TARGET_VALUE_CEILING as _TARGET_VALUE_CEILING

#: Damage per prize. DERIVED, not tuned: the MEDIAN HP-per-prize over the whole card set (ADR-0078;
#: `tests/strategy/test_currency.py` recomputes it from the CSV). Reaches neither `KO_SCORE` nor Worth.
PRIZE_DAMAGE_RATE = 100.0


# There is deliberately NO general `WORTH_DAMAGE_RATE` — the corpus anchor gate RAN and FAILED
# (ADR-0080/0086). The three seam-scoped rates below are the honest exceptions, labelled at each site.


#: The deploy ratios' yardstick — the top `ROLE_TIER` band, read at import so a re-band moves it.
#: Deliberately FIXED and board-independent: a per-decision normaliser would deploy every turn.
DEPLOY_WORTH_SCALE = max(_ROLE_TIER.values())     # == 30.0 (win_condition / primary_attacker)

#: A FULL-relevance deploy on the damage scale — a PRESERVATION CHOICE, never a derivation (ADR-0086),
#: pinned to the incumbent +12..+25 rung range. Divided by `DEPLOY_WORTH_SCALE` it is the third rate.
DEPLOY_BAND = 25.0


def deploy_relevance_to_damage(relevance: float) -> float:
    """Callers hand a RATIO (a Needs marginal already divided by `DEPLOY_WORTH_SCALE`), never a raw
    worth value — that would be the scale-boundary crossing ADR-0078 decision 2 forbids."""
    return float(relevance) * DEPLOY_BAND


#: Damage per card-worth point AT THE ITEM-HOLD SEAM — a worth<->damage rate, scoped to one seam.
#: A PRESERVATION CHOICE, never a derivation: the ratio the deleted `_DENIAL_ITEM_COST` asserted.
ITEM_HOLD_WORTH_RATE = 1.0


def item_hold_to_damage(keep_worth: float) -> float:
    """Callers hand a WORTH magnitude (a `needs` marginal floored by `hold_value.ITEM_HOLD_FLOOR`),
    never a prize-equivalent — that is `prize_to_damage`."""
    return float(keep_worth) * ITEM_HOLD_WORTH_RATE


#: A FULL-ceiling gust target on the WORTH scale — a PRESERVATION CHOICE, not a derivation: it IS
#: `TAG_TIER["gust"]`, read at import so a re-band of the tiers moves it with it (ADR-0107).
GUST_TARGET_BAND = _TAG_TIER["gust"]                  # == 10.0

#: Worth per prize-equivalent AT THE GUST-TARGET SEAM — a prize<->worth rate, scoped to one seam. It
#: DISAGREES ~39x with the composed `PRIZE_DAMAGE_RATE / ITEM_HOLD_WORTH_RATE`; recorded, unreconciled.
GUST_TARGET_WORTH_RATE = GUST_TARGET_BAND / _TARGET_VALUE_CEILING     # ~= 2.564


def target_value_to_worth(prize_equivalents: float) -> float:
    """Callers hand a PRIZE-EQUIVALENT (an `_opponent_target_rows` ``value``), never a worth magnitude.
    The clamp is unreachable for every shipped caller; it bounds a future 4-prize body."""
    return max(0.0, min(float(prize_equivalents), _TARGET_VALUE_CEILING)) * GUST_TARGET_WORTH_RATE


def prize_to_damage(prize_equivalents: float) -> float:
    """Callers holding a *card-worth* value want the Worth Damage Rate, which does not exist."""
    return float(prize_equivalents) * PRIZE_DAMAGE_RATE


def tiebreak_bonus(relevances, k: float) -> float:
    """Half the finest distinction a ``[0,1]`` relevance menu draws, in SCORE units — so a tiebreak
    cannot overtake a difference relevance settled. ``1 / k`` (one damage unit) when the menu is flat."""
    distinct = sorted(set(relevances))
    gaps = [b - a for a, b in zip(distinct, distinct[1:]) if b > a]
    return 0.5 * float(k) * (min(gaps) if gaps else (1.0 / float(k)))
