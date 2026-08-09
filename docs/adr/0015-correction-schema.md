# ADR-0015: The Correction schema — atomic, two-axis, self-contained

**Status.** Accepted and BUILT — the shipped Correction schema (`tools/train/blunder/correction.py`,
`store.py`). Substantially extended since: the four amendments below (embedded agent `obs`, build
identity, the per-build correction tree, `live_trace`) and [ADR-0049](0049-corrections-carry-a-scope-decision-turn-or-match.md),
which relaxes "one Decision" into a Scope (`decision` | `turn` | `match`).

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

## Amendment ([ADR-0018](0018-applying-tuner-output.md)): build-identity traceability

Each Correction also records the **build that played the game** — `agent_build` (the
`submissions/<agent>_<date>_<sha>[-dirty]/` stem), `agent_version` (the git sha), and `built_at`
(the parsed timestamp) — **auto-derived from the replay path** (`provenance.build_identity`); no
flags to remember. This ties every correction to a concrete agent version + date, so the report
can show how the blunder profile evolved build-by-build over the competition. Pre-existing records
backfill via `tools/train/backfill_obs.py`.

## Amendment: per-build storage (correction tree)

The log is no longer one growing `data/corrections/corrections.jsonl` but a **tree mirroring
`data/replays/<stem>/`**: `data/corrections/<agent_build>/corrections.jsonl`. Routing is automatic —
a Correction carries its `agent_build` (the build-identity amendment), so `store.append_correction`
files it under that build's subdir; corrections with no parseable build go to `_unfiled/`. A `.jsonl`
path addresses one file; a **directory** addresses the whole tree (`load_corrections` unions + dedups
every `<build>/corrections.jsonl`). This gives competition-long traceability — at the end you can see
exactly which build had which corrections (the report's by-build view reads the tree). Reusable
consumers are unchanged (they read the root dir by default). Migration: the single file was split by
`agent_build` into per-build subdirs.

## Amendment ([ADR-0049](0049-corrections-carry-a-scope-decision-turn-or-match.md)): Scope

"Atomic granularity" above is now the **default**, not the only shape. A Correction carries a
**Scope** (`decision` | `turn` | `match`); a legacy record with no `scope` loads as `decision`.
Off `decision` scope, identity is the Scope's subject rather than the frame, `correct` is optional
and — when given — must index the **Anchor** Decision (the first divergent one), and the record
embeds the **Span** of Decisions it covers. The Tier-2 deferral above is upgraded to an invariant:
a multi-frame counterfactual line cannot be option-indexed at all, because prescribing a different
Anchor pick invalidates every later frame's `select.option`.

## Amendment: executable counterfactual turns

The Tier-2 deferral is now built for retained replays. `counterfactual.py` reconstructs the Anchor's
full-information state in cgpy, executes the human's alternate first choice, and records each newly
generated menu by semantic option identity. `turn-sequence/v2` embeds the completed proof and its
end-state digest; raw later replay indices remain invalid and are never reused.

Commutativity is empirical engine evidence: fork once, execute both adjacent action orders, and call
them `commutes` only when both remain legal, consume no randomness, and produce the same complete
engine state. The full-line grader compares end-state digests, so a proved reorder satisfies the
ideal line while a genuinely different state reports its first semantic block divergence.

## Amendment ([ADR-0019](0019-submissions-are-traceable-and-tracked.md)): embed the live trace

When the game's **Decision Telemetry** log (`episode-<id>-agent-<seat>-logs.json`) is available, the
Correction also embeds **`live_trace`** — the `@T` record the *shipped* agent emitted at this exact
decision (`plan`, `tier`, `chosen`, per-option `score`/`tac`/`fired:[[hyp_id, weight]]`, `margin`):
the ground truth for *how the agent actually decided* (not a re-derivation). Joined by the positional
frame↔record map in `train.blunder.telemetry_log`, validated by option-count + chosen. It is the
`before` anchor the **retest** (`train.tuner.retest`, same `telemetry.to_record` format) diffs the
post-fix decision against. It reflects the build's *shipped* `tuned.json`, which can differ from
current source — that divergence is the retest signal. Backfilled by `tools/train/backfill_obs.py`.
