# ADR-0165 — Effective configuration is typed, versioned, and residual

The code-owned configuration schema defines stable feature names, valuation parameters, compute bounds, and canonical
serialization. Behavior identity covers the complete resolved valuation, compute, and Prize Plan identities; source
provenance is recorded separately so equivalent effective inputs identify the same behavior.

Deck Overlays are sparse additive residuals over general valuation coefficients. This lets global tuning continue to
reach every deck and matches the future global-model plus deck-residual training shape. Absolute current overrides migrate
to deltas; effective constraints validate after resolution, and overlays cannot alter extraction or Compute Configuration.
