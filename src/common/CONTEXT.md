# Shared agent runtime

Every shipped deck uses one system: `common.runtime.AgentRuntime`. Live decisions come from the
Ledger (`common/ledger/`, a 1-ply worth-differencing decider over
`common/observation/` ObservationState, ADR-0145); the shell around it does declarative pregame,
typed knowledge reduction, and one coordinated post-pregame decision path. Forced and degraded
choices remain typed Decision Results. The pre-Ledger Bellman planner is quarantined under
`deprecated/bellman/` (ADR-0149) and extends this shell as the offline teacher.

## Language

**Ledger**:
The live decider: board value is the sum of Feature Activations multiplied once by resolved
Valuation Coefficients; every option's price is its expected successor value minus the root value.
_Avoid_: Evaluator stack, value families

**Swing**:
The one-ply Ledger adapter's scalar Decision Delta: expected successor value minus root value.
Continuation footprints describe policy consequences without changing that value.
_Avoid_: Score, reward

**Position Key**:
Identity of one player-visible position and its explicit legal knowledge, independent of the
question currently presented.
_Avoid_: State key, decision id

**Decision Key**:
Identity of one choice point: its Position Key plus the exact legal question and actions offered.
_Avoid_: Position Key, replay id

**Episode Key**:
Stream-scoped identity shared by every record from one Episode when no external Episode id exists.
_Avoid_: Match id, Position Key, Decision Key

**Legal Knowledge**:
Facts the player may carry from earlier observations but the current engine printout does not contain.
It includes exact facts and honest beliefs, never hidden truth or provider-control metadata.
_Avoid_: Scratch state, hidden state, provider metadata

**Observation State**:
One immutable player-visible position, its Legal Knowledge, and any legal question currently offered.
It never represents hidden game truth or provider-control state.
_Avoid_: BoardState, GameState, DecisionState

**Evaluation Model**:
The versioned card knowledge, opponent profiles, roles, Valuation Configuration, and static Prize
Plan used to interpret an Observation State. It never contains per-decision knowledge, search
effort, or a selector; the evaluator emits derived Prize Map policy evidence for Decision Policy.
_Avoid_: Observation State, LedgerContext, evaluator state

**Value Evaluator**:
A pure mapping from an Observation State and Evaluation Model to one decomposed State Valuation.
It never traverses actions or chooses among them.
_Avoid_: Decision evaluator, action evaluator, search

**Evaluation Request**:
One Observation State and Evaluation Model plus optional parent valuation and Observation Delta
hints. Hints may accelerate evaluation but never change its result.
_Avoid_: Evaluator session, mutable context, cache key

**Valuation Cache**:
A Search Algorithm's decision-scoped reuse of State Valuations keyed by every semantic evaluation
input.
_Avoid_: Evaluator memory, Observation State field, global memo

**State Valuation**:
The decomposed value of one Observation State under one Evaluation Model, with explicit root-seat
perspective, Value Scale, and Evaluator Identity.
_Avoid_: Swing, Search Value, action score

**Value Scale**:
The versioned semantic unit and bounds shared by every value and delta in one search.
_Avoid_: Untyped score, model identity, coefficient

**Ledger-worth**:
The Ledger Value Scale anchored so one net Prize Card equals `1.0` and terminal victory or defeat
equals `+100` or `-100`. These anchors are fixed; learned coefficients remain regularized toward
their reviewed seeds so Pairwise Value Audits stay interpretable in prize-equivalent units.
_Avoid_: arbitrary score, trainable Prize unit, unbounded preference logit

**Value Component**:
One stable, versioned contribution to a State Valuation or Decision Delta. Every evaluator exposes
components that sum to its total; concrete evaluators may add typed evidence.
_Avoid_: Optional diagnostic, untyped part, Feature Activation

**Evaluator Identity**:
The canonical identity of the Value Evaluator implementation or model and its Value Scale.
_Avoid_: Behavior Identity, configuration hash alone

**Search Algorithm**:
The owner of candidate transition traversal and Search Value assembly. It returns every valued
root candidate and leaves the deployed choice to Decision Policy.
_Avoid_: Value Evaluator, decider

**One-Ply Ledger Boundary**:
One root action plus every required effect-resolution choice until control returns to the main
action menu or the turn ends. It never selects a second independent main action.
_Avoid_: whole-turn search, PUCT horizon, fixed action count

**Search Value**:
What a Search Algorithm has established for one action on the root State Valuation's Value Scale,
including its Decision Delta and decomposed contributions.
_Avoid_: State Valuation, policy prior, reward

**Feasible Option Portfolio**:
The state value of compatible opportunities remaining in the current turn under shared allowances,
costs, and targets. Equivalent opportunities retain their multiplicity, while a selected opportunity
retains the exact physical source needed for Realized Portfolio Credit. It is derived without
traversing actions and never sums conflicting plays.
_Avoid_: hand-value sum, Action Path, committed turn plan

**Portfolio Problem**:
The canonical, source-independent representation of current opportunities, multiplicities,
constraints, and worth used to solve one Feasible Option Portfolio.
_Avoid_: legal action menu, physical-card list, cached Decision Delta

**Portfolio Plan**:
The exact best compatible allocation for one Portfolio Problem, before its selected copies are
materialized onto physical hand sources.
_Avoid_: Action Path, approximate hand plan, selected card serials

**Portfolio Memo**:
A Search Algorithm's bounded, turn-scoped reuse of exact Portfolio Plans keyed by the complete
Portfolio Problem and evaluator identity. It resets at the turn boundary and never spans matches.
_Avoid_: global cache, approximate reuse, Valuation Cache

**Decision Delta**:
One candidate's decomposed marginal value against the root State Valuation.
_Avoid_: State Valuation, reward, Swing outside the one-ply adapter

**Turn-End Counterfactual**:
The legal pass successor used to value the End candidate itself.
_Avoid_: unchanged root zero, second MAIN action, opponent rollout

**Valued Candidate**:
One legal root action paired with its aggregate Search Value and explicit Successor Results.
_Avoid_: OptionPrice, chosen action, ranking row

**Candidate Roster**:
The exact legal root-action set materialized before search. Budget exhaustion changes Evaluation
Status but never removes a candidate.
_Avoid_: Expanded actions, top candidates, policy shortlist

**Candidate Disposition**:
A structural statement that a candidate continues the decision phase, ends the turn, or is forced.
It informs Decision Policy without changing value.
_Avoid_: Action-name check, valuation bonus, ranking

**Action Path**:
A root Legal Action followed by the effect-resolution actions traversed to one Successor Result.
It is advisory for search and never masquerades as the root's currently legal action set.
_Avoid_: Compound action, plan commitment, legal alternatives

**Successor Result**:
One probability-weighted legal-view landing for a Valued Candidate, including its Action Path,
Observation State, termination, completeness, and explicit uncertainty or failure.
_Avoid_: ProviderState, raw engine branch, hidden world

**Evaluation Status**:
A closed statement that a candidate value is complete, explicitly estimated, or unavailable.
_Avoid_: Gap string, silent zero, validity boolean

**Policy Model**:
The replaceable source of action priors P(a|s) used to order and allocate search effort.
_Avoid_: Decision Policy, Search Value, action chooser

**Decision Policy**:
The replaceable rule that chooses from a Search Algorithm's completed candidate results.
_Avoid_: Policy Model, Value Evaluator, transition provider

**Decision Coordinator**:
The single neutral entry point that composes Search Algorithm, Policy Model, Value Evaluator, and
Decision Policy for one typed decision.
_Avoid_: LedgerDecider, runtime routing, evaluator stack

**Decision Result**:
The chosen Legal Action together with the complete Search Result, policy or fail-safe reason, and
Behavior Identity.
_Avoid_: Diagnostics bag, chosen action alone, Search Result

**Decision Parity**:
Preservation of the legal candidate roster, decomposed results, explicit statuses, and chosen action
through a behavior-neutral architectural change.
_Avoid_: Choice parity, aggregate agreement alone

**Fail-safe Policy**:
The explicit policy used when candidate Search Values cannot be compared. Its decision carries the
Evaluation Status that required degradation.
_Avoid_: Exception fallback, neutral score, dropped action

**Valuation Feature**:
A canonical deck-agnostic marginal property of a card, board, belief, or continuation.
Independent active features contribute additively.
_Avoid_: Rule, card pin, mechanic branch

**Feature Catalog**:
The single typed authority for every Valuation Feature identity and coefficient requirement.
_Avoid_: Weight field, emitted string, subsystem registry

**Feature Activation**:
A sparse observed or derived quantity emitted independently of coefficients.
_Avoid_: Contribution, configured weight

**Activation Rule**:
A typed, coefficient-independent Feature Catalog declaration mapping legal facts to one Feature
Activation.
_Avoid_: Mechanic branch, Strategic coefficient, Evaluator switch

**Feature Contribution**:
A Ledger Value Component equal to one Feature Activation multiplied once by its resolved Valuation
Coefficient.
_Avoid_: Activation, hidden term

**Valuation Configuration**:
The complete versioned coefficients applied to Valuation Features. A Deck Overlay changes
coefficients but never extraction.
_Avoid_: legacy deck-profile names, deck branch

**Deck Overlay**:
Sparse residuals from our deck added to the general Valuation Configuration.
_Avoid_: Absolute replacement, card override, opponent preference

**Compute Configuration**:
A versioned deployment-owned envelope pairing Search Configuration with Policy Configuration.
_Avoid_: Valuation weight, policy preference

**Correction Compute Profile**:
The deterministic Compute Configuration used by Correction Runs to complete root-candidate pricing
under structural work bounds. Wall time is failure containment, never a search allocation; expiry
rejects the decision rather than publishing partial correction evidence.
_Avoid_: Submission profile, Performance Profile, unlimited search

**Search Configuration**:
The versioned depth, node, time, chance-sampling, and randomness controls bounding Search Algorithm
work.
_Avoid_: Valuation Configuration, tie policy, deck overlay

**Budget Controller**:
The Search Algorithm service that stops work at configured depth, node, or monotonic-time bounds.
Completed node count and stop reason make a timed result replayable as deterministic bounded work.
_Avoid_: Deadline heuristic, valuation threshold, Policy Configuration

**Policy Configuration**:
The versioned indifference, tie, accepted-status, and fail-safe controls used by Decision Policy.
_Avoid_: Search budget, Valuation Configuration

**Behavior Identity**:
The canonical identity of every replaceable behavior component: evaluator, Evaluation Model
(including resolved Valuation Configuration and Prize Plan), search, Policy Model, Decision Policy,
transition semantics, and their effective configurations.
_Avoid_: Weights-only hash, deck name

**Indifference Set**:
Actions equal within Policy Configuration tolerance. A Prize Plan may order an exactly equal
subset; near-equal actions and any remaining exact ties use the neutral seeded lottery.
_Avoid_: Lowest selection, hidden hierarchy

**Archetype Belief**:
A candidate-conditioned set of opponent claims and resources paired with posterior probability.
_Avoid_: Matched Brief, posture, top archetype

**Opponent Trait**:
A typed parameterized opponent claim which only gains value through board context.
_Avoid_: Opponent weight, free-form claim

**Continuation Footprint**:
The marginal state value and action opportunities an action creates, preserves, or consumes.
_Avoid_: Restock tag, card branch

**Action Opportunity Cost**:
A Valuation Feature pricing commitment to a turn-continuing action.
_Avoid_: Act threshold, noise floor

**Realized Portfolio Credit**:
The selected Feasible Option Portfolio contribution fulfilled by playing its owning card. Discarded
payment and unselected opportunities receive no credit.
_Avoid_: hand refund, card-play bonus, generic action reward

**Development Reach**:
A Pokémon's rule-legal proximity to a meaningful current or next-turn state under uncertain resources.
_Avoid_: Projected evolution, guaranteed next-turn attack

**Coverage Unknown**:
Legitimate missing game knowledge, emitted as a named feature and diagnostic. Unknown vocabulary
or malformed configuration is an error.
_Avoid_: Silent zero, typo fallback

**Observation Record**:
The versioned, hidden-safe serialized form of an Observation State used for replay and learning.
_Avoid_: Raw observation, diagnostic dump

**Decision Record**:
The versioned, hidden-safe serialization of one typed runtime decision and its complete legal evidence.
_Avoid_: Bellman record, diagnostics dump, chosen action

**Outcome Record**:
One Episode's terminal public facts and labels, linked to every Decision Record in that Episode.
_Avoid_: Terminal decision, reward row

**Episode Telemetry Receipt**:
Match-scoped closure proof for every reserved Decision Record and its commit or delivery failure. An
incomplete receipt cannot certify an Outcome Record or Episode Bundle.
_Avoid_: Flush flag, Best-effort count, Log scrape

**Opponent Belief**:
Scouting's immutable evidence-level estimate of the opponent: candidate-conditioned probabilities,
unknown mass, public evidence, and explicit failures. Evaluation Models interpret it; the belief
contains no compiled roles, weights, or matchup policy.
_Avoid_: Opponent Layer, Brief, matchup weights

**Observation Event**:
A typed event legally shown since the previous choice, used to advance Legal Knowledge.
An unknown event invalidates affected certainty rather than preserving a stale belief.
_Avoid_: Raw log, generic event mapping

**Transition Trace**:
A versioned training record linking a starting Position Key, an action sequence, and its resulting
Position Key. Search emits one per Successor Result; it supplies commutativity evidence, never proof
that a branch is safe to prune.
_Avoid_: Position identity, pruning rule

**Tracking Serial**:
The engine's match-local identity for one physical card copy, used to correlate observations and
events. It never contributes directly to semantic position identity.
_Avoid_: Card ID, Position Key

**Observation Delta**:
Parent-relative facts about which parts changed while producing an Observation State.
It guides Valuation Cache reuse and training but never contributes to state identity or value.
_Avoid_: Observation State, event history

**Strategy**:
An authored, conditional hint about decision sequences likely to reach valuable end states.
It schedules search traversal and never changes action or board value.
_Avoid_: Need, rule, reward

**General Strategy**:
A deck-independent Strategy shared by every pilot, such as taking inexpensive information first.
_Avoid_: Generic value

**Deck Strategy**:
Own-deck doctrine that may add to or explicitly override General Strategies.
_Avoid_: Card Role, hard-coded line

**Prize Plan**:
Deck doctrine naming stable preservation and sacrifice preferences without enumerating every
possible knockout sequence.
_Avoid_: Exhaustive route list

**Prize Map**:
The live, state-dependent projection of how the opponent can take its remaining prizes from our
reachable bodies, including any forced prize overrun.
_Avoid_: Static Prize Route, Prize Plan

**Opponent Strategy**:
Scouting doctrine activated by an **Archetype Belief**, including target and avoidance priorities.
_Avoid_: Opponent Role, matchup value

**Pokémon Role**:
Typed deck or scouting doctrine describing one precise strategic job a Pokémon performs.
Roles contribute to development, preservation, and KO value but never target priority.
_Avoid_: Engine, disruption target, Trainer function, Strategy

**General Pokémon Role**:
A deck-independent Pokémon Role used whenever the same body has the same strategic job for either player.
_Avoid_: Repeated deck Role, Card Function

**Pre-evolution Role**:
Scouting doctrine marking an undeveloped Pokémon whose known evolution line makes it a valuable denial target.
_Avoid_: Win condition base, automatic deck Role

**Evolution Relationship**:
The intrinsic ancestry between Pokémon cards. It comes from card facts and is not deck doctrine.
_Avoid_: Authored evolution map, Pokémon Role

**Card Function**:
An intrinsic typed parameterized card capability shared across decks. It carries no value itself;
the Ledger combines it with board context to emit Valuation Features.
_Avoid_: Tag, Pokémon Role, deck doctrine, valuation feature

**Opponent Model**:
The match-scoped owner of opponent knowledge. It updates before each evaluated decision and emits
an **Opponent Snapshot**; it never chooses actions or pass its mutable state to consumers.
_Avoid_: mutable opponent state, opponent policy

**Opponent Snapshot**:
The Opponent Model's immutable legal-view output for one decision. Its evidence-level projection
enters Observation State as Opponent Belief; telemetry may retain the full snapshot.
_Avoid_: Opponent Belief, mutable opponent state, evaluator input

**Opponent Evidence**:
The typed public facts and events from which the **Opponent Model** learns. Hidden hand contents and
deck order cannot be represented.
_Avoid_: raw observation, replay truth, Opponent Snapshot

The runtime performs declarative setup choices, resolves Roles and evolution from the unified
card records (deck declarations REPLACE authored defaults), builds the deck's Evaluation Model
and complete effective configuration, and sends every post-pregame decision through the Decision
Coordinator. A forced Candidate Roster skips transition preview; unavailable work is resolved by
the typed Fail-safe Policy.

Deck-local policy is data in `src/agents/<deck>/strategy.py`:

- Pokémon Roles; evolution relationships are derived from card facts;
- starter priority and preferred first/second turn;
- sparse Prize Plan preservation/sacrifice selectors;
- a sparse additive Ledger overlay over shared Valuation Features.

The live decision path:

- `decision/`: neutral evaluator, search, policy, candidate, successor, value-scale, budget, and
  coordinator contracts;
- `ledger/`: the Feature Catalog, linear activation/contribution evaluation, decider, option
  previews, and compute-profiled sampled-hand chance
  (ADR-0145), plus the preview seam over the providers (ADR-0146);
- `observation/`: ObservationState, its builder, knowledge, provider capsule, keys, record codec,
  events, and parent-relative delta;
- `cards/`: the unified card store — one record module per card, carrying typed clauses,
  coverage verdicts, and engine stat corrections (ADR-0143/0153) — and the per-function
  mechanics (`fetch.py`, `draw.py`, `energy.py`, `attack_lock.py`) and live bench reach in
  `damage.py`;
- `native_engine.py`: the production `cg` transition provider — forks the engine, enumerates and
  applies actions, never ranks; unknown zones use low-discrepancy identity spacing so the
  deployment world cannot inherit numeric-id ordering as fake draw knowledge;
- `engine.py`: offline cgpy twin of the provider, excluded from submissions;
- `refresh.py`: the printed-counts shuffle-refresh transition both providers emit and the Ledger
  prices analytically;
- `information.py`: exact draw/reveal outcomes for the offline provider;
- `algebra.py`, `api.py`, `options.py`: the transition algebra, decision contracts, and
  legal-action construction (the providers' old DecisionState moved to the quarantine — the live
  path builds none, pinned in `tests/ledger`).

Neutral retained services are Scouting, card/stat providers, card-function data, own-deck tracking,
option equivalence and telemetry.
