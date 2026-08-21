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
The versioned card knowledge, roles, and parameters used to value an Observation State.
It changes evaluation, never the facts or identity of the position.
_Avoid_: Observation State, LedgerContext, evaluator state

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
Deck or scouting doctrine describing a Pokémon's strategic job, such as primary attacker, backup attacker, or support.
Roles contribute to development, preservation, and KO value.
_Avoid_: Win condition, secondary attacker, Trainer function, Strategy

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
An intrinsic Trainer or Energy capability shared across decks, such as search, draw, gust, or acceleration.
_Avoid_: Pokémon Role, deck doctrine

The runtime performs declarative setup choices, resolves Roles and evolution from the unified
card records (deck declarations REPLACE authored defaults), builds the deck's EvaluationModel
from them and `ledger_overrides`, and sends every normal-turn decision to `common.ledger`.

Deck-local policy is data in `src/agents/<deck>/strategy.py`:

- Pokémon Roles; evolution relationships are derived from card facts;
- starter priority and preferred first/second turn;
- partner dependencies;
- prize routes;
- upward-only Worth overrides and `ledger_overrides`.

The live decision path:

- `ledger/`: the decider, worth/zone evaluation, option previews, and sampled-hand chance
  (ADR-0145), plus the preview seam over the providers (ADR-0146);
- `observation/`: ObservationState, its builder, knowledge, provider capsule, keys, record codec,
  events, and parent-relative delta;
- `cards/`: the unified card store — one record module per card, carrying tags, clauses,
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
