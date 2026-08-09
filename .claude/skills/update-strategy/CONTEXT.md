# Strategy Application

Glossary for the `update-strategy` skill and the analysis/application split (ADR-0046). Runtime terms
(**Hypothesis**, **Verifier**, **Brief**, **Turn Planner**) are canonical elsewhere and reused verbatim.

## Language

**Strategy Proposal**:
The shared fodder record — a structured-markdown unit of proposed strategy change emitted by an analysis
skill and consumed only by `update-strategy`. Carries `source`, `target_layer`, a thin `spec` (authoring
spec), `candidate_signal`, `verification_contract`, `provenance` (link to the rich source doc), and
`status`. Lives in the unified queue `data/strategy/proposals/`. Generalises the correction-path
tuner ledger `data/corrections/tuner/*.json` to all sources.
_Avoid_: fodder (informal), correction (that's the specific blunder-source input), digest (a strategy-ingest source doc).

**Analysis skill / Producer**:
A skill that *finds/clusters/researches/scouts* and ends at a Strategy Proposal — `strategy-ingest`,
`blunder-buster`, `deck-genie`, `matchup-genie`, `deck-align`. It never authors or commits executable
strategy (post-migration).
_Avoid_: authoring skill (they stop before authoring).

**Applier**:
`update-strategy` — the sole skill that authors a proposal into its target layer, runs its gate, and
lets the human commit. The apply half split out of the producers (ADR-0018 generalised).
_Avoid_: compiler (evocative but implies determinism; authoring is LLM-behind-a-gate).

**Target layer**:
Where a proposal is applied: `composer-differencer` (transition modelling and sequence scoring),
`turn-sequencer` (Composer search and planner hand-off), `value-equation` (a proven `state_value` term),
`lethal-solver` (sound win detection), or `matchup-brief` (a Brief JSON). `update-strategy` never adds
a Hypothesis, rung, or `when()` predicate.
_Avoid_: destination.

**Verification contract**:
The gate a proposal declares for `update-strategy` to pass: `composer-retest` (fixture re-drive plus
emitted Composer working), `engine-cascade` (native multi-step proof), or `brief-validator` (Brief
schema/covers/card checks).
_Avoid_: gate (fine informally; the field name is verification_contract).

**Capability-gap**:
A proposal whose sound application needs unbuilt infra (a new signal / Context / Board / Scouting field).
Resolved as `status: deferred` with a definition-of-done, not silently dropped — mirrors blunder-buster's
4th outcome.
_Avoid_: blocked, wontfix.
