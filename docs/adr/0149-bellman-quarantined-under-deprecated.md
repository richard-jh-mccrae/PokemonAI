# ADR-0149 — The Bellman era moves to `deprecated/`; live source is Ledger-only

Status: Accepted (2026-08-20); BUILT. Follows ADR-0145/0146.

## Context

ADR-0145 made the Ledger the sole live brain, but the Bellman search stack stayed interleaved in
`src/common`: the runtime constructed both brains every match, the Kaggle bundle shipped the dead
search (solver, planner, demand, potential, the seventeen-family value stack), and CI re-ran the
Bellman suites on every source change. The teacher role is real — corrections pins and offline
corpus replay still exercise it — but nothing live selects it, and `tools/train/bellman_corpus.py`
had silently started replaying through the Ledger when ADR-0145 flipped the default brain.

## Decision

Everything that is Bellman-search-and-before is quarantined under `deprecated/`, importable but
one-way: `deprecated/` may ride `src/`, never the reverse.

- **The boundary is a gate, not a convention**: `tests/test_import_hygiene.py` scans every
  checkout file and fails if `src/` or `tools/submit/` imports `deprecated`.
- **`deprecated/bellman/`** holds the moved brain (solver, planner, demand, potential, value,
  value_equations, family_ranking, terminal, commutativity, transition_value, pilot_profile,
  budget_prototype, the refresh evaluator, deck beliefs, dragapult's potential subclass) and
  re-exports the surface `common/__init__.py` used to carry for it.
- **The teacher is a subclass**: `BellmanTeacherRuntime(AgentRuntime)` in
  `deprecated/bellman/runtime.py` reinstates the planner epoch, plan-suffix and proof caches,
  strategy-beam activation and fallback, pilot overlay, and the decision clock.
  `build_teacher_runtime` replaces `build_runtime(..., brain="bellman")`; the six mega_starmie
  correction pins reproduce their pre-move results exactly (including main's one standing red).
- **Providers keep only live hooks**: `footprint`, `terminal_action_supported` (native) and
  `resolve_end` moved to `BellmanNativeProvider`/`BellmanCgpyProvider`;
  `bellman_provider_factory` maps live factories to them, mirroring the preview seam. The
  effect-coverage predicate (`terminal_effects_supported`) relocated to `common/effects.py`
  because the offline provider's ability-noop guard is a live consumer; the cgpy provider keeps
  `terminal_action_supported` for the same reason.
- **Splits at the seam**: `refresh.py` keeps the printed-counts `Refresh` transition (the Ledger
  prices those nodes); the Bellman valuation became `refresh_evaluator.py`. `information.py`
  keeps the exact draw/reveal outcome classes (the offline provider's chance modelling); deck
  profiles and opponent beliefs became `belief.py`.
- **The live shell slims**: `AgentRuntime` (renamed from `BellmanRuntime`) is pregame, forced
  selections, attack-lock folding, the Ledger, and a last-resort crash fallback. The bundle
  therefore stops shipping the search stack; the manifest is schema 7, `system: "ledger"`, and
  documents the resolved `LedgerWeights` instead of a pilot profile.
- **CI runs none of it** (owner's ruling): the moved suites leave every CI job; `deprecated/**`
  stays a known path in the filters only so it does not trip the fail-closed all-jobs fallback.
  The teacher is validated on demand — `python -m pytest deprecated/tests` — accepting that a
  live-tree change can break it between manual runs.

## Consequences

Crash-time decisions degrade from a strategy-beam pick to the last-resort ranked pick, under the
backend id `last-resort-fallback` (the teacher keeps `strategy-fallback`); ADR-0145's loud-crash
regime is what makes that acceptable. `AGENT_OVERLAY`, `AGENT_STRATEGY_ENABLED`, and
`AGENT_DECISION_SECONDS` no longer affect the live shell — they configure only the teacher — and
the packager's `--overlay`/`--strategy` flags are gone with the `runtime_config.json` they wrote.
`Strategy.potential_factory` left the live dataclass; deck potential subclasses are a teacher-side
map. Strategy declarations (`common/strategy/`) stay live as authored data for the phase-2 search
and the deck files that ship. When the teacher finally retires, `deprecated/` deletes whole.
