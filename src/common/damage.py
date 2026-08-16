"""The damage oracle (ADR-0032): the ONE closed-form Tier-0 damage computation.

`compute_active_damage` is the single seam where per-attack effect facts (`AttackStat`) meet card
facts (`CardStat` Weakness/Resistance) and defender-side prevention. Pure and lib-free: the engine
audit calls it directly without a Pilot.

Per-target: the defending ACTIVE only. A bench-snipe rider is a separate path
(``AttackStat.benchSnipe``) — it ignores W/R by rule and the Active's own prevention does not stop it.
"""
from __future__ import annotations

_RESISTANCE = 30       # flat S&V Resistance reduction — engine-verified (tools/sim/probe_resistance.py)
_PREVENT_EX_TAG = "prevent_ex_damage"

#: The OPEN filtered-count family (ADR-0115), family -> the context key holding its RAW MATERIAL.
#: ``AttackStat.scaleFilter`` carries the predicate's argument; the vocabulary of families stays CLOSED.
_FILTERED_COUNTS = {
    "both_in_play_named": "both_in_play_names",
    "atk_in_play_with_attack": "atk_in_play_attack_names",
}


def _filtered_count(var: str, material, terms: tuple) -> int:
    """How many units the filtered-count ``var`` sees in ``material`` under ``terms``. SUBSTRING and
    case-sensitive — an owner prefix is part of the printed name (`docs/rules.md` §9). Fails CLOSED."""
    if var == "both_in_play_named":
        return sum(1 for n in material if n and any(t in n for t in terms))
    return sum(1 for names in material if any(t in names for t in terms))


def wr_adjust(attacker, defender, dmg: float) -> float:
    """The attack-BLIND Weakness/Resistance rule (ADR-0052): x2 on Weakness, then a flat -30 Resistance
    floored at 0, vs the ATTACKER's type (rules.md §5). For fallbacks where no attack record resolves."""
    if not (dmg and attacker and defender and attacker.energyType is not None):
        return dmg
    if defender.weakness is not None and defender.weakness == attacker.energyType:
        dmg *= 2
    if defender.resistance is not None and defender.resistance == attacker.energyType:
        dmg = max(0, dmg - _RESISTANCE)
    return dmg


def compute_active_damage(attack, attacker, defender, defender_tags=frozenset(), *,
                          bound: str = "exact", context: dict | None = None,
                          defender_transient: dict | None = None) -> float:
    """Closed-form damage this attack deals to the defending Active (ADR-0032 E1). ``bound``: ``"min"`` the
    sound floor, ``"max"`` the ceiling, ``"exact"`` printed. Fail-open — a missing stat invents no modifier."""
    if attack is None:
        return 0
    if (getattr(attack, "requiresBench", None) and bound != "max"
            and (context or {}).get("atk_bench_names") is not None
            and not all(n in context["atk_bench_names"] for n in attack.requiresBench)):
        # A bench-partner condition unmet on the LIVE board: 0 this decision (exact AND min). The "max"
        # bound keeps printed — Incoming is a worst case and they can bench the partner before attacking.
        return 0
    dmg = float(attack.damage or 0)
    if bound == "min" and attack.damageMin is not None:
        dmg = float(attack.damageMin)
    elif bound == "max" and attack.damageMax is not None:
        dmg = float(attack.damageMax)
    if attack.scaleVar == "atk_discard_energy" and attack.scalePerUnit and context:
        # attacker's discard is OPEN info for both players (Riptide-class): typed filter reads
        # the Basic-Energy histogram, untyped counts every Energy card
        if attack.scaleEnergyType is not None:
            units = (context.get("atk_discard_basic_by_type") or {}).get(attack.scaleEnergyType)
        else:
            units = context.get("atk_discard_energy_total")
        if units is not None:
            dmg += attack.scalePerUnit * units
    elif attack.scaleVar in _FILTERED_COUNTS and attack.scalePerUnit and attack.scaleFilter:
        # An OPEN filtered count: the family names the context key, the ATTACK names the predicate. No
        # filter -> no claim at all; falling through to "count everything in play" would be an over-read.
        material = (context or {}).get(_FILTERED_COUNTS[attack.scaleVar])
        if material is not None:
            dmg += attack.scalePerUnit * _filtered_count(attack.scaleVar, material,
                                                         tuple(attack.scaleFilter))
    elif attack.scaleVar and attack.scalePerUnit and (context or {}).get(attack.scaleVar) is not None:
        dmg += attack.scalePerUnit * context[attack.scaleVar]
    if attack.hiddenPerUnit and attack.hiddenSample:
        # Hidden-state deck-discard scaler: hidden ORDER but EXACT deck facts, so the distribution is
        # known — pigeonhole floor is SOUND, hypergeometric mean is "exact", ceiling is min(sample, fuel).
        units = (context or {}).get("hidden_units")
        deck_n = (context or {}).get("atk_deck_count")
        fuel = ((context or {}).get("atk_deck_basic_by_type") or {}).get(attack.hiddenEnergyType) \
            if attack.hiddenEnergyType is not None else None
        if units is None and deck_n and fuel is not None:
            sample = min(attack.hiddenSample, deck_n)
            if bound == "min":
                units = max(0, sample - (deck_n - fuel))
            elif bound == "max":
                units = min(sample, fuel)
            else:
                units = int(sample * fuel / deck_n)            # hypergeometric mean, floored
        if units is not None:
            dmg += attack.hiddenPerUnit * units
        elif bound == "max":
            dmg += attack.hiddenPerUnit * attack.hiddenSample  # no deck facts: assume every card fuels
    if not dmg:
        return 0
    for amount, atype, vs_ex in (context or {}).get("atk_boosts") or ():
        # Flat Trainer damage-boosts live for this attack — "before applying Weakness and Resistance",
        # and only onto an attack already dealing damage (a boost never turns a 0 into 30).
        if atype is not None and (attacker is None or attacker.energyType != atype):
            continue
        if vs_ex and not (defender is not None and defender.is_ex_body):
            continue
        dmg += amount
    if not attack.ignoresEffects and _prevented(attacker, defender, defender_tags):
        return 0
    atype = attacker.energyType if attacker is not None else None
    if atype is not None and defender is not None:
        if not attack.ignoresWeakness and defender.weakness == atype:
            dmg *= 2
        if not attack.ignoresResistance and defender.resistance == atype:
            dmg = max(0, dmg - _RESISTANCE)
    if not attack.ignoresEffects and defender is not None:
        # defender-side facts (ADR-0032 G1) — both explicitly AFTER Weakness/Resistance:
        reduction = getattr(defender, "damageReduction", 0)
        r_types = getattr(defender, "damageReductionTypes", None)
        if reduction and (r_types is None or atype in r_types):   # Dewgong: {R}/{W} attackers only
            dmg = max(0, dmg - reduction)
        threshold = getattr(defender, "preventsDamageAtLeast", 0)
        if threshold and dmg >= threshold:                 # Drednaw: big-enough hit is prevented
            return 0
    if not attack.ignoresEffects and defender_transient:
        # LIVE transient grant on defending body (ADR-0033: Frost Barrier's -30, a prevent-all
        # wall) — effect on the Active, so Nebula class pierces it too
        if defender_transient.get("prevent_all"):
            return 0
        if defender_transient.get("reduction"):
            dmg = max(0, dmg - defender_transient["reduction"])
    return dmg


def _prevented(attacker, defender, defender_tags) -> bool:
    """The defender's Ability prevents this attacker's damage outright — the `prevent_ex_damage` tag OR
    ``CardStat.preventsDamageFrom`` ("ex", or "basic_ex" which also requires a Basic attacker)."""
    if attacker is None or not attacker.is_ex_body:
        return False
    if _PREVENT_EX_TAG in (defender_tags or frozenset()):
        return True
    scope = getattr(defender, "preventsDamageFrom", None) if defender is not None else None
    if scope == "ex":
        return True
    return scope == "basic_ex" and not getattr(attacker, "evolvesFrom", None)


def bench_reach(attack) -> int:
    """Single-target bench damage: snipe hits one target; spread counters can all concentrate
    on one, so its total is an equivalent no-split reach."""
    return max(int(getattr(attack, "benchSnipe", 0) or 0),
               int(getattr(attack, "benchSpread", 0) or 0))
