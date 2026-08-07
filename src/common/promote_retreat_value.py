"""Promote/retreat DECIDER (ADR-0100, Issue #141) — the **Sub-lethal Residual**: what remains once
the Knock-Outs available on both sides of the swap have cancelled, in the DAMAGE currency.

    promote_value(B) = my_yield(B) + closure(B) - exposure(B) + tempo_denied(B) - fatal(B)
    retreat_option   = max over bench B of promote_value(B)  +  preservation(A) - retreat_cost(A)
    pick_option(B)   = promote_value(B)

ONE evaluator, three call sites (§9): only the whether-to-retreat question at MAIN carries the
A-side terms, since they are CONSTANT across destinations and could change no ordering at a pick.

The layers SUM; nothing recuses (§1). The residual is strictly sub-lethal BY CONSTRUCTION — there is
no lethal input to pass — so it cannot double-pay the tactical layer's Knock-Out delta.

Pure over MEASUREMENTS: the Pilot fills :class:`PromoteBody` / :class:`RetreatSide`, so the equation
makes no oracle calls and every ADR-0100 ruling is assertable without constructing a board.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from common.currency import PRIZE_DAMAGE_RATE as _PRIZE_DAMAGE_RATE
from common.grading import HORIZON, halve
from common.strategy.context import ENERGY_RECOVER, KO_SCORE

#: Re-exported from `common.currency`, which owns the derivation and its recomputing test (ADR-0078).
PRIZE_DAMAGE_RATE = _PRIZE_DAMAGE_RATE


@dataclass
class PromoteBody:
    """The damage-currency reading of ONE body — a promote candidate B, or the Active A being
    retreated. Filled by the Pilot from the StateModel snapshot; every field a measurement."""

    # -- my_yield: what B earns as the new Active (§3, §3a, §3b) --------------------------------
    #: Best damage reachable THIS turn under its OWN Attach Budget — typed, so unpayable colours out.
    reach: float = 0.0
    #: ADR-0040 KO-Race per-turn wall progress (`hp / t_star`) when no affordable attack KOs this
    #: turn — else None, and `reach` stands. Vs a standing wall the single hit is fake value.
    wall_progress: float | None = None
    #: Energy this body's accel rider would attach AND a recipient can USE (`_recover_units`).
    #: FRACTIONAL — an EXPECTED count (ADR-0077); `my_yield` must not `int()` it.
    accel_units: float = 0.0

    # -- closure: the probabilistic middle (§5) -------------------------------------------------
    #: PER-ATTACK ``max`` of ``damage(a) x Δreadiness_p``; the draw window is ZERO at a forced promote.
    closure: float = 0.0

    # -- exposure / preservation: the prize side (§4) --------------------------------------------
    #: Prizes a Knock Out of this body yields — Mega ex 3, ex 2, else 1 (rules.md §6).
    prizes: int = 1
    #: `turns_to_ko_me` at the ACTIVE area — where a promoted body ARRIVES and a retreating one STANDS.
    ko_active: int = HORIZON
    #: `turns_to_ko_me` at the BENCH area, at the `HARVEST_UNAVOIDABLE` (RESCUE) reading — a benched
    #: KO the opponent can redirect denies nothing. Bench-immune Tera bodies read the full HORIZON.
    ko_bench: int = HORIZON

    # -- tempo_denied: the Threat-Clock delta (§6) -----------------------------------------------
    #: ``incoming(t=2) - incoming(t=1)`` — ONE development step's threat growth off the live curve.
    tempo_step: float = 0.0
    #: This body item-locks AND the opponent PROVABLY still holds live Item copies. Fails CLOSED (no
    #: matched Read -> no credit): the term ENDORSES a play, and ADR-0067 is fail-closed on yield.
    denies_items: bool = False

    # -- fatal: the endgame dominance band (§7a) --------------------------------------------------
    #: Prizes the opponent still needs.
    opp_prizes_remaining: int = 6
    #: This body takes a Knock Out on arrival — ruling 5's stand-down, so `fatal` does not fire on a
    #: trade we are happy to make. The KO's own magnitude is the tactical layer's (§1, §11).
    takes_ko: bool = False

    # ---- the terms ------------------------------------------------------------------------------

    def my_yield(self) -> float:
        """The two legs ADD rather than `max`: independent card features, so `max` WITHIN an axis
        and sum ACROSS (ADR-0069 §1)."""
        attack = self.reach if self.wall_progress is None else float(self.wall_progress)
        return max(0.0, attack) + ENERGY_RECOVER * max(0.0, float(self.accel_units))

    def exposure(self) -> float:
        """The prizes promoting this body HANDS the opponent, graded by the ACTIVE-area clock —
        continuous and per-body, never a boolean cliff."""
        return self.prizes * PRIZE_DAMAGE_RATE * halve(self.ko_active - 1)

    def preservation(self) -> float:
        """The clock DIFFERENCE, Active minus Bench, is the whole term. Floored at 0: a bench clock
        shorter than the Active one is a redirect artefact, not a cost of retreating."""
        return max(0.0, self.prizes * PRIZE_DAMAGE_RATE
                   * (halve(self.ko_active - 1) - halve(self.ko_bench - 1)))

    def tempo_denied(self) -> float:
        """A CEILING, not an identity: the lock denies ITEMS while the curve delta measures a WHOLE
        development step. The live-Items gate is what bounds the over-credit."""
        return max(0.0, float(self.tempo_step)) if self.denies_items else 0.0

    def fatal(self) -> float:
        """A finite dominance BAND, not a veto: when every option is fatal the residual still orders
        them. The near-goal escalation is EMERGENT from `prizes >= opp_prizes_remaining` (§7b)."""
        if self.takes_ko or self.ko_active > 1:
            return 0.0
        return KO_SCORE if self.prizes >= self.opp_prizes_remaining >= 2 else 0.0


@dataclass
class RetreatSide:
    """The A-side of a VOLUNTARY swap. Present only at the whether-to-retreat question; absent at a
    body pick and at a forced promote."""

    #: A itself, for :meth:`PromoteBody.preservation`.
    body: PromoteBody = field(default_factory=PromoteBody)
    #: **Build Standing** of A as it stands — `(matched/slots)^2 x maxDamage` on its payoff attack.
    build_before: float = 0.0
    #: Build Standing after the retreat discards its N Energy — the greedy cheapest-to-lose typed
    #: choice, retreat slots being colourless so the set is ours to pick.
    build_after: float = 0.0
    #: ADR-0069 §5c resource premium: worth ABOVE a reusable Basic, so only a one-shot is charged.
    resource_premium: float = 0.0
    #: A switch-class ITEM pays a CARD and no Energy (§11), so its cost is the card's Worth rather
    #: than a build delta. Mutually exclusive with the build legs in practice.
    card_worth: float = 0.0

    def retreat_cost(self) -> float:
        """The exact mirror of the attach decider (an attach is `+build`, a retreat pays `-build`).
        NOT refunded for recursion decks: `_recover_units` already credits that on the attack."""
        return max(0.0, self.build_before - self.build_after) + \
            max(0.0, self.resource_premium) + max(0.0, self.card_worth)


@dataclass
class PromoteRetreatInputs:
    """The board facts a promote/retreat option's value reads, so the equation stays pure."""
    #: B — the body being brought to the Active Spot.
    body: PromoteBody = field(default_factory=PromoteBody)
    #: A — the body leaving it. None at a body PICK and at a forced promote (§9).
    retreat: RetreatSide | None = None


@dataclass
class PromoteRetreatValue:
    """The value with its inner terms — the decider's legible working, so a wrong answer is
    diagnosable term by term rather than as one number."""
    my_yield: float = 0.0
    closure: float = 0.0
    exposure: float = 0.0
    tempo_denied: float = 0.0
    fatal: float = 0.0
    preservation: float = 0.0
    retreat_cost: float = 0.0
    total: float = 0.0


def promote_value(inp: PromoteRetreatInputs) -> PromoteRetreatValue:
    """ONE evaluator for all three sites: ``retreat=None`` for a body PICK or a forced promote, a
    :class:`RetreatSide` for the whether-to-retreat question at MAIN."""
    b = inp.body
    my, clos = b.my_yield(), max(0.0, float(b.closure))
    expo, tempo, fatal = b.exposure(), b.tempo_denied(), b.fatal()

    # Constant across destinations, so ONLY on the whether-site: at a pick they change no order (§9).
    preserved = inp.retreat.body.preservation() if inp.retreat is not None else 0.0
    cost = inp.retreat.retreat_cost() if inp.retreat is not None else 0.0

    total = my + clos - expo + tempo - fatal + preserved - cost
    return PromoteRetreatValue(my_yield=my, closure=clos, exposure=expo, tempo_denied=tempo,
                               fatal=fatal, preservation=preserved, retreat_cost=cost,
                               total=total)
