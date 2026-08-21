# ADR-0158 — Shared features use explicit context interactions

The same generic Valuation Feature has one baseline meaning for either player and enters evaluation with signed activation:
own presence adds it and opponent presence subtracts it. Duplicating the whole vocabulary by side would weaken feature
semantics, double the tuning surface, and allow unexplained asymmetry.

Real asymmetry from turn ownership, agency, or knowledge is represented by a separately named Context Interaction. Each
interaction must state the context it captures and have its own coefficient, registry validation, decomposition, and tests;
no evaluator branch may silently change a shared feature because of side.
