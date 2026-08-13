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

Production transitions use the native `cg` search API. `cgpy` is an offline diagnostic adapter only
and is excluded from submissions. Both adapters enter the same state, ledger, value registry, and
solver contracts.

Shuffle-refresh cards are a deliberate exception to successor-state expansion. The solver does not
invent a shuffled hand and play a hypothetical remainder of the turn. `common.needs` derives
immediate unmet jobs, direct/fetch coverage, and deterministic next-turn options for visible cards.
The next-turn projection advances only evolution legality for known cards; future Supporter effects
remain in the normal hand family until a generic effect-outcome evaluator exists. It never predicts
an opponent action or unknown card. `common.refresh` integrates immediate coverage classes with exact hypergeometric
probabilities and weighs that benefit against both current and next-turn known-hand option value.
The branch stops at the refresh commitment; after the live engine produces the real hand, the next
callback replans from reality.

This keeps refresh decisions inside the Bellman ledger without turning random cards into an
imaginary turn. It also makes useful non-Supporter plays naturally precede a refresh: realizing a
known option removes its shuffle-away cost, while a need already satisfiable from hand receives no
draw credit.

No incomplete result or adapter failure falls back to another strategy system.
