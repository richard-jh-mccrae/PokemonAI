# ML Training Pipeline — Frozen Cross-Track Contracts (C1/C2/C3)

**Status:** frozen 2026-07-13 in Build Session 1 (Work Package 0). These are the three interfaces
that let Work Packages 1–4 build in parallel worktree sessions without stepping on each other. Changing one after a downstream
session has consumed it is a breaking change — amend here first, with a reason, then update every
consumer. Governing plan: [ADR-0053](../adr/0053-ml-training-pipeline-build-plan.md); playbook:
[ml-training-build.md](ml-training-build.md).

---

## C1 — Schema / feature versioning

Two artifacts carry a version so a stale one is refused rather than silently mis-mapped.

### C1a — Corpus run manifest (`data/replays/corpus/<run_id>/manifest.json`)

`manifest_version: 1`. Fields (written by `tools/sim/corpus.py`):

| Field | Meaning |
|---|---|
| `manifest_version` | int; bump on any breaking shape change |
| `run_id` | stable id for the run (survives resume) |
| `created_at` | ISO8601 (first creation; unchanged on resume) |
| `git_rev` | short commit of the generating tree |
| `agents` | list of our decision-owning agents in the matrix |
| `opponents` | list of extra opponent bundles (meta-deck drivers); `[]` in v1 |
| `agent_versions` | `{name: git_short}` provenance per contestant |
| `pairings` | `[{a, b, stem, target, done}]` — `done` recounted from disk on resume |
| `per_pairing` | target games per pairing |
| `caps` | `{max_games, max_bytes}` — hard stops |
| `corpus_schema` | `{replay_shape: "cabt-visualize", value_model_format: 2}` — links the corpus to the artifact format it feeds |
| `status` | `running` \| `complete` \| `capped` |
| `totals` | `{games, bytes}` |

**Disk is authoritative, not the manifest.** Replay files are named `{index:06d}_{episode_id}.json`;
resume recounts per-pairing progress from the max on-disk index, so a crash between a file write
and a manifest flush never double-writes or collides. The manifest is a convenience header,
flushed periodically and on exit.

### C1b — Value model artifact (`src/common/value/value_model.json`)

`format: 2` (see [ml-training-design-s2a.md](ml-training-design-s2a.md) §D3). The loader
(`src/common/value/model.py`) pins on an **exact match** of both the `features` name list and the
`archetypes` vocab against the running build's `FEATURE_NAMES` / `ARCHETYPE_VOCAB`; any drift →
null model (fail-open to the heuristic). A `format`-less artifact is the v1 committed seed
(back-compat logistic path). This is specified fully in the Build Session 2a design; C1 only fixes that the
**corpus manifest records `value_model_format` so a corpus and the artifact it trains can never
silently disagree on shape**.

---

## C2 — Machine-Correction provenance (LOCKED: new `provenance` field)

**Decision (user-approved 2026-07-13):** `Correction` gains `provenance: str = "human"`
(`tools/train/blunder/correction.py`), written `"machine"` by the ML labeler (Work Package 3). `source`
stays `"own"`/`"peer"` and keeps its meaning (whose *game* it was) — a machine label of our own
game is `source="own", provenance="machine"`.

**Why this encoding, not a new `source` value or a separate store:**
- Backward-compatible in both directions: old `corrections.jsonl` records lack the key →
  `from_dict` defaults to `"human"`; every existing `source=="own"` filter (`tune.py:146`,
  `report.py`, shell defaults) keeps working untouched.
- One deliberate opt-in per consumer that wants to distinguish machine records, instead of N
  filter edits that silently drop machine corrections if one is missed.
- Human and machine corrections still meet in `find_conflicts` (same store), so a disagreement on
  the same decision surfaces for review instead of hiding in a parallel tree.

**Fit-time collision rule (Build Session 3b must implement):** when a machine record and a human record share
the identity key `(episode_id, seat, scope, subject)`, the **human record wins** — the machine
record is excluded from the weight fit. `reviewed.json` dispositions apply to both classes
identically. Rationale: an automated ΔP(win) flag must never overrule a human's reviewed
judgment on the same decision.

**Status:** the field + `build_correction(provenance=...)` param are BUILT in Build Session 1 (default
`"human"`, zero behavior change). The labeler writing `"machine"` and the fit exclusion are Build Session 3a / Build Session 3b.

---

## C3 — Eval report format (Work Package 2 emits → Adoption Gate consumes)

The JSON the eval harness (`tools/sim/eval*`) writes and the Adoption Gate reads. `report_version: 1`:

| Field | Meaning |
|---|---|
| `report_version` | int |
| `generated_at` | ISO8601 |
| `git_rev` | short commit under test |
| `baseline` / `candidate` | contestant descriptors `{agent, label, config}` (e.g. weights on/off) |
| `n_games` | total games run |
| `matchups` | `[{opponent, seat, n, candidate_wins, baseline_wins, draws}]` — the matchup × seat cells |
| `paired_delta` | `{win_delta, ci_low, ci_high, method}` — candidate−baseline, reusing `paired_ab.py` |
| `strata` | `[{name, n, win_delta, ci_low, ci_high}]` — e.g. the skill-sensitive stratum (or `[]` if the fork-replay spike didn't land) |
| `checkpoints` | `[{build_id, n, candidate_wins}]` — the frozen-checkpoint opponent pool results |
| `aivat` | `{variance_reduction, corrected_delta}` or `null` (fills after Work Package 1) |
| `verdict` | `pass` \| `fail` \| `inconclusive` — the Adoption Gate's read against the win-delta CI |

Work Package 2 owns the exact emitter; C3 fixes the field set so the Adoption Gate's consumer and any dashboard can be
written against a stable shape before the harness exists. Additive fields are non-breaking; a
removed/renamed field bumps `report_version`.

---

## Change log

- 2026-07-13 — C1/C2/C3 frozen in Build Session 1; C2 `provenance` field built (behavior-neutral).
