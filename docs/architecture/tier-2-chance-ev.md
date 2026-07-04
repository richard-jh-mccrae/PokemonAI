# Tier 2 — Chance & EV (Gamble Lines)

**Status: ~15% complete** (2026-07-05). Design accepted in
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

## Built (the 15%)

Deck tracker with prize-exact resolution (`common/deck_tracker.py`); hypergeometric
`Board.deck_contains_probability` (`common/deck_odds.py`, ADR-0029); sound emptiness oracle;
Shuffle-Refresh Layer A keep-value + dead-hand fallback (ADR-0024); flat whiff suppressor; coin
min/max bounds in Damage Formulas (the EV-ranking inputs); Fetch value comparator (ADR-0023).

## Gap to final (the 85%)

1. **Outcome-Class enumerator** — per chance-node kind: draw-6/8 classes over "contains ≥1 of
   target set" partitions (multivariate hypergeometric over the tracked deck), fetch hit/whiff,
   coin H/T.
2. **Gamble family generator** in the planner (candidate = pre-actions → chance action → per-class
   follow-up policy) + EV valuation + ladder ranking.
3. **Sequencing accounting** — attach-once-per-turn and supporter-once-per-turn constraints across
   the branch (the bank-vs-gamble decision falls out of correct accounting).
4. Hand-disruption side-value heuristic for Judge-class refreshes (opponent hand unknown — a
   heuristic term, flagged as such).
5. Coin-EV ranking switch for heuristic rungs (sound paths untouched).
6. Trace format: per-class P + value + the EV comparison line (writeup-grade legibility).
7. T0 fallback EV terms for non-MAIN contexts.

## Acceptance

Fixture: the Lillie's-class board flips to the gamble exactly when EV says so (and NOT when the
deck lacks {W} count — tracker-driven); corpus non-regression; M1 A/B ≥50%, 0 crashes; trace shows
Outcome Classes with probabilities.
