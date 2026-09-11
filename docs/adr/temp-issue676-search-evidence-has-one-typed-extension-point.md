# ADR-TEMP-676 — Search evidence has one typed extension point

Search Result carries at most one optional Search Evidence value identified by algorithm and schema,
and consumers narrow it to a concrete evidence type. PUCT implements this extension point while simple
searches may omit it; a temporary `puct` compatibility projection remains until #611 retires it. This
avoids both algorithm-specific fields in neutral contracts and untyped diagnostics at the cost of typed
dispatch and a transitional adapter.

Per-candidate algorithm statistics live inside that evidence keyed by exact Action Choice Identity.
Valued Candidate carries no algorithm slot; typed Decision Statistics expose the narrow policy view, and
the compatibility adapter reconstructs current candidate-level PUCT projections. Policy Distribution is
likewise the sole prior authority under ADR-0199, with candidate prior fields retained only as projections.

Neutral Search Result does not retain universal-looking node counts, raw stop strings, opaque frontiers, or
the duplicative Search Trace. Search Outcome and Search Termination own shared termination facts; algorithm
evidence owns topology and work, Candidate Results own Action Paths, and compatibility adapters reproduce
legacy diagnostics only for assigned consumers.
