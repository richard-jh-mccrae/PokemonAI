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
The value is the damage their best AFFORDABLE attack loses when one Energy leaves:

    Mega Lucario ex — Aura Jab {F} 130, Mega Brave {F}{F} 270

      2 Energy: best 270 -> strip -> 130   denies 140   (the nuke goes off)
      1 Energy: best 130 -> strip ->   0   denies 130   (the attacker goes off)
      3 Energy: best 270 -> strip -> 270   denies   0   (SURPLUS — the Hammer does nothing)

Closed-form off the attack table and their visible Energy, in the same shape as the KO oracle.
"""
from __future__ import annotations


def best_affordable_damage(energy: int, attacks: dict) -> int:
    """Damage of the best attack this Pokémon can PAY FOR with `energy` Energy attached.

    `attacks` is ``{attack_id: (cost, damage)}``. 0 when nothing is affordable — a body holding
    Energy it cannot convert into an attack is not a threat, and stripping it denies nothing.
    """
    return max((dmg for cost, dmg in attacks.values() if cost <= energy), default=0)


def denial_value(energy: int, attacks: dict, *, removed: int = 1) -> int:
    """Damage this Pokémon LOSES if `removed` Energy is discarded from it — the honest worth of a
    Hammer aimed here. Zero when the Energy is SURPLUS (they still afford the same attack) or when
    they could not afford an attack in the first place. Never negative."""
    before = best_affordable_damage(energy, attacks)
    after = best_affordable_damage(max(0, energy - removed), attacks)
    return max(0, before - after)


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
