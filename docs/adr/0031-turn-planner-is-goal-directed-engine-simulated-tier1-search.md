# ADR-0031: The Turn Planner is a goal-directed, engine-simulated whole-turn optimizer (Tier-1 Search)

**Status.** Accepted (grilled 2026-07-01, `/grill-with-docs`). **Extended by
[ADR-0037](0037-lethal-solver-is-the-turn-planners-top-rung.md) (2026-07-03): the "subsumes the
Lethal Solver" claim becomes literal — the win goal is the Planner's in-module sound top rung, the
two entry points merge, and `TurnLine` becomes the one line type (wire format preserved).** **Implemented 2026-07-01** (`/tdd`, TDD):
the **Turn Planner** ([planner.py](../../src/common/strategy/planner.py), `PlannerMixin`/`TurnLine`
composed into the Pilot, running after the Lethal Solver and before the tuned scoring). Built the whole
ladder: **(0)** the cost spike measured `search_step`≈0.1 ms → ~0.05 ms/line → **always-engine-sim** (no
selective-escalation code); **(1)** the **KO-for-prizes** goal — multi-step enabling lines (retreat into a
benched attacker, evolve the Active, or **play an energy-tutor Supporter** — Hilda, `tutor_energy` — that
fetches into hand the attachable Energy the line lacks, then this turn's one attach) that unlock a KO the
greedy scorer misses, gated **layer-on-top** (only when no status-quo KO exists), which caught the `7f48`
/ `4298` shapes; **(2)** the **leaf-eval scalar** (prizes dominant + survival vs a glossary-faithful **Incoming** +
threat removed), with the hard-rung invariant (a positional score can never outrank a prize); **(3)** the
**Engine-Search** primitive (`_simulate_line` / `_engine_leaf_value`) that steps a candidate then re-runs
the policy on each intermediate `SearchState` to my end-of-turn board, proven to round-trip a real
observation; **(4)** the **turn-scoped committed-plan cache** + re-plan-on-reveal + a reentrancy guard so a
sim never nests a search, with the engine sharpening the committed line's value. Also built the **stabilize-then-KO** goal (heal a doomed Mega ex to full with a `clutch_heal`, bounce its
Energy, re-attach, still take a NON-winning KO — fires despite a status-quo KO, unlike the layer-on-top
KO-for-prizes gate; the winning-KO case stays owned by the Lethal Solver upstream). Gated by
`REQ-PLANNER-0001..0023` ([tests/strategy/test_planner.py](../../tests/strategy/test_planner.py),
[tests/strategy/test_planner_engine.py](../../tests/strategy/test_planner_engine.py)); the verdict rides in Decision
Telemetry (`planned`). Verified on real games (6 mirror games, 0 crashes, the Planner committing + engine-
ranking live) AND on the actual replay states of the CRITICALs that named the feature: **all three
in-scope CRITICALs are FIXED and gated as real-state regressions** — `7f48` (retreat→attach→KO for 2
prizes), `0cbc` (heal-then-KO), and `4298` (play Hilda for the energy grab → retreat → Jetting-Blow KO)
([tests/fixtures/corrections/](../../tests/fixtures/corrections/)); the two multi-turn corrections
(`a21472`, `b4649`) remain out of scope — captured, re-measured, and fixtured for a future session in
[docs/todo/deferred-multi-turn-criticals.md](../todo/deferred-multi-turn-criticals.md) (`a21472` is still a
live gap; `b4649` re-measured as already covered by tuned scoring).

**Amended 2026-07-02 (wiring pass) — three deferred pieces built, each kill-switched
(`Strategy.params`, ADR-0021 pattern; OFF until the arena A/B clears them):**
**(a) Multi-candidate engine RANKING** (`planner_engine_rank`, REQ-PLANNER-0026..0029, 0034): the
closed-form rungs now emit ALL candidates (`_closed_form_candidates`); with the switch ON every
candidate forward-sims to its end-of-turn board and the ENGINE leaf value picks the committed line
(`_commit_best`). A candidate whose sim fails keeps its closed-form value on the same leaf scale
(decision 7, per candidate); when even the best ranked value falls below one prize the pool's
premise failed in sim and the Planner DEFERS — the natural veto, resolving the "veto-and-replan vs
rank" fork in ranking's favor because the sim is trusted for ranking, never as a per-line guarantee
(coins auto-resolve to one sample). Provenance rides in telemetry (`planned.ranked` = engine/closed
+ `planned.diverged` vs the closed-form pick — the A/B divergence signal); plan-once-cache holds
(N sims per reveal, not per decision). OFF = the closed-form pick with value-sharpening, exactly
the pre-amendment behavior.
**(b) The KO-the-key-threat rung** (`planner_key_threat`, REQ-PLANNER-0031/0032): ENABLING lines
(retreat / evolve-the-Active / energy-tutor Supporter) that unlock a bench-snipe KO of the benched
TOP-threat body — ranked by the shared `_body_threat_rank`, the select-independent core extracted
from the snipe threat rank so MAIN-menu planning and DAMAGE-select sniping order the bench
identically. A snipe-KO already ON the menu needs no rung (the Tactical layer credits its prizes
KO_SCORE-class — measured during this build, which is also why a "direct" rung would be vacuous);
the STEP that reaches one was scored by no hook. Candidates join the KO-for-prizes pool under the
same layer-on-top gate; the leaf scalar ranks across rungs (prizes dominant, then threat removed).
**(c) The development leaf term** (decision 4's fourth term, exercised): `_board_development` — my
end-of-turn bodies + attached Energy, read off the SIM board — feeds `_PLANNER_DEV_W`, capped
(`_PLANNER_DEV_CAP`) so the positional sum stays below one prize (REQ-PLANNER-0033). Engine-rank
phase only: closed-form candidates keep development 0, so the term rides (a)'s switch.

**Remaining (deferred, per the build ladder):** tagging the
sibling energy-tutors beyond Hilda (a card-data sweep — 22 other cards search an Energy into hand) and the
evolve-via-Supporter variant of the same line; enabling-step snipe lines that need TWO steps
(gust-up-then-snipe); the full selective-override *margin*
comparison (commit only when a line **clearly beats** the status-quo develop line by engine-sim value) is
tuning-gated on the M1 A/B ladder, so v1 ships the conservative "otherwise-missed KO" gate; the develop-order fold-in / full unification; the **Base Value Model**
([ADR-0007](0007-learning-is-one-offline-value-model.md)) leaf-eval upgrade; and all multi-turn planning
(`a21472`, `b4649`). **Realizes** the designed **Tier-1 Search** / M3 of
[ADR-0008](0008-pilot-is-a-layered-rules-pipeline.md); **generalizes**
[ADR-0030](0030-winning-this-turn-is-an-eager-engine-verified-lethal-solver.md) — the **Lethal Solver
is the win-goal special case and the sound top rung** of the Planner. Terms in
[src/common/CONTEXT.md](../../src/common/CONTEXT.md): *Turn Planner*, *Turn Goal*, *Turn Line* (alongside
*Lethal* / *Lethal Line*).

**Context.** After the Lethal Solver shipped, the most-recent corpus shifted from "a rule was missing"
to **multi-decision, whole-turn sequencing** misplays — several tagged **CRITICAL** and naming the
feature outright: *"another multi decision example showing that we need a turn planner system… retreat
Cinderace into Mega Starmie, attach 3rd energy, KO Fezandipiti for 2 prizes"* (`7f48cbe86e8c`); *"needs
to start planning its turn ahead of time, mapping out potential outcomes, and then picking best path…
KO via Hilda for energy grab, attach, retreat, jetting blow"* (`4298b98d39e8`); *"Should have healed
with Wally, attached single energy, KO opponent"* (`0cbc478f2d86`). This is **exactly M3's documented
entry trigger** — the roadmap ([docs/todo/roadmap-search-posture-learning.md](../todo/roadmap-search-posture-learning.md))
says Tier-1 activates when "corrections become 'an extra ply would have caught it' (multi-step tactical)
rather than 'a rule was missing.'" The agent decides greedily per-option; nothing plans a whole turn.

What already exists (≈60 % scaffolded): the Sense→Plan→Score→Act pipeline; `_finish_turn_last` (today's
*coarse* turn-sequencer — tiers 0-4); the **Engine Search** (`search_begin`/`search_step`, proven to
round-trip a real observation, ADR-0030); the Tier-0 `_tactical` score; and the board signals a
leaf-eval needs (`_prize_value`, **Incoming**/**Survival Window**/`active_doomed`, snipe/forward-evo
threat rank). Net-new: candidate-line **generation** across goals, **engine-simulation** of a whole
line to end-of-turn, and a **board-state leaf evaluation**. Cost context measured in the grill: ~1 ms /
decision × 20-50 decisions/match against a ~600 s bank — *large* headroom (see *Consequences*).

Two corrections are **multi-turn**, not this-turn — `a21472f6f4d2` ("KO Lucario over 3 turns — 2 Jetting
Blows and a Nebula") and `b4649ba9c304` ("prize math… big brain… requires search"). Out of scope here
(they need opponent modelling + deep search + the value model), split off exactly as multi-turn
prize-math was split off the Lethal Solver.

**Decision.** Build a **Turn Planner** — the eager whole-turn optimizer that runs first each turn and
generalizes the Lethal Solver from the *win* goal to a **Goal Ladder**. Seven decisions, each the head
of a resolved trade-off (see *Considered options*):

1. **Hybrid, not pure-backward or full-tree.** A closed, prioritized Goal Ladder **generates** a few
   candidate **Turn Lines** by backward-chaining (generalizing `find_lethal_line`); the **Engine Search**
   **simulates** each to its end-of-turn board; a leaf-eval **ranks** them. Goal-directed generation *is*
   the pruning that makes it tractable and legible; the engine makes each line's outcome exact.
2. **Scope = this turn only; threat-aware leaf-eval.** Plan the current turn's action sequence; the
   leaf-eval sees 1-ply survival (**Incoming**/**Survival Window**), so the *defensive* corrections
   (heal-because-doomed) work with **no opponent-turn search**. Multi-turn is deferred.
3. **Win is a HARD rung; a scalar ranks the rest.** If a Lethal exists, take it (sound, no trade-off —
   the Lethal Solver unchanged). Below it, rank candidate lines by a **scalar** over the resulting board,
   so combined goals (heal *and* KO) and trade-offs (1 prize + safe vs 2 prizes + doomed) are
   expressible — but a positional score can **never** outrank a real win/KO (a hard override, not a big
   number — the false-lethal direction stays forbidden).
4. **Leaf-eval = hand-weighted existing signals.** prizes taken (dominant, ~`KO_SCORE`-weighted) +
   threats removed + my survival vs Incoming + development toward the win-condition. Seeded + tunable;
   the **Base Value Model (ADR-0007) is the drop-in upgrade later** ("leaf eval = Tier-0 score
   initially" — roadmap M3).
5. **Plan once, cache, re-plan on reveal.** Run the (expensive) engine-sim ranking **once** at turn
   start, cache the chosen Turn Line as **turn-scoped state**, execute it step by step, and **re-plan
   only when a search/draw reveals information** that invalidates the cache. Reconciles "a cohesive plan
   before the first decision" (the committed goal) with hidden information; "informative actions first"
   emerges. (This is the turn-scoped locked line the Lethal Solver deferred.)
6. **Selective override, layered on top.** The Planner commits a Turn Line **only when its leaf-value
   clearly beats the status-quo develop line** the existing scoring would play; otherwise it defers to
   today's Hypothesis scoring + `_finish_turn_last` **unchanged**. Lowest regression risk on the live
   tuned agent (the Lethal Solver's layer-on-top pattern); the tuned rules stay the proven default.
7. **Calibrate first; default to always-sim; never time out.** Phase-0 is a search-cost spike
   (ms/step, ms/line, projected ms/match). If cheap (expected at 1 ms/decision), **always-engine-sim**
   every candidate — no selective-escalation code. Selective escalation (closed-form rank, engine-sim
   only the uncertain lines) is the fallback **only if** the engine proves slow. A `remainingOverageTime`
   guard + the closed-form leaf-eval as a legal fallback keep the never-time-out guarantee regardless.

**Considered options.**

- **Pure backward-from-best-outcome (the human's #1), open-ended** — rejected as stated: "best outcome"
  is unbounded. Tamed by a **closed, prioritized goal set**, it becomes the generation spine of the
  hybrid. (Kept, bounded.)
- **Full forward search tree (the human's #2)** — rejected as the primary: the per-turn action space
  (items × orderings × deck-search reveals) is large, most expensive against the bank, and a black-box
  tree is the least legible for the Strategy-Category writeup. Its *mechanism* (engine simulation) is
  reused to evaluate the goal-directed candidates.
- **Shallow 2-ply (model the opponent's reply)** — rejected/deferred: multiplies cost, is far fuzzier
  (their move depends on their hidden hand), and drifts into the multi-turn problem. The threat-aware
  leaf-eval captures the defensive cases without it.
- **Rigid lexicographic goal ladder** — rejected: can't express combined goals (heal+KO) or "fewer
  prizes to stay safe" — the exact trade-offs in the corpus. A scalar below the win-rung can.
- **Pure scalar, no hard rungs** — rejected: a tuning slip could let a non-winning board outscore a
  winning one — the catastrophic false-lethal direction we made a hard override.
- **Learned Base Value Model now (ADR-0007 / M4)** — rejected for v1: heaviest, last-in-roadmap; needs
  the replay data engine; delays the feature the human needs *now*. It is the pluggable leaf-eval
  upgrade once the Planner is proven.
- **Re-derive every decision (no cache)** — rejected: re-running engine sims on each of a turn's many
  decisions blows the budget (the Lethal Solver's cheap per-call re-derivation is closed-form; this
  is not).
- **Fold-in / full-subsume the tuned core now** — rejected for v1: routing every turn through the
  Planner (or deleting `_finish_turn_last`) is a big-bang replacement of the tuned decision core on a
  live submission — high regression risk, strands the blunder-buster apparatus mid-flight. Selective
  override first; unify once proven.

**Consequences.** The Pilot gains an eager, first-class **Turn Planner** that **subsumes the Lethal
Solver** (win = its top rung) and finally exercises **Tier-1 Engine Search on normal decisions** — the
M3 seam. It gains **turn-scoped committed-plan state** (a cached Turn Line + reveal-triggered
invalidation) beside its match-scoped Scout/deck-tracker state. A **board-state leaf evaluation** is
net-new (today's score is per-option); its hand-weighted terms are the ADR-0007 value model's eventual
feature set, so the model is a clean later swap. Because it **layers on top** (selective override), the
tuned Hypothesis scoring + `_finish_turn_last` and the whole blunder-buster/tuning apparatus keep
working as the default — the Planner only overrides when a multi-step line clearly wins.

The one flagged **risk is cost**, and the grill's arithmetic makes it small: ~20 planning runs/match ×
~5 candidates × ~4 `search_step`s ≈ 400 steps/match; at ~1 ms/step that is ~400 ms of a ~600 s bank
(0.07 %). So the spike likely retires the risk and permits always-sim; the never-time-out guard is cheap
insurance regardless. Build is **incremental, TDD, ladder-gated** (the Lethal Solver playbook):
**(0)** calibrate spike → **(1)** the KO-for-prizes goal (the bulk of the CRITICALs; generalize the
lethal generator, closed-form leaf-eval) → **(2)** threat-KO + stabilize-then-KO goals → **(3)**
engine-sim verify/rank (real-battle tests) → **(4)** selective-override + turn-scoped cache +
re-plan-on-reveal, gated by ladder A/B. Deferred beyond v1: develop-order fold-in / full unification,
the value-model leaf-eval (ADR-0007), and all multi-turn planning (`a21472`, `b464`). **Built
2026-07-01** (`/tdd`) — the whole ladder (0)-(4), layer-on-top and behaviour-neutral by default; see the
Status block for the as-built record and what remains deferred.
