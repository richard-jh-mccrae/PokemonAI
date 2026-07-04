# Tier 6 — Escalation Search

**Status: ~10% complete** (2026-07-05). The narrow, budgeted engine tree for the one thing
closed-form provably cannot see: **opponent choice**. Demoted by this grilling from "the" multi-turn
answer (old M3) to the last-resort residue handler — KO-Race arithmetic (T3) now owns the dominant
multi-turn case.
**Upstream:** T3's tie/ambiguity signal (trigger), T4's predicted opponent zones (reply model),
T5 leaf (when built).
**Downstream:** overrides the T1 choice only when it triggers AND completes within budget.

## Final design

- **Trigger, not always-on**: fires only when the closed-form layers cannot discriminate —
  KO-Race tie within ε at attack choice, or an opponent-choice-dominated board (disruption /
  gust / heal density flagged from Function Tags + Brief). Everything else never pays a step.
- **Mechanics**: depth 2–3 over the Engine Search (`search_begin/step/end/release`); my nodes drive
  real candidate lines; opponent nodes play the γ-gated predicted deck's plausible replies (T4) —
  verdicts trusted per the prediction-invariance rule (prefer conclusions robust across the
  overlay's uncertainty).
- **Budget = hard invariant**: per-move step cap derived from measured `search_step` cost
  (~0.1 ms) against the 10-min match bank; the T1/T0 answer is computed FIRST and returned
  unconditionally on exhaustion — never-crash/never-timeout is structural, not aspirational.
- **Leaf** = T5 value model when present, closed-form scalar otherwise.
- Tier-1 telemetry keys (tree depth/branches, reserved since ADR-0019) get wired here.

## Built (the 10%)

The Engine Search API wrapper (`cg/api.py`); a real multi-step search **driver** — the lethal
verifier's cascade drive (`_engine_confirms_win` walks my selects through the policy to the
engine's verdict) and `_simulate_line` (auto-coin end-of-turn sim) in `planner.py`; measured step
cost; reserved telemetry schema.

## Gap to final (the 90%)

1. Trigger predicate (T3 tie signal + opponent-choice board flag).
2. Opponent-reply generation from the T4 overlay (bounded: promote/attach/attack/gust classes).
3. Budget accounting across the match (per-move cap + global bank guard).
4. Telemetry wiring; A/B at the chosen budget.

## Acceptance

Zero triggers on plain boards (cost stays zero); on trigger fixtures the tree completes or falls
back inside the cap; playability holds (0 crash/timeout across an A/B run); M1 A/B ≥ T1-only on
close-line fixtures.
