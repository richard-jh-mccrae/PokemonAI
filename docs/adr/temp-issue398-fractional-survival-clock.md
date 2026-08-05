# ADR-TEMP-398 - The survival clock is read fractionally, and the Flat Tie is measured to be STRUCTURAL

⚠️ **Temp-named, not numbered.** Real number assigned at /open-pr rebase time. Cite the issue.

**Status:** Accepted (grill of Issue #398, 2026-08-05). Amends **ADR-0071 decision 4**.
**Amended 2026-08-05, before merge**, by its own build-time measurement — see *Correction* below.
Issue #398 is **NOT closed by this ADR**; the defect it names is still open.

## Correction — what this ADR originally claimed, and what the measurement said

The first draft of this ADR asserted:

> The cause is quantization, not a missing feature. […] The discarded quantity is exactly the one
> the discrimination needs.

**That is false as a dominant cause, and it was the premise the whole decision rested on.** It was
written from the shape of the accumulate loop, not from a differential measurement, and the
differential measurement was only run when the change was built.

`tools/train/probes/fractional_clock_sweep.py` runs the pre- and post-change rankings over the
correction corpus, reconstructing the pre-change arm by patching the SHIPPED model route rather
than reimplementing it (a reimplementation would be the second oracle this ADR elsewhere refuses):

| arm | equal-prize groups | tied on VALUE (the Flat Tie) | tied on `survival_shift` |
|---|---|---|---|
| integer clock (pre) | 343 | **281 (81.9%)** | 251 (73.2%) |
| fractional clock (post) | 343 | **253 (73.8%)** | 219 (63.8%) |

**Quantization was 10.0% of the Flat Tie, not the Flat Tie.** 28 groups recovered; 253 survive.

⚠️ **The right-hand column is what the first draft of this correction reported, and it was the
wrong quantity** — caught in review, not by the instrument. A Flat Tie is identical **`value`**,
because `value` is what the ranking sorts on and therefore what falls through to list order. Ties on
`survival_shift` are a strict SUB-population: equal prize plus equal shift forces equal value, but
the converse fails, because `needs.opponent_target_value` floors the shift at `max(0.0, shift)` (so
rows with different NEGATIVE shifts collapse to one value) and at `phase == 0` the survival term
vanishes entirely. Measuring the sub-population biased both directions at once — it understated the
defect (73.2% against a true 81.9%) and overstated the recovery (32 groups against a true 28). The
73.2% headline Issue #398 was FILED on carries the same error; it came from
`opponent_target_credit_sweep.py`, which compared the same wrong field.

The MECHANISM is read off the `survival_shift` column (the right-hand one above), and there it is
unambiguous — every one of the 219 shift-tied groups is tied at **exactly 0**, never at a shared
non-zero value, and 1036 of 1244 opponent bodies price at exactly 0:

```
equal-prize groups          : 343
  discriminated             : 124      <- on `survival_shift`; on `value` it is 90
  STILL TIED, all shifts = 0: 219
  still tied at a non-zero  : 0        <- NOT ONE. The residue is a hard zero, not a near-miss.
per-body shift distribution : {exactly 0: 1036, fractional: 203, integral >0: 5}
```

The `still tied at a non-zero: 0` row is the load-bearing one: if the residual ties were rounding,
some group would tie at a shared non-zero shift. None does.

### The real cause: `incoming()` is a per-turn MAXIMUM

`CombatMath.incoming` takes `worst = max(worst, ...)` over their attacker forms — the sum of
per-turn **maxima**, which ADR-0071 decision 4 chose deliberately as the bounded-pessimism reading.
A removal Δ therefore has a structural consequence nobody had stated:

> **Removing a body that is not the argmax leaves the maximum untouched, so its removal Δ is
> exactly 0 at ANY resolution.** A body scores only where it is the UNIQUE argmax at some turn at
> or before the crossing; where two bodies tie for the lead at every turn, NEITHER scores.

⚠️ **A stronger form of this claim was drafted and is false.** The first version read *"at most ONE
body per board can carry a non-zero `survival_shift`"*. That is wrong: `incoming(t)` grants each
form `attached + t` energy, so the leading form can CHANGE across turns, and every body that leads
at some turn before the crossing scores. Constructed counter-example, verified — my 300 HP, their
`Early` (cost 1, 100/turn) and `Late` (cost 3, 250 from t=3):

```
both present            -> turns=3 exact=2.4
remove Early            -> turns=4 exact=3.2    shift +0.8000   (led at t=1,2)
remove Late             -> turns=3 exact=3.0    shift +0.6000   (led at t=3)
```

Both score. The corpus average (208 non-zero shifts over 359 frames) is consistent with the false
form, which is exactly why an average must not be read as a bound. Pinned as
`test_more_than_one_body_scores_when_the_lead_changes_across_turns`.

The weaker, true form is confirmed analytically where the lead does NOT change
(`tests/strategy/test_opponent_target_value.py`):

```
board [C60, D90, A]     remove C60 -> +0.0000   (never leads)
                        remove D90 -> +0.0000   (never leads)
                        remove A   -> +0.1111   (leads at every turn)
board [A, A]            shifts [0.0, 0.0]       (neither is the UNIQUE lead)
```

The consequence for the live seam is sharper than the corpus average suggests: `gust_target_slot`
reads the **Bench only**, and the opponent's Active is usually the per-turn maximum — so on the
scope that actually decides, `survival_shift` is structurally incapable of ranking anything. **The
missing feature this ADR originally argued was absent is real.**

## Context

`pilot._opponent_target_rows` prices every opponent body as
`needs.opponent_target_value(prize_advance, survival_shift, phase)`, where `prize_advance` is
`CardStat.prize_value ∈ {1,2,3}` and `survival_shift` is `Δ turns_to_ko_me` under removal of that
body. Measured over the corrections corpus, 281 of 343 equal-prize groups carried an identical
value and the winner was decided by list order. Frame `81906755|1|decision|77` is the shape: five
2-prize bodies, all valued exactly `2.0`.

Two causes were conflated in the original filing and are now separated:

1. **Quantization** (10.0%). `turns_to_ko_me` accumulates `incoming()` and returns the first integer
   turn at which `dealt >= hp`. `dealt` is continuous; the integer is only where it crosses. Where a
   removal *does* move the maximum, the size of that move was being rounded away. **This ADR fixes
   this cause and only this cause.**
2. **The max structure** (90.0%). Above. **Not addressed here.** It needs a term that is not a
   removal-Δ of a maximum, and designing that is Issue #398's remaining work.

For cause 1 the fix is genuinely free: `incoming()` prices through `predicted_max_damage` (the
Damage Formula, so scaling attacks are correct) and its availability gate is all-descendants —
*"the evolution reach is already MAXIMAL at `t=1`"* — so energy cost, printed and scaled damage,
riders, weakness, live boosts **and the forward evolution closure** are already composed into
`dealt` before the threshold discards the remainder.

## Decision

**Interpolate the crossing to a fractional turn, and expose it beside the integer.**

```
t* = (t_cross − 1) + (hp − dealt(t_cross − 1)) / incoming(t_cross)
```

One additional line in the existing accumulate loop, returned as `SurvivalClock(turns, exact)`.
No new constant, no new composition, no new oracle. `survival_value` already takes turns, so units
and `_SURVIVAL_CAP` are unchanged.

The integer return is preserved byte-identically for every current caller — `turns_to_ko_me` is
defined as `survival_clock(...).turns`, so the two readings cannot drift. Only the opponent-target
equation opts into the fractional reading. A second oracle was rejected for the reason this issue
exists at all: two answers to one question drift, and nothing reports it.

**This decision is kept on its merits, not on its original rationale.** It is correct, costs
nothing, recovers 28 real groups (62 → 90 discriminated on value), and any future fix that differences the
clock wants the precision. It is a **prerequisite for** the fix to Issue #398, not the fix.

## The two alternatives: RE-OPENED, not defeated

The original draft rejected both. Each rejection was argued against the "quantization is the cause"
premise, and that premise has failed. Neither rejection stands as written; both are open questions
for Issue #398's re-grill, restated here with what survives of the original objection:

- **An authored feature blend** over `maxDamageCost` / `hp` / `tera` / `retreatCost` / riders. The
  original objection — *"it would re-derive by hand what `incoming()` already composes"* — is now
  known to be wrong in the direction that matters: `incoming()` composes those facts into a
  **maximum**, which discards every non-leading body by construction. What survives of the
  objection is only the cost: each weight is a new authored constant needing a sound-rule whitelist
  entry.
- **Roles supplying the magnitude** (Issue #395's shape). The original objection — that it fails
  silently at γ = 0, where *"the derivation would have priced it correctly with no Read at all"* —
  assumed a derivation that prices unroled bodies correctly. Measured, that derivation prices 83%
  of bodies at exactly 0. The γ = 0 objection is materially weakened.

## Policy

- **A causal claim about a ranking requires a DIFFERENTIAL measurement, not a reading of the code
  that produces it.** This ADR's original claim was derived from the shape of the accumulate loop
  and was wrong by a factor of seven. The loop was read correctly; what was never measured is how
  much of the observed effect it accounts for. Reading an implementation tells you what a term
  *can* do, never what share of an outcome it *does*.
- **State the aggregation when stating a removal Δ.** A Δ under a `max` is zero for every
  non-leading element, and that is a property of the aggregation rather than of the elements. Any
  future term defined as "the difference made by removing X" must say what it is differencing.
- **The fractional reading is opt-in.** A caller taking it states why at the call site; the integer
  stays the default, so ADR-0071 decision 4's accumulate semantics are unchanged for every family
  that was not measured here (`survival`, `readiness`, `threat` each carry scale anchors calibrated
  against the integer clock).
- **Discrimination is recovered from the existing composition where the composition HAS it.** The
  original blanket form of this policy — never author beside the derivation — is narrowed to its
  defensible core: before adding a term, check whether the quantity is already computed and
  discarded. Here it was, for 10.0% of the problem. For the other 90.0% it is not computed at all,
  and a policy forbidding new terms would forbid the fix.

## Verification

- The pre/post tie population is reproducible from
  `tools/train/probes/fractional_clock_sweep.py`, which prints both arms and their denominators per
  run. **This is the bar this change clears**: 281 → 253 tied on value, 62 → 90 discriminated.
- **The sham bar is reported and NOT cleared, and that is stated rather than buried.** Under
  ADR-TEMP-398-SHAM, bench argmax movement:

  | arm | moves |
  |---|---|
  | fractional clock | 8/241 (3.3%) |
  | sham `cid % 7` | 64/241 (26.6%) |
  | sham `hp % 70` | 59/241 (24.5%) |
  | sham position | 147/241 (61.0%) |

  The honest reading: the shams break ties **arbitrarily**, while the clock declines to break the
  83% that are structurally zero. Moving *less* than a sham is evidence the term is not noise; it
  is not evidence the term is good, and it is not a claim to have fixed Issue #398. A movement
  number is the wrong instrument for a leg whose correct behaviour is to leave most orderings
  alone — which is itself a limit of the sham policy worth carrying into ADR-TEMP-398-SHAM.
- Every current caller of `turns_to_ko_me` is byte-identical after the change, asserted **literally**
  in `test_the_integer_clock_is_unchanged_by_the_fractional_reading` rather than inferred from the
  diff being additive.
- `decider_lab.py diff --baseline data/decider_lab/baseline.json` runs on this change **alone**
  (Issue #398 landing sequence, PR (a)), so its flips are attributable to the clock and not to the
  work that follows. The Decision Gate was measured GREEN on the unmodified tree at `37f5975`
  (agree 251/340, 0 picks moved), which is the control this comparison needs.
- **Decision Gate, POST-change: PASS, `agree 251/340 -> 251/340`, 0 picks moved.** Recorded here
  because a gate result cited only as a control is half a measurement. Zero movement is the
  EXPECTED outcome and not a null result: the change recovers precision on a term whose residual
  87% is a Structural Zero, so it was never likely to reach a ruled decision. It does mean this PR
  ships no behavioural change on the corpus — which is the honest reading of "prerequisite, not
  fix", and the reason nothing here is offered as evidence that the ranking got better.
