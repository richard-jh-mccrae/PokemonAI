# ADR-0205 — Candidate rosters are structural

Candidate Roster is the immutable ordered legal root menu and contains no values, priors, successor results,
or algorithm evidence. Search Result carries one neutral Candidate Result per Action Choice Identity, while
coverage, statistics, distributions, and algorithm evidence use the same keys. This makes legal proof stable
through search and selection at the cost of a major contract migration.

Completeness and availability attach to each semantic value or evidence item, not Candidate Result as a whole.
Mixed evidence therefore remains honest: a choice may simultaneously have complete root value, estimated
successors, no Sampled Mean, and valid algorithm accounting.
