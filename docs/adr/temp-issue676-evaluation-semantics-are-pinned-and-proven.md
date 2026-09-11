# ADR-TEMP-676 — Evaluation semantics are pinned and proven

Each Evaluation Request pins a legal Observation State, Evaluation Model identity, and root perspective;
the Value Evaluator contract declares its identity, accepted model contract, and Value Scale. Every returned
State Valuation must prove matching position, model, evaluator, perspective, and scale before search uses it,
and reuse keys cover every semantic input. This rejects incompatible evaluation early at the cost of stricter
requests, fixtures, cache identities, and boundary validation.
