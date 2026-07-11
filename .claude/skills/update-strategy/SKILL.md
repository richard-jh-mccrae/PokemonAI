---
name: update-strategy
description: The applier of PokemonAI strategy changes — drains the Strategy Proposal queue, authors each proposal into its target layer behind the declared gate, and the human commits. The apply half of ADR-0046.
disable-model-invocation: true
---

# update-strategy — the applier

**update-strategy is the applier**: the one skill that turns a **Strategy Proposal** into committed
strategy. Every analysis skill (the *producers* — strategy-ingest, blunder-buster, deck-genie,
matchup-genie, deck-align) ends at a proposal (fodder) and stops; the applier drains the queue, authors
the real change behind the proposal's gate, and the human commits
([ADR-0046](../../../docs/adr/0046-strategy-authoring-splits-analysis-proposes-one-skill-applies.md)).
Vocabulary: [CONTEXT.md](CONTEXT.md). Proposal shape: [contract](references/strategy_proposal_contract.md).

**Invocation:** `/update-strategy` (drain all open) or `/update-strategy <proposal-file-or-glob>`.

## Workflow — a serial grill feeding a background conveyor

Grill one proposal at a time (the human floor). The instant a decision locks, it drops onto a **background
conveyor** — an Agent authors + pre-verifies it while you grill the next. **The grill never waits on
authoring.** Everything converges at one end-join → one diff → one commit. (Agent-tool background spawn,
not a Workflow: grill and commit stay in the interactive loop. Full fan-out mechanics:
[authoring-gates.md](references/authoring-gates.md).)

### Phase 0 · Load + enrich (fan out, read-only)
Enumerate the queue first. Files are **multi-proposal**: each `## ` entry is one proposal with its own
`- status:` line — status is per-entry, never file-level. Extract the open set in one command (do not
re-derive it):
```
grep -rn '^- status: open' data/strategy/proposals/*.md
```
Each hit is `<file>:<line>: - status: open`; the enclosing `## ` heading above it is the proposal.
Read open proposals from `data/strategy/proposals/` (status `open`). **Fan out one read-only agent per
proposal** to follow `provenance` → source doc, confirm `candidate_signal` maps to a real signal, and
return a tight **grill brief** (candidate trigger + weight band + capability-gap smell). Bounce any `spec`
too thin to author from back to its producer — never invent the doctrine here. Print the queue summary
(count per layer / producer / gate) + briefs.

### Phase 1 · Grill (serial, one at a time)
Grill each proposal against its brief: lock the exact trigger/board condition, the starter weight (on the
[weight scale](../../../docs/weights.md)), the id, and confirm the signal maps to a real one — or route to
capability-gap. On lock, drop it onto the conveyor and move to the next; **do not wait**.

### Phase 2 · Conveyor — author + pre-verify in the background
Per locked proposal a background Agent authors into `target_layer`, then runs *that proposal's own*
`verification_contract` (mechanics + parallel/serial rules: [authoring-gates.md](references/authoring-gates.md)):
- **author** — `general-hypothesis` → `baseline_*.py` `when()`+weight+`status:assumed` · `deck-strategy` →
  `src/agents/<deck>/strategy.py` · `matchup-brief` → `briefs/<slug>.json` · `planner-code` →
  Turn-Planner / Lethal-Solver code.
- **gate** — `verifier` (re-fit over Corrections) · `score-diff` (neutrality, ADR-0034) · `brief-validator`
  (`validate_brief.py <slug>`) · `seed-ladder` (ship `assumed`, kill-switched + telemetry, ladder-validated).

Disjoint proposals author in parallel worktrees; a shared **serial-only surface** (same
`card_functions.json` card, same `ROLES`/ctor, any new `Context`/`Board` signal) serializes. An
unbuilt-infra proposal → capability-gap, off the conveyor.

### Phase 3 · End-join (once, serial — the barrier)
When the last grill lands and the conveyor drains: **union-verify the merged tree** (`train.tuner`
`union_verify` — each Hypothesis injected once vs a seeds-only baseline, over the corpus **including**
previously-`covered` corrections; raises on duplicate ids / regressions) **+ one `pytest` over the whole
suite** — the suite runs once here, not per proposal. A regressing pair is behavior-dependent → merge into
one cluster, triggers mutually exclusive, re-join.

### Phase 4 · One diff, one commit
Present the single combined diff. **The human makes ONE commit** (single commit authority). Set each
proposal `status` → `applied` (shared commit id) / `refuted` (why) / `deferred` (capability-gap +
definition-of-done, like blunder-buster's 4th outcome).

## Guardrails
- **Thin fodder, apply-time authoring** — author from the `spec`; never invent doctrine the producer owed,
  never wait for it to hand you finished code.
- **No auto-commit of executable code** (ADR-0018) — the end-join gate passes first, then the human commits.
- **Weights are ladder-tuned seeds** — a doctrine-sourced weight ships `assumed` + kill-switched; never
  present a fabricated number as validated.
- **Card claims are the producer's** — the engine + `data/EN_Card_Data.csv` are ground truth; re-verify a
  proposal's card claim before shipping.
