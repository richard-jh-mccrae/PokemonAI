# ADR-0111 — A DECLINE is a ruling, and the writer must accept the shape the reader already grades

**Status:** Accepted (agent-grilled 2026-08-02 on Issue #229, batched issue-sequence run); BUILT.
**Amends [ADR-0049](0049-corrections-carry-a-scope-decision-turn-or-match.md)** — the Scope contract
whose `decision` row read *"`correct` mandatory"*. That row now carries one exception.
**Leaves [ADR-0015](0015-correction-schema.md) untouched**: a `correct` that names options still
indexes the Anchor, and every one of the 362 records that name one is unchanged.
Does **not** supersede anything, and does **not** re-rule any record.

**Context issues:** Issue #229 (this build), Issue #251 (wiring
`records_a_decline_it_cannot_state` — unblocked by this, not done by it), Issue #256
(`Correction.from_dict` validation), Issue #197 / [ADR-0086](0086-the-deploy-marginal-prices-a-bench-slot-and-what-fills-it.md)
(where the unstatable shape was first measured), Issue #243 /
[ADR-0089](0089-a-corpus-reading-probe-is-a-gate-a-ruling-or-a-routed-diagnostic.md) (which lifted the
predicate to `gates.py` and left it unwired).

## Context

An **optional** engine select (`minCount == 0`) puts "take none" on the table as a legal answer. A
human watching the agent take one of those options may want to rule exactly that: *taking any of
these was wrong; the right play was to decline.*

The record could not say it. `build_correction` required a non-empty `correct` at `decision` scope,
so the only way to file a ruling on such a frame was to name the option the agent already took —
producing `chosen == correct`, which reads as *"the pick was right"* and is the opposite of the
intended ruling. `records_a_decline_it_cannot_state` exists precisely to detect that degenerate
shape, and `ep83661652` f3 is the case it was written from: **a record whose rationale says the
opposite of its fields.**

### Verified on this checkout, not recalled (2026-08-02)

Measured through the Corpus Reader (`gates.keyed_corrections`), never by walking raw JSONL — 23
records carry no explicit `scope` key and only default to `decision` inside `Correction.from_dict`,
so a raw walk mis-scopes them and under-counts.

| Claim | Verdict | Evidence |
|---|---|---|
| `build_correction` refused `correct: []` at `decision` scope | **TRUE** | `correction.py`, the `elif correct or scope == "decision"` branch |
| every `correct: []` record in the corpus is `turn` scope | **TRUE** | 10 of 10; corpus is 372 = 353 decision / 18 turn / 1 match |
| **three** records sit in the degenerate shape | **FALSE — two.** | `85785609\|0\|decision\|4` and `83661652\|0\|decision\|3`. The third, `86088989\|0\|turn\|0`, is a *turn*-scope `correct: []` — an already-legitimate decline, not a degenerate record. The issue body's table said three; it is corrected here because that is exactly the number a later reader would take on trust. |
| the exposure is confined to optional selects | **TRUE** | both are `minCount == 0`, one option, context 2 |
| every optional select is at risk | **FALSE** | 28 decision-scope `minCount == 0` records exist; **26** name a `correct` that differs from `chosen` and state a real preference |
| only `build_correction` refused the shape | **FALSE — there were two refusals.** | The tagging pane (`shell.py`) rejected an empty `correct` at decision scope client-side, unconditionally. See *Consequences*. |

Positive control for the census: the same reader finds **362** records that *do* name a `correct`.
Without it, an empty corpus or a broken reader would satisfy every "we found none" assertion above at
once.

## Decision

### 1. Admit `correct: []` at `decision` scope. Do NOT add a `declines: true` field.

The issue framed this as overloading a list "whose emptiness already means something at `turn`
scope". Inspection refutes the framing. `gates.satisfies_human` **already** reads an empty `correct`
as a recorded DECLINE — matched exactly, never by subset — and it takes no `scope` argument at all,
so it has always done this at **every** scope:

```python
if not correct:                       # a recorded DECLINE — exact, never subset
    return not chosen
```

Its docstring names the case and explains why subset would be catastrophic there (the empty set is a
subset of everything, so a subset reading would make every frame vacuously agree). **The reader
already spoke this language; only the writer refused it.** `decision` scope was the outlier, not the
innovation.

A second encoding would therefore be strictly worse: every consumer would have to handle both, and
`declines: true` alongside `correct: [0]` is a contradiction no type would catch.

### 2. The relaxation is gated on `minCount == 0`.

At a **mandatory** select "take none" is not a legal answer, so `correct: []` there is a malformed
record and keeps raising. Only `minCount == 0` carries the encoding gap — the same narrowness
`records_a_decline_it_cannot_state` was built with, for the same reason.

### 3. Where `minCount` cannot be established, REJECT (fail closed).

`Decision` carries no `minCount` field and `snapshot()` omits it, so the only route to it is
`obs["select"]["minCount"]` — and `obs` is `None`-able. Where it cannot be read, the old behaviour
stands. This makes the change a **strict** relaxation: a decline is admitted only where the optional
select is *proved*, never where it is assumed. An unverifiable decline is indistinguishable from a
record that simply failed to state one, which is the degenerate shape this issue exists to stop.

`select_min_count` is deliberately **not** shared with `records_a_decline_it_cannot_state`, which
reads the same field for the opposite job and needs the opposite fail direction: that predicate only
ever *removes* a frame from grading, so unknown-means-optional is its safe read, while admitting a
record is a write and must fail closed. One extraction, two deliberate policies.

### 4. The validated `obs` is the stored `obs`.

`build_correction` accepts an `obs=` override that wins over the Anchor's own. Resolving it once,
before validation, is load-bearing: validating against `decision.obs` while storing the override
would admit a record on evidence the record does not carry.

### 5. The Leaf Lab needs no change — assert the behaviour instead.

*What does the lab do with a decline?* Traced: `is_leaf_frame` requires a truthy `correct` or a
`turn_plan`, so a decision-scope decline is not a leaf frame; and were it scored anyway,
`evaluate_leaf_on_correction` finds no `correct_vals` and returns `unscorable: True`, which
`gates._scorable` filters out of the diff. **A decline has no rank, and the code already declines to
invent one.** That is correct, and it is now asserted by test so admitting the shape cannot silently
change what gets scored.

### 6. "Take fewer than offered" is NOT a gap. Closed.

`correct: []` means *take none*. "Take fewer, but at least one" is expressed by naming the subset you
would take — which the schema already allows and `satisfies_human`'s subset reading already grades.
No new vocabulary is owed.

### 7. A decline is an ordinary ruling. No third state.

[ADR-0082](0082-a-corrections-ruling-lives-in-its-claim-and-must-agree-with-its-record.md)'s Claim
Agreement checks fixture↔record; a
decline is a ruling that `satisfies_human` grades exactly. Nothing interacts.

### 8. This ADR does not re-rule either exposed record.

Making the shape *writable* is a schema change. Deciding that `85785609|0|decision|4` or
`83661652|0|decision|3` *should become* `correct: []` is a human ruling that moves a gate number, and
it belongs to the developer under
[ADR-0088](0088-a-voided-ruling-leaves-the-agree-rate-and-the-gate.md)'s void-and-re-capture
protocol. **This build is gate-neutral: both baselines byte-identical, both diffs clean.**

## Consequences

**A ruling nobody can type is not writable.** The spec asserted that `build_correction` was the only
refusal. Verification found a **second**, in the tagging pane — `shell.py` rejected an empty
`correct` at decision scope client-side, unconditionally. Relaxing the validator alone would have
left the corpus exactly as unable to hold a decline as before, because the pane is the only thing
that calls the validator for a *human* ruling. So the pane is fixed too, gated on the **same**
number: `frames_payload` now carries the select's `min_count`, derived through the same
`select_min_count` the validator uses, so the pane can never offer a save the validator rejects nor
block one it would accept. This is the self-filed-spec failure mode `CLAUDE.md` describes, caught by
re-verifying the claim rather than by trusting it.

**Issue #251's premise holds.** Once the shape is writable end-to-end, the two exposed frames become
*repairable at the source* rather than needing an instrument to route around them. That is #251's own
item 5, and it is why #229 landed first. #251 rules on the consequence.

**The corpus census is now a test.** 372 records, 10 declines all `turn` scope, 28 decision-scope
optional selects of which 2 are exposed — asserted in `tests/train/test_unstatable_decline_records.py`
with a positive control. When the first decision-scope decline is recorded, that test fails, and that
failure is the feature working: a corpus-shape claim in an ADR should go red when it stops being
true, not decay silently.

**Nothing is auto-repaired.** No existing record changes. `records_a_decline_it_cannot_state` stays
unwired (Issue #251) and `Correction.from_dict` stays unvalidated (Issue #256).

## Alternatives rejected

* **A `declines: true` field** — decision 1. Two encodings of one fact, with a representable
  contradiction.
* **Allow `correct: []` at decision scope unconditionally** — would admit a decline on a mandatory
  select, where "take none" is not a legal answer, and would admit unverifiable declines on obs-less
  records, which is the degenerate shape itself.
* **Share one `is_optional_select` predicate with `gates.py`** — decision 3. The two callers need
  opposite fail directions; collapsing them would silently hand the writer the reader's leniency.
* **Repair the two exposed records while in here** — decision 8. A ruling is the developer's, and it
  moves a gate number.
