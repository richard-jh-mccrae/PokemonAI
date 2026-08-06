# ADR-0128: The selection tie-break needs a FLOAT-NOISE FLOOR — one ULP was deciding corpus frames

**Status.** Accepted (Issue #400 Phase 2 flip review, 2026-08-06). BUILT.

**Context issue.** Issue #400 (POC-T4). Found while investigating a single flip the developer ruled a
regression; it turned out not to be a valuation defect at all.

## Context

Issue #263 § *Beam-quality package* item 1 rules that the composer's final ordering **"must NEVER
fall through to raw option/sequence generation order"**, and `composer.selection_key` implements it:
score first, then the Worth of the touched card, then a stable card-id sort, then the menu index. The
rule is on record because it fixed three CRITICAL production bugs (ADR-0062:29's oldest-attached
fall-through; `mega_starmie` ep82867148 f48/f87; `mega_lucario` ep83661652 f33/f40/f44 — *"benched
whichever Basic sat lowest in the menu"*).

**The score leg was compared EXACTLY, and that reopened the same class through arithmetic.**

Two orderings of one commutative block reach the *same end board*, so their scores are one sum added
in two different orders — and floating-point addition is not associative. `state_value._terms` says
so outright in its own docstring, as the reason its term-iteration order is a contract:
*"Floating-point addition is not associative, so a reordering would move the last bits of the sum."*
That warning was about the terms inside one leaf; nothing carried it forward to the composer, where
whole candidate SCORES are summed across steps in whatever order the beam built them.

Measured on `82226116|0|decision|70` (`mega_starmie`), the frame that exposed it:

```
retreat-then-evolve   score = 0.9052836100260416   steps [16, 11]
evolve-then-retreat   score = 0.9052836100260415   steps [11, 16]   <-- the developer's ruled step
difference            1.1102230246251565e-16                        (one ULP)
```

`selection_key`'s `-score` leg separated on that last bit, so the Worth leg **never ran** — and the
Worth leg is exactly the one that knows the answer: the evolve's first step is a Mega Starmie ex
(`role_worth` **30.0**) against the retreat's bare `{"type": 12}` (**0.0**). The composer had already
FOUND the ruled line; it simply reported the same two actions in the other order, and the corpus
scored that a miss.

This is not a near-miss to be widened away. It is the identical fall-through ADR-0062:29 records,
reached through the last bit of a sum instead of through generation order.

## Decision

**Compare the score leg at a FLOAT-NOISE FLOOR of 12 decimal places** — `composer._SCORE_PLACES` —
so that two candidates the arithmetic cannot honestly separate fall through to the Worth leg the rule
was written for.

```python
return (bool(candidate.coverage_gap), -round(candidate.score, _SCORE_PLACES), -worth, card_id, ...)
```

**Twelve places is six orders of magnitude above the noise and six below anything real.** Observed
1-ply deltas on this corpus run 1e-5 to 1e-3 and the epsilon admission band is 5e-3, so the rounding
provably cannot merge two candidates the leaf actually separates. Both directions are asserted by
test: one ULP must NOT decide, and a genuine 1e-5 margin must STILL decide before Worth is consulted.

**`EPSILON` is deliberately NOT reused, and the distinction is Issue #263's own.** `EPSILON` (0.005,
`family_diag.DECIDER_FLOOR`) is the corpus-calibrated band for not LOSING a near-tie during *search*;
this is a noise floor at *selection*. Issue #263 § *Beam-quality package* is explicit that the two
mechanisms must not be conflated, and quantising selection onto the admission band would silently
hand every sub-epsilon decision to the Worth leg — a different ruling, which nobody has made.

**This is not a fix to the commutative-block machinery.** `commutative_blocks` reports `((3, 11),)`
here: option 16 (the retreat) is NOT in a block with the evolve, so both orderings are legitimately
explored as separate branches. That is the fail-closed commutativity contract working as designed —
an unproven pair gets both orderings. The defect was only ever in how the two were *chosen between*.

## Consequences

- `82226116|0|decision|70` now agrees with the developer's ruling: the composer commits option 11,
  the ruled evolve, instead of option 16.
- **Corpus agreement 88 → 90 of 270** MAIN ruled frames (against the developer's 2026-08-06
  re-rulings), on top of ADR-0127. No frame regresses.

  > ⚠️ **These levels moved twice on the day, and the round trip is the point.** They were first
  > reported as 88 → 90, then corrected to **87 → 89**, then landed back on 88 → 90. The middle value
  > was not an error and the outer two are not a retraction:
  >
  > 1. `composer_lab.fixture_rulings` flattened the fixture walk with `out[key] = ...`, so on
  >    `85164605|1|decision|41` — the one frame two committed fixtures ruled DIFFERENTLY — the grading
  >    claim was whichever FILENAME sorted last (`[4]`, not the Correction's `[3]`).
  > 2. Fixing that dropped the conflicted frame from the ruled population, and the levels fell to
  >    87 → 89: the lab correctly fell back to the record's `[3]`, which the composer does not pick.
  > 3. The developer then RULED the frame to `[4]` (the free direct-evolve), both fixtures were
  >    reconciled, and the frame re-entered the population at the claim that is now authoritative.
  >
  > **So the broken mechanism happened to emit the answer the developer later ruled, and it was still
  > broken.** Resolving a ruling by filename order is unsound whatever it returns; that it was
  > accidentally right on the only frame it fired on is the reason it had survived unnoticed. The
  > **delta is +2 throughout** — that frame grades identically on both sides of the comparison — which
  > is why the tie-break's own result never depended on any of this. Guarded now by
  > `tests/test_fixture_ruling_conflicts.py`.
- Cost is nil — one `round()` per candidate at selection time, off the leaf path entirely.
- Both ADR-0072 gates unmoved: `selection_key` lives in the composer, which is still DARK.

**The generalisable finding, because it is not really about this frame.** A tie-break whose first leg
is a float is a tie-break that can be pre-empted by arithmetic noise before its principled legs run.
Any future ordering key in this codebase that leads with a computed float owes the same floor — and
the smell to look for is a docstring like `state_value._terms`' that already knows reordering moves
the last bits, in a module that then compares those bits exactly somewhere else.

## Prior art

ADR-0062:29 and the `mega_lucario` f33/f40/f44 fall-throughs are the same bug class through a
different door; Issue #263 § *Beam-quality package* item 1 is the rule both violate.
`state_value._terms` already carried the non-associativity fact and pinned its own iteration order
for exactly this reason — it simply stopped at the leaf boundary. ADR-0103 (class identity, not menu
position) is the sibling ruling about what a tie-break may legitimately fall through TO.
