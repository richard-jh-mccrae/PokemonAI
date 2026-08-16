# Contextual Strategy sequence coverage

Status: implemented on `claude/strategy-sequence-coverage-bcb41e`

Extends [strategy-beam-bellman.md](strategy-beam-bellman.md); its invariants remain in force.
Depends on PR #541 (`codex/strategy-anytime-fallback`).

## Problem

The Strategy beam scored each legal action by its strongest matching active hint alone. A line that
advances several compatible needs received no additional search preference over a line that advances
only the strongest one, wasting bounded Bellman time on turns where one sequence can satisfy several
General and deck-specific Strategies. A raw sum is also wrong: duplicate declarations or several
low-value conveniences could outweigh one critical need.

## Decision

Rank Strategy guidance lexicographically, never additively:

```text
highest contextual urgency satisfied
→ highest authored conviction satisfied
→ protected (high-urgency/high-conviction) outcomes satisfied
→ additional distinct outcomes satisfied, capped so declaration volume cannot dominate
→ reachability evidence
→ stable deterministic tie-break
```

Five low-priority outcomes must not outrank one high-urgency outcome. A line satisfying the same
high-urgency outcome plus useful secondary outcomes searches before a line satisfying only the
high-urgency outcome. Bellman's value remains the final chooser.

## Shape

- `StrategyBeamBuilder._priority` produces the lexicographic rank and per-action coverage; `build`
  sorts the focused beam by that rank. `outcome_identity` is the shared deduplication key — desired
  kind, bound recipient body (serial and card id, never the authoring selector or the strategy
  identifier), target set, and waypoint — so equal declarations collapse to one need.
- Coverage counts only certain direct advances (evolve, attach, deploy, heal, damage classes). An
  access match (a card that may *find* a need) keeps setting the primary tier, reachability, and
  odds, but adds zero coverage: one action never counts the alternatives it merely reaches.
  With coverage restricted to certainty, the written coverage-before-reachability order and the
  protected-bundle reachability-first rank cannot disagree.
- `SequenceCoverage`/`combined_coverage` are the pure projection for a searched prefix or candidate
  continuation: best need tier reached plus the ordered distinct outcomes advanced. The solver folds
  it along the harvest prefix (`prefix_outcomes`), so a sequence counts each distinct outcome once.
- Satisfied and externally-proven-impossible outcomes stop contributing; unknown reachability fails
  open. Ordering only: Bellman values, bounds, dominance and terminal proofs, and the exhaustive
  policy are unchanged, enforced by tests.
- `strategy.sequence_coverage_enabled` (default on, not learnable) is the kill switch for paired
  slow-frame comparison. The runtime effect-safe timeout fallback keeps the legacy ordering.
- The protected two-slot bundle pool from PR #541 keeps its reachability-first rank and its time
  shares; sequence coverage never multiplies a bundle's reserved time.

## Validation

Contracts live in `tests/strategy/test_strategies.py` (rank properties, dedup, rename/scope
neutrality, cap, prefix, Riolu/Lunatone fixture) and `tests/bellman/test_m3_solver.py` (toggle
changes no value, bound, or exhaustive policy; harvest hands the beam the prefix outcomes).
Acceptance: no correction movement, no exhaustive policy difference, no p95 total-time regression;
improvement expected in first-complete-line timing on turns with several compatible active needs,
measured via `tools/sim/strategy_bench.py` with only this switch toggled.
