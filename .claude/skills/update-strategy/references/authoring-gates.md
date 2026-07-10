# Authoring & gates — how update-strategy applies a proposal

The apply mechanics for each `verification_contract`, relocated here from blunder-buster under ADR-0046
(that skill now only *analyses + proposes*). update-strategy authors the change from the proposal's thin
`spec`, then runs the declared gate. **No commit without the gate passing; the human commits.**

## `verifier` — general-hypothesis / (from blunder-buster corrections)

The proposal's `provenance` names the correction ids + a state fixture. Author the candidate `when()` from
the `spec` (the correction rationale is the authoring spec):
- Prefer universal features (`tags`, `roles`, `board`, `stat`) over hard-coded `card_id`s; pure + total
  predicate; seed `weight` in-band ([../../../docs/weights.md](../../../docs/weights.md)); `status="assumed"`.
- **Missing signal → build the infra now** (never defer): a derived decision signal → `Context`/`Board`
  in `src/common/pilot.py`; a card-behavioral property → a tag in `card_functions.json` (+ `src/common/cards.py`);
  engine vocabulary → `src/cg/api.py`. Compute pure + total; mirror an existing signal; verify every fact
  at source (`docs/rules.md`, `docs/rulebook.txt`, `data/EN_Card_Data.csv`); add a focused unit test.
- **Verify** (`train.tuner.verify`): build `pilot_with(extra)`, load the cluster's Corrections, require
  `result.passed` (cluster satisfied + empty `regressed`). Too narrow → broaden; too broad → tighten.
- **Retest** (`train.tuner.retest`, ADR-0019): re-derive the decision in `@T` format, diff vs the embedded
  `live_trace`; require `fixed` (the `correct` option now chosen). Show `chosen/margin before→after`.
- **Suite-green** — `python -m pytest tests/ -q` (incl. any new signal's test).
- **Place** — universal trigger → the matching `src/common/strategy/baseline/baseline_<context>.py`
  `HYPOTHESES` (ADR-0025); a card-archetype rule → `src/common/strategy/doctrines/doctrine_*.py`;
  deck-specific → `src/agents/<deck>/strategy.py`. Commit prefix `Blunder Bustin':` for correction-sourced.

## `planner-code` — Lethal Solver / Turn Planner (ADR-0030/0031)

A layer-driven blunder (proposal from a `live_trace.lethal`/`planned` routing) is **never** a weight or
`when()`. Edit `src/common/strategy/lethal.py` (win detection / `_attack_wins` soundness) or
`src/common/strategy/planner.py` (goal line-generators / leaf-eval / commit gate), **plus** a focused test
(`tests/strategy/test_lethal.py` / `test_planner*.py`) gating the correction's state as a fixture
(`tests/fixtures/corrections/`). The Verifier does **not** gate code fixes — the fixtured retest
(surfacing `lethal/planned before→after`) + suite-green are the gate.

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

## `score-diff` — deck-strategy / folds (ADR-0034)

Author into `src/agents/<deck>/strategy.py` (or fold into `baseline_*`), author-time authoring rules per
[../../deck-genie/references/authoring.md](../../deck-genie/references/authoring.md). Gate:
`python tools/sim/score_diff.py diff --agent <deck> --baseline <the proposal's captured baseline>` in
`scores` (folds — score-equality, ADR-0034) or `choice` (vocabulary) mode; a shared-general-rule change
runs it for every corpus agent. Then suite-green + Playability (`tools/sim/check_agent.py <deck>`) + A/B
mirrors when behavior changes. Never hand-edit `tuned.json` (weight_overrides, ADR-0035). Advance the deck
`aligned.json` ledger on a deck-align-sourced commit.

## `seed-ladder` — doctrine with no state fixture (strategy-ingest / doctrine seeds)

No correction to re-measure. Author the `when()`+weight (or code) as an `assumed` seed, **default-on,
kill-switched, with blunder-buster telemetry**; the ladder validates (the cross-deck gauntlet is
invalid-for-gain — see [[gauntlet-invalid-ladder-only]]). The Verifier still checks well-formedness +
suite-green. A seed whose sound form needs new infra is a **capability-gap** (defer with a
definition-of-done), same as the correction path.

## Parallel apply (optional, orchestration-capable sessions)

When ≥2 proposals are file- AND behavior-disjoint (append-only into different `baseline_<context>.py`
`HYPOTHESES`; NOT two touching the same `card_functions.json` card, the same `ROLES`/ctor, or any new
`Context`/`Board` signal — those are always serial), author them in parallel worktree agents, then a
**serial join** union-verifies the merged tree (`train.tuner` `union_verify` — injects each authored
Hypothesis once against a seeds-only baseline; raises on duplicate ids / contaminated baseline; require
`passed` + empty `regressed` over the corpus **including** previously-`covered` corrections), full
`pytest`, and union-retest before any commit. A regressing pair is behavior-dependent → merge into one
cluster, make triggers mutually exclusive, re-enter the full join. Merges are one-way (terminates).
