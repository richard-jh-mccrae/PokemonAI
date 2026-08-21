"""The damage oracle (ADR-0032): the ONE closed-form Tier-0 damage computation.

`compute_active_damage` is the single seam where an Attack record's effect Clauses meet the
PokemonCard records' Weakness/Resistance and defender-side prevention. Pure and lib-free: the
engine audit calls it directly without a Pilot.

Per-target: the defending ACTIVE only. A bench-snipe rider is a separate path (the Attack's
``bench_snipe`` clause) — it ignores W/R by rule and the Active's own prevention does not stop it.
"""
from __future__ import annotations

_RESISTANCE = 30       # flat S&V Resistance reduction — engine-verified (tools/sim/probe_resistance.py)
#: The OPEN filtered-count family (ADR-0115), family -> the context key holding its RAW MATERIAL.
#: The scale clause's ``filter`` carries the predicate's argument; the family vocabulary stays CLOSED.
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
    if not (dmg and attacker and defender and attacker.energy_type is not None):
        return dmg
    if defender.weakness is not None and defender.weakness == attacker.energy_type:
        dmg *= 2
    if defender.resistance is not None and defender.resistance == attacker.energy_type:
        dmg = max(0, dmg - _RESISTANCE)
    return dmg


def compute_active_damage(attack, attacker, defender, *,
                          bound: str = "exact", context: dict | None = None,
                          defender_transient: dict | None = None) -> float:
    """Closed-form damage this Attack record deals to the defending Active (ADR-0032 E1). ``bound``:
    ``"min"`` floor, ``"max"`` ceiling, ``"exact"`` printed. Fail-open: a missing clause adds nothing."""
    if attack is None:
        return 0
    partner = attack.clause("requires_bench")
    if (partner is not None and partner.name and bound != "max"
            and (context or {}).get("atk_bench_names") is not None
            and partner.name not in context["atk_bench_names"]):
        # A bench-partner condition unmet on the LIVE board: 0 this decision (exact AND min). The "max"
        # bound keeps printed — Incoming is a worst case and they can bench the partner before attacking.
        return 0
    dmg = float(attack.damage or 0)
    damage_range = attack.clause("damage_range")
    if bound == "min" and damage_range is not None and damage_range.minimum is not None:
        dmg = float(damage_range.minimum)
    elif bound == "max" and damage_range is not None and damage_range.maximum is not None:
        dmg = float(damage_range.maximum)
    scale = attack.clause("scale")
    if scale is not None and scale.var == "atk_discard_energy" and scale.per_unit and context:
        # attacker's discard is OPEN info for both players (Riptide-class): typed filter reads
        # the Basic-Energy histogram, untyped counts every Energy card
        if scale.energy_type is not None:
            units = (context.get("atk_discard_basic_by_type") or {}).get(scale.energy_type)
        else:
            units = context.get("atk_discard_energy_total")
        if units is not None:
            dmg += scale.per_unit * units
    elif (scale is not None and scale.var in _FILTERED_COUNTS and scale.per_unit
          and scale.filter):
        # An OPEN filtered count: the family names the context key, the ATTACK names the predicate. No
        # filter -> no claim at all; falling through to "count everything in play" would be an over-read.
        material = (context or {}).get(_FILTERED_COUNTS[scale.var])
        if material is not None:
            dmg += scale.per_unit * _filtered_count(scale.var, material, tuple(scale.filter))
    elif (scale is not None and scale.var and scale.per_unit
          and (context or {}).get(scale.var) is not None):
        dmg += scale.per_unit * context[scale.var]
    hidden = attack.clause("hidden_scale")
    if hidden is not None and hidden.per_unit and hidden.sample:
        # Hidden-state deck-discard scaler: hidden ORDER but EXACT deck facts, so the distribution is
        # known — pigeonhole floor is SOUND, hypergeometric mean is "exact", ceiling is min(sample, fuel).
        units = (context or {}).get("hidden_units")
        deck_n = (context or {}).get("atk_deck_count")
        fuel = ((context or {}).get("atk_deck_basic_by_type") or {}).get(hidden.energy_type) \
            if hidden.energy_type is not None else None
        if units is None and deck_n == 0:
            units = 0    # deck exactly known EMPTY: zero hidden units is a fact, not a missing one
        elif units is None and deck_n and fuel is not None:
            sample = min(hidden.sample, deck_n)
            if bound == "min":
                units = max(0, sample - (deck_n - fuel))
            elif bound == "max":
                units = min(sample, fuel)
            else:
                units = int(sample * fuel / deck_n)            # hypergeometric mean, floored
        if units is not None:
            dmg += hidden.per_unit * units
        elif bound == "max":
            dmg += hidden.per_unit * hidden.sample  # no deck facts: assume every card fuels
    if not dmg:
        return 0
    for amount, atype, vs_ex in (context or {}).get("atk_boosts") or ():
        # Flat Trainer damage-boosts live for this attack — "before applying Weakness and Resistance",
        # and only onto an attack already dealing damage (a boost never turns a 0 into 30).
        if atype is not None and (attacker is None or attacker.energy_type != atype):
            continue
        if vs_ex and not (defender is not None and defender.is_rule_box):
            continue
        dmg += amount
    ignores_effects = attack.clause("ignores_effects") is not None
    if not ignores_effects and _prevented(attacker, defender):
        return 0
    atype = attacker.energy_type if attacker is not None else None
    pierces_wr = attack.clause("ignores_wr") is not None
    if atype is not None and defender is not None and not pierces_wr:
        if defender.weakness == atype:
            dmg *= 2
        if defender.resistance == atype:
            dmg = max(0, dmg - _RESISTANCE)
    if not ignores_effects and defender is not None:
        # defender-side printed facts (ADR-0032 G1) — both explicitly AFTER Weakness/Resistance:
        reduction_clause = _body_clause(defender, "damage_reduction")
        if reduction_clause is not None and reduction_clause.amount:
            r_types = reduction_clause.attacker_types
            if r_types is None or atype in r_types:    # Dewgong: {R}/{W} attackers only
                dmg = max(0, dmg - reduction_clause.amount)
        prevent_clause = _body_clause(defender, "prevents_damage_at_least")
        if (prevent_clause is not None and prevent_clause.amount
                and dmg >= prevent_clause.amount):     # Drednaw: big-enough hit is prevented
            return 0
    if not ignores_effects and defender_transient:
        # LIVE transient grant on defending body (ADR-0033: Frost Barrier's -30, a prevent-all
        # wall) — effect on the Active, so Nebula class pierces it too
        if defender_transient.get("prevent_all"):
            return 0
        if defender_transient.get("reduction"):
            dmg = max(0, dmg - defender_transient["reduction"])
        for amount, r_types, needs_ability in defender_transient.get("typed") or ():
            # Attacker-gated Tool reductions (Payapa/Haban/Thick Scale typed, Sacred Charm's
            # Ability gate). Fail-open: an unknown attacker record invents no reduction.
            if r_types is not None and atype not in r_types:
                continue
            if needs_ability and not (attacker is not None and attacker.has_ability):
                continue
            dmg = max(0, dmg - amount)
    return dmg


def _body_clause(card, kind: str):
    """A defender-side printed effect leg, wherever the record carries it (Ability today)."""
    return next((clause for ability in getattr(card, "abilities", ()) or ()
                 for clause in ability.clauses if clause.kind == kind), None)


def _prevented(attacker, defender) -> bool:
    """Whether the defender's typed Ability clause prevents this attacker's damage."""
    if attacker is None or not attacker.is_rule_box:
        return False
    clause = _body_clause(defender, "prevents_damage_from") if defender is not None else None
    scope = clause.scope if clause is not None else None
    if scope == "ex":
        return True
    return scope == "basic_ex" and not attacker.evolves_from


def bench_reach(attack) -> int:
    """Single-target bench damage: snipe hits one target; spread counters can all concentrate
    on one, so its total is an equivalent no-split reach."""
    snipe = attack.clause("bench_snipe")
    spread = attack.clause("bench_spread")
    return max(int(snipe.amount or 0) if snipe is not None else 0,
               int(spread.amount or 0) if spread is not None else 0)
