# ADR-TEMP-582 — Opponent traits compile to contextual features

The #559 Opponent Snapshot supplies typed, parameterized, candidate-conditioned traits as evidence claims rather than
valuation entries. Giving a broad trait a direct price would make its meaning depend on unstated board context and blur
the ownership boundary between opponent knowledge and Ledger valuation.

#582 owns deck-agnostic compilers that combine each registered trait with current board state to emit marginal Valuation
Features. Posterior expectation then scales those feature activations, while every coefficient remains in the resolved
Valuation Configuration. Unknown traits fail validation instead of disappearing or inheriting a default value.
