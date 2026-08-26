# ADR-0193 — Ledger values observable capabilities

Status: Accepted.

## Context

Role labels compressed board evaluation into deck-author guesses. They could not explain why one
Energy unlocks more damage than another, why one gust target is safer, or why Solrock and Lunatone
change each other's value. Fixed information and ordering bonuses had the same defect: they priced
an action name instead of its resulting board and remaining legal line.

## Decision

The Ledger prices observable capabilities and resources directly. Attacks use exact payment,
damage, target HP, Weakness, Resistance, prize yield, bench reach, partner gates, and reachable
evolutions. Abilities price their current draw, search, movement, healing, acceleration, denial,
and costs. Hand, deck, discard, prizes, Stadium, and opponent hidden zones expose contextual option
factors. Strategy roles remain scouting metadata but cannot emit valuation features.

Remaining-turn value comes from bounded conditional preview. Static continuation bonuses default
to zero; root reveal choices expose expected log-choice information value. A turn begins with a
four-group valuation snapshot; later observations use
`ObservationDelta` to invalidate dependent groups, with an opt-in full-evaluation parity assertion.

Every feature has a catalog seed and a constrained training parameter. Correction sweeps export
candidate feature vectors. Training splits by match, fits pairwise correction preferences under
sign and range constraints, calibrates margins, and emits artifacts bound to catalog, seed, and
data identities. Coverage, role removal, parameter coverage, and incremental parity are executable
certification checks.

## Consequences

Similar actions compare through the whole resulting board, not assigned Pokémon roles or action
names. New card clauses and observation fields must enter the coverage ownership tables. Weight
changes remain learned residuals over explicit seeded factors; exact rules and legality stay code.
Incremental groups are deliberately coarse: correctness is identical to a full evaluation, while
future profiling may split hot groups without changing valuation semantics.
