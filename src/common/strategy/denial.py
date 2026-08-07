"""ORACLE: Energy denial — ADR-0062. What discarding one Energy actually takes away.

A Hammer targets ANY of their Pokémon, Active OR Bench, and the engine agrees (`op_trash_energy_enemy`,
`src/cgpy/chain.py`); `activeOnly` is the attack-rider flavour, which Crushing Hammer does not set.

The MAGNITUDE half of this module is DELETED (Issue #228): `common/deny_relevance.py` owns the scoring
end to end. What survives is the **COIN**, which relevance does not model and still needs.
"""
from __future__ import annotations


# COIN facts, id-keyed, verified at data/EN_Card_Data.csv. A denial Item that flips is worth its
# odds: half of all Crushing Hammers do nothing whatever the board looks like.
_DENIAL_COIN = {
    1120: 0.5,   # Crushing Hammer — "FLIP A COIN. If heads, discard an Energy from 1 of your
                 #                    opponent's Pokemon."
    1081: 1.0,   # Enhanced Hammer — no flip. (Special Energy only; the damage model below does not
                 #                    yet filter by Energy type, and no deck in the pool runs it.)
}


def coin_odds(card_id) -> float:
    """P(the denial actually lands). 1.0 for a deterministic strip; 0.5 for Crushing Hammer."""
    return _DENIAL_COIN.get(card_id, 1.0)
