# ADR-0046: Strategy authoring splits — analysis skills propose, one skill applies

**Status:** Accepted (2026-07-09). `update-strategy` built + proven; **all five producers trimmed to
emit proposals (2026-07-09)** — apply mechanics relocated to
`.claude/skills/update-strategy/references/authoring-gates.md`. Remaining: exercise the end-to-end
apply on real queued proposals.

## Context

Five skills now touch agent strategy. Four of them *analyse* a source and three of those also *apply*
the result — they author executable strategy AND verify AND commit, all in one skill:

- `strategy-ingest` — external articles/videos → a **Strategy Digest** (fodder only; already terminates
  at fodder — [strategy-ingest](../../.claude/skills/strategy-ingest/SKILL.md)).
- `blunder-buster` — correction log → cluster/route → **authors `when()` rules / routes to
  Planner-Lethal code / ties to Briefs → Verifier → commit**.
- `deck-genie` — deck.csv → grilled STRATEGY.md doctrine → **emits `strategy.py`**.
- `matchup-genie` — opponent deck → grilled doctrine → **emits the Brief JSON**.
- `deck-align` — maintenance diff → **applies folds/adoptions**.

The apply step is the same *shape* every time (author into a layer → run that layer's gate → present a
diff → human commits) and is already codified for the correction path by
[ADR-0018](0018-applying-tuner-output.md): weights auto-load; Hypotheses are LLM-authored **from the
Correction rationale (the authoring spec) behind the deterministic Verifier**; the human commits; no
auto-commit of code. But that apply engine is trapped inside `blunder-buster`, and re-implemented in a
bespoke way inside each genie. The four analysis skills carry unfocused scope (they must each know how to
*write and gate* their target layer), and there is no single place that owns "turn a strategy proposal
into a committed change."

## Decision

**Split analysis from application at a shared fodder seam.** The four analysis skills each **end at
fodder** — a `Strategy Proposal` record. One new skill, **`update-strategy`**, is the sole applier:
it grills a proposal, authors the change, runs the proposal's gate, and the human commits.

### The `Strategy Proposal` contract (the fodder)

A structured-markdown record (one per proposed change), emitted by every producer, consumed only by
`update-strategy`. Fields:

- `source` — `strategy-ingest | blunder-buster | deck-genie | matchup-genie | deck-align`.
- `target_layer` — `general-hypothesis | deck-strategy | matchup-brief | planner-code`.
- `spec` — the **authoring spec**: the doctrine/claim/rationale rich enough to author from (per ADR-0018,
  the rationale *is* the spec, not a footnote). **Thin fodder** — NOT the finished code.
- `candidate_signal` — a non-binding pointer at what it might key on (Function Tag / CardStat / board or
  Context field / "needs a new signal").
- `verification_contract` — which gate `update-strategy` must pass: `verifier` (re-measure over
  Corrections), `score-diff` (neutrality gate), `brief-validator`, or `seed-ladder` (ship as `assumed`
  seed, kill-switched + telemetry, ladder-validated — for doctrine with no state fixture to re-measure).
- `provenance` — link to the rich source doc (Digest / STRATEGY.md / matchup doctrine / correction id).
  **The source doc stays in its home; the record links, never duplicates.**
- `status` — `open → applied | refuted | deferred (capability-gap)`.

Records live in a **unified queue: `data/strategy/proposals/`** — one place to see everything open,
generalising today's per-deck `data/proposals/*.json`.

### `update-strategy` (the sole applier)

Reads open records → grills each with the human → authors into `target_layer` using shared per-layer
references (weights.md, the Verifier, `validate_brief.py`, `score_diff.py`) → runs the
`verification_contract` gate → presents a diff → **the human commits** (single commit authority) →
updates `status`. **Thin fodder, apply-time authoring** — exactly ADR-0018 generalised from corrections
to all four sources.

## Alternatives considered

- **Keep apply inside each skill (status quo).** Rejected: duplicated apply machinery, unfocused scope,
  no cross-source "what's open" view.
- **Rich fodder + `update-strategy` as a thin commit-gate.** Rejected: the analysis skills would still do
  the hard authoring, so their scope wouldn't actually narrow, and `update-strategy` wouldn't justify
  being a skill.
- **Fold everything into `blunder-buster`.** Rejected: it is correction-centric (log, `reviewed.json`,
  CRITICAL ordering, re-measure gate); doctrine sources need a different gate (`seed-ladder`) and would
  muddy a sharp tool.
- **Per-source formats, consumer dispatches.** Rejected: reintroduces unfocused scope on the consumer.

## Consequences

- **Complexity relocates, it does not vanish:** `update-strategy` must know all four target layers + four
  gates. Mitigated by (a) thin fodder carrying the authoring spec, (b) shared per-layer references, (c)
  reusing the existing gates as tools rather than reinventing them.
- **`blunder-buster`'s re-measure gate survives the split** because the proposal carries the correction
  id + state fixture in `provenance`/`verification_contract=verifier`; `update-strategy` runs the same
  Verifier. blunder-buster keeps cluster/route/triage/capability-gap; it drops authoring+Verifier+commit.
- **Genies cut at their existing Phase-A/B seam:** deck-genie keeps STRATEGY.md, matchup-genie keeps the
  doctrine; each emits proposals instead of code/JSON.
- **Migration is staged and de-risked:** build the contract + `update-strategy` first and prove it on the
  existing Digest's Unfair-Stamp general claim, THEN trim producers one at a time (blunder-buster last —
  most entangled). Until a producer is trimmed it keeps working; nothing breaks mid-migration.
- **Supersedes the apply half of ADR-0018 conceptually** (weights still auto-load deterministically; the
  Hypothesis authoring/Verifier step moves from blunder-buster into `update-strategy`).
