---
name: deck-align
description: >
  Re-align an EXISTING agent's deck strategy with the current General Strategy and Pilot systems —
  the recurring maintenance pass (ADR-0036) that keeps every agent in top form as common/ evolves.
  Ledger-diffed (aligned.json), score_diff-gated, fold-capable: retires/folds deck rules the
  general layer now covers (ADR-0034), suggests deck rules that could be generalized, adopts new
  vocabulary and opt-in surfaces (params, tags, Context/Board fields, Brief coverage), and
  refreshes STRATEGY.md dispositions + hygiene. Use whenever the user wants to update, refresh,
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
   `data/proposals/<deck>.json` + `data/corrections/reviewed.json` — blunder-buster may have
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
  `preferred_start` / `search_budget`, `fetch_priority`, Matchup-Brief coverage, new Roles).
- **Docs + hygiene**: STRATEGY.md dispositions naming renamed/moved rules; stale fold-table rows;
  stale migration NOTEs; `tuned.json` keys matching no live Hypothesis id (breaks
  `test_tuned_wiring`); `weight_overrides` entries whose underlying general seed has drifted
  since authoring → re-justify or drop.

## Phase 2 · Per-item sign-off

Walk the report one item at a time. Anything that moves or rewrites a rule (every fold,
generalization, weight change, wiring that activates new behavior) gets an explicit approve /
reject from the user before execution. Pure hygiene (stale NOTEs, doc renames, dead tuned keys)
may be batched under one approval.

## Phase 3 · Execute + gate (approved items only)

Author against live source (never memory), following deck-genie's authoring rules. Then gate:

1. **Suite** — `python -m pytest tests/ -q` green.
2. **score_diff** — `python tools/sim/score_diff.py diff --agent <deck> --baseline
   data/score_diff/<deck>.base.json` in the mode the item demands: `scores` for folds
   (score-equality, the ADR-0034 bar), `choice` for vocabulary fixes. Zero divergence, or every
   intended divergence enumerated + justified in the report. A change to a **shared general rule**
   runs score_diff for **every** agent with a corpus.
3. **Playability** — `python tools/sim/check_agent.py <deck>`.
4. **A/B mirrors** — ONLY when the pass intends behavior change (weight shifts, activating
   wiring): self-play old-vs-new via `tools/sim/battle.py`; flag a winrate outside the noise band
   instead of shipping silently.

Never hand-edit `tuned.json` (tuner-owned, ADR-0018) — authored deltas go in
`Strategy.weight_overrides`. Never let a positional rule override a KO.

## Phase 4 · Record + present

1. Update STRATEGY.md (dispositions, fold table, NOTEs) and, for folds,
   `docs/general-strategy.md`; glossary only if vocabulary moved (`src/common/CONTEXT.md`).
2. Write the ledger `src/agents/<deck>/aligned.json`:
   `{"common_commit": "<HEAD sha>", "aligned_at": "YYYY-MM-DD", "summary": "<one line>"}`
   (local provenance — the Bundle whitelist never ships it).
3. Present the full diff + the gate evidence. **The human commits** (ADR-0017).

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
  when a pass completes Phase 4.
