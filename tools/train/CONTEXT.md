# Training (`tools/train/`)

Offline tooling that turns downloaded **Replays** into curated learning signal. Its first
component is the **blunder inspector** (`blunder_correction`): it replays an Episode in the
official cabt viewer and lets a human mark a blunder, emitting a **Correction**. The **Tuner**
(Job A, planned) and the **Automatic Value Trainer** (Job B, `tools/train/value/`, built)
([ADR-0009](../../docs/adr/0009-training-methodology.md)) are its two sibling training jobs —
distinct mechanisms (see those terms below), both offline.

Shared vocabulary — **Correction** is defined in the
[Agent Runtime](../../src/common/CONTEXT.md) context and reused verbatim; **Replay**,
**Episode**, **Archetype** come from the [Meta Tracker](../../CONTEXT.md) context. Game-rule
terms follow the enums in `src/cg/api.py`.

## Language

**Decision**:
One `select` the cabt engine presents at a single step — the agent picks option index(es)
from `select.option` under a `SelectContext` (`MAIN`, `SWITCH`, `DISCARD`, attack-target, …).
The **atomic unit** of the game: `chosen` and `correct` are option choices *at one Decision*.
A Correction's **Scope** says how many Decisions it is *about*; `chosen`/`correct` always
index the **Anchor** Decision's options, never a later one.
_Avoid_: move / play (human-level, may span several Decisions), turn (a **Turn** is many
Decisions — see below), step (the replay timeline index, not the choice itself)

**Turn**:
One *ply* — a single seat's turn, numbered by the film's `current.turn`. For `turn ≥ 1`
exactly one seat acts, so the number identifies the actor; **`turn 0` is the shared setup
phase** and both seats act in it, so a Turn is keyed by `(episode, seat, turn)`.
_Avoid_: round (both players), step, frame

**Scope**:
What a Correction is *about* — `decision` (one Decision), `turn` (every Decision that seat
made in one Turn), or `match` (the whole Episode from that seat). Orthogonal to **Category**:
scope is the *size* of the blunder, category is its *kind*.
_Avoid_: granularity, grain, level, tier (Tier means the Pilot's search tier)

**Span**:
The ordered Decisions a Correction's Scope covers — one for `decision` scope, a Turn's
Decisions for `turn`, the seat's whole Episode for `match`. Embedded in the record, so a
scoped Correction survives replay deletion like an atomic one.
_Avoid_: line (a **planner's** committed line — `planned.next_step`, evolution line), window,
sequence, range

**Anchor**:
The single Decision the human tagged a Correction *from* — the point they were looking at.
It carries the record's embedded state and, when a `turn`-scoped Correction names a `correct`
option, that option indexes the **Anchor**'s `select.option` (asserting the Anchor is the
*first divergent Decision*). **Provenance and context, never identity**: a Correction is keyed
by its Scope's subject, so the same Turn tagged from two frames is one Correction.
_Avoid_: pivot, mark, point, frame (the film index, not the Decision)

**Category**:
The **human** axis of a Correction — *what kind* of mistake the blunder is, picked from a
closed, extensible vocabulary (`missed_win`, `overextension`, `misattachment`, …).
**Mandatory**; the dimension the trend report buckets by. Strategic, not mechanical (the
engine `SelectContext` is captured separately as metadata). Extended by process, like
**Role** / **Plan**.
_Avoid_: type (too generic), blunder type, tag, label

**Attribution**:
The **machine** axis of a Correction — *which tunable surface* the blunder blames
(`hypothesis:<id>`, `missing_hypothesis`, `tactical`, `value`, `scouting`). **Derived, never
hand-written**: the tuner replays the Pilot on the Decision and diffs which Hypotheses fire
for `correct` vs `chosen` — they differ → those Hypotheses (a weight fix); identical → no rule
discriminates (`missing_hypothesis` → author a new rule); the gap is combat → `tactical`. The
bridge from a blunder to *where the fix lands*, and the **W-vs-H router** (Job A).
_Avoid_: cause, blame, Category (that is the human axis)

**Source**:
Whose game a Correction was marked in — `own` (a game our submission played; the *gold*,
targeted signal) or `peer` (another team's game of our deck; *expertise injection*). Per
[ADR-0009](../../docs/adr/0009-training-methodology.md). The trend report's "my agents over
time" view is the `own` pile; `peer` Corrections are training data shown separately.
_Avoid_: origin, owner

**Tuner**:
The offline component (`tools/train/`, planned) that compiles the **Correction** log into agent
improvements. It derives each Correction's **Attribution** (replaying the Pilot on the embedded
`obs`), then *fans out*: `hypothesis:<id>` → a Tier-0 weight override (`tuned.json`);
`missing_hypothesis` → a proposed new **Hypothesis** (assisted, human-committed); plus a Hypothesis
**status** transition. **Job A** of [ADR-0009](../../docs/adr/0009-training-methodology.md); designed in
[ADR-0017](../../docs/adr/0017-corrections-compile-to-hypotheses.md). Its input is **human-tagged**
Corrections, never game outcomes — it trains the **rules** (`tuned.json`).
_Avoid_: weight-tuner (too narrow — it also authors Hypotheses), Automatic Value Trainer (Job B, the value model)

**Automatic Value Trainer**:
The offline trainer (`tools/train/value/`) that fits the **Automatic Value Model** — the
`state → P(win)` evaluator — by supervised gradient descent on mined **Self-Play** states (label =
the game's eventual winner). **Job B** of [ADR-0009](../../docs/adr/0009-training-methodology.md)
(ADR-0042). The counterpart to the **Tuner** (Job A), and the two disambiguate the overloaded word
*training*:
- **Tuner (Job A)** — input is **human Corrections**; output changes the **rules** (`tuned.json`);
  manual, correction-driven.
- **Automatic Value Trainer (Job B)** — input is **game outcomes** (W/L) as automatic labels; output
  changes the **Automatic Value Model** (`value_model.json`), a tie-break leaf that only *advises*
  the rules; automatic, supervised.
Neither is RL: Job A never reads outcomes, and Job B trains an **evaluator that never becomes the
policy** — so a win never auto-rewrites a rule weight (the ADR-0007 line). Its data is Self-Play (the
ladder film is discarded, ADR-0002).
_Avoid_: RL / self-play trainer (the rejected outcome→policy loop — this is outcome→evaluator), Tuner
(Job A, the rules), fine-tuning (ambiguous — say which Job)

**Verifier**:
The deterministic accuracy gate for an authored **Hypothesis**: inject the candidate (its
`when()` trigger + a seed weight), re-run the **Tuner**'s weight fit over all **Corrections**,
and accept only if it satisfies its target cluster (`correct ≻ chosen`), regresses none that
were previously satisfied, and keeps the test suite green. What makes an LLM-authored trigger
trustworthy. See [ADR-0017](../../docs/adr/0017-corrections-compile-to-hypotheses.md).
_Avoid_: validator, checker, test

**Leaf Lab**:
The offline instrument that re-scores a **Leaf Frame**'s board through `_engine_leaf_value` — once
per menu option — and reports whether the leaf ranks the human's `correct` option top
(`tools/train/leaf_lab.py`). cgpy-backed and **deterministic** (`SeededRng(0)`), so two builds
measured over the same **Corrections** store differ by exactly the code between them: no sampling,
no confidence interval, ~20 min per arm over 267 scorable frames. This is what the **Discrimination
Gate** (see [Agent Checks](../sim/CONTEXT.md)) captures before and after a **Mid-build Swap**.
It measures the *leaf's ranking*, **not the shipped decision** — a `MISS` says the end-of-turn board
evaluation buries the human's option, not that the live agent played the frame worse.
_Avoid_: leaf test, leaf eval, leaf benchmark (it is an instrument, and its readings are rankings)

**Decider Lab**:
The Leaf Lab's sibling one level up: it replays every replayable **Correction** through a fresh
shipped Pilot and records what the agent **DECIDES**, then diffs that against a committed capture
(`tools/train/decider_lab.py`, `data/decider_lab/baseline.json`). Where the Leaf Lab asks *does the
leaf RANK the human's option top*, this asks *does the agent PLAY it* — the end-to-end reading, and
the one a ladder actually sees. Since ADR-0085 Amendment I it **is** the **Decision Gate**.

It exists because the gate's old reference rotted silently. ADR-0072 named each phase's
`*_decider_sweep.py`, and every one of those compared the agent against its own kill-switch OFF —
correct at the swap, when OFF was the incumbent rung pile, and meaningless once each phase DELETED
that pile as directive 1 requires. `baseline_promote` was left holding **zero** rungs. With no
incumbent, OFF is an empty scorer whose argmax is option index, so all four sweeps compared their
equation against nothing and **could only ever report FIX**. They reported `PASS` throughout.

The lesson is one line, and it is why this instrument has the shape it has: **a gate must diff
against a RECORDED baseline, never against a live switch.** The baseline is a RULING RECORD — never
auto-recaptured, re-taken only once a build's flips have been ruled, exactly as `data/leaf_lab/`.
Since ADR-0085 Amendment J it is watched on `main` by `.github/workflows/decider-gate-main.yml`, and
the four `*_decider_sweep.py` have lost the dead OFF arm entirely — they are per-leg diagnostics that
report and exit 0.

**A green Decision Gate means nothing REGRESSED. It does not mean the agent is right** — the baseline
records every frame it captured as the reference, including the 101 where the agent contradicts a
human ruling (`docs/plans/decider-disagreement-triage.md` tiers them).

⚠️ Its corpus is **372** frames, not the 332 the pre-ADR-0087 capture reported, and the 101/331
figures are readings of that reduced, mis-keyed set. It is a **Corpus Reader** and bound by that
term's rules — the defect Issue #241 fixes was one raw-JSONL walk plus one hand-built key, which
between them left only 169 of 372 frames correctly named and put 4 of the 11 **Held-out Ledger**
rulings out of the gate's reach entirely.
_Avoid_: decision test, decider suite, regression run (it is an instrument; its readings are picks)

**Satisfying a Correction**:
What it means for a pick to match a human ruling: `correct ⊆ chosen`, never `correct == chosen`
(`gates.satisfies_human`, ADR-0085 Amendment J). A Correction's `correct` names **the card the ruling
was about**; a multi-pick select returns **every** index the engine demands, so the two are different
vocabularies and equality across them mis-reports — it scored `DISCARD` at 1/12 where satisfaction
reads 10/12. One exception, and it is load-bearing: `correct: []` is a recorded **DECLINE**, matched
EXACTLY, because the empty set is a subset of everything and subset-reading it would make every frame
vacuously agree. Both the Decision Gate's direction test and its agree-rate readout key on this one
predicate, deliberately, so they cannot drift apart.
_Avoid_: "the agent agrees with the correction" as a synonym for equality — say **satisfies**

**Corpus Reader**:
Any code that reads `data/corrections/`. Under **ADR-0087** (Issue #241) it **constructs**
`Correction` objects via `train.blunder.store.load_corrections` and derives every **Frame Key** as
`frame_key_of(*identity_key(c))` — never a raw-JSONL walk, never a hand-built key. Both shortcuts are
the same defect: a *second idea of what a record is*, which is what silently cost the **Decision
Gate** 40 records (an empty `agent` is *recoverable* from `agent_build`, and only `from_dict`
backfills it) and mis-keyed 163 more (`seat` is top-level, so `decision.get("seat", 0)` was always
0). Enforced, not asserted: a test fails on any raw `corrections.jsonl` glob outside the store module
that is not on an allowlist, and an allowlist entry must name a live issue.
_Avoid_: loader (fine in prose, but the noun that matters is *what it constructs*), parser, corpus
walk (**`iter_keyed_fixtures`** is the *fixture* walk — a different corpus)

**Ruling Move**:
A frame present in both captures whose **Correction**'s `correct` CHANGED between them — the human
re-ruled (`gates.ruling_moves`, ADR-0087 decision 7). Reported by both the **Decision Gate** and
the **Discrimination Gate** beside `added`/`removed`, and **never gating**: a re-ruling is a
deliberate human act, not an agent regression. It exists because both diffs emit a row only when
`chosen` (resp. `correct_is_top`) moves, so a re-ruling on a frame the agent plays identically
produced **no row at all** while silently changing that frame's verdict — `85709280` went `[] → [0]`
in `b6d7483` and moved the headline `230 → 231` with no decision changed. The same blindness family
as Issue #239. Distinct from `added`/`removed`, which report the *frame* appearing or leaving; this
reports the *ruling about* a frame moving.
_Avoid_: re-rule (the human act — this is the instrument's report of it), label change (a
**Correction**'s `correct` is the ruling, not a label), corpus drift (that is `added`/`removed`)

**Ruling Index**:
The ONE query that spans every store a ruling can live in — `gates.ruling_index()`, `{Frame Key:
Ruling}` (**ADR-TEMP-239**, Issue #239). Built on `keyed_corrections`, so the `review_key` ↔ **Frame
Key** join is *derived per record inside the one walk* (ADR-0087 decision 2) — both keys come off
the same `Correction`, neither derives from the other, so the walk is the only honest join point. It
merges `data/corrections/reviewed.json` and the **Held-out Ledger**; `RECORDED_MISSES` is retired
into them rather than read as a third source. Read-only: no **Correction** record is ever rewritten.
Exists because a frame could be ruled four different ways and still read as unreviewed —
`81905522-75` and `82749168-38` carry the same ADR-0085 ruling and were triaged Tier C vs Tier A
purely by which store held them.
_Avoid_: ledger (the **Held-out Ledger** and `reviewed.json` are *stores*; this is the index over
them), registry, disposition map (it returns a **Ruling**, not a string)

**Ruling** / **Voided Ruling**:
What the **Ruling Index** returns for one frame: the raw `disposition` plus its `source`
(`reviewed` / `held_out`, extensible) and `reason` — and one DERIVED predicate,
`gates.voids_the_label`. A **Voided Ruling** is one where that predicate is true: `refuted` (the
ruling is disowned) or **Transposition** (the ruling stands but cannot grade). Consumers key on the
predicate, **never** on the disposition string, so the vocabulary can grow without every grader
re-learning it — `reviewed.json` already carries `fixed` and `deferred-multi-turn`, neither of which
`DISPOSITIONS` lists, so that drift is measured rather than hypothetical. An unrecognised disposition
is non-voiding and **surfaced loudly** in both gate readouts. Precedence when two stores hit one
frame: **any voiding source wins**; all matches are kept so the readout can name every store.
A voided frame leaves the agree-rate DENOMINATOR (`agree / (labelled − voided)`) and is held out of
gating — reported, never failing `main`, the same treatment ADR-0072 decision 4 gives a **Held-out
Frame**, for a different reason. `satisfies_human` is NOT touched; only what the callers count.
_Avoid_: refuted (one of two voiding dispositions, not the category), excluded / skipped (it is still
read and still printed), disagreement (a voided frame is neither agreement nor disagreement)

**Transposition**:
A disposition (**ADR-TEMP-239** decision 6): the human's ruling is correct, but its `correct` names
one of an **indistinguishable** set of options, so no agent can be scored on picking "the right one".
Voiding, for a different reason than `refuted` — and the distinction is load-bearing, because
ADR-0085 decision 4 cites `81905522-75`'s pick (two identical Riolu, no board signal splits them,
design-doc R3) to justify leg-scoped rather than whole-target guards. Filing it `refuted` would write
an assertion into the ledger that a shipped ADR contradicts. Only the *instance* is handled; making
`satisfies_human` transposition-AWARE (an equivalence class over options, so either pick satisfies)
is **Issue #247** — it needs an indistinguishability oracle read off `obs`, which is a
board-reading problem, not a corpus-record one.
_Avoid_: tie (the scores tying is the symptom; the cause is the options being the same), ambiguous
label, refuted

**Agree Delta**:
The aggregate half of the **Ruling Move** fix (**ADR-TEMP-239** decision 7): `agree_delta` on both
diffs — `{before: (agree, denom), after: (agree, denom), moved, reruled, voided}` — printed by one
shared printer beside `print_ruling_moves`, so the two gates cannot describe it differently. It
exists because offsetting moves can present as stillness: `230/331 -> 230/331` was printed while
three rows moved, one re-ruling exactly cancelling one held-out regression. Deliberately COUNTS, not
a causal decomposition — a frame can be re-ruled, voided and moved at once, so no point of the delta
has a single honest owner, and a confidently-wrong instrument is this module's expensive failure.
_Avoid_: attribution / breakdown (rejected — it claims causality this does not), summary line

**Leaf Frame**:
A **Correction** the **Leaf Lab** can score: a reseedable MAIN-select (context 0) board carrying
something to rank — either a `turn_plan` payload or any MAIN-select pick correction naming a
`correct` option (`is_leaf_frame`). Non-MAIN and obs-less records are excluded because the offline
sim reseeds only from a MAIN-select board. 276 today, of which 267 are *scorable*.
_Avoid_: frame (bare — that's a replay timeline index), fixture (a committed corpus pin under
`tests/fixtures/corrections/`), leaf case

**Endorsement Claim**:
The third thing a fixture can assert (ADR-0072 amendment A): *this slot is (or is not) taken at all*,
evaluated against `score > 0` — the endorsement floor `_finish_turn_last` gates on. It exists for the
**single-option lane**, where an ordering claim has nothing to rank: f35 carries exactly one evolve
option, yet the 1b swap's real fix there is that the premature evolve went 45.0 → **0.0 with no rule
firing**. Zero is a *structural* boundary (act / don't act), not a tuned magnitude, so it survives a
currency re-banding as ordering does — and no magnitude is compared, so it is **not** the score claim
1a's f29 rewrite rejected. A claim whose slot is absent from the menu is **unprovable**, never
vacuously true.
_Avoid_: score claim (rejected — this compares no magnitude), threshold claim, zero claim, veto

**Decision Claim** / **Axis Claim**:
The two things a corpus fixture can assert, declared explicitly in its `claims` block
([ADR-0072](../../docs/adr/0072-mid-build-swaps-are-gated-by-deterministic-instruments.md)
decision 3). A **Decision Claim** (`{"decision": [2]}`) is cross-lane and end-to-end: given the whole
board, the agent picks this — today's only assertion. An **Axis Claim**
(`{"axis": {"option_type": 9, "prefer": <slot>, "over": [...]}}`) is within ONE lane: among the
options of that `OptionType`, this one outranks those, resolved by body slot
`(inPlayArea, inPlayIndex)` and **never** by raw option index. Ordering within a lane survives a
currency re-banding; cross-lane *scores* do not — which is why an Axis Claim is an ordering claim and
never a score claim (1a's f29 rewrite is the precedent). An Axis Claim must never be able to launder a
composition defect into green: f35 is rescued by one, f32 is deliberately not.
_Avoid_: pin (the older word for a fixture that asserts *something* — say which claim), score claim
(rejected), expectation, label (a **Correction**'s `correct`, one layer down)

**Held-out Frame** / **Held-out Ledger**:
A frame whose failure has been ruled OUT of the current decider's scope and onto a named owner —
`{"owner": "#165", "ruled": "...", "why": "..."}` in its `claims` block (ADR-0072 decision 4). The
**Held-out Ledger** is the set of them, printed as an always-visible `HELD OUT (n)` section by both
the **Decision Gate** and the **Discrimination Gate**, carrying each frame's current verdict but
**never gating**. Deleting `owner` returns the frame to gating. The point is that a re-ruling is a
*state the instruments read*, not prose in a swap-review doc — the sweep has no exclusion list, so
before this nothing in code ever knew f32/f82 had been re-ruled. Useful only while small: past ~a
dozen frames the section becomes wallpaper, which is the failure mode it exists to prevent.
_Avoid_: excluded / skipped (it still runs and still reports), xfail (the pytest mechanism, a
different surface), deferred frame, parked

**Frame Key**:
A **Correction**'s `identity_key` (`episode|seat|scope|n` — ADR-0049's Scope-*subject* identity)
carried on a corpus fixture as `frame_key`: the join that lets an instrument find the Correction a
fixture was cut from. Declaring it is what opts a fixture into both the **Held-out Ledger** and
**Claim Agreement**. Fixtures predating [ADR-0072](../../docs/adr/0072-mid-build-swaps-are-gated-by-deterministic-instruments.md)
instead carry a loose `episode` + `frame` pair, which is **not** the identity and does not join — the
two populations are disjoint (34 loose-keyed, 8 `frame_key`, and every one of the 8 carries a `claims`
block while none of the 34 do), which is the defect
[ADR-0082](../../docs/adr/0082-a-corrections-ruling-lives-in-its-claim-and-must-agree-with-its-record.md)
back-fills. Several fixtures may legally share one Frame Key — they assert different things about the
same board — so a consumer keys on it without assuming uniqueness.

**Always DERIVED, never hand-built** (ADR-0087 decision 2): `frame_key_of(*identity_key(c))` off
a constructed `Correction`, which is what makes one **Held-out Ledger** ruling hold a frame out of
*both* gates (ADR-0072 decision 4). A key assembled from raw dict lookups is a second implementation,
and it drifts silently because both sides of a diff share the same wrong key — `decider_lab` read
`seat` from the `decision` snapshot, which has no `seat` field, so every key it built said seat 0
against a corpus that is 201/171. The wrong keyspace even leaked into `satisfies_human`'s docstring,
which cites `86088989|0|decision|3` for a frame whose identity is `86088989|0|turn|0`.
_Avoid_: episode/frame (the loose pre-0072 pair, not an identity), fixture id, correction id, key

**Claim Agreement**:
The invariant (ADR-0082) that a fixture's **Decision Claim** equals its **Correction**'s `correct`,
joined by **Frame Key** — because the Correction is the *ruling of record* and the **Leaf Lab** scores
Corrections, not fixtures (`leaf_lab.py`), so a record left wrong keeps feeding bad ranking signal
however many fixtures are right. Exactly two escapes, both already-shipped ADR-0072 fields and both
machine-readable: an `owner` (a **Held-out Frame** — ruled out of this decider's scope) or a dated
`why` (a re-ruling recorded on the fixture). An **undeclared** disagreement is the defect the check
exists to catch; two existed when it was written, both in the pre-`claims` generation that has nowhere
to put a re-ruling. Note `parse_claims` synthesises a Decision Claim from a bare top-level `correct`,
so a stale `correct` *is* a stale Claim wherever it is reached.
_Avoid_: sync, parity, drift check (the failure is an *undeclared* disagreement, not drift as such —
note the separate `obs_mismatch` finding is about the two BOARDS not matching, a different referent),
label check (a **Correction**'s `correct` is one layer down)
