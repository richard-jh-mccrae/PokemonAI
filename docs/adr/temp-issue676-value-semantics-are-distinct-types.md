# ADR-TEMP-676 — Search value semantics remain distinct types

State Valuation, root-relative Decision Delta, Sampled Mean, Expected Continuation, and Best Continuation
remain semantically distinct value types carrying scale and perspective; no neutral contract exposes a
universal `Q`. Decision Policies require exact Decision Statistics, while algorithm evidence retains its
native accounting; the accepted cost is additional types, codecs, and static compatibility checks.

Decision Statistic is an extensible typed protocol rather than a global enum. Common owns only shared
semantic quantities; algorithm packages own specialized statistics such as PUCT visit evidence, and policy
contracts require exact statistic identities without forcing unrelated algorithms to publish them.
