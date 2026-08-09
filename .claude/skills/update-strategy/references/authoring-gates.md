# Authoring & gates — how update-strategy applies a proposal

The apply mechanics for each `verification_contract`, relocated here from blunder-buster under ADR-0046
(that skill now only *analyses + proposes*). update-strategy authors the change from the proposal's thin
`spec`, then runs the declared gate. **No commit without the gate passing; the human commits.**

## `composer-retest` — Composer/differencer, turn sequencer, and value equation

The proposal's `provenance` names correction ids, a state fixture, and the emitted Composer working.
Do not add a `when()`, Hypothesis, rung, score weight, or deck-local priority. Diagnose from the replay:

- **`composer-differencer`:** fix a missing/refused transition, expectation handling, option-equivalence
  collapse, beam admission, terminal EV, or 1-ply/end-state difference in `common/composer.py` and the
  apply/expectation seam it calls. The test must assert the corrected transition's difference and the
  resulting first action.
- **`turn-sequencer`:** fix sequence expansion, commutativity, continuation handling, or the Composer ↔
  `planner.py` commit hand-off. The test must assert the intended ordered steps and reject the old order.
- **`value-equation`:** alter `state_value.py` only when the proposal names one family and the telemetry
  proves both alternatives were modelled but that family supplied the wrong order. Assert the before/after
  family terms and the decision. Never compensate for an absent transition or an unsearched sequence with
  a value term.

Gate every change by re-driving the correction through the real Pilot and serialising it with
`telemetry.to_record`. Require: corrected `chosen`; a changed relevant `composer.differencing` or
sequence/candidate; unchanged unrelated value families; and no regression in the cluster's other fixtures.
Add focused `tests/strategy/test_composer.py`, `test_planner*.py`, or `test_value*.py` coverage, then run
the suite.

## `lethal-solver` — sound win detection

A verified or missed win is never a heuristic policy adjustment. Edit `common/strategy/lethal.py` only,
with a focused fixture regression in `tests/strategy/test_lethal.py`; retain the engine-cascade proof below
for multi-step wins.

**Multi-step lethal proposals** (retreat/tutor/fetch/attach compositions — a first step whose win
depends on `decide()` driving 2–5 follow-up selects) get the stronger **engine-cascade** gate, not a
closed-form-only retest (ADR-0050). The fixture must carry a seed: backfill it with
`tools/train/backfill_seed.py` (adds `search_begin_input` + the exact `own_prizes` split), then gate on
`tests/lethal_helpers.py::engine_confirms(fixture, pilot) is True` — real play completes the line under
the native engine, not just recognition at the MAIN menu. Author the follow-up encodings against
`tools/sim/lethal_probe.py` (dumps each follow-up select's resolved options), never guessed — a phantom
win loses the game. A closed-form-only line (recognition fires, cascade refutes) is a **false-green**;
`engine_confirms` returns `False` on it.

## `brief-validator` — matchup-brief (ADR-0027)

Author `src/common/scouting/briefs/<slug>.json` from the doctrine `spec` (schema:
`../../../../src/common/scouting/brief.schema.json`), `covers` verbatim from `index.json`; register any new
`opponent_properties` key. Gate: `python .claude/skills/matchup-genie/scripts/validate_brief.py <slug>`.
Commit prefix `matchup:`.

Legacy `verifier`, `score-diff`, and `seed-ladder` proposals that would add or tune a rule are returned to
their producer for Composer/differencer routing. Rule-retirement remains removal-only.

## The conveyor — fan-out for a multi-proposal drain

The time-efficient drain shape (SKILL.md Workflow): the human grills serially while authoring +
per-proposal verification run in **background Agents**, converging at one end-join + one commit. **The grill
never waits on authoring** — that idle time is where the wall-clock is won. Three fan-out points:

1. **Enrich (Phase 0)** — one read-only Agent per proposal, in parallel: resolve `provenance`, confirm the
   `candidate_signal` maps to a real signal, return a grill brief. No merge surface — always safe, always
   worth it.
2. **Author + pre-verify (Phase 2, the conveyor)** — the instant a grill locks, spawn a background Agent to
   author the change and run its Composer retest / `brief-validator` / engine-cascade gate. File- AND
   behavior-disjoint Composer changes run in parallel **worktree** Agents; shared transition and
   `state_value` surfaces serialize. An unbuilt-infra proposal drops off as a capability-gap.
3. **End-join (Phase 3, the one barrier)** — when the conveyor drains, serially re-drive the union of
   correction fixtures and compare `@T` Composer working + **one whole-suite `pytest`**. A regressing pair
   is behavior-dependent → merge into one sequence/differencing cluster and re-enter the join.

**When it pays:** worktree setup is ~200–500ms + disk per Agent, so a 2-append queue may not clear the
overhead — fan out the enrich always; fan out authoring when the queue is large or the gates are heavy
(`score-diff` sims, engine-cascade, A/B mirrors). Serial single-session apply stays correct — the conveyor
is an accelerator, and the end-join barrier is byte-identical either way.
