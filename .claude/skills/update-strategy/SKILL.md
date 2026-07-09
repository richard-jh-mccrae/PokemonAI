---
name: update-strategy
description: >
  The SOLE applier of strategy changes for the PokemonAI agent. Consumes Strategy Proposal records
  (structured-markdown fodder) from the unified queue data/strategy/proposals/ — produced by the analysis
  skills (strategy-ingest, blunder-buster, deck-genie, matchup-genie, deck-align) — grills each with the
  user, AUTHORS the change into its target layer (general Hypothesis when()+weight / deck strategy.py /
  matchup Brief JSON / Planner-Lethal code), runs the proposal's declared verification gate, presents a
  diff, and the human commits. Use whenever the user wants to turn analysis into a shipped strategy change:
  "apply the proposals", "update the strategy from this digest/brief/doctrine", "work the proposal queue",
  "/update-strategy". This is the APPLY half split out of the analysis skills (ADR-0046). Do NOT use it to
  FIND/analyse (that's the four producer skills) — it only applies what they proposed.
---

# update-strategy — turn Strategy Proposals into committed strategy changes

The one place that *applies* strategy. Every analysis skill ends at a **Strategy Proposal** (fodder);
this skill drains the queue, authors the real change behind the right gate, and the human commits. It is
ADR-0018 generalised from corrections to all four sources ([ADR-0046](../../../docs/adr/0046-strategy-authoring-splits-analysis-proposes-one-skill-applies.md)).
Contract: [references/strategy_proposal_contract.md](references/strategy_proposal_contract.md).

**Invocation:** `/update-strategy` (drain all open) or `/update-strategy <proposal-file-or-glob>`.

## What it is / is NOT

- **IS** the applier: author + verify + diff + (human) commit, for `general-hypothesis`, `deck-strategy`,
  `matchup-brief`, `planner-code`.
- **NOT** the analyser: it never finds, clusters, researches, or scouts — the producers do that and hand
  it a proposal. If a proposal's `spec` is too thin to author from, it bounces back to the producer, it
  does not go invent the doctrine.

## Workflow

### Phase 0 · Load the queue (deterministic)
Read open Strategy Proposals from `data/strategy/proposals/` (status `open`). For each, follow
`provenance` to its rich source doc (Digest / STRATEGY.md / matchup doctrine / correction) for full
context. Group by `target_layer`. Surface any `spec` too thin to author from → bounce to the producer.

Print the queue summary (count per target layer, count per producer, count per gate) and source doc links.

### Phase 1 · Grill each proposal (per record, one at a time)
With the user, sharpen the proposal into a concrete authored change: resolve the exact trigger/board
condition, the starter weight (on the [weight scale](../../../docs/weights.md)), the id, and confirm the
`candidate_signal` maps to a real signal — or that new infra is needed (→ capability-gap).

### Phase 2 · Author into the target layer (apply-time authoring — thin fodder)
Full apply mechanics per `verification_contract` (author steps + the exact gate + parallel apply):
[references/authoring-gates.md](references/authoring-gates.md). Use the shared per-layer references
(do not reinvent):
- **`general-hypothesis`** → author `when()` + starter weight + `status: assumed` + rationale in
  `src/common/strategy/baseline/baseline_*.py` (feature catalog + [general-strategy.md](../../../docs/general-strategy.md)).
- **`deck-strategy`** → author/extend `src/agents/<deck>/strategy.py` from the STRATEGY.md doctrine.
- **`matchup-brief`** → author `src/common/scouting/briefs/<slug>.json` from the doctrine.
- **`planner-code`** → author the Turn-Planner / Lethal-Solver change (code, not a weight).

### Phase 3 · Run the declared gate (`verification_contract`)
- `verifier` → the deterministic Hypothesis Verifier (re-fit over Corrections; regress none; suite green) — ADR-0018.
- `score-diff` → `tools/sim/score_diff.py` neutrality gate (folds/deck rules — ADR-0034).
- `brief-validator` → `python .claude/skills/matchup-genie/scripts/validate_brief.py <slug>`.
- `seed-ladder` → no state to re-measure: ship as `assumed` seed, **default-on, kill-switched, with
  blunder-buster telemetry**, ladder-validated (gauntlet is invalid-for-gain). Verifier still checks
  well-formedness + suite-green.

### Phase 4 · Diff, commit, status
Present the full diff. **The human commits** (single commit authority for all strategy changes). Then set
the proposal `status` → `applied` (with the commit/id), `refuted` (with why), or `deferred` (a
capability-gap: needs unbuilt infra — record the definition-of-done, like blunder-buster's 4th outcome).

## Guardrails
- **Thin fodder, apply-time authoring** — author from the `spec`; never wait for the producer to hand you
  finished code, and never invent doctrine the producer should have supplied.
- **No auto-commit of executable code** (ADR-0018) — the human commits every diff.
- **Reuse the gates**, don't reinvent them. The gate is chosen by the proposal, not by you.
- **Weights are ladder-tuned seeds** — a doctrine-sourced weight ships `assumed` + kill-switched; never
  present a fabricated number as validated.
- **Card facts:** the engine + `data/EN_Card_Data.csv` are ground truth; a proposal's card claim is its
  producer's claim — verify before shipping (project CLAUDE.md).
