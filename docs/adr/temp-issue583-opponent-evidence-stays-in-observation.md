# ADR-TEMP-583 — Opponent evidence stays in the observation

Observation State owns candidate-conditioned opponent evidence and uncertainty; Evaluation Model
owns static profile interpretation, replacing per-decision `EvaluationModel.with_opponent`. This
supersedes ADR-0175 only where it says Ledger consumes Opponent Snapshot directly; Opponent Model
ownership and full-snapshot telemetry remain unchanged.
