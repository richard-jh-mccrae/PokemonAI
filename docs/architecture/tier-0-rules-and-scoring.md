# Tier 0 — Rules & Tuned Scoring

**Status: ~90% complete** (2026-07-05). The backbone and the universal fallback: every other tier
degrades here, and every non-MAIN decision context (search picks, snipe targets, multi-select,
mulligan, yes/no) is scored here directly.
**Upstream:** Observation + Board/Context signals, Function Tags, compendium, Read.
**Downstream:** leaf-eval inside T1 ranking; the T2 fallback EV terms; the trainable surface for
Corrections.

## Final design (unchanged by the 2026-07-05 grilling)

- `Score(option) = Σ wₕ·firesₕ + Tactical` — named, testable **Hypotheses** (deck Strategy over the
  General Strategy baseline, weight overrides per ADR-0035, folds per ADR-0034), plus the
  closed-form **Tactical Evaluator** (KO/damage/prize math from the effect compendium).
- **Card knowledge is measured, never recalled**: `CardStat`/`AttackStat` (damage formulas, effect
  modifiers, ADR-0032), Effect Clauses, Function Tags (ADR-0006), `TransientTracker` (ADR-0033),
  `TurnBoostTracker`, forward-evolution index (ADR-0020).
- **Teacher = Corrections** (ADR-0015/0017/0018): blunder tagging → verified Hypotheses/weights via
  the soft-margin perceptron + adoption gate; the reviewed ledger keeps rounds incremental.
  W/L never teaches rules; it only gates configs (M1 pre-filter, ADR-0021 + real ladder).
- Remains the **legibility substrate** (ADR-0012): every fired rule is named in the trace.

## Built (the 90%)

`src/common/strategy/` — baseline clusters (ADR-0025) + doctrines (Gust ADR-0022, Fetch ADR-0023,
Shuffle-Refresh ADR-0024, Tool ADR-0028) + context/board signals; effect compendium + damage oracle
(ADR-0032, 96.6% pool-verified, over-prediction zero); deck tracker + sound emptiness oracle +
Deck-Content Odds (ADR-0029); tuning pipeline `tools/train/tune.py` + blunder inspector + retest
harness; per-deck Strategies (mega_starmie, mega_lucario, dragapult_ex) with alignment passes
(ADR-0036). Suite >1100 green, Windows+Linux CI.

## Gap to final (the 10%)

1. **T2 fallback terms** — closed-form pull-EV/whiff-EV terms for stochastic options in non-MAIN
   contexts where the planner never runs (see [tier-2](tier-2-chance-ev.md), fallback tier).
2. **T3 vocabulary adoption** — path/race/denial Board signals become `when()`-visible so deck
   Strategies can key rules on them (fold policy applies).
3. Ongoing: correction rounds keep growing the rule set; vocabulary stays curated (blunder-category
   vocab, closed select-context enums).

## Acceptance

Suite green both OSes; correction-corpus score non-regression (Score-Diff Gate for neutral changes);
tune.py margins; M1 A/B for behavior changes.
