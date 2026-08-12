# Agent architecture

All decks share the same Bellman runtime.

```text
agent main.py
  -> common.runtime.make_agent
  -> declarative setup, or
  -> Scouting Read + deck Strategy profile
  -> Bellman transition tree
  -> recursive value solve
  -> commit the root action
```

`strategy.py` is the only deck-specific policy surface. It declares Roles, evolution Lines, starter
order, partner dependencies, prize routes, and a preferred starting turn. Mega Starmie, Mega Lucario,
and Dragapult all enter the same `BellmanRuntime` and `BellmanTurnPlanner`.

The transition provider reconstructs the offered state in the forkable `cgpy` rules engine. The
native grader remains the source of the offered observation and opaque search token; both live and
historical frames enter the same state, ledger, value registry, and solver contracts.

Hypergeometric probability remains part of the system in `common.information`: draw outcomes
are disjoint classes with an explicit whiff class. The deleted `common.needs` and `common.deck_odds`
were duplicate legacy owners, not the Bellman probability implementation.

No incomplete result or adapter failure falls back to another strategy system.
