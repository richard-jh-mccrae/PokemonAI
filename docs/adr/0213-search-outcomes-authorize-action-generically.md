# ADR-0213 — Search outcomes authorize action generically

Every Search Algorithm returns one validated, algorithm-neutral Search Outcome that owns completion,
coverage, failure, and action permission. Permission follows from outcome status while algorithm-specific
evidence stays separate, preventing contradictory fields and removing PUCT knowledge from shared coordination;
the accepted cost is a coordinated migration of producers, telemetry, and tests.

Search Coverage records the exact Candidate Roster members supporting each typed Decision Statistic.
It does not estimate explored state-space coverage; Decision Policies validate their declared statistic
requirements against it, preserving distinctions such as zero visits versus an absent sampled mean.

Ordinary budget exhaustion after the algorithm's declared evidence floor is a permitting bounded outcome,
not failure. Exhaustion before that floor is insufficient initialization and does not permit normal selection;
the exact stop cause remains separate from this generic semantic status.

Exact causes use algorithm-owned typed Search Terminations with owner and schema identity. Shared code never
branches on these namespaced reasons. Hard failure requires Decision Failure, cancellation does not, and only
validated completed evidence survives.
