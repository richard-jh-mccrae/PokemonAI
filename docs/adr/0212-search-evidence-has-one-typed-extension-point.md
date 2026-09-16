# ADR-0212 — Search evidence has one typed extension point

Search Result carries at most one optional Search Evidence value identified by algorithm and schema,
and consumers narrow it to a concrete evidence type. PUCT implements this extension point while simple
searches may omit it. This avoids both algorithm-specific fields in neutral contracts and untyped
diagnostics at the cost of typed dispatch.

Per-candidate algorithm statistics live inside that evidence keyed by exact Action Choice Identity.
Typed Decision Statistics expose the narrow policy view, and Policy Distribution is the sole prior authority
under ADR-0199.

Neutral Search Result does not retain universal-looking node counts, raw stop strings, opaque frontiers, or
the duplicative Search Trace. Search Outcome and Search Termination own shared termination facts; algorithm
evidence owns topology and work, and Candidate Results own Action Paths.
