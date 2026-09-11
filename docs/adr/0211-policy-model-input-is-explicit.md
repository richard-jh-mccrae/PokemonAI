# ADR-0211 — Policy model input is explicit

Policy Model receives a typed request containing the legal Observation State, structural Candidate Roster,
source identities, Candidate Results, and available Decision Statistics. Its Component Contract declares
both static statistic types and runtime Decision Requirements: uniform requires no priced evidence, while
Ledger prior requires comparable root deltas. Policy Distribution covers the exact roster, and #677 retains
ownership of bounded evidence preparation.
