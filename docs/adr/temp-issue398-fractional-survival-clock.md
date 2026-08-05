# ADR-TEMP-398 - The survival clock is read fractionally; opponent-target discrimination is recovered, not authored

⚠️ **Temp-named, not numbered.** Real number assigned at /open-pr rebase time. Cite the issue.

**Status:** Accepted (grill of Issue #398, 2026-08-05). Amends **ADR-0071 decision 4**.

## Context

`pilot._opponent_target_rows` prices every opponent body as
`needs.opponent_target_value(prize_advance, survival_shift, phase)`, where `prize_advance` is
`CardStat.prize_value ∈ {1,2,3}` and `survival_shift` is `Δ turns_to_ko_me` under removal of that
body.

Measured over the correction corpus (359 frames producing target rows):

- **343** equal-prize groups exist — two or more opponent bodies whose `prize_advance` ties.
- `survival_shift` breaks that tie in **92 (26.8%)**.
- **251 (73.2%) remain perfectly tied**, every row carrying identical value; the winner is decided
  by list order.

Frame `81906755|1|decision|77` is the shape: five 2-prize bodies, all valued exactly `2.0`.

The cause is quantization, not a missing feature. `CombatMath.turns_to_ko_me` accumulates
`incoming()` and returns the first integer turn at which `dealt >= hp`. `dealt` is continuous;
the integer is only where it crosses. Removing a body lowers `dealt` at every horizon, and that
reduction is discarded unless it happens to move a threshold.

The discarded quantity is exactly the one the discrimination needs. `incoming()` prices through
`predicted_max_damage` — the Damage Formula, so scaling attacks are priced correctly — and its
availability gate is all-descendants: *"the evolution reach is already MAXIMAL at `t=1`
(`forward_card_ids` is all-descendants, existence-gated: every forward form is considered under the
current energy budget)"*. So the clock already accounts for energy cost, printed and scaled damage,
riders, weakness, live boosts, **and the forward evolution closure**. Dragapult ex (200 at
`maxDamageCost` 2, plus a 60 spread) and Latias ex (200 at cost 3) are distinguishable today, and
the distinction is rounded to zero.

Two alternatives were considered and rejected during the grill:

- **An authored feature blend** over `maxDamageCost` / `hp` / `tera` / `retreatCost` / riders. Every
  weight would be a new authored constant requiring a sound-rule whitelist entry and eventual
  reconciliation, and it would re-derive by hand what `incoming()` already composes from card data.
- **Roles supplying the magnitude** (Issue #395's shape, and three successive proposals during this
  grill). This makes the role system load-bearing for a class of card it has no special knowledge
  about, and fails silently at γ = 0 — an unroled body in an unrecognised matchup gets nothing,
  where the derivation would have priced it correctly with no Read at all.

## Decision

**Interpolate the crossing to a fractional turn, and expose it beside the integer.**

```
t* = (t_cross − 1) + (hp − dealt(t_cross − 1)) / incoming(t_cross)
```

One additional line in the existing accumulate loop. No new constant, no new composition, no new
oracle. `survival_value` already takes turns, so units and `_SURVIVAL_CAP` are unchanged.

The integer return is preserved byte-identically for every current caller; only the opponent-target
equation opts into the fractional reading. A second oracle was rejected for the reason this issue
exists at all — two answers to one question drift, and nothing reports it.

## Policy

- **Discrimination is recovered from the existing composition, never authored beside it.** A
  proposal to add a weighted feature to opponent-target value must first show the quantity is not
  already computed inside `incoming()` and discarded.
- **Roles do not supply magnitude for anything card facts can price.** Their scope is the
  non-damage ability dimension (see Issue #395 as re-scoped, and
  `gusting-keepcost-design.md` §2), sourced from `card_functions.json` tags first so the general
  tier stays γ-independent, with the Brief correcting rather than originating.
- **The fractional reading is opt-in.** A caller taking it states why at the call site; the integer
  stays the default so ADR-0071 decision 4's accumulate semantics are unchanged for every family
  that was not measured here.

## Verification

- The 73.2% flat-tie measurement is reproducible from
  `tools/train/probes/opponent_target_credit_sweep.py`; its denominators (359 frames with rows, 343
  equal-prize groups) are printed per run.
- A fractional `survival_shift` must beat the **sham leg** by a wide margin under
  ADR-TEMP-398-SHAM's bar. It is the first leg in this area with a real null to clear, and a
  fractional clock that only matches the sham has recovered nothing.
- `decider_lab.py diff --baseline data/decider_lab/baseline.json` runs on this change **alone**
  (Issue #398 landing sequence, PR (a)), so its flips are attributable to the clock and not to the
  denial work that follows. The Decision Gate was measured GREEN on the unmodified tree at
  `37f5975` (agree 251/340, 0 picks moved), which is the control this comparison needs.
- Every current caller of `turns_to_ko_me` must be byte-identical after the change; the fractional
  value is additive, not a replacement.
