# ADR-TEMP-582 — The valuation model cuts over atomically

#582 replaces current Ledger weights, feature extraction, ordering branches, and evaluation together on the production
path. The legacy evaluator remains available only through a frozen offline Parity Oracle used before merge; production
does not ship a feature flag, fallback, or translation adapter between competing valuation semantics.

The atomic boundary makes the new Feature Catalog, resolved configuration, decomposition, and Behavior Identity the only
runtime authority. Constrained parity gates protect intended behavior and an ADR-linked allowlist explains deliberate
flips. #559 starts integration only after this complete dependency leaf lands.
