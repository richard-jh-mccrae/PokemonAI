# ADR-TEMP-606 — Policy models consume priced candidate evidence

Status: Accepted for Issue #606 (2026-08-31).

## Context

The action-only Policy Model interface cannot derive a Ledger prior without repeating work already
owned by Search. Missing candidate evidence also cannot safely be treated as low value.

## Decision

Search supplies the Policy Model with the authoritative hidden-safe Candidate Roster after pricing.
The Ledger Policy Model forms a Policy Distribution from comparable canonical Decision Deltas using
stable temperature softmax plus uniform mixing. A multi-action roster with any non-comparable value
falls back to a typed uniform distribution; a forced single action receives probability one.

Ledger prior P0 and leaf value V0 must name the same frozen Ledger Baseline, evaluator, Evaluation
Model, and Value Scale. Uniform and Ledger models share one request/result contract. Calibration uses
the frozen certified Correction evidence, which is the tuning source rather than the held-out game
partition. Baseline `98a582d49a32146b18e59beed0019041ce1745fd653e94f7d9c86f8cf0aec92d`
selects temperature `8.0` and uniform mixing `0.01`; the identified artifact records the grid,
three-deck smoke results, and zero held-out inputs. Estimated values require explicit opt-in. The
existing status model represents incomplete chance evaluation as estimated; it has no rejected
status, so unavailable and disallowed-estimated evidence are the independently typed fallbacks.

## Consequences

Prior construction performs no transitions or evaluations, every legal action retains nonzero
probability, and missing evidence cannot masquerade as a bad action. One missing value discards the
Ledger bias for that node. Issue #606 does not activate search in the live Pilot; Issue #607 consumes
the Policy Distribution and Issue #611 later owns corpus persistence.
