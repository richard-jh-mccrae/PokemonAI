"""The combat oracle in parts: one module per question, each a `*Mixin` the `CombatMath` composes.

`budget` and `policy` carry the records and constants; `cards` says what a card does, `energy`
what pays for it, `reach` what that reaches, and `harvest` / `forward` / `clocks` compose over
those. ADR-0052 still holds — ONE class, ONE entry point; only the source is distributed."""
