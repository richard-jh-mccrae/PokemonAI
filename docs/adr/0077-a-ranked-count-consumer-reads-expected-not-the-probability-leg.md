# ADR-0077: A ranked consumer asking HOW MANY reads `expected`, not the Probability Leg

**Status.** Accepted (grilled 2026-07-28, `/grill-with-docs` on Issue #172 — four locked decisions).
**Amends [ADR-0074](0074-a-probability-may-weight-a-ranked-value-never-gate-a-lock.md) decision 1**
(the ranked branch is not one instrument — see decision 1 below) and resolves its decision 6
"second instrument" objection for the `expected` leg (decision 2). Extends
[ADR-0061](0061-a-locking-attacks-value-includes-its-forced-follow-up.md), which owns
`_deck_basic_energy_fuel`. Terms in [src/common/CONTEXT.md](../../src/common/CONTEXT.md):
*Count Triple*, **Leg Assignment**, *Probability Leg*.

## Context

`Pilot._deck_basic_energy_fuel` ([pilot.py](../../src/common/pilot.py):4518) answers *"matching Basic
Energy a whole-deck search rider can still find in my deck."* It is the binding bound in
`_recover_units` = `min(recoverN, fuel, recipient need)`, which prices every energy-accel rider —
Cinderace's **Turbo Flare** and, on the discard path, Mega Lucario ex's **Aura Jab**.

Pre-anchor it returns the sound pigeonhole floor, `max(0, unseen - prizes_hidden)`. That floor
collapses to **zero** exactly when the rider matters most. Measured on `main` at 2026-07-28, frame
`82756664|1|decision|97` (mega_starmie, turn 9):

| | |
|---|---|
| Basic `{W}` in the decklist | 9 |
| visible (3 attached + 3 in hand) | 6 |
| unseen | 3 |
| face-down prizes | 5 |
| deck | 25 |
| **`_deck_basic_energy_fuel`** | `max(0, 3 - 5)` = **0** |

One object away, from the *same* `(u, k, d)`, the canonical derivation says:

```
deck_energy_counts = {Water: CountTriple(floor=0, expected=2.5, ceiling=3, p_any=0.9975)}
```

The read claims nothing on a deck that is **99.75 %** to hold Water. `_recover_units` becomes
`min(3, 0, 4)` = 0 and the accel dividend dies.

ADR-0074 ruled the general question the other way and built the instrument, but bounded its scope
"by a seam, not by the ticket: every consumer already ON the Budget". `_deck_basic_energy_fuel` is
ADR-0061's rider-fuel read, not a Budget consumer, so it fell outside that seam and is now the last
hand-rolled pigeonhole floor outside the `CountTriple` derivation.

**Applying ADR-0074 decision 1 literally gives the wrong answer here**, which is why this needs a
decision record rather than silent inheritance. Its ranked branch says a compared scalar "weights by
`p_any`". `p_any` answers *is there at least one?*; this consumer asks *how many will I get?* —
a graded quantity feeding a `min()`. Weighting a full count of 3 by P(≥1) claims "99.75 % chance of
all three" when the honest answer is 2.5.

## Decision

### 1. The ranked branch is not one instrument — it splits by the QUESTION

**This amends ADR-0074 decision 1.** Its gate-vs-ranked split stands unchanged. Within the ranked
branch:

- a consumer asking **"is there any?"** — a presence question whose output multiplies — weights by
  **`p_any`** (the `ko_for_prizes` prize term, the attach/promote marginals; ADR-0074 decisions 3-4);
- a consumer asking **"how many?"** — a count question whose output is compared or bounded — reads
  **`expected`**.

A LOCK consumer still may never read either. The Win Rung is untouched.

This is not new machinery: `_promote_closure` / `_evolve_income_delta` already take
`CountTriple.expected` for exactly this shape, after #167 found that passing the raw triple silently
zeroed three ADR-0070 terms on every board. The fuel read faced the identical question and answered
it the opposite way; the two now agree.

### 2. `expected` composes ADDITIVELY across types; `p_any` does not

Turbo Flare and Whimsicott ex's Energy Gift are **untyped** — verified in
`data/EN_Card_Data.csv`: *"Search your deck for up to 3 **Basic Energy** cards"*,
`recoverEnergyType=None`. `deck_energy_counts` is keyed per type, so an untyped rider needs a union —
the *"SECOND probability instrument … an untyped union beside the per-type projection"* ADR-0074
decision 6 forbids.

For `expected` that objection does not apply, because every type's leg shares the same `(d, k)`:

```
Σₜ expectedₜ  =  Σₜ nₜ·d/(d+k)  =  (Σₜ nₜ)·d/(d+k)  =  expected(Σₜ nₜ)
```

The union is **exactly** the aggregate — one derivation, two readings that cannot disagree. `p_any`
has no such identity (ADR-0074 had to take a deliberately conservative `∏` and leave the negative
correlation unmodelled), so **the untyped union stays forbidden on `p_any` and is licensed on
`expected`**. A test pins the identity so it cannot later be "optimised" into a per-type max or a
second aggregate triple.

### 3. The fuel read reads the one derivation; the hand-rolled floor is DELETED

`_deck_basic_energy_fuel` reads `MySide.deck_energy_counts` — the `_matches` closure, the
`visible`/`unseen`/`prizes_hidden` arithmetic **and the `deck_known_counts` short-circuit** all go.

The short-circuit is the point. The Pilot's hand-rolled `prizes_hidden` counts face-down entries in
`me["prize"]`, and anchoring is *our inference* — the engine never turns those cards face-up
(`me["prize"]` stays `[None, …]` throughout). So the hand-rolled value reads 5 forever while
`MySide.prizes_hidden` drops to 0 the moment the tracker resolves, and `unseen_counts` subtracts the
known prizes where the hand-rolled `unseen` does not. Under a *floor* that divergence is invisible
because the short-circuit returns before the formula runs. Under an expectation it would not be.
Keeping a second `(u, k, d)` in sync by hand is what `CountTriple` exists to make unnecessary:

> Two regimes, ONE interface … So no consumer ever branches on "are we anchored?" — the reason this
> shape beats a bare expectation.

Rejected: computing `unseen · deck/(deck+prizes)` in place. It reaches the same number today
(`me["deckCount"]` is available), but it is the bare expectation that sentence names — it *keeps*
the anchored branch and the duplicate derivation, and is a strictly larger function than the read
that replaces it.

Consequences: `_deck_basic_energy_fuel` and `_recover_units` return `float`; the latent
`is_basic_energy` / `is_typed_basic_energy` mismatch between the two paths resolves onto the typed
test. Both consumers were checked and neither gates — `_promote_accel_units` feeds the ADR-0073 §3b
dividend, and in `_tactical` the lethal branch uses `recover` only as a **capped sub-prize
tiebreak** (`min(_RECOVER_KO_CAP, …)`) *after* `dmg >= hp` has already established the KO. So
decision 1's ranked branch applies with no lock in scope.

### 4. An expectation may feed a bound or a score term — never a cost comparison

*Count Triple*'s standing caution — *"a bare expectation invites `1.6 >= 1` on a deck that holds
zero"* — is about comparing an expectation **against a cost**, and it stands. This consumer never
does: it feeds a `min()` whose product is an additive score term, which is what `expected`'s own
contract already licenses (*"for expectation math only; never comparable to a cost"*). Stated as a
rule so the boundary is greppable rather than re-litigated per consumer.

*Known approximation, stated rather than implied:* `min` is concave, so
`min(r, E[X], n) >= E[min(r, X, n)]` — a slight over-claim when `expected` sits near the binding cap.
It vanishes when `recoverN >= unseen` (the f97 case: `min` is inactive on X, so the two are equal).
Not modelled; the honest direction is documented instead.

## Verification

Frame `82756664|1|decision|97` is **evidence, never an assertion**. Its ruling is held out to
**Issue #165** as a Maneuver (`claims.decision.owner = "#165"`, ADR-0070 amendment J) and this ADR
does not take it back: the 3 Water are *in hand* at decision time — which is why `unseen` is only 3 —
and the human's line shuffles them back with **Harlequin** before attacking, so the fuel that line
actually uses exceeds both the floor (0) and the expectation (2.5). This decision makes the read less
wrong; it does not make the frame right. Asserting the flip would bank a half-earned green and strip
Issue #165 of its motivating frame.

Owed instead, at the seam:

- **tail** — `(u=3, k=5, d=25)` reads `2.5` where `floor` is `0`;
- **anchored collapse** — `k=0` reads the exact integer, proving the deleted `deck_known_counts`
  short-circuit is genuinely subsumed;
- **union identity** — `sum(expected over types) == expected(sum of unseen)` (decision 2);
- **degeneracy** — an anchored frame scores byte-identical to today. This, not the tail test, is what
  separates "thin-Energy frames moved" from "everything moved".

Plus the gates Issue #172 names, mandatory because this is a scoring change on a live shared path
(`_tactical` credits `ENERGY_RECOVER × recover` on an attack, so attack scoring moves too, not just
promote/retreat): the attach/evolve/promote decider sweeps, the Discrimination Gate, and the paired
A/B.

## Consequences

- The last hand-rolled hidden-zone count outside `CountTriple` is retired; ADR-0074 decision 2's
  "one derivation, readings that cannot disagree" holds across the whole codebase rather than across
  the Budget seam only.
- The ranked branch of **Leg Assignment** now names its instrument by the question asked, so a future
  count consumer is not pointed at `p_any` by a rule written for a multiplier.
- `expected`'s union identity is doctrine, so untyped riders (Turbo Flare, Energy Gift) have one
  licensed reading rather than a per-consumer `sum()`.
- Part (ii) of Issue #172 — that no decision-time read can see fuel a LATER STEP puts back
  (Harlequin) — is **out of scope by construction**. It is a property of step ORDER and remains
  Issue #165's.
