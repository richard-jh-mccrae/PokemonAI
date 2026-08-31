# ADR-0198 — Teacher targets are complete contingent policies

Status: Accepted for Issue #605 (2026-08-31).

## Context

The deprecated Bellman planner cannot define current teacher behavior. A within-turn search must
share the Turn Search Environment, hidden-information boundary, chance semantics, and Ledger leaf
value used by the current experiment stack. Chance means one turn may have no single action sequence
that represents every reached branch.

## Decision

The Within-Horizon Teacher is an offline, fixed-perspective traversal from one Experiment Root.
Player and forced decisions maximize expected absolute Ledger leaf value; exact or sampled Chance
Expansions back up probability-weighted expectation. Search ends only at turn end, terminal state,
Information Boundary, or an explicit safety cap.

The teacher target is a Contingent Turn Policy. Root action values and the chosen policy retain every
primitive choice by Search State Key. Principal variation and best full sequence are diagnostics;
the latter exists only when one path can represent the result. Incomplete or unavailable coverage
cannot produce a preferred action or training target, and no fallback substitutes for missing work.

Search is deterministic under structural budgets, versioned configuration, stable chance and tie
seeds, complete-result memoization, and active-path cycle detection. Wall-clock replay uses completed
node count. Batch execution may run independent Experiment Roots in isolated processes, but one root
remains single-process; worker count never changes search identity or result ordering.

## Consequences

The first build owns one single-root search seam plus a process-based batch seam. Safety limits are
versioned inputs rather than policy hidden in the traversal. Any cap, cycle, worker failure, or
incomplete successor stays typed and benchmark-visible rather than being silently promoted into
teacher evidence. Certification requires a validated frozen one-ply Ledger Baseline.
