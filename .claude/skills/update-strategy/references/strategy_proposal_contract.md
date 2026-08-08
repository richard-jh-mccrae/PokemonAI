# The Strategy Proposal contract (the shared fodder)

Every analysis skill (`strategy-ingest`, `blunder-buster`, `deck-genie`, `matchup-genie`, `deck-align`)
ends by emitting **Strategy Proposal** records; `update-strategy` is their only consumer
([ADR-0046](../../../docs/adr/0046-strategy-authoring-splits-analysis-proposes-one-skill-applies.md)). Get
this shape right and the producers stay focused on analysis while one applier owns authoring+gate+commit.

## Location

Unified queue: **`data/strategy/proposals/`**. One record per proposed change (or a per-batch file
holding a list). The rich source doc (Digest / STRATEGY.md / matchup doctrine / correction) **stays in
its home**; the record **links** to it via `provenance` and never duplicates it.

## The record (structured markdown)

One `## ` entry per proposal, with a fenced field block, then the free-text spec:

```
## <short-proposal-title>
- id: <stable-slug>                     # unique within the queue
- source: strategy-ingest | blunder-buster | deck-genie | matchup-genie | deck-align
- target_layer: general-hypothesis | deck-strategy | matchup-brief | planner-code | rule-retirement
- candidate_signal: <Function Tag / CardStat / board-or-Context field / "needs a new signal">
- verification_contract: verifier | score-diff | brief-validator | seed-ladder
- provenance: <link to source doc + locator, e.g. data/strategy/<digest>.md#unfair-stamp / correction 83661652:f3>
- status: open | applied | refuted | deferred
- for: <general | deck:<deck> | opponent:<archetype>>   # who it targets

**Spec (authoring spec — thin fodder, not finished code):**
<the doctrine/claim/rationale, rich enough for update-strategy to author from — WHAT the rule must do and
WHY it wins; the concrete trigger/weight are resolved at apply time, not pre-baked here.>
```

## Field rules

- **`target_layer` picks the authoring path and (with `verification_contract`) the gate.** The producer
  decides it — it knows whether its finding is a general rule, deck rule, opponent Brief field, or a
  Planner-code change.
- **`rule-retirement` is the one REMOVAL layer** (blunder-buster): remove (or, for
  a rule that also fires on KO/lethal turns, *demote* — narrow the `when()`) a scoring Hypothesis a
  broader mechanism already subsumes. `update-strategy` deletes the Hypothesis definition + its `tuned.json`
  weight and ledgers it. `verification_contract: seed-ladder` — proof is the **batched R-off ladder run**:
  candidates' weights are zeroed in ONE committed build, submitted, and
  a neutral-or-positive ladder delta confirms the batch (a regression bisects). The `spec` names the rule
  id, its charter (why it's inside the rung's within-turn-development mandate), and the corroboration
  count; it must NOT be applied before its R-off ladder run returns.
- **`verification_contract` is chosen by the finding's nature, not the layer alone:**
  - `verifier` — the finding has a **state fixture / correction** to re-measure against (blunder-buster).
  - `score-diff` — a deck rule / fold that must stay score-neutral (ADR-0034).
  - `brief-validator` — a matchup Brief field (schema + covers + card-in-deck checks).
  - `seed-ladder` — **doctrine with no state to re-measure** (strategy-ingest, deck/matchup doctrine): ship
    as an `assumed` seed, default-on, kill-switched, blunder-buster telemetry, ladder-validated.
- **`spec` is thin.** It carries the authoring intent, not the code. If a producer finds itself writing
  the `when()` predicate or the Brief JSON, that authoring belongs in `update-strategy`; the producer
  over-reached. (Exception: none — keep the seam clean.)
- **`candidate_signal = "needs a new signal"`** is a legitimate, useful value: it tells `update-strategy`
  the honest outcome may be a **capability-gap** (new Context/Board/Scouting infra to build first), not a
  one-shot authoring.
- **`provenance` must resolve.** A record with no working link back to its source doc/correction is not
  applyable — bounce it.

## Producer responsibilities (post-ADR-0046 migration)

- `strategy-ingest` — Digest Agent-Doctrine entries → proposals (already ~this shape; the migration is to
  also drop a linked record into the queue). `general` → `general-hypothesis`/`planner-code`;
  `opponent:` → `matchup-brief`; `our-deck:` → `deck-strategy`.
- `blunder-buster` — cluster/route/triage only; emit proposals (`verifier` contract, correction id in
  `provenance`) or capability-gaps. Drops authoring+Verifier+commit.
- `deck-genie` — grilled STRATEGY.md → `deck-strategy` proposals (`score-diff`). Drops `strategy.py`.
- `matchup-genie` — grilled doctrine → `matchup-brief` proposals (`brief-validator`). Drops Brief JSON.
- `deck-align` — fold/adopt diffs → proposals (`score-diff`). Drops the apply half.
