# ADR-0161 — Card Functions compile into marginal features

Card records describe intrinsic capabilities through typed, parameterized Card Functions. Ledger combines those facts
with board state to emit Marginal Basis features; a capability label carries no standing value by itself. Rule affordances
remain typed facts but are not valuation coefficients.

This removes loose parameterized tag strings and `TAG_WORTH`, preventing overlapping labels from double counting the same
capability. Store construction rejects unknown functions, while the existing card generator and coverage gates migrate to
the typed schema across the full store.
