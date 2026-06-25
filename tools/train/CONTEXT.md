# Training (`tools/train/`)

Offline tooling that turns downloaded **Replays** into curated learning signal. Its first
component is the **blunder inspector** (`blunder_correction`): it replays an Episode in the
official cabt viewer and lets a human mark a blunder, emitting a **Correction**. The
weight-tuner and value-trainer ([ADR-0009](../../docs/adr/0009-training-methodology.md)) are
planned siblings here.

Shared vocabulary — **Correction** is defined in the
[Agent Runtime](../../src/common/CONTEXT.md) context and reused verbatim; **Replay**,
**Episode**, **Archetype** come from the [Meta Tracker](../../CONTEXT.md) context. Game-rule
terms follow the enums in `src/cg/api.py`.

## Language

**Decision**:
One `select` the cabt engine presents at a single step — the agent picks option index(es)
from `select.option` under a `SelectContext` (`MAIN`, `SWITCH`, `DISCARD`, attack-target, …).
The **atomic unit a Correction targets**: `chosen` and `correct` are option choices *at one
Decision*. A human *turn* contains many Decisions; when the better play is a multi-step line,
the Correction marks only the **first divergent Decision** and the `rationale` prose carries
the rest.
_Avoid_: move / play (human-level, may span several Decisions), turn (many Decisions), step
(the replay timeline index, not the choice itself)

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
**status** transition. Job A of [ADR-0009](../../docs/adr/0009-training-methodology.md); designed in
[ADR-0017](../../docs/adr/0017-corrections-compile-to-hypotheses.md).
_Avoid_: weight-tuner (too narrow — it also authors Hypotheses), trainer (the value model, Job B)
