# ADR-0136: Absolute state potentials own consequences and difference once

Status: Accepted; built for Issue #494 (2026-08-10).

## Context

Issue #493 proved that the six `state_value` families were the production valuation seam, but its
diagnostics depended on private extractors and independently subtracted flattened trees. `reads`
also treated shared raw inputs as double counting even when two families priced different economic
consequences. That made the audit useful but not a stable implementation contract for #495.

## Decision

`common.state_value` remains the only runtime value module and the scalar remains the authority.
The state registry stays, in order, `prize_race`, `survival`, `threat`, `readiness`, `hand`, and
`development`; the separate terminal registry remains only `attack_ev`.

Each `TermFamily` now declares globally unique `ConsequenceSpec` ownership, derived ordered raw
inputs, unit, horizon, bounds, and its evaluator. Raw inputs may be shared when the consequence key
and rationale differ. Duplicate consequences and undeclared shared inputs fail closed.

Evaluators retain one arithmetic path. Scalar calls allocate no diagnostic tree, preserve the
`("state_value",)` memo key, registry order, constants, caps, and formulas. Explicit
`value_breakdown` calls return immutable prize-denominated family/leg results with `known`,
`deliberate_zero`, or `unknown` status, registry content identity, bound adjustments, and the
terminal exclusion. A diagnostic call may seed the scalar memo; a scalar call never seeds the
diagnostic memo.

`value_difference(before, after)` is the sole canonical subtraction. It aligns families in registry
order and dynamic legs in before-order followed by after-only legs. A missing leg is known zero;
signed zero is normalised. All contract types expose deterministic JSON-primitive `as_dict()`
projections.

## Consequences

The Composer runtime is unchanged in #494; behavior changes belong to #495. Value Lab times only
the scalar call. Family diagnosis and sensitivity probes consume the public breakdown/difference
contract. Sensitivity schemas advance to `/2`; the coverage census advances to schema 3, records
the registry identity and consequence metadata, and is regenerated against Issue #493's merged SHA.
Static blind spots remain authored `TermFamily.blind_to` declarations rather than runtime unknowns.
