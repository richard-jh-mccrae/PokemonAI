---
name: deck-align
description: >
  Re-align an EXISTING agent's deck strategy with the current General Strategy and Pilot systems —
  the recurring maintenance pass (ADR-0036) that keeps every agent in top form as common/ evolves.
  Ledger-diffed (aligned.json), it produces a drift report and, for each approved finding, ENDS at
  fodder — Strategy Proposals in data/strategy/proposals/ (ADR-0046): folds of deck rules the general
  layer now covers (ADR-0034), generalization suggestions, new-vocabulary/opt-in adoptions, and
  STRATEGY.md hygiene. It does NOT execute or commit — /update-strategy applies each proposal (score_diff-
  gated) and advances the ledger. Use whenever the user wants to update, refresh,
  re-align, or modernize an already-built deck/agent against the system: "align <deck>",
  "/deck-align <deck>", "bring mega_starmie up to date", "are my agents aligned with common?",
  "run an alignment pass". This is deck-genie's MAINTENANCE counterpart. Do NOT use it to author a
  new deck's doctrine from scratch (that's /deck-genie), to tune weights from blunder corrections
  (that's /blunder-buster), or to author opponent counterplay (that's /matchup-genie).
---

# deck-align — the recurring alignment pass (ADR-0036)

Reconcile one agent's `src/agents/<deck>/` (strategy.py + STRATEGY.md + sidecars) with the
**current** state of `src/common`. deck-genie authors a deck once; this skill owns the upkeep as
the General Strategy grows. Direction of travel is [ADR-0034](../../../docs/adr/0034-deck-rules-fold-general-when-vocabulary-is-general.md):
**rules migrate toward general**; a deck file converges on declarations (Roles / Lines / params),
authored `weight_overrides` ([ADR-0035](../../../docs/adr/0035-weight-overrides-are-authored-seeds-under-learned-deltas.md)),
genuinely deck-bound Hypotheses, and migration NOTEs.

**Invocation:** `/deck-align <deck>` (one pass) · `/deck-align <deck> --full` (ignore the ledger,
re-reconcile everything) · bare `/deck-align` (staleness report across all agents, then pick).
A deck with no real `strategy.py` is deck-genie's job first — report it, don't align it.

Shared reference (do not restate — read them): deck-genie's
[references/authoring.md](../deck-genie/references/authoring.md) (trigger authoring rules, the
three gates) and its Phase-4 disposition vocabulary (`covers-as-is` / `override-candidate` /
`conflicts` / `gap`).

## Phase 0 · Orient (silent, deterministic)

1. **Read the ledger** `src/agents/<deck>/aligned.json` —
   `{"common_commit", "aligned_at", "summary"}`. Missing ⇒ first pass ⇒ `--full` behavior.
2. **Scope the drift**: `git diff <ledger-commit>..HEAD -- src/common src/agents/<deck>
   docs/general-strategy.md docs/adr` (on `--full`: treat everything as changed). Also read
   `data/corrections/tuner/<deck>.json` + `data/corrections/reviewed.json` — blunder-buster may have
   authored deck rules since (each is "a standing folding candidate", ADR-0034).
3. **Read the deck**: strategy.py (hypotheses, roles, lines, params, weight_overrides),
   STRATEGY.md (dispositions, fold table, progress), tuned.json (learned keys).
4. **Capture the score_diff baseline BEFORE touching anything**:
   `python tools/sim/score_diff.py capture --agent <deck> --out data/score_diff/<deck>.base.json`

## Phase 1 · Drift report (present, then walk it)

From the diff, produce a categorized report — each finding carries a recommendation and the
evidence (rule ids, commits, files). Three axes:

- **Folds** (ADR-0034, recurringly applied):
  - a deck Hypothesis whose trigger vocabulary is (or has become) universal → fold into the
    matching `baseline_*` cluster / doctrine under a card-name-free id;
  - a deck Hypothesis now **covered** by a newer general rule or **subsumed by a system**
    (Planner / Lethal Solver / a doctrine Mixin / Pilot sequencing) → retire with a migration
    NOTE naming the successor;
  - a deck rule that *could* generalize with a rewrite → **suggest** it (broadened trigger must
    be provably vacuous on this deck's pool, per ADR-0034);
  - weight differs from the general twin's seed → fold anyway; the deck's band goes to
    `weight_overrides` (score-equal for this deck, ADR-0035).
  Partial coverage is NOT a fold — keep, split, or generalize. Coverage is proven on recorded
  decisions (`score_diff`), never by prose similarity.
- **Vocabulary + wiring**: triggers still reading old/brittle forms where new `Context`/`Board`
  fields or Function Tags exist; unwired opt-in surfaces (`params` like `my_archetype` /
  `preferred_start` / `search_budget`, `fetch_priority`, `starter_priority`, Matchup-Brief coverage,
  new Roles).
  - **Named check — the opening pick (ADR-0078).** A deck with **≥2 startable bodies** (Basics, plus
    `opener`-tagged cards) and **no `starter_priority`**, or one whose declaration does not rank
    *every* startable body, is a **drift finding** — not a nice-to-have. It is the only rule at the
    Set-Up Active seam, so an undeclared or partial deck loses that decision to the engine's option
    index (the dragapult f2 / mega_lucario f1 bug). Also flag any surviving deck Hypothesis gated on
    `_SETUP_ACTIVE`: it is a fold candidate into the declaration by construction, and if it reads a
    `card_id` it is the card-id reflex ADR-0078 removed.
- **Docs + hygiene**: STRATEGY.md dispositions naming renamed/moved rules; stale fold-table rows;
  stale migration NOTEs; `tuned.json` keys matching no live Hypothesis id (breaks
  `test_tuned_wiring`); `weight_overrides` entries whose underlying general seed has drifted
  since authoring → re-justify or drop.

## Phase 2 · Per-item sign-off

Walk the report one item at a time. Anything that moves or rewrites a rule (every fold,
generalization, weight change, wiring that activates new behavior) gets an explicit approve /
reject from the user before execution. Pure hygiene (stale NOTEs, doc renames, dead tuned keys)
may be batched under one approval.

## Phase 3 · Emit Strategy Proposals (approved items only; ADR-0046)

deck-align **authors no code, runs no gate, commits nothing.** For each approved drift-report item,
write a **Strategy Proposal** into `data/strategy/proposals/` (contract:
[../update-strategy/references/strategy_proposal_contract.md](../update-strategy/references/strategy_proposal_contract.md)):
- **fold / generalization** → `target_layer: general-hypothesis`, `verification_contract: score-diff`;
- **deck-local rewrite / wiring** → `target_layer: deck-strategy`, `verification_contract: score-diff`;
- **hygiene** (stale NOTEs, doc renames, dead tuned keys) → `target_layer: deck-strategy`,
  `verification_contract: score-diff` (trivial; applier commits it).

Each `spec` names the exact move (rule id, source→target file/cluster, the fold bar it must meet) and
links the Phase-0 `score_diff` baseline in `provenance` so the applier can diff against it. `/update-strategy`
then authors the edit, runs the gates the item demands (suite → `score_diff` in `scores`/`choice` mode; a
shared-general-rule change runs it for **every** corpus agent → Playability → A/B mirrors only when
behavior changes), updates STRATEGY.md/`docs/general-strategy.md`, and commits. It never hand-edits
`tuned.json` (authored deltas → `weight_overrides`, ADR-0035) and never lets a positional rule override a KO.

## Phase 4 · Present + hand off

1. Present the **drift report** + the **queued proposal set** (one record per approved item).
2. The ledger `src/agents/<deck>/aligned.json`
   (`{"common_commit", "aligned_at", "summary"}`) **advances when `/update-strategy` commits** the
   applied proposals — that skill writes it (local provenance; the Bundle whitelist never ships it),
   so an aborted apply doesn't falsely mark the deck aligned.
3. deck-align's own output is the proposals + report — no diff, no commit here (ADR-0046).

## Completion discipline — one continuous pass (no convenient stopping points)

Phase 2's per-item verdicts are the ONLY approval stops in this skill. Once the verdicts are in,
Phases 3–4 run to completion in **one continuous push**: every approved item written as a Strategy
Proposal, the report + queued set presented. (Execution/gating/commit happen in `/update-strategy`.)
Hard rules:

- **Never end a turn with approved items still un-queued** ("queued 3 of 7 — say go"). If you can
  name the next approved item, write its proposal now.
- **A "clean checkpoint" mid-execution is never a reason to stop.** Resumability covers involuntary
  interruption (context limits, crashes), not voluntary pauses.
- **Legitimate stops, exhaustively:** a Phase-2 verdict still owed by the user, a gate failure that
  needs a user decision (e.g. an unexplained score_diff divergence), or a hard blocker you cannot
  resolve. Everything else: keep executing.
- The pass is done only when Phase 4 completes — nothing less.

## Staleness sweep (bare `/deck-align`)

For each `src/agents/*/` with a strategy.py: read its ledger, count commits touching
`src/common` since, and report `deck · last-aligned date · commits behind · quick drift guess`.
Recommend which deck to align first. No edits in sweep mode.

## Guardrails

- **Behavior-neutral by default** — a pass with no approved behavior change must prove
  score-equality end to end. The mega_starmie 24%-regression is the scar; score_diff is the guard.
- **Engine is ground truth** for card facts (`docs/rules.md` first); the **user** for intent;
  ADR-0034/0035/0036 for placement and precedence.
- **Fold bar**: universal vocabulary, score-equal (or provably-vacuous broadening), card-name-free
  id, rationale credits the origin deck as an example.
- Resumable: the drift report + per-item verdicts live in the session; the ledger only advances
  when a pass completes Phase 4. Resumability is for involuntary interruption only — never a
  license to stop voluntarily (see Completion discipline).
- **No convenient stopping points** — after verdicts, emit a proposal for ALL approved items through
  Phase 4 in one push; never end a turn listing remaining approved work.
