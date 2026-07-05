# Tier 5 — Value Model

**Status: ~65% complete** (built 2026-07-05, `/tdd`, ADR-0042; a 40-game seed model trains
end-to-end, holdout logloss **0.60** vs the 0.69 coin-flip floor; DEFAULT OFF pending its ladder
A/B). The single learned seam (ADR-0007), realized as a **dependency-free logistic over the T3/T4
objective primitives**.
**Upstream:** mined replays + self-play corpus (labelled states); T3/T4 primitives as features.
**Downstream:** the planner leaf blend (a capped sub-prize term); `win_prob` on telemetry.

## Final design (ADR-0042)

- **One supervised model**, `state → P(win)`, label = eventual winner. NOT the rejected "brute-force
  W/L training": config-level W/L is one noisy bit per agent; state-level supervision assigns it to
  thousands of states/match and the noise averages into calibrated probability.
- **Realized as a dependency-free LOGISTIC** (not LightGBM): the grader is dependency-frozen, so
  *inference* must be pure stdlib; and once the features are the already-nonlinear T3/T4 primitives,
  a linear model's ceiling gap to a GBDT is small. A GBDT trainer exporting a pure-Python forest
  stays the future option if the linear model plateaus.
- **Features = objective primitives** (ADR-0007's open question, resolved by architecture): race
  delta, both Prize-Path turns, prize counts + diff, favorability + γ, development, hand/energy/HP,
  doom, line-ready. The fitted weights are narratable — the seed model's top weights are
  `prize_diff +0.44`, `line_ready +0.31`, `active_doomed −0.27`, `opp_bench −0.47`.
- **Refines judgment only** — a capped sub-prize planner-leaf term (`_PLANNER_VALUE_W × (P−0.5)`,
  the positional sum stays below one KO_SCORE); **never overrides a sound rung**; absent/off → the
  null model (P=0.5, zero influence) so the closed-form leaf is unchanged.

## Built (the 65%) — 2026-07-05, ADR-0042

- **Feature vector** (`src/common/value/features.py`): the fixed, named T3/T4 primitive vector, pure
  over a `Board`, None-path-turn → finite sentinel. Gated REQ-VALUE-0002.
- **Pure-Python trainer** (`tools/train/value/`): `extract` (replay film → `(features, won)` via the
  shipped Pilot's `_board`), `logistic` (stdlib GD + L2, standardization, log-loss), `train` (mine →
  fit → write `value_model.json` + calibration report). Trains on the self-play corpus. Gated
  REQ-VALUE-0003 (separability + round-trip).
- **Absent-safe runtime** (`src/common/value/model.py`): load once, null model on absent / malformed
  / feature-drift, pure dot-product predict. Gated REQ-VALUE-0001.
- **Planner leaf blend** (`_value_term` + `_leaf_value` `value=`), capped below a prize (REQ-VALUE-0004
  proves the hard-rung invariant holds); `win_prob` on the Decision + telemetry for calibration.
- Wired in all three agents + the tune builder behind `value_model` (**DEFAULT OFF**).

## Gap to final (the 35%)

1. **Production corpus** — the shipped artifact is a 40-game seed; retrain on thousands of games
   before the switch flips.
2. **Matchup-conditioned + per-deck tiers** (ADR-0007 general → conditioned → per-deck) as data
   justifies — a `--conditioned` split.
3. **Gamble-branch + path-tiebreak** leaf seams (today: the planner engine-rank leaf only).
4. The **A/B** (value-on vs off) → default-ON decision.

## Acceptance — met 2026-07-05 (seed)

Round-trip + separability (REQ-VALUE-0003); absent-safe (REQ-VALUE-0001); leaf capped below a prize
(REQ-VALUE-0004); seed holdout logloss 0.60 < 0.69; clean fallback with the artifact absent. The
seed A/B (value-on vs off, 2000 games, Battle #60) is **50% (CI 48–53), 0 crashes** — the expected
result for a 40-game seed in a MIRROR (both sides identical; favorability/matchup features don't vary,
so the leaf blend rarely changes a tie): it proves the blend is **safe** (no regression, no crash),
not yet an improvement. The production-corpus retrain + a **non-mirror gauntlet** A/B (where the
matchup features actually vary) remain before default-ON — which is exactly why the switch stays OFF.
