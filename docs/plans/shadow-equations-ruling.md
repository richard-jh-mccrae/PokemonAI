# Standing ruling: build the equation anyway — run it in SHADOW beside the rungs

**Ruled by the user, 2026-07-19.** Applies to every current and future value-equation effort (the
gusting `their_keep_cost` design, the hand-disruption build, the attach valuation, promote/retreat,
and any later convergence). Supersedes the narrow reading of the anti-speculation clause in the
grill specs; candidate for ratification as an ADR when the next equation ships under it.

**First equation shipped under this ruling (2026-07-19): the DISCARD keep-cost shadow**
(`pilot._discard_shadow` — see `seam-discard-convergence.md` §Shadow emitter). It followed the
mechanism below verbatim (decision-point compute, full working + agreement bit, the gamble-trace
plumbing, mid-sim guard) and its first corpus sweep produced disagreement rows on 9 of 12 recorded
discard decisions — the evidence bridge working as designed. ADR ratification is now on the table.

**The migration path this bridge feeds was RULED 2026-07-19** (see `seam-discard-convergence.md`
§Grill RULING): *gates real, equation shadow, swap gated-last.* The generalisable insight for every
future convergence — a GATE (a Worth factor) is built real and fires live under a corpus gate, while
the DECISION SITE it feeds rides as a shadow until its agreement rate earns the swap. Factors and
deciders are gated differently: the factor by its live consumers, the decider by the shadow.

## The ruling (user's words, lightly edited)

> "What I want is general card/action value equations that solve related decisions gracefully,
> consistently, and correctly. If that equation exists where many, many features from manual
> corrections currently work fine, I'd still like the equation's inner workings and output on the
> side of the emit() output, for eventual replacement of the features. I want cleanliness and
> elegance and correctness over many different features all firing in combination."

## What changes

**Before:** anti-speculation blocked BUILDING an equation until corpus corrections demanded a
behavioural change (the grab/pitch precedent: measured, found subsumed, built nothing).

**Now:** anti-speculation governs *behaviour change only*. An equation whose design is settled gets
BUILT and run in **shadow** — computed at the real decision point, its inner working and output
emitted beside the decision, **deciding nothing**. A rung family passing its corrections no longer
blocks the equation's construction; it only blocks the *swap*.

The end state is still replacement, not eternal shadow: the user's goal is ONE equation over many
rungs firing in combination. Shadow is the evidence bridge.

## The mechanism (the gamble-trace precedent — reuse it, don't invent)

The full pattern already ships for the gamble rung: `_gamble_trace` → `Decision.gamble` → the
sparse `@T` stderr key → the blunder-shell `<details>` dropdown. A shadow equation follows it
exactly:

1. Compute at the decision point (same inputs the rungs see). **Mid-sim guard applies** — never
   write traces under `self._planning`; keep the shadow cheap enough for live play (memoise the
   deck-fixed legs, the closure discipline).
2. Emit per-option: the equation's OUTPUT (its ranking/score) AND its inner working (the terms —
   e.g. for attach: the P-delta, the deadline, the valued attack, `resource_cost`) — enough that a
   human reading the dropdown can audit WHY, the ADR-0019 full-working standard.
3. Emit the AGREEMENT bit: did the equation's top pick match the rungs' chosen option? Disagreement
   rows are the telemetry gold — each one is either a shadow bug or a latent rung bug; /blunder-
   buster rounds and the corpus adjudicate which.
4. The SWAP stays gated exactly as before: per family, corpus + score-diff + the currency-zone rule
   (the equation REPLACES the rung family it shadowed, and the shadow telemetry is the evidence).

## Immediate consequences (2026-07-19 state)

- **Gusting `their_keep_cost`** (`gusting-keepcost-design.md`, designed-not-built, "waits for
  corpus evidence"): the wait is REPEALED for construction — build it as a shadow emitter; the
  corpus wait now governs only the swap. The ADR-0066 rulings (≤ ~1 effective-prize denial
  ceiling; stall stays separate) bound the equation it shadows.
- **Hand-disruption build (in flight):** ship its graded STRIP/GIFT + damage-swing terms in shadow
  first if the ADR-0060 pins constrain a direct swap; the pins then arbitrate promotion.
- **Attach valuation** (`attach-valuation-grill-spec.md`): the queue-behind-the-exchange-rate
  blocker softens — the shadow oracle can be built while the unit question settles, since a shadow
  emits in its own units harmlessly. The grill still rules the design; Round 0 still runs (it now
  classifies replacement PRIORITY rather than gating construction).
- **Elegance pressure is now a standing requirement:** when a shadow equation and a rung family
  agree everywhere over a telemetry window, that agreement is itself the argument to RETIRE the
  rungs (fewer features firing in combination) — file the swap, don't let both live indefinitely.
