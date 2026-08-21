# ADR-0172 — Residual ties use a deterministic neutral lottery

Actions equal within configured numerical tolerance form an explicit Indifference Set. Ledger resolves that set with a
deterministic lottery whose seed and tolerance belong to Compute Configuration, and records the tied option ordinals in
diagnostics. Replay remains stable without pretending an arbitrary engine order is strategic evidence.

Card IDs, names, selection tuples, mechanic categories, and deck branches cannot influence tie priority. A generic
least-commitment hierarchy would still be strategy and must instead emerge from priced Valuation Features before the tie.
Enumeration changes may alter an otherwise indifferent selection, which is acceptable and visible in compute identity.
