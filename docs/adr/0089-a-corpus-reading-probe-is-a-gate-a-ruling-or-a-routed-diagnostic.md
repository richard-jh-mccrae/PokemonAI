# ADR-0089 — A corpus-reading probe is a GATE, a RULING, or a routed DIAGNOSTIC — never a fourth thing

**Status:** Accepted (grilled 2026-07-31, `/grill-with-docs` on Issue #243).
**Build = Issue #243.**
**Extends [ADR-0087](0087-a-corpus-reader-constructs-corrections-and-keys-by-identity.md)** (a corpus
reader CONSTRUCTS Corrections and keys by IDENTITY — *how* a reader reads) with the question that ADR
did not ask: *what a corpus-reading probe is allowed to be at all.*
**Finishes [ADR-0085](0085-snipe-is-a-categorical-relevance-instrument-and-the-fold-collapses-the-additive-stack.md)
Amendment J** on its fourth, missed sibling. Does **not** supersede anything.

**Context issues:** Issue #243 (this grill), Issue #241 (ADR-0087 — the parent; recorded the census of
eleven raw readers), Issue #239 (ADR-0088 — converted `snipe_decider_sweep`, the exemplar payoff),
Issue #238 (the consumer of the widened corpus).

## Context

ADR-0087 fixed the Decision Gate's corpus read and, measuring the blast radius, found `decider_lab`
was not the second raw reader but the **twelfth**. Issue #243 owns the other eleven. Its stated
presumption — *delete the four `*_decider_sweep.py`, they are the vacuous ones* — did not survive
being measured.

### Measured 2026-07-31, not recalled

```
snipe_decider_sweep            already converted (Issue #239, ADR-0088) — off the allowlist
attach_decider_sweep           OLD arm ALREADY DELETED by ADR-0085 Amendment J  -> healthy
evolve_decider_sweep           OLD arm ALREADY DELETED by ADR-0085 Amendment J  -> healthy
promote_retreat_decider_sweep  OLD arm ALREADY DELETED by ADR-0085 Amendment J  -> healthy

deploy_decider_sweep           NOT flagged by the issue — and it is the vacuous one
  params["deploy_value"] = False; overrides = {hid: 0 for hid in RETIRED}
  all nine RETIRED hypothesis ids are GONE from src/; baseline_bench holds one rung
  -> OLD scores a near-empty pile, argmax falls to option index -> FIX-or-nothing
  -> and it is the ONLY one of the ten that gates:  raise SystemExit(sweep(...))
  -> and it HAND-BUILDS the frame key (ADR-0087 decision 2), feeding held_out_frames()
```

Amendment J retired the three siblings and missed this one **because it was the only one that
gated** — a passing exit code read as evidence of health.

Two further vacuities found in passing:

```
threat_sweep --slots   compares the shipped PROFILE against _forced(gust_target_slots=True) /
                       _forced(recur_fuel_relax=True) — both flags ship ON (runtime.py:180, :156,
                       armed-ON 2026-07-27). Same-vs-same: 0 flips BY CONSTRUCTION.
                       Its sibling sweep_rank forces BOTH sides explicitly and its docstring says
                       why ("so it stays an A/B after the PROFILE ships the flag ON") — sweep_slots
                       is exactly the mistake that comment was written to prevent.

deploy_anchor_sweep    self-declares terminal in its own docstring: "Result, 2026-07-29: NO USABLE
                       ANCHOR, and the reason is structural" / "Capturing more frames cannot
                       change this."
```

### The enforcement was scoped to half the tree, and to a spelling

`tests/train/test_corpus_readers.py::_python_sources()` walks `REPO/"tools"` only, and `_GLOB_RE`
matches a `glob(` call. Both bounds are occupied:

```
tests/strategy/*  globbing the corpus raw:                              9
  test_scaled_rank_corpus.py carries the IDENTICAL filter, verbatim:
      if d.get("obs") and d.get("agent"):        # -> short the same 40
  the other 8 glob raw, then select HARDCODED (episode, frame) literals

reading data/corrections/ by a FIXED PATH — invisible to _GLOB_RE:      2
  tests/strategy/test_attach_target_priority.py:32
  tests/strategy/test_counter_mover_attach.py:41
      REPO/"data"/"corrections"/"dragapult_ex_20260715_32530b9"/"corrections.jsonl"
```

A hardcoded build-directory name is arguably *worse* than a glob: it breaks silently when a build
dir is renamed. A check that names a spelling rather than a behaviour trains people to find another
spelling — and two files found one without anyone doing it deliberately.

### The actual gap

All four vacuous sweeps satisfied ADR-0087's reader contract perfectly well and were still
worthless. Reading the corpus correctly is necessary and not sufficient. Nothing said what a probe
is *for*, so `tools/train/probes/` accumulated a fourth category — **a runnable script nobody
watches** — which is where every failure in this series was incubated: four sweeps reported PASS for
weeks in a state where PASS was impossible to distinguish from FAIL, and PASS was read as evidence.

## Decisions

### 1. Three fates, and the fourth is the failure

A module that reads the corrections corpus is exactly one of:

* **A GATE** — a committed baseline (a *ruling record*, never auto-recaptured) plus a CI watchdog
  that turns red. `leaf_lab` + `leaf-gate-main.yml`, `decider_lab` + `decider-gate-main.yml`.
* **A RULING** — a one-shot investigation whose answer is written down and whose script is then
  **deleted**. The recorded answer is the artifact; the script is scaffolding.
* **A routed DIAGNOSTIC** — re-runnable, answers a question the gates deliberately do not
  (e.g. the per-axis *term breakdown* behind a decision, which `decider_lab` records the outcome of
  but never the terms of), and reads through `gates.keyed_corrections` / `train.blunder.store`.

A runnable script that is none of these is the failure mode, not a fourth option. It is
unfalsifiable by construction: nobody runs it, so nobody notices when what it measures stops
existing.

### 2. A corpus-wide ruling carries its provenance

A ruling reached by **counting across the whole corpus** is a claim about a corpus that will not
exist next week. It must record `measured at <commit>, N frames`. Without the stamp a future reader
cannot distinguish a live finding from one computed against a corpus half the current size — which
is not hypothetical: `budget_sweep`'s "zero decision flips" was ruled over 332 frames while the
corpus held 372.

### 3. A structural or named-frame ruling does NOT need the stamp

Growing the corpus cannot move it, and a stamp that is applied where it cannot matter trains people
to apply it without reading. Explicitly:

| ruling | why exempt |
|---|---|
| `deploy_anchor_sweep` | structural; the docstring says capturing more frames cannot change it |
| `deny_gate217` | reads six hardcoded `(episode, frame)` literals — corpus size is not an input |
| `deny_gate1` | the answer was CATEGORICAL ("deny is a relevance instrument, not a magnitude one", ADR-0080); the rate was ruled MOOT |
| `budget_sweep` | **NOT exempt** — a count over every frame. Re-run on the full corpus before the ruling is accepted. |

### 4. `ALLOWED_RAW_READERS` is a work queue that terminates — here

The allowlist is paid to **empty** by this issue and the dict is deleted, along with the three tests
that exist only to police its entries (`..._exists_and_still_reads_raw`, `..._names_an_issue`,
`..._census_matches_what_the_grill_measured`). What survives is the enforcement that matters, and it
survives *widened* (decision 5): no module outside the store reaches the corpus.

An allowlist kept alive past its work queue becomes a set of permanent exemptions nobody can
distinguish from real ones. An allowlist that empties while unenforced readers sit one directory
over is worse — it is a false clean.

### 5. The rule forbids reaching the corpus, not one spelling of it

`_python_sources()` walks `tools/` **and** `tests/`, and the check matches any construction of a
`data/corrections` path — not just `glob(`. Eleven files convert: the nine globbing tests plus the
two fixed-path readers. `test_modules_that_only_mention_the_log_in_prose_are_not_flagged` is
extended to guard the second pattern against matching prose, for the reason it already exists: a
check that cannot tell a mention from a read trains people to widen the allowlist.

Measured: `_GLOB_RE` over `tests/` flags exactly those nine and no tenth; `tmp_path /
"corrections.jsonl"` constructions (14 files) correctly do not match.

**The widened pattern must not over-match, and getting that right took a real case.** `data/corrections/`
also holds the reviewed ledger, the tuner's proposals and the machine store, and every gate CLI
defaults `--store` to that directory before handing it to `train.blunder.store` — which is the
contract being *followed*. So the rule targets reaching the **log**, not the directory. One genuine
over-match surfaced on first run: `tests/label/test_category.py` passes
`"data/corrections/machine/corrections.jsonl"` to `git check-ignore` to prove the machine store stays
untracked, and never opens it. The slash-string spelling therefore only counts when the same line
also builds or opens the path. Flagging that test would have forced a correct assertion onto an
exemption list — restarting the decay decision 4 removes the allowlist to end. Both the catch and the
non-catch are pinned as cases.

### 6. One seam for the whole family — and ONE helper, not eleven copies

All eleven conversions go through `gates.keyed_corrections()`. Ten of the eleven have no use for the
Frame Key and discard it. That cost is taken deliberately: the failure this ADR closes is *many
slightly-different ideas of what the corpus is*, and the lower seam (`store.jsonl_files` +
`load_corrections`) — though explicitly permitted by the contract — preserves two idioms at exactly
the layer where they diverge.

The eleven private loaders collapse into **one shared test helper**, `tests/corpus_helpers.py`
(`corpus_index` / `corpus_record` / `corpus_records` / `replay_agent`), following the established
`tests/`-on-path convention (`pilot_helpers`, `scouting_helpers`). Eleven copies of the same
two-line comprehension would satisfy the letter of the contract and reproduce its spirit's failure —
eleven places a defect can live. The index is `lru_cache`d because eleven modules constructing the
whole corpus independently would pay for it eleven times.

Verified safe: all 372 `(episode_id, frame)` pairs are unique, so the re-index preserves every
file's semantics including the last-write-wins ones, and `load_corrections`' dedup makes it strictly
safer than the raw walks (which appended per matching line and would double-count a duplicate).

Two behaviours changed on purpose, both toward failing louder:

* `corpus_record` **raises** where `test_needs_deny_resolver` used to `pytest.skip`. Every caller
  names a literal frame it asserts real behaviour about; a skip nobody can notice is the same
  false-clean shape this ADR exists to remove.
* `test_leaf_profile`'s `len(out) == len(wanted)` guard becomes a raise that names *which* frame is
  missing, where the count could only say that one was.

## What the widening actually surfaced — measured 2026-07-31

The 40-record backfill was expected to force adjudications. It forced **none**. Both frames that
looked like they would need a ruling were measured, and both are clean:

```
82228640-9   EXCLUDED in test_hyperclosure_corpus.py as "no-agent — unreplayable".
             FALSE on both counts: agent backfills to mega_starmie, obs present,
             correct=[1], chosen=[0].  Shipped Pilot picks [1] == correct.
             -> exclusion deleted, frame moved into test_hyperclosure_corpus's PINS.

test_scaled_rank_corpus.py, widened 332 -> 372:
  CLEFAIRY_EX (272)        8 frames,  0 new,  0 failures, fired 8,  max 120.0
  KADABRA/ALAKAZAM (742,743) 18 frames, 7 new, 0 failures, fired 21, max 0.0 -> 280.0
             -> all 7 new frames satisfy every in-loop invariant. Converts straight.
```

Issue #238 is therefore **not** touched by this build, and no frame enters the Held-out Ledger. That
is a finding, not an assumption: the census predicted `test_hyperclosure_corpus.py` would be the
hard conversion, and measuring it retired the prediction — the same "measure before asserting"
correction this ADR series keeps having to make.

The build then retired two more predictions the same way:

```
budget_sweep re-run, measured at 4be1db3, 372 frames:
  371 SAME, 0 IMPROVED, 0 REGRESSED, 0 MOVED, 1 SKIP     -> ruling SURVIVES the widening

corpus agent census:  247 mega_starmie  70 mega_lucario  54 dragapult_ex  1 SkiChu
```

`SkiChu` is why the private `_agent` fallbacks were **kept**, not deleted. The census had called them
deletable on the strength of one frame that backfills cleanly; repo-wide, one record names an agent
with no directory of its own, and dropping the fallback would have crashed a replay. It survives as
`corpus_helpers.replay_agent`, with the reason stated — the workaround it *did* retire is the
"predates the agent field" comment, which the backfill made false.

## Consequences

### Dispositions

| module | fate | why |
|---|---|---|
| `deploy_decider_sweep.py` | **DELETE** | vacuous OLD arm, gates on it, hand-built key. Keep `_records_a_decline_it_cannot_state` → `gates.py` (public), with its test retargeted — **lifted UNWIRED**, see below |
| `deny_gate1.py` | **DELETE** | answered categorically, ADR-0080; forces `deny_strip_delta`, ships OFF |
| `deny_gate217.py` | **DELETE** | answered, ADR-0084; six hardcoded frame literals |
| `deploy_anchor_sweep.py` | **DELETE** | self-declared terminal in its own docstring |
| `budget_sweep.py` | **SPLIT** | re-run on the full corpus, stamp the ruling, then delete the runner; keep the tested pure core (`upgrade_charged`/`wrap_reachable`/`verdict`, REQ-BUDGETSWEEP) |
| `attach_decider_sweep.py` | **ROUTE** | live term-breakdown diagnostic + the ADR-0069 retune grid |
| `evolve_decider_sweep.py` | **ROUTE** | live term-breakdown diagnostic; OLD arm already gone |
| `promote_retreat_decider_sweep.py` | **ROUTE** | live term-breakdown diagnostic; OLD arm already gone |
| `needs_sweep.py` | **ROUTE** | `docs/writeup-from-corrections-to-needs.md` promises its numbers reproduce |
| `threat_sweep.py` | **ROUTE, −2 modes** | `--doom`/`--recur`/`--target` live; **delete `--slots`** (same-vs-same, 0 flips by construction) and **`--rank`** (answered ADR-0083, covered by `test_scaled_rank_corpus.py`); fix the stale line-17 docstring |
| 11 files under `tests/strategy/` | **ROUTE** | 9 globbing + 2 fixed-path; one carried the identical 40-record filter |

### The predicate is lifted UNWIRED, and that is the decision

`records_a_decline_it_cannot_state` moves to `gates.py` **and gains a `decision`-scope guard the
measurement exposed.** Three committed records sit on an optional select asserting only the agent's
own pick, and one of them is a trap:

```
85785609|0|decision|4   decision  chosen=[0] correct=[0]   -> unstatable, exclude
83661652|0|decision|3   decision  chosen=[0] correct=[0]   -> unstatable, exclude
86088989|0|turn|0       turn      chosen=[]  correct=[]    -> a REAL decline, must survive
```

At `turn`/`match` scope `correct: []` **is** encodable and **is** a statable ruling that
`satisfies_human` grades exactly. `[] == []` makes the bare comparison true, so the unguarded
predicate the deploy sweep carried would swallow a live ruling. The sweep never hit it because it
only looked at deploy frames; a *shared* predicate must not have that hole, and the census is pinned
by a test so it cannot rot.

It is **not wired into `decider_lab`**. The Decision Gate has the same exposure on the two
`decision`-scope frames, but **which frames stop gating is a ruling, not a refactor** — wiring it
makes a `main` watchdog *quieter*, the one direction a gate must never move as a side effect of a
cleanup. Both gates' verdicts on `main` are bit-identical before and after this build. **Issue #251**
owns the decision, and argues LOW priority on purpose: the gap is DORMANT (ADR-0086 decision 9), can
only fire on a deliberate future flip, and fails loud and correctly attributed — whereas wiring it
wrong is unfalsifiable from outside.

Five modules leave `tools/train/probes/`; five stay, routed. The tree loses two things it should
never have had — a gate that could only report FIX, and the last hand-built frame key — and
`probes/` stops being a place where a dead instrument can sit looking alive.

Cost, stated: `ADR-0086`, `ADR-0076:235`'s slots numbers,
`ADR-0078` and several ADR references become historical rather than
live; if the denial lane reopens, its harness is rebuilt from ADR-0080 / ADR-0084's description
rather than edited. That is the trade this ADR takes deliberately — a stale harness is a trap, not a
head start.

## Alternatives rejected

* **Fix all ten loaders.** Satisfies ADR-0087 and leaves a gate that cannot go red plus two
  same-vs-same sweeps. Reading the corpus correctly is not the same as measuring something.
* **Keep the one-shots because the corpus may grow.** True of every probe ever written; under it the
  allowlist never empties. Corpus growth is handled *for the gates* — a frame absent from a frozen
  baseline is unbaselined, never a REGRESSION, and is absorbed at the next deliberate human
  re-capture. An instrument that must survive corpus growth becomes a gate (fate 1); one that does
  not becomes a ruling (fate 2). There is no third answer that keeps a script alive.
* **PR body as the record.** Reproduces the condition this ADR exists to end: nobody could say when
  or why the four sweeps went vacuous until someone measured.
* **Repair `threat_sweep --slots` into a real A/B** rather than delete it. Recreates an A/B for a
  decision ADR-0076 already made and shipped; if that swap is revisited, `sweep_rank` is the working
  template sitting in the same file.
* **Leave the enforcement at `tools/` and note the `tests/` family as known-and-unowned**, or
  allowlist the eleven against a follow-up issue. Both buy an empty dict at the price of the
  sentence being false — rejected for the reason decision 4 states.
