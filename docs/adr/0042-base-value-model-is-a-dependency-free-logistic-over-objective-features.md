# ADR-0042: The Automatic Value Model is a dependency-free logistic over the objective features

**Status.** Accepted + **Built 2026-07-05** (`/tdd`, Tier 5). The single learned seam (ADR-0007),
scoped by the 2026-07-05 architecture grilling: its FEATURES are the Tier-3/Tier-4 objective
primitives, and it refines judgment only. Build record:
[docs/architecture/tier-5-value-model.md](../architecture/tier-5-value-model.md). Terms:
*Automatic Value Model* in [src/common/CONTEXT.md](../../src/common/CONTEXT.md) (already defined ADR-0007).

**Context.** ADR-0007 committed to ONE learned component — a replay-trained `state → P(win)` — and
named "state-feature encoding" the highest-leverage open question. Two constraints shape the
realization: (1) the grader is CPU-only, offline, dependency-frozen — LightGBM/sklearn are not
guaranteed present, so *inference* must be pure stdlib (the same constraint that rejected card2vec);
(2) the project builds on Windows + Linux from the stdlib alone. Meanwhile Tiers 3-4 now compute the
prize-race primitives (both Prize-Path turns, KO-Race delta, favorability, development) that a raw
board encoder would have to re-learn from scratch.

**Decision.** The Automatic Value Model is a **logistic regression over the Tier-3/Tier-4 objective
features**, trained offline in pure Python and shipped as a JSON artifact a dependency-free runtime
evaluates.

1. **Features = the objective primitives** (`common/value/features.py`, a FIXED named vector): race
   delta, both Prize-Path turns (None → a finite sentinel, so an early board is in-distribution),
   prize counts + diff, favorability, γ, development, hand/energy/HP, doom, line-ready. The symbolic
   tiers did the credit assignment; the logistic learns only their relative weights — less data, and
   the fitted weights stay narratable (the trained model's top weights are `prize_diff +0.44`,
   `line_ready +0.31`, `active_doomed −0.27`, `opp_bench −0.47` — the race story, readable).
2. **Pure-Python trainer** (`tools/train/value/`, never ships): mine `(features, won)` from replay
   films via the shipped Pilot's `_board` (label = eventual winner — the state-level supervision that
   turns one noisy bit/match into thousands of calibrated rows), standardize, fit with full-batch GD
   + L2, report train/holdout log-loss.
3. **Dependency-free, absent-safe runtime** (`common/value/model.py`): load the JSON once; a missing
   / malformed / feature-drifted artifact yields the **null model** (P=0.5, zero influence), so the
   closed-form heuristic is the clean fallback. Inference is one standardize-then-dot-product.
4. **Refines judgment only — NEVER overrides a sound rung**: consumed as a capped sub-prize term in
   the planner leaf (`_PLANNER_VALUE_W × (P−0.5)`, the whole positional sum stays below one KO_SCORE
   — the ADR-0031 hard-rung invariant) and emitted on telemetry (`win_prob`) for calibration.
   **Default OFF** — a learned seam ships only after its own ladder A/B (like every kill-switched
   layer), and the shipped artifact is inert until `value_model` is turned on.

**Rejected.**
- **Raw board encoding + a deep model**: re-learns prize math from scratch (data-hungry), opaque for
  the writeup, and needs a heavier runtime than the grader budget allows.
- **A GBDT (LightGBM) shipped for inference**: not dependency-free at grader time; a tree ensemble's
  extra ceiling is small once the features are the already-nonlinear objective primitives. (A GBDT
  *trainer* exporting to a pure-Python forest stays a future option if the linear model plateaus.)
- **The model as an arbiter above the ladder** (veto sound rungs / gamble thresholds): a
  miscalibrated model overriding a proven Lethal is the self-inflicted loss the sound layer exists to
  prevent; it breaks the legibility gate and reintroduces the opaque end-to-end evaluator ADR-0007
  rejected.

**Consequences.** The ADR-0007 "feature encoding" question is resolved by architecture, not by a
learned encoder. Corrections/telemetry now carry `win_prob` (calibration measurable on real games).
`build order general → matchup-conditioned → per-deck` (ADR-0007) is a future `--conditioned` split;
v1 ships one general model. The shipped artifact is a 40-game seed proof-of-pipeline (holdout logloss
0.60 vs the 0.69 coin-flip floor) — a production model retrains on a larger corpus before the switch
flips. The seed A/B (2000 games, Battle #60) is 50% (CI 48–53), 0 crashes: the blend is **safe**
(no regression / crash) but not yet an improvement — a 40-game model in a MIRROR can't move the
tie-break (the matchup features that carry the model's signal don't vary when both seats are the same
Pilot). Default-ON waits on the production retrain + a non-mirror gauntlet A/B.
