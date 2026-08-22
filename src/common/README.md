# common

Shared live agent runtime.

| path | purpose |
|---|---|
| `runtime.py` | Agent hook, setup policy, Opponent Model integration, Ledger invocation |
| `ledger/` | Feature Catalog, evaluation, option preview, and live decider |
| `observation/` | Immutable legal view, knowledge, keys, and provider state |
| `cards/` | Typed card records, Functions, and mechanics |
| `strategy/` | Declarative deck profile types only |
| `scouting/` | Opponent recognition and matchup facts |
| `deck_tracker.py` | Sound own-prize/deck tracking |
| `telemetry.py` | Decision and observation records |

Deck-specific code belongs in `src/agents/<deck>/strategy.py`; tactical selectors do not.
