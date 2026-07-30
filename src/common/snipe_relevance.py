"""Snipe Relevance — *does damaging this body matter to their plan and to my prize route?*
(ADR-0085, Issue #188).

The snipe instrument's value, and **not a magnitude**. Issue #188 was chartered to fold the six
additive target rungs in `baseline_snipe.py` onto the shared prize-denominated marginal; measuring
that refuted it (7/19 against the shipped rungs' 17/19), and on `83667237-107` it restored the exact
pre-ADR-0044 blunder — because `needs.opponent_target_value`'s `prize_advance` is its own docstring's
*"if-KO'd term"* while the bench-snipe rider is 50 damage and **14 of 19 corpus frames offer no Knock
Out at all**. It paid 3.0 prize-equivalents to chip a 340-HP body that keeps ~85% of its HP.

Magnitude-shaped successors fail too, and **provably** rather than by measurement luck: `82756021-57`
and `83667237-107` each offer an 80-HP 1-prize Makuhita against a 340-HP 3-prize Mega Lucario ex, at
identical rider and identical turns-to-finish, and the human rules them **opposite ways**. No monotone
function of those inputs separates them. That is ADR-0062's wall — *"no monotone pricing of magnitude
alone can separate them"* — reached by a second instrument, for the same structural reason deny hit
it: **the target survives**, so what matters is whether it *matters*, not how big it is.

So snipe takes **Deny Relevance**'s shape (ADR-0080): a scalar in ``[0, 1]``, scaling an incumbent
constant rather than introducing a scale. This module owns the **scoring**; `Pilot` owns the board
plumbing. The split mirrors `deny_relevance.strip_relevance` beside `Pilot._relevance_terms`.

## The shape, and why it is a PRODUCT where deny is a MAX

```
relevance = their_plan x my_route
their_plan = max(imminence, forward, forced) x brief
my_route   = max(ko_delta, reach, share, prevent_ex)
```

Deny's legs are alternative claims about **one** subject — this Energy matters, for one reason or
another — which is what `max` is for. Snipe's split across **two** subjects, and they are
*conjunctive*: a snipe is worth spending only when the body matters to the opponent **and** the
damage advances me. A terrifying body I have no route through is a bad snipe; a harmless body sitting
on my route is also a bad snipe. Multiplication says that directly, and makes the additive failure
mode **unrepresentable** rather than merely capped — which matters, because that failure mode is a
documented blunder class in the deleted rungs' own rationales (`top-threat 30 + forced-promotion 40 +
evolving-threat 45 = 115` on an un-KO-able Grookey beating `60` on the KO-able Applin, `82754241-45`).
`max` still governs *within* each side, where the claims really are alternatives.

## their_plan — does this body matter to the opponent's offence?

Sourced from the **Threat Clock**, not from `pilot._body_threat_rank` (ADR-0085 decision 3, and
ADR-0045's own thesis — it names `_body_threat_rank` among the six scattered reads the Threat Clock
exists to unify). The design doc specifies this exact query: *"`strongest_threat_rank` (snipe
imminence) | the curve's earliest-KO-turn / slope per body | prep policy."*

Won for free rather than re-derived: `nextTurnSelfLock` (Latias ex's Eon Blade 200 locks itself out
next turn, so it is not a 200-per-turn threat), typed affordability, Weakness/Resistance,
`AttackStat.handSizeDamage`, and every parsed `scaleVar` scaler. `_ENERGIZED_SNIPE_TIER = 100000`
retires as **subsumed** by `turns_to_afford` rather than being re-expressed — the standing *"a graded
term REPLACES its guard family"* discipline. Measured: over the 9 corpus frames where energized and
bare bodies are both on offer, `turns_to_afford` reproduces all six energized picks with no tier.

**The two ADR-0044 reads are LEG-SCOPED, not whole-target gates** (decision 4). They zero the
imminence leg only, exactly as `baseline_snipe.py` attached them to two of six rungs and no more.
Three corpus frames — `81905522-75`, `82523811-41`, `85164131-22` — have the human picking a body
carrying `target_promotion_mirage`, so a whole-target gate makes them **unreachable**. Dropping the
reads entirely is also refuted (Tera-only gating measured 6-7/9 against 8/9).

**The forced-promotion leg is GRADED, never a flat 1.0** (decision 10). A saturating constant beat
the Riolu's forward-wincon leg on `ms_snipe_evolving_wincon_preevo_f75` and took Solrock instead —
the first held-out fixture caught it. It carries **no imminence discount**: a forced promotion *is*
the timing claim (the body attacks next turn by definition), so `turns_to_afford` on top would
double-count the ADR-0044 read that established it.

## my_route — does hurting it advance MY prize route?

**`ko_delta` is the turns REMOVED from how long the body will sit Active against my real attacker**
(decision 11, user ruling 2026-07-29):

> *"if i snipe a benched mega lucario with 50dmg such that it now has not 340 HP but 290HP, that does
> nothing to help — ill still need two turns from mega starmie Nebula Beam to take it down. thus we
> must consider the amount of dmg we will do to the body once it moves into active and how many turns
> until we can KO it. if sniping it once or twice reduces the number of turns itll sit active, thats a
> real win, otherwise we are just wasting our snipes."*

Priced through `combat.turns_to_ko`, which reads the body **as an Active** against my real attack —
the *"once it moves into active"* the ruling asks for — rather than counting rider hits. The **two**-chip
window is load-bearing and the corpus proves it: on `82756021-57` the 340-HP Mega has `turns_to_ko`
3, one chip saves **nothing**, two chips save one turn, and the human takes it. A one-chip read scores
that frame's correct answer at zero.

`reach` (my repeatable rider finishes it outright — a prize riding alongside my main KOs) and `share`
(its prizes against what I still need) are the two other route claims. `share` was removed and
restored: dropping it measured 16/19, because on `82756021-57` it is the leg that selects the 3-prize
Mega over an 80-HP small whose `reach` is higher. It cannot manufacture value on its own — it is
multiplied by `their_plan`, so a gated body scores 0 however many prizes it carries.

`prevent_ex` is `_PREVENT_EX_SNIPE_BOOST` **re-homed** (decision 9). A line reaching
`prevent_ex_damage` while my Active is an ex/Mega ex does not threaten me harder once evolved — it
becomes **immune to my attacker**, closing my route through it permanently. That is a route fact, not
a threat magnitude, and filing it under "how scary are they" was a category error the additive stack
could never see. It scores maximal because this turn is the last one in which the route exists.

## Constants

**None are introduced.** `MAX_ATTACK_DAMAGE` is `deny_relevance`'s existing derived, CSV-recomputed
normalizer, imported rather than copied so a future set re-derives it once for both instruments.
`K = MAX_ATTACK_DAMAGE` is also the exit to the damage-scale `score` (ADR-0085 Amendment A1): since
`relevance = setback / MAX_ATTACK_DAMAGE`, `K x relevance` lands back in damage units, exactly as
ADR-0080 Amendment B derived for deny. **`currency.PRIZE_DAMAGE_RATE` is NOT a consumer** — relevance
is a `[0,1]` scalar, not a prize-denominated value, so a prizes-to-damage rate would convert nothing
and merely rescale.

**Ten constants are deleted** by the fold: the six rung weights (60/45/40/30/20/12),
`_ENERGIZED_SNIPE_TIER`, `_PREVENT_EX_SNIPE_BOOST`, `_SNIPE_THREAT_PRIZE_FLOOR`, and (once Issue #213
lands the curve fix) `_HAND_SIZE_ATTACKER_BOOST`.

## What stays OUTSIDE this scalar

`snipe-for-the-ko` remains a structural dominator, and `Pilot._snipe_tera_veto` remains an
**ordering** veto (`-KO_SCORE`) rather than a zero — a benched Tera takes no attack damage
(`rules.md §185`), but when it is the ONLY offered target the select is forced and the option must
stay selectable. This module therefore never zeroes on Tera; it only lets the Tera fact stand a
positive Brief boost down (below).
"""
from __future__ import annotations

import math

from common.deny_relevance import MAX_ATTACK_DAMAGE, normalize

#: The exit rate from the ``[0, 1]`` relevance band back into the damage-scale ``score`` the
#: doctrines compete on. IDENTICAL to the normalizer by construction, which is the point: since
#: ``relevance = setback / MAX_ATTACK_DAMAGE``, ``K x relevance`` recovers the setback in DAMAGE, so
#: the armed rung prices in the incumbent's own units and is a strict generalisation of it rather
#: than a re-scaling. There is no free parameter. Derived for deny by ADR-0080 Amendment B and
#: adopted here by ADR-0085 Amendment A1, which corrects this ADR's original claim that
#: `currency.PRIZE_DAMAGE_RATE` was the exit — it is not, and it never was: relevance is not
#: prize-denominated, so that rate would convert nothing.
K = MAX_ATTACK_DAMAGE


def ko_delta(turns_before: float | None, turns_after: float | None) -> float:
    """Fraction of the body's Active clock that ``chips`` worth of damage removes.

    The user's ruling (ADR-0085 decision 11): a chip is worth something only if it takes a TURN off
    how long the body will sit in the Active spot against my real attacker. A 50-damage snipe onto a
    340-HP Mega Lucario ex takes it to 290 and removes no turn at all — a wasted snipe.

    Args:
        turns_before: `combat.turns_to_ko` against the body as it stands. ``None`` when my Active
            deals it no damage at all (infeasible), which scores 0 — I have no route through it to
            shorten.
        turns_after: the same read against the chipped body.

    Returns:
        ``0.0`` when no turn is removed (the common case, and the point of the read), rising to
        ``1.0`` when the chip closes the clock entirely.
    """
    if not turns_before or turns_after is None:
        return 0.0
    return min(1.0, max(0.0, (float(turns_before) - float(turns_after)) / float(turns_before)))


def rider_reach(hp_remaining: int, rider_damage: int) -> float:
    """``1 / ceil(hp / rider)`` — a prize my repeatable rider finishes alongside my main attacks.

    The arithmetic `objectives.prize_paths`' `snipe_prize_reach` tie-break already computes
    (`⌈80/50⌉ = 2` for a Makuhita). 0 when the rider deals nothing or the body has no HP left to
    read, which keeps a missing provider from inventing a route.
    """
    if not hp_remaining or not rider_damage:
        return 0.0
    return 1.0 / math.ceil(hp_remaining / rider_damage)


def prize_share(prize_value: int, prizes_needed: int) -> float:
    """How much of my REMAINING prize requirement this body's Knock Out would cover.

    Derived from two visible counts; capped at 1.0 because a body worth more prizes than I still need
    covers the requirement and no more (the `prize_advance` overshoot ADR-0044's Prize-Redundant
    Target read exists to catch, expressed here as saturation rather than as a gate).
    """
    if prizes_needed <= 0:
        return 0.0
    return min(1.0, max(0.0, float(prize_value) / float(prizes_needed)))


def target_relevance(*, incoming_damage: int = 0, turns_to_afford: int | None = None,
                     forward_damage: int = 0, is_strongest_forward: bool = False,
                     forward_form_in_play: bool = False, is_forced_promotion: bool = False,
                     prize_redundant: bool = False, promotion_mirage: bool = False,
                     is_tera: bool = False, brief_priority: float = 0.0,
                     brief_boost: float = 1.0,
                     turns_to_ko_before: float | None = None,
                     turns_to_ko_after: float | None = None,
                     hp_remaining: int = 0, rider_damage: int = 0,
                     prize_value: int = 1, prizes_needed: int = 6,
                     prevents_my_ex: bool = False) -> dict:
    """Relevance of aiming this turn's snipe/chip at ONE offered opponent body, with its legs.

    Args:
        incoming_damage: `combat.incoming(my_active, [body], t=1, charged=None)` — the CEILING
            policy. Decision 8 splits the conservatism deliberately: ceiling on how HARD they can hit
            (under-counting their reach loses games, ADR-0064's hidden-burst lesson) and the slow
            rules-floor clock on how SOON (over-counting their speed only wastes a rider).
        turns_to_afford: `combat.turns_to_afford(body, attaches_per_turn=1)` — the slow half of that
            split. ``None`` means UNKNOWN (fail-closed at source), and takes no discount at all
            rather than reading as maximally distant, which would be the fail-open direction.
        brief_boost: the multiplier a matched Brief applies — the caller's `_BRIEF_THREAT_BOOST`.
            Passed in rather than defined here so one constant governs both instruments.
        forward_damage: `stats.forward_max_damage(card_id)`, for the developing-wincon leg.
        is_strongest_forward / forward_form_in_play: ADR-0044's `snipe-the-evolving-threat`
            discriminator — chip the pre-evo only while the evolved wincon is NOT already on board.
        is_forced_promotion: ADR-0044's Forced-Promotion Read.
        prize_redundant / promotion_mirage: the two ADR-0044 reads. **Leg-scoped** — they zero the
            imminence leg and nothing else (decision 4).
        is_tera: used ONLY to stand a positive Brief boost down. The Tera veto itself is an ORDERING
            (`Pilot._snipe_tera_veto`), never a zero here — a benched Tera that is the only offered
            target must remain selectable.
        brief_priority: the matched MatchupPlan/Brief priority, signed and already scaled. A
            POSITIVE priority stands down on a redundant / mirage / Tera body; a negative (``avoid``)
            priority always applies. That asymmetry is load-bearing (ADR-0085 Amendment A3): a
            booster must scale the oracle, never override it.
        turns_to_ko_before / turns_to_ko_after: `combat.turns_to_ko` against the body as it stands
            and after the two-chip window (decision 11).
        hp_remaining / rider_damage: for the `reach` leg.
        prize_value / prizes_needed: for the `share` leg.
        prevents_my_ex: this body's line reaches `prevent_ex_damage` AND my Active is an ex body —
            my route through it closes permanently once it evolves (decision 9).

    Returns:
        ``{"relevance", "their_plan", "my_route", "imminence", "forward", "forced",
        "ko_delta", "reach", "share", "prevent_ex", "brief_multiplier"}``.
    """
    # ── their_plan ────────────────────────────────────────────────────────────────────────────
    # The two ADR-0044 reads suppress the IMMINENCE claim specifically: "I don't need this body's
    # prizes" and "they will never actually promote this" are objections to treating it as an
    # imminent attacker, not to pre-chipping a developing win-condition on it.
    if prize_redundant or promotion_mirage:
        imminence = 0.0
    else:
        # `None` means the body or its biggest-attack cost is UNKNOWN (`combat.turns_to_afford` is
        # fail-closed there), not "it can never attack". Discounting an unknown body to zero threat
        # would be fail-OPEN, which is the direction decision 8 exists to forbid — under-counting
        # their reach feeds them the wincon. So an unknown clock takes NO discount.
        t = 0 if turns_to_afford is None else max(0, int(turns_to_afford))
        imminence = normalize(incoming_damage) / (2 ** t)

    forward = (normalize(forward_damage)
               if (is_strongest_forward and not forward_form_in_play) else 0.0)

    # GRADED, and with no imminence discount — see the module docstring and decision 10.
    forced = normalize(incoming_damage) if is_forced_promotion else 0.0

    their_plan = max(imminence, forward, forced)

    # Only the SIGN of the priority is read here. The magnitude is the caller's existing
    # `_BRIEF_THREAT_BOOST` (1.25), passed in rather than re-derived: a Brief is a SHARPENER, and how
    # hard it sharpens is already settled for the sibling instrument. Scaling the raw MatchupPlan
    # priority into this band would need a rate nothing derives — the free parameter ADR-0065 forbids.
    multiplier = 1.0
    if brief_priority > 0 and not (prize_redundant or promotion_mirage or is_tera):
        multiplier = max(0.0, float(brief_boost))
    elif brief_priority < 0 and brief_boost:
        multiplier = 1.0 / float(brief_boost)      # the mirror, so one constant governs both directions
    their_plan = min(1.0, their_plan * multiplier)

    # ── my_route ──────────────────────────────────────────────────────────────────────────────
    delta = ko_delta(turns_to_ko_before, turns_to_ko_after)
    reach = rider_reach(hp_remaining, rider_damage)
    share = prize_share(prize_value, prizes_needed)
    # Maximal, because this turn is the last one in which the route exists at all: once the line
    # reaches its `prevent_ex_damage` form my ex attacker cannot damage it, ever.
    prevent_ex = 1.0 if prevents_my_ex else 0.0
    my_route = max(delta, reach, share, prevent_ex)

    return {"relevance": their_plan * my_route,
            "their_plan": their_plan, "my_route": my_route,
            "imminence": imminence, "forward": forward, "forced": forced,
            "ko_delta": delta, "reach": reach, "share": share, "prevent_ex": prevent_ex,
            "brief_multiplier": multiplier}
