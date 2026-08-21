# ADR-TEMP-582 — Evaluation exposes activations and contributions

Ledger evaluation returns the canonical sparse Feature Activation vector, each activation's contribution under the
resolved Valuation Configuration, and their total. A scalar or contribution-only result cannot distinguish changed game
evidence from changed coefficients and prevents clean retraining or completeness audits.

Activations are deterministic and coefficient-independent; contributions equal activation times resolved coefficient and
must sum to the reported total. Optional source provenance is separate from the canonical vector. #582 defines this
internal evaluation contract and its tests, while #585 remains responsible for any external telemetry wire format.
