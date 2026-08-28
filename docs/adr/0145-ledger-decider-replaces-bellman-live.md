# ADR-0145 — The Ledger decides live; Bellman becomes the offline teacher

Status: Superseded in part by Issue #582's Feature Catalog and effective configuration. The
live-Ledger decision remains; the weight-vector valuation described below is historical. Plan:
`docs/plans/PokemonAI_Ledger_Plan.md`; chance model: `docs/plans/PokemonAI_Supporter_Decision_Handoff.md`.

## Context

The Search/Policy/Value handoff needs a cheap, hand-trainable policy prior before anything can
be learned. The old composer's differencing idea was right but its hand-written transition
stack (deleted whole in #515) made it a stub factory. Meanwhile Bellman — the sole runtime
since #515 — spends seconds per decision, was never ladder-validated, and its seventeen-family
value stack is bespoke per aspect. The engine's `TransitionProvider` seam and ADR-0144's
`BoardState` make a different shape possible: real transitions, one evaluator.

## Decision

`src/common/ledger/` is the new live brain: a 1-ply worth-differencing decider.

- **One equation** (`evaluate.py`): board value = each visible card's worth × a zone
  multiplier (in play / attached-usable / hand / deck / discard), my side minus theirs, plus
  the prize race, in prizes. Energy usability is marginal (a unit must fill an unfilled attack
  slot; typed slots see the forward evolution line, colorless slots only the body's own
  attacks); hand worth is demand-scaled and counts already-fielded copies; bench slots hold
  harmonic option value; HP clamps at zero so overkill buys nothing; rule-box bodies carry
  prize liability. Every weight lives in `LedgerWeights` (general defaults + thin per-deck
  `Strategy.ledger_overrides`).
- **The engine previews, BoardState digests** (`preview.py`): each option is played by the
  provider; forced follow-up chains resolve greedily inside the preview (advisory — the real
  prompt re-decides); a capped chain scores the mid-effect board rather than deleting the root
  option.
- **Sampled hands for shuffle-draw supporters** (`chance.py`): whole hands drawn from the real
  pool, evaluated as boards, averaged — seeded from the board key, so replays are identical.
  Coin flips and reveals take exact branch math.
- **Spend the turn, then end best** (`decider.py`): turn-continuing options must clear a
  float-noise floor; enders compete only when nothing is worth doing; End is the zero.
  Unpriceable anything decides anyway at a floor and sinks a coverage record.
- **The swap**: `BellmanRuntime.decide` routes to the Ledger. The planner/solver machinery
  stays constructed and callable — `brain="bellman"` re-selects it for its own pins
  (`tests/bellman_helpers.runtime()`) and offline teacher tooling. Nothing switches brains
  mid-match; the strategy fallback and pregame shell are brain-independent. `algebra.Ledger`
  was renamed `BellmanLedger` so the new system owns the name.

## Measured

Three real correction frames replay through the Ledger in 30–80 ms each (Bellman: seconds);
two full cgpy mirror matches complete in 2.1 s wall with zero crashes. Untrained agreement with
human rulings is expected to be poor — training is the corrections-replay loop, and the done
bar is the generality dashboard (general weights alone clearing per-deck agreement).

## Consequences

Live play is now a 1-ply decider with untrained weights: strength regresses until the training
rounds run; that is the accepted bootstrap cost, and ladder win-rate is explicitly not the
scoreboard (generality on the corpus is). Changed-piece re-pricing is deferred — v1 re-evaluates
the whole board at 30–80 ms per decision; `BoardState.changed` is the seam when the cache is
needed. The shell's exception fallback (strategy beam) still answers if the Ledger itself
throws; such decisions name their backend in telemetry and the dashboard, so they cannot hide
as ordinary misses. Tests that pinned the live path to Bellman behavior
re-pointed case by case (`brain="bellman"` for teacher pins; the live-path legality pin now
asserts `backend == "ledger"`). Phase 2 migrates this same evaluator into search as the
branch-ordering prior; the preview's chance seam is where a short search replaces the static
read.

## Addendum 2026-08-28

End remains the policy zero, but its real successor is the Turn-End Counterfactual. Every
turn-ending candidate is differenced against that same-phase successor; continuing actions remain
differenced against the root. This prevents ordinary phase advancement from counting only against
attacks while preserving strict one-ply search.
