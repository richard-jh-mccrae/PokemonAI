# Shared agent runtime

Every shipped deck uses one system: `common.runtime.BellmanRuntime`.

## Language

**Action Family**:
Legal sibling choices that answer the same local question.
_Avoid_: Decision group, option bucket

**Family Score**:
An offline diagnostic from a bespoke equation. The Pilot does not compute or consume it.
_Avoid_: Action value, policy value

**Search Wave**:
A cohort of admitted candidates that receives equal shallow planning work before any candidate is deepened.
_Avoid_: Beam, batch

**Planning Epoch**:
Planning work performed from one known state until an information boundary or validated plan completion.
_Avoid_: Callback budget

**Plan Suffix**:
The deterministic remainder of a chosen line, guarded by its expected states and legal choices.
_Avoid_: Script, macro

**Information Boundary**:
An event that reveals previously unknown facts or hands control to the opponent, invalidating a plan suffix.
_Avoid_: Any callback

**Structural Prune**:
Permanent removal justified by semantic equivalence or coefficient-independent dominance.
_Avoid_: Low score, clear loser

**Terminal Proof**:
A sound certificate that a legal current-turn policy wins under every relevant outcome.
_Avoid_: Lethal score, likely win

**Lethal Solver**:
The current-turn search that produces a Terminal Proof or abstains without changing normal policy.
_Avoid_: Lethal heuristic, win bonus

**Strategy**:
An authored, conditional hint about decision sequences likely to reach valuable end states.
It schedules Bellman traversal and never changes action or board value.
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

**Strategy Match Strength**:
The degree to which a legal action advances active Strategies in the known state.
It controls search priority only.
_Avoid_: Action value, Bellman reward

**Strategy Snapshot**:
The resolved General, Deck, and Opponent Strategies activated for one Planning Epoch.
New strategy-relevant information creates a new snapshot.
_Avoid_: Turn-only cache, live action score

**Strategy Beam**:
The focused root actions scheduled first from Strategy Match Strength, plus safe executable actions.
Bellman later widens into every unresolved legal path and owns the final choice.
_Avoid_: Pruning rule, replacement planner

**Candidate Harvest**:
Strategy-ordered depth-first search for distinct executable attack/End lines before Bellman widening.
It stops at its Pilot Profile line quota or clock share, whichever comes first.
_Avoid_: Strategy policy, early final choice

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

**Demand Slot**:
One value-side recipient, capability, and resource requirement used to price access and retained options.
_Avoid_: Strategy, wanted card

**Bellman Value**:
The comparable utility of an action's resulting state and continuation.
Strategies never enter this quantity; Roles, Card Functions, prize yield, and board development may.
_Avoid_: Strategy Match Strength

**Bound Prune**:
Planning-epoch removal proved by an upper bound no better than the current executable lower bound.
_Avoid_: Structural Prune, low-priority branch

**Pilot Profile**:
The resolved, versioned set of adjustable value, search, clock, belief, execution, and diagnostic parameters.
_Avoid_: Constants, tuning blob

The runtime performs declarative setup choices, builds a deck profile from `Strategy`, reads the
opponent through Scouting, and sends every normal-turn decision to `common.BellmanTurnPlanner`.
There is no rules-pipeline fallback.

Deck-local policy is data in `src/agents/<deck>/strategy.py`:

- Pokémon Roles; evolution relationships are derived from card facts;
- Deck Strategies and explicit General Strategy overrides;
- starter priority and preferred first/second turn;
- partner dependencies;
- prize routes;
- upward-only Worth overrides.

The flattened Bellman core owns the decision model:

- `information.py`: opponent belief and exact hypergeometric draw/reveal outcome classes;
- `strategy/strategies.py`: General, Deck, and Opponent Strategy declarations and Planning-Epoch
  activation snapshots;
- `demand.py`: Strategy Beam scheduling plus value-side Demand Slots and exact access odds;
- `cards/functions/attack_lock.py`: pure fold of the printed "can't use this attack next turn" state,
  which the observation omits, from the public ATTACK log; read by `potential.py` on both seats;
- `refresh.py`: analytic shuffle-refresh commitments. It integrates demand-coverage classes with exact
  hypergeometric probabilities, prices immediate and next-turn known-hand options surrendered, and
  never constructs or searches a hypothetical redraw;
- `value.py` and `potential.py`: portable card Worth and successor-state potential;
- `native_engine.py`: production Bellman branches through native `cg` search sessions; unknown
  zones use low-discrepancy identity spacing so the deployment world cannot inherit numeric-id
  ordering as fake draw knowledge;
- `engine.py`: offline-only diagnostic/test transition adapter, excluded from submissions;
- `effects.py`: the legacy effect-clause table, still feeding the scouting/authoring layers and the
  Lethal Solver's coverage gate; the per-function mechanics live one module each under
  `cards/functions/` (`fetch.py`, `draw.py`, `damage.py`, `energy.py`, `attack_lock.py`) and read
  the unified card records (ADR-0143), resolved once at each consumer's `cards` mapping;
- `solver.py`: reference recursion plus production successive-halving search. Every legal root gets
  focused Strategy paths first, retains executable safety paths, then widens across unresolved legal
  roots until proof or timeout. Strategy changes order only; Bellman value selects the action;
- `planner.py`: first-action Bellman commitment;
- `runtime.py`: match-scoped deployment, guarded deterministic plan-suffix reuse, forced selections,
  and declarative setup;

Neutral retained services are Scouting, card/stat providers, card-function data, own-deck tracking,
option equivalence, telemetry, and board-card traversal.

Revealed choices use `E[max continuation after reveal]`. Hidden shuffle-refresh draws do not: their
identities are integrated out as demand-coverage classes, and the solver commits or declines before
the live random result. Actual post-refresh cards are planned only on the next engine callback.

Native semantic transpositions include a signature of the actual determinized hidden zones, not
the action path used to reach them. Commutative action orders can therefore share exact results
without merging different deck, prize, or opponent-hand worlds.

Production also removes commutative permutations before expansion. Deterministic actions declare
abstract read/write footprints; independent actions use one canonical sleep-set order. Opaque,
random, draw, and reveal effects are barriers, and every stochastic outcome begins a fresh order.
