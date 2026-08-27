# ADR-0193 — Ledger values observable capabilities

Status: Accepted.

## Context

Role labels compressed board evaluation into deck-author guesses. They could not explain why one
Energy unlocks more damage than another, why one gust target is safer, or why Solrock and Lunatone
change each other's value. Fixed information and ordering bonuses had the same defect: they priced
an action name instead of its resulting board and remaining legal line.

## Decision

The Ledger prices observable capabilities and resources directly. Card Function names carry no
value themselves; their amounts, conditions, targets, costs, and resulting board changes feed
independent valuation axes. Strategy roles remain scouting metadata and cannot emit value.

Bounded preview values the remaining legal line. Search owns a dependency-group snapshot for the
turn and invalidates it from observation deltas while retaining full-evaluation parity.

The feature catalog distinguishes trainable value from aliases, legality, conditional rules,
retired terms, and missing seeds. Executable field and mechanic contracts prevent unvalued state
from silently entering weight-only correction rounds.

Every deployed clause parameter is a direct equation input. Qualifiers that were previously left
to an assumed successor receive seeded `clause.parameter.*` features, and the readiness gate
removes or perturbs every exact card/clause occurrence to require a nonzero valuation delta. Each
seeded qualifier also declares its expected feature and monotonic direction; reversed equations
fail the same gate.

Multi-step effects are valued as one successor chain. Target-local effects choose a legal target
jointly with that target's costs; terminal self-KO routes include their prize-loss liability.

## Consequences

Similar actions compare through the whole resulting board, not assigned Pokémon roles or action
names. New card clauses and observation fields must enter the coverage ownership tables. Weight
changes remain learned residuals over explicit seeded factors; exact rules and legality stay code.
Incremental groups are deliberately coarse: correctness is identical to a full evaluation, while
future profiling may split hot groups without changing valuation semantics.

Untyped printed effects remain explicit coverage failures, never silent zeroes.
