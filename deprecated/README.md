# Deprecated: the pre-Ledger era

Everything here is Bellman-search-and-before, quarantined by ADR-0149 after ADR-0145 made the
Ledger the sole live brain. It stays importable — the teacher role is real until the training
rounds retire it — but the dependency is one-way: this tree may import `src/`, and nothing in
`src/` or `tools/submit/` may import `deprecated` (`tests/test_import_hygiene.py` enforces it).

## Layout

- `bellman/`: the search brain, its value stack, Bellman algebra, damage/information helpers,
  card-family matching, telemetry compatibility, and canonical `state.py` (DecisionState).
  `runtime.BellmanTeacherRuntime`
  extends the live `common.runtime.AgentRuntime`; `build_teacher_runtime(...)` is the drop-in
  for the old `build_runtime(..., brain="bellman")`. `providers.py` restores the search-only
  provider hooks (`footprint`, the lethal gate, `resolve_end`) on the live engine seams.
- `bellman/card_effects.json`: the teacher's FROZEN effect table (ADR-0153) — the live tree
  bakes clauses into card records instead; this copy is deliberately never regenerated.
- `tests/`: the moved suites — Bellman milestone/policy contracts and the mega_starmie correction
  pins that freeze the teacher's rulings.

## Running the suite

```
python -m pytest deprecated/tests -q -n auto
```

CI deliberately runs none of this tree (ADR-0149): the quarantine is free until someone needs
the teacher. Run the command above before relying on it — a live-tree change made since the
last manual run can have broken it without anything going red.

## Language (teacher-era terms)

**Action Family**: legal sibling choices that answer the same local question.
**Family Score**: an offline diagnostic from a bespoke equation; nothing live consumes it.
**Search Wave**: a cohort of admitted candidates receiving equal shallow planning work.
**Planning Epoch**: planning work from one known state until an information boundary.
**Plan Suffix**: the deterministic remainder of a chosen line, guarded by expected states.
**Information Boundary**: an event revealing unknown facts or handing control to the opponent.
**Structural Prune**: permanent removal justified by coefficient-independent dominance.
**Terminal Proof**: a sound certificate that a legal current-turn policy wins in every outcome.
**Lethal Solver**: the current-turn search producing a Terminal Proof or abstaining.
**Candidate Harvest**: depth-first search for distinct executable lines.
**Demand Slot**: one value-side recipient, capability, and resource requirement.
**Bellman Value**: the comparable utility of an action's resulting state and continuation.
**Bound Prune**: removal proved by an upper bound no better than the executable lower bound.
**Pilot Profile**: the resolved, versioned set of search/value/clock parameters (teacher-only;
the live equivalent is `LedgerWeights` + `Strategy.ledger_overrides`).
