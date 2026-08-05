# ADR-TEMP-398 - An argmax probe reports nothing without a sham leg as its null

⚠️ **Temp-named, not numbered.** Real number assigned at /open-pr rebase time. Cite the issue.

**Status:** Accepted (grill of Issue #398, 2026-08-05). Methodology; applies to every probe that
reports "how often does the top pick move".

## Context

Issue #398 was filed on a measurement: adding `state_value`'s denial credit to
`pilot._opponent_target_rows` moves the top-ranked opponent target on **46 of 314** rankable corpus
frames (later corrected to **69 of 241** once scoped to the bench-only seam `gust_target_slot`
actually reads). The probe carried a **null control** — arm A compared against itself, reporting 0
moves — and that control passed.

The null control was insufficient, and the number was close to meaningless.

Re-run with **sham legs** — deliberately meaningless terms injected in the same magnitude band as
the real credit — over the same 241 bench-rankable frames:

| leg | moves the argmax |
|---|---|
| real denial credit | 69/241 (28.6%) |
| sham `cid % 7` | 64/241 (26.6%) |
| sham `hp % 70` | 59/241 (24.5%) |
| sham position index | 147/241 (61.0%) |

The real credit separates from a meaningless number of the same size by **five frames out of 241**.
The headline was measuring *"a continuous term breaks flat ties"*, not *"this term discriminates
correctly"* — and the underlying reason (73.2% of equal-prize groups are perfectly tied; see
ADR-TEMP-398-CLOCK) guarantees that **any** term in that band scores similarly.

The A-vs-A null could not have caught this. It proves the comparison is *stable* — that the tie
convention does not itself manufacture movement. It says nothing about whether the movement means
anything, because it introduces no term at all. The two controls answer different questions and
neither substitutes for the other.

Cost of the omission: a false headline reached an issue body, a committed probe docstring, and a
commit message, and was on its way into a spec. It was caught by a reviewer challenging the
*premise* rather than by any instrument.

## Decision

**A probe that reports argmax movement MUST report, in the same table, the movement produced by at
least one sham leg** — a term with no causal claim, scaled into the same magnitude band as the term
under test.

A movement number published without its sham baseline is not evidence and must not be cited as
such.

## Policy

- **Two controls, not one.** A **null control** (the arm against itself, expect 0) proves the
  comparison is stable. A **sham control** (a meaningless term in the same band) proves the movement
  is attributable. Both are required; they are not interchangeable.
- **Prefer more than one sham.** `cid % 7` and `hp % 70` are card-derived but causally empty;
  a position index is the degenerate case and is worth printing because a term that cannot beat
  *list order* is not ordering anything.
- **Band-match the sham to the term under test.** A sham an order of magnitude smaller trivially
  loses and proves nothing. Scale it to the real leg's measured range, which the probe already knows.
- **Report the tie population.** A movement percentage is uninterpretable without knowing how much
  of the candidate set was tied before the term was added — that is what sets the floor any leg
  clears for free.
- **Movement is still not merit.** Beating the sham shows a term *discriminates*; it does not show
  it discriminates *correctly*. The corpus rules chosen options, not internal orderings, so the
  decision test remains `decider_lab.py diff` against a pre-registered prediction.
- **A movement number is the WRONG instrument for a term whose correct behaviour is to leave most
  orderings alone** (amendment, 2026-08-05, from this policy's first application). The Fractional
  Survival Clock moves the bench argmax on 8/241 against `sham cid%7`'s 64/241 — it *loses* to a
  meaningless leg, and that is the term behaving correctly: the shams break ties arbitrarily, while
  the clock declines to break the ones that are a **Structural Zero**. Under-movement therefore
  falsifies nothing on its own. A leg that MATCHES its sham has discriminated nothing; a leg well
  BELOW its sham needs a different question asked of it, not a verdict read off this table. Say
  which case a number is before reading it as a result.

## Verification

- `tools/train/probes/opponent_target_credit_sweep.py` prints the null arm, the sham arms and the
  tie population on every run; its closing note states plainly that movement is not merit.
- A probe added under this policy without a sham arm should be treated as unreviewed, whatever its
  numbers say.
