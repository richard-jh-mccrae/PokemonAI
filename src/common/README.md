# common

Shared Bellman agent code.

| path | purpose |
|---|---|
| `runtime.py` | Agent hook, setup policy, Scouting integration, Bellman invocation |
| `bellman/` | State, transitions, probability, value, and recursive solver |
| `strategy/` | Declarative deck profile types only |
| `scouting/` | Opponent recognition and matchup facts |
| `cards.py`, `card_functions.json` | Portable card functions |
| `card_worth.py` | Shared card opportunity-cost currency |
| `deck_tracker.py` | Sound own-prize/deck tracking |
| `telemetry.py` | Bellman decision records |

Deck-specific code belongs in `src/agents/<deck>/strategy.py`; tactical selectors do not.
