# Tier 6 — Escalation Search

**Status: ~55% complete** (built 2026-07-05, `/tdd`, ADR-0043; DEFAULT OFF pending its budgeted
ladder A/B). The narrow, budgeted engine tree for the one thing closed-form provably cannot see:
**opponent choice**. Demoted by the 2026-07-05 grilling from "the" multi-turn answer (old M3) to the
last-resort residue handler — KO-Race arithmetic (T3) owns the dominant multi-turn case.
**Upstream:** T3's close-attack-tie trigger; the opponent-reply proxy policy; the T5 leaf.
**Downstream:** overrides the tuned pick only when it triggers, strictly wins, AND stays in budget.

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

## Built (the 55%) — 2026-07-05, ADR-0043

- **The trigger** (`_close_attack_tie`, REQ-ESCALATE-0001): fires only on ATTACK options within
  `_ESCALATE_EPS` tactical points; a clear leader / lone attack / KO-on-menu short-circuit to no
  escalation, so plain boards pay zero.
- **Depth-2 evaluation** (`_two_ply_value` over `_simulate_line(opponent_reply=True)`): sims each
  tied attack through my turn AND the opponent's reply (our own policy as the proxy) to the start of
  my next turn, leaf = the T5 value model when present else the closed-form scalar; an opponent-reply
  WIN scores −KO_SCORE (avoid the attack that hands them the game).
- **Conservative commit**: the best two-ply attack commits only if it strictly beats the tuned
  tie-pick's own two-ply value; else defer (escalation breaks a tie, never overturns a clear pick).
- **Hard per-move budget** (`_search_steps` capped at `search_budget`; the reply sim halts when
  spent) + **never-time-out** (engine absent / slip → None → tuned pick). The Tier-1 `_simulate_line`
  path is byte-identical when `opponent_reply=False`. Committed lines ride telemetry under
  `goal="escalation"`. Gated REQ-ESCALATE-0001..0003; DEFAULT OFF.

## Gap to final (the 45%)

1. **The budgeted A/B** (escalation + a measured `search_budget` vs off) → default-ON decision;
   engine-backed trigger-fixture test (the two-ply sim is exercised via the shared `_simulate_line`).
2. **Deeper trees** (depth 3+) + a favorability-scaled budget.
3. **A real opponent-deck reply model** (vs the our-policy proxy) from the T4 overlay.
4. The opponent-choice-DENSITY trigger (gust/heal/disruption boards) beside the attack-tie trigger.

## Acceptance — met 2026-07-05 (build)

Zero triggers on plain boards (REQ-ESCALATE-0001); defers when off / no budget / no search input
(REQ-ESCALATE-0002); DEFAULT OFF on the shipped Pilot (REQ-ESCALATE-0003); the Tier-1 sim path
unchanged (full suite green). The budgeted ladder A/B remains before default-ON.
