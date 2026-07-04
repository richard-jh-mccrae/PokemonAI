# Tier 3 — Match Objectives (Prize Path · KO Race · Phases)

**Status: ~10% complete** (2026-07-05). Design accepted in
[ADR-0040](../adr/0040-match-judgment-is-per-turn-closed-form-objectives.md). Gives every turn
match-scale intent — computed fresh each turn, never a lock.
**Upstream:** board + deck knowledge (T0), KO/damage math (compendium), T4's γ-gated predicted
opponent bodies.
**Downstream:** conditions T1's rungs (targets), promote/bench/develop scoring (T0 weights via new
Board signals), derived phases, T5 features, T6 trigger.

## Final design (ADR-0040)

- **Prize Path, two-sided, per turn**: enumerate assignments of KOs over the other side's KO-able
  bodies whose prize values ({1,2,3} = regular/ex/Mega-ex, verified `docs/rules.md` §6) sum to the
  remaining prizes — MY cheapest feasible acquisition path over their board, and THEIR cheapest
  path over mine. Feasibility weight per KO from KO-Race turns + replacement likelihood. ≤6 bodies
  a side ⇒ trivial subset-sums. Mild **stickiness** (path-switch penalty) buys coherence without
  commitment.
- **Path Denial** — the "force 7, not 6": bench discipline (never gift the body completing their
  ≤6 route), promote order (interpose generalized: the absorbed KO should sit OFF their cheapest
  path), KO-priority on their path-critical attackers.
- **KO Race** — closed-form turns-to-KO both directions: my best attack **sequence** vs a standing
  wall (damage accumulation; riders/snipes credited when they land on Prize-Path targets — the
  `a21472` fix: 2×Jetting+Nebula = 450 ≥ 440 in the same 3 turns as any order, so the 100 bench
  chip onto Riolu breaks the tie), and their sequence vs each of my bodies (Survival Window
  generalized). Opponent-static per computation; recomputed every turn.
- **Derived phases — advisory, never gates** (contract from the 2026-07-05 phase grilling):
  `Plan` becomes a pure function of the objectives — behind-in-race + their-path-imminent →
  **STABILIZE** (denial/heal/wall bands up); my-path ≤2 prizes or lethal-adjacent → **CLOSE**
  (force the line, deprioritize long-horizon development); else SETUP→RACE as today. The label
  carries only small, **confidence-scaled** weight bands — a **gate ban** forbids `plan == X`
  rule eligibility (existing SETUP/RACE gates migrate to readiness signals via Alignment Passes);
  the label is **hysteretic** (anti-oscillation) while the continuous terms react same-turn;
  derivation is memoryless so transitions run backwards freely; a **phase-ablation A/B** (label
  off ⇒ within noise) is a permanent invariant. Deck Strategy keeps its readiness
  parameterization. STABILIZE/CLOSE stop being dead enum values.
- **Epistemic tier**: exact arithmetic under the standing-board assumption — same class as
  Incoming/Survival Window. Where opponent CHOICE dominates, T6 escalates; the objective itself
  never locks (the phantom-lethal mistake at match scale).

## Built (the 10%)

Interpose cheap-attacker promote (prize-economy drivers + never-1 veto); `_prize_value` weighting in
KO scoring; key-threat rung (T1); Incoming + Survival Window (the single-body KO-Race cases);
`active_doomed` forward-doom; STABILIZE/CLOSE vocabulary in `strategy.py`; prize-value table
verified in rules.md.

## Gap to final (the 90%)

1. **Path enumerator** (both sides) + feasibility weights + stickiness; `Board` exposure for rule
   vocabulary.
2. **KO-Race sequence solver** (attacks × target × horizon ≤4 turns; riders credited on-path).
3. **Denial terms** in bench/promote/target scoring (generalizes interpose, keeps its veto).
4. **Phase derivation** replacing `choose_plan`'s readiness-only logic (Score-Diff-gated where
   neutral, A/B'd where not) + hysteresis + confidence-scaled bands + the gate-ban migration of
   existing `plan`-keyed rules to readiness signals.
5. `a21472` becomes a green REQ gate (the definition-of-done in
   [deferred-multi-turn-criticals.md](../todo/deferred-multi-turn-criticals.md)); mine a fresh
   prize-race failing example for the denial side (`b4649` is covered — do not regress it).
6. Trace: print the two live cheapest paths + race delta each turn (writeup-grade).

## Acceptance

`a21472` gate green through the real Pilot; corpus non-regression; phases fire on fixtures
(behind→STABILIZE, ≤2→CLOSE; hysteresis holds on an oscillation fixture); **phase-ablation A/B
within noise** (the not-load-bearing invariant); M1 A/B ≥50%, 0 crashes; trace shows
paths/race/phase rationale.
