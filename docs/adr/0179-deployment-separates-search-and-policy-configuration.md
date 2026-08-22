# ADR-0179 — Deployment separates search and policy configuration

Deployment's versioned Compute Configuration pairs owner-specific Search and Policy Configurations,
while Evaluation Model contains no compute controls and Behavior Identity covers every replaceable
behavior component. Timed search stops at deterministic node boundaries and records completed work,
so replay uses the observed node count instead of pretending wall-clock execution is deterministic.
