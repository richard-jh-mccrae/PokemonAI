# ADR-TEMP-239 — A VOIDED ruling leaves the agree rate and the gate, and one Ruling Index says so

**Status:** Accepted (grilled 2026-07-31, `/grill-with-docs` on Issue #239 — seven locked decisions).
**Build = Issue #239.**
**Extends [ADR-0087](0087-a-corpus-reader-constructs-corrections-and-keys-by-identity.md)** (THE
Corpus Reader and the derived Frame Key — this adds a second thing derived from the same walk) and
**[ADR-0072](0072-mid-build-swaps-are-gated-by-deterministic-instruments.md) decision 4** (the
Held-out Ledger — a voided frame gets the same never-gating treatment for a different reason). Does
**not** supersede anything, and does **not** change what either gate gates on.

⚠️ **Temp-named, not numbered.** Real number assigned at `/open-pr` rebase time. Cite the issue.

**Context issues:** Issue #239 (this grill), Issue #241 / ADR-0087 (the Corpus Reader, and
`ruling_moves`, which closed half of Issue #239 before this grill opened), Issue #229 (a Correction
cannot express a DECLINE — neighbouring hole in the same layer), Issue #238 (13 `covered` frames
closed by deleted rungs — three of the 18 refuted labels also cite a deleted rung), Issue #146 (the
correction rounds whose denominator this makes honest), PR #236 / ADR-0085 Amendment J
(`satisfies_human`, left unchanged here), ADR-0082 (a ruling lives in its Claim).

## Context

When a human ruling is later found wrong, the refutation is recorded in
`data/corrections/reviewed.json` as `disposition: "refuted"`. **The Correction record is never
touched** — it still carries the original, refuted `correct`. Every grader reads the record, not the
disposition, so a refuted label scores as a disagreement and the agent is marked wrong for being
right.

### Measured, not recalled (Issue #239, `data/decider_lab/baseline.json` @ `e50735a`, 332 frames)

```
recorded disagreements:                        101
  of which the label is REFUTED:                18
corpus agree rate as printed:              230/331
honest denominator:                       ~230/313
```

A build that "fixed" one of those 18 would be a regression wearing a `FIX` label — and, because the
Decision Gate runs on every push to `main`, it would fail `main` for moving away from a ruling the
human had already disowned.

### Rulings live in four stores; no query spans them

| store | keyspace | who reads it |
|---|---|---|
| `data/corrections/reviewed.json` | `review_key` — `<ep>-<frame>` / `<ep>-t<turn>s<seat>` / `<ep>-m<seat>` | `tune.py`, the blunder report |
| Held-out Ledger (`tests/fixtures/corrections/*.json` `frame_key` + Decision-Claim `owner`) | **Frame Key** — `<ep>\|<seat>\|<scope>\|<subject>` | both `main` gates |
| `snipe_decider_sweep.RECORDED_MISSES` | `review_key`-shaped, free-text values, **no disposition vocabulary** | one probe script |
| the ADRs (prose) | — | humans |

`82749168-38` sits in `reviewed.json` **and** ADR-0085 decision 7 → triaged Tier A. `81905522-75`
sits in ADR-0085 decision 7 **and** `RECORDED_MISSES`, never in `reviewed.json` → triaged Tier C,
*"never reviewed"*. Same ruling, same ADR, same permanence, different tier, purely by which store
held it.

Two further facts read at source and load-bearing below:

* `reviewed.json` already contains `fixed` (5 entries) and `deferred-multi-turn` (1) — dispositions
  absent from `DISPOSITIONS` (`tools/train/blunder/reviewed.py:37`). The vocabulary has **already**
  drifted; a design that puts disposition semantics in each consumer is drifting by construction.
* `gates.ruling_moves` / `print_ruling_moves` (ADR-0087 decision 7) already report a re-ruling
  independent of whether the pick moved. **Issue #239's "the diff is blind to a label move" half was
  closed before this grill opened**, and the `RERULED` verdict it proposed is not built — the report
  lives outside the verdict enum, which is the better place because a re-ruling must never gate.

## Decisions

**1. Scope: the corpus/readout half, plus the aggregate delta line. The diff-blindness half is
closed.**
`ruling_moves` discharges it per-frame. What remains is (a) refuted labels poisoning the agree rate
and the gate, (b) the *aggregate* form of the same failure — offsetting moves presenting as
stillness. No `RERULED` verdict is added.

**2. A read-only Ruling Index — `gates.ruling_index()` — is the one query that spans the stores. No
Correction record is rewritten.**
`{frame_key: Ruling}`, built on `keyed_corrections` so the `review_key`↔`frame_key` join is
**derived per record inside the one walk** (ADR-0087 decision 2: never a hand-assembled key). Both
keys come off the same `Correction`; neither derives from the other, so the walk is the only honest
join point.

Rejected — **put refutation on the record** (`refuted: true` / `superseded_by`): it makes a record
mutable under the C2 provenance contract, needs a migration of committed JSONL, and lands on
ADR-0082's Claim Agreement. It may still be right later; building the index first means that schema
change becomes *one more source the index reads*, not a rewrite of every grader.

Rejected — **each grader reads `reviewed.json`**: the "each consumer needs its own copy" shape
Issue #229 already names and ADR-0087 was written to kill.

**3. The index returns a `Ruling` — raw `disposition` + `source` + `reason` — and ONE derived
predicate, `voids_the_label`. Consumers key on the predicate, never on the string.**
`source ∈ {reviewed, held_out}` (extensible). Precedence when two stores hit one frame: **any
voiding source wins** — a refutation is a strictly later, stronger act than a `covered`, and merging
must never let a weaker disposition mask it. All matches are kept so the readout can name every
store. An **unrecognised** disposition is non-voiding and **surfaced loudly** in both gate readouts,
never silently dropped — `fixed` and `deferred-multi-turn` are the standing proof that silence here
is a live defect, not a hypothetical one.

Keeping the raw disposition is what makes the index also the *"has this frame been ruled, and
where?"* register Issue #239 asks for; deriving one boolean is what stops every grader from having
to learn that `refuted` voids and `covered` does not.

**3a. The index owes a DETACHMENT GUARD, and it must be walked from the ledger's side.**
Added during the two-axis code review, which caught that the property *"a ledger entry naming a frame
the store does not carry is reported rather than silently voiding nothing"* had no production code
behind it — and that the test standing in for it was **tautological**: `ruling_index` walks the
corpus and looks each record up, so `voided_frames(index) ⊆ keyed_corrections()` holds *by
construction* and can never fail. `orphan_rulings` walks the other way, from `reviewed.json` toward
the corpus, and both gates print what it finds.

It immediately found two, live in the committed ledger — and **one of them, `86091435-119`, is a
`refuted`**: a human refutation voiding nothing, silently, which is Issue #239's own defect one layer
in. Fixing them is a re-key or the deletion of a human ruling, so they are pinned by a test rather
than changed here; a *third* turns the suite red.

**3b. `fixed` and `deferred-multi-turn` are ADOPTED into the vocabulary, not left unregistered.**
The spec left this open (*"whether they get formally adopted, renamed, or migrated is a judgement
call for the build"*). Adopted, because the alternative is a permanent warning on every push to
`main` — wallpaper, the exact failure the loud path exists to avoid — and because a writer that
rejects words the loader already accepts is simply broken. The loud path stays armed for the *next*
unknown word, which is what it is for. The writer's tuple and `RECOGNISED_DISPOSITIONS` are pinned
equal by a test, and `blunder/report.py`'s census now derives from the same tuple rather than
re-typing it: that consumer was ALREADY dropping `transposition` and `deferred-multi-turn` from its
counts, which is this decision's own drift showing up in a third place.

**4. A voided frame leaves the agree-rate DENOMINATOR and is held out of the gate. Both counts are
reported.**
A ruling the human took back is no longer a ruling: it cannot say the agent agreed and it cannot say
the agent disagreed. Capture gains `refuted`/`voided` beside `n`/`labelled`/`agree`; the rate becomes
`agree / (labelled − voided)`. In both diffs a voided frame's `REGRESSION` is reported and **never
gates** — the same treatment ADR-0072 decision 4 gives a ruled frame, for a different reason.
`satisfies_human` is **not** touched; the change is in what the callers count and gate on.

Rejected — **count a voided frame as agreement**: actively false. A refuted label says nothing about
whether the agent's pick was good, and inventing 18 agreements would flatter the score with frames
nobody has ruled.

Rejected — **keep them in the denominator and print `n_refuted` alongside**: leaves the live hazard,
a refuted `REGRESSION` still failing `main`, with a footnote.

⚠️ Consequence, accepted deliberately: the agree rate changes value at the next capture, so both
baselines become non-comparable to their current selves. That needs a **deliberate re-capture commit
with the delta explained**. Per `CLAUDE.md` the gates never auto-recapture, and nothing here changes
that.

**5. `RECORDED_MISSES` is RETIRED. Each entry moves to the store whose semantics it matches; the
index reads two sources, not three.**
`82749168-38` needs no action (already `reviewed.json` `refuted`) — the constant was a duplicate.
`81905522-75` gains a real entry (decision 6). The sweep's *"is this run starting to pass a permanent
miss?"* overfitting signal is re-expressed against the index rather than deleted. Same pass replaces
`snipe_decider_sweep._frames`' raw JSONL glob (`snipe_decider_sweep.py:64`) with `keyed_corrections`
— the exact bypass ADR-0087 named.

Rejected — **index reads `RECORDED_MISSES` as a third source**: `gates.py` would import from
`tools/train/probes/`, inverting the layering, and the store would keep a shape with no disposition
vocabulary at all.

**6. `transposition` is a NEW disposition: the ruling stands, but its label names one of an
indistinguishable set, so it cannot grade. Voiding, for a different reason than `refuted`.**
`81905522-75` is two identical Riolu with no board signal splitting them (design-doc R3, ADR-0085
decision 7). The human's judgment is **correct and load-bearing** — ADR-0085 decision 4 cites that
frame's pick to justify leg-scoped rather than whole-target guards. Filing it as `refuted` would
write into the ledger an assertion a shipped ADR contradicts. `DISPOSITIONS` gains `transposition`;
`voids_the_label` is true for `{refuted, transposition}`; the readout prints the disposition, so a
transposition exclusion never reads as a refutation in CI logs.

Deferred to **Issue #247** — making `satisfies_human` transposition-*aware* (an equivalence
class over indistinguishable select options, so either pick satisfies). That is the better eventual
answer and it fixes the class rather than the instance, but it needs a sound "these two options are
indistinguishable" oracle read off the frame's `obs` — a board-reading problem, not a corpus-record
one — and it would change a predicate two `main` gates key on. Not smuggled into this build.

**7. Both diffs return an `agree_delta` block, printed by ONE shared printer beside
`print_ruling_moves`.**
`{before: (agree, denom), after: (agree, denom), moved, reruled, voided}`, rendered e.g.
`agree 230/331 -> 231/313  (3 picks moved, 1 ruling moved, 18 voided)`. Pure over the two captures,
unit-testable with no filesystem. `leaf_lab_diff` gets the identical treatment through the same
printer — the two instruments are kept beside each other precisely so they cannot drift.

Rejected — **full causal decomposition** (`+1 reruled, −1 regressed`): a frame can be re-ruled,
voided and moved at once, so no point of the delta has a single honest owner. This repo's history
(the mis-keyed baseline, the under-reporting diff) says a confidently-wrong instrument is the
expensive failure; a count cannot be confidently wrong.

Rejected — **before/after rate only**: `230/331 -> 230/331` with three rows moved is verbatim the
state Issue #239 calls dishonest.

Two readout details, decided at build time rather than in the grill:

* **`--context` withholds the delta.** The delta is corpus-wide while `--context` reports one
  `SelectContext`'s frames; printing it there would put two populations in one report — the exact
  trap `ruling_moves`' `keep` argument exists to avoid. Withheld with a one-line note rather than
  mislabelled.
* **Voided frames list on `capture`, tally on `diff`.** 25 frames with paragraph-length reasons on
  every push to `main` is wallpaper — the failure the Held-out Ledger's own glossary entry warns
  about. The verdict block still names any voided frame that actually MOVED (the actionable subset),
  and the machine-readable artifact carries `{frame key: disposition}` rather than a bare key list, so
  a consumer can tell a `transposition` exclusion from a `refuted` one.

## Measured at the build (2026-07-31, not recalled)

```
Ruling Index over the committed corpus:        25 voided   (24 refuted, 1 transposition)
Decision Gate agree rate:                253/371  ->  248/346      (25 voided out of the rate)
Discrimination Gate agree rate:          193/268  ->  183/249      (19 voided out of the rate)
snipe_decider_sweep DAMAGE frames:            19  ->  23           (the raw walk's dropped records)
raw-reader allowlist census:                  11  ->  10
```

Two readings worth keeping. **Five of the 25 voided frames were previously scored as AGREEMENTS**
(253 − 248 = 5 while 371 − 346 = 25) — so voiding is not a one-way flatter of the number; it removes
frames from both sides, which is the point. And the snipe sweep saw **19 DAMAGE frames where the
corpus holds 23**: its private raw-JSONL walk was short four records, exactly the loss ADR-0087
measured on the Decision Gate, and retiring `RECORDED_MISSES` is what forced that walk out.

A third reading, found by a test rather than by inspection: `82749168-38` is **seat 1**. The retired
constant keyed it `"82749168-38"` with no seat at all, which is why that store could never join the
gates' keyspace — the concrete form of *"a frame can be ruled four ways and still read as unreviewed"*.

## Consequences

* One query answers *"has this frame been ruled, and where?"* — the register Issue #239's table was
  written to demand. `81905522-75` and `82749168-38` stop being triaged differently by accident.
* The Decision Gate stops failing `main` for correcting a ruling the human disowned.
* Issue #146's correction rounds get an honest denominator.
* Cost: a deliberate baseline re-capture on both gates; a new vocabulary word and its ADR entry; a
  probe script edited outside its own scope; both gate readouts gain lines, so `main`'s CI log format
  changes.
* Not addressed, by design: the transposition *class* (**Issue #247**), Issue #229's DECLINE-writer
  question, and Issue #238's expired coverage claims.
