"""Deny Relevance — *is this Energy doing important work for the opponent's plan?* (ADR-0080, Issue #199).

The deny instrument's value, and **not a magnitude on the damage scale**. ADR-0078 tried to price a
strip through the shared prize-denominated marginal and needed a Worth Damage Rate to get the answer
back into the Needs DP's card-worth currency; Issue #199's grill measured that rate **underivable**
(the corpus-wide DISCARD sweep found 12 `Discard` frames, exactly one holding a Hammer, and that one
prices 0.000 under *both* instruments, so the rate divides out). The user's doctrine then reframed
the question entirely: deny is a **liveness gate, a redundancy gate, and a relevance read**, none of
which crosses a scale boundary — so no bridge is needed and none ships (ADR-0080 decision 1).

The read is a scalar in ``[0, 1]`` per ``(body, Energy)`` pair (decision 3), scaling the incumbent
constants rather than introducing a scale of its own. This module owns the **scoring**; the Pilot
owns the board plumbing (gathering the line's attacks and the Ability fuel types) and emits the
result on its opponent-target rows. The split mirrors `needs.opponent_target_value` (pure) beside
`Pilot._strip_delta_terms` (plumbing).

## The legs

**Attack leg — the typed unlock.** An Energy is relevant to an attack when removing it puts that
attack further out of reach. Two ways that happens, and *only* two:

  1. **It pays a specific-type slot the body is not already surplus in** (``type_count <= needed``).
  2. **It is the count that binds**: every specific-type slot is already covered and the body sits
     exactly on the attack's total cost, so losing any Energy drops it under.

The surplus clause in (1) is what makes ADR-0062's whiff arrive **structurally** rather than as a
bolted-on gate: Mega Lucario ex holding 3 ``{F}`` against Aura Jab ``{F}`` / Mega Brave ``{F}{F}``
is surplus for both and over the total on both, so every strip scores 0.00 — exactly the 0 its
worked table records for the 3-Energy row.

⚠️ **Why this is deliberately NOT a plain affordability diff, despite Issue #199's spec text calling
for one.** A literal "was it affordable before, is it affordable after" diff — or any rule that
counts an Energy relevant merely because the body drops below an attack's TOTAL cost — breaks two of
the user's five worked rulings, and the arithmetic is worth keeping:

  * **Meowth ex would stop being ignorable.** Tuck Tail costs ``●●●`` with no specific slot at all.
    Under a total-count rule a lone Energy on a Meowth ex reads as a setback toward a 60-damage
    attack, where the doctrine says flatly *"does opponent has a meowth with an energy, ignore it."*
    Pure-colourless costs are excluded here precisely because ANY Energy substitutes into them, so
    no particular Energy is ever on their critical path.
  * **Dragapult ex's stray ``{D}`` would become a target.** Holding ``{D}`` + ``{R}`` against Phantom
    Dive ``{R}{P}``, the body sits exactly on the 2-Energy total, so a total-count rule flags BOTH
    Energies — against *"hammer against fire only, ignore the darkness."* Clause (2) is guarded on
    every specific slot already being covered for exactly this reason: here the ``{P}`` is still
    missing, so the binding constraint is the type, not the count, and the ``{D}`` is not on the path.

Clause (2) then recovers the case that motivated the objection — a genuinely typed attack such as
``{F}●●`` on a body holding exactly ``{F}`` plus two others, where stripping one of the others really
does break it.

The scan runs over the whole **line** (the body plus every forward form —
`combat.forward_card_ids`, all-descendants since S1a), because attached Energy carries through an
evolution. That is the **forward-potential** leg: it is the scan's SCOPE rather than a separate
addend, and it is what ranks a ``{F}`` on a Riolu (banking toward Mega Lucario ex's Mega Brave 270)
above a ``{F}`` on a Solrock (Cosmic Beam 70, and no descendants at all), which raw current-form
damage orders backwards. ``forward_setback`` reports it separately so the contribution stays
inspectable. It is also why the read is NOT gated on current affordability: Dragapult ex holding
``{D}`` + ``{R}`` cannot afford Phantom Dive yet, and the ``{R}`` is still the Energy worth taking.

**Ability leg — the mute.** Stripping the last Energy of a type some form's Ability is gated on
switches that Ability off (`CardStat.abilityEnergyTypes`, ADR-0032). This is the MIRROR of the attach
marginal's dormant-Ability predicate (Issue #139): that one prices *fuelling* a dormant Ability, this
one prices *muting* a live one. Both read the same field, so the two cannot drift (the
`_build_standing` / `_affords` one-function-owns-the-fact lesson).

Only ONE card in the live pool is affected — **Munkidori** (112), whose Adrena-Brain reads *"if this
Pokémon has any {D} Energy attached"*. The user's ruling on it is a WITHIN-body target pick: on a
Munkidori holding ``{D}`` + ``{P}``, take the ``{D}`` (mute the Ability) rather than the ``{P}``
(Mind Bend's cost). So the leg is scored to **strictly dominate the body's own best attack leg and
nothing more** — it wins its own body, and it does not lift a small support body above a real
attacker. Valuing a mute at a flat 1.0 was rejected: it would rank a benched Munkidori on one ``{D}``
above a Mega Lucario ex sitting on ``{F}{F}``, an assertion the doctrine never made. Valuing it at
the Ability's own damage equivalent (Adrena-Brain relays 3 counters = 30) was also rejected — it
scores 0.086 against the ``{P}``'s 0.171 and so CONTRADICTS the ruling outright.

## Known limitations, recorded rather than hidden

  * **Okidogi** (116) — *"if this Pokémon has any {D} Energy attached, it gets +100 HP, and the
    attacks it uses do 100 more damage"* — is a STATIC buff, so muting it is worth far more than its
    Good Punch 70 implies, and the ability leg under-rates it. Out of the deck pool and every
    authored matchup (user, 2026-07-29), so the gap is latent. Shuckle (711, heal 30) and
    Fezandipiti (970, a coin-flip damage prevention — NOT Fezandipiti **ex** 140, whose Flip the
    Script needs no Energy) are the other two out-of-pool cases.
  * **Rainbow-class Special Energy** (Legacy 12, and Neo Upper 10 / Prism 16 under their conditions)
    *"provides every type of Energy"*, but `CardStat.energyType` reports it untyped, so it scores 0
    on the typed leg. This matches how the shipped `combat.attached_type_counts` already treats it —
    deliberately consistent rather than a second, divergent reading of the same fact.
"""
from __future__ import annotations

import math

#: The **relevance normalizer** — the largest attack damage printed in the card set.
#:
#: DERIVED, not tuned, in the same spirit as `currency.PRIZE_DAMAGE_RATE`: it is the maximum leading
#: damage figure over every attack row in `data/EN_Card_Data.csv` (Core Memory's Geobuster, 350), and
#: `tests/strategy/test_deny_relevance.py` RECOMPUTES it from the CSV rather than pinning the literal,
#: so a future set re-derives it instead of inheriting it. Its only job is to map a damage setback
#: into the ``[0, 1]`` band decision 3 fixes — it is NOT an exchange rate and must never be used as
#: one (that is the Worth Damage Rate, which ADR-0080 rules moot for deny).
MAX_ATTACK_DAMAGE = 350.0


def normalize(setback_damage: float) -> float:
    """Map a damage setback into the ``[0, 1]`` relevance band.

    Named for what it does rather than for one of its callers: both legs run through it, so calling
    it ``attack_leg`` made the Ability leg's own use of it read as a category error.

    Args:
        setback_damage: an attack damage figure from the body's line. 0 when this Energy puts no
            attack further out of reach anywhere in the line (an all-colourless cost such as Meowth
            ex's Tuck Tail ``●●●`` can never produce one).
    """
    return min(1.0, max(0.0, float(setback_damage) / MAX_ATTACK_DAMAGE))


def strip_relevance(*, energy_type, type_count: int, line_attacks, ability_types=(),
                    total_attached: int = 0, attached_counts=None) -> dict:
    """Relevance of removing ONE Energy of ``energy_type`` from a body, with its legs.

    Args:
        energy_type: the EnergyType code this Energy contributes, or ``None``/``0`` for a
            colourless / special Energy that pays colourless slots only. **Never infer this from the
            Energy's card id** — for Basic Energy the two happen to coincide (Basic ``{F}`` is card 6
            and FIGHTING is 6) but that is a coincidence in the data, and Ignition Energy is card 17.
        type_count: how many Energy of ``energy_type`` are attached to the body right now, this one
            included. Drives the surplus clause and the mute clause.
        line_attacks: ``(damage, {EnergyType: slots}, total_cost, is_forward)`` for every attack of
            every form in the body's line. ``is_forward`` marks an attack belonging to a FORWARD form
            rather than the body as it stands, so the forward-potential contribution stays visible.
        ability_types: EnergyType codes any form's Ability is gated on
            (``CardStat.abilityEnergyTypes``).
        total_attached: how many Energy of any type the body holds, for the binding-count clause.
        attached_counts: ``{EnergyType: count}`` for the whole body, for the binding-count clause.

    Returns:
        ``{"relevance", "attack_leg", "ability_leg", "setback_damage", "forward_setback"}``.
        Relevance is the MAX of the legs — the shape `card_worth.role_value` uses to combine
        heterogeneous claims.
    """
    blank = {"relevance": 0.0, "attack_leg": 0.0, "ability_leg": 0.0,
             "setback_damage": 0, "forward_setback": 0}
    if energy_type in (None, 0) or type_count <= 0:
        return blank
    counts = attached_counts or {}

    setback = forward_setback = body_best = 0
    for damage, need, total_cost, is_forward in line_attacks:
        body_best = max(body_best, int(damage))
        if not need:                          # pure-colourless cost — any Energy substitutes into it
            continue
        typed_slot = type_count <= need.get(energy_type, 0)
        # The binding count: every specific slot is already covered and the body sits exactly on the
        # total, so losing ANY Energy drops it under. Guarded on full type coverage so a body still
        # missing a colour (Dragapult ex without its {P}) is bound by the TYPE, not the count.
        type_ready = all(counts.get(t, 0) >= n for t, n in need.items())
        count_binds = type_ready and total_attached <= total_cost
        if typed_slot or count_binds:
            setback = max(setback, int(damage))
            if is_forward:
                forward_setback = max(forward_setback, int(damage))
    attack = normalize(setback)

    # The mute. Only the LAST Energy of the gated type switches an Ability off: "any {D} attached"
    # survives while a second {D} remains, so a strip off a doubled-up body mutes nothing.
    ability = 0.0
    if energy_type in (ability_types or ()) and type_count == 1:
        # Strictly above its own body's best attack leg and nothing further — `nextafter` is the
        # smallest representable step, so this asserts an ORDER without asserting a magnitude and
        # introduces no tunable constant.
        ability = math.nextafter(normalize(body_best), 1.0)

    return {"relevance": max(attack, ability), "attack_leg": attack, "ability_leg": ability,
            "setback_damage": setback, "forward_setback": forward_setback}
