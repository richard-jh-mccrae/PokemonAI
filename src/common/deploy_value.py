"""Deploy DECIDER — ADR-0083 (grill: Issue #197), the fourth per-seam value equation.

What is putting ONE body into ONE Bench slot worth, right now? Beside the attach (ADR-0069), evolve
(ADR-0070) and promote/retreat (ADR-0073) marginals, and owning every way a body reaches my Bench:
the pregame placement, a `PLAY` from hand at the main menu, and a fetch straight onto the Bench.

    deploy(X) = BAND x ( assignment_relevance(X) + ability_relevance(X) )
                + accel_unlock(X)          # already damage
                - exposure(X)              # already damage

**Four legs, not five** (amendment B). The Needs assignment over the free Bench slots already prices
scarcity — if better bodies fill every slot a candidate's marginal is ~0 on its own — so a body's
contribution and what it displaces are two readings of ONE quantity (`needs.deploy_marginal`), not
two terms to subtract. Subtracting them again double-counts, which the first build did.

**The Worth legs are dimensionless RATIOS** (`marginal / currency.DEPLOY_WORTH_SCALE`), which is the
whole currency argument: the Worth points cancel, so the Worth scale never escapes the Needs
assignment and no `WORTH_DAMAGE_RATE` is referenced — a constant that does not exist and, after
ADR-0080 ruled it moot for deny, is absent by design rather than pending. `test_deploy_value.py`'s
scale-invariance test is what keeps that true: a regression that reintroduced a raw magnitude would
otherwise be silent, because the numbers would still look plausible.

Relevance here is **signed**, unlike deny's [0,1]. A strip is never actively bad; a deploy is — a
body worth less than what it displaces is a mistake, and the equation must be able to say so, because
that is how the optional-select take-fewer decline and `_finish_turn_last`'s floor come to refuse it.
Magnitude still saturates at the yardstick so one freak marginal cannot swamp the damage-native legs.

What is deliberately NOT here: the empty-Bench guard. An empty Bench under a Knocked-Out Active loses
the game on the spot (`docs/rules.md` §7 case 2), and `_LINE_CAP`'s band invariant means a bounded
positional term can never be un-outbiddable — so that guard is a post-setup SOUND RUNG above this
equation, never a leg inside it (decision 7).

A pure function of its inputs — the Pilot resolves the board into `DeployInputs`, so the equation
stays testable at the seam and cannot reach for state it was not handed.
"""
from __future__ import annotations

from dataclasses import dataclass

# Read through the MODULE rather than binding the names at import: the yardstick and the band are
# one source of truth in `currency`, and the scale-invariance test re-points the yardstick to prove
# the ratios are dimensionless. A `from currency import DEPLOY_WORTH_SCALE` would silently defeat it.
from common import currency
from common.grading import halve as _halve


@dataclass
class DeployInputs:
    """Board facts the Pilot resolves; every field is a plain number or flag.

    The two `*_marginal` fields are WORTH-denominated (`needs.py` points) and are the only inputs
    that cross a scale boundary — they do it as ratios, here, once."""

    #: `needs.deploy_marginal` for this body: the netted assignment marginal in Worth points, already
    #: capacity-bounded by the free Bench slots. SIGNED — negative when the body is worth less than
    #: what it displaces (f51's second Solrock against the Makuhita line).
    assignment_marginal: float = 0.0

    #: Worth points of the best need a bench-drop Ability's fetch could fill (Meowth ex's Last-Ditch
    #: Catch searching out a Supporter). 0 when the position needs nothing the fetch can supply —
    #: which is "only bench it when we need a SPECIFIC Supporter", as arithmetic rather than a rule.
    ability_marginal: float = 0.0

    #: P(the fetchable class is still in deck). A ranked consumer WEIGHTS by probability and never
    #: gates on it (ADR-0074).
    ability_odds: float = 0.0

    #: Whether the bench-drop trigger can fire at all. False covers three facts that are one fact —
    #: Set Up precedes the first turn so "once during your turn" is unsatisfiable; the card's own
    #: "no more than 1 Last-Ditch Ability each turn"; and a body with no such Ability. The Pilot owns
    #: deciding which; the equation only needs to know the trigger is dead.
    ability_can_fire: bool = False

    #: Whether this turn's one Supporter is already played (`rulebook.txt` L133). A fetch made after
    #: it banks for NEXT turn and takes the shared one-turn discount.
    supporter_quota_spent: bool = False

    #: DAMAGE the Attach Budget realises because a legal landing spot now exists (decision 8) —
    #: ADR-0069's `this_turn` counterfactual applied to a deploy option. Scales with the accelerator's
    #: real yield, so a 3-Energy Turbo Flare pays more than a 1-Energy trickle, and is 0 when the
    #: accelerator is not Active or already has a recipient.
    accel_unlock: float = 0.0

    #: PRIZE-equivalents by which deploying this body shortens the opponent's cheapest Prize Path
    #: (decision 5). Positive = a gift. Converted through `PRIZE_DAMAGE_RATE`, never the deploy band.
    exposure_prizes: float = 0.0

    #: `needs.phase_scale` — sharpens the prize-denominated leg as the opponent nears their last
    #: Prize. 1.0 is the neutral read.
    phase: float = 1.0


@dataclass
class DeployValue:
    """The per-leg breakdown plus the total. The breakdown is not decoration: the decider sweep
    prints it on both sides of every flip and a human rules the Decision Gate by reading it, so a
    bare total would make the gate unrulable."""

    assignment_relevance: float = 0.0
    ability_relevance: float = 0.0
    accel_unlock: float = 0.0
    exposure: float = 0.0
    total: float = 0.0

    def working(self) -> dict:
        """The legible working, for telemetry and the sweep's flip table."""
        return {"assignment_relevance": self.assignment_relevance,
                "ability_relevance": self.ability_relevance,
                "accel_unlock": self.accel_unlock,
                "exposure": self.exposure,
                "total": self.total}


def _relevance(worth_marginal: float) -> float:
    """A Worth-denominated marginal as a dimensionless, signed, saturating ratio.

    The yardstick is FIXED and board-independent on purpose (amendment C): the deploy marginal
    competes against `End` (0) and against attacks, so the ratio must mean the same thing on every
    board. Normalising per decision — dividing by the best candidate at THIS decision — was rejected
    on correctness, because the best available deploy would read 1.0 whether it is excellent or
    merely least-bad, and the agent would deploy every turn."""
    scale = float(currency.DEPLOY_WORTH_SCALE)
    if scale <= 0:                                   # defensive: never divide by a re-banded zero
        return 0.0
    return max(-1.0, min(1.0, float(worth_marginal) / scale))


def deploy_value(inp: DeployInputs) -> DeployValue:
    """Price one candidate deploy, in the damage currency the tactical rungs already share."""
    assignment = _relevance(inp.assignment_marginal)

    ability = 0.0
    if inp.ability_can_fire:
        odds = max(0.0, min(1.0, float(inp.ability_odds)))
        ability = _relevance(inp.ability_marginal) * odds
        if inp.supporter_quota_spent:
            # Cashable only next turn — graded by the shared halving convention (ADR-0070 §6) rather
            # than a decay rate invented for this equation.
            ability *= _halve(1)

    accel = float(inp.accel_unlock)
    exposure = float(inp.exposure_prizes) * float(inp.phase) * currency.PRIZE_DAMAGE_RATE
    total = currency.deploy_relevance_to_damage(assignment + ability) + accel - exposure
    return DeployValue(assignment_relevance=assignment, ability_relevance=ability,
                       accel_unlock=accel, exposure=exposure, total=total)
