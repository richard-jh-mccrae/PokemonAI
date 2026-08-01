# ADR-0087 — A corpus reader CONSTRUCTS Corrections and keys a frame by IDENTITY

**Status:** Accepted (grilled 2026-07-31, `/grill-with-docs` on Issue #241 — nine locked decisions,
one of them a mid-grill correction of an earlier one).
**Build = Issue #241.**
**Extends [ADR-0072](0072-mid-build-swaps-are-gated-by-deterministic-instruments.md) decision 4**
(the Held-out Ledger, whose "one ruling holds a frame out of BOTH gates" property this repairs) and
**[ADR-0049](0049-corrections-carry-a-scope-decision-turn-or-match.md)** (Correction identity = the
Scope's subject). Does **not** supersede anything.

**Context issues:** Issue #241 (this grill), Issue #238 (the 13 expired coverage claims — the
consumer of the widened corpus), Issue #239 (label moves the diff cannot report — same blindness
family), Issue #228 (the frame that exposed it), PR #227 (introduced the instrument), PR #236
(ADR-0085 Amendment J, left it unchanged), ADR-0082 (a ruling lives in its Claim), ADR-0085
Amendment I (the Decision Gate's rebuild against a recorded baseline).

## Context

`tools/train/decider_lab.py` — the Decision Gate that `decider-gate-main.yml` runs on every push to
`main` — read the corrections corpus through its own raw-JSONL loop instead of through
`train.blunder.store.load_corrections`, and built its frame key by hand out of raw dict lookups
instead of through `Correction.identity_key`. Both shortcuts were wrong, and the second was the
larger error.

### Measured 2026-07-31, not recalled

```
raw records in data/corrections/:                                     372
  the gate's _records() saw:                                          332   (-40)
  every one of the 40 is  data/corrections/mega_starmie_20260627_93a70be/
  each carries  agent: ""  plus a populated  agent_build  -> recoverable

decision snapshot keys: ['current','frame','options','select_context','select_type','turn']
  `seat` is TOP-LEVEL on the record.  `_key` read  decision.get("seat", 0)  ->  ALWAYS 0.

data/decider_lab/baseline.json  seat distribution:   {0: 332}
true corpus                     seat distribution:   {0: 201, 1: 171}

so, over the true 372-frame keyspace:
  keys the committed baseline names CORRECTLY:      169  (45%)
  mis-keyed (seat, and scope/subject for 19):       163
  absent entirely:                                   40
```

`_key` also passed the literal `"decision"` as scope and the Anchor `frame` as subject; 19 records
are `turn`/`match` scope, whose identity under ADR-0049 is the Scope's subject, not the frame.

### The consequence that was live in CI

```
held-out rulings (ADR-0072 decision 4):  11
  reachable by the Decision Gate:         7
  UNREACHABLE:                            4
    82756664|1|decision|97   seat-1 key; the gate's keyspace is entirely seat-0
    85163634|1|decision|41   same
    85164605|1|decision|41   same
    85785609|0|turn|8        turn-scope key; the gate files it as decision|82
```

ADR-0072 decision 4 states that one ruling holds a frame out of both gates. For 4 of 11 that was
false. Any of those four flipping to `REGRESSION` would have **failed `main`** against a standing
ruling — the opposite of the "silently held out" failure the ledger was built to prevent, and just
as bad.

### It is not the second loader — it is the twelfth

```
raw-JSONL readers carrying the identical `v.get("obs") and v.get("agent")` filter:  11
  attach_decider_sweep   budget_sweep   deny_gate1   deny_gate217   deploy_anchor_sweep
  deploy_decider_sweep   evolve_decider_sweep   needs_sweep   promote_retreat_decider_sweep
  snipe_decider_sweep    threat_sweep
```

Every one is short the same 40 records. `tools/sim/score_diff.py` globs raw but goes through
`Correction.from_dict`, so it is clean. Four of the eleven are the `*_decider_sweep.py` that
ADR-0085 Amendment I declared **vacuous and replaced** — for those, "fix the loader" is likely the
wrong answer and deletion the right one.

### A ruling can move and NO instrument can report it

Found while chasing an apparent count mismatch (the baseline shows 11 `correct: []` rows where the
store has 10). The extra row is `85709280`:

```
baseline row  85709280|0|decision|51   correct: []    chosen: [0]
store record  85709280|1|match|        correct: [0]   scope: match
```

`git show e50735a:` — at the baseline's own commit the record read `correct: []`. It was **re-ruled**
2026-07-29 in `b6d7483` (ADR-0081 Amendment D): *"recorded `correct: []` at a minCount-1 Main select:
degenerate, ungateable... Re-ruled with the user on the pulled-up board state to `correct: [0]`."*
That commit reached `main` by a merge after the capture.

`decider_lab_diff` reads `correct` from the **after** side and emits a row only when `chosen` moves.
Here `chosen` is `[0]` on both sides, so the frame produces **no row at all** — while its verdict
silently flips from unsatisfied to satisfied and the headline moves `230 → 231` with no decision
changed. `leaf_lab_diff` has the identical blindness: it compares `correct_is_top`, which is computed
*from* `correct`. Neither `added` nor `removed` can see it, because the frame exists on both sides.

This is Issue #239's family — *a thing that moved that the instrument cannot report* — reached from a
different direction.

### Two claims this grill made and then RETIRED against measurement

Recorded because both were plausible and both were wrong, and the ADR should not read as if the
first guess held.

- **"An empty `correct` is a free pass that inflates the agree rate."** False.
  `gates.satisfies_human` already special-cases it: `if not correct: return not chosen` — a recorded
  **DECLINE**, matched exactly, built deliberately by ADR-0085 Amendment J. `230/331` is honest, and
  a scope-aware labelling rule would have **removed 10 standing DECLINE rulings from the gate**.
  Measured: 1 of the 11 baseline DECLINE rows is satisfied, and re-running `satisfies_human` over the
  committed rows reproduces `230/331` exactly.
- **"The two loaders' dedup tie-break keeps a different record."** False.
  `load_corrections(dedup=False)` and `dedup=True` both return **372**; zero keys carry more than one
  record. The dedup rule is entirely inert on today's corpus, so the ruling comment's *"one real
  behavioural decision"* moves nothing — it matters only as a forward contract.

One casualty worth naming: `satisfies_human`'s own docstring cites this DECLINE frame as
`86088989|0|decision|3`. That is the **buggy** key — its true identity is `86088989|0|turn|0`. The
wrong keyspace has already leaked out of `decider_lab` and into an ADR-backed docstring, which is the
clearest possible argument that a hand-built key is not a local defect.

### Two facts that made the repair tractable

```
collisions on (episode, anchor frame) across all 372:                  0
old baseline rows joining uniquely to the store on that pair:    332/332   (0 multi, 0 miss)
distinct new keys produced by that join:                             332   (0 collisions)
after re-key, the widening reads:                            added 40, removed 0

leaf_lab baseline keys absent from the TRUE decider keyspace:          0
```

So the re-key is total and injective, the widening is separable from it, and once both land the
decider corpus properly **contains** the leaf corpus — which is what ADR-0085 Amendment I put the
two gates side by side to guarantee.

## Decision

**1. A corpus reader CONSTRUCTS `Correction` objects.** Any code reading `data/corrections/` goes
through `train.blunder.store.load_corrections`. No second raw-JSONL walk. This is what inherits the
`agent_build` backfill in `Correction.from_dict` — and, more to the point, every future
normalisation, for free and in both gates at once. The bug was never the falsy `agent` check; a
falsy check is a symptom that a second idea of "what a record is" exists.

**2. A frame key is `frame_key_of(*identity_key(c))`. Never hand-built.** `gates.frame_key_of`'s
docstring already claimed to be "THE one place that shape is built"; `decider_lab._key` falsified
that claim one module over, and the falsification was invisible because both sides of a diff shared
the same wrong key. A hand-built key from raw dict lookups is decision 1's second loader, one
function lower. `decider_lab._key(c)` and `leaf_lab.frame_key(c)` must be byte-identical, and a
test asserts it directly rather than a docstring asserting it in prose.

**3. No scope FILTER, and NO new labelling rule — `satisfies_human` already IS the contract.**

The gate replays all 372 records, unfiltered. *"The gate's corpus equals the store's replayable
set"* is the invariant decision 4's test asserts, and a scope filter would force that test to encode a
second hand-maintained rule for a third divergence to hide behind.

⚠️ **This decision replaces a wrong one made earlier in the same grill.** The first version added a
scope-aware `is_labelled` predicate on the premise that an empty `correct` was a vacuously-agreeing
free pass. It is not — `gates.satisfies_human` special-cases it as a recorded **DECLINE**, matched
exactly (ADR-0085 Amendment J), and the rule would have removed **10 standing DECLINE rulings** from
the gate. The three labelling cases are already defined in exactly one place, are already
ADR-backed, and are already right:

| case | meaning | treatment |
|---|---|---|
| `chosen is None` | the frame could not be replayed | satisfies nothing |
| `correct is None` | no ruling was recorded | `UNLABELLED`, never gates |
| `correct == []` | a recorded **DECLINE** — *"take none of these"* | matched EXACTLY; labelled and gated |

So `decider_lab` adds no labelling concept. Writing one would have created a second authority over a
question decision 1 exists to keep singular — the error this record argues against, committed inside
the record itself.

The one record that *looked* like a scope violation — `85709280|1|match|` carrying `correct: [0]`,
which `build_correction` refuses to construct — is not a defect in the `correct` field. It is a
deliberate human re-ruling (`b6d7483`, ADR-0081 Amendment D) filed under the wrong **scope**: the
commit describes *"a minCount-1 Main select"*, i.e. one Decision. It is routed as a corpus **re-tag**
to `decision` scope with `subject: 51` — a ruling-record edit that changes its Frame Key, so it
belongs with the user as its own act, not folded silently into this PR (decision 5). Until then it
keeps a `match|` key no fixture or ledger entry can usefully join against.

**4. The contract is ENFORCED by an allowlist test, and an allowlist entry must name a live issue.**
A test walks `tools/**/*.py` for raw `corrections.jsonl` globs outside the store module and fails on
any file not on a named allowlist. The eleven known readers go on it, each tagged with the follow-up
issue; `decider_lab.py` leaves it in this PR. A twelfth reader cannot appear silently. An untagged
or stale entry rots exactly the way `reviewed.json`'s `covered` claims did (Issue #238), so the
issue reference is part of the entry, not a comment on it.

The eleven are **not** bulk-fixed. The follow-up asks fix-or-delete per reader, because for the four
replaced sweeps the honest answer is deletion and a loader swap would be investment in a retired
instrument.

**5. A mechanical re-key of a committed baseline is a TRANSCRIPTION, not a re-blessing.** The
landing is two commits, in one PR so `main` never sees the intermediate:

- **A — relabel.** Rewrite only the `key` field of the 332 committed rows, joining to the store on
  `(episode, anchor frame)` (proven unique above). No Pilot runs; `chosen`, `correct`, `agent`,
  `context`, `error` and every summary field are untouched, so a reviewer confirms it is a relabel
  by reading the diff. This is where the four detached rulings reattach — ahead of any corpus
  change, so the two effects are separable in history.
- **B — widen.** Land decisions 1–3 and re-capture. `decider_lab_diff` against A reports
  `compared: 332, added: 40, removed: 0`. Any row whose `chosen` actually moved is a genuine flip
  and is ruled with the user before the capture is committed.

Hand-editing a ruling record is permitted **only** in this shape: correcting the *name* of a frame a
human already ruled on. Re-capturing what the agent DECIDES stays a deliberate human act after the
flips are ruled — the discipline `decider-gate-main.yml` and `data/leaf_lab/` already carry, and the
one whose absence made the old sweeps vacuous.

**6. Whoever moves an instrument owes the corrected reading; a RULING belongs to its chartered
issue.** This issue re-derives every *number* over the full 372 — the capture's own summary,
`docs/plans/decider-disagreement-triage.md`'s totals (dated, not overwritten, matching how that doc
already records `220/331 → 230/331`), and Issue #238's Tier B candidate join. It adjudicates no
frame. Opening each newly-surfaced candidate with `frame_view.py` and ruling it right-or-wrong is
Issue #238's charter, and the new rows land there labelled as unadjudicated candidates.

**7. A moved RULING gets its own report channel, shared by both gates, never gating.**
`gates.ruling_moves(before, after)` returns every frame present on both sides whose `correct` changed
under `picks_as_set` — emitted **independently of whether `chosen` moved**, which is the whole bug:
today an unchanged `chosen` produces no row, so the move is invisible. Both `decider_lab_diff` and
`leaf_lab_diff` return it and both reports print it beside the existing `⚠️ corpus shape moved` line.

It sits next to `added`/`removed` because it is the same idea one level in — those report a frame
appearing or leaving, this reports the *ruling* about a frame moving — and the module's stated
doctrine is that a corpus-shape move must never read as a quiet green. It **never gates**: a
re-ruling is a deliberate human act, not an agent regression. `decision_gate_verdict` and
`discrimination_gate_verdict` are untouched.

Shared, not per-gate, for decision 2's reason: the Discrimination Gate has the identical blindness
(`leaf_lab_diff` compares `correct_is_top`, computed *from* `correct`), and a second implementation
would drift. `85709280` (`[] → [0]`) is the worked first case the test asserts on.

Without this, Q5's re-derived numbers cannot separate *"moved because the corpus widened"* from
*"moved because a ruling changed"* — the separability decision 5 exists to protect.

`82225643-11` is the worked example: closed in `reviewed.json` as `covered` with the note
*"retest [1]→[0]=correct"*, while the shipped Pilot returns `[3]` Play Crushing Hammer. It is not a
regression the widening causes — it is a pre-existing disagreement no gate could see, and it belongs
to Issue #238's Tier B once that count is re-derived.

## What the build measured (2026-07-31)

Every prediction in decisions 1–7 held, and the two commits landed as specified.

```
decider corpus                332 -> 372      added 40, removed 0
held-out rulings reachable      7 -> 11        (of 11)
agree                     230/331 -> 253/371
leaf frames outside the decider keyspace:  0
both gates:  Decision PASS (372 compared, 0 unruled) · Discrimination PASS (268, 0 unruled)
```

**The relabel was provably a relabel.** 163 of 332 keys changed; the diff is 163 lines and
`git diff -U0 | grep -v '"key"'` is **empty**. Independently re-confirmed downstream: Issue #238's
Tier B join computes to **28** on both the original capture and the relabelled one — a re-key that
moved a ruling would have moved that number.

**The widening's effect is fully attributed**, which is what decision 5's sequencing bought:

```
Tier B:  43  =  28 (as published)  +  14 (frames the 332 could not see)  +  1 (agent drift)
                                                                            0 resolved
```

**`ruling_moves` fired on its worked case on the first real run** — `85709280|1|match|`,
`correct [] -> [0]` — a frame the agent plays identically, which produced no diff row at all before
this existed.

**Two `chosen` moves were ruled before the capture was committed** (decision 5), neither caused by
this work — 24 commits touched `src/` between `e50735a` and now, and `_build_pilot` is uncached so
the reader's new key ordering cannot move a decision:

| frame | move | verdict | disposition |
|---|---|---|---|
| `86090147\|0\|decision\|22` | `[4] -> [6]` | NEUTRAL (human ruled `[7] Retreat`) | absorbed; candidate for Issue #238 |
| `83661652\|0\|decision\|44` | `[2] -> [0]` | REGRESSION | held out to Issue #165 |

### Two defects found while landing, fixed here

Both are the same class as the issue itself — a committed artifact that silently depended on who
produced it.

* **`write_text` wrote the re-captured baseline as CRLF.** Both committed baselines are LF, dev is
  Windows and the grader is Linux, so a 40-row change appeared as a **4835-line whole-file rewrite**
  — burying the only thing a reviewer of a re-capture needs to see. `gates.write_json_artifact` is
  now the single LF-framed writer behind all four capture/verdict sites across both labs.
* **The capture embedded an absolute path** in the one unreplayable frame's error
  (`/home/user/PokemonAI/...` from the Linux capture vs `C:\Users\...` from a Windows one), so the
  same build re-captured elsewhere produced a different committed ruling record. Now repo-relative.
  The bug survived because the path arrives already repr-escaped, so matching `str(REPO)` against
  the raw text silently fails on Windows — the normalisation has to precede the strip.

### One decision the build revisited

`frame_view.py` was to be *"audited and either cleaned or listed"*. Audited: it re-parsed raw JSON,
so all 40 records rendered with a **blank agent** — a real user-visible defect, not a latent one.
Cleaned rather than listed. `82225643-11` now reads `agent mega_starmie`. Cleaning it needed
`store.jsonl_files` made public, which turned out to be overdue anyway: three modules were already
reaching into the private `_jsonl_files`, and `tools/sim/score_diff.py` was the instructive
near-miss — it CONSTRUCTED its records correctly while still globbing for the files itself, i.e.
decision 1 satisfied and the corpus *layout* still duplicated. Both halves come from the store.

## Consequences

- **The agree rate moves for TWO independent reasons and decision 7 is what separates them.** The
  corpus widens by 40 frames, and at least one ruling has moved since the capture (`85709280`,
  `230 → 231` on its own). Without the ruling-move channel the re-derived headline is a single number
  with two causes and no way to attribute either.
- **`reviewed.json` is a third key shape** — `episode-frame`, no seat, no scope. On today's corpus
  that join is unambiguous (0 collisions on `(episode, anchor frame)`), but by property of the data,
  not by construction. Recorded as a named residual; a schema change there belongs with Issue #238
  item 4 / Issue #229's neighbourhood, not here.
- **Eleven readers stay wrong, on the record, for a while.** That is the deliberate cost of decision
  4 over a bulk fix.
- **The two gates can finally be joined.** All 277 leaf frames are a strict subset of the true 372,
  so a frame ruled once is held out of both, and a claim measured against one is quotable against
  the other.
- **`gates.satisfies_human`'s docstring must be corrected** — it cites the DECLINE frame as
  `86088989|0|decision|3` (the buggy key; true identity `86088989|0|turn|0`) and states the corpus
  holds eleven DECLINE rulings, which is the mis-keyed baseline's count. The corpus holds **10**, all
  `turn` scope. Fixing prose that quotes a wrong key is part of fixing the key.
- **One corpus record needs a scope re-tag** (`85709280`, `match` → `decision|51`), which is a
  ruling-record edit and stays outside this PR per decision 5.
- **A Held-out ruling can shelter a regression it was never ruled against.** `83661652|0|decision|44`
  regressed *after* the ruling that holds it out, and the gate excused it automatically — correctly
  by ADR-0072 decision 4 as written, and still worth knowing. The ledger records *"this frame is out
  of this decider's scope"*, not *"this frame may degrade without limit"*, and nothing distinguishes
  the two today. Named here rather than fixed: it is a general property of decision 4's design, not a
  fact about this frame, and reddening `main` mid-landing would have been the wrong instrument for
  it. A candidate shape, if it is ever worth closing: record the held-out frame's *verdict at ruling
  time* alongside the owner, so a further degradation is reportable even while the frame stays
  ungated — the same move `ruling_moves` makes for a corpus whose ruling shifts.
