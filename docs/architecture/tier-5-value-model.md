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

## Finish plan (grilled 2026-07-05, `/grill-with-docs`) — the cross-deck gauntlet

The seed A/B was a MIRROR → 50% neutral-BY-CONSTRUCTION (favorability, the model's matchup signal,
is invariant when both seats are the same Pilot; the corpus was mirror-only too, so the seed never
saw a varying-favorability state to LEARN from). The finish validates the model where favorability
actually varies, using our **three real agents** (mega_starmie / mega_lucario / dragapult_ex) as the
non-mirror set — no new decks (the `briefs/` are opponent-recognition data, not playable strategies).
Flip-or-park; parking with recorded evidence is a first-class done (§7).

1. **Corpus harness** — a thin recorder on `battle.py`'s process-isolated `play_match` loop (it
   already holds each seat's obs + choice + winner). Process isolation is the ONLY collision-free
   path: the in-process selfplay loader collides in `sys.modules` on two decks' bare
   `from strategy import STRATEGY` (`AgentServer`'s own docstring: an in-process load "cannot" seat
   two Bundles without colliding). Emit one cabt-`visualize`-shaped film per game under
   `data/replays/gauntlet/`, so the existing `tools/train/value/extract.py` + blunder-buster/meta-tracker
   consume it unchanged (one corpus format across every replay tool).
2. **Corpus mix** — all 3 cross pairings (SM×ML, SM×DP, ML×DP) **+ the 3 mirrors**, baseline both
   seats (`value_model` OFF — you can't train the leaf on a policy that already uses it), ~150 games
   each (~900 total; the raw-engine recorder does this in ~a minute). Mirrors keep the model
   calibrated on near-symmetric mid-game boards; cross-deck carries the new favorability signal.
3. **Retrain + sanity gate** — retrain the one shared general model; the **favorability weight must
   move off ~zero** (dead in the seed because favorability never varied). If it stays dead, the
   favorability FEATURE (T4) is the bottleneck, not the model → **park T5 pointing at the T4 gap**
   (opp_tempo / Brief coverage), don't force it.
4. **Paired-delta A/B** — for each directed matchup (our deck D vs a FIXED baseline opponent O≠D),
   `winrate(D@value-on vs O) − winrate(D@value-off vs O)`, aggregated equally across all 6 directed
   matchups; N≈4000/battle. Paired-delta is the only design that subtracts out the raw deck matchup
   (SM may beat ML 55% regardless — only the on−off delta is the model). A naive single-battle >50%
   proves nothing.
5. **Flip bar** — `value_model` ON iff aggregate delta ≥ 0 AND its CI lower bound ≥ −1% (rules out a
   real regression) AND 0 crashes; else **park OFF** with the numbers recorded here. The leaf is
   capped sub-prize, absent-safe, and never overrides a sound rung, so a demonstrated non-regression
   is a sufficient bar (it cannot cause the self-inflicted loss an unbounded model could, and shipping
   it validated-safe keeps T5 live for the matchup-conditioned upgrade). Parks only if it hurts.

## Finish result — PARKED OFF with evidence (2026-07-05, `/tdd`)

**The value model stays DEFAULT OFF — parked, not flipped.** The finish plan ran end to end and the
cross-deck A/B decided park:

- **Pipeline bug found + fixed first** (the real blocker): `_build_pilot` — the pilot the value
  extractor mines through — silently DROPPED the Scout that `main.py` wires, so `favorability` and γ
  were the neutral default in EVERY training row, the seed included. That, not the mirror-only corpus
  alone, is why the seed's favorability weight never moved. Fixed in `tools/train/tune.py` (wire
  scout + briefs + posture, mirroring main.py); **blast radius zero** (full suite green — posture is
  advisory). Locked by REQ-VALUE-0007. (This also makes every blunder/planner retest faithful to the
  shipped agent's Read, which they weren't before.)
- **Cross-deck gauntlet built + retrained**: recorder on `battle.py::play_match` (`sim/record.py`) →
  `sim/gauntlet.py` cross-deck corpus (6 pairings, 900 games); retrained the shared model on **92,454
  states** (holdout logloss **0.555** vs the seed's 0.60, floor 0.69). **Sanity gate passed** —
  favorability is now LIVE (+0.047, z≈15: weak but unambiguous; the board primitives legitimately
  dominate the matchup prior). So the pipeline fix worked and favorability is a weak-but-real feature,
  NOT the T4 bottleneck the park-contingency guarded against.
- **Paired-delta A/B (48k games, 6 directed matchups, 0 crashes)**: value-on aggregate
  **delta = −0.55%, 95% CI [−1.27%, +0.16%]**, **5 of 6 matchups negative** → `flips_on = False`
  (fails both delta ≥ 0 and CI-lo ≥ −1%). The learned leaf marginally REGRESSES even where favorability
  varies, because its features are largely REDUNDANT with the closed-form leaf the tuned tiers already
  score (ADR-0042's own caveat) — over redundant inputs a general logistic adds slight miscalibration,
  not signal. Capped + degrade-safe, so the regression is tiny, but consistently negative → park per
  the park-**only**-if-worse rule.

**Kept for the future**: the retrained artifact (`src/common/value/value_model.json` — favorability-live,
better-calibrated) is the better base for the deferred **matchup-conditioned** model (ADR-0007), which
is the real signal unlock (a *general* model over features redundant with the closed-form leaf cannot
beat it). The gauntlet tooling (`sim/record.py`, `sim/gauntlet.py`, `sim/paired_ab.py`,
`sim/gauntlet_ab.py`, `train/value/sanity.py`) + the `_build_pilot` Read fix are reusable regardless.
Parked per the finish-plan's flip-**or-park** definition of done.

## Deferred refinements (data-justified, not blockers)

- **Matchup-conditioned + per-deck tiers** (ADR-0007 general → conditioned → per-deck) — a
  `--conditioned` split, as data justifies. This is the real matchup-signal unlock now that the general
  model is shown neutral-to-slightly-negative.
- **Gamble-branch + path-tiebreak** leaf seams (today: the planner engine-rank leaf only).

## Acceptance — met 2026-07-05 (seed)

Round-trip + separability (REQ-VALUE-0003); absent-safe (REQ-VALUE-0001); leaf capped below a prize
(REQ-VALUE-0004); seed holdout logloss 0.60 < 0.69; clean fallback with the artifact absent. The
seed A/B (value-on vs off, 2000 games, Battle #60) is **50% (CI 48–53), 0 crashes** — the expected
result for a 40-game seed in a MIRROR (both sides identical; favorability/matchup features don't vary,
so the leaf blend rarely changes a tie): it proves the blend is **safe** (no regression, no crash),
not yet an improvement. The production-corpus retrain + a **non-mirror gauntlet** A/B (where the
matchup features actually vary) remain before default-ON — which is exactly why the switch stays OFF.
