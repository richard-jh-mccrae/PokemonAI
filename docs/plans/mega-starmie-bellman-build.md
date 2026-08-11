# Mega Starmie Bellman build ledger

Canonical architecture: [ADR-0139](../adr/0139-mega-starmie-uses-one-bellman-style-full-turn-planner.md).

This file is the durable execution state for the build. Conversation memory and compaction summaries
are advisory only. At the beginning of every work period, read this file, the ADR, `git status`, and
the commits since the last completed milestone.

## Current

**COMPLETE: M8 — full corpus adjudication, broad validation, and closeout.**

M0 is complete. Runtime routing remains unchanged.

## Frozen decisions

- Build sequentially with one architectural owner; no implementation subagents for the kernel.
- Mega Starmie only; Mega Lucario and Dragapult remain legacy during the prototype.
- Pregame/Set-Up remains outside Bellman; starter declaration plus hard no optional setup Bench.
- Isolated complete prototype first; one atomic live cutover after all gates pass.
- No legacy strategic fallback or mixed ownership on Mega Starmie's Bellman path.
- Every legal action and nested selection is a Bellman node.
- End is exactly zero; every other action pays all consumed costs.
- Attack is terminal only after full attack resolution and forced promotion.
- Known uncertainty is an explicit distribution followed by real-state replanning.
- Scouting supplies opponent belief; it never chooses actions or targets.
- Human Worth seeds first; training is out of scope.
- Full Mega Starmie corpus, including “covered” rows, is audited without exclusions.
- Correction rationale outranks an accidentally inconsistent action label.
- Gate baselines are never rewritten without a developer ruling.

Changing a frozen decision requires amending the ADR before changing production code.

## Checkpoint protocol

For each milestone:

1. Confirm this file names that milestone as `CURRENT`.
2. Re-read its ADR sections and inspect prior-art owners named below.
3. Confirm `git status`; preserve unrelated user changes.
4. Write the milestone's failing contract tests before implementation.
5. Implement only the milestone scope. Scope growth requiring a new design decision stops for an ADR
   amendment; adjacent mechanical work may remain in the milestone and is recorded.
6. Run the milestone checkpoint, relevant existing tests, documentation checks, and `git diff --check`.
7. Record files, decisions, measurements, failures, and the exact next action under `Run log`.
8. Commit the completed milestone alone.
9. Mark it `DONE`, advance exactly one successor to `CURRENT`, and commit that ledger update with the
   successor's work or as the completed milestone's final change.

No milestone advances on a new unexplained failure. Pre-existing failures require clean-`main`
evidence or an existing recorded adjudication.

## Milestones

### M0 — inventory and executable contracts — DONE

Purpose: prove what must be modeled before selecting implementation details.

Deliverables:

- machine-generated inventory of every Mega Starmie MAIN option kind, card effect, nested selection,
  per-turn allowance, attack rider, chance source, and opponent-response node;
- prior-art map naming the nearest reusable provider and its ADR for every capability;
- new Bellman package boundary with public types only—no strategic implementation;
- executable purity/import rule and initial End-zero/action-cost contracts;
- the two Cinderace/Lillie's/Boss full-turn fixtures, initially failing at the planner boundary;
- measured current live-Pilot and complete-corpus baseline, without exclusions or recapture.

Exit: inventory has no silent “other” bucket; all gaps are named; package boundary and failing
contracts import cleanly; no runtime routing change.

### M1 — canonical state, budgets, and transition algebra — DONE

Deliverables:

- immutable decision state carrying visible board, hands/deck knowledge, turn budgets, belief, and
  value-registry identity;
- canonical action identity;
- deterministic/Choice/Chance/Terminal/Unknown transition result types;
- End, quota consumption, semantic cycle identity, and exact diagnostic schemas;
- engine-option enumeration adapter that proves legal-option parity without choosing.

Exit: every sampled Mega Starmie root option appears once with stable identity; End is exact zero;
allowances persist through successors; no tactical score is imported.

### M2 — one benefit/cost ledger and terminal board value — DONE

Deliverables:

- portable Worth resolver and upward deck overrides at the Bellman boundary;
- realized benefit, consumed cost, and continuation decomposition;
- canonical state potentials with single-owner/difference-once tests;
- game, prize, damage/KO, readiness, dependency progress, hand option, denial, survival, and mobility
  consequences;
- exact-zero End and strictly negative no-benefit card/non-card actions.

Exit: synthetic conservation tests prove no duplicated consequence and no free non-End action; all
seed constants are centralized and diagnostic.

### M3 — deterministic recursive solver — DONE

Deliverables:

- exhaustive reference recursion for deterministic MAIN actions and nested our/opponent choices;
- `max`/`min` semantics, continuation, memoization, semantic cycle prevention;
- commit-first-action/replan interface;
- root ledger containing chosen, End, and best rejected alternative;
- deterministic complete-line fixtures for attach, evolve, retreat, heal, fetch, gust, and Supporter
  opportunity costs.

Exit: reference solver finds complete deterministic turns without any legacy chooser; stopping is
chosen whenever all actions are negative.

### M4 — chance, information, Needs, and Scouting belief — DONE

Deliverables:

- complete mutually exclusive chance classes with explicit whiff mass;
- hypergeometric outcome probabilities and Needs-valued branch marginals;
- actual-state replan after reveal/shuffle/search;
- causal dependency Needs sufficient for Turbo Flare -> Staryu -> Mega Starmie;
- immutable OpponentBelief adapter from visible facts, Scouting posterior/history/Brief, and unknown
  mass;
- opponent `min` responses and denial/target counterfactuals.

Exit: probability mass is exactly one; expected policy and actual replan share one evaluator; the
60-HP Lillie's fixture passes without a card/frame exception.

### M5 — complete attack-resolution trees — DONE

Deliverables:

- attack cost/payment and full post-attack terminal transition;
- deterministic damage/effects, Active and Bench KOs, prizes, game result, and forced promotion;
- recursive Turbo Flare count/recipient and Jetting Blow target decisions;
- general allocation primitives suitable for Aura Jab and Phantom Dive without deck logic;
- opponent legal promotion enumeration as `min`, valued by OpponentBelief;
- single-payment/exact-once tests across attack riders and KO relief.

Exit: attacks are never valued on the pre-attack board; every Mega Starmie attack/nested option has
reference coverage; the 50-HP Boss/KO boundary fixture passes economically.

### M6 — complete Mega Starmie mechanic coverage — DONE

Deliverables:

- deterministic or enumerated adapters for every ordinary deck card, Ability, and nested target from
  M0;
- typed Energy, discard, shuffle, search, draw, heal/bounce, gust, denial, switch/retreat, evolution,
  and Bench-capacity parity;
- full-turn scenario matrix covering useful, redundant, and harmful uses of every function family;
- zero reachable `UNKNOWN` results in the matrix and complete-corpus replay.

Exit: isolated reference planner completes every reachable Mega Starmie correction state and scenario
without strategic legacy calls. Exact legacy agreement is reported, not fitted blindly.

### M7 — bounded production search and atomic cutover — DONE

Deliverables:

- bounded production search over the identical transition/value contracts;
- exact semantic transposition, deterministic ordering, explicit cap telemetry;
- reference-versus-production regret and runtime measurements on representative and worst corpus
  states;
- purity test with every legacy strategic chooser replaced by a raising stub;
- structural dependency audit;
- one atomic Mega Starmie routing switch; no fallback.

Exit: accepted performance/regret budget, purity green, no ordinary `UNKNOWN`, and live Pilot passes
the isolated full-turn suite.

### M8 — full corpus adjudication, broad validation, and closeout — DONE

Deliverables:

- unfiltered sweep of every Mega Starmie correction, including every row claimed covered;
- per-mismatch full ledger and one of the five ADR classifications;
- rationale-led manual adjudication of every mismatch;
- all turn-planner hard gates;
- crash-free smoke gauntlet and broad test suite;
- docs, CONTEXT/glossary, architecture map, CI routing, and finalized ADR number;
- deletion or explicit quarantine of Mega Starmie's bypassed strategic code only after reference and
  history show it has no other consumers.

Exit: zero unexplained mismatch, zero introduced broad-suite failure, no baseline recapture without a
ruling, final PR explains behavior, performance, corpus dispositions, and remaining migration work.

## Prior-art owners to inspect at M0

| capability | nearest existing owner |
|---|---|
| local benefit minus opportunity cost | ADR-TEMP-507, `common.card_worth`, `common.action_cost` |
| absolute consequence ownership | ADR-0136, `common.state_value` |
| combat/typed readiness | ADR-0137, combat profile/CombatMath |
| semantic identity/reference search | ADR-0138, Composer frontier identity/reference mode |
| current whole-turn search | ADR-0031/0037, legacy planner/lethal solver |
| option transitions/refusal | ADR-0098, apply seam and coverage report |
| causal demand | ADR-0065/0127, Needs ledger |
| information ordering/chance windows | ADR-0095/0129/0133 |
| opponent knowledge | ADR-0047 plus latest Scouting provider/artifact |
| setup | ADR-0079/0086, opening decider and `setup-never-bench` rule |
| correction interpretation | ADR-0049/0082/0087/0088/0090 |

M0 must verify these at source; this table is a route, not proof that reuse is sound.

## Run log

### 2026-08-11 — architecture checkpoint

- Added ADR-TEMP-507 for the pure Mega Starmie Bellman planner.
- Added this durable sequential build ledger.
- Runtime/source implementation: none.
- Current milestone: M0.
- Exact next action after compaction: re-read ADR + ledger, inspect source owners and deck inventory,
  then author M0's generated inventory and failing package-boundary contracts.

### 2026-08-11 — M0 inventory and contracts

- Generated `docs/plans/mega-starmie-bellman-inventory.json` from the 60-card deck and cgpy card/
  attack definition tables: 20 unique cards; every effect operation, attack rider, nested context,
  chance source, allowance, and opponent response is categorized; uncategorized operations fail.
- Recorded the source/ADR prior-art route for every neutral capability in that inventory.
- Added `common.bellman`'s public boundary, End-zero and named-consumption contracts, plus an AST
  purity test forbidding legacy strategic imports.
- Added the two Cinderace/Lillie's/Boss executable fixture cases; the unavailable planner boundary is
  a strict expected failure, never a legacy delegation.
- Added `tools/train/bellman_corpus.py` and captured an unfiltered 259-record live baseline: 0
  exclusions, 171 equivalent-aware agreements, 88 misses. Contexts: 207 MAIN and 52 nested choices.
- Checkpoint: `tests/bellman/test_m0_boundary.py` passes with only the intended strict xfail;
  inventory freshness and `git diff --check` pass. Runtime routing is unchanged.
- M1 exact next action: define immutable Bellman state/action/budget/node/diagnostic algebra, then
  adapt engine menus to stable identities without reading any legacy score or chooser.

### 2026-08-11 — M1 state and transition algebra

- Added immutable `DecisionState`, visible opponent belief with conserved probability mass, exact
  own-deck/prize counts when anchored, and explicit Supporter/attach/retreat/Ability/attack/Stadium
  budgets. Semantic identity includes every allowance, belief, hidden-zone fact, and value registry.
- Added deterministic, our-choice max, opponent-choice min, normalized Chance, Terminal, and reasoned
  Unknown node types plus stable ledger/diagnostic schemas.
- Added serial-free legal-menu enumeration. Interchangeable physical copies form one action while
  every engine menu index is covered exactly once; unresolved enum growth stays named by its number.
- Corpus parity contract walks all 259 Mega Starmie records and proves every offered root/nested index
  appears once with stable identity after a deep copy. No legacy score/chooser is imported.
- Checkpoint: M0+M1 Bellman tests pass (7 passed, one intended M0 xfail); runtime remains unchanged.
- M2 exact next action: centralize portable Worth/deck overrides, build one differenced board potential
  and consumed-resource ledger, then prove conservation and strict negativity for benefitless actions.

### 2026-08-11 — M2 value conservation

- Added the Bellman `ValueRegistry`: one portable cross-deck Worth resolver, derived line-base role,
  shared function tags, known/Basic-Energy/ACE facts, and upward-only deck overrides. Its complete
  content identity rides in every search state.
- Added one differenced `ValueOracle`. Existing neutral board families own game/prizes, damage and
  threat removal, survival, typed readiness, mobility, dependencies, persistent development, and
  denial; Bellman replaces the legacy hand family with the exact sum of portable held-card Worth.
- Every positive family delta is a realized benefit; every negative delta is a consumed cost. Each
  family is differenced once. Every consumed allowance is explicit, every non-End selection pays an
  ordinal decision cost, and End returns the empty exact-zero ledger.
- Conservation tests prove Hammer with no realized denial is strictly below End, Hammer with 0.10
  realized board benefit nets exactly that benefit minus its 6/120 portable cost, and no known
  non-End action can tie End without benefit.
- Checkpoint: Bellman + existing card-Worth/state-value suites: 162 passed, 3 expected xfails.
- M3 exact next action: implement deterministic reference recursion over engine-observation branches,
  max/min continuation, memoization/cycle prevention, commit-first-action diagnostics, and fixtures.

### 2026-08-11 — M3 deterministic recursion

- Added exhaustive reference recursion over one transition provider: our choices maximize, opponent
  choices minimize, Chance nodes expect, Terminal states stop, and Unknown/cap/cycle states remain
  incomplete instead of becoming numeric zero.
- Added memoization by full semantic state, cycle prevention, explicit depth/node caps, deterministic
  ordering, commit-only-the-first-selection output, and root diagnostics containing exact-zero End,
  chosen ledger, all rejected alternatives, branch values, node count, and cache hits.
- Legal enumeration now generates every combination from `minCount..maxCount`, grouping only truly
  equivalent physical selections; optional decline is a real empty selection.
- Added a cgpy transition provider which reconstructs a neutral engine state, forks every selection,
  preserves exact own prizes, identifies whose choice it is, and terminates only after complete attack
  resolution passes the turn. Engine errors become reasoned Unknown nodes.
- Deterministic complete-line tests cover attach, evolve, retreat, heal, fetch, gust, Supporter/card
  costs, opponent min, known chance, stop-at-End, and a real corpus MAIN-menu reconstruction.
- Checkpoint: 23 Bellman tests pass; one intended M0 xfail; live routing remains unchanged.
- M4 exact next action: turn manual coins and hidden draw/search windows into normalized outcome
  distributions, add causal Turbo-Flare demand and immutable Scouting belief, then pass the 60-HP
  attach-Water -> Lillie's expected-policy fixture with actual-state replan semantics.

### 2026-08-11 — M4 known uncertainty and beliefs

- Added exact multivariate-hypergeometric count classes over disjoint causal needs plus explicit
  remainder/whiff; every window asserts probability mass exactly one.
- Added declarative causal Needs for Turbo Flare recipient -> Staryu -> Mega Starmie, typed reusable
  Water, and evolved burst Energy. Needs emits marginal demand/rationale only and never chooses.
- Added branch-controlled cgpy randomness. Lillie's Determination, Pokégear's top-seven reveal,
  Harlequin's coin/draw split, and every manual coin now produce explicit Chance children. Coarse
  non-need draw representatives carry a conditional portable-Worth correction rather than sampled
  value; the real revealed state is replanned through the same solver.
- Added immutable Scouting posterior adapter: exact visible opponent state, normalized archetype
  probabilities, Brief properties, and explicit unknown mass. No targeting/action output crosses.
- The 60-HP acceptance fixture now chooses attach Water first and then Lillie's expectation; the
  chance branch replans after Staryu versus whiff. Engine tests prove all four real deck chance plays
  become normalized Chance nodes.
- Checkpoint: 29 Bellman tests pass, one intended M0 xfail; runtime remains unchanged.
- M5 exact next action: prove cgpy's complete attack tree as the Bellman transition, including attack
  payment, Turbo Flare allocation, Jetting target, all KOs/prizes/game results, and opponent min
  promotion before post-attack value.

### 2026-08-11 — M5 complete attack resolution

- The cgpy provider now carries its exported internal search token in semantic state. Distinct
  in-progress attack allocations can no longer collide merely because their visible boards match.
- Reference search resolves attack payment, deterministic damage, Active/Bench KOs, prizes, game
  result, Turbo Flare's zero-to-three Energy count and per-Energy recipients, Jetting Blow's snipe
  target, and the opponent's legal promotion before a terminal board is valued.
- Exact fixtures prove Turbo Flare can allocate three persistent Water, Jetting Blow takes the
  fragile Bench KO, and Nebula Beam collects three prizes before the opponent minimizes by promoting
  its stronger Mega Starmie.
- Checkpoint: 34 Bellman tests pass, one intended M0 xfail; runtime remains unchanged.
- M6 exact next action: run every M0 mechanic family and all 259 correction observations through the
  engine adapter, close every named Unknown, and add useful/redundant/harmful benefit-cost fixtures.

### 2026-08-11 — M6 complete deck mechanics

- Added a one-selection historical nested adapter for old corrections whose opaque engine frame was
  never recorded. Live search still retains and uses the exact cgpy frame; the adapter only applies
  the fully visible nested consequence and stops, without ranking targets.
- Replaced the ambiguous tuple freeze format with tagged map/list/tuple/set representations. Empty
  Energy lists can no longer thaw as dictionaries, and hidden pending-frame identity remains exact.
- Audited all 259 unfiltered Mega Starmie corrections: every provider is available and all 1,692
  offered root actions transition without Unknown.
- A representative of every deck action source recursively resolves all nested mechanics. The
  matrix covers switch, Bench deployment, fetch, discard, damage, heal, evolution source/target,
  Turbo Flare Energy selection/placement, and denial; all chance sources are explicit.
- Checkpoint: M6 mechanics tests pass in 35.5 seconds; runtime routing remains unchanged.
- M7 exact next action: add bounded search over the same contracts, measure against the reference on
  tractable states, retain live engine sessions across nested decisions, and atomically route every
  post-setup Mega Starmie selection through Bellman with raising legacy chooser stubs.

### 2026-08-11 — M7 bounded search and atomic cutover

- Added production search over the reference engine/value contracts: every root action is generated
  and simulated, nested mechanics resolve before admission, semantic memoization is exact, and a
  bounded beam continues the best complete line. Caps choose reachable End only; mandatory choices
  never receive fabricated zero.
- Known information uses exact probability partitions with presence-class compression, followed by
  actual-state replanning. Pokégear uses an exact highest-portable-Worth Supporter partition.
- Added a direct, centralized Mega Starmie board potential with documented human seeds for prizes,
  chip, survival, typed readiness, threat, line development, Turbo dependencies, and actionable
  hand Needs. ValueRegistry continues to own portable held-card cost.
- Cached immutable observation/key projections removed repeated full-tree canonicalization. A
  worst multi-fetch sample dropped from 25.8 profiled seconds to 1.8 seconds at zero lookahead;
  selective causal lookahead is retained for attach/evolve/retreat, denial/deploy, gust, and heal.
- Atomically routed every post-setup Mega Starmie selection through Bellman. Set-Up, starter order,
  and hard no optional setup Bench remain legacy-owned. No strategic fallback exists.
- Live fixtures pass: at 60 HP the policy attaches Water then plays Lillie's; at 50 HP it plays Boss,
  selects the target, and continues the KO line. A raising-stub purity test covers all legacy chooser
  entry points. Production has zero regret against reference on 12 terminal attack states.
- Checkpoint: 41 Bellman tests pass in 31.4 seconds.
- M8 exact next action: sweep all 259 corrections with rationale-first adjudication, emit ledgers for
  every mismatch, run turn-planner/broad/doc/CI gates, finalize the ADR number, then push the PR.

### 2026-08-11 — M8 corpus adjudication and closeout

- Replayed all 259 Mega Starmie corrections, including every row historically marked covered; no
  row was excluded. The final policy agrees with 141 labels.
- Added a fail-closed adjudicator and permanent JSON/Markdown ledger. Every one of the 118 label
  mismatches was read against its rationale and classified: 24 equivalent-or-better complete lines,
  19 stale labels whose rationale agrees, 13 unmodelled historical/multi-turn rulings, and 62 named
  Bellman tuning errors. There are zero unexplained rows and no baseline recapture.
- Replayed Issue #507's 21 target frames: 15 match, two are defensible complete-line equivalents,
  one label is stale against its rationale, and three remain explicitly named Bellman errors.
- Added acceptance gates for action/transition coverage, no-Unknown mechanics, exact-zero End,
  benefit-minus-cost conservation, complete attack resolution, atomic legacy isolation, runtime
  bounds, corpus freshness, and adjudication closure.
- Focused closeout is green: 66 Bellman tests, 27 M7/M8 acceptance and adjudication tests, and 13
  docs/import checks (one intentional skip). Two crash-free broad attempts exceeded 15 and 20 minute
  local bounds after the live-search cutover; their failure cache contains only three defects already
  reproduced on clean `main`. This runtime increase is recorded, not represented as a broad pass.
- Finalized the architecture as ADR-0139 and documented the Mega Starmie-only runtime exception,
  glossary, build result, and CI ownership. Other decks remain on the legacy planner.
- The prototype is complete and live. The 62 error rows are the honest seed-tuning queue; they are
  not represented as covered or silently fitted with tactical frame rules.
