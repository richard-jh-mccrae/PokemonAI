# ADR-TEMP-582 — Ledger valuation uses additive marginal features

Ledger valuation becomes the sum of independently active, typed Valuation Features. The current maximum-tier rule masks
all but the largest Role, Card Function, or kind signal, leaving valid configuration entries unable to influence a card
and producing ambiguous training evidence.

Feature extraction is code-owned and deck-agnostic. Valuation Configuration supplies every coefficient and strategic
shaping parameter; deck overlays may bend coefficients but cannot replace extraction or aggregation. Nonlinear effects
must be exposed as named transforms or interaction features rather than hidden selection rules.
