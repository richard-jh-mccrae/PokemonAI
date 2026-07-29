"""Deny Relevance — *is this Energy doing important work for the opponent's plan?* (ADR-0079, #199).

The deny instrument's value, and **not a magnitude on the damage scale**. ADR-0078 tried to price a
strip through the shared prize-denominated marginal and needed a Worth Damage Rate to get the answer
back into the Needs DP's card-worth currency; #199's grill measured that rate **underivable** (the
corpus-wide DISCARD sweep found 12 `Discard` frames, exactly one holding a Hammer, and that one
prices 0.000 under *both* instruments, so the rate divides out). The user's doctrine then reframed
the question entirely: deny is a **liveness gate, a redundancy gate, and a relevance read**, none of
which crosses a scale boundary — so no bridge is needed and none ships (ADR-0079 decision 1).

The read is a scalar in ``[0, 1]`` per ``(body, Energy)`` pair (decision 3), scaling the incumbent
constants rather than introducing a scale of its own. This module owns the **scoring**; the Pilot
owns the board plumbing (gathering the line's attacks and the Ability fuel types) and emits the
result on its opponent-target rows. The split mirrors `needs.opponent_target_value` (pure) beside
`Pilot._strip_delta_terms` (plumbing).

## The two legs

**Attack leg — the typed unlock.** An Energy is relevant to an attack when its type covers one of
that attack's SPECIFIC-type slots *and the body is not already surplus in that type for it*. The
surplus clause is what makes ADR-0062's whiff arrive **structurally** rather than as a bolted-on
gate: Mega Lucario ex holding 3 `{F}` against Aura Jab `{F}` / Mega Brave `{F}{F}` is surplus for
both, so every strip scores 0.00 — exactly the 0 its worked table records for the 3-Energy row.

The scan runs over the whole **line** (the body plus every forward form —
`combat.forward_card_ids`, all-descendants since S1a), because attached Energy carries through an
evolution. That is what ranks a `{F}` on a Riolu (banking toward Mega Lucario ex's Mega Brave 270)
above a `{F}` on a Solrock (Cosmic Beam 70, and no descendants at all), which raw current-form damage
orders backwards. It is also why the read is NOT gated on current affordability: Dragapult ex holding
`{D}` + `{R}` cannot afford Phantom Dive `{R}{P}` yet, and the `{R}` is still the Energy worth taking.

**Ability leg — the mute.** Stripping the last Energy of a type some form's Ability is gated on
switches that Ability off (`CardStat.abilityEnergyTypes`, ADR-0032). This is the MIRROR of the attach
marginal's dormant-Ability predicate (#139): that one prices *fuelling* a dormant Ability, this one
prices *muting* a live one. Both read the same field, so the two cannot drift (the
`_build_standing` / `_affords` one-function-owns-the-fact lesson).

Only ONE card in the live pool is affected — **Munkidori** (112), whose Adrena-Brain reads *"if this
Pokémon has any {D} Energy attached"*. The user's ruling on it is a WITHIN-body target pick: on a
Munkidori holding `{D}` + `{P}`, take the `{D}` (mute the Ability) rather than the `{P}` (Mind Bend's
cost). So the leg is scored to **strictly dominate the body's own best attack leg and nothing more**
— it wins its own body, and it does not lift a small support body above a real attacker. Valuing a
mute at a flat 1.0 was rejected: it would rank a benched Munkidori on one `{D}` above a Mega Lucario
ex sitting on `{F}{F}`, an assertion the doctrine never made. Valuing it at the Ability's own damage
equivalent (Adrena-Brain relays 3 counters = 30) was also rejected — it scores 0.086 against the
`{P}`'s 0.171 and so CONTRADICTS the ruling outright.

⚠️ **Known limitation, recorded rather than hidden.** Okidogi (116) — *"if this Pokémon has any {D}
Energy attached, it gets +100 HP, and the attacks it uses do 100 more damage"* — is a STATIC buff, so
muting it is worth far more than its Good Punch 70 implies, and this leg under-rates it. It is out of
the deck pool and every authored matchup (user, 2026-07-29), so the gap is latent. Shuckle (711,
heal 30) and Fezandipiti (970, a coin-flip damage prevention — NOT Fezandipiti **ex** 140, whose Flip
the Script needs no Energy) are the other two out-of-pool cases. Revisit if any enters the pool.
"""
from __future__ import annotations

#: The **relevance normalizer** — the largest attack damage printed in the card set.
#:
#: DERIVED, not tuned, in the same spirit as `currency.PRIZE_DAMAGE_RATE`: it is the maximum leading
#: damage figure over every attack row in `data/EN_Card_Data.csv` (Core Memory's Geobuster, 350), and
#: `tests/strategy/test_deny_relevance.py` RECOMPUTES it from the CSV rather than pinning the literal,
#: so a future set re-derives it instead of inheriting it. Its only job is to map a damage setback
#: into the ``[0, 1]`` band decision 3 fixes — it is NOT an exchange rate and must never be used as
#: one (that is the Worth Damage Rate, which ADR-0079 rules moot for deny).
MAX_ATTACK_DAMAGE = 350.0

#: The strict-dominance nudge that puts an Ability mute just above its own body's best attack leg.
#: Structural, not a magnitude: it encodes "muting the Ability is worth AT LEAST this body's best
#: attack" and asserts nothing further. Small enough that it can never reorder two different bodies
#: whose attack legs differ by a real damage step (the smallest damage step in the set is 10, i.e.
#: 10/350 ≈ 0.029, two orders of magnitude above this).
_MUTE_EDGE = 1e-4


def attack_leg(setback_damage: float) -> float:
    """The typed-unlock leg: a damage setback mapped into ``[0, 1]``.

    Args:
        setback_damage: the biggest attack damage in the body's line whose specific-type slot this
            Energy covers without the body already being surplus in that type. 0 when the Energy
            covers no specific slot anywhere in the line (an all-colourless cost such as Meowth ex's
            Tuck Tail ``●●●`` can never produce one).
    """
    return min(1.0, max(0.0, float(setback_damage) / MAX_ATTACK_DAMAGE))


def strip_relevance(*, energy_type, type_count: int, line_attacks, ability_types=()) -> dict:
    """Relevance of removing ONE Energy of ``energy_type`` from a body, with its legs.

    Args:
        energy_type: the EnergyType code this Energy contributes, or ``None``/``0`` for a
            colourless / special Energy that pays colourless slots only. **Never infer this from the
            Energy's card id** — for Basic Energy the two happen to coincide (Basic ``{F}`` is card 6
            and FIGHTING is 6) but that is a coincidence in the data, and Ignition Energy is card 17.
        type_count: how many Energy of ``energy_type`` are attached to the body right now, this one
            included. Drives both the surplus clause and the mute clause.
        line_attacks: ``(damage, {EnergyType: slots_needed})`` for every attack of every form in the
            body's line (current form + all forward forms). Colourless slots are already excluded.
        ability_types: EnergyType codes any form's Ability is gated on
            (``CardStat.abilityEnergyTypes``).

    Returns:
        ``{"relevance", "attack_leg", "ability_leg", "setback_damage"}``. Relevance is the MAX of the
        legs — the same shape `card_worth.role_value` uses to combine heterogeneous claims. (A sum
        would be indistinguishable here: the mute leg already dominates its own body by construction,
        so the two agree wherever they could disagree.)
    """
    if energy_type in (None, 0) or type_count <= 0:
        return {"relevance": 0.0, "attack_leg": 0.0, "ability_leg": 0.0, "setback_damage": 0}

    # ── attack leg. The surplus clause `type_count <= need` is ADR-0062's whiff, derived: a body
    # holding more of the type than the attack asks for loses nothing it can still pay for.
    setback = 0
    body_best = 0
    for damage, need in line_attacks:
        n = need.get(energy_type, 0)
        if n > 0 and type_count <= n:
            setback = max(setback, int(damage))
        body_best = max(body_best, int(damage))
    attack = attack_leg(setback)

    # ── ability leg. Only the LAST Energy of the gated type mutes: "any {D} attached" survives while
    # a second {D} remains, so a strip off a doubled-up body switches nothing off.
    ability = 0.0
    if energy_type in (ability_types or ()) and type_count == 1:
        ability = min(1.0, attack_leg(body_best) + _MUTE_EDGE)

    return {"relevance": max(attack, ability), "attack_leg": attack,
            "ability_leg": ability, "setback_damage": setback}
