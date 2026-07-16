# Tier 3 — Match Objectives (Prize Path · KO Race · Phases)

**Status: ~75% complete** (built 2026-07-05, `/tdd`; joint objectives A/B **50%** CI 48–53, 0
crashes, 2000 games — Battle Result #57 — switches default ON; the live `a21472` blunder gate is
GREEN). Design in [ADR-0040](../adr/0040-match-judgment-is-per-turn-closed-form-objectives.md).
Gives every turn match-scale intent — computed fresh each turn, never a lock.
**Upstream:** board + deck knowledge (T0), KO/damage math (compendium), T4's γ-gated predicted
opponent bodies.
**Downstream:** conditions T1's rungs (targets), promote/bench/develop scoring (T0 weights via new
Board signals), derived phases, T5 features, T6 trigger.

## Final design (ADR-0040)

- **T3.1 Prize Path, two-sided, per turn**: enumerate assignments of KOs over the other side's KO-able
  bodies whose prize values ({1,2,3} = regular/ex/Mega-ex, verified `docs/rules.md` §6) sum to the
  remaining prizes — MY cheapest feasible acquisition path over their board, and THEIR cheapest
  path over mine. Feasibility weight per KO from KO-Race turns + replacement likelihood. ≤6 bodies
  a side ⇒ trivial subset-sums. Mild **stickiness** (path-switch penalty) buys coherence without
  commitment.
- **Path Denial (part of T3.1)** — the "force 7, not 6": bench discipline (never gift the body completing their
  ≤6 route), promote order (interpose generalized: the absorbed KO should sit OFF their cheapest
  path), KO-priority on their path-critical attackers.
- **T3.2 KO Race** — closed-form turns-to-KO both directions: my best attack **sequence** vs a standing
  wall (damage accumulation; riders/snipes credited when they land on Prize-Path targets — the
  `a21472` fix: 2×Jetting+Nebula = 450 ≥ 440 in the same 3 turns as any order, so the 100 bench
  chip onto Riolu breaks the tie), and their sequence vs each of my bodies (Survival Window
  generalized). Opponent-static per computation; recomputed every turn.
- **T3.3 Derived phases — advisory, never gates** (contract from the 2026-07-05 phase grilling):
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

## Built (the 75%) — 2026-07-05

- **T3.2 KO Race** (`common/strategy/objectives.py` `race_values` + `_race_attack_tactical`, switch
  `objectives_race`, ON): wall attacks priced by the best min-turn SEQUENCE (`hp/t★` + own chip +
  tempo-discounted rest-chip, bench-pool-capped) — **the live `a21472` blunder is a green gate**
  (REQ-OBJ-0001: the shipped Pilot picks Jetting on the captured state).
- **T3.1 Two-sided Prize Path** (`prize_paths` + `_path_signals` → five Board fields:
  `my_path_turns` / `their_path_turns` / `race_ahead` / `path_target_ids` / `their_path_my_ids`),
  always-on data, re-derived per decision; consumers behind `objectives_path` (ON):
  `snipe-on-the-path` (+12), `dont-bench-onto-their-path` (−10, the "force 7" brake, REQ-OBJ-0006),
  the planner key-threat on-path bump (+25 sub-prize).
- **T3.3 Derived advisory phases** (`_derive_phase`, switch `objectives_phases`, ON): STABILIZE via the
  race Schmitt trigger (enter ≤ −1 / exit ≥ +1, REQ-OBJ-0007), CLOSE at payoff-online + ≤2 prizes;
  the two small `baseline_phases` bands are the ONE sanctioned `board.phase` consumer.
- **The gate-ban migration**: all 24 `c.plan` rule sites migrated to the real signals
  (`Board.line_ready` / clause drops — provably ≡, suite-verified) and a permanent lint guard
  (REQ-OBJ-0008) bans `c.plan` from every rule module. `Context.plan` now carries the derived
  phase (trace-visible).
- **The T4 overlay** (ADR-0040 §5): Read-predicted attackers join `_their_turns_to_ko` behind the
  γ-CONTINUOUS deploy lead `ceil(2/γ)` (REQ-OBJ-0009 — γ→0 byte-identical to visible-only).
- Substrate (pre-existing): interpose promote, `_prize_value` KO weighting, key-threat rung,
  Incoming/Survival Window, forward-doom.

## Gap to final (the 25%)

1. **Stickiness term** on the path choice (oscillation unobserved so far; phases carry the only
   hysteresis today).
2. **Trace line** printing the two live cheapest paths + race delta each turn (the signals exist;
   the writeup-grade line doesn't yet).
3. Promote-side path term (interpose keeps prize-economy; an explicit off-their-path driver).
4. Fresh prize-race failing example for deeper denial (`b4649` remains covered — never regress it).
5. Phase-ablation A/B as a RECURRING invariant (first pass rode the joint objectives A/B).

## Acceptance — met 2026-07-05

`a21472` green through the real Pilot (REQ-OBJ-0001); suite 1269 green (incl. hysteresis + band +
lint-guard gates REQ-OBJ-0007/0008); joint A/B 50% (CI 48–53, Battle #57) and the post-overlay
consumer A/B **52%** (CI 50–54, Battle #59), both 0 crashes → all three switches ON.
