"""The damage oracle (ADR-0032): the ONE closed-form Tier-0 damage computation.

`compute_active_damage` is the single seam where per-attack effect facts (`AttackStat` — the
ignore-flag family) meet card facts (`CardStat` Weakness/Resistance) and defender-side prevention
(the `prevent_ex_damage` Function Tag): every closed-form damage estimate — my attacks AND the
opponent's Incoming — routes through it, so a new mechanic lands in exactly ONE place and the
engine audit diffs exactly one function. Pure and lib-free: the audit calls it directly without a
Pilot. Subsumes the attack-blind `_wr_adjusted` + `_ability_prevents_damage` pair: the old pair
zeroed EVERY attack into Crustle — including Nebula Beam, which ignores the defender's effects and
lands 210 (the ADR-0032 motivating blunder).

Per-target semantics: this computes damage to the defending ACTIVE only. A bench-snipe rider is a
separate path (``AttackStat.benchSnipe``) — it ignores Weakness/Resistance by rule and is NOT
stopped by the Active's own prevention (Jetting Blow deals 0 to Crustle but its 50 still snipes).
"""
from __future__ import annotations

_RESISTANCE = 30       # flat S&V Resistance reduction — engine-verified (tools/sim/probe_resistance.py)
_PREVENT_EX_TAG = "prevent_ex_damage"


def compute_active_damage(attack, attacker, defender, defender_tags=frozenset(), *,
                          bound: str = "exact", context: dict | None = None,
                          defender_transient: dict | None = None) -> float:
    """Closed-form damage this attack deals to the defending Active (ADR-0032 E1).

    The base damage — printed, or the attack's conditional ``bound`` (see below) — then, unless
    the attack's own ignore flag pierces the modifier — the defender's damage-prevention Ability
    (`prevent_ex_damage` vs an ex/Mega attacker → 0), Weakness (x2), and Resistance (-30, floored
    at 0), in rules order (rules.md §5). Fail-open: a missing stat/tag never invents a modifier —
    degrade to printed damage (matching `_wr_adjusted` / `_ability_prevents_damage` semantics).

    Args:
        attack: the ``AttackStat`` record (None → 0: no attack, no damage).
        attacker: the attacking Pokémon's ``CardStat`` (ex-ness, energy type), or None.
        defender: the defending Active's ``CardStat`` (weakness/resistance types), or None.
        defender_tags: the defender's Function Tags (prevention lives there), if known.
        bound: which damage a conditional/coin attack contributes — ``"min"`` its sound floor
            (the Lethal Solver: never lock a phantom win), ``"max"`` its ceiling (Incoming:
            worst case), ``"exact"`` the printed damage (the scoring heuristics' status quo).
            A deterministic attack (bounds None) reads printed under every bound.
        context: visible-state counts for a scaling attack (ADR-0032 Damage Formula) —
            ``{"atk_hand", "def_hand", "def_active_energy", "atk_active_energy"}``, attacker-
            relative. Scaling is EXACT when its variable is supplied (every var is public);
            with no context the term contributes 0 (a sound floor, a weak ceiling).

    Returns:
        The predicted damage to the Active (never negative).
    """
    if attack is None:
        return 0
    dmg = float(attack.damage or 0)
    if bound == "min" and attack.damageMin is not None:
        dmg = float(attack.damageMin)
    elif bound == "max" and attack.damageMax is not None:
        dmg = float(attack.damageMax)
    if attack.scaleVar == "atk_discard_energy" and attack.scalePerUnit and context:
        # the attacker's discard is OPEN information for both players (Riptide-class): a typed
        # filter reads the Basic-Energy histogram, an untyped one counts every Energy card
        if attack.scaleEnergyType is not None:
            units = (context.get("atk_discard_basic_by_type") or {}).get(attack.scaleEnergyType)
        else:
            units = context.get("atk_discard_energy_total")
        if units is not None:
            dmg += attack.scalePerUnit * units
    elif attack.scaleVar and attack.scalePerUnit and (context or {}).get(attack.scaleVar) is not None:
        dmg += attack.scalePerUnit * context[attack.scaleVar]
    if attack.hiddenPerUnit and attack.hiddenSample:
        # hidden-state deck-discard scaler (Hammer-lanche class): the units are hidden card ORDER,
        # but with EXACT deck facts (the tracker-anchored deck) the distribution is known: the
        # pigeonhole floor is SOUND (any `sample` cards off a deck of N with F fuel hit at least
        # sample-(N-F)), the hypergeometric mean prices "exact", the ceiling caps at min(sample, F).
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
            dmg += attack.hiddenPerUnit * attack.hiddenSample  # no deck facts: every card fuels
    if not dmg:
        return 0
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
        if threshold and dmg >= threshold:                 # Drednaw: a big-enough hit is prevented
            return 0
    if not attack.ignoresEffects and defender_transient:
        # a LIVE transient grant on the defending body (ADR-0033: Frost Barrier's -30, a
        # prevent-all wall) — an effect on the Active, so the Nebula class pierces it too
        if defender_transient.get("prevent_all"):
            return 0
        if defender_transient.get("reduction"):
            dmg = max(0, dmg - defender_transient["reduction"])
    return dmg


def _prevented(attacker, defender, defender_tags) -> bool:
    """The defender's Ability prevents this attacker's damage outright — the boolean
    `prevent_ex_damage` Function Tag OR the parsed ``CardStat.preventsDamageFrom`` field
    ("ex" — Crustle/Sylveon (the tag misses Sylveon); "basic_ex" — Farigiraf ex, where the
    attacker must also be Basic, i.e. carry no ``evolvesFrom``). False on missing stats."""
    if attacker is None or not (attacker.ex or attacker.megaEx):
        return False
    if _PREVENT_EX_TAG in (defender_tags or frozenset()):
        return True
    scope = getattr(defender, "preventsDamageFrom", None) if defender is not None else None
    if scope == "ex":
        return True
    return scope == "basic_ex" and not getattr(attacker, "evolvesFrom", None)
