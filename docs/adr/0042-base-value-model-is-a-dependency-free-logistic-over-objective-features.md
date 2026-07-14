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
v1 ships one general model.

> **⚠️ The A/B below is STALE and describes a model that is no longer on disk (corrected 2026-07-14).**
> It reported the **40-game seed** (holdout logloss 0.60; 2000-game mirror A/B at 50%, CI 48–53, 0
> crashes — safe but not an improvement, because a mirror cannot move a tie-break whose signal is the
> matchup). That is not what ships.
>
> What actually happened next: a **pipeline bug** was found — `tune.py`'s `_build_pilot` silently
> dropped the Scout that `main.py` wires, so `favorability` and γ were the neutral default in *every*
> training row, the seed included. It was fixed, the model was **retrained** on a 6-pairing cross-deck
> corpus (900 games → **92,454 states**, holdout logloss **0.5551**; favorability now live at +0.047,
> z≈15), and that retrained artifact is what `src/common/value/value_model.json` contains today.
>
> Its real measurement is a **paired-delta A/B over 48,000 games** across 6 directed matchups, 0
> crashes: **−0.55%, 95% CI [−1.27%, +0.16%]**, negative in 5 of 6 matchups. Parked.
>
> The park does not rest on that CI (which crosses zero) but on a **structural** argument that holds
> regardless: the model's top weights — `prize_diff`, `my_prizes_remaining`, `my_active_hp`,
> `active_doomed` — are precisely what the closed-form leaf already scores directly, and a general
> logistic over redundant inputs adds miscalibration, not signal. Its only matchup-conditioned
> features carry weights of **+0.047** and **+0.029**. ADR-0053 replaces this artifact wholesale at
> WP1 and flips the default at G2; do not flip it before then.
