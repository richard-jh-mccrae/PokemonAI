# ADR-0015: The Correction schema — atomic, two-axis, self-contained

**Context.** [ADR-0009](0009-training-methodology.md) named the Correction
`(state, chosen, correct, attribution, rationale)` but never defined its shape, the
granularity of a "decision", or how `state` is stored. The blunder inspector
(`tools/train/blunder/`) needs all three pinned.

**Decision.**

- **Atomic granularity.** A Correction targets exactly **one Decision** — one engine
  `select` at one frame of the full-information `visualize` film (both hands visible,
  unlike the agent Observation). `chosen`/`correct` are **positional indices into
  `select.option`**. When the better play is a multi-step line, the Correction marks the
  **first divergent Decision** (Tier-1); the rest of the line lives in `rationale` prose.
  Clicking out full counterfactual lines (Tier-2, needs re-simulation) is deferred.
- **Two axes.** `category` is the **human** axis — a closed, extensible vocabulary
  (`missed_win`, …), **mandatory**, the dimension the trend report buckets by.
  `attribution` is the **machine** axis — the tunable surface the blunder blames
  (`hypothesis:<id>`, `missing_hypothesis`, `tactical`, `value`, `scouting`),
  **optional in v1** (auto-suggestable later by replaying our Pilot).
- **Source.** `own` (our submission's game; gold) vs `peer` (another team's game of our
  deck; expertise injection). The trend report's "my agents" view is the `own` pile.
- **Self-contained state.** The Correction **embeds a deep-copied snapshot** of the
  Decision (`frame`, `turn`, `select_context/type`, `options`, full-info `current`) plus a
  provenance reference (`episode_id`, `seat`). It therefore **survives replay deletion**
  (the [ADR-0002 amendment](0002-extracts-only-retention.md)); the trainer and report
  never need the raw replay.
- **Storage.** Append-only **JSONL** at `data/corrections/corrections.jsonl`, **committed**
  (gold, hand-authored training data) — the "correction log" of ADR-0009.

**Validation.** `correct` must index legal option positions and **differ from `chosen`**
(otherwise it is not a blunder); `category` must be in the closed vocabulary; `source` must
be `own`|`peer`.

**Consequences.** Corrections are small and durable. The report reads only the log. The
atomic model yields clean Job-A ranking labels ("`correct` should outrank `chosen` at this
state") but cannot, in v1, encode multi-step alternative lines — captured as prose until
Tier-2. `chosen_label`/`correct_label` are filled by the option decoder for legibility.

## Amendment ([ADR-0017](0017-corrections-compile-to-hypotheses.md)): embed the agent `obs`

The embedded film `current` is full-info, string-enum — for human display. The **Tuner** needs
the Pilot's exact input, so the Correction also embeds the **agent `obs`** (int-enum, hidden-info)
for the Decision's frame. This makes featurization self-contained (no replay needed) at identical
accuracy. Existing records (saved before this) backfill `obs` from their retained replays.
