# Needs as a strategy beam for Bellman

Status: implementation in progress

This specification replaces the per-state, additive-value interpretation of Needs in
`terminal-proof-needs-bounded-bellman.md`. Its terminal-proof requirements remain in force.

## Intent

Bellman owns strategic value. With a correct model and sufficient search, it must choose the same policy whether
Needs is enabled or disabled.

Needs exists to help bounded Bellman find strong lines sooner. It compiles authored general and deck-specific
strategy into a small, state-specific first-search beam. It does not define utility, duplicate lethal analysis, or
delete a line merely because that line does not match an authored strategy.

Odds remains an exact probability and reachability service. It updates as access information changes and helps
Bellman order actions, compress chance, and tighten admissible bounds.

The runtime order is:

```text
same-turn Terminal Proof
→ turn-start Needs strategy snapshot
→ live Odds/access overlay
→ structural duplicate and dominance proofs
→ Needs-ordered bounded Bellman
→ iterative widening of every unresolved line
```

## Core invariants

1. Exhaustive Needs ON and Needs OFF choose the same Bellman policy.
2. Needs changes exploration order only.
3. Needs contributes no independent reward or penalty.
4. Needs cannot independently prune a legal branch.
5. Odds contributes probabilities and reachability, not additive utility.
6. Unknown evidence fails open: Bellman retains and eventually widens the line.
7. Every deletion names an independent legality, equivalence, dominance, or admissible-bound proof.
8. A deck may have no confident Need guidance for a turn.

## Authored strategy contract

General and deck-specific Needs strategies use one declarative, serializable interface. Arbitrary callbacks are not
allowed because runtime behavior, tests, A/B identity, and the submission brief must consume the same source.

Each authored strategy declares:

- a stable identifier;
- its general or deck scope;
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

General strategies apply by default. Deck strategies may add guidance. A deck may disable or narrow a general
strategy only through an explicit override referencing the general strategy's stable identifier. Resolution never
silently replaces a strategy by name or priority.

The resolved strategy set has a stable content hash. The runtime and submission manifest consume that exact resolved
set.

## Turn-start Needs snapshot

Needs runs once at the first controllable decision of each own turn, after mandatory turn-start resolution. The
result is cached for the remainder of that turn.

The snapshot is hand-independent. Drawing, searching, recovering, or revealing cards does not redefine the turn's
Needs. Those events update Odds against the existing snapshot.

Each active hint identifies desired board facts for a specific recipient and deadline. A hint may become satisfied,
obsolete, or unreachable as Bellman walks a branch. Those are cheap branch-local status updates; they do not rebuild
the strategy snapshot.

If a branch makes a hint unreachable, that branch stops receiving the hint's priority. It is not penalized or pruned
for doing so. Bellman determines whether the alternative state is stronger.

Needs may abstain when strategy is ambiguous. Complex tradeoffs, such as investing in a support engine versus a
future attacker, remain Bellman decisions unless authored conditions identify a high-confidence beam without
assigning final value.

## Needs beam formation

Activated strategies form a small first-search frontier. Ordering uses only:

1. deadline category;
2. categorical authored confidence;
3. current probability of satisfying the desired facts;
4. the marginal access improvement offered by a legal action.

Needs does not simulate board-potential deltas to rank strategies. It does not enumerate every positive evolution,
attachment, heal, deployment, denial, or future development operation.

Several non-dominated strategy hints may share the first beam. Bellman gives those hints fair shallow evaluation and
then refines the strongest executable results. Ambiguous states may produce an empty beam.

## Odds and access

Odds is evaluated against the cached turn snapshot. It refreshes when visible access facts change, including hand,
deck knowledge, discard, known top cards, reveals, and remaining access resources.

For each relevant action, Odds may report the marginal probability of satisfying a hint before its deadline. An
access action with no live target or no probability improvement receives no Needs priority.

Odds may also:

- provide exact chance probabilities;
- compress equivalent hidden outcomes;
- establish whether a desired fact remains reachable;
- tighten a Bellman value-family ceiling.

Odds is never added to Bellman value merely because access probability increased. Bellman values the states that
access can reach.

## Bellman allocation and widening

Bellman searches the Needs beam first and obtains an executable lower bound. Non-Need root actions initially receive
a cheap admissible upper-bound check rather than an equal deep search.

An outside action is deleted only when its upper bound cannot beat the incumbent lower bound under Bellman's exact
tie rules. Infinite or unresolved bounds require widening. With unlimited wall clock, every unresolved legal line is
eventually evaluated.

This preserves the anytime benefit of authored strategy without turning the beam into a second policy engine.

## Bellman upper bound

Needs is removed from additive Bellman bounds. The upper bound is:

\[
Q_U(s,a)=\Delta V(s,a)+U_{reachable}(s')
\]

`U_reachable` is expressed only in Bellman value families and is constrained by remaining allowances, reachable
mechanics, exact Odds, and terminal-proof evidence.

Terminal Proof supplies a three-valued result:

- proved: execute the verified winning policy;
- refuted: terminal win value is unavailable to that proved scope;
- unknown: retain the terminal ceiling and widen conservatively.

Needs does not recreate prize or same-turn win logic. A terminal value is removed only by a conclusive proof result,
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
- Needs identifies which information is relevant;
- Odds measures the access improvement.

The reverse order is deleted only by a structural dominance proof. Information-first must preserve every downstream
commitment choice, consume no conflicting resource, introduce no harmful state change, and retain every result
reachable by committing first.

When those obligations are unresolved, Needs/Odds may order information first, but Bellman retains both lines.

## Submission strategy interface

`common.strategy` remains the owner of deck declarations. The shared general strategy registry and each deck's
declarations resolve through the same serializable Needs strategy type.

Every submission manifest and `brief.html` includes:

- the authored general strategies;
- the deck-specific strategies;
- explicit deck overrides;
- the resolved effective strategy set;
- stable strategy identifiers and provenance;
- activation conditions and desired facts in human-readable form;
- the resolved strategy-set hash;
- the Needs ON/OFF state;
- the Odds state and Bellman profile hash.

The rendered brief is a projection of the same manifest consumed by packaging tests. It is not maintained as a
second prose copy.

## Telemetry

Runtime telemetry exposes enough evidence to review search behavior without feeding diagnostics back into policy:

- turn snapshot identity and strategy-set hash;
- activated, inactive, and abstained strategy identifiers;
- cached hint status changes;
- Odds and marginal access changes;
- first-beam actions and widening events;
- commutativity, dominance, and admissible-bound proofs;
- terminal-proof status;
- time attributed to Needs, Odds, structural reduction, and Bellman;
- planner calls and guarded continuation reuse.

## Needs A/B contract

The canonical comparison changes only the Needs strategy beam.

Needs ON enables authored strategy activation and beam ordering. Needs OFF disables that activation and ordering.
Both variants retain Odds, Terminal Proof, structural reduction, Bellman limits, value parameters, and the same
resolved strategy catalog.

Both artifacts record Needs state, Odds state, strategy-set hash, and Bellman profile hash in `brief.html`. Paired
matches use the same seeds, seats, decks, artifact inputs, and limits.

A/B reporting covers decision latency, match latency, callback distribution, beam and widening counts, correction
agreement, policy differences, and match outcomes. Odds-only experiments are separate and cannot be labeled as the
canonical Needs comparison.

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

The analyzer supports a machine-readable JSON form for paired Needs A/B comparison. Text and JSON are projections of
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
4. the corresponding Needs OFF commands for a paired comparison.

## Acceptance gates

The implementation is not releasable until all of these hold:

1. Exhaustive differential tests prove Needs ON and OFF choose the same completed policy.
2. Hand and access changes update Odds without rebuilding the turn Needs snapshot.
3. A turn may produce no Needs guidance and still execute ordinary Bellman.
4. No Need hint enters utility, transition ledgers, or additive upper bounds.
5. Every branch deletion records an independent proof and executable incumbent where applicable.
6. Static and diamond commutativity tests preserve exact reference-solver policy.
7. Strategy resolution, overrides, hashes, and `brief.html` rendering share one manifest source.
8. Needs ON/OFF A/B artifacts differ only in the declared Needs toggle and derived identity.
9. Existing human correction gates remain blocking.
10. Replay timing fixtures verify aggregation, missing samples, explicit limit hits, and frame attribution.
11. The packaged native five-match mirror gate remains a user-run final measurement.

## Deferred work

Multi-turn Bellman is the intended consumer of the saved wall clock, but its horizon, opponent policy, and terminal
value model are outside this specification. Needs must not encode future-turn strategy to compensate for a missing
multi-turn Bellman implementation.
