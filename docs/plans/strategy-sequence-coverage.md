# Contextual Strategy sequence coverage

Status: implemented

Extends [strategy-beam-bellman.md](strategy-beam-bellman.md); its invariants remain in force.

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

## Why the boundaries sit where they do

- Coverage counts only certain direct advances. An access match — a card that may *find* a need —
  has not advanced it; counting reach would let any generic draw card saturate the cap and outrank
  the play that actually does the thing. Restricting coverage to certainty also makes the written
  coverage-before-reachability order provably agree with the protected-bundle reachability-first
  rank: an action with any coverage already carries reachability one.
- Outcomes deduplicate on the bound recipient body, never the authoring selector or the strategy
  identifier, so renaming or re-declaring guidance cannot manufacture search preference.
- A sequence counts each distinct outcome once: the solver hands the beam the outcomes the searched
  prefix already advanced, and re-advancing one adds nothing.
- Impossibility marks are an epoch-scoped external proof with no in-repo producer yet; the beam
  honors them as a caller-owned contract and treats unknown reachability as fail-open.
- This is traversal and publication order only. A structural proof may not depend on beam width or
  sort order, so the dominance filter reads the full match set, not the width-truncated beam.
- The runtime effect-safe timeout fallback keeps legacy ordering: its contract was frozen by this
  design's non-goals, and any change to it must land as its own measured decision.

## Validation

Contracts live in `tests/strategy/test_strategies.py` and `tests/bellman/test_m3_solver.py`.
Acceptance: no correction movement, no exhaustive policy difference, no p95 total-time regression;
improvement expected in first-complete-line timing on turns with several compatible active needs,
measured via `tools/sim/strategy_bench.py` with only the coverage switch toggled.
