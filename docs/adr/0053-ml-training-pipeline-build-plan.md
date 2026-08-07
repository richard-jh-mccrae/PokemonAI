# ADR-0053: ML Training Pipeline — Build Plan

**Status.** Accepted (2026-07-13); an accepted BUILD PLAN — no work package has started (the S1/WP0 row
of the status ledger in [docs/plans/ml-training-build.md](../plans/ml/ml-training-build.md) still reads
"not started", and `value_model` is still `PROFILE=False`).

- **Status:** accepted (2026-07-13)
- **Input:** `docs/research/ml-training-system.md` (deep-research report, 2026-07-11)
- **Operational plan:** `docs/plans/ml-training-build.md` (per-session playbook + status ledger)
- **Numbering note:** 0052 (KO Oracle) and 0056 (Stat Provider seam, renumbered from a 0051 that
  collided with the MatchupPlan spine) are taken on an unpushed arch-review worktree branch; this
  ADR took 0053 to avoid a numbering collision.

## Context

The research report recommends five stages: (1) win-probability value net, (2) automated
blunder labeling via value deltas, (3) expert-iteration weight tuning, (4) league self-play
with exploiter probes, (5) fixed evaluation protocol. This ADR fixes the build order,
parallelization topology, and scope for the multi-session build. It does not re-argue the
architecture — the report does that.

Infrastructure inventory (2026-07-13) established three plan-shaping facts:

1. **Stage 1 is an upgrade, not greenfield.** The ADR-0042 pipeline exists end-to-end:
   17-feature extractor (`src/common/value/features.py`), replay→rows extraction
   (`tools/train/value/extract.py`), pure-Python logistic trainer, committed
   `value_model.json`, null-model fail-open, planner-leaf consumption, `win_prob` telemetry.
2. **The engine has no deal-seed control.** `cg.game.battle_start` cannot force identical
   shuffles. The report's duplicate-deal evaluation cannot be built as written. `search_begin`
   forks from any captured state, so duplicate-deal replay from a captured opening is a
   timeboxed spike inside the eval track; the fallback is paired high-N on the existing
   `gauntlet_ab.py`/`paired_ab.py` machinery.
3. **The corpus is already re-derivable.** Training rows are computed offline by replaying
   stored replay JSON through the Pilot (`pilot._board`). Feature changes never force
   regeneration of games. This removes the schema-churn risk that normally forbids parallel
   builds, and means corpus generation starts day one and runs in the background throughout.

## Decision 1 — build order: dependency diamond, two serial gates

```
WP0 corpus v2 ──┬─→ WP1 value net ──[G1]──┬─→ WP3 blunder labeler → existing corrections flow
 (runs in bg)   │                         └─→ WP4 expert-iteration tuner ──[G2]─→ shipped weights
                └─→ WP2 eval harness ─────────(G2 measured on WP2)──────────↑

WP5 league/exploiter — deferred (after WP4 checkpoints exist)    WP6 rotation-loop glue — last
```

Plumbing may parallelize; **integration is gated**. WP3 thresholds and WP4 training targets
are garbage against a miscalibrated net, so both integrate only after G1. WP4's weights ship
only after G2. The eval harness is built early (P2), not last — "Stage 5" numbering in the
report is architecture, not build order.

## Decision 2 — work packages

| WP | Scope | Owns (disjoint per track) | Reuses |
|----|-------|---------------------------|--------|
| WP0 | Corpus v2: all-deck-pair matrix (our agents × agents + exported meta decks driven by the generic Pilot), scale-out via battle.py's worker fan-out, corpus manifest, background-run entrypoint | `tools/sim/selfplay.py`, `tools/sim/gauntlet.py`, new corpus runner | `battle.py` workers, `MatchRecorder`, meta-deck exports |
| WP1 | Value net v2: matchup/archetype conditioning, feature growth beyond the 17, capacity step (logistic → small MLP), validation suite | `tools/train/value/`, `src/common/value/` | entire ADR-0042 pipeline |
| WP2 | Eval harness: matchup×seat-balanced matrix runner, paired-delta stats, skill-sensitivity stratification, fork-replay duplicate-deal spike, frozen-checkpoint opponent pool (Build Ledger zips), AIVAT plug-in point (fills after WP1) | `tools/sim/eval*` (new) | `gauntlet_ab.py`, `paired_ab.py`, `score_diff.py`, Build Ledger |
| WP3 | Blunder labeler: per-decision ΔP(win). v1 = consecutive-own-state value deltas (Suphx Φ-style, no simulation); v2 = fork-simulate top-k alternatives via `search_begin`. Emits auto-Corrections with distinct provenance; "lost with zero flags" = played-well-lost report | new labeler package under `tools/train/` | Correction schema, `backfill_seed.py` content-join, store/reviewed/tune rails |
| WP4 | Expert-iteration tuner: expert = Turn Planner + value-net leaves; extends `tuner/fit.py` from correction ranking-constraints to per-decision expert targets (SGD); learned matchup-keyed weight tables on the Brief/`weight_overrides` carriers. Compound-feature construction (Soemers co-active pairs) = v2, separate iteration | `tools/train/tuner/` | `fit.py`, `featurize.py`, `verify.py`, `retest.py` |
| WP5 | League + BC/PPO exploiter probe | — | **deferred** (Decision 6) |
| WP6 | Rotation-loop orchestration CLI, docs, CI filter entries | `tools/train/pipeline.py` (new) | meta-tracker scheduled-run precedent |

## Decision 3 — gates

- **G1 (value net validates):** held-out logloss/AUC beats the committed seed model and the
  0.69 entropy floor; calibration curve acceptable; cross-deck generalization split (hold out
  a deck pair entirely); `sanity.py`-style probes (P(win) monotone in prize diff, known-lethal
  states → high P). Fail → iterate WP1; WP3/WP4 integration blocked, their plumbing is not.
- **G2 (learned weights ship):** WP4 output beats current hand-tuned weights on the WP2
  harness (paired, matchup×seat balanced), with `score_diff.py` neutrality checks where
  behavior should not move. Ship default-ON, kill-switched, per existing doctrine; Kaggle
  ladder remains the final arbiter.

## Decision 4 — topology: 2 parallel tracks

- **P1 (serial, 1 session):** WP0 + freeze the three cross-track contracts (below) + kick off
  background corpus generation.
- **P2 (2 worktree sessions):** WP1 ∥ WP2. Then G1.
- **P3 (2 worktree sessions):** WP3 ∥ WP4 (WP4 likely spans two sessions). Then G2.
- **P4:** WP6 (+ WP5 whenever unlocked).

Two tracks matches the diamond — at no point are more than two packages unblocked. Each track
owns disjoint files (table above); `main.py` wiring and shared-file touches happen at phase
joins only. ~8 serial sessions collapse to ~5 rounds; corpus wall-clock hides behind P2.

**Contracts frozen in P1:** (a) feature-vector versioning in `value_model.json` (name list =
schema, drift → null model already); (b) auto-Correction provenance tag distinguishing
machine-flagged from human-tagged in the store/reviewed flow; (c) eval-report format WP2 emits
and G2 consumes.

## Decision 5 — training-side dependencies

Offline training code may use numpy/torch via a new `requirements-train.txt`, consumed only by
`tools/train/` on the dev box. The shipped agent stays pure-stdlib: weights export to
`value_model.json`, hand-rolled forward pass (existing ADR-0042 pattern). Rationale: the
corpus will be millions of rows; pure-Python GD stops being practical past logistic capacity.
CI: training-deps job optional; runtime suite unchanged.

## Decision 6 — Stage 4 scope

Exploiter deferred. WP2 includes a frozen-checkpoint opponent pool now (cheap — Build Ledger
zips already run under battle.py), which catches regressions and non-transitivity drift. The
BC+PPO exploiter builds only after WP4 ships checkpoints worth attacking. Rationale: an
exploiter probe is meaningless before trained artifacts exist, and deferral takes nothing off
the critical path.

## Deviations from the report

- Duplicate deals → fork-replay spike + paired high-N fallback (engine limitation, fact 2).
- Corpus: all-deck-pairs supersedes the T5 mirror-corpus design (report Stage 1 note).
- Eval harness built second, not fifth.
- "Gauntlet invalid" doctrine is superseded by the protocol-fixed harness (stratification +
  pairing + balancing + AIVAT); ladder stays the final arbiter.

## Consequences

- Manual blunder rounds become review-of-flagged-anomalies; the corrections store gains a
  machine provenance class and volume.
- `tune.py`'s perceptron/LSQ evolves into the expert-target SGD loop (WP4) — same rails,
  new target source.
- Each WP lands with tests under the mirrored `tests/` area plus a `.github/filters.yml`
  entry for selective CI.
- The committed seed `value_model.json` stays the runtime artifact until G1+G2 replace it;
  `strategy.params["value_model"]` default flips only at G2.
