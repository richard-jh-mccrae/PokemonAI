# ADR-0192 — Diagnostics separate replay, policy, and outcome

Ledger diagnostics classify exact Replay Drift, rule-based Policy Inconsistency, and statistical
Outcome Residuals separately. This prevents deterministic but poor valuation from passing as healthy
and prevents a noisy terminal result from being mislabeled as proof that one decision was wrong.
