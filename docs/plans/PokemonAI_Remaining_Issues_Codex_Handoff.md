# PokémonAI Policy-Guided Turn Search
## Codex Handoff for GitHub Issue Creation and Implementation

> Historical handoff. Bounded PUCT replaced the proposed exhaustive Teacher; Teacher-specific
> issues and acceptance criteria below are retired as of 2026-09-04.

**Repository:** `richard-jh-mccrae/PokemonAI`  
**Purpose:** Create the remaining GitHub issues, link their dependencies, and implement them in order.  
**Competition boundary:** **Issue 11 is the explicit stopping point for the Kaggle Pokémon AI Strategy Competition submission.**

---

# 1. Instructions to Codex

## 1.1 Before creating anything

1. Read the repository's current `CONTEXT.md`, `CONTEXT-MAP.md`, applicable ADRs, and `.agents/skills`.
2. Inspect existing issues before creating new ones.
3. Do **not** duplicate or replace:
   - `#584` — route every post-pregame runtime decision through Ledger;
   - `#585` — emit versioned ML-ready Ledger decision and outcome telemetry;
   - `#586` — build a lossless validated Ledger training corpus;
   - `#587` — tracker for retiring dead code and making Ledger ML-ready.
4. Treat `#584–#587` as the prerequisite infrastructure program.
5. Verify current repository names, modules, labels, and deck identifiers rather than trusting stale prose.

## 1.2 Issue-creation procedure

1. Create Issue 1, the tracker.
2. Create Issues 2–17 in the order listed below.
3. Capture each returned GitHub issue number.
4. Update the tracker with a dependency-ordered checklist linking every child issue.
5. Update every child body so `Depends on` references use actual GitHub issue numbers.
6. Use existing repository labels only. Suggested labels in this document are advisory.
7. Make Issue 11 visibly and unambiguously the competition cutoff:
   - include `Competition submission cutoff` in the title;
   - state in the body that closing Issue 11 means the submission is ready;
   - ensure Issues 12–17 do not block it.
8. Do not start implementing post-submission Issues 12–17 until Issue 11 is closed, unless the user explicitly changes the priority.

## 1.3 Architectural invariants

- The tuned one-ply Ledger is the initial:
  - policy prior source; and
  - leaf state evaluator.
- Do **not** restore the retired 175-feature action decider as a second policy system.
- Do **not** restore the deprecated Bellman runtime into live `src/`.
- The deprecated Bellman code may supply:
  - historical tests;
  - edge cases;
  - algorithmic ideas;
  - a temporary reference result where it still runs.
- The new exhaustive teacher and bounded search must share:
  - one current primitive turn-search environment;
  - the current Ledger evaluator;
  - current action identities;
  - current chance semantics;
  - current information boundaries;
  - current legal-view state contract.
- `cgpy` owns controlled counterfactual execution.
- Policies and value evaluators consume legal `ObservationState`, never hidden `GameState`.
- Uniform-prior bounded search is a mandatory control.
- The deep teacher is a **teacher-relative reference**, not a claim of complete game-theoretic optimality.
- Competition evidence must include failures, uncertainty, and limitations.

---

# 2. Program Context

The project has passed through three important stages:

1. A manually corrected linear feature agent became strong quickly, but required extensive human/LLM feature work and transferred poorly to a substantially different deck.
2. A Bellman-style turn planner found stronger multi-action sequences, but searches of roughly 10–90 seconds, repeated 1–4 times per turn, could exceed the ladder's ten-minute match limit.
3. The current one-ply Ledger consolidates approximately 175 strategic concepts into one canonical, tunable, deck-agnostic valuation system.

The next experimental question is:

> Can the tuned one-ply Ledger be repurposed as a soft policy prior so bounded turn search approaches a deep within-horizon teacher faster than uniform-prior search?

The intended competition comparison is:

```text
A. Repeated greedy one-ply Ledger

B. Deep exhaustive-within-horizon teacher search
   + Ledger leaf evaluation

C. Bounded PUCT
   + uniform prior
   + Ledger leaf evaluation

D. Bounded PUCT
   + Ledger-derived prior
   + Ledger leaf evaluation
```

All four systems must begin from controlled, identical start-of-turn roots when doing turn-level comparisons.

---

# 3. Dependency Overview

```text
Existing prerequisites:
#584 → #585 → #586
  \       |       /
          #587
            ↓
Issue 2: freeze Ledger baseline
Issue 3: deterministic cgpy snapshots
            ↓
Issue 4: primitive turn-search environment
            ↓
Issue 5: chance and whole-hand EV semantics
          /   \
         ↓     ↓
Issue 6: deep teacher
Issue 7: Ledger-derived prior
          \   /
           ↓
Issue 8: bounded PUCT
           ↓
Issue 9: branching/search optimization
           ↓
Issue 10: four-way A–D turn benchmark
           ↓
Issue 11: paired-seed match validation and writeup
          ★ COMPETITION SUBMISSION CUTOFF ★
           ↓
Issue 12: search-teacher telemetry/corpus
           ↓
Issue 13: policy/value representation
           ↓
Issue 14: learned P and V
           ↓
Issue 15: generation/league training
          / \
         ↓   ↓
Issue 16: adaptive match-clock budget
Issue 17: hidden-information multi-turn search
```

Issues 2 and 3 may proceed in parallel after the prerequisite program is stable.

Issues 6 and 7 may proceed in parallel after Issues 4 and 5.

---

# 4. Issue Specifications

---

## Issue 1 — Tracker: Build and validate policy-guided turn search

### Phase

Program tracker spanning competition and post-submission work.

### Objective

Coordinate the implementation and validation of bounded policy-guided multi-ply turn search on top of the ML-ready Ledger infrastructure.

### Central hypothesis

> A tuned, deck-agnostic one-ply Ledger can serve as a soft policy prior so bounded search approaches a deep within-horizon teacher more efficiently than uniform-prior search, while remaining compatible with the match clock.

### Required tracker structure

The tracker must contain two clearly separated phases.

#### Competition phase

Issues 2–11:

- freeze and document the current three-deck Ledger;
- build deterministic `cgpy` counterfactual roots;
- define a primitive turn-search environment;
- implement reproducible chance handling;
- implement a deep teacher;
- derive Ledger priors;
- implement bounded PUCT;
- optimize measured branching bottlenecks;
- run the four-way A–D turn benchmark;
- run limited paired-seed match validation and produce submission artifacts.

#### Post-submission phase

Issues 12–17:

- extend telemetry/corpus for search targets;
- define policy/value inputs;
- train learned P/V;
- add generation-based distillation and opponent leagues;
- learn match-clock budget allocation;
- extend search to hidden information and opponent turns.

### Tracker rules

- Issue 11 must be marked as the explicit competition cutoff.
- Issues 12–17 must not block Issue 11.
- The tracker must link the actual created child issue numbers.
- The tracker must describe the dependency spine.
- The tracker must state that the old feature decider and deprecated Bellman runtime are not to be restored into production.
- The tracker must distinguish implemented results from planned learning work.

### Acceptance criteria

- Every child issue is linked in dependency order.
- Competition and post-submission phases are visibly separate.
- Issue 11 is labeled in prose as the submission stopping point.
- Tracker status can be determined entirely from its child checklist.
- Closing Issue 11 is sufficient to declare the competition package ready.
- Closing the tracker requires completion of all 17 issues.

### Suggested labels

Use existing equivalents of:

- `architecture`
- `status:2-spec`

---

## Issue 2 — Freeze a reproducible three-deck one-ply Ledger baseline

### Phase

Competition-critical.

### Depends on

- Existing `#584–#587`.

### Objective

Establish the final one-ply Ledger baseline used by all later search comparisons.

### Problem

The Ledger is still being tuned using the historical corrections corpus and targeted human blunder correction. Search experiments will be invalid if the evaluator changes during comparison.

### Scope

1. Resolve the three authoritative deck definitions from the current repository.
2. Run each deck with the one-ply Ledger as the sole post-pregame decision maker.
3. Emit and inspect:
   - every decision;
   - every legal option;
   - absolute and delta values;
   - feature/component decomposition;
   - selected action;
   - forced/fail-safe status;
   - decision time;
   - terminal outcome.
4. Perform a limited, explicitly recorded final round of blunder correction.
5. Re-run:
   - the historical correction corpus;
   - cross-deck regression suites;
   - native-provider and `cgpy` full-game tests.
6. Create a held-out evaluation set that was not used to tune the final weights.
7. Freeze and record:
   - commit SHA;
   - feature schema version;
   - Ledger evaluator identity;
   - global weight/configuration hash;
   - deck overlay hashes;
   - corrections-corpus version;
   - held-out corpus manifest;
   - random seeds;
   - test results.
8. Define a policy for newly discovered blunders during the A–D experiment:
   - record them;
   - do not silently retune the frozen baseline;
   - only create a new baseline version through an explicit decision.

### Required outputs

- A baseline manifest in a stable repository path.
- A concise baseline report per deck.
- A held-out turn/state manifest.
- A machine-readable version identity consumed by later benchmark records.
- A list of known baseline weaknesses.

### Acceptance criteria

- All three decks can complete representative matches using only the common Ledger decision path.
- No post-pregame decision bypasses the Ledger contract.
- Every baseline decision is reproducibly linked to its configuration and weights.
- Held-out evaluation turns are separated from tuning turns.
- Final corrections improve the declared tuning target without unreported regressions.
- A single immutable baseline identity is available for Issues 6–11.
- Later experiments can fail if a different Ledger version is accidentally used.

### Out of scope

- Multi-ply search.
- Learned policy/value models.
- Continuing indefinite manual tuning during the benchmark phase.

### Suggested labels

- `enhancement`
- `testing`
- `status:2-spec`

---

## Issue 3 — Build deterministic `cgpy` counterfactual experiment snapshots

### Phase

Competition-critical.

### Depends on

- Existing `#584–#587`.
- Coordinate with the repository's existing saved-moment/replay infrastructure rather than creating a parallel loader.

### Objective

Create exact, seed-controlled start-of-turn roots that can be forked into A–D counterfactual runs.

### Problem

The four methods must begin from the same complete engine state and RNG state. Reconstructing only from `ObservationState` can lose turn markers, attachment order, effect-chain state, hidden zones, or randomness state.

### Scope

1. Define a versioned `ExperimentSnapshot` containing at least:
   - complete `cgpy` game state;
   - complete RNG state;
   - root legal-view `ObservationState`;
   - turn and decision identifiers;
   - player/seat;
   - deck identities;
   - engine/schema/code versions;
   - originating episode/replay metadata where available.
2. Support:
   - in-memory `Engine.fork()` use;
   - persistent snapshot save/load;
   - validation after load;
   - deterministic re-forking.
3. Add an A–D root factory:
   - create four independent engine forks;
   - prove they initially share the same full state and RNG state;
   - prove advancing one fork does not alter another.
4. Enforce hidden-information discipline:
   - the harness may hold full engine truth;
   - decision algorithms receive only legal-view observations.
5. Add paired-seed full-match support:
   - same initial seed set across methods;
   - seat swaps where valid;
   - recorded initial setup identity.
6. Record the distinction between:
   - identical start state/RNG;
   - identical future randomness, which is not guaranteed after action paths consume randomness differently.
7. Add parity gates for all cards/effects used in the selected three-deck experiments.
8. Validate representative snapshots against native-engine traces.

### Common-random-number requirement

Search chance sampling must not depend on traversal order.

Define keyed sample seeds conceptually from:

```text
experiment seed
root state key
node state key
action identity
sample index
chance schema version
```

The same branch/sample must produce the same outcome in uniform-prior and Ledger-prior search even if the traversal order differs.

### Acceptance criteria

- A saved snapshot reproduces the same legal root and full engine state after reload.
- Four forks begin identical and evolve independently.
- Decision code cannot access hidden engine truth through the public search contract.
- Keyed chance samples are independent of search visitation order.
- Paired-seed full matches can be launched reproducibly.
- All experiment cards/effects have declared `cgpy` parity coverage.
- Snapshot incompatibilities fail closed with useful diagnostics.

### Out of scope

- General-purpose replay storage redesign.
- Learned belief models.
- Claiming identical downstream randomness after policies diverge.

### Suggested labels

- `enhancement`
- `testing`
- `architecture`

---

## Issue 4 — Define a primitive turn-search environment

### Phase

Competition-critical.

### Depends on

- Issue 3.
- Current legal-view state and decision contracts from the prerequisite program.

### Objective

Expose the primitive state transitions required for true multi-action search.

### Problem

The current one-ply preview may greedily resolve follow-up menus internally. A real turn planner must see choices such as discards, search targets, bench targets, attachments, and forced menus as searchable nodes.

### Required interface

Create or adapt a minimal search environment with operations conceptually equivalent to:

```text
legal_actions(node)
transition(node, action)
observation(node)
actor(node)
node_kind(node)
is_terminal(node)
is_turn_boundary(node)
is_information_boundary(node)
state_key(node)
fork(node)
```

### Node kinds

At minimum:

- player decision;
- forced decision;
- chance;
- terminal;
- information boundary;
- turn boundary;
- unavailable/incomplete state.

### Scope

1. Operate one level below greedy one-ply action pricing.
2. Expose forced follow-up decisions as explicit nodes.
3. Preserve stable action identities across:
   - runtime;
   - search;
   - telemetry;
   - replay.
4. Define perspective and actor semantics:
   - same player may make many consecutive primitive actions;
   - do not flip value perspective after every tree depth;
   - chance nodes do not own strategic choices.
5. Define explicit information boundaries:
   - shuffle/draw;
   - random reveal;
   - turn transition;
   - opponent decision;
   - unsupported hidden-information transition.
6. Define canonical state identity suitable for:
   - memoization;
   - transpositions;
   - deterministic traces.
7. Keep full `GameState` internal while exposing legal observations to policy/value code.
8. Port relevant test cases from deprecated Bellman tests without importing deprecated production modules.
9. Cover representative multi-step cards and menus from all three decks.

### Acceptance criteria

- Ultra Ball-style multi-step choices appear as separate searchable decisions.
- Search can traverse a complete deterministic turn sequence without invoking the greedy decision policy for internal nodes.
- State transitions match normal `cgpy` execution.
- Actor/perspective behavior is explicit and tested.
- Information and turn boundaries are typed and reproducible.
- Canonical state keys are stable for semantically identical states.
- Hidden state is inaccessible through the public policy/value interface.
- No live source imports from `deprecated/`.

### Out of scope

- Choosing PUCT parameters.
- Learned P/V.
- Multi-turn hidden-information search.

### Suggested labels

- `architecture`
- `enhancement`
- `status:2-spec`

---

## Issue 5 — Implement reproducible chance nodes and whole-hand expected value

### Phase

Competition-critical.

### Depends on

- Issues 3 and 4.

### Objective

Give the teacher and bounded searches correct, deterministic chance semantics.

### Problem

Shuffle/draw and other random actions must be evaluated by expected downstream value, not by the luckiest sampled result or only the probability of hitting one desired card.

### Scope

1. Add exact finite outcome enumeration where practical:
   - coin flips;
   - small discrete random choices;
   - small bounded combinations.
2. Add deterministic keyed sampling for large outcome spaces.
3. Make samples invariant to search traversal order.
4. Support probability-weighted backup:
   - chance nodes average;
   - decision nodes optimize.
5. Implement whole-hand expected-value evaluation for hand-changing effects:
   - sample complete resulting hands;
   - continue search from each hand;
   - average resulting values.
6. Preserve existing hypergeometric calculations as exact probability components where appropriate.
7. Compare:
   - simple hit/miss approximation;
   - complete-hand outcome evaluation.
8. Ensure all opportunity costs enter the successor state:
   - Supporter consumed;
   - old hand replaced or shuffled;
   - deck composition changed;
   - newly drawn cards available;
   - later actions legal from the successor.
9. Add deterministic tests for cards such as Lillie's Determination and Harlequin using current repository card identities.
10. Add chance sample budgets and explicit incomplete-status handling.
11. Document that chance sampling is engine simulation, not access to future hidden truth.

### Acceptance criteria

- The same branch/sample key produces identical outcomes across search algorithms.
- Exact outcome tests match analytical probabilities.
- Expected values are probability-weighted.
- Search does not select the luckiest sampled hand.
- Whole-hand EV can choose differently from single-out hit probability in a controlled fixture.
- Chance budgets, seed identities, and sample counts appear in search traces.
- Hidden-information boundaries remain intact.
- Chance behavior is reproducible from telemetry.

### Out of scope

- Learned stochastic models.
- Full opponent-hand belief search.
- Multi-turn information-set planning.

### Suggested labels

- `enhancement`
- `testing`
- `architecture`

---

## Issue 6 — Implement an exhaustive within-horizon teacher search

### Phase

Competition-critical.

### Depends on

- Issues 4 and 5.
- Frozen Ledger baseline from Issue 2.

### Objective

Build a simple current-contract deep teacher for turn-sequence comparison and later distillation.

### Problem

The deprecated Bellman solver is coupled to retired contracts and bespoke strategy/beam logic. The competition needs a clean teacher that shares the new environment and Ledger evaluator with bounded search.

### Definition

The teacher is:

> Exhaustive or near-exhaustive traversal of the modeled within-turn tree until turn end, typed information boundary, terminal state, or explicit safety cap.

It is **not** a claim of complete-match optimality.

### Scope

1. Implement a straightforward DFS or equivalent exhaustive traversal.
2. Use:
   - canonical state keys;
   - memoization/transpositions;
   - cycle detection;
   - typed terminal/boundary handling;
   - exact/sampled chance expectation;
   - current Ledger leaf evaluation.
3. Correctly handle:
   - many consecutive actions by the same player;
   - forced menus;
   - chance nodes;
   - terminal win/loss;
   - unavailable/incomplete successors.
4. Add explicit safety controls:
   - node cap;
   - time cap;
   - chance-sample cap;
   - recursion/cycle guard.
5. Return:
   - root action values;
   - preferred first action;
   - best full sequence;
   - principal variation;
   - leaf/end-state identity;
   - node count;
   - time;
   - cache/transposition statistics;
   - completion status;
   - stop reason.
6. Mine deprecated Bellman tests for cases covering:
   - long finite turns;
   - chance expectation;
   - cycle handling;
   - terminal proof;
   - incomplete search.
7. Compare representative results against the legacy Bellman where it still runs, but do not depend on it.

### Acceptance criteria

- Teacher traverses representative full turns for all three decks.
- It exposes every primitive decision in its chosen sequence.
- Chance backups are correct and reproducible.
- Same-player perspective is handled correctly.
- Repeated runs from the same snapshot are deterministic.
- Incomplete results cannot be mistaken for complete teacher results.
- Teacher outputs are serializable and benchmark-ready.
- No deprecated production module is imported into live code.

### Out of scope

- Meeting ladder time limits.
- Learned policy/value models.
- Complex beam heuristics.
- Hidden-information opponent turns.

### Suggested labels

- `enhancement`
- `architecture`
- `testing`

---

## Issue 7 — Convert one-ply Ledger deltas into soft policy priors

### Phase

Competition-critical.

### Depends on

- Issues 2, 4, and 5.

### Objective

Turn the tuned one-ply Ledger from the final greedy chooser into the initial soft prior used by bounded search.

### Problem

The current policy seam may be uniform, while the Ledger already prices every immediate candidate. Recalculating previews or using only the greedy winner would waste work and preserve one-ply rigidity.

### Scope

1. Derive a prior from all valid one-ply candidate values/deltas.
2. Support configurable normalization methods, beginning with:
   - temperature-scaled softmax;
   - probability floor / uniform mixing.
3. Preserve nonzero probability for ordinary legal actions.
4. Never create a one-hot prior from only the Ledger winner.
5. Define behavior for:
   - negative values;
   - unavailable candidates;
   - forced single-action menus;
   - exact ties;
   - large score ranges;
   - incomplete chance evaluation.
6. Avoid duplicate action preview/evaluation:
   - consume already-priced candidates where possible;
   - revise the policy interface if required.
7. Emit policy evidence:
   - raw Ledger delta;
   - normalized score;
   - final prior;
   - temperature;
   - floor/mixing coefficient;
   - evaluator/config identity.
8. Keep a uniform policy implementation for the control experiment.
9. Add tests showing that:
   - the Ledger prior initially favors the greedy choice;
   - PUCT can still discover another action;
   - all priors are finite and normalized.
10. Define the bootstrap dual role:
    - Ledger-derived `P0(a|s)`;
    - Ledger leaf `V0(s)`.

### Acceptance criteria

- Every legal candidate receives a valid normalized prior.
- No ordinary candidate is permanently excluded by zero probability.
- Prior construction reuses existing Ledger pricing rather than duplicating preview work.
- Uniform and Ledger prior modes share one interface.
- Prior evidence is available in telemetry.
- Tests prove search can override an incorrect Ledger prior.
- The old 175-feature decider is not restored as a parallel policy.

### Out of scope

- Learned policy networks.
- Policy training.
- Claiming Ledger scores are calibrated win probabilities.

### Suggested labels

- `enhancement`
- `architecture`
- `status:2-spec`

---

## Issue 8 — Implement bounded policy-guided PUCT turn search

### Phase

Competition-critical.

### Depends on

- Issues 4–7.

### Objective

Implement the primary bounded, anytime turn-search algorithm for the competition comparison.

### First-version scope

The first version is deliberately narrow:

- current player's turn;
- stops at turn end or typed information boundary;
- current Ledger as leaf evaluator;
- uniform or Ledger-derived prior;
- fixed node/time/chance budgets;
- deterministic experimental mode;
- no learned P/V;
- no opponent-turn information-set search.

### Required edge statistics

At minimum:

```text
P — policy prior
N — visit count
W — accumulated backed-up value
Q — W / N
```

### Scope

1. Implement PUCT selection.
2. Expand one primitive action at a time through the turn-search environment.
3. Evaluate new leaves with the frozen Ledger.
4. Back values up with correct perspective:
   - no automatic sign flip after every primitive action;
   - flip/minimize only when control passes to an opponent in later extensions;
   - chance nodes average.
5. Support:
   - node budget;
   - wall-clock budget;
   - chance sample budget;
   - explicit stop reason;
   - deterministic tie-breaking.
6. Return:
   - chosen root action;
   - root visit distribution;
   - root `Q` values;
   - principal variation;
   - planned full sequence;
   - node/time statistics;
   - convergence snapshots;
   - incomplete/complete status.
7. Re-root and replan after actual action execution.
8. Record planned sequence versus executed sequence.
9. Support tree reuse when state identity proves compatible.
10. Ensure the algorithm is anytime:
    - it must always have a valid best-known action after initial expansion.
11. Add tests for:
    - policy override;
    - same-player multi-action backup;
    - chance backup;
    - deterministic replay;
    - budget interruption;
    - forced menus;
    - terminal states.

### Root decision policy

For deterministic evaluation, choose the highest-visit root action with a defined tie-break.

Do not use self-play temperature sampling in the competition benchmark unless explicitly configured.

### Acceptance criteria

- PUCT finds complete within-turn sequences.
- Uniform and Ledger prior differ only in the supplied prior.
- Fixed-seed runs are reproducible.
- Search respects every configured budget.
- Search can return a valid answer before exhausting the budget.
- Root visits, `Q`, priors, and principal variation are emitted.
- Replanning after execution is correct.
- Search can overturn the one-ply greedy Ledger action in a controlled fixture.
- No hidden engine state enters policy or value evaluation.

### Out of scope

- Learned P/V.
- Progressive widening unless immediately required for correctness.
- Opponent-turn search.
- Information-set particles.
- Gumbel search.

### Suggested labels

- `enhancement`
- `architecture`
- `status:2-spec`

---

## Issue 9 — Optimize turn search for Pokémon branching

### Phase

Competition-critical, but optimization follows a correct minimal PUCT.

### Depends on

- Issue 8.
- Benchmark fixtures from Issues 2 and 3.

### Objective

Reduce redundant branching and improve bounded-search efficiency without changing semantics.

### Rule

Profile first. Add each optimization only with measured evidence.

### Scope

1. Instrument branching by:
   - menu/context;
   - card/effect;
   - action type;
   - depth;
   - chance node;
   - deck.
2. Implement canonicalization for action-order-equivalent states.
3. Add transposition tables keyed by canonical semantic state.
4. Add cycle detection and repeated-state handling.
5. Add tree reuse across executed actions.
6. Identify mechanical permutations that can be safely collapsed:
   - independent action ordering;
   - equivalent discard order;
   - equivalent selection ordering.
7. Add progressive widening when profiling demonstrates too many legal children.
8. Add double progressive widening for chance outcomes only if required.
9. Preserve a small nonzero path for low-prior actions.
10. Implement a simple policy-guided beam or best-first search baseline using the same environment/evaluator.
11. Compare:
    - correctness;
    - teacher agreement;
    - nodes;
    - wall time;
    - memory;
    - stability.
12. Avoid embedding card-name or deck-specific pruning branches.

### Acceptance criteria

- Every optimization has before/after benchmark evidence.
- Canonically equivalent paths share state work.
- Transposition use cannot mix incompatible hidden or perspective states.
- Search results remain deterministic in evaluation mode.
- Progressive widening, if enabled, is configuration-controlled and tested.
- Beam/best-first baseline uses the same priors and leaf evaluator.
- No optimization silently removes legal strategically distinct actions.
- At least one representative high-branching turn shows measurable improvement.

### Out of scope

- Learned search budget.
- Gumbel AlphaZero.
- GPU batching.
- Hidden-information opponent search.

### Suggested labels

- `performance`
- `enhancement`
- `testing`

---

## Issue 10 — Build and run the four-way A–D turn-search benchmark

### Phase

Competition-critical.

### Depends on

- Issues 2–9.

### Objective

Run the core experiment across multiple held-out turns from each of the three decks.

### Systems under test

```text
A. Repeated greedy one-ply Ledger

B. Deep exhaustive-within-horizon teacher

C. Bounded PUCT with uniform prior

D. Bounded PUCT with Ledger-derived prior
```

### Experimental unit

One saved start-of-turn `cgpy` snapshot:

```text
same complete state + same RNG state
           |
    fork A / B / C / D
```

Each method follows its own trajectory after the common root.

### Required budgets

Run bounded C and D at a small fixed sweep, initially:

```text
250 ms
1 second
3 seconds
5 seconds
```

Also record node-based budgets where useful so machine speed is not the only comparison.

### State selection

1. Select turns before seeing method results.
2. Use consecutive eligible held-out turns from predetermined games where practical.
3. Exclude only with explicit reasons:
   - forced single-action turn;
   - corrupt/incomplete snapshot;
   - unsupported `cgpy` behavior;
   - invalid parity state.
4. Target approximately 15–25 nontrivial start-of-turn states per deck, subject to documented feasibility.
5. Stratify after selection:
   - opening/setup;
   - midgame development;
   - behind/comeback;
   - prize-race/lethal;
   - high-branching draw/search;
   - low-branching/simple.

### Root versus trajectory comparison

Once first actions differ, later states are no longer direct A/B comparisons.

Report separately:

- root choice from identical state;
- planned principal variation;
- executed trajectory with replanning;
- final end-of-turn state.

### Required metrics

#### Decision/search metrics

- first-action agreement with teacher;
- top-k root agreement;
- teacher-relative regret;
- root visit distribution;
- root `Q` values;
- chosen-line stability by budget;
- nodes expanded;
- leaf evaluations;
- chance samples;
- cache hits;
- transpositions;
- wall time per decision;
- wall time per turn;
- median, p90/p95, maximum.

#### Sequence/state metrics

- exact sequence agreement;
- planned versus executed sequence;
- canonical final-state agreement;
- strategically equivalent final state;
- final Ledger value and decomposition;
- objective end-of-turn facts.

#### Objective board-state facts

At minimum, where applicable:

- prizes taken;
- KO achieved;
- damage placed;
- active attacker readiness;
- next-attacker readiness;
- viable attacker count;
- usable attached energy;
- stranded/wasted energy;
- bench prize liabilities;
- hand size;
- live cards in hand;
- Supporter used;
- attachment used;
- remaining opportunities.

### Teacher-relative regret

Define and document:

```text
teacher value of teacher action
minus
teacher value of tested method's action
```

Do not call this true optimal regret.

### Required outputs

- machine-readable raw results;
- deterministic run manifest;
- summary tables;
- compute-quality curves;
- teacher-agreement curves;
- per-deck breakdown;
- selected success cases;
- selected failure cases;
- known limitations.

### Acceptance criteria

- Every method starts from the same validated root per turn.
- C and D differ only by policy prior.
- B, C, and D share environment, chance semantics, and Ledger leaf value.
- All three decks have multiple held-out turns represented.
- Results are reproducible from manifests.
- No cherry-picked-only analysis is presented.
- Circularity is acknowledged because Ledger supplies both D's prior and B–D leaf values.
- Objective state facts and teacher comparisons supplement Ledger final scores.
- The benchmark identifies where the Ledger prior helps, does not help, or hurts.

### Out of scope

- Definitive universal win-rate claims.
- Learned P/V.
- Full hidden-information multi-turn planning.

### Suggested labels

- `testing`
- `research`
- `enhancement`

---

## Issue 11 — Competition submission cutoff: Run paired-seed match validation and produce Strategy Competition evidence

### Phase

Competition-critical final issue.

### Depends on

- Issue 10.
- All Issues 2–10 required for the chosen final experiment.

### Explicit stopping rule

> **Closing this issue means the PokémonAI project is ready for the Kaggle Strategy Competition submission. Issues 12–17 are post-submission work and must not block this issue.**

### Objective

Test whether turn-level search improvements plausibly translate into match play, then produce the complete competition submission package.

### Scope

1. Define a predetermined paired-seed match set.
2. For each relevant method:
   - use the same initial seed set;
   - use the same deck matchup;
   - use the same fixed/frozen opponent where appropriate;
   - swap seats where valid.
3. At minimum compare:
   - repeated greedy one-ply Ledger;
   - selected bounded Ledger-prior search configuration.
4. Include uniform-prior and/or teacher configurations where compute permits.
5. Record:
   - wins/losses;
   - prizes/score;
   - turn count;
   - terminal reason;
   - total match time;
   - decision-time distribution;
   - search nodes;
   - failures/timeouts;
   - seed and seat.
6. Treat the match sample as a sanity validation if statistically small.
7. Produce final competition evidence:
   - architecture diagram;
   - method description;
   - A–D turn results;
   - compute-quality curves;
   - strategic end-state examples;
   - full-match sanity results;
   - limitations;
   - reproducibility instructions;
   - code/data/version manifest.
8. Clearly distinguish:
   - implemented competition system;
   - future learned policy/value roadmap.
9. Avoid presenting standard PUCT as the innovation.
10. Frame the contribution around:
    - auditable cross-deck Ledger valuation;
    - deep search as teacher;
    - Ledger-derived soft priors;
    - bounded sequence search under a hard clock;
    - deterministic `cgpy` counterfactual evaluation.
11. Create the final submission artifact in the format required by the competition.
12. Freeze/tag the submission code and archive experiment artifacts.

### Minimum report claims

The writeup may claim only what the evidence supports, such as:

- Ledger prior reaches teacher-like choices faster than uniform search on the tested turn corpus;
- bounded search improves selected strategic end states over repeated one-ply greed;
- deep teacher quality is too expensive for live use;
- the bounded configuration fits or approaches the match-clock requirement;
- results transfer across the three tested decks to the measured extent.

### Required limitations section

Include at least:

- deep teacher is horizon- and evaluator-bounded;
- Ledger prior and leaf evaluator share bias;
- sample size is limited;
- full-match evidence may be exploratory;
- learned P/V is not yet implemented;
- hidden-information multi-turn search remains future work;
- `cgpy` parity is limited to validated experiment coverage.

### Acceptance criteria

- Paired-seed match runs are reproducible.
- Runtime failures and timeouts are reported.
- Turn-level and match-level evidence are internally consistent.
- Final figures/tables can be regenerated.
- Submission code is frozen and identified.
- Competition artifact is complete and honest.
- Issue body contains a final checklist verifying every required artifact.
- Closing the issue is the explicit authorization to stop competition development and submit.

### Out of scope

Everything in Issues 12–17.

### Suggested labels

Use existing equivalents of:

- `competition`
- `milestone`
- `research`
- `status:2-spec`

---

# Post-Submission Issues

---

## Issue 12 — Extend telemetry and corpus records with search-teacher targets

### Phase

Post-submission.

### Depends on

- Issues 10 and 11.
- Existing `#585–#586`.

### Objective

Extend the ML-ready decision corpus so it can train and audit policy, value, and search-budget models.

### Scope

Add versioned records for:

- root policy priors;
- raw Ledger deltas;
- root visits;
- `N`, `W`, and `Q`;
- principal variation;
- chosen and alternative action paths;
- teacher root values;
- teacher completion status;
- search budget and stop reason;
- convergence snapshots;
- shallow/deep disagreements;
- planned versus executed sequence;
- leaf valuation;
- final outcome;
- model/policy/search identities;
- state and action schema versions.

Define targets for:

```text
policy target
value target
budget/convergence target
teacher confidence
```

### Requirements

- Preserve every legal root action.
- Preserve legal-view boundaries.
- Do not store hidden engine truth as model input.
- Allow full deterministic reconstruction of teacher targets.
- Make disagreement reports derived views, not storage filters.
- Support prioritized re-search queues.
- Add corpus health metrics for missing/incomplete search targets.

### Acceptance criteria

- Search runs join cleanly to decision and terminal records.
- Policy/value targets are reproducible.
- Incomplete teacher results are distinguishable from complete targets.
- Schema migration/rejection behavior is explicit.
- Hidden-information leak tests remain green.
- A small end-to-end fixture creates trainable P/V examples.

### Out of scope

- Selecting neural architecture.
- Training the final models.

---

## Issue 13 — Define a cross-deck policy/value input representation

### Phase

Post-submission.

### Depends on

- Issue 12.
- Current `ObservationState` and card-function registries.

### Objective

Create a model input representation that can transfer across decks and new cards without consuming hidden simulator truth.

### Scope

1. Encode legal observation state:
   - active/bench structure;
   - hand/deck/discard/prize knowledge;
   - attached cards/energy;
   - damage/status;
   - turn allowances;
   - player-to-act perspective;
   - opponent belief summaries.
2. Encode deck context.
3. Encode cards using:
   - identity embedding;
   - structured mechanics;
   - role/function information;
   - type/stage/HP/cost/damage;
   - effects and restrictions;
   - prize liability;
   - evolution/dependency links.
4. Encode legal actions with stable parameterization.
5. Support variable numbers of:
   - cards;
   - actions;
   - board entities.
6. Preserve compatibility with future cards:
   - unknown identity handling;
   - structured mechanic fallback;
   - schema versioning.
7. Define model masks for legal actions.
8. Add invariance tests:
   - irrelevant ordering;
   - hidden truth changes;
   - seat/perspective normalization.
9. Produce dataset adapters from the Issue 12 corpus.
10. Create held-out deck/card splits for transfer evaluation.

### Acceptance criteria

- No hidden engine truth enters the input.
- All legal actions can be encoded and masked.
- Equivalent observations encode equivalently under defined invariances.
- New/unknown card identities have a valid structured fallback.
- Three current decks and held-out cards pass representation tests.
- Dataset generation is deterministic and versioned.
- Representation size and inference cost are measured.

### Out of scope

- Final network architecture tuning.
- Self-play league orchestration.

---

## Issue 14 — Train the first learned policy and value models

### Phase

Post-submission.

### Depends on

- Issues 12 and 13.

### Objective

Train the first shared cross-deck `P(a|s)` and `V(s)` models from deep-search and match-outcome supervision.

### Policy target

Use deep-search evidence such as:

- normalized root visits;
- teacher action-value distribution;
- stable top-action ranking;
- teacher confidence.

Do not train only on the final chosen action where richer evidence exists.

### Value target

Combine:

```text
deep teacher state estimate
+
terminal match outcome
```

with confidence-aware weighting.

Later experiments may add n-step or TD targets.

### Scope

1. Implement a baseline model suitable for available CPU/GPU hardware.
2. Train one shared model across all current decks.
3. Produce:
   - policy loss;
   - value loss;
   - calibration metrics;
   - held-out deck/card results.
4. Compare:
   - uniform prior;
   - Ledger prior;
   - learned P;
   - Ledger V;
   - learned V;
   - blended variants.
5. Add configurable blending:
   - manual/Ledger prior plus learned P;
   - Ledger leaf value plus learned V.
6. Evaluate search at fixed node/time budgets.
7. Measure whether learned P/V reduce required search.
8. Add frozen model/version artifacts.
9. Prevent training/validation leakage by snapshot/episode grouping.
10. Report calibration by deck, matchup, and game phase.

### Acceptance criteria

- Learned P beats uniform on held-out teacher agreement.
- Learned V has measured calibration and improves over a trivial baseline.
- Search can consume learned models without changing environment semantics.
- Model artifacts are versioned and reproducible.
- Blending weights are configuration, not hard-coded.
- No regression is hidden by aggregate-only metrics.
- A frozen learned checkpoint can be evaluated against the competition Ledger baseline.

### Out of scope

- Full league training.
- Learned adaptive budget.
- Hidden-information multi-turn search.

---

## Issue 15 — Add generation-based search distillation and opponent-league training

### Phase

Post-submission.

### Depends on

- Issue 14.

### Objective

Create an iterative training system in which search improves play, and improved play generates stronger policy/value targets.

### Scope

1. Implement generation-based workflow:
   - freeze current learner;
   - generate self-play/cross-play;
   - select states for deeper re-search;
   - train candidate generation;
   - evaluate;
   - promote/reject.
2. Maintain an opponent pool:
   - current checkpoint;
   - previous checkpoint;
   - older strong checkpoints;
   - historically difficult checkpoints;
   - deck specialists.
3. Train across:
   - mirror matches;
   - cross-deck matches;
   - held-out evaluation decks.
4. Add prioritized experience/re-search:
   - P versus teacher disagreement;
   - V versus teacher disagreement;
   - unstable search;
   - surprising outcome;
   - novel mechanics/state.
5. Track catastrophic forgetting.
6. Define promotion gates:
   - win rate against frozen pool;
   - teacher agreement;
   - V calibration;
   - runtime/search efficiency;
   - no unacceptable cross-deck regression.
7. Keep deterministic manifests for:
   - seeds;
   - model versions;
   - corpus versions;
   - opponent sampling.
8. Support CPU parallel match workers and later GPU batched inference/training.
9. Measure compute-hours per generation.

### Acceptance criteria

- A full generation can be reproduced.
- Candidate promotion is automatic and testable.
- Opponent pool prevents evaluation only against the immediately previous model.
- Cross-deck metrics and forgetting metrics are mandatory.
- Prioritized re-search demonstrably focuses teacher compute.
- Failed candidate generations are retained with diagnostics.
- At least one promoted generation improves a frozen benchmark without unacceptable regressions.

### Out of scope

- Information-set opponent-turn search.
- Final large-scale distributed training cluster.

---

## Issue 16 — Add adaptive match-clock search budgeting

### Phase

Post-submission.

### Depends on

- Issues 12, 14, and preferably 15.
- Competition benchmark data from Issue 10.

### Objective

Allocate search time according to decision difficulty and remaining match clock.

### Initial approach

Begin with an explicit rule-based controller using recorded search signals.

Later, train a budget model `B(s)` if data supports it.

### Candidate inputs

- remaining match time;
- turn number;
- branching factor;
- policy entropy;
- top-prior gap;
- top-`Q` gap;
- shallow/deep disagreement history;
- convergence rate;
- value uncertainty;
- chance-node count;
- game/prize leverage;
- forced/simple menu status.

### Scope

1. Define match-level budget accounting.
2. Guarantee a valid action before deadline.
3. Support:
   - near-zero search for obvious choices;
   - short search for normal choices;
   - deeper search for critical/uncertain turns.
4. Add stop/continue criteria based on expected improvement.
5. Record budget decisions and reasons.
6. Benchmark:
   - fixed per-decision budget;
   - fixed per-turn budget;
   - adaptive budget.
7. Train `B(s)` from convergence histories only after rule-based behavior is stable.
8. Enforce hard safety reserve for protocol/latency overhead.
9. Test worst-case high-branching matches.

### Acceptance criteria

- No evaluated match exceeds the configured hard search-time budget.
- Obvious decisions consume less search than difficult decisions.
- Adaptive budgeting improves or preserves strength at equal total match time.
- Budget decisions are reproducible in deterministic mode.
- Remaining-clock behavior is monotonic and safe.
- Search always returns a valid action on interruption.
- Learned budget work, if added, has a fixed-rule baseline.

### Out of scope

- Hidden-information multi-turn search.
- General cluster scheduling.

---

## Issue 17 — Extend PUCT to hidden-information and multi-turn planning

### Phase

Post-submission long-term.

### Depends on

- Issues 14 and 15.
- Issue 16 where match-clock allocation is required.
- Stable belief/observation infrastructure.

### Objective

Extend within-turn PUCT into selective multi-turn information-set search without hidden-information leakage or strategy fusion.

### Scope

1. Key public search nodes by legal observation/information set.
2. Maintain belief particles or sampled hidden worlds consistent with observations.
3. Add root sampling for hidden state.
4. Add opponent response nodes using the same side-to-move P/V system.
5. Correctly model:
   - our maximize nodes;
   - opponent minimize/own-maximize nodes;
   - chance expectation;
   - turn-boundary perspective.
6. Prevent strategy fusion:
   - current root action cannot depend on sampled hidden facts unavailable to the player.
7. Add re-determinization or equivalent opponent-model safeguards where required.
8. Search selectively through:
   - our current turn;
   - opponent strong/plausible responses;
   - our continuation;
   - learned V thereafter.
9. Use policy priors and widening to restrict opponent branching.
10. Compare:
    - implicit long-horizon V only;
    - one-opponent-turn search;
    - deeper selective search.
11. Add belief calibration and hidden-information correctness tests.
12. Record sampled-world and information-set diagnostics without leaking them into model inputs.

### Acceptance criteria

- Changing only hidden simulator truth does not change the root public state input.
- Root decisions aggregate correctly across sampled hidden worlds.
- Opponent decisions cannot exploit hidden facts unavailable to that opponent.
- Strategy-fusion regression fixtures fail before the fix and pass afterward.
- Chance and perspective backups remain correct across turns.
- Multi-turn search improves selected tactical/strategic cases under a bounded budget.
- Match-clock controller can cap the added cost.
- All hidden-information diagnostics are separated from legal policy/value inputs.

### Out of scope

- Claiming full game-theoretic equilibrium.
- Full CFR solution of the complete card game.
- Unbounded full-match tree search.

---

# 5. Tracker Checklist Template

After creating all issues, replace placeholders with actual GitHub issue numbers:

```markdown
## Competition phase

- [ ] #NNN — Freeze a reproducible three-deck one-ply Ledger baseline
- [ ] #NNN — Build deterministic cgpy counterfactual experiment snapshots
- [ ] #NNN — Define a primitive turn-search environment
- [ ] #NNN — Implement reproducible chance nodes and whole-hand expected value
- [ ] #NNN — Implement an exhaustive within-horizon teacher search
- [ ] #NNN — Convert one-ply Ledger deltas into soft policy priors
- [ ] #NNN — Implement bounded policy-guided PUCT turn search
- [ ] #NNN — Optimize turn search for Pokémon branching
- [ ] #NNN — Build and run the four-way A–D turn-search benchmark
- [ ] #NNN — **Competition submission cutoff:** paired-seed match validation and Strategy evidence

## Post-submission phase

- [ ] #NNN — Extend telemetry and corpus records with search-teacher targets
- [ ] #NNN — Define a cross-deck policy/value input representation
- [ ] #NNN — Train the first learned policy and value models
- [ ] #NNN — Add generation-based search distillation and opponent-league training
- [ ] #NNN — Add adaptive match-clock search budgeting
- [ ] #NNN — Extend PUCT to hidden-information and multi-turn planning
```

---

# 6. Implementation Priority Rule

Codex should implement in dependency order and preserve a runnable system after every issue.

The competition path is:

```text
baseline
→ deterministic roots
→ primitive environment
→ chance semantics
→ teacher/prior
→ minimal PUCT
→ measured optimizations
→ A–D benchmark
→ paired-seed validation/writeup
→ STOP AND SUBMIT
```

Do not allow the following to delay Issue 11:

- neural policy/value architecture debates;
- league training;
- learned budget allocation;
- information-set opponent-turn search;
- Gumbel search;
- GPU optimization;
- broad card-pool generalization beyond the validated experiment decks.

The post-submission roadmap begins only after the competition package is complete.
