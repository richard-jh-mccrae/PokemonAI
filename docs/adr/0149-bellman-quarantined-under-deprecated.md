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
  budget_prototype, DecisionState, the strategy activation engine, the refresh evaluator, Bellman
  algebra, damage/information helpers, telemetry compatibility, deck beliefs, dragapult's potential
  subclass) and re-exports the surface `common/__init__.py`
  used to carry for it. What stays in `src/common` outside cards/board/ledger is exactly the
  live agent's dependency set plus the offline engine twin the Ledger corpus and its tests run
  on (`engine.py`, `information.py`) and the scouting layer PR #576 wires into the Ledger.
- **The teacher is a subclass**: `BellmanTeacherRuntime(AgentRuntime)` in
  `deprecated/bellman/runtime.py` reinstates the planner epoch, plan-suffix and proof caches,
  strategy-beam activation and fallback, pilot overlay, and the decision clock.
  `build_teacher_runtime` replaces `build_runtime(..., brain="bellman")`; the six mega_starmie
  correction pins reproduce their pre-move results exactly (including main's one standing red).
- **Providers keep only live hooks**: `footprint`, `terminal_action_supported` (native) and
  `resolve_end` moved to `BellmanNativeProvider`/`BellmanCgpyProvider`;
  `bellman_provider_factory` maps live factories to them, mirroring the preview seam. The
  effect-coverage predicate (`terminal_effects_supported`) lives in `engine.py` with its one
  live consumer, the offline provider's ability-noop guard; the cgpy provider keeps
  `terminal_action_supported` for the same reason.
- **Splits at the seam**: `refresh.py` keeps the printed-counts `Refresh` transition (the Ledger
  prices those nodes); the Bellman valuation became `refresh_evaluator.py`. `information.py`
  keeps provider draw/reveal outcomes; Bellman demand-count classes moved with their sole consumer;
  deck profiles and opponent beliefs became `belief.py`; the strategy declaration/activation catalog
  was deleted once the Ledger became the live decider. `state.py` (DecisionState, the providers'
  canonical-state build) moved whole: the live path
  constructs none (ADR-0146's pin) and both providers are duck-typed over the state shape, so
  the ADR-0146 heavy-vs-light parity tests now import it from the quarantine — honestly, since
  that pin is precisely a comparison against the quarantined binding.
- **The live shell slims**: `AgentRuntime` (renamed from `BellmanRuntime`) is pregame, forced
  selections, attack-lock folding, the Ledger, and a last-resort crash fallback. Match-start
  role resolution reads the unified card records (`Roles.resolve(deck)`: authored
  `default_roles`, deck declarations REPLACING, ancestry from `evolves_from`) — the pre-store
  tag inference moved to `scouting/pokemon_roles.py`, where it remains the coverage mechanism
  for opponent cards without a record; the teacher re-resolves through
  `legacy_roles_resolve` so its frozen contract is untouched. This corrected a live
  mispricing: the inference was overwriting mega_lucario's authored `supporter_tutor` on
  Meowth ex with off-vocabulary words the Ledger prices at zero. `card_tags.is_card_key`
  folded into `cards/tags.py`. `CardEffects` (the pre-store clause table) moved to the
  quarantine with its one remaining runtime consumer, the teacher: the deck tracker's
  known-top stackers now read the store's record clauses (provably identical live — the only
  two `deck_top` cards are in no shipped deck), and the coverage predicate moved into
  `engine.py`, its one live consumer. `card_effects.json` STAYS in src as the audited
  authoring source the store records are generated from, but leaves the bundle. The bundle
  therefore stops shipping the search stack; the manifest is schema 7, `system: "ledger"`, and
  documented the then-current resolved weight vector instead of a pilot profile; Issue #582
  replaced that vector with the effective Valuation Configuration.
- **CI runs none of it** (owner's ruling): the moved suites leave every CI job; `deprecated/**`
  stays a known path in the filters only so it does not trip the fail-closed all-jobs fallback.
  The teacher is validated on demand — `python -m pytest deprecated/tests` — accepting that a
  live-tree change can break it between manual runs.

## Consequences

Crash-time decisions degrade to the last-resort ranked pick under the backend id
`last-resort-fallback`; ADR-0145's loud-crash regime is what makes that acceptable.
`AGENT_OVERLAY` and `AGENT_DECISION_SECONDS` no longer affect the live shell — they configure only
the teacher — and
the packager's `--overlay`/`--strategy` flags are gone with the `runtime_config.json` they wrote.
`Strategy.potential_factory` left the live dataclass; deck potential subclasses are a teacher-side
map. When the teacher finally retires, `deprecated/` deletes whole.
