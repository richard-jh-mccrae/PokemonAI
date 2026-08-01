# ADR-0090 — A ruling names its record through a RESOLVER, and every surface prints that name

**Status:** Accepted (grilled 2026-07-31, `/grill-with-docs` on Issue #250 — four locked decisions
plus five side calls).
**Build = Issue #250.**
**Extends [ADR-0087](0087-a-corpus-reader-constructs-corrections-and-keys-by-identity.md)** (a corpus
reader constructs records and keys by identity — this rules on the *writer* and the *display*, the
two actors 0087 never faced) and **[ADR-0049](0049-corrections-carry-a-scope-decision-turn-or-match.md)**
(Correction identity = the Scope's subject, the vocabulary this preserves rather than migrates).
**Repairs the two defects [ADR-0088](0088-a-voided-ruling-leaves-the-agree-rate-and-the-gate.md)
decision 3a's `orphan_rulings` detector found.** Does **not** supersede anything.

**Context issues:** Issue #250 (this grill), Issue #239 / ADR-0088 (built the detector that found
these two, and established the void-and-re-capture protocol), Issue #241 / ADR-0087 (the same
hand-built-key defect one store over, on the reader), ADR-0049 (the three Scope key shapes).

> **Note on the issue body.** Issue #250 was filed with a body of literally `@-` — a botched
> `gh issue create -F body=@-`. The grill worked from the title, `gates.orphan_rulings`'s docstring
> and ADR-0088 decision 3a. Nothing was recalled; everything below was measured on HEAD (`4be1db3`).

## Context

`gates.orphan_rulings` reports every `data/corrections/reviewed.json` entry whose `review_key`
matches no committed **Correction** — a human ruling that rules on nothing. It found two. Both were
assumed to be stale rulings pointing at deleted records. **Neither is.** Both point at live,
committed Corrections, under the wrong name.

### Measured 2026-07-31, not recalled

**Orphan 1 — `85046350-10` (`covered`): the wrong EPISODE.**

```
reviewed.json reason:  "...decide() on f10 flips to [2] attach;
                        pinned by test_blunder_20260710_split_fixes.py::test_f10_"
that test loads:       tests/fixtures/corrections/dragapult_gust_wasted_in_setup_f10.json
                         chosen  [1]  Play Boss's Orders
                         correct [2]  Attach Basic {P} Energy -> Dreepy (active - 70/70)

record d374430e9bc7  =  episode 85045840, frame 10, wasted_resource
                         chosen  [1]  Play Boss's Orders
                         correct [2]  Attach Basic {P} Energy -> Dreepy (active - 70/70)
                         rationale: "Gusting up the Snover doesnt help us here..."

episode 85046350 frames present:  18 20 21 31 32 45 79 81 85     <- never a 10
both episodes live in the SAME file: data/corrections/dragapult_ex_20260709_e2f0a07-dirty/
true key 85045840-10 is FREE (only 85045840-8 is ruled)
```

**Orphan 2 — `86091435-119` (`refuted`): the wrong key SHAPE.**

```
record 948537a24fb2  =  episode 86091435, ANCHOR frame 119, turn 14
                         scope: "turn"   subject: 14          <- ADR-0049
                         review_key(c)  ==  "86091435-t14s0"  <- NOT "86091435-119"
                         chosen [3] Play Boss's Orders / correct [2] Play Night Stretcher
                         — the exact line the ledger entry's reason refutes
true key 86091435-t14s0 is FREE
```

### The root cause is the WRITER, and the report is its accomplice

`tools/train/review_correction.py:42` takes the ledger key as a bare `argparse` positional. It is
never derived from a record, never checked against the corpus. Its `--help` says
`"correction id: '<episode_id>-<frame>'"` — **decision shape only**, pre-ADR-0049 — and
`reviewed.json`'s own `_note` repeats it verbatim. An operator ruling a turn-scoped record follows
the documented shape and produces an orphan.

Worse, the operator did not invent `86091435-119`; they **copied it off the report**:

```
tools/train/tuner/report_md.py:31
    def _at(correction) -> str:
        return f"ep {correction.episode_id} f{correction.decision.get('frame')}"
```

`_at` is scope-BLIND and is used at lines 85, 112 and — pointedly — **123, the reviewed-entries
section**, so the report has been printing the broken ruling beside the anchor frame that broke it.
`_where(proposal)` *is* scope-aware but emits prose (`ep 86091435 turn 14 (seat 0)`), not a key. The
true key exists in exactly one place, `tuner/io.py:117,126` — a machine JSON snapshot no human reads.

Which makes `reviewed.py`'s docstring claim, repeated at `gates.py:847` —

> keyed by the Correction's **Scope subject** (*the same id the reports print*, `review_key`)

— **false**, and false in the one direction that manufactures orphans. This is ADR-0087 decision 2's
prohibition one store over: **a hand-typed ruling key is a hand-built key**, and it drifted
undetectably for the same reason 0087's did — nothing walked the join from the other side until
ADR-0088 built `orphan_rulings`.

### What the repair costs, measured against both baselines

| Frame Key | in baselines | today | after the re-key |
|---|---|---|---|
| `85045840\|0\|decision\|10` | both | gradeable, AGREE (`chosen [2] == correct [2]`) | **unchanged** — `covered` is non-voiding |
| `86091435\|0\|turn\|14` | both | gradeable; decider `chosen [3]` vs `correct [2]` = **fails**; leaf `correct_is_top` = **OK** | **VOIDED** |

So repairing orphan 2 moves both gates in opposite directions: the Decision Gate loses a frame the
agent currently fails (agree rate up), the Leaf Gate loses an OK (leaf rate down). That is exactly
ADR-0088's void-and-re-capture path, and it is the price of putting a real human refutation into
effect for the first time since 2026-07-19.

Repairing orphan 1 moves no gate. Its live consequence is elsewhere: `tune.py`'s
`partition_reviewed` has never excluded ep `85045840` f10, so a correction the human dispositioned
`covered` has re-surfaced as fresh work in every round since.

## Decision

### 1. Re-key both entries, and close the writer hole behind them

The rulings are sound; only their addresses are wrong. `85046350-10` → **`85045840-10`**;
`86091435-119` → **`86091435-t14s0`**. Neither target is occupied.

Deleting them was rejected: the refutation is cited by name in ADR-0066 and
`docs/plans/gusting-round0-measurement.md`, and destroying a correct human ruling because a key was
typo'd repairs nothing. Re-keying the data *alone* was also rejected — `orphan_rulings` is a
**detector**, and a detector plus a free-text writer means this repo's answer to "don't hand-build
keys" is "we will notice afterwards."

`tests/train/test_gates.py::test_the_committed_ledgers_orphans_are_the_two_that_are_known` changes
from asserting the known two by name to asserting **empty**. It also proves, in one assertion, that
all 145 committed entries resolve.

### 2. The writer RESOLVES a locator; it never accepts a key

`review_correction.py` stops taking a ledger key and starts taking a **Ruling Locator** — any of:

* the canonical `review_key` (`86091435-t14s0`)
* the **Frame Key** (`86091435|0|turn|14`)
* the `Correction.id` (`948537a24fb2`)
* the **anchor form** the report prints (`86091435-119`)

All four resolve to the one canonical `review_key`, which is what gets written. An unresolvable
locator **exits non-zero** with near-miss candidates.

`--remove` resolves identically **but falls back to the literal ledger key**, and the asymmetry is
deliberate. Removal is an operation on the *ledger*, so the ledger's own keys are a legitimate second
source for it — and a necessary one: resolving `--remove` against the corpus alone made the one entry
that most needs deleting, an **Orphaned Ruling**, un-deletable, since by definition no Correction
resolves it. (Also caught by `/code-review`'s Spec axis.) Resolution still wins where it succeeds,
which is what keeps the Anchor form working. **Recording admits no such fallback** — accepting a key
the corpus cannot reach is the free-text writer this ADR exists to remove.

A locator is not a relaxation of ADR-0087 decision 2 — it is that rule applied to the writer. The
key is still *derived from the record*; the operator merely supplies a way to find the record.

### 3. Near-misses are two deterministic rules, UNIONED, never fuzzy matching

* **same frame number under a different episode** → catches `85046350-10` → `85045840-10`
* **same episode, unknown subject** → the *generalisation* of "anchor↔Scope-subject translation".
  Orphan 2's literal spelling (`86091435-119`) now **resolves** via decision 2's Anchor form rather
  than being suggested — that rule succeeding instead of guessing — so the literal translation rule
  would be a branch that can never fire. What is left for it to catch is a locator naming a real
  episode and a subject nothing carries.

Both are read off the two real cases. Edit-distance/fuzzy suggestion was rejected outright: a
confident wrong suggestion that points at *someone else's human ruling* is strictly worse than no
suggestion, and the failure would be silent — a correctly-formed entry ruling on the wrong record,
which `orphan_rulings` by construction cannot see.

**The rules UNION; they never chain — and this was got wrong first.** Implemented as
``same_frame or same_episode``, rule 1 suppressed rule 2 whenever any *other* episode happened to
carry the same frame number. Measured on the committed corpus, `near_misses("86091435-120")`
answered `['82753102-120', '83667237-120']` — two unrelated episodes — while all eleven rulings in
the operator's **own** episode were hidden. That is the banned failure mode arrived at from the
other direction: confident, wrong, and concealing the right candidate. `/code-review`'s Spec axis
caught it; the stub test that first covered rule 2 had passed only because its fixture corpus
contained no other episode carrying that frame, i.e. the setup guaranteed its own result.

Rule 2's block is listed **first**, because getting the episode right is the stronger signal — the
operator was demonstrably reading that episode's report. And the *shape* is part of the safety
argument: several labelled candidates are a prompt to go and look, whereas one confident answer
invites a blind paste, so the rules widen the list rather than trying to pick a winner.

### 4. Every surface prints the ledger key

`report_md.py`'s `_at(correction)` returns `review_key(c)`. The docstring claim in `reviewed.py`
and `gates.py:847` becomes true rather than being deleted, and `reviewed.json`'s `_note` and
`review_correction.py`'s `--help` gain all three ADR-0049 shapes.

This is the half that makes decision 2 hold. A resolver alone would silently rewrite the operator's
input while the report kept displaying a different string — correct output, worse to debug than
either endpoint.

### 5. The resolver lives in `blunder/reviewed.py`, with the corpus INJECTED

```python
resolve_locator(locator: str, keyed) -> str | None
near_misses(locator: str, keyed) -> list[str]
```

`keyed` is `gates.keyed_corrections()`'s `[(Frame Key, Correction), ...]` — the same injected-corpus
shape `partition_reviewed(corrections, reviewed)` already uses.

`reviewed.py` owns `review_key`; **the inverse of a function belongs with the function**, or the two
drift — which is exactly what happened between `review_key`'s three shapes and the writer's
one-shape `--help`. `blunder/` never imports `gates` (the dependency runs the other way), so
injection is what keeps the layering one-directional, and it means the whole resolver tests against
a `tmp_path` corpus with no CLI in the loop.

Putting it in `gates.py` beside `orphan_rulings` was rejected — that puts an *authoring* path into
the module CI grades with. Putting it in the CLI was rejected as a second idea of what a ledger key
is, one layer above the second idea of a *record* that ADR-0087 was written about.

### 6. The ledger keeps ADR-0049's three key shapes — it is NOT migrated to Frame Key

Collapsing `reviewed.json` onto the gates' **Frame Key** vocabulary would delete the join outright,
and was seriously considered on exactly that ground. Rejected:

* With decision 2 in place both spellings already resolve to one canonical key, so the migration
  buys a join that is now derived *and* guarded by decision 1's test.
* It rewrites **145 committed human rulings** — a hand-curated record — for an internal spelling.
* ADR-0049's Scope subject is the right *human* id. A turn ruling reads as "turn 14, seat 0";
  `86091435|0|turn|14` is a machine key that reads as nothing.

Recorded explicitly because it is the decision most likely to be re-proposed by the next reader who
notices there are two vocabularies.

## Consequences

* **Both gate baselines must be re-captured by hand**, with the delta written into `docs/ci.md`'s
  log, per ADR-0088. `86091435|0|turn|14` leaves `gradeable` in both. **Never auto-recapture** — a
  baseline is a ruling record, and that is exactly how the old Decision Gate died.
* **`tune.py` stops re-surfacing ep `85045840` f10.** A `covered` disposition finally takes effect
  after ~3 weeks of the correction returning as fresh work each round.
* **`_at`'s output changes shape in every report**: `ep 85046350 f21` → `85046350-21`. Terser, and
  copy-pasteable into `review_correction.py`, but plans quoting the old prose form read as stale.
* **`review_correction.py` gains a corpus load** (~0.4 s) where it was a pure JSON edit.
* **No new CI gate.** `gates.orphan_rulings() == []` lives in `tests/train/test_gates.py`, which
  `ci.yml` already runs on every push. CLAUDE.md's two main-watchdog gates exist because *nothing*
  ran them on main; this runs.
* **`report.py:_entry_key`'s legacy `"<ep>-<frame>"` fallback is left alone** — documented, and
  measurably unexercised (0 of 17 committed tuner snapshot entries lack a recorded `key`, and 2
  already carry non-decision scopes).
* **Out of scope, deliberately:** whether a *turn-scoped* Correction should be graded by the
  Decision Gate at all (18 turn-scope rows sit in `data/decider_lab/baseline.json`). Pre-existing,
  untouched here, and a separate question from whether a ruling can find its record.
