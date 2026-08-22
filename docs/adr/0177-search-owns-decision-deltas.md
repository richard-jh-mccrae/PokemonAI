# ADR-0177 — Search owns decision deltas; value evaluators own state value

Search Algorithm owns traversal and Q(s,a), Value Evaluator remains a pure V(s) function, Policy
Model supplies P(a|s), and Decision Policy alone selects the deployed action. Neutral contracts live
under `common/decision/`; Ledger supplies replaceable one-ply evaluator, search, and policy adapters,
preventing today's greedy behavior from becoming the permanent architecture.
