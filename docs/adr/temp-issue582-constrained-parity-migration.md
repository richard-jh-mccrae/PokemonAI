# ADR-TEMP-582 — Additive defaults migrate under constrained parity

The additive model seeds general coefficients and then deck residuals against a frozen pre-migration corpus baseline.
Unaffected feature contributions and choices must preserve intended behavior; every accepted flip is explicitly tied to a
semantic decision from this issue rather than hidden by replacing the baseline wholesale.

The migration retains the worst-deck generality floor and zero-unexplained-regression gates. Directly copying old numbers
cannot preserve meaning after aggregation changes, while a neutral reset would ask an incomplete correction corpus to
reconstruct competent behavior it never recorded.
