# Training (`tools/train/`)

Offline tooling that turns downloaded **Replays** into curated learning signal. Its first
component is the **blunder inspector** (`blunder_correction`): it replays an Episode in the
official cabt viewer and lets a human mark a blunder, emitting a **Correction**. The
weight-tuner and value-trainer ([ADR-0009](../../docs/adr/0009-training-methodology.md)) are
planned siblings here.

Shared vocabulary — **Correction** is defined in the
[Agent Runtime](../../my_submissions/common/CONTEXT.md) context and reused verbatim; **Replay**,
**Episode**, **Archetype** come from the [Meta Tracker](../../CONTEXT.md) context. Game-rule
terms follow the enums in `my_submissions/cg/api.py`.

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
The **machine** axis of a Correction — *which tunable surface* the blunder blames, from a
closed set tied to the learning architecture (`hypothesis:<id>`, `missing_hypothesis`,
`tactical`, `value`, `scouting`). **Optional in v1** (often unknown before Hypotheses exist);
auto-suggestable for our own games by replaying the Pilot and reading which Hypotheses fired.
The bridge from a blunder to *where the fix lands* (Job A).
_Avoid_: cause, blame, Category (that is the human axis)

**Source**:
Whose game a Correction was marked in — `own` (a game our submission played; the *gold*,
targeted signal) or `peer` (another team's game of our deck; *expertise injection*). Per
[ADR-0009](../../docs/adr/0009-training-methodology.md). The trend report's "my agents over
time" view is the `own` pile; `peer` Corrections are training data shown separately.
_Avoid_: origin, owner
