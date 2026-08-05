"""GRAB DECIDER — ADR-0121 (grill: Issue #406), the fifth per-seam value equation.

What is taking ONE revealed candidate into my hand worth, right now? Beside the attach (ADR-0069),
evolve (ADR-0070), promote/retreat (ADR-0100) and deploy (ADR-0086) marginals, and owning the one
seam none of them reach: a `_TO_HAND` search select, where the engine has already revealed the
candidates and the only question left is which one to take.

    grab(X) = BAND x add_relevance(X)

**One leg, and that is the whole point.** Until this equation the `_TO_HAND` grab was decided by 23
one-sided endorsement Hypotheses — `doctrine_fetch._greedy_grab` says so against itself: *"At a
BENCH grab the Deploy Marginal prices the whole cost … At a `_TO_HAND` grab there is no equation,
only one-sided endorsement rungs."* Its sibling contexts each already had one (`_TO_BENCH` →
`needs.deploy_marginal`, `_DISCARD` → `needs.cheapest_removal`), so this is the third reading of the
same assignment rather than a new model of anything.

## The marginal is `keep_v2`, unchanged

`needs.keep_v2(slots, elig, resupply, index)` is defined as ``V(all) - V(all - index)``. Take the
rows to be my hand plus exactly one candidate X, and the index to be X::

    keep_v2(X) = V(hand u {X}) - V(hand)

which is exactly the ADD-marginal of taking X. No new math and no new module on the `needs` side —
the equation this file names was already computable, and was simply never asked at this context.

**Why the candidate enters ALONE** (the grill's R2). Putting every candidate in the rows at once
makes them rivals for the same slot under `needs`' sets-not-sums assignment, so each one's marginal
is depressed by the presence of the others — yet exactly one will be taken. Every candidate must be
priced against the identical hand baseline. It is also what keeps the slot count at hand-slots + 1,
clear of `needs._MAX_KEEP_SLOTS` truncation, and what stops an unbounded-breadth DP from being
multiplied by the menu width.

## The crossing is a RATIO, and the contrast in `currency` decides it

`tactical` sums on the DAMAGE scale; `keep_v2` returns CARD-WORTH points. Handing raw Worth to a
damage-scale consumer is the ADR-0078 decision-2 violation `currency.py` exists to forbid, and that
module already contrasts the two legal crossings:

* `deploy_relevance_to_damage` takes a RATIO — *"a deploy marginal HAS a natural yardstick — the
  ceiling on one card's assignment contribution — so the Worth cancels"*;
* `item_hold_to_damage` takes a MAGNITUDE — *"a hold price has no such yardstick."*

A grab marginal is the SAME quantity as a deploy marginal — one card's contribution to the
assignment — so it has the same yardstick and takes the same route: `currency.worth_relevance`
(divide by `DEPLOY_WORTH_SCALE`) then `currency.deploy_relevance_to_damage` (times `DEPLOY_BAND`).
It must NOT take the `item_hold_to_damage` route, which is seam-scoped to the hold price and pinned
to a different anchor ratio.

**The band is nearly free here, and the reason is structural rather than lucky.** A `_TO_HAND` menu
is HOMOGENEOUS — every option is a grab, and the equation never competes against an attack or
against `End`, because a follow-up select is not `_MAIN`. So any positive band gives the same
ordering among candidates. `test_grab_value.py` asserts that invariance rather than assuming it, on
the same discipline `test_deploy_value.py` applies to the yardstick.

## Unsigned, unlike deploy

`deploy_value`'s relevance is signed because a body worth less than what it displaces is an active
mistake the equation must be able to say. A grab marginal cannot be negative — `keep_v2` is
``V(superset) - V(subset)`` over a monotone assignment — so this equation never speaks against
taking a card. **That is a deliberate limit, not an oversight**: what a card COSTS to take (it thins
the deck, and it must then be held) is the take-fewer bar's jurisdiction (`_greedy_grab`'s
``<= 0`` / the single-pick ``< 0``), not this equation's, and the two must not both charge it.

A pure function of its inputs — the Pilot resolves the board into `GrabInputs`
(`pilot._grab_decision`), so the equation stays testable at the seam and cannot reach for state it
was not handed.
"""
from __future__ import annotations

from dataclasses import dataclass

# Read through the MODULE rather than binding the names at import: the yardstick and the band are
# one source of truth in `currency`, and the scale-invariance tests re-point them to prove the ratio
# is dimensionless. A `from currency import DEPLOY_BAND` would silently defeat that.
from common import currency


@dataclass
class GrabInputs:
    """Board facts the Pilot resolves; every field is a plain number.

    ``add_marginal`` is WORTH-denominated (`needs.py` points) and is the only input that crosses a
    scale boundary — it does it as a ratio, here, once."""

    #: `needs.keep_v2` over ``hand u {candidate}`` indexed at the candidate: what TAKING this card
    #: adds to the board's resolved need coverage, in Worth points. Never negative (see the module
    #: docstring); 0 means "covers nothing my hand does not already cover", which is the honest
    #: reading a one-sided rung ladder could not express.
    add_marginal: float = 0.0


@dataclass
class GrabValue:
    """The per-leg breakdown plus the total. The breakdown is not decoration: the decider sweep
    prints it on both sides of every flip and a human rules the Decision Gate by reading it, so a
    bare total would make the gate unrulable."""

    add_relevance: float = 0.0
    total: float = 0.0

    def working(self) -> dict:
        """The legible working, for telemetry and the sweep's flip table."""
        return {"add_relevance": self.add_relevance, "total": self.total}


def grab_value(inp: GrabInputs) -> GrabValue:
    """Price one candidate grab, in the damage currency the tactical rungs already share."""
    add = currency.worth_relevance(inp.add_marginal)
    return GrabValue(add_relevance=add,
                     total=currency.deploy_relevance_to_damage(add))


__all__ = ("GrabInputs", "GrabValue", "grab_value")
