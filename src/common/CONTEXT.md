# Shared agent runtime

Every shipped deck uses one system: `common.runtime.BellmanRuntime`.

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
- `value.py` and `potential.py`: portable card Worth and successor-state potential;
- `native_engine.py`: production Bellman branches through native `cg` search sessions; unknown
  zones use low-discrepancy identity spacing so the deployment world cannot inherit numeric-id
  ordering as fake draw knowledge;
- `engine.py`: offline-only diagnostic/test transition adapter, excluded from submissions;
- `effects.py`, `fetch.py`, and `draws.py`: effect data and pure chance-window mechanics;
- `solver.py`: reference and bounded production recursion;
- `planner.py`: first-action Bellman commitment;
- `runtime.py`: match-scoped deployment and declarative setup.

Neutral retained services are Scouting, card/stat providers, card-function data, own-deck tracking,
option equivalence, telemetry, and board-card traversal.

Information has no authored bonus. Its value is the Bellman quantity
`E[max continuation after reveal]`; deterministic commitments, chance, and reveal choices all use
the same successor-state utility.
