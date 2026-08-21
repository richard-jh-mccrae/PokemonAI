# ADR-0169 — Action ordering prices generic continuation persistence

Ledger replaces mechanic-specific ordering with additive features describing whether an action's gains and remaining
opportunities survive other currently legal actions. Typed Continuation Footprints expose created or replaced zones,
consumed allowances, and immediately usable outputs without naming a card, id, or mechanic-specific tag tuple.

This keeps #582 one-ply while removing `_RESTOCK_TAGS`. A second-action preview would cross into #583's policy and search
ownership; immediate successor value alone cannot represent the known sequencing loss. #583 may carry the same features
through its extracted evaluator contract without changing their meaning.
