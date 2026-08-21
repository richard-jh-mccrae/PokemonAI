# ADR-0168 — Schema errors fail; game uncertainty stays explicit

Unknown Roles, Card Functions, traits, Feature keys, overlays, and shipped artifact declarations are software or authoring
errors and fail during construction. Runtime invariant violations produce typed degradation in live mode and re-raise in
strict offline mode; they never become zero-valued features or apparently valid empty knowledge.

Legitimate game uncertainty remains representable. Missing card coverage emits a Coverage Unknown feature and diagnostic,
while opponent uncertainty uses explicit unknown posterior mass. This preserves live availability against the open card
pool without allowing typos or malformed artifacts to change policy silently.
