# ADR-0155 — One catalog owns the valuation vocabulary

A single typed Feature Catalog is the authority for every Valuation Feature Ledger may emit. Each entry defines stable
identity, activation shape, and whether valuation requires a coefficient. Treating configuration fields or distributed
subsystem strings as the vocabulary would leave emission validity and cross-registry completeness implicit.

Role, Card Function, opponent-trait, board, and action compilers declare their possible catalog outputs. Construction
validates those declarations and requires the resolved Valuation Configuration to cover exactly all priced entries.
Adding or retiring compiler behavior therefore changes the catalog and its semantic schema version deliberately.
