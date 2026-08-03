# ADR-0110 — A gate flip caused by a re-ruling is LABELLED, never excused

**Status:** Accepted (agent-grilled 2026-08-02 on Issue #230, batched issue-sequence run); BUILT.
**Extends [ADR-0087](0087-a-corpus-reader-constructs-corrections-and-keys-by-identity.md) decision 7
(`ruling_moves`, the never-gating detector this consumes) and
[ADR-0072](0072-mid-build-swaps-are-gated-by-deterministic-instruments.md) (the Discrimination
Gate's verdict rule, which this leaves EXACTLY as it was).**
**Rides beside [ADR-0094](0094-recapture-must-be-ruling-gated.md)** — that one guards *whether* a
re-capture may be written; this one writes down *where it must be taken from*, the half 0094's guard
structurally cannot see.
Does **not** supersede anything.

**Context issues:** Issue #230 (this build), Issue #241 / ADR-0087 (`ruling_moves`), Issue #259 /
ADR-0094 (the ruling-gated capture, and the trace of `84071010|0|decision|15` this ADR reuses),
Issue #165 (holds that frame out).

## Context

`leaf_lab_diff` compares `correct_is_top`. That field is **frozen into each capture** and computed
under *that capture's own* `correct` (`leaf_lab.py`, `evaluate_leaf_on_correction`). So when the
human re-rules a frame, the diff grades its two halves under **two different oracles** — and prints

```
REGRESSED 84071010|0|decision|15  OK -> MISS   rank 1 -> 2
```

about a build that did not move. `discrimination_gate_verdict` excuses only `held_out │ voided`, so
the frame counts in `ok_to_miss` and the gate goes red.

### Verified on this checkout, not recalled (2026-08-02)

The detector for this already exists and is already wired. `gates.ruling_moves` (ADR-0087 decision 7)
compares the two captures' `correct`, is called by **both** `leaf_lab_diff` and `decider_lab_diff`,
and prints through `print_ruling_moves`. What did not exist was any connection between that detector
and the verdict readout. Probed directly, with a positive control:

| case | `ok_to_miss` | `ruling_moves` | gate |
|---|---|---|---|
| ruling moved `[1] → [2]`, `correct_is_top` flips, agent pick unchanged | `['reruled']` | 1 | **FAIL** |
| control — same `correct` both sides, agent genuinely regressed | `['real']` | 0 | **FAIL** |

The two are **indistinguishable** in the readout and in the verdict. That is the defect.

**The defect is the LABEL, not the redness.** The gate is *right* to be red: its reference was
captured under a ruling that no longer stands, so it cannot speak about this frame. It was *wrong*
about why — it said the build regressed, and the build did not move.

## Decisions

### 1 — A Ruling-Move flip still FAILS the gate. It is not excused.

`discrimination_gate_verdict` reads `ok_to_miss` **whole** and does not consult the new key. A gate
getting quieter as a side effect is the one direction a gate must never move (ADR-0085 Amendment I),
and an excuse keyed on "the ruling also moved" would give a real regression somewhere to hide:
re-rule a frame in the same commit that breaks it and the red disappears.

This is enforced **structurally, not by convention** — `stale_baseline` holds the very entry objects
`ok_to_miss` holds, so "it stays gated" is an identity, not a promise. `discrimination_gate_verdict`
therefore returns the identical verdict on every input before and after this change. **The build is
verdict-neutral by construction**, which is why neither committed baseline is owed a re-capture for
it, and why a gate flip out of this change would have meant something was built wrong.

### 2 — Re-label them: `leaf_lab_diff` gains a `stale_baseline` partition.

The `ok_to_miss` entries whose `key` is also in that same diff's `ruling_moves`, drawn from the
**same** `_scorable` row filter — a partition naming a frame the report's own `compared` count
excludes would put two populations in one report, the trap `ruling_moves`' `keep` argument already
exists for.

`print_stale_baseline` (shared, beside `print_ruling_moves`, so two readouts cannot describe one
fact differently) prints them always-visible-when-non-empty like `HELD OUT` and `VOIDED`, with the
one sentence the frame is owed: *re-capture at a commit carrying the ruling but **not** the change
under test, then re-run.* The key also reaches the JSON gate artifact, as a subset of `ok_to_miss`
rather than a subtraction from it.

### 3 — REJECT "a re-ruling must re-capture in the same change, test-enforced".

Enforcing same-change re-capture forces the capture to happen at `HEAD`, which bakes the change under
test into its own reference — the vacuous-gate failure `decider_lab_diff`'s docstring exists about,
and precisely how the old Decision Gate died. It also couples two independent acts: re-ruling a frame
is a statement about the game, re-capturing is a statement about a build.

Decision 2 makes the gate **self-announcing** instead, which is strictly better on both counts: it
fires only when it actually matters, and it names the fix rather than performing it.

### 4 — Write the capture point down: *"a commit carrying the ruling but NOT the change under test."*

Tribal knowledge until now, and it cost ADR-0094's author a wrong answer before the right one — the
wave-1 packet asked to rule `84071010|0|decision|15` and *then* re-capture, on a premise that turned
out stale; the frame was already a `MISS` in the baseline and already held out onto Issue #165.

It lands in `docs/ci.md` §"Where to re-capture FROM", with `guarded_capture`'s docstring pointing at
it. Naming the gap that guard leaves is the point: ADR-0094 asks whether every fail-direction frame
carries a **ruling**, never whether the tree carries the **change**. A capture taken at `HEAD` passes
that guard and still poisons the reference.

### 5 — The Decision Gate deliberately gets NO symmetric partition.

`ruling_moves` is shared by both diffs, so an asymmetry here has to be argued rather than assumed.
Probed on this checkout:

* a re-ruling with an **unchanged pick** emits **no verdict row at all** from `decider_lab_diff` —
  the row is gated on `chosen` moving, so there is nothing to mislabel;
* when the pick *did* move, `correct` is resolved from the **after** capture alone and grades **both**
  sides through it (`gates.decider_lab_diff` comment at `gates.py:1400`: *"Resolved from TODAY's
  corpus, never from either capture"*). One oracle, both halves.

So a decider `REGRESSION` beside a ruling move remains the honest claim *"under today's ruling this
build is wrong here and the baseline was right."* Labelling it `stale_baseline` would print
*"your reference cannot speak, re-capture"* over a reference that speaks fine — the mirror image of
the defect this ADR fixes. The asymmetry is a property of the two diffs' oracle handling, not an
oversight, and it is locked by a test rather than left to this paragraph.

## Consequences

* One new key, one new shared printer, one new `docs/ci.md` section. No verdict moves; both gate
  diffs were clean after the change, as decision 1 predicts.
* The `stale_baseline` label is only as good as `ruling_moves`, which needs `correct` present in
  both captures. A baseline predating that field reports nothing here — it degrades to today's
  behaviour rather than to a wrong answer.
* A frame can be stale-labelled *and* genuinely regressed at once (re-ruled and broken in the same
  build). The readout says both things and the gate stays red, which is the honest outcome; no
  attempt is made to decompose the cause, for `agree_delta`'s reason — a confidently-wrong
  instrument is this module's expensive failure.
