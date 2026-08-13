# Shared agent runtime

Every shipped deck uses one system: `common.runtime.BellmanRuntime`.

## Language

**Action Family**:
Legal sibling choices that answer the same local question and may be ranked by one family equation.
_Avoid_: Decision group, option bucket

**Family Score**:
An explainable within-family scheduling score. It orders search and never contributes to Bellman utility.
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

**Pilot Profile**:
The resolved, versioned set of adjustable value, search, clock, belief, execution, and diagnostic parameters.
_Avoid_: Constants, tuning blob

The runtime performs declarative setup choices, builds a deck profile from `Strategy`, reads the
opponent through Scouting, and sends every normal-turn decision to `common.BellmanTurnPlanner`.
There is no rules-pipeline fallback.

Deck-local policy is data in `src/agents/<deck>/strategy.py`:

- card Roles and evolution relationships;
- starter priority and preferred first/second turn;
- partner dependencies;
- prize routes;
- upward-only Worth overrides.

The flattened Bellman core owns the decision model:

- `information.py`: opponent belief and exact hypergeometric draw/reveal outcome classes;
- `needs.py`: deck-neutral immediate demand, card-to-need assignment, and deterministic next-turn
  option value for visible cards. It projects only rule clocks and known cards, never hidden draws;
- `refresh.py`: analytic shuffle-refresh commitments. It integrates need-coverage classes with exact
  hypergeometric probabilities, prices immediate and next-turn known-hand options surrendered, and
  never constructs or searches a hypothetical redraw;
- `value.py` and `potential.py`: portable card Worth and successor-state potential;
- `native_engine.py`: production Bellman branches through native `cg` search sessions; unknown
  zones use low-discrepancy identity spacing so the deployment world cannot inherit numeric-id
  ordering as fake draw knowledge;
- `engine.py`: offline-only diagnostic/test transition adapter, excluded from submissions;
- `effects.py`, `fetch.py`, and `draws.py`: effect data and pure chance-window mechanics;
- `solver.py`: reference recursion plus production successive-halving search. Every legal root gets
  an equal value probe; the two strongest incomplete continuations get the full pass. This shapes
  beam width only—turn depth remains uncapped;
- `planner.py`: first-action Bellman commitment;
- `runtime.py`: match-scoped deployment and declarative setup.

Neutral retained services are Scouting, card/stat providers, card-function data, own-deck tracking,
option equivalence, telemetry, and board-card traversal.

Revealed choices use `E[max continuation after reveal]`. Hidden shuffle-refresh draws do not: their
identities are integrated out as need-coverage classes, and the solver commits or declines before
the live random result. Actual post-refresh cards are planned only on the next engine callback.

Native semantic transpositions include a signature of the actual determinized hidden zones, not
the action path used to reach them. Commutative action orders can therefore share exact results
without merging different deck, prize, or opponent-hand worlds.

Production also removes commutative permutations before expansion. Deterministic actions declare
abstract read/write footprints; independent actions use one canonical sleep-set order. Opaque,
random, draw, and reveal effects are barriers, and every stochastic outcome begins a fresh order.
