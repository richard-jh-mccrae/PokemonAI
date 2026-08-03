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

#: The OPEN filtered-count family (ADR-TEMP-361, Issue #361), family -> the context key holding its
#: RAW MATERIAL. ``scaleVar`` names the FAMILY and ``AttackStat.scaleFilter`` carries the predicate's
#: argument, because the argument is an arbitrary name substring or attack name and cannot be
#: flattened into a variable name without hardcoding a card list into the vocabulary. A pre-reduced
#: integer in the context is impossible for the same reason: the builder cannot know what an attack
#: it has never seen will filter on. This generalises the ``atk_discard_energy`` exception below from
#: one special case to a small, CLOSED class of two — the vocabulary of families stays closed even
#: though each family's argument is open.
_FILTERED_COUNTS = {
    "both_in_play_named": "both_in_play_names",
    "atk_in_play_with_attack": "atk_in_play_attack_names",
}


def _filtered_count(var: str, material, terms: tuple) -> int:
    """How many units the filtered-count ``var`` sees in ``material`` under ``terms``.

    * ``both_in_play_named`` — Pokémon in play on EITHER side whose card name CONTAINS any term
      ("does 40 damage for each Pokémon in play that has 'Koffing' or 'Weezing' in its name (both
      yours and your opponent's)"). Substring, case-sensitive, and the card asks for CONTAINMENT
      rather than equality for a reason: an owner prefix is part of the printed name
      (`docs/rules.md` §9 — *"suffix/owner/regional forms are part of the name"*), so the pool's
      "Team Rocket's Koffing" is a DIFFERENT name from "Koffing" and only a substring test counts
      it. Case-sensitive because the pool's own capitalisation IS the fact, not an approximation.
    * ``atk_in_play_with_attack`` — the ATTACKER's in-play bodies HAVING an attack of that exact
      name ("for each of your Pokémon in play that has the Round attack"). Bodies, not names: the
      material is one entry per body precisely so two Round-havers cannot collapse into one.

    Both fail CLOSED on a body that carries no name / no resolvable attacks — these scalers multiply
    MY OWN damage, and an over-read is the direction that manufactures a phantom lethal.
    """
    if var == "both_in_play_named":
        return sum(1 for n in material if n and any(t in n for t in terms))
    return sum(1 for names in material if any(t in names for t in terms))


def wr_adjust(attacker, defender, dmg: float) -> float:
    """The card-level Weakness/Resistance rule (ADR-0052): x2 on the defender's Weakness, then a
    flat -30 Resistance floored at 0, vs the ATTACKER's type — rules order (rules.md §5). The
    attack-BLIND variant for worst-case fallbacks where no attack record resolves (a partially
    known table must never shrink a worst case); ``compute_active_damage`` below applies the same
    two rules attack-gated (the ignore-flag family) — both live in THIS module, the one W/R home.
    Unknown attacker/defender/type → unadjusted."""
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
            with no context the term contributes 0 (a sound floor, a weak ceiling). Two families
            read RAW MATERIAL rather than a count and reduce it with the attack's own filter —
            ``atk_discard_energy`` (its Energy-type filter) and the open filtered counts
            ``both_in_play_named`` / ``atk_in_play_with_attack`` (``AttackStat.scaleFilter``).

    Returns:
        The predicted damage to the Active (never negative).
    """
    if attack is None:
        return 0
    if (getattr(attack, "requiresBench", None) and bound != "max"
            and (context or {}).get("atk_bench_names") is not None
            and not all(n in context["atk_bench_names"] for n in attack.requiresBench)):
        # a bench-partner condition ("does nothing without Lunatone on your Bench") unmet on the
        # LIVE board: the attack does 0 this decision (exact AND min — the bench is what it is when
        # the attack is scored; benching the partner first re-presents the menu with it met). The
        # "max" bound keeps printed: Incoming is a worst case, and the opponent can bench the
        # partner before attacking next turn. Fail-open without the context key.
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
        # an OPEN filtered count: the family names the context key, the ATTACK names the predicate.
        # No filter -> no claim at all (falling through to "count everything in play" would be a
        # board-wide over-read), and a missing key contributes 0 like every other absent variable.
        material = (context or {}).get(_FILTERED_COUNTS[attack.scaleVar])
        if material is not None:
            dmg += attack.scalePerUnit * _filtered_count(attack.scaleVar, material,
                                                         tuple(attack.scaleFilter))
    elif attack.scaleVar and attack.scalePerUnit and (context or {}).get(attack.scaleVar) is not None:
        dmg += attack.scalePerUnit * context[attack.scaleVar]
    if attack.hiddenPerUnit and attack.hiddenSample:
        # hidden-state deck-discard scaler (Hammer-lanche class): hidden ORDER but EXACT deck facts ->
        # distribution known: pigeonhole floor SOUND (>= sample-(N-F)), hypergeometric mean "exact", ceiling min(sample,F).
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
        # flat Trainer damage-boosts live for this attack (Premium Power Pro plays this turn,
        # an attached Maximum Belt) — "before applying Weakness and Resistance", so added here,
        # ahead of the W/R step below, and only onto an attack already dealing damage (a boost
        # never turns a does-nothing attack into 30). Each carries its own gates: an attacker
        # EnergyType ("your {F} Pokémon") and/or a defender-{ex} scope (which includes Mega ex —
        # rulebook.txt:337).
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
    """The defender's Ability prevents this attacker's damage outright — the boolean
    `prevent_ex_damage` Function Tag OR the parsed ``CardStat.preventsDamageFrom`` field
    ("ex" — Crustle/Sylveon (the tag misses Sylveon); "basic_ex" — Farigiraf ex, where the
    attacker must also be Basic, i.e. carry no ``evolvesFrom``). False on missing stats."""
    if attacker is None or not attacker.is_ex_body:
        return False
    if _PREVENT_EX_TAG in (defender_tags or frozenset()):
        return True
    scope = getattr(defender, "preventsDamageFrom", None) if defender is not None else None
    if scope == "ex":
        return True
    return scope == "basic_ex" and not getattr(attacker, "evolvesFrom", None)
