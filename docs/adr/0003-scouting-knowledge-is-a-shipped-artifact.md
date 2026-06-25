# Scouting knowledge is an offline-compiled, shipped artifact

**Context.** The runtime agent must recognize opponents and produce the Read, but
the meta analysis (`meta.db`) lives outside the submission bundle and Kaggle's
runtime is offline and self-contained (no DB, no network, native lib only).

**Decision.** A build-time compiler (in `tools/`, outside the bundle) reads the
latest meta report + enriched card metadata and emits a compact, self-contained
**JSON artifact of *meta knowledge only*** into `common/scouting/`: per-Archetype
priors, `P(card | archetype)`, Signatures, representative builds, evolution lines,
and threat/target role tags — all referencing cards by `cardId`.

Static **card stats** (hp, weakness, resistance, abilities, attacks) are *not*
shipped. The runtime reads them from the already-loaded `cg` engine
(`all_card_data()` / `all_attack()`) **once at startup** and caches them in a
`{cardId: stats}` dict. No DB or network at runtime; the meta artifact is a
point-in-time snapshot, regenerated and re-bundled as the meta shifts.

**Consequences.**
- Mid-match recognition and threat/target resolution are **O(1) dict lookups** —
  both the meta artifact and the card-stat cache are loaded once at startup.
- Card stats are **authoritative and never stale** (the engine is the runtime
  source of truth); only the meta snapshot is point-in-time and must be
  regenerated/re-bundled to track the meta.
- The meta JSON is a **versioned data contract** between the offline compiler and
  the runtime loader — schema changes must move both in lockstep.
- One-time startup cost to build the card-stat cache (absorbed at import / the
  deck-selection call, not paid per decision).
