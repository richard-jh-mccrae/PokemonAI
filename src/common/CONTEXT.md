# Shared agent runtime

Every shipped deck uses one system: `common.runtime.AgentRuntime`. Live decisions come from the
Ledger (`common/ledger/`, a 1-ply worth-differencing decider over
`common/observation/` ObservationState, ADR-0145); the shell around it does declarative pregame,
forced selections, typed knowledge reduction,
and a last-resort crash fallback. The pre-Ledger Bellman planner is quarantined under
`deprecated/bellman/` (ADR-0149) and extends this shell as the offline teacher.

## Language

**Ledger**:
The live decider: board value = card worth × zone multiplier, both sides, prizes; an option's
price is the swing it causes and only ending the turn is worth zero.
_Avoid_: Evaluator stack, value families

**Swing**:
One option's price under the Ledger: value after minus value now, expected value at chance points.
_Avoid_: Score, reward

**Position Key**:
Identity of one player-visible position and its explicit legal knowledge, independent of the
question currently presented.
_Avoid_: State key, decision id

**Decision Key**:
Identity of one choice point: its Position Key plus the exact legal question and actions offered.
_Avoid_: Position Key, replay id

**Legal Knowledge**:
Facts the player may carry from earlier observations but the current engine printout does not contain.
It includes exact facts and honest beliefs, never hidden truth or provider-control metadata.
_Avoid_: Scratch state, hidden state, provider metadata

**Observation State**:
One immutable player-visible position, its Legal Knowledge, and any legal question currently offered.
It never represents hidden game truth or provider-control state.
_Avoid_: BoardState, GameState, DecisionState

**Evaluation Model**:
The versioned card knowledge, roles, Valuation Configuration, and Compute Configuration used to
value an Observation State. It changes evaluation, never position facts or identity.
_Avoid_: Observation State, LedgerContext, evaluator state

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

**Feature Contribution**:
A Feature Activation multiplied once by its resolved Valuation Coefficient.
_Avoid_: Activation, hidden term

**Valuation Configuration**:
The complete versioned coefficients applied to Valuation Features. A Deck Overlay changes
coefficients but never extraction.
_Avoid_: Pilot Profile, deck branch

**Deck Overlay**:
Sparse residuals from our deck added to the general Valuation Configuration.
_Avoid_: Absolute replacement, card override, opponent preference

**Compute Configuration**:
The versioned limits, sampling controls, and tolerances bounding Ledger work.
_Avoid_: Valuation weight, policy preference

**Behavior Identity**:
The resolved Valuation Configuration and Compute Configuration identities recorded together.
_Avoid_: Weights-only hash, deck name

**Indifference Set**:
Actions equal within Compute Configuration tolerance; a neutral seeded lottery selects among them.
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

**Opponent Belief**:
Scouting's immutable evidence-level estimate of the opponent, including its uncertainty.
Evaluation Models interpret it; the belief itself contains no roles, weights, or matchup policy.
_Avoid_: Opponent Layer, Brief, matchup weights

**Observation Event**:
A typed event legally shown since the previous choice, used to advance Legal Knowledge.
An unknown event invalidates affected certainty rather than preserving a stale belief.
_Avoid_: Raw log, generic event mapping

**Transition Trace**:
A versioned training record linking a starting Position Key, an action sequence, and its resulting
Position Key. It supplies commutativity evidence, never proof that a branch is safe to prune.
_Avoid_: Position identity, pruning rule

**Tracking Serial**:
The engine's match-local identity for one physical card copy, used to correlate observations and
events. It never contributes directly to semantic position identity.
_Avoid_: Card ID, Position Key

**Observation Delta**:
Parent-relative facts about which parts changed while producing an Observation State.
It guides reuse and training but never contributes to state identity.
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

**Opponent Strategy**:
Scouting doctrine activated by the matched opponent Brief.
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

The runtime performs declarative setup choices, resolves Roles and evolution from the unified
card records (deck declarations REPLACE authored defaults), builds the deck's Evaluation Model
and complete effective configuration, and sends every normal-turn decision to `common.ledger`.

Deck-local policy is data in `src/agents/<deck>/strategy.py`:

- Pokémon Roles; evolution relationships are derived from card facts;
- starter priority and preferred first/second turn;
- partner dependencies;
- prize routes;
- a sparse additive Ledger overlay over shared Valuation Features.

The live decision path:

- `ledger/`: the Feature Catalog, linear activation/contribution evaluation, decider, option
  previews, and compute-profiled sampled-hand chance
  (ADR-0145), plus the preview seam over the providers (ADR-0146);
- `observation/`: ObservationState, its builder, knowledge, provider capsule, keys, record codec,
  events, and parent-relative delta;
- `cards/`: the unified card store — one record module per card, carrying typed clauses,
  coverage verdicts, and engine stat corrections (ADR-0143/0153) — and the per-function
  mechanics (`fetch.py`, `draw.py`, `damage.py`, `energy.py`, `attack_lock.py`);
- `native_engine.py`: the production `cg` transition provider — forks the engine, enumerates and
  applies actions, never ranks; unknown zones use low-discrepancy identity spacing so the
  deployment world cannot inherit numeric-id ordering as fake draw knowledge;
- `engine.py`: offline cgpy twin of the provider, excluded from submissions;
- `refresh.py`: the printed-counts shuffle-refresh transition both providers emit and the Ledger
  prices analytically;
- `information.py`: exact hypergeometric draw/reveal outcome classes for the offline provider;
- `algebra.py`, `api.py`, `options.py`: the transition algebra, decision contracts, and
  legal-action construction (the providers' old DecisionState moved to the quarantine — the live
  path builds none, pinned in `tests/ledger`).

Neutral retained services are Scouting, card/stat providers, card-function data, own-deck tracking,
option equivalence and telemetry.
