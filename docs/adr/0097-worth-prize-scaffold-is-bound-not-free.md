# ADR-0097 — The Worth→prize scaffold is BOUND: reconciled, dated, and its underivability premise is void

**Status:** Accepted (grilled 2026-08-01, `/grill-with-docs` on Issue #259, wave-1 packet item 4).
**Build = Issue #259 (POC-T0 registry + contract note), value authored in T3.**
**Amends [ADR-0078](0078-currency-owns-the-exchange-rates.md)** (which owns the scale bridges and
records the reconciliation debt this discharges in one direction) and
**voids the structural half of [ADR-0080](0080-deny-is-a-categorical-relevance-instrument.md) /
[ADR-0086](0086-the-deploy-marginal-prices-a-bench-slot-and-what-fills-it.md)'s underivability
finding** — not by disputing the measurement, but because the POC's architecture removes the premise
it rested on. Does **not** supersede anything.

⚠️ **Temp-named, not numbered.** Real number assigned at `/open-pr` rebase time. Cite the issue.

**Context issues:** Issue #259 (this grill), Issue #199 / ADR-0080 (ran the deny anchor gate and it
failed), Issue #197 / ADR-0086 (ran the deploy anchor sweep and it failed), Issue #172 (derived
`ENERGY_RECOVER` and moved the catalogue gap from ~9x to ~6.7x without closing it).

## Context

Wave-1 packet item 4 asks approval for `POC_WORTH_PRIZE_RATE`: "one authored scaffold constant
crossing Worth→prize inside `state_value` only (module-local, tagged authored-not-derived,
whitelisted, retired by the post-POC learning phases; `common/currency.py` and `test_currency.py`
untouched)."

### Measured 2026-08-01 at source, not recalled

`src/common/currency.py` holds one genuinely derived bridge and no Worth bridge:

```
PRIZE_DAMAGE_RATE = 100.0     DERIVED — median HP-per-prize over 1061 bodies in
                              data/EN_Card_Data.csv; test_currency.py RECOMPUTES it from the CSV
                              rather than pinning the literal
WORTH_DAMAGE_RATE             ABSENT BY DESIGN — the anchor gate was RUN and FAILED (ADR-0080)
```

But the same module catalogues **three** de-facto worth↔damage rates that disagree by ~6.7x:

```
trainer   TAG_TIER["gust"] 10.0  vs  _DENIAL_ITEM_COST 10        ~1.0
energy    ENERGY_TIER      8.0   vs  ENERGY_RECOVER  160/3       ~6.7
deploy    DEPLOY_BAND / DEPLOY_WORTH_SCALE = 25/30               ~0.83
```

The third is labelled without euphemism — *"Stated plainly rather than buried:
`DEPLOY_BAND / DEPLOY_WORTH_SCALE` has units of damage-per-worth-point. It IS a worth↔damage rate,
scoped to one seam"* — and carries an explicit **RECONCILIATION DEBT**: "if a general Worth Damage
Rate is ever derived, `DEPLOY_BAND / DEPLOY_WORTH_SCALE` must be checked against it."

### The premise the POC destroys

ADR-0086's reason for underivability is **structural**, not a corpus gap:

> "a deploy is never exclusive with a damage-denominated option (benching consumes no attach, no
> Supporter slot, and does not end the turn), so it cannot TRADE against one, and the only genuine
> competitor for a Bench slot is another deploy — worth versus worth, carrying no rate information."

Under ADR-0092's hybrid differencing that is no longer true. `value(play) = state_value(after) −
state_value(before)`. Before the play the card is in hand — the `hand` term, Worth-denominated.
After it, the card is on the board — `development` / `readiness`, prize-denominated. **The
difference crosses the scale boundary by construction, and the Worth does not cancel.** This holds
for *every play that spends a card*, not only deploys.

Two consequences, opposite in sign:

1. `POC_WORTH_PRIZE_RATE` is **not** a narrow scaffold for one term. It is the global constant
   setting what a card in hand costs, on essentially every decision the POC makes. The blast radius
   in the packet's framing ("module-local") understates it by a wide margin.
2. The corpus now **does** generate anchors. Every ruled spend-vs-hold frame is an observation on
   the rate. That is precisely the evidence the old architecture structurally could not produce,
   which is why both prior gates failed.

## Decision

**Approve the mechanism, BOUND by three conditions.** `POC_WORTH_PRIZE_RATE` is module-local to
`state_value`, tagged authored-not-derived, and whitelisted — as the packet proposes — and
additionally:

**1. Reconciled at authoring, not isolated.** Its authoring note converts the value to
damage-per-worth-point and states its position against the three incumbents (trainer ≈1.0, energy
≈6.7, deploy ≈0.83). A disagreement is **recorded, not hidden**. This discharges `currency.py`'s
reconciliation debt in the direction of evidence. ADR-0078's founding complaint was that two
constants priced the same object differently; adding a fourth silently would repeat it with the
largest blast radius yet.

**2. A pre-registered retirement test.** Stated in the T0 registry now: post-POC, fit the rate
against ruled spend-vs-hold frames; retire the authored value iff the fit converges. An authored
scaffold with no retirement test becomes permanent — the same failure mode this grill's bench filter
decision guards against (ADR-0096 decision 1).

**3. The underivability premise is recorded VOID.** The T0 registry states that ADR-0080/0086's
structural argument does not survive differencing, so the post-POC derivation begins from a stated
anchor rather than re-running a gate that has already failed twice for a reason that no longer
applies. The measurements themselves stand; only their premise expires.

`common/currency.py` and `tests/strategy/test_currency.py` remain **untouched**, exactly as the
packet specifies — ADR-0080's underivability measurement is a record of what was true, and this ADR
does not edit it.

## Consequences

- Authoring the number now requires arithmetic against three incumbent rates and publishing a
  disagreement. That is the cost, and it is the point.
- A second dated obligation joins the registry beside ADR-0096's filter-retirement test.
- If the reconciliation shows `POC_WORTH_PRIZE_RATE` landing far outside the ~0.83–6.7 spread, that
  is evidence about the *incumbents* as much as about this constant — ADR-0078's own rule ("a
  disagreement is evidence about ONE of the two rather than automatically about this one") applies.
- Refusing the crossing entirely was considered and rejected: it prices holding a card at zero
  against playing it, which makes every free Item strictly worth playing — the defect
  `_DENIAL_ITEM_COST` patches for Hammers and Issue #212 is generalizing.
