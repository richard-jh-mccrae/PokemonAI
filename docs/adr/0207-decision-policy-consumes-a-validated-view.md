# ADR-0207 — Decision policy consumes a validated result view

Decision Policy receives a narrow Decision Policy Request containing the authoritative roster, outcome,
coverage, typed final statistics, and optional typed search evidence after Component Contract validation.
It returns one Action Choice Identity, which the coordinator resolves exactly once. This avoids coupling
policies to the complete Search Result and prevents candidate-option fields from becoming an implicit
compatibility protocol.

Each policy declares both statically required Decision Statistic types and typed runtime Decision
Requirements. The coordinator proves producer compatibility at assembly and actual readiness before
selection; a permitting result that fails readiness is a hard Search contract failure, not a policy exception.
