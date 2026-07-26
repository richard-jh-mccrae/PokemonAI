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

**Leaf Frame**:
A **Correction** the **Leaf Lab** can score: a reseedable MAIN-select (context 0) board carrying
something to rank — either a `turn_plan` payload or any MAIN-select pick correction naming a
`correct` option (`is_leaf_frame`). Non-MAIN and obs-less records are excluded because the offline
sim reseeds only from a MAIN-select board. 276 today, of which 267 are *scorable*.
_Avoid_: frame (bare — that's a replay timeline index), fixture (a committed corpus pin under
`tests/fixtures/corrections/`), leaf case

**Endorsement Claim**:
The third thing a fixture can assert (ADR-0071 amendment A): *this slot is (or is not) taken at all*,
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
([ADR-0071](../../docs/adr/0071-mid-build-swaps-are-gated-by-deterministic-instruments.md)
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
`{"owner": "#165", "ruled": "...", "why": "..."}` in its `claims` block (ADR-0071 decision 4). The
**Held-out Ledger** is the set of them, printed as an always-visible `HELD OUT (n)` section by both
the **Decision Gate** and the **Discrimination Gate**, carrying each frame's current verdict but
**never gating**. Deleting `owner` returns the frame to gating. The point is that a re-ruling is a
*state the instruments read*, not prose in a swap-review doc — the sweep has no exclusion list, so
before this nothing in code ever knew f32/f82 had been re-ruled. Useful only while small: past ~a
dozen frames the section becomes wallpaper, which is the failure mode it exists to prevent.
_Avoid_: excluded / skipped (it still runs and still reports), xfail (the pytest mechanism, a
different surface), deferred frame, parked
