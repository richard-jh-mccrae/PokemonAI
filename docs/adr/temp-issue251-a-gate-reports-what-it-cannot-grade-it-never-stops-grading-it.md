# ADR-TEMP-251 — A gate REPORTS what it cannot grade properly; it never quietly stops grading it

⚠️ **Temp-named, not numbered.** Real number assigned at /open-pr rebase time. Cite the issue.

**Status:** Accepted (agent-grilled 2026-08-02 on Issue #251, batched issue-sequence run); BUILT.
**Closes the question [ADR-0089](0089-a-corpus-reading-probe-is-a-gate-a-ruling-or-a-routed-diagnostic.md)
left open** — it lifted `records_a_decline_it_cannot_state` to `gates.py` UNWIRED and named
Issue #251 as the owner of *"which frames stop gating"*. The answer is **none of them**.
**Builds on [ADR-TEMP-229](temp-issue229-a-decline-is-a-ruling-the-writer-must-accept.md)**, which
made the record repairable and is the reason this ruling can go the way it does.
**Amends nothing.** Neither gate verdict function changes; no frame starts or stops gating.

**Context issues:** Issue #251 (this ruling), Issue #229 (made `correct: []` writable at `decision`
scope, end to end), Issue #197 / [ADR-0086](0086-the-deploy-marginal-prices-a-bench-slot-and-what-fills-it.md)
(where the shape was first measured and excluded, inside a sweep now deleted), Issue #243 / ADR-0089
(the unwired lift), [ADR-0072](0072-mid-build-swaps-are-gated-by-deterministic-instruments.md)
(both gates),
[ADR-0088](0088-a-voided-ruling-leaves-the-agree-rate-and-the-gate.md) (the other way a frame stops
grading, and the contrast that makes this one legible).

## Context

An **optional** engine select (`minCount == 0`) puts *"take none"* on the table. Before Issue #229 a
`decision`-scope Correction could not say it: `correct` had to be non-empty and index a legal option,
so a human ruling *"you should have declined"* could only name the option the agent already took. The
record then reads `chosen == correct` — *"the pick was right"* — which is the opposite of the ruling.
`gates.records_a_decline_it_cannot_state` detects exactly that shape.

The predicate has had **no caller at all** since ADR-0089 deleted `deploy_decider_sweep`, where it
was a per-frame verdict that removed the frame from grading. Issue #251 asked whether the **Decision
Gate** should adopt that exclusion. Two states were on the table and a third was not noticed until
building: unwired-and-unreported is not neutral, it is the weakest of the three.

### Verified on this checkout, not recalled (2026-08-02)

Measured through the Corpus Reader (`gates.keyed_corrections`), never by walking raw JSONL — 23
records carry no explicit `scope` and only default to `decision` inside `Correction.from_dict`, and
this predicate tests `scope` first, so a raw walk would under-count.

| Claim | Verdict | Evidence |
|---|---|---|
| the predicate exists and is UNWIRED | **TRUE** | `gates.py`; `decider_lab.py` imported 19 names from `train.gates` and this was not among them. Positive control: `satisfies_human` — another `train.gates` symbol — *is* imported and used there, so the empty grep is a real negative rather than a broken instrument |
| it fires on exactly two frames | **TRUE** | `85785609\|0\|decision\|4` (dragapult_ex) and `83661652\|0\|decision\|3` (mega_lucario), out of 372 records |
| the `turn`-scope guard prevents swallowing a live ruling | **TRUE** | `86088989\|0\|turn\|0` carries `correct: []` and is a real decline; the bare `chosen == correct` test would take it |
| the **Discrimination Gate** shares the exposure | **NO** | `is_leaf_frame` is `False` on both exposed frames — neither carries a `turn_plan` and both are `context 2`. Positive control: the same predicate returns `True` on **278** of the same records. See decision 3 for why the spec's *reason* for this is wrong even though its answer is right |
| *"the tally reads `unstatable 0`"* | **FALSE — it is 2.** | See *Claims verification refuted*, below |
| *"`is_leaf_frame` requires `select.context == 0`"* / *"a repaired decline is not a leaf frame either"* | **FALSE as stated** | `is_leaf_frame` is a DISJUNCTION — see decision 3 |

## Decision

### 1. `records_a_decline_it_cannot_state` stays OUT of both gate verdicts.

`decision_gate_verdict` and `discrimination_gate_verdict` are untouched. **This build is
verdict-neutral: no frame starts or stops gating, both baselines byte-identical, both diffs clean.**

Three reasons, in the order they bind:

1. **An exclusion makes a `main` watchdog permanently quieter.** A gate that under-reports cannot be
   told apart from one with nothing to report — the property that let four `*_decider_sweep.py`
   report PASS for weeks in a state where PASS could not be distinguished from FAIL (ADR-0089). And
   the exclusion outlives its cause: it would keep these frames ungraded *after* the record is
   repaired and they become perfectly gradeable.
2. **Issue #229 made the record repairable, end to end.** `correct: []` is now writable at `decision`
   scope **through the tagging pane, by a human** — Issue #229 found and relaxed a *second* refusal in
   `blunder/shell.py`, gated on the same `select_min_count` as the validator. That is what turns
   "repairable at source" from a Python-caller technicality into an act the developer can actually
   perform. A repaired record is graded *exactly* by `satisfies_human`; an excluded frame is graded
   not at all. The first is strictly better.
3. **Nothing forces the worse fix now.** Neither frame's pick has moved off the baseline, so neither
   produces a gate verdict today. There is no live failure buying the exclusion anything.

### 2. Unwired *and unreported* is the state this fixes. The readout NAMES the exposure.

`decider_lab` gains `unstatable_frames` (the predicate's one caller, a REPORTING one) and
`print_unstatable_readout`, printed by both `capture` and `diff`. Always visible when it fires,
silent at zero — the shape `print_gate_report`'s `HELD OUT` and `VOIDED` sections already have, and
for the same reason: **a frame a gate cannot grade properly must not become scenery.**

The line says what to DO, not merely how many:

```
  unstatable (2) — reported, NEVER excluded (Issue #251):
    83661652|0|decision|3  records a decline it cannot state (optional select, chosen == correct); still GRADEABLE, still in the denominator
      agent picks [] against a recorded correct [0]
      -> re-rule it to `correct: []` (writable at `decision` scope since Issue #229) rather than excluding it
```

*"Still GRADEABLE"* is **computed**, not asserted — from `gradeable_rows`, the same one definition
`build_report`'s totals and the per-context breakdown now use. A readout with its own private idea of
the denominator could say "still gradeable" about a frame something else had quietly dropped, which
is the failure this section exists to make impossible. (**Gradeable**, not *graded*: `CONTEXT.md`
reserves the word, because the two labs once used different ones for the same concept and drifted
apart inside a release.)

### 3. No Discrimination Gate change — by measurement, and the spec's reason for it was wrong.

The answer is right and the argument was not. Both the issue's table and this build's first draft
said *"`is_leaf_frame` requires `select.context == 0`"* and *"it additionally requires a truthy
`correct`, so a repaired decline is not a leaf frame either."* **`is_leaf_frame` is a DISJUNCTION.**
A record carrying a `turn_plan` is a leaf frame on its own — any context, empty `correct` and all —
and `86088989|0|turn|0`, the very record the spec's own table cites as a real turn-scope decline, is
exactly that shape: context 2, `correct: []`, **and a leaf frame**. Only the second arm requires
`correct` truthy AND context 0.

The conclusion survives on a narrower fact: **neither exposed frame carries a `turn_plan`, and both
are context 2**, so both fail both arms — today, and after a repair to `correct: []`, which adds no
`turn_plan`. So the Discrimination Gate never had these two and ADR-0072 decision 4's *one ruling
holds a frame out of both gates* is satisfied **vacuously**. Asserted by test — including the
disjunction itself, with the positive control — so the next reader neither re-derives it nor
re-inherits the false version.

### 4. Neither record is re-ruled here.

Re-ruling `85785609|0|decision|4` or `83661652|0|decision|3` to `correct: []` is a **human** act that
moves a gate number, under ADR-0088's protocol. This issue makes it *advisable* and — via Issue #229
— *possible*. It does not perform it. That is also why the readout is imperative: the fix belongs to
a person, and until now nothing told them it was owed.

## Claims verification refuted

The spec was **self-filed** — written by the same session that then built it — so it cannot catch its
author's own misreading. Two of its claims did not survive verification. Neither changes the ruling;
both were reaching the code and the docs as fact.

### The tally is 2, not 0

The spec stated the exposure was DORMANT and that **"the tally reads `unstatable 0`"**, concluding
the new section would print nothing today. Both the spec and the build brief carried it.

**It is 2, and the section prints.** The `0` was inherited from ADR-0086's *"dormant since decision
9"*, which is a claim about a **different instrument and a different population**: `unstatable` was a
per-frame verdict inside `deploy_decider_sweep`, over that sweep's deploy-only frames, where it read
`unstatable 1`. Across the whole committed corpus the predicate fires on two records, and it always
did — the number was never re-measured after the sweep was deleted.

What *is* dormant is the **gate verdict**, not the exposure: both frames sit in the baseline with
`chosen: []` against a recorded `correct: [0]`, so they are standing DISAGREEMENTS that cost the
agree rate and produce no *move*, hence no REGRESSION. That distinction also corrects the spec's
statement of the hazard. In the baselined gate the available false verdict is a false **FIX**, not a
false REGRESSION: if the agent ever starts taking the option — the play the human ruled *against* —
it would move onto the record's `correct` and the gate would applaud. A false REGRESSION was the
hazard in the *two-arm sweep* world, which ADR-0072 replaced.

This strengthens reason 1. The exposure is live enough to print, and that it printed `2` on the first
run is the section doing its job.

### `is_leaf_frame` is a disjunction, so D4's stated reason was false

Covered in full at decision 3. The spec's row — *"`is_leaf_frame` requires `select.context == 0`"*
and *"the Leaf Lab additionally requires `bool(correct)`, so a repaired decline is not a leaf frame
either"* — reads the second arm of a two-arm predicate as the whole of it. A `turn_plan` record is a
leaf frame at any context with an empty `correct`, and the corpus holds ten of them. The spec's own
citation `86088989|0|turn|0` is one. Caught by the Spec axis of `/code-review`, after this build had
already copied the false reasoning into `gates.py` and this ADR; both are corrected.

## Consequences

**Two frames are now visibly owed a re-ruling.** Every Decision Gate run, on `main` and locally,
names them and says what to do. Neither is excluded, so the agree rate keeps paying for them until a
human repairs the records — which is the correct pressure, applied to the correct party.

**The predicate's docstring no longer describes a resolved question as open.** It said wiring "is
owned by Issue #251"; leaving that standing is how the next session re-opens a decided question. It
now carries the ruling, the three reasons, the corrected tally, and the corrected leaf-frame
measurement. Its closing note on fail direction is re-justified rather than deleted: it was chosen
when a spurious hit removed a frame from grading, and under the reporting role a spurious hit costs
one advisory line and no verdict at all — so the same lenient read is still right, for a new reason.

**`gradeable_rows` is one definition with three readers.** Extracted from `build_report`, which had
it inline and `_print_summary` had it copied. Behaviour is identical (`build_report` sets the row's
`voided` flag iff the key is in the voided set, so the flag test and the set test agree); the point
is that the new readout's *"still gradeable"* claim cannot drift from what the gate actually counts.

**The readout is a pattern Issue #256 can reuse.** It is a pure `(data, report) -> None` printer,
resolved in `main` and called from both subcommands — the same shape as `print_ruling_readout`. A
second reporting-only section (that issue's corpus-shape audit) slots in beside it without a shared
helper being owed; if a third arrives, that is when to extract one. It indexes rows through
`gates.rows_by_key`, which that module documents as *the one place a capture is turned into a
lookup*, so #256 should too.

**The capture artifact does not change.** The exposure is computed in a second corpus pass rather
than recorded on each row the way `voided` and `equiv` are. Row fields are the right home for
something a reviewer must be able to read back off the committed capture — but adding one changes
the shape of a **ruling record**, and a reporting-only, verdict-neutral issue does not get to move
the artifact. The cost is one `load_corrections` against 372 Pilot replays.

## Alternatives rejected

* **Wire the exclusion into `decision_gate_verdict`** — decision 1. Permanently quieter watchdog, and
  the exclusion outlives the record shape that justified it.
* **Wire it, but only until the records are repaired** — nothing would ever remove it. An exclusion
  with no expiry mechanism is a permanent one with a comment attached.
* **Report nothing and leave the predicate unwired** — the status quo, and the weakest state: the
  gap is real, undetectable from any report, and rediscovered from scratch each time.
* **Re-rule the two records here** — decision 4. A human ruling that moves a gate number.
* **Record the exposure on each capture row** (beside `voided` / `equiv`) instead of a second corpus
  pass — see *Consequences*. Cheaper, and it would put the fact in the artifact; but it changes the
  shape of a ruling record, which this issue is not entitled to do.
* **Add a symmetric Discrimination Gate section** — decision 3. It would report an empty set forever,
  because the gate has never held either frame.
* **Define `unstatable` narrowly enough to read 0 today**, matching the spec's prediction — engineering
  a number to fit a premise verification had already refuted.
