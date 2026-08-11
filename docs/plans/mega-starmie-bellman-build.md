# Mega Starmie Bellman build ledger

Canonical architecture: [ADR-TEMP-507](../adr/temp-issue507-mega-starmie-bellman-turn-planner.md).

This file is the durable execution state for the build. Conversation memory and compaction summaries
are advisory only. At the beginning of every work period, read this file, the ADR, `git status`, and
the commits since the last completed milestone.

## Current

**CURRENT: M2 — one benefit/cost ledger and terminal board value.**

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

### M2 — one benefit/cost ledger and terminal board value — CURRENT

Deliverables:

- portable Worth resolver and upward deck overrides at the Bellman boundary;
- realized benefit, consumed cost, and continuation decomposition;
- canonical state potentials with single-owner/difference-once tests;
- game, prize, damage/KO, readiness, dependency progress, hand option, denial, survival, and mobility
  consequences;
- exact-zero End and strictly negative no-benefit card/non-card actions.

Exit: synthetic conservation tests prove no duplicated consequence and no free non-End action; all
seed constants are centralized and diagnostic.

### M3 — deterministic recursive solver — PENDING

Deliverables:

- exhaustive reference recursion for deterministic MAIN actions and nested our/opponent choices;
- `max`/`min` semantics, continuation, memoization, semantic cycle prevention;
- commit-first-action/replan interface;
- root ledger containing chosen, End, and best rejected alternative;
- deterministic complete-line fixtures for attach, evolve, retreat, heal, fetch, gust, and Supporter
  opportunity costs.

Exit: reference solver finds complete deterministic turns without any legacy chooser; stopping is
chosen whenever all actions are negative.

### M4 — chance, information, Needs, and Scouting belief — PENDING

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

### M5 — complete attack-resolution trees — PENDING

Deliverables:

- attack cost/payment and full post-attack terminal transition;
- deterministic damage/effects, Active and Bench KOs, prizes, game result, and forced promotion;
- recursive Turbo Flare count/recipient and Jetting Blow target decisions;
- general allocation primitives suitable for Aura Jab and Phantom Dive without deck logic;
- opponent legal promotion enumeration as `min`, valued by OpponentBelief;
- single-payment/exact-once tests across attack riders and KO relief.

Exit: attacks are never valued on the pre-attack board; every Mega Starmie attack/nested option has
reference coverage; the 50-HP Boss/KO boundary fixture passes economically.

### M6 — complete Mega Starmie mechanic coverage — PENDING

Deliverables:

- deterministic or enumerated adapters for every ordinary deck card, Ability, and nested target from
  M0;
- typed Energy, discard, shuffle, search, draw, heal/bounce, gust, denial, switch/retreat, evolution,
  and Bench-capacity parity;
- full-turn scenario matrix covering useful, redundant, and harmful uses of every function family;
- zero reachable `UNKNOWN` results in the matrix and complete-corpus replay.

Exit: isolated reference planner completes every reachable Mega Starmie correction state and scenario
without strategic legacy calls. Exact legacy agreement is reported, not fitted blindly.

### M7 — bounded production search and atomic cutover — PENDING

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

### M8 — full corpus adjudication, broad validation, and closeout — PENDING

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
