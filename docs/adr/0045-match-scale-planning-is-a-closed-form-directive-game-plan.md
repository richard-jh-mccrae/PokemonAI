# ADR-0045: Match-scale planning is a closed-form directive Game Plan atop the Turn Planner

**Status.** Accepted (grilled 2026-07-06/07, `/grill-with-docs`) + **BUILT 2026-07-07 (`/tdd`, all four
stages S1–S4; see the Amendment).** The behavioral seams (S3 `match_planner_steer`, S4 `forgo_ko`) ship
**DEFAULT OFF, byte-identical**, wired in all three agents' `main.py` + `_build_pilot` for a params/overlay
flip — matured via the Kaggle ladder (the gauntlet is invalid). The Threat Clock (S1) and the Match
Planner synthesis + telemetry (S2) are live and compute-only. Full suite green (1366). One finding
refined the affordability claim below — see the Amendment.
**Grows** [ADR-0040](0040-match-judgment-is-per-turn-closed-form-objectives.md) — the Tier-3 Match
Objectives (two-sided Prize Path / KO Race / derived phases) become the Match Planner's primitives, not a
layer it consumes. Relates [ADR-0031](0031-turn-planner-is-goal-directed-engine-simulated-tier1-search.md)
(the Turn Planner — the executor one scope below), [ADR-0030](0030-winning-this-turn-is-an-eager-engine-verified-lethal-solver.md)
(the sound win rung that always preempts), [ADR-0043](0043-escalation-search-is-a-budgeted-depth-2-tree-on-a-close-attack-tie.md)
(the T6 engine-tree search — the **rejected** multi-turn alternative), [ADR-0044](0044-opponent-choice-residue-is-narrow-closed-form-reads.md)
(the ship-and-refine-via-ladder precedent + the Forced-Promotion Read this consumes), and
[ADR-0026](0026-posture-generic-core-is-net-new-read-levers.md)/[ADR-0027](0027-matchup-brief-is-hand-authored-opponent-doctrine.md)
(the Read/Briefs — the γ sharpener). New glossary terms *Match Planner*, *Game Plan*, *Threat Clock*, and
the *Plan* enum grown to six modes, in [src/common/CONTEXT.md](../../src/common/CONTEXT.md). **Validation
reality:** the Kaggle ladder is the only valid gain measure (the cross-deck gauntlet is invalid — mega_lucario
/ dragapult_ex are too weak to discriminate); features ship-and-refine, not A/B-gated.

## Context

The user asked for a "cohesive multi-turn planner" that identifies developing opponent threats (a benched
pre-evolution powering toward an ex/Mega, promoted via retreat/Switch) and prepares 1–3 turns ahead
(pre-snipe, pre-gust, heal early), explicitly **without** enumerating hundreds of branches — "merely
identify that here is a potential threat after 1 or 2 or 3 turns, let's prepare." The grill widened it to
its true scope: **the top of the decision hierarchy** — a match-scale strategist that maps routes to
victory (six prizes or board-out), reads incoming damage and responds (heal / sacrifice / retreat), knows
when *not* KO-ing a weak blocker buys setup time, calls the sprint, carries a **confidence**, adapts as the
opponent counters, and **outputs a turn-by-turn goal** the Turn Planner then concretizes and executes —
with the tuned weights as the fallback when both are uncertain.

Two facts framed the design:

- **The scattered status quo.** Six forward-looking reads each compute a slice of "opponent threat" and
  none cohere: `_forward_incoming_damage` (opponent **Active** evolving, one turn), `_incoming_active_damage`
  / `_active_doomed` (one turn, **affordability-blind** — credits attacks the opponent can't pay for, an
  open over-doom bug, [incoming-affordability.md](../todo/incoming-affordability.md)), `_their_turns_to_ko`
  (Tier-3, current-form damage + γ-predicted attackers on a flat lead), `_forced_promotion_key` (ADR-0044,
  **offensive** only), `_body_threat_rank` (snipe order). None models the **energy-attach clock** the user's
  "attaching the LAST energy" scenario needs; none sees a **benched** attacker powering up and being
  **Switched in** on the defensive side.

- **The epistemic boundary the codebase already drew.** Multi-turn *search* is parked: T6 (ADR-0043) was
  built and **regressed** (44 % mirror A/B); the docs repeat "plans THIS turn only." But ADR-0040 proved the
  complement: opponent-**static** multi-turn *arithmetic* (the KO Race) is sound closed-form and shipped ON.
  The user's "no branches, just project a threat and prepare" lands exactly on the proven closed-form side —
  this is **not** a revival of the search that lost.

## Decision

Build a **Match Planner**: the match-scale planner and top of the decision hierarchy, parallel to the Turn
Planner one scope up (`plan_match` : match :: `plan_turn` : turn).

1. **Three-layer hierarchy.** Match Planner (match scope, runs first each turn) → **Turn Planner** (turn
   scope, the executor — ADR-0031) → tuned weights (the well-worn fallback). Each layer defers downward when
   uncertain.

2. **Grow Tier 3; do not stack a second brain.** The Match Planner **is** the Tier-3 Match Objectives grown
   up: the two-sided Prize Path, the KO Race, the derived phases, and the new **Threat Clock** are its
   primitives. No parallel match-scale module consuming T3's five Board signals from outside.

3. **The Game Plan is a composite `{ route + mode + confidence + directed Turn Goal }`.** The **route** is a
   concrete two-sided Prize Path (which specific bodies I KO to bank my six; board-out is a route variant =
   KO-all / deny-promotion). The **mode** is the `Plan` enum grown from four to **six** — `SETUP` / `RACE` /
   `STALL` (build while declining giant-waking KOs) / `STABILIZE` / `SACRIFICE` (trade the Active, race on
   prize math — the `b4649` Cinderace-delay-wall) / `CLOSE`. Several candidate strategies are ranked and
   retained ("strategy, **or** strategies"); the top is committed.

4. **Confidence is a closed-form per-strategy feasibility scalar**, composed from primitives already trusted:
   route feasibility (my Prize-Path turns vs theirs — the KO-Race margin) · defensive survival (the Threat
   Clock: do my needed bodies outlast the incoming over the route) · Read γ. **Not** a learned win-probability
   (the Automatic Value Model, T5/ADR-0042, may later *refine* a leaf, never *be* the confidence — it is
   parked and estimates overall P(win), not "confidence in achieving THIS route"). Confidence gates the
   handoff: above threshold the Game Plan **directs**; below it the Pilot defers to the Turn Planner's own
   goal + tuned weights — the layer-on-top discipline the Turn Planner already uses.

5. **Directive via the Turn Goal seam — never via rule eligibility.** The Game Plan supplies the Turn Planner
   its top **heuristic** rung (goal-kind + target set + tempo directive), strictly **below the sound win
   rung** (a real Lethal always preempts — ADR-0030 soundness untouched). The Turn Planner concretizes it into
   a Turn Line (which cards, what order), engine-verifies, executes. **ADR-0040's gate-ban STANDS**: no rule
   keys the mode; a wrong plan biases one turn's goal, it can never silence a rule family. The Game Plan
   **never LOCKS** (the phantom-lethal-at-match-scale mistake) — it is re-derived every turn. The match-scale
   *stance* (sacrifice-vs-stabilize, stall-vs-sprint) is the mode; the turn-scale *concretization* (which
   heal card, retreat-vs-heal, attach order) stays the Turn Planner's.

6. **Memoryless re-derivation + stickiness/hysteresis.** The Game Plan is derived fresh each turn from the
   current board — so it **adapts as the opponent counters** with no explicit "they countered" detector (their
   response shifts the primitives → the confidence ranking shifts → the plan follows). Commit the top with the
   shipped `_PATH_STICKY` margin + the phase Schmitt-trigger hysteresis (anti-oscillation, the ADR-0040
   contract); retain the ranked alternates + confidences in the trace. No cross-turn plan state, no committed
   multi-turn lock.

7. **The Threat Clock — the net-new defensive primitive that unifies the six scattered reads.** A closed-form,
   opponent-static projection of *when* each opponent body could KO one of my bodies. For every opponent
   attacker — a visible current form, a form its line **forward-evolves INTO** (the Evolving Threat, inverted
   `evolvesFrom`), or a Read-predicted not-yet-benched attacker — it computes the earliest future turn it can
   **afford** a KO of a given body of mine: Energy at the verified ~1-attach/turn floor (`docs/rules.md` §4)
   plus known acceleration (`energy_accel`), evolution at one turn per hop, gated by the form's **real** attack
   cost (the effect compendium, ADR-0032) and its W/R-adjusted damage, accumulating over turns when one hit
   doesn't KO (the **Survival Window** generalized). A **benched** attacker carries a promotion surcharge
   (mirrors Prize Path's `_PATH_BENCH_EXTRA`), **reduced** when the opponent holds a promotion enabler (a
   `switch` / `gust` card revealed or Read-predicted, or a cheap/free retreat vs a stuck Active — `retreatCost`
   is a card fact) and **waived** for a true bench-snipe. Opponent-static; the Read γ-sharpens the attach rate
   and which line the opponent actually runs; **with zero Read it is pure card fact — the base fallback the
   user required.** It **subsumes** `_forward_incoming_damage` / `_incoming_active_damage` /
   `_their_turns_to_ko` / `_forced_promotion_key`, and **fixes the affordability over-doom bug**
   ([incoming-affordability.md](../todo/incoming-affordability.md)) as a side effect.

8. **Forgo-KO behind a tight sound gate (the user's "don't wake the giant" play).** The Game Plan may direct
   the Turn Planner to forgo an available **non-winning** KO — but ONLY when ALL hold: (i) the KO does not
   advance my committed Prize Path this route; (ii) their Forced-Promotion body is a **strictly worse** threat
   to me by the Threat Clock (KO-ing genuinely wakes a scarier attacker — the weak Active is shielding me);
   (iii) I have a productive develop toward my wincon to make instead; (iv) confidence is high. When ANY
   condition is unsure, **take the KO** — the refuted `forgo-ko-corrections-are-refuted` principle ("a prize is
   a prize") stays the prior. A real Lethal is never forgone (win rung preempts), so the risk is bounded to
   individual prizes. Own kill-switch, built last, default-OFF.

9. **Card-fact base, Read γ-sharpens — the fallback requirement.** The whole system runs on card facts alone
   (costs, evolution, damage, retreat, disruption tags) with zero opponent recognition; the Read/Brief only
   sharpens the attach rate and the run-this-line accuracy, γ-gated, so an unrecognized opponent moves nothing
   (structural no-regression — the ADR-0026 lever discipline).

10. **Ship-and-refine via the Kaggle ladder — not an A/B gate.** The cross-deck gauntlet is **invalid**
    (mega_lucario / dragapult_ex too weak to discriminate; the ADR-0044 problem generalized). We **must** have
    this capability, so it ships staged behind kill-switches, default-ON, and **matures via manual ladder-match
    corrections + user feedback** routed through the blunder-buster — which requires the Match Planner to emit
    **blunder-buster-parseable telemetry** into `live_trace` (committed route, mode, confidence, ranked
    alternates, directed Turn Goal, the Threat Clock read, the forgo-KO decision), mirroring the ADR-0041
    posture-observability pattern. Mirror A/B + the pytest suite + captured-blunder gates remain the
    no-regression / no-crash **floor**, never the gain gate.

## Build staircase (paused — recorded for the build go-ahead)

Each stage independently valuable and reversible; each behind a kill-switch; no stage flips behavior until the
one below is proven no-regression.

- **S1 — Threat Clock primitive.** Unify the six scattered reads into the energy-aware projection and fix the
  affordability over-doom; re-baseline the ~19 synthetic fixtures + re-verify the two CRITICAL planner gates
  (`test_critical_0cbc_*` / `test_critical_6858_*`) on their real states (the load-bearing subsystem pass the
  TODO flagged). Valuable alone (a real bug fix), behavior-first.
- **S2 — Match Planner synthesis, COMPUTE-ONLY.** Rank routes/modes, compute confidence, commit a Game Plan,
  emit the telemetry — **zero decisions change** (the M2.0 Read-wiring pattern). Verified in isolation.
- **S3 — the seam.** Wire the directed Turn Goal as the Turn Planner's top heuristic rung, behind a
  kill-switch; the win rung still preempts.
- **S4 — the forgo-KO gate.** The riskiest behavior, last, behind its own kill-switch.

## Rejected

- **Revive T6 Escalation Search into the multi-turn planner** (ADR-0043). It is branch-enumeration over
  opponent CHOICE — the opposite of the user's "no branches" ask — and it already regressed and parked; its
  unlock is the T5 leaf + a real opponent-reply model, not more tree.
- **A new match-scale layer stacked above an unchanged Tier 3.** Two brains doing match-scale reasoning →
  redundant computation and a murky "who owns the path/phase" boundary where the advisory phase and the
  directive Game Plan can disagree.
- **Make the directive a hard gate (remove ADR-0040's gate-ban / never-lock).** Re-introduces exactly the
  failure ADR-0040 earned its contract against — a wrong match-scale read silencing a rule family, and a
  match-scale lock (phantom-lethal at match scale). The tuned-weights fallback the user specified requires the
  soft handoff.
- **Confidence = the learned value model (T5).** Parked, regressed, and it estimates overall P(win) not
  per-route feasibility; it would make the whole legible hierarchy depend on the one inert learned seam.
  Allowed only as a later leaf *refinement*.
- **Broad forgo-KO whenever mode == STALL.** The refuted forgo-KO-by-vague-positional-value pattern; leaves
  free prizes on the board in ordinary races.
- **Gauntlet A/B as the gain gate.** The measuring instrument is invalid (weak decks); the ladder is the only
  valid signal. Recorded in [[gauntlet-invalid-ladder-only]].
- **Big-bang build.** If it regresses (as T5/T6 did) the compounded seam is unbisectable; the staircase keeps
  each piece measurable and revertible.

## Consequences

- **`common/strategy/objectives.py` grows into the Match Planner** (the Tier-3 module gains the synthesis head:
  strategy ranking, confidence, the Game Plan, the directed Turn Goal). The `Plan` enum (`strategy.py`) grows
  to six modes; `_derive_phase` generalizes into mode derivation.
- **The Turn Planner (`planner.py`) gains a directed-goal input** — a new top heuristic rung fed by the Game
  Plan, below the win rung; its own Goal Ladder becomes the fallback when confidence is low.
- **The six scattered forward reads fold into the Threat Clock**, re-baselining every `active_doomed` consumer
  (~19 fixtures + the two CRITICAL gates); [incoming-affordability.md](../todo/incoming-affordability.md) is
  **subsumed** (its affordability fix is the Threat Clock's energy model). The Evolving Threat forward-evo
  index and the Forced-Promotion Read (ADR-0044) are consumed, not duplicated.
- **The blunder-buster gains Match-Planner routing** (like ADR-0041 posture): a ladder misplay ties to the
  Game Plan's route/mode/confidence via `live_trace`, so a correction lands on the planner code, not a weight.
- **Shipping model = ADR-0044 generalized:** staged default-ON, kill-switched for a one-line revert, ladder-
  matured. No new A/B tooling; the gauntlet is not used.
- **The Automatic Value Model's feature set is unaffected** now; the confidence scalar is a candidate future
  refinement, not a dependency.
- **Open build-time details** (not architecture): the exact confidence weighting; the projection horizon +
  prep-lead (default: project to the KO-Race 8-turn cap, prep at ≤1–2 turns out — the user's "heal 1 turn
  ahead"); the `live_trace.game_plan` telemetry schema; board-out route mechanics.

## Amendment — BUILT 2026-07-07 (`/tdd`), and the burst-Energy finding

All four stages shipped, full suite green (1366 passed):

- **S1 — Threat Clock** (`objectives.py`: pure `threat_turns` + `_threat_clock`/`_threat_forms`/
  `_promotion_surcharge`; `tests/strategy/test_threat_clock.py`, `REQ-CLOCK-0001..0005`). Energy-aware
  (1 attach/turn, verified `docs/rules.md` §4), forward-evolution + promotion-surcharge aware, multi-hit
  accumulation; card-fact base with the compendium dual-path + hand-size fallback.
- **S2 — Match Planner synthesis, compute-only** (`plan_match`/`_derive_mode`/`plan_confidence`; the `Plan`
  enum grown to six; `GamePlan` on `Board` + `Decision` + `to_record`; `tests/strategy/test_match_planner.py`,
  `REQ-MATCH-0001..0007`). Zero decisions change — proven by the full suite.
- **S3 — the seam** (`_gameplan_goal_bonus`, sub-prize confidence-scaled bump in the planner's candidate
  ranking; kill-switch `match_planner_steer`; `REQ-MATCH-0008`). **Default OFF.**
- **S4 — forgo-KO** (`_forgo_ko_line`/`_forgo_ko_gate`/`_opp_after_forced_promote`; the tight sound gate;
  kill-switch `forgo_ko`; `REQ-MATCH-0009/0010`). **Default OFF.**

**The burst-Energy finding (refines Decision 7 + the incoming-affordability side-effect claim).** The
`active_doomed` rewire (making the survival boolean affordability-aware via the Threat Clock) was built and
**reverted**: on the two CRITICAL `stabilize_then_ko` gates (`planner_6858`/`planner_0cbc`) the opponent is a
Mega Starmie **mirror** holding **1 Energy** but a hidden **Ignition** (a 3-Energy burst) it plays next turn
to fire Nebula Beam. A naive 1-attach affordability cap reads it as *not* doomed and **re-opens the blunder**
(the agent re-picks the attach). Since the opponent's hand is hidden and under-preparing loses games, the
**survival-critical `active_doomed` stays worst-case** (Incoming reads the ceiling); the Threat Clock's
affordability model is the **multi-turn PREP read** only (off-by-a-turn is recoverable). So the ADR's
"fixes the affordability over-doom as a side effect" is **withdrawn** for the survival boolean — the
incoming-affordability.md fix is unsound as specified (it ignores hidden burst Energy). This is the one
place the build corrected the design; the Threat Clock still provides the accurate multi-turn projection the
Match Planner's confidence and prep reads consume.
