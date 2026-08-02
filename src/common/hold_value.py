"""HOLD price — what SPENDING a held card costs, for every free-Item decider (Issue #261 item 2f,
old Issue #212).

A free Item is tiered ahead of everything by `pilot._finish_turn_last`, so **a purely positive term
can never DECLINE one**: any score above zero gets it played, and a score of exactly zero ties End
and gets it played by option index (ADR-0093 decision 4). Declining requires a strictly negative
score, which requires the play to be priced NET of keeping the card.

ADR-0062 solved that for one card class with a constant::

    _DENIAL_ITEM_COST = 10     # the value of KEEPING the Hammer

and its only consumer was gated shut for everything else, so *"an Item is finite"* was priced for
Crushing / Enhanced Hammer and for no other card in the pool. This module is the generalisation the
POC plan asks for — *"generalize `_DENIAL_ITEM_COST` into the keep machinery"* — as ONE price any
free-Item decider can consume.

## The two facts a hold price is made of

    hold(card) = max( keep_v2(card), ITEM_HOLD_FLOOR ) x ITEM_HOLD_WORTH_RATE

**The assignment leg** is `needs.keep_v2` over the whole hand: the exact counterfactual marginal of
no longer holding this card, against the board's resolved NEEDS. Board-derived, so a card covering a
live need is dear and a card covering nothing is cheap — the same machinery the refresh SHED
(ADR-0101) and the discard decider (ADR-0065 WP-N4) already decide on. One keep question, one answer.

**The floor** is the finiteness the assignment cannot see, and it is load-bearing rather than
decoration. Measured on the four committed deny anchors, a Crushing Hammer's `keep_v2` is
`0.00 / 4.82 / 3.57 / 0.00` — **below the incumbent 10 on every one, and exactly 0 on two of them**,
because a role-less Hammer's only slot is the very `deny` slot the fire rung is already pricing
(`card_worth.TAG_TIER`: *"A role-less Hammer still prices its global worth 0; only its live-strip
DENY slot earns the band"*). So on a whiff the assignment says keeping it is worth nothing, the net
is exactly 0.0, and ADR-0093 decision 4's defect walks straight back in. Worse, two Hammers in hand
solo-price 0 each against one deny slot (sets-not-sums, correctly), so the copy being spent looks
free precisely when the hand is richest in it.

A card spent is a card gone whatever the assignment covers. That is what the floor says, and
`max` — not `+` — is what says it: the floor is a LOWER BOUND on the card's worth, not a surcharge
on top of it, so a card whose live need already exceeds it is not charged twice. It is the same
shape `needs.keep_v2` uses for its own `intrinsic` hedge, deliberately: this is a second hedge of
that kind and not a new arithmetic.

**Consequence, stated precisely rather than over-claimed:** the swap is byte-identical for deny
*wherever the floor binds*, and the floor binds on **every committed deny anchor** — measured, four
of four, not asserted. It is NOT identical by construction: `keep_v2` above the floor is reachable
in principle (a Hammer covering a second live `deny` slot), and if a future board reaches it the
Hammer costs more to spend than the incumbent charged, which is the equation working rather than
drifting. Issue #212's scope note (*"Generalising must not perturb the deny 5/5"*) is therefore met
by MEASUREMENT over the ruled frames, and the useful corollary holds on those frames: gate movement
in the build that introduced this is attributable to the sequencer boundary beside it, not to the
price.

Pure and lib-free; the Pilot resolves the board facts and passes the keep value
(`pilot._item_hold_price`) — the `gate_library` / `deploy_value` pattern.
"""
from __future__ import annotations

# Read the rate through the MODULE, not by binding the name at import: `currency` owns every scale
# crossing in one place, and a `from currency import ...` would let a re-pointed rate be silently
# ignored here (the `deploy_value` precedent, and the reason its scale-invariance test can work).
from common import currency

#: The FINITENESS floor, in WORTH points (`card_worth`'s scale): what spending a card costs when the
#: Needs assignment says it covers nothing. **AUTHORED, not derived** — whitelisted under
#: `sound_rules.firing-equation-constants`, which is the honest label for it.
#:
#: The value is `_DENIAL_ITEM_COST`'s, re-homed rather than re-derived. Issue #212 put re-deriving it
#: explicitly OUT of scope (*"It is derived and its derivation is re-confirmed as of ADR-0062
#: Amendment A"*), and keeping it is what makes the generalisation behaviour-preserving where the
#: incumbent already ruled. It is also exactly `card_worth.TAG_TIER["gust"]` — the disruption-Trainer
#: band — which is the pairing `currency.py` already catalogues as the "trainer ~1.0" worth<->damage
#: entry. Not asserted as a coincidence: it is why the rate below is 1.0.
ITEM_HOLD_FLOOR = 10.0


def hold_price(keep_worth: float) -> float:
    """What spending a held card costs, in the DAMAGE currency the tactical rungs share.

    ``keep_worth`` is the card's `needs.keep_v2` marginal in Worth points — the Pilot resolves it
    (`pilot._item_hold_price`). Negative or absent reads as 0: an assignment marginal is never a
    reason to think spending a card is a GAIN, and the floor is what a free Item pays regardless.

    Always strictly positive, which is the contract the sequencer needs: a decider that subtracts
    this can reach a negative score and so can DECLINE a free Item, where a purely positive term
    never can."""
    worth = max(0.0, float(keep_worth), ITEM_HOLD_FLOOR)
    return currency.item_hold_to_damage(worth)


__all__ = ("ITEM_HOLD_FLOOR", "hold_price")
