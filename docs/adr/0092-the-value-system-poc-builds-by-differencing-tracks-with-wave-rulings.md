# ADR-0092 — The Value System POC builds by differencing tracks with wave rulings

Date: 2026-08-01 · Status: accepted · Issue: the POC restructure grill (2026-07-31/08-01)
· Plan: `docs/plans/value-system-poc-plan.md` · ⚠️ number claimed at authoring time — renumber
at merge if collided (tracker directive 8; six collisions in five days as of 2026-07-30).

## Context

The Issue #136 phase list was correct but serial: one issue → one grill → one build, with a
per-swap paired A/B plus per-deletion rulings (directive 6). Measured against the remaining
scope (finish Phase 1, Turn Planner, `state_value`), the user ruled the cadence unaffordable
("going one task at a time is taking forever"), and a five-sweep source audit (2026-07-31) found
whole weight-driven families with no owning issue at all (the ~45-rung fetch ladder, heal, tools,
stadium, draw economy).

## Decisions

1. **Scope cut.** The POC ends at the Turn Planner + `state_value` (old Issues #165/#145,
   merged). Learning phases (Issues #146–#148), depth-2 (Issue #150), slowking (Issue #149) and
   decline-a-prize (Issue #190) are post-POC.
2. **Hybrid differencing.** Built bespoke marginals stay the deciders for their seams. Every
   still-weight-driven family is priced as `state_value(after) − state_value(before)` by the Turn
   Planner through a closed-form apply-seam; stochastic effects price as hypergeometric
   expectation, never engine-shuffle samples. A play that changes state no term reads prices 0 —
   the term registry (T0) owns coverage, and the audit's map is its checklist.
3. **Verification regime for POC tracks (amends ADR-0072's mid-build rule, these tracks only).**
   The paired A/B tripwire is dropped; the two deterministic gates and the suite remain
   mandatory per track; corpus flips batch into ~3 wave ruling packets the user rules
   frame-by-frame. Baselines re-capture only on rulings — never automatically. Post-POC work
   returns to ADR-0072 as written.
4. **No shadows, no fallbacks.** Every swap is the deletion (tracker directive 1, now applied
   retroactively to the pre-tracker legacy): the six shadow emitters, the v1 discard fallback,
   and the dark deny flags' OFF paths are removed by their owning tracks. A parity check may
   exist only as a test fixture, never a runtime path.
5. **Six tracks, contract-first.** T0 freezes three contracts (`state_value` term registry +
   currency rules; StateModel completion API; apply-seam), then T1 (substrate) ∥ T2 (Phase-1
   finish) beside the critical path T3 (`state_value`) → T4 (Turn Planner) → T5 (purge +
   integration). After T0 merges, a contract changes only by a wave-packet ruling.
6. **Currency honesty.** The Worth↔prize rate remains underived (ADR-0080's measurement stands).
   The single authored scaffold `POC_WORTH_PRIZE_RATE` lives module-local to `state_value`, is
   ratified in wave 1, is whitelisted as authored-not-derived, and is retired by the post-POC
   learning phases. It never enters `common/currency.py`.

## Consequences

- The user's steering surface is three touches: wave rulings, optional PR review, and a ≤2-budget
  escape hatch for genuine doctrine forks.
- The sound-rule whitelist (plan §6) becomes the only legitimate home for non-equation rules;
  everything tuned outside it is deleted by its owning track.
- Absorbed issues close with supersession comments (plan §8); Issue #136 gains a POC section
  pointing at the six track issues.
