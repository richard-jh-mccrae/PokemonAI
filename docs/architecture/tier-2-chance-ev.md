# Tier 2 — Chance & EV (Gamble Lines)

**Status: ~70% complete** (built 2026-07-05, `/tdd`; A/B **52%** CI 50–54, 0 crashes, 2000 games —
Battle Result #58 — default ON). Design in
[ADR-0039](../adr/0039-gamble-lines-are-closed-form-expectimax-over-outcome-classes.md). Prices
stochastic actions by **exact** expectation instead of flat penalties or not at all.
**Upstream:** deck tracker (exact own-deck composition) + Deck-Content Odds (ADR-0029); effect
compendium for branch valuation.
**Downstream:** a candidate family on T1's Goal Ladder; fallback EV terms in T0 for non-MAIN
contexts.

## Final design (ADR-0039)

- **Gamble Line** = a Turn Line with exactly ONE **Chance Node** (depth-1 by definition), valued as
  `EV = Σ P(class)·value(best follow-up | class)` over **Outcome Classes** — macro-partitions
  sharing one best follow-up ("≥1 {W} Basic among the 6 drawn" vs "Ignition redrawn, no {W}" vs
  "neither"), never raw card permutations.
- **Probabilities are exact**: own-deck composition = decklist − seen (deck tracker); unseen copies
  split hypergeometrically over hidden prizes (`deck_odds.py`). No sampling, no engine sim through
  the chance node — the Engine Search fork is ONE predicted determinization and its verdict is
  untrusted for prediction-dependent outcomes (the glossary's prediction-invariance rule).
- **Branch valuation is closed-form**: max over legal follow-ups using the compendium's damage
  math + development value — the same evaluators T1 rungs already use.
- **Competition rule**: Gamble Lines rank against deterministic lines by EV on the ladder; the sound
  win rung preempts every gamble; Lethal/Incoming keep worst-case (EV never enters sound math).
  Break-even is EV equality — never a fixed probability threshold.
- **v1 scope** (grilled): ① Hand-Refresh supporters — both *whether* (upgrades ADR-0024's deferred
  pull-EV) and *sequencing* (bank the attach before the shuffle vs gamble for a better draw);
  ② fetch hit/whiff EV inside lines (upgrades the flat `dont-search-a-probable-whiff` −25);
  ③ coin-attack EV for heuristic **ranking** only. Opponent-side stochastics excluded (no exact
  tracker — that's T4 territory).

## The canonical example (facts at source)

Mega Starmie ex Active, 0 Energy; hand: Lillie's Determination (*shuffle hand into deck, draw 6*),
Ignition Energy (*{C}{C}{C}, discard at end of turn*); opponent Active Water-weak.
- **Deterministic line**: attach Ignition → Lillie's → Nebula Beam ●●● 210 — which *ignores
  Weakness* (the ×2 is wasted) and the energy evaporates at end of turn.
- **Gamble line**: Lillie's first (Ignition shuffled away — the stake), then per class: {W} drawn →
  attach → Jetting Blow {W} = **240 with Weakness + 50 snipe**, energy persists; Ignition redrawn →
  Nebula 210 anyway; neither → no attack.
The right choice is EV equality over those classes — board-dependent, not "P > 50%".

## Built (the 70%) — 2026-07-05

- **The Gamble rung** (`planner._best_gamble_line`, kill-switch `gamble_lines`, ON): below every
  deterministic goal, plays a Hand Refresh FIRST when the draw's exact-odds EV beats the banked
  line — KO-enabling Outcome Classes (`_gamble_ko_classes`: type-aware one-attach-short analysis
  over `AttackStat.energyTypes`), tracker-anchored hypergeometrics (`deck_odds.draw_hit_probability`,
  fail-closed), the deterministic baseline (`_gamble_det_baseline` = best menu tactical or best
  after-attach chip), per-refresh draw branches (`_DRAW_COUNTS`). Stands down: mid-sim / KO on the
  menu / protected hand / pre-anchor / hand already holds the enabler. Trace prints P, the class,
  and the EV-vs-held comparison. Gated REQ-GAMBLE-0001..0005 (`tests/strategy/test_gamble.py`) —
  the canonical Lillie's board commits the gamble at 230 HP and stands down at 200.
- **The type-payable fix** (`Pilot._attack_type_payable`): the attach-lethal hook no longer counts
  Ignition's {C}{C}{C} as funding Jetting Blow's {W} — the false KO_SCORE unlock that produced the
  original attach-then-Nebula blunder. (The same count-blindness in `_best_affordable_ko_value` /
  `_develop_wins` is engine-verify-backstopped live and spun off as its own task.)
- **Coin-EV ranking**: a coin/conditional CHIP ranks by its min/max mean (rides `objectives_race`);
  the KO test, Lethal floor, and Incoming ceiling untouched.
- Substrate (pre-existing): deck tracker prize-exact resolution, ADR-0029 odds, sound oracle,
  Shuffle-Refresh Layer A + `dont-refresh-into-a-probable-miss`, Fetch comparator. **Fetch
  hit/whiff EV** is satisfied by design: planner tutor lines gate SOUND (`deck_definitely_has`),
  the score layer keeps the ADR-0029 probabilistic threshold rule.

## Gap to final (the 30%)

1. **Recovery classes** — the "no {W} but the Ignition came back" branch (EV under-counted today;
   conservative direction).
2. Multi-class EV across several enabling attacks/refreshes in one menu (today: best single class).
3. Hand-disruption side-value for Judge-class refreshes (opponent hand unknown — heuristic term).
4. T0 fallback EV terms for non-MAIN contexts.
5. Pre-anchor gambles via the ADR-0029 prize-split hypergeometric (today: post-anchor only).

## Acceptance — met 2026-07-05

Lillie's-class fixture flips exactly on the EV comparison (REQ-GAMBLE-0001/0002); suite 1269
green; A/B 52% (CI 50–54), 0 crashes → `gamble_lines` default ON; trace carries the class + odds.
