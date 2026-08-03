# ADR-TEMP-256 — The store is an ARCHIVE, so the writer's rules are re-applied as a REPORT, never as a loader

⚠️ **Temp-named, not numbered.** Real number assigned at /open-pr rebase time. Cite the issue.

**Status:** Accepted (agent-grilled 2026-08-02 on Issue #256, batched issue-sequence run); decisions
2 and 4 BUILT, decisions 1 and 3 RULED BUT NOT EXECUTED (they move a gate number — see
`docs/plans/issue-sequence-230-wave3-packet.md`).
**Sits beside [ADR-TEMP-251](temp-issue251-a-gate-reports-what-it-cannot-grade-it-never-stops-grading-it.md)**,
whose ruling this repeats one layer down: that one reports a record that cannot *state* its ruling,
this one reports a record the writer would not have *created*. Both report; neither excludes.
**Builds on [ADR-TEMP-229](temp-issue229-a-decline-is-a-ruling-the-writer-must-accept.md)**, which
made the `decision`-scope **Decline** writable and is why the audit's decline rule is narrow rather
than absolute.
**Amends nothing.** Neither gate verdict function changes; no frame starts or stops gating; both
baselines byte-identical.

**Context issues:** Issue #256 (this ruling), Issue #250 /
[ADR-0090](0090-a-ruling-names-its-record-through-a-resolver.md) (which split this out and is the
same family: *the constructor is not the only way in*), Issue #229, Issue #251,
[ADR-0049](0049-corrections-carry-a-scope-decision-turn-or-match.md) (Scope, the **Anchor**, and the *first divergent
Decision* reading), [ADR-0087](0087-a-corpus-reader-constructs-corrections-and-keys-by-identity.md) (the **Corpus Reader**),
[ADR-0072](0072-mid-build-swaps-are-gated-by-deterministic-instruments.md) (both gates),
[ADR-0088](0088-a-voided-ruling-leaves-the-agree-rate-and-the-gate.md) (the void-and-re-capture
protocol decisions 1 and 3 must go through).

## Context

A `turn`- or `match`-scoped **Correction** is about a whole ply or a whole Episode, but both gates
grade it at its **Anchor** — the single Decision the human happened to be looking at. Nobody had
ruled whether that is right, and one committed record makes the question sharp:
`85709280|1|match|` (`ee3191f7c3d6`) is **`match` scope carrying `correct: [0]`**, a shape
`build_correction` refuses outright. Its own rationale records a hand re-ruling on 2026-07-29, which
is how it got past the writer. `Correction.from_dict` — THE loader — validates nothing, so it loads
silently and grades in both gates.

### Verified on this checkout, not recalled (2026-08-02)

Measured through the **Corpus Reader** (`gates.keyed_corrections`), never by walking raw JSONL: 23
records carry no explicit `scope` key and only default to `decision` inside `Correction.from_dict`,
and every rule discussed here dispatches on scope.

| Claim | Verdict | Evidence |
|---|---|---|
| `85709280|1|match|` (`ee3191f7c3d6`) is `match` scope carrying `correct: [0]` | **TRUE** | the record, via the Corpus Reader |
| it is the ONLY `match`-scope record repo-wide | **TRUE** | 372 = 353 `decision` / 18 `turn` / **1** `match` |
| `build_correction` refuses that shape | **TRUE** | driving the real constructor with it raises `ValueError`; asserted by test, not by reading |
| `Correction.from_dict` performs no validation | **TRUE** | it backfills `id`/`agent`/`scope`/`subject` and calls the dataclass; loading the refused record round-trips silently |
| the turn-scope rule `correct != chosen` is enforced by the constructor | **TRUE** | compared as SETS; **decision 2 rests entirely on this** |
| **it grades as an AGREE** | **TRUE — and the spec said the opposite** | see *Claims verification refuted* |
| no OTHER committed record carries a refused shape | **TRUE** | 0 turn-scope `correct == chosen`, 0 `correct` off the menu, 0 unprovable declines, 0 bad `source`/`scope`/`category`. **Positive controls** for every one of those zeros: the reader returns 372 records and the audit calls 371 of them clean (so it is neither an empty corpus nor a predicate that flags everything); `is_valid_category("not_a_category")` is `False` and the real constructor raises on each shape (so the checks fire when a thing is there) |

## Decision

### 1. A `match`-scope Correction should NOT grade at its Anchor. RULED, **NOT EXECUTED**.

A `match` Correction is a claim about a whole Episode. Its own constructor forbids it from naming a
`correct` option, on the stated grounds that *"no single `select` carries a whole-match verdict."*
Grading it at an Anchor therefore grades a field the schema says must not exist — the verdict is an
artefact of a malformed record, not a reading of a ruling.

There is a second, sharper reason the grill surfaced only by measuring, and it is the one that makes
this a ruling rather than a preference: **the only `match`-scope shape the constructor will produce
is one `satisfies_human` reads as a DECLINE.** `build_correction` stores `list(correct)`, so a legal
match record carries `correct: []` — and `satisfies_human` grades `[]` exactly, as *"take none of
these"*. So a well-formed match Correction, graded at its Anchor, asserts that the agent should have
picked nothing at whatever select the human happened to be looking at. That is not a weaker claim
than the malformed record's; it is a *different, unintended* one. Match scope and Anchor grading do
not compose, in either direction.

**Not executed here** because it removes a frame from grading in both gates, which is a ruling under
ADR-0088's void-and-re-capture protocol, not a refactor — the identical line Issue #251 drew and the
reason Issue #243 left its predicate unwired. → **wave-3 packet**, with the measured consequence.

### 2. A `turn`-scope Correction KEEPS grading at its Anchor. RULED, and this only writes it down.

ADR-0049 makes the Anchor's `correct` assert *"the Anchor is the first divergent Decision"*, and
`build_correction` **enforces** that assertion: it rejects a turn-scope `correct` equal to `chosen`
(compared as sets), precisely so the claim is non-vacuous. A record that named the agent's own pick
would assert nothing; the writer refuses it. That is a coherent, deliberate design.

So turn-scope Anchor grading is not an accident of the gates reaching for whatever field was handy —
it is the schema working as ADR-0049 specified. The issue asked that it *stop looking accidental*;
this paragraph and the test pinning the enforcement rule are the whole change. **No code, gate-neutral.**

The contrast with decision 1 is the load-bearing part: `turn` scope has a rule that makes the Anchor's
`correct` mean something, and `match` scope has a rule that forbids it from existing. The two scopes
were never symmetric, and treating them as one is what left the question open.

### 3. `85709280|1|match|` should be re-ruled — but **NOT to `match` + `correct: []` alone**. RULED, **NOT EXECUTED**.

Of the three options the issue lists, re-scoping to `decision` at frame 51 is the one that invents a
ruling: it would assert the human ruled *that Decision*, and the record's rationale is a whole-match
note. Leaving it alone preserves a shape the schema forbids. So the record is re-ruled to the shape
the constructor would accept — `match` scope, no `correct` — with the intended line ("Play Lillie's
Determination") in the rationale, which is exactly what the constructor's own error message
prescribes and where that record's rationale already carries it.

**With one correction to the issue's framing, found by measuring:** executed *alone*, this makes the
record **worse**, not better. Its select has `minCount 1` — a mandatory MAIN select — and its own
rationale says the 2026-07-29 re-ruling moved `correct` `[] -> [0]` *because* "the empty pick was
degenerate at a minCount-1 Main select". Re-ruling back to `correct: []` restores that exact
degeneracy: `satisfies_human` would grade it as a DECLINE at a select where declining is illegal, so
**no legal pick could ever satisfy it**. A permanently-unsatisfiable disagreement is a worse state
than a false agreement.

**Decision 3 is therefore conditional on decision 1.** Executed together, the `correct: []` is inert
because the frame no longer grades, and the record is simply a well-formed whole-match note. Executed
alone, it converts a false agree into a standing, unfixable disagree. The packet says so.

**Not executed** — it changes a committed record and two gate numbers, so it needs ADR-0088's protocol
and a human. → **wave-3 packet**.

### 4. `Correction.from_dict` must NOT validate. A non-fatal **shape audit** instead. BUILT.

The asymmetry is **deliberate and correct**. `from_dict` is what the **Corpus Reader** loads through
(ADR-0087), so validating there would reject committed records at *read* time and take **both** gates
down over a record that has been sitting green for weeks. *Load anything committed, refuse to create
new bad shapes* is the right contract for a store that is also an **archive**. A gate whose loader can
refuse the corpus is a gate that cannot report on the corpus.

But *unvalidated* must not mean *unobserved* — and it was. Nothing re-applied the writer's rules to
what is already on disk, which is how the one forbidden record got in and stayed. So:

* `gates.shape_the_constructor_would_refuse(correction)` — per record, returns `REFUSED_SHAPES` slugs.
* `gates.refused_shapes(store)` — the corpus walk, `[{key, id, scope, violations}, ...]`.
* `decider_lab.print_refused_shape_readout` — a second reporting-only section, printed by both
  subcommands, silent at zero.

**It reports only.** Neither verdict function changes, and a test asserts behaviourally that a refused
record still gates — the exclusion that would quietly appear later is what that test exists to stop.

#### Which of the constructor's rules are re-applied, and which are not

Re-applied: `source`, `scope`, and the four `correct`-shape rules (`match` naming a `correct`; a
`correct` off the Anchor's menu; a `turn`-scope `correct` equal to `chosen`; an empty `correct` at
`decision` scope without an `obs` proving `minCount == 0`). Every one is a property of the record
*itself*, judged against a vocabulary fixed in `correction.py` that does not grow.

**Deliberately NOT re-applied: `is_valid_category`.** Its vocabulary lives in `categories.py`, is
documented as *extensible*, and grows by process. Refusing a committed record because a category was
later renamed would report **a vocabulary edit as a corpus defect** — a different question, and one
that needs a ruling rather than a predicate. Measured either way: all 372 records pass `source`,
`scope` **and** `category` today, so the line costs nothing now and is drawn for the future. A test
pins the omission, with a positive control proving the constructor really does refuse a stale
category — so it reads as a decision rather than as a rule nobody noticed.

Two smaller faithfulness choices, both stated so they are not "fixed" later by accident:

* **Every applicable rule is reported**, where the constructor stops at its first raise. *Would refuse*
  is true if any fires, so reporting all is strictly more informative and cannot be wrong about one.
  The exception is an unrecognised `scope`, which returns alone: every rule below it dispatches on
  scope, so classifying further would be guessing.
* **The range check is the constructor's, verbatim** — including that `bool` is an `int` in Python, so
  `correct: [True]` would be admitted as index 1. The audit answers *what would the writer refuse*,
  not *what should it*; widening here would make the two disagree about a record.

## Claims verification refuted

The spec was **self-filed** — written by the same session that then built it — so it cannot catch its
author's own misreading. Its single most prominent claim, presented as a *correction to the issue*,
is itself false, and it inverts the consequence of decision 1.

### The record grades as an **AGREE**. The issue body was right; the spec's "correction" was wrong.

The spec's verification table says:

> *"it currently grades as agree (`chosen [0]` vs `correct [0]`)"* — **FALSE — stale**. measured
> `chosen=[2]`, `correct=[0]` → `satisfies_human` returns **False**. It grades as a **DISAGREE**.

and then draws the conclusion that *"ungrading this record **raises** the agree rate rather than
lowering it."*

**Both are wrong, from one confusion.** A Correction has two different `chosen` values and they are
not interchangeable:

* `Correction.chosen` — what the agent did **in the recorded game**. For this record, `[2]`.
* the capture row's `chosen` — what a **fresh shipped Pilot picks on replay**,
  `pilot.explain(rec.obs).chosen`, which is what `build_report` stores and the **only** one
  `satisfies_human` is ever handed by the gate. For this record, `[0]`.

The Decision Gate grades the second against `correct`. `satisfies_human([0], [0])` is **True**, the
committed baseline row reads `chosen: [0]` / `correct: [0]`, and the frame sits in the gradeable
denominator as an **AGREE** — exactly as the issue body stated. The spec measured the record's
historical pick and reported it as the gate's verdict.

The consequence inverts with it: ungrading the frame **lowers** the agree count by one
(250/347 → 249/346 on this build), it does not raise it. So does decision 3's re-ruling
(250/347 → 249/347), and so does the Discrimination Gate's `leaf_correct` (180/247 → 179/246, from
the committed capture, where the row reads `correct_is_top: True`). Every measured consequence in the
packet is the opposite sign from the one the spec asserted.

This matters beyond arithmetic. A ruling made on the belief that the record grades as a *disagree*
would read decision 1 as *removing a false failure* — free, obviously correct. It is the reverse: it
removes a **false success**, and pays one point of agree rate to do it. That is still the right
ruling, for decision 1's own reasons, but it is a ruling with a cost and the human signing it off must
see the cost. Both numbers are now asserted by test against the committed baseline, with the two
`chosen` values named side by side, so the confusion cannot be re-made silently.

### The `85709280` re-ruling that created the shape is already on the record

`ruling_moves`' own docstring records it: *"`85709280` went `[] -> [0]` in `b6d7483` (ADR-0081
Amendment D) and moved the agree rate 230 -> 231 with no decision changed."* That is this record, and
it is the direct measurement that the move was worth **+1 agree** — so reverting it is **−1**. The
evidence refuting the spec was already committed in the module the spec was reading.

## Consequences

**One committed record is now visibly owed a re-ruling**, on every Decision Gate run, on `main` and
locally — named, with its violated rule spelled out and with the fact that it is *grading anyway*
stated rather than implied. The store held a shape its own writer forbids for weeks and no report
mentioned it.

**A second bad shape is now loud.** The census test asserts exactly one, over the whole committed
corpus, and it goes red the moment a second appears — the property the store lacked entirely. It also
goes red when this one is repaired, which is precisely the moment a human is looking.

**The audit is a differential test of the constructor, not a paraphrase of it.** Each caught shape is
driven through the *real* `build_correction`, which must raise, and through the audit, which must name
it — plus the reverse direction, so an audit gone paranoid fails too. A re-implementation of six rules
that nothing held to the original is how the two would silently diverge, and the divergence would
appear as *the audit going quiet*, which is indistinguishable from a clean corpus.

**`decider_lab` now has two reporting-only sections and no shared helper.** Deliberate: they answer
different questions about different populations (`unstatable` is report-scoped and asks *"can this
record state its ruling?"*; `refused shape` is corpus-wide and asks *"could the writer have written
this record at all?"*). Two eleven-line printers beat one parameterised printer that has to explain
which mode it is in. If a third arrives, that is when to extract one. Both are pure
`(data, report) -> None`, resolved once in `main`, and both index rows through `gates.rows_by_key` —
*the one place a capture is turned into a lookup*.

**The corpus walk lives in `gates.py`, not `decider_lab.py`** — unlike `unstatable_frames`. That one
narrows to the replayable population `build_report` scores, so *"is it still gradeable?"* is
answerable against that report's own rows. A malformed record that cannot be replayed is still
malformed, so this walk is corpus-wide and is not narrowed by `--agent` either: a record hidden by a
filter is the one least likely to be repaired.

**Decisions 1 and 3 are owed to the developer, together.** The packet carries the exact one-line
change and the measured gate consequence for each, and states that 3 without 1 makes the record worse.

## Alternatives rejected

* **Validate in `Correction.from_dict`** — decision 4. It would take both gates down at *load* on a
  record that has been green for weeks, and the store is an archive as well as a write target.
* **Validate in `from_dict` but only warn** — a loader that warns is a loader nobody reads; the corpus
  is walked by two gates and several scripts, so the warning lands in whatever stream happens to be
  open. A named report in the gate readout reaches the one person who can act.
* **Re-apply `is_valid_category` too** — decision 4. It reports a vocabulary edit as a corpus defect.
* **Execute decisions 1 and 3 here** — both move a gate number, which is a developer act under
  ADR-0088. Executing them inside a reporting-only issue is exactly how a baseline stops being a
  ruling record.
* **Execute decision 3 alone** ("just fix the malformed record") — the obvious move, and measurably
  the worst available: at a `minCount 1` select, `correct: []` is a decline no legal pick can satisfy.
* **Record the finding on each capture row** (beside `voided` / `equiv`) instead of a second corpus
  pass — it would change the shape of a **ruling record**, which a reporting-only issue is not
  entitled to do. Same call ADR-TEMP-251 made, same reason.
* **Carry the spec's "it grades as a DISAGREE" correction into the ADR** — it is false, and it would
  have put the wrong sign on every number the developer signs off.
