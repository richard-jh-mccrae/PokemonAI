# ADR-0166 — Deployment owns a separate compute profile

Preview limits, sampling controls, deterministic seeds, and numerical tolerances form a complete versioned Compute
Configuration selected by the runtime deployment. Deck overlays cannot alter it: allowing decks to buy different search
effort would confound valuation comparisons, tuning results, and runtime-cost guarantees.

Compute Configuration has its own canonical identity because changing a cap or sample can change a ruling even when all
preferences remain fixed. Each decision records a Behavior Identity pairing the resolved valuation identity with the
compute and Prize Plan identities. Strategic thresholds are excluded from compute and must instead be decomposed
Valuation Features.
