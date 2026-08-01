"""ORACLE: Energy denial — ADR-0062. What discarding one Energy actually takes away.

  Crushing Hammer (1120, Item): "Flip a coin. If heads, discard an Energy from 1 of your opponent's
                                 Pokémon."          <- ANY Pokémon: Active OR Bench
  Enhanced Hammer  (1081, Item): "Discard a Special Energy from 1 of your opponent's Pokémon."

Both target *any* of their Pokémon, and the engine agrees: `op_trash_energy_enemy`
(`src/cgpy/chain.py`, trace-verified against the native engine and pinned to ml_dx_2001 f175 /
ms_mirror_1002 f14) builds its option list from ACTIVE **+** BENCH. `activeOnly` is a different
flavour — the attack-rider one — which Crushing Hammer does not set.

**A Hammer is worth exactly what it stops them doing.** Not "do they have Energy" — that is what the
pre-ADR-0062 rung asked, and it is why Hammers burned on bodies carrying more Energy than they needed.

⚠️ **The MAGNITUDE half of this module is DELETED** (Issue #228, tracker directive 1: *"rungs an
equation replaces are DELETED, not suppressed"*). `best_affordable_damage` and `denial_value` priced
a strip in damage — *"the damage their best AFFORDABLE attack loses when one Energy leaves"* — and
were the arithmetic behind `Pilot._denial_at` / `_opp_denial_best`. ADR-0080 re-derived deny as a
**categorical relevance** instrument rather than a magnitude one, `common/deny_relevance.py` now owns
the scoring end to end, and Issue #228 armed it and removed the incumbent. The two functions
outlived their last production consumer by that one commit.

What survives here is the **COIN**, which relevance does not model and still needs: half of all
Crushing Hammers do nothing whatever the board looks like.
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
