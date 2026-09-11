# ADR-0208 — Decision resolution is discriminated

Decision Result carries a typed Decision Resolution distinguishing normal selection, forced selection,
Fail-safe selection, and no selection. Selection variants carry exact Action Choice Identity and optional
policy-owned versioned evidence; no selection is valid only for an empty roster or non-permitting Search
Outcome. Nullable choice plus a shared policy-reason enum was rejected despite the migration cost because it
admits contradictory states and makes neutral contracts own every policy's explanation vocabulary.
