# Tier 1 — Turn Planner

**Status: ~85% complete** (2026-07-05). Built and default-ON (ADR-0031 + ADR-0037 join; A/B 51%/52%,
0 crashes). This tier already realizes the core of the "map end-of-turn board states, rank, commit"
vision — the remaining 15% is absorbing the new rungs the other tiers add.
**Upstream:** T0 leaf-eval; T3 goal conditioning (future); T2 gamble family (future).
**Downstream:** the decision itself; telemetry (`planned`/`lethal` keys) consumed by blunder triage.

## Final design

- **One planning entry point**: `plan_turn` at the single-pick MAIN menu; every other context defers
  to T0. Plan once per board fingerprint, re-plan on reveal (cache keyed by fingerprint).
- **Goal Ladder, top-down**: **win rung** (Lethal Solver — sound: min-bound damage, worst-case
  coins, engine-verified lock, materialized-replay veto with identity matching) › KO-the-key-threat
  › KO-for-prizes › stabilize-then-KO › develop. Heuristic rungs generate candidate Turn Lines,
  engine-sim to end-of-turn, rank by leaf-eval, commit the best.
- **Two soundness regimes, one module**: only the win rung locks; everything below is ranking.
- Final-architecture additions (this grilling):
  1. **T2 Gamble Lines** join the ladder as a candidate family below the win rung (EV-valued,
     ADR-0039).
  2. **T3 conditions the ladder**: key-threat/KO-for-prizes rungs become Prize-Path-aware (prefer
     on-path targets); derived phases move weight bands (ADR-0039).
  3. **Leaf-eval upgrade path**: closed-form scalar now → T5 value model when trained.
- **Open (deliberately unresolved):** the layer-on-top commit rule (commit only when tuned scoring
  would miss the outcome, ADR-0031 d6) vs commit-by-default. Revisit via A/B **after** T2/T3 enrich
  the leaf — a richer leaf is the precondition for trusting commit-by-default.

## Built (the 85%)

`src/common/strategy/planner.py` — the whole above minus the three additions: goal ladder, lethal
family generator (direct/attach/retreat/evolve/gust/energy-tutor, single+multi-develop), engine
verify + veto replay (`lethal_family`/`lethal_veto` ON), engine RANKING of heuristic candidates,
dev leaf, closed-form fallback when the engine is absent, per-goal telemetry. Gated by
REQ-LETHAL-0015..0029 + planner CRITICAL regressions (7f48/0cbc/4298) in
`tests/strategy/test_planner_engine.py`.

## Gap to final (the 15%)

1. Accept the **T2 gamble family** into candidate generation + EV-vs-deterministic ranking rules.
2. Accept **T3 conditioning** (path-aware rung targeting; phase-band weights).
3. **Leaf seam** for T5 (value-model call with closed-form fallback).
4. Then re-run the defer-vs-commit A/B (above).

## Acceptance

Existing planner gates stay green; each addition ships behind its own switch + M1 A/B (≥50%, 0
crashes) exactly like `lethal_family`/`lethal_veto` did.
