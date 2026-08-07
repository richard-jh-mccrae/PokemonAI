"""HOLD price: what SPENDING a held card costs, for every free-Item decider (ADR-0062, Issue #261).

    hold(card) = max( needs.keep_v2(card), ITEM_HOLD_FLOOR ) x currency rate

Free Items are tiered first by `pilot._finish_turn_last`, so a purely POSITIVE term can never DECLINE
one; the floor prices finiteness `keep_v2` cannot see (a whiffing Hammer assigns exactly 0).
"""
from __future__ import annotations

# Read the rate through the MODULE: a `from currency import ...` binding would let a re-pointed rate
# be silently ignored here.
from common import currency

#: Finiteness floor in WORTH points. AUTHORED, not derived — whitelisted under
#: `sound_rules.firing-equation-constants`; the value is `_DENIAL_ITEM_COST`'s, re-homed (ADR-0062).
ITEM_HOLD_FLOOR = 10.0


def hold_price(keep_worth: float) -> float:
    """`keep_worth` is Worth points (`needs.keep_v2`); the return is DAMAGE currency. Always strictly
    positive, so a decider subtracting it can reach a negative score and DECLINE a free Item."""
    worth = max(0.0, float(keep_worth), ITEM_HOLD_FLOOR)
    return currency.item_hold_to_damage(worth)


__all__ = ("ITEM_HOLD_FLOOR", "hold_price")
