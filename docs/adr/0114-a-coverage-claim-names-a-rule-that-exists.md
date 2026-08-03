# ADR-0114 — A coverage claim names a rule that EXISTS, and expiry is made loud

**Status:** Accepted (agent-grilled 2026-08-02 on Issue #238, batched issue-sequence run); decisions
1-6 BUILT. Issue #238's items 1-3 — opening 27 frames and ruling each — are **handed back to the
developer**, not built; see *Scope*.
**Sits beside [ADR-0113](0113-the-store-is-an-archive-so-the-writers-rules-are-re-applied-as-a-report.md)**
and [ADR-0112](0112-a-gate-reports-what-it-cannot-grade-it-never-stops-grading-it.md),
whose ruling this repeats one store over: those re-apply a rule to committed **Correction** records
and REPORT; this re-applies one to the committed **review ledger** and reports. All three report;
none excludes, and none moves a gate number.
**Amends nothing.** No gate verdict function changes, no frame starts or stops gating, both
baselines byte-identical.

**Context issues:** Issue #238 (this ruling), Issue #241 (whose comment on it added 14 candidates),
Issue #229 (the **Correction** record schema — a *different* store, see decision 5),
[ADR-0069](0069-the-attach-marginal-is-an-axes-sum-and-the-decider-may-say-no.md) / Issue #139 and
[ADR-0070](0070-the-evolve-marginal-is-a-body-substituted-delta-in-damage.md) / Issue #140 (the deletion
passes that emptied the rungs these notes name),
[ADR-0100](0100-the-promote-retreat-equation-is-the-sub-lethal-residual-in-damage.md)
(the promote/retreat deletions), [ADR-0102](0102-hand-size-relief-is-the-survival-a-refresh-buys-on-both-hands.md)
(the most recent, which took `play-harlequin-vs-hand-size` two days before this audit ran),
[ADR-0090](0090-a-ruling-names-its-record-through-a-resolver.md) (the ledger's key shape and its
resolver), [ADR-0088](0088-a-voided-ruling-leaves-the-agree-rate-and-the-gate.md) (the **Ruling
Index**, which reads this ledger's `disposition` and never its prose).

## Context

`data/corrections/reviewed.json` closes a Correction with `disposition: "covered"` when a shipped
rule is believed to handle the frame. That is a claim about the **shipped agent**, and it is stored
as one string of free prose. Nothing has ever read it back.

Four deletion passes have since emptied most of the rung families those closures name. When the rule
a closure names is deleted, the closure does not become wrong — it becomes **unexamined**. The frame
is still held off fresh work, by a reason that no longer exists, and no surface anywhere says so.
Issue #238 found 13 of these by hand, by cross-referencing the four `*_decider_sweep.py` probes'
`RETIRED` lists out of git history.

This is the same failure shape the Decision Gate rebuild is built around — *a measured claim expires
when the thing it measured moves* — one level down, in a store instead of in a gate.

### Verified on this checkout, not recalled (2026-08-02)

Every rung count below is an AST harvest of `Hypothesis(id=…)` over `src/**/*.py`, not a grep: a
grep for `id="…"` over-counts by 15 on this tree because it cannot tell a `Hypothesis` id from a
`SoundRule` one, and that is exactly the distinction that decides whether a token is a live rung.

| Claim | Verdict | Evidence |
|---|---|---|
| the five rungs the 13 `covered` notes lean on have **zero** live definitions | **TRUE** | `dont-waste-discard-energy`, `concentrate-energy-on-wincon`, `build-active-wincon`, `power-up-attacker`, `conserve-burst-when-no-ko` — 0 each; `attach-energy-last` (the `refuted` trio) 0 |
| **POSITIVE CONTROL** — the rungs the same swap KEPT are found | **TRUE** | `prefer-active-attach-in-setup` and `use-acceleration`, **1 each**, both in `baseline_energy.py`. A sweep that cannot find these could not be believed about the zeros |
| **STRUCTURAL CONTROL 1** — the git-history harvest sees every rung that is live today | **TRUE** | all 95 live ids appear in it |
| **STRUCTURAL CONTROL 2** — it sees every name the four sweeps' `RETIRED`/`ZEROED` tuples list | **TRUE** | 45/45 |
| all 13 of the issue's hand-derived frames are flagged by the mechanical check | **TRUE** | 13/13, plus the 3 `refuted` re-reads |
| the live rung count is 110 | **FALSE — the spec's own number** | **95**. 110 is the crude `id="…"` grep, which sweeps in 15 `SoundRule` ids |
| all five vanished rungs "appear by name" in `baseline_energy.py`'s fold map | **FALSE — the spec's own claim** | only `dont-waste-discard-energy` and `conserve-burst-when-no-ko` do. The other three appear ONLY as the abbreviations `concentrate` / `build-active` / `power-up`. This is why the fold map is not the vocabulary |
| "a first pass flags 63 stale of 108 `covered`" | **FALSE — the spec's own headline** | **60** entries over the whole ledger, of which **50** are `covered`. The 63 came from the crude scan the spec itself calls unreliable |

## Scope — what an agent may build here, and what it may not

Issue #238's items 1-3 ask, per frame, whether the agent's current decision is right **on its own
merits**. That is a human ruling about Pokémon TCG play — the same act the corrections corpus exists
to record — and the issue forbids the shortcut in its own words: *"Each needs the frame opened … not
a bulk re-open."* An agent producing 27 such rulings and committing them would be manufacturing the
one thing the store is supposed to hold only human judgement of.

So this ADR ships the **instrument and the worklist**; the developer ships the rulings. That split is
what makes item 4 worth building: a validator with no worklist is a red test nobody can action.

## Decision

### 1. A `covered` disposition is auditable, and the audit is `tools/train/reviewed_audit.py`

Item 4 of the issue — *"the mechanical version of this whole finding"* — is the only part that
prevents recurrence. A `covered` claim expires silently because the ledger stores prose; the audit
reads the prose back and names the closures whose stated rule is gone.

### 2. The vocabulary is CURATED and HARVESTED, never a loose regex and never a hand list

A review note is prose. The corpus's most frequent hyphenated token is `attack-last` — 46
occurrences — and it is not a rung at all; it is the Pilot's structural resequencing. A bare
`[a-z-]+` scan flags nearly every note in the ledger, which is why the spec's crude first pass
reported 63 with visible false positives.

A token resolves only against three harvested namespaces:

* **live** — every `Hypothesis(id=…)` in `src/`, by AST, at audit time. Never a list: a rung deleted
  tomorrow leaves the live set tomorrow with no edit anywhere.
* **sound rule** — every `SoundRule(id=…)` in `src/`. Its own namespace because 15 of its ids are
  hyphenated and were never Hypotheses; without this they would read as retired rungs.
* **retired** — every id that WAS a `Hypothesis(id=…)` at some commit and is not one now, harvested
  from `git log --all -p` over `src/**/*.py`.

Anything in none of the three is **not a rung reference** and is never flagged. The count of those
(242 distinct, 415 occurrences) is printed beside the finding so the vocabulary's own blind spot
stays visible instead of being quietly absorbed.

**The retired half is definitional, not prose-derived, and that was a change from the plan.** The
spec proposed harvesting retired names from the committed fold maps in `baseline_*.py`. Measurement
killed that: `baseline_energy.py`'s fold map ABBREVIATES — `concentrate / build-active / power-up /
spread / …` — so three of the five rungs the whole issue is about do not appear there by name at all.
*Was a Hypothesis, is not now* needs no prose parsing and cannot be defeated by an author's
shorthand. The fold maps are still read, but for the report's *what it became* column, which is the
job they are actually written for.

### 3. The audit REPORTS; the ratchet is an allowlist, not a red build

It flags 60 committed entries. A hard failure would red `main` on day one with no path to green
except mass re-closure — the bulk re-open item 1 forbids. So a test asserts the flagged set equals
`data/corrections/reviewed_audit_allowlist.json`, which **is** the developer's worklist. Ruling a
frame and re-closing it against a live rule removes it from both. A *new* expired closure is red
immediately.

The allowlist is keyed by entry **and carries the dead rungs**, so re-closing an entry against a
*second* dead rung is a change it notices; a bare key list would have called that green.

Bulk-refreshing the allowlist to go green defeats the whole mechanism. That is not hypothetical —
`CLAUDE.md` records it as exactly how the old Decision Gate died.

### 4. The worklist is generated, and carries what the rule BECAME

`docs/plans/covered-disposition-audit.md`: one row per flagged entry — ledger key, disposition, the
dead rung(s), **what each became**, any live rule still named, and the note verbatim. The *what it
became* column is what makes a ruling cheap (`dont-waste-discard-energy` → *the BURST discipline* is
usually enough to decide whether the modern equation still reaches the call), and it is read out of
the code's own fold maps rather than written by hand — an empty cell where no fold map names the rung
is a real answer and better than an invented target.

The report's reconciliation against Issue #238's own lists is **derived at render time**, not
transcribed: 13/13 of the body's list, 3/3 of the `refuted` re-reads, 4/14 of the Issue #241 comment.

The test on the report asserts coverage (every allowlisted key appears), deliberately not byte
equality against a fresh render — the *what it became* column reads `src/` prose, so a byte-compare
would red CI on an unrelated docstring edit, which is the day-one wall decision 3 exists to avoid.

### 5. This lives with the LEDGER, not with the Correction schema

Issue #238 wonders whether item 4 belongs in Issue #229's neighbourhood. It does not. Issue #229
governs the **Correction** record schema; `reviewed.json` is the **review ledger** — a separate
store, keyed `<episode>-<frame>`, a third key shape carrying neither seat nor scope. The audit reads
it through `blunder.reviewed.load_reviewed`, the store's own loader, and reports in the store's own
key shape.

`gates.shape_the_constructor_would_refuse` (ADR-0113) is the same *"re-apply a rule to committed
records"* shape, and is deliberately NOT reused: it is `Correction`-keyed, and putting a ledger rule
behind a record-schema function would conflate two stores whose keys do not agree.

### 6. `refuted` notes are audited too, and listed apart

`82525741-81`, `82867148-87` and `85058574-114` cite a deleted rung in their *refutation*. A
`refuted` label owes no fix either way, so they are not blockers — but the refutation rests on the
same vanished premise, so the audit covers every disposition and the report lists the non-blocking
ones in their own section. Seven entries qualify, not three: the audit found four more the issue
never named.

## Consequences

* **60 expired closures are now visible**, against the 13 the issue derived by hand: 50 `covered`,
  7 `refuted`, 2 `fixed`, 1 `deferred`, over 25 distinct dead rungs. Forty of them are entries Issue
  #238 never named. All 13 of the issue's list, and all 3 of its `refuted` re-reads, are inside the
  60 — the mechanical check is a strict superset of the hand reading.
* **10 of the Issue #241 comment's 14 are correctly NOT flagged**, and this is the vocabulary
  earning its keep rather than a miss: every one of the 10 closes on `attack-last`, verified by
  reading their notes. That names no rung, live or dead. Their question — *is same-turn ordering a
  blunder at all?* — is a different one, and the comment filing them says so.
* **The 27 adjudications remain unscheduled work.** This ADR does not rule a single frame. The
  worklist is the input to that sitting.
* **A shallow clone cannot re-derive the vocabulary**, so it is committed. `load_vocabulary` still
  widens the retired set with `live_at_capture − live_now`, which covers deletions made after the
  last refresh with no git access; the git-derived half is re-verified by a test that skips, loudly,
  where history is absent.
* **No scoring code is touched.** Both gate diffs clean, both baselines byte-identical.

## Alternatives considered

* **Fail CI on any expired closure.** Rejected by decision 3: 60 red entries on day one, and the
  only fast route to green is the bulk re-closure the issue forbids.
* **Harvest the retired names from the fold-map docstrings** (the spec's proposal). Rejected on
  measurement: the energy fold map abbreviates, so three of the five rungs the issue is about are not
  there by name. Kept for the *what it became* column, where abbreviation is fine because a
  hyphen-prefix match inside a slash-separated name list is unambiguous.
* **Hand-maintain the retired list.** Rejected: it is the same artefact as the `covered` note itself
  — a claim about the codebase, written once, never re-read.
* **Validate on write, in `review_correction.py`.** Insufficient on its own and out of scope here:
  the 60 are already committed, and a writer-side check cannot see a rung deleted *after* the entry
  was written, which is every case in the backlog. Worth doing later; it would prevent a different
  (smaller) failure.
* **Put the check in `gates.py` beside the Refused Shape audit.** Rejected by decision 5: different
  store, different key shape.
