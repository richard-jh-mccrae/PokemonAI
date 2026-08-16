# Strategy-guided Bellman beam

Status: implemented on `codex/strategy-anytime-fallback`; full-suite validation in progress

This specification replaces the per-state, additive-value interpretation of demand in
`terminal-proof-strategy-guided-bellman.md`. Its terminal-proof requirements remain in force.

## Intent

Bellman owns value and final choice. With sufficient search, it chooses the same policy whether Strategy guidance
is enabled or disabled.

Strategies help bounded Bellman find strong lines sooner. It compiles authored General, Deck, and matched Opponent
strategy into a small, state-specific first-search beam. It does not define utility, duplicate lethal analysis, or
delete a line merely because that line does not match an authored strategy.

Odds remains an exact probability and reachability service. It updates as access information changes and helps
Bellman order actions, compress chance, and tighten admissible bounds.

The runtime order is:

```text
same-turn Terminal Proof
→ Planning-Epoch Strategy Snapshot
→ live Odds/access overlay
→ structural duplicate and dominance proofs
→ Strategy-ordered bounded Bellman
→ iterative widening of every unresolved line
```

## Implementation plan

Implement this as extensions to the current owners. Do not add a second Strategy evaluator, value
function, planner, or fallback doctrine.

### 1. Lock the contracts with tests

Add failing tests before each production slice:

- `tests/strategy/test_strategies.py`: authored conviction is fixed; urgency changes with the
  branch-local deadline window; optional bundle IDs and ordered waypoints round-trip through the
  manifest and stable hash; Strategy activation never claims feasibility.
- `tests/bellman/test_m3_solver.py`: Strategy only reorders; exhaustive Strategy ON/OFF policy is
  identical; deep own-node ordering remains active in every search phase; candidate tiers,
  protected bundle shares, challenger reserve, and stable-incumbent stopping follow this plan.
- `tests/bellman/test_m7_runtime.py`: a timeout inside an effect latches Strategy fallback through
  the rest of that effect, clears at the next effect boundary, and cannot produce an illegal or
  empty productive selection.
- `tests/bellman/test_m5_attacks.py`: Dragapult's attack may publish a recoverable line before all
  six counters are planned; timeout fallback places all six legally and deterministically, with
  Strategy preferring a KO or pressure on the primary attacker.
- `tests/sim/test_strategy_bench.py`: the report exposes first recoverable, first fully planned,
  stabilization, phase allocation, fallback, reachability, challenger, and timeout metrics.

Keep focused fixtures small enough to run on every Bellman CI job. Use recorded slow frames for a
separate deterministic performance suite; do not use full mirrors during development.

### 2. Extend the authored Strategy model

`src/common/strategy/strategies.py` remains the declaration and activation owner.

- Replace ambiguous authored `confidence` terminology with `conviction`. Accept `confidence` only
  as a serialized migration alias, emit `conviction`, and register the retired name.
- Add an optional `bundle_id` and ordered outcome window to each hint. A hint remains a desired
  fact, never an action script.
- Keep conviction immutable for the match artifact. Compute urgency from the current waypoint's
  window and elapsed turn progress; do not alter conviction when feasibility changes.
- Represent branch-local outcome status explicitly: satisfied, guaranteed, probabilistic,
  proven impossible, or unknown. Strategy can bind a visible recipient and determine satisfaction;
  Bellman/Odds supplies every reachability status beyond satisfaction.
- Recompute activation only at the existing planning-epoch boundary. Re-evaluate satisfaction,
  urgency, and the current waypoint cheaply at every simulated own state.

Update the shared manifest/brief projection and package hashes from this same model. Add initial
Dragapult bundle declarations only as minimal integration fixtures; the separate Dragapult strategy
work remains the owner of its full doctrine.

### 3. Make the existing beam the single guidance engine

Evolve `src/common/demand.py::StrategyBeamBuilder` instead of creating a fallback Strategy path.

- Split authored preference from feasibility evidence. Urgency plus conviction orders preferences;
  a Bellman/Odds reachability overlay controls whether protected search budget may be borrowed.
- Evaluate bundle and waypoint progress against every simulated own state, in candidate harvest,
  probing, and refinement. A satisfied waypoint stops receiving focus; later bundle endpoints stay
  active when still relevant.
- Expose one pure, bounded legal-option ranker from the same matcher for runtime fallback. Its
  fallback mode may inspect the cached snapshot, current visible state, and offered legal options;
  it must not call Odds, native transitions, or Bellman.
- Preserve stable semantic-action ordering as the final tie-break. Unknown evidence fails open.

### 4. Publish anytime candidates by execution tier

Extend `src/common/solver.py` and the existing candidate bank with an explicit execution tier:

1. fully planned: every mandatory choice through the next information/effect boundary is planned;
2. Strategy-recoverable: the legal prefix is publishable and the first unresolved mandatory choice
   can be completed by the shared fallback ranker;
3. safety: the current deterministic safe action.

Publish candidate-bank checkpoints atomically. Never expose a half-mutated recursive result.
Attack lines with unresolved mandatory post-attack choices are recoverable, not fully planned.
Rank recoverables by sound Bellman lower bound, then urgency, conviction, and stable deterministic
tie-break. When no trustworthy lower bound exists, Strategy preference owns the fallback order.

Return the best fully planned candidate first, then the best recoverable candidate, then safety.
Preserve the existing guarded plan suffix only through the last planned step; runtime replans or
falls back at the first new or unresolved choice.

### 5. Replace fixed phases with bounded allocation

Move the percentages into `src/common/pilot_profile.py`; `src/common/solver.py` only consumes the
resolved profile. Keep each phase independently toggleable for attribution.

- Reserve the fallback tail first: five percent of the external decision limit, clamped to one to
  five seconds. All search shares use the remaining Bellman budget.
- Normal candidate harvest receives 20%. Guarantee two slots: primary Strategy and safety. Permit a
  third Strategy variation only after the primary becomes fully planned or its slice expires or
  stalls.
- High-urgency/high-conviction work may use at most one shared 50% protected pool. One compatible
  bundle may use all of it. With two incompatible bundles, spend the first 25% equally, then give
  the remaining 25% to the bundle with more structural progress.
- Protect at most two bundles. Report additional high/high bundles and send them through ordinary
  widening.
- Count only waypoint reached, mandatory nested choice resolved, recoverable published, or fully
  planned published as structural progress. Node count, action count, and value churn do not count.
- Give a protected bundle only a cheap initial probe. It may borrow toward 50% while feasibility is
  guaranteed, probabilistic and competitive, or unknown but structurally progressing. Proven
  impossible or dominated work releases its unused share immediately.
- Replace the unconditional all-root probe with a 10% challenger reserve. Probe at most the top two
  credible off-Strategy roots selected by cheap optimistic Bellman bounds; skip any root whose
  upper bound cannot beat the incumbent lower bound.
- Return every unused slice to ordinary refinement. With no protected bundle the nominal split is
  20% harvest, 10% challenger, 70% refinement. With protected work, refinement retains at least 40%.

Use one monotonic `DecisionClock` created at callback entry. Make the end-to-end external limit
available to runtime, give Bellman the pre-tail deadline, and leave the process watchdog as final
containment. Remove the current ambiguity where the benchmark subtracts grace before runtime sees
the limit.

### 6. Add sound stability stopping

Use the existing incumbent timeline and upper bounds in `src/common/solver.py`.

- Stop immediately on Terminal Proof.
- Otherwise stop only when a fully planned incumbent is unchanged across two published checkpoints
  and no credible challenger upper bound can beat its lower bound.
- Require patience of 20% of the Bellman budget, clamped to one to ten seconds.
- A recoverable-only incumbent never triggers stability stopping.

Strategy satisfaction alone never stops search. Strategy fields never enter Bellman value, lower
bounds, upper bounds, dominance, or pruning.

### 7. Make timeout fallback effect-safe

`src/common/runtime.py` owns the effect-scoped fallback latch and final legal submission.

- Terminal Proof still runs once before planning and may abstain.
- If Bellman times out at any choice inside a multi-step effect, latch Strategy fallback for every
  remaining choice in that effect; do not rerun Bellman for each Dragapult counter.
- Clear the latch on a proven new effect, return to main action context, turn change, or seat change.
- Rank only currently offered legal options with the shared Strategy matcher. With no Strategy
  opinion, use a deterministic effect-specific default, then the canonical legal sanitizer.
- Never voluntarily decline an already-spent productive fetch/draw/placement effect when an
  eligible option exists. Fetch-to-hand chooses the maximum allowed; fetch-to-bench chooses a legal
  Strategy-preferred count from one through maximum; mandatory damage placement spends every
  counter. Empty selection is valid only when no eligible target exists or rules force zero.
- Replace `_last_resort_selection` with this same legal fallback, including exception handling. An
  in-process planning exception must not forfeit the match. The outer process watchdog remains the
  containment boundary for an actual hung or dead process.

### 8. Instrument before optimizing

Extend `src/common/telemetry.py` and `tools/sim/strategy_bench.py` from the same decision record:

- first recoverable, first fully planned, and final stabilization timestamps;
- execution tier and incumbent lower bound;
- phase budgets, used time, released time, and structural-progress events;
- bundle, waypoint, urgency, conviction, and reachability status;
- challenger attempts and whether a challenger replaced the incumbent;
- fallback cause, effect latch, selected waypoint, choice, and remaining tail;
- external limit, Bellman deadline, deadline hit, exception fallback, and process timeout.

The text, CSV, and JSON reports must be projections of the same fields. Keep policy independent of
telemetry emission.

### 9. Validate in isolated slices

Run targeted tests after each numbered slice, then:

```text
python -m pytest tests/strategy tests/bellman/test_m3_solver.py tests/bellman/test_m7_runtime.py -q
python -m pytest tests/bellman tests/agents tests/common tests/sim/test_strategy_bench.py -q
python -m pytest tests/parity tests/cards tests/submit -q
python -m pytest tests/test_doc_links_resolve.py tests/test_line_endings_policy.py -q
python -m tools.doc_budget src/common --detail
```

For every allocator/stop feature, compare the same recorded slow frames with only that feature
toggled. Do not combine narrow nested budgets, continuation reuse, and bound stopping in one first
measurement; the prior combined experiment regressed both first-pick and total time and could not
attribute the cause.

Use paired seeds and full-budget Bellman as the policy reference. Initial release gates are:

- zero crashes, external decision timeouts, illegal fallbacks, or voluntary empty productive fetches;
- first recoverable within 20% of the Bellman budget;
- at least 25% median improvement in first-fully-planned time on high/high frames versus Strategy OFF;
- no constrained top-pick agreement regression;
- no p95 total-decision regression;
- exhaustive Strategy ON/OFF policy identity.

After fast gates pass, amend ADR 0139 with measured evidence while preserving its rejected-experiment
record. Then hand the user one three-match native mirror command, producing six Pilot seat-runs, for
the final timing measurement. Mirror win rate is secondary to correctness and latency gates.

## Implementation gate evidence

The implementation adds authored conviction, bundle waypoints, anytime execution tiers, a reserved
fallback tail, protected allocation, bounded challengers, stability checks, effect-scoped fallback,
and shared Strategy legal-option ranking. The focused architecture suite passes: 159 tests across
Strategy, solver, runtime, profile, agent, and benchmark contracts.

After rebasing onto current `main`, all 63 historical correction gates pass. The final bounded-policy
rule lets only a protected high-urgency/high-conviction Strategy hold an unresolved incumbent, and
only until a challenger's lower bound closes that focused line's upper bound. Ordinary Strategy stays
reorder-only. Focused architecture and regression groups pass; the full repository suite reached 86%
with no failure before its long integration tail was interrupted for the requested checkpoint commit.
PR validation resumes after that checkpoint.

## Core invariants

1. Exhaustive Strategy ON and Strategy OFF choose the same Bellman policy.
2. Strategies change exploration order only.
3. Strategies contribute no independent reward or penalty.
4. Strategies cannot independently prune a legal branch.
5. Odds contributes probabilities and reachability, not additive utility.
6. Unknown evidence fails open: Bellman retains and eventually widens the line.
7. Every deletion names an independent legality, equivalence, dominance, or admissible-bound proof.
8. A deck may have no confident Strategy guidance for a turn.

## Authored strategy contract

General, deck-specific, and opponent Strategies use one declarative, serializable interface. Arbitrary callbacks are not
allowed because runtime behavior, tests, A/B identity, and the submission brief must consume the same source.

Each authored strategy declares:

- a stable identifier;
- its general, deck, or opponent scope;
- board and match activation conditions;
- desired board facts;
- a recipient selector;
- a deadline category;
- a categorical confidence;
- provenance and enabled state.

Activation may inspect visible board and match facts, including roles, evolution state, position, Energy, damage,
prizes, turn allowances, and the opponent's visible board. Activation does not inspect the current hand or available
access cards.

Strategies describe desired facts, not action scripts. They do not carry independent utility or detailed tactical
weights. Stable deck roles and relationships may guide activation; matchup sequences and card-specific ordering do
not belong in this contract.

General strategies apply by default. Deck and matched Opponent strategies may add guidance. A deck may disable or narrow a general
strategy only through an explicit override referencing the general strategy's stable identifier. Resolution never
silently replaces a strategy by name or priority.

The resolved strategy set has a stable content hash. The runtime and submission manifest consume that exact resolved
set.

## Strategy Snapshot

General, Deck, and matched Opponent Strategies resolve at the first controllable decision of each turn. Their
activation becomes the Planning-Epoch Strategy Snapshot. A newly revealed strategy-relevant fact ends that epoch;
the three layers combine again against the new known state. Hand changes that do not affect activation reuse the
same snapshot while Odds updates against current access.

Each active hint identifies desired board facts for a specific recipient and deadline. Match strength ranges from
zero to strong based on condition fit and the action's live probability of advancing that fact. A hint may become satisfied,
obsolete, or unreachable as Bellman walks a branch. Those are cheap branch-local status updates; they do not rebuild
the strategy snapshot.

If a branch makes a hint unreachable, that branch stops receiving the hint's priority. It is not penalized or pruned
for doing so. Bellman determines whether the alternative state is stronger.

Strategies may abstain when strategy is ambiguous. Complex tradeoffs, such as investing in a support engine versus a
future attacker, remain Bellman decisions unless authored conditions identify a high-confidence beam without
assigning final value.

## Strategy beam formation

Activated strategies form a small first-search frontier. Ordering uses only:

1. deadline category;
2. categorical authored confidence;
3. current probability of satisfying the desired facts;
4. the marginal access improvement offered by a legal action.

Strategy guidance does not simulate board-potential deltas to rank strategies. It does not enumerate every positive evolution,
attachment, heal, deployment, denial, or future development operation.

Several non-dominated strategy hints may share the first beam. Bellman gives those hints fair shallow evaluation and
then refines the strongest executable results. Ambiguous states may produce an empty beam.

## Odds and access

Odds is evaluated against the current Planning-Epoch Strategy Snapshot. It refreshes when visible access facts change, including hand,
deck knowledge, discard, known top cards, reveals, and remaining access resources.

For each relevant action, Odds may report the marginal probability of satisfying a hint before its deadline. An
access action with no live target or no probability improvement receives no Strategies priority.

Odds may also:

- provide exact chance probabilities;
- compress equivalent hidden outcomes;
- establish whether a desired fact remains reachable;
- tighten a Bellman value-family ceiling.

Odds is never added to Bellman value merely because access probability increased. Bellman values the states that
access can reach.

## Bellman allocation and widening

Bellman searches the Strategy Beam first and obtains several completed, executable paths. Outside root actions initially receive
a cheap admissible upper-bound check rather than an equal deep search.

An outside action is deleted only when its upper bound cannot beat the incumbent lower bound under Bellman's exact
tie rules. Infinite or unresolved bounds require widening. With unlimited wall clock, every unresolved legal line is
eventually evaluated.

Bellman then widens into unresolved legal paths until their own bounds prove they cannot beat the incumbent or the
decision timeout expires. The best completed path is always the safe decision. Strategy satisfaction never stops search.

## Bellman upper bound

Strategies are absent from additive Bellman bounds. The upper bound is:

\[
Q_U(s,a)=\Delta V(s,a)+U_{reachable}(s')
\]

`U_reachable` is expressed only in Bellman value families and is constrained by remaining allowances, reachable
mechanics, exact Odds, and terminal-proof evidence.

Terminal Proof supplies a three-valued result:

- proved: execute the verified winning policy;
- refuted: terminal win value is unavailable to that proved scope;
- unknown: retain the terminal ceiling and widen conservatively.

Strategy guidance does not recreate prize or same-turn win logic. A terminal value is removed only by a conclusive proof result,
not by failure to find a proof within a cap.

## Structural search reduction

Structural reduction runs after the strategy beam is formed and before Bellman value recursion.

Static action footprints prove obvious independence from declared reads, writes, allowances, information, chance,
and triggers. Retreat is modeled by its known lineup, Energy, and allowance effects rather than treated as opaque.
Supporter status alone does not make an action a barrier; the declared effect controls its footprint.

Unresolved deterministic action pairs may use an exact diamond proof:

```text
state → A → B → result X
state → B → A → result Y
```

Both orders must be legal and deterministic. The proof compares semantic board state, hand, allowances, triggers,
knowledge, and the remaining legal menu. Equality admits one canonical order. Difference or uncertainty retains
both.

Pair proofs are cached. Their independence relation forms a dependency graph, so a web of independent actions has
one canonical ordering rather than factorial permutations. Bellman does not calculate utility while proving the
diamond.

Chance operations may commute only through a declared probability-preserving independence proof. Information
actions are not called commutative merely because one fixed outcome reaches the same final board.

## Information before commitment

Information-before-commit spans three owners:

- authored general strategy states the preference;
- Strategy guidance identifies which information is relevant;
- Odds measures the access improvement.

The reverse order is deleted only by a structural dominance proof. Information-first must preserve every downstream
commitment choice, consume no conflicting resource, introduce no harmful state change, and retain every result
reachable by committing first.

When those obligations are unresolved, Strategies/Odds may order information first, but Bellman retains both lines.

## Submission strategy interface

`common.strategy` remains the owner of deck declarations. The shared general strategy registry and each deck's
declarations resolve through the same serializable Strategy type.

Every submission manifest and `brief.html` includes:

- the authored general strategies;
- the deck-specific strategies;
- matched opponent strategies supplied by Scouting Briefs;
- explicit deck overrides;
- the resolved effective strategy set;
- stable strategy identifiers and provenance;
- activation conditions and desired facts in human-readable form;
- the resolved strategy-set hash;
- the Strategy ON/OFF state;
- the Odds state and Bellman profile hash.

The rendered brief is a projection of the same manifest consumed by packaging tests. It is not maintained as a
second prose copy.

## Telemetry

Runtime telemetry exposes enough evidence to review search behavior without feeding diagnostics back into policy:

- Planning-Epoch snapshot identity and strategy-set hash;
- activated, inactive, and abstained strategy identifiers;
- cached hint status changes;
- Odds and marginal access changes;
- first-beam actions and widening events;
- commutativity, dominance, and admissible-bound proofs;
- terminal-proof status;
- time attributed to Strategies, Odds, structural reduction, and Bellman;
- planner calls and guarded continuation reuse.

## Strategies A/B contract

The canonical comparison changes only the Strategy beam.

Strategy ON enables authored strategy activation and beam ordering. Strategy OFF disables that activation and ordering.
Both variants retain Odds, Terminal Proof, structural reduction, Bellman limits, value parameters, and the same
resolved strategy catalog.

Both artifacts record Strategy state, Odds state, strategy-set hash, and Bellman profile hash in `brief.html`. Paired
matches use the same seeds, seats, decks, artifact inputs, and limits.

A/B reporting covers decision latency, match latency, callback distribution, beam and widening counts, correction
agreement, policy differences, and match outcomes. Odds-only experiments are separate and cannot be labeled as the
canonical Strategy comparison.

## Implementation validation workflow

Implementation completes before the native mirror measurement begins. Automated work may use unit tests, synthetic
engine tests, recorded corrections, exhaustive differential fixtures, packaging checks, and bounded smoke tests to
guide development.

The implementer does not repeatedly launch the full mirror gate while changing code. After the implementation and
fast blocking gates pass, the implementer stops and gives the user the exact command for a manual mirror run. Mirror
results returned by the user are then analyzed as a separate measurement step.

A failed manual mirror run may justify a targeted reproduction and fix. It does not authorize an open-ended loop of
full mirror runs. Another full measurement waits for the next explicit user-run result.

## Replay timing analyzer

A command-line analyzer accepts a replay directory and recursively reads every supported replay and paired agent log
within it. It reuses the existing replay-decision and telemetry-log join rather than defining another frame format.

The text report includes:

```text
match time: min, max, avg
decision time: min, max, avg
decision time limits hit: count
limit hits: match-id/frame-id entries
```

The report also states match count, decision count, and missing-sample counts. Limit-hit entries include seat,
observed seconds, and the declared limit when available. Statistics use finite valid samples only and never replace
missing values with zero.

The analyzer supports a machine-readable JSON form for paired Strategies A/B comparison. Text and JSON are projections of
the same calculated report.

Exact match wall time must come from explicit replay metadata or a timing sidecar written by the match runner. It is
never inferred from summed decision time. Replays without that field remain usable for decision statistics, while
match-time output reports those samples as unavailable.

Decision telemetry records the effective decision limit and whether the solver actually stopped on that limit. The
analyzer uses this explicit event instead of guessing from rounded elapsed time. It joins each event to the replay's
match and frame identifiers through the existing positional validation.

After implementation, the handoff gives the user:

1. the manual command that produces mirror replays, logs, and explicit match timing;
2. the analyzer command for that output directory;
3. the expected report shape;
4. the corresponding Strategy OFF commands for a paired comparison.

## Acceptance gates

The implementation is not releasable until all of these hold:

1. Exhaustive differential tests prove Strategy ON and OFF choose the same completed policy.
2. Strategy-relevant new facts rebuild the Planning-Epoch Strategy Snapshot; access-only changes update Odds.
3. A turn may produce no Strategy guidance and still execute ordinary Bellman.
4. No Strategy hint enters utility, transition ledgers, or additive upper bounds.
5. Every branch deletion records an independent proof and executable incumbent where applicable.
6. Static and diamond commutativity tests preserve exact reference-solver policy.
7. Strategy resolution, overrides, hashes, and `brief.html` rendering share one manifest source.
8. Strategy ON/OFF A/B artifacts differ only in the declared Strategy toggle and derived identity.
9. Existing human correction gates remain blocking.
10. Replay timing fixtures verify aggregation, missing samples, explicit limit hits, and frame attribution.
11. The packaged native five-match mirror gate remains a user-run final measurement.

## Deferred work

Multi-turn Bellman is the intended consumer of the saved wall clock, but its horizon, opponent policy, and terminal
value model are outside this specification. Strategies must not encode future-turn strategy to compensate for a missing
multi-turn Bellman implementation.
