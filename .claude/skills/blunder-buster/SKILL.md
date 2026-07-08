---
name: blunder-buster
description: Turn a round of blunder Corrections into ROUTED Strategy Proposals — exhaustively. Reads the correction log, clusters EVERY still-open missing_hypothesis blunder, and analyses each cluster's live_trace to ROUTE it to a target layer: a general when() Hypothesis, a Lethal-Solver/Turn-Planner code fix (live_trace lethal/planned), or a Matchup Brief / recognition fix (live_trace.posture — a matchup misplay tied to its believed archetype). It emits one Strategy Proposal per cluster into data/strategy/proposals/ (thin spec = the correction rationale; verification_contract from the routing; provenance = correction ids + a state fixture), records covered/refuted set-asides by test, and evidences a capability-gap when the sound fix is an unbuilt roadmap layer. It does NOT author when()/code, run the Verifier, or commit — /update-strategy applies each proposal behind its gate (ADR-0046). Every open correction is resolved in-session to a terminal ANALYSIS outcome (proposal-routed / covered / refuted / capability-gap); nothing is punted. CRITICAL-rationale corrections are surfaced first, one at a time, blocking the rest. Invoke as /blunder-buster [corrections.jsonl] (defaults to data/corrections/corrections.jsonl). Use after a round of manual blunder tagging (ADR-0018/0046).
---

# blunder-buster — corrections → routed Strategy Proposals

Convert a **round** of blunder Corrections into **routed Strategy Proposals** for `/update-strategy` to
apply. blunder-buster is an **analysis producer** ([ADR-0046](../../../docs/adr/0046-strategy-authoring-splits-analysis-proposes-one-skill-applies.md)):
it clusters, reads the live trace, decides *which layer* each blunder's fix belongs in, and emits fodder.
It **does not** author `when()`/code, run the Verifier, or commit — that is `/update-strategy` (mechanics:
[../update-strategy/references/authoring-gates.md](../update-strategy/references/authoring-gates.md)). See
`docs/blunder-tuner.md`, ADR-0017, ADR-0018.

**One run resolves the WHOLE open set** to terminal ANALYSIS outcomes — start to finish, no punting.

## Exhaustive completion mandate (read first)

A run is **finished only when the open set is empty** — every still-open correction reaching exactly one
terminal ANALYSIS outcome, with evidence:

- **proposal-routed** — a Strategy Proposal is queued for it (its cluster's routed record in
  `data/strategy/proposals/`). This replaces the old "fixed": blunder-buster no longer authors/commits the
  rule — it hands `/update-strategy` a proposal with the routing + rationale-spec + fixture. (The
  *definition of done* for the blunder is that the proposal exists and is well-formed, not that code
  shipped — that happens at apply time.)
- **covered** — an existing Hypothesis/Brief already handles it; **name** it, confirmed against the real
  Pilot `decide()` (not the W-route). No proposal.
- **refuted** — a bad correction (forgoes a KO / high-value attack), **proven with a test**; dropped from
  the fit. See [[forgo-ko-corrections-are-refuted]]. No proposal.
- **capability-gap** — the sound fix is a designed-but-unbuilt roadmap layer (multi-turn search, opponent
  prize-trajectory, the M4 value model). Evidenced, not punted — the four artifacts, in-session:
  (1) re-measure through the real Pilot first (it may already be covered); (2) fixture the state
  (`tests/fixtures/corrections/<name>.json`); (3) a `docs/todo/` entry with a definition-of-done;
  (4) ledger it (`python tools/train/review_correction.py <ep>-<frame> deferred "capability-gap: <layer> — see docs/todo/<file>"`).
  **A missing signal/tag/enum is NOT a capability-gap** — it's carried in the proposal's `spec` as
  infra-to-build, and `/update-strategy` builds it at apply time (authoring-gates.md).

"Open" = every `missing_hypothesis` proposal in `data/proposals/<deck>.json` `open[]` **plus** every
`UNSATISFIED` line `tune.py` prints. Each lands in exactly one cluster → one outcome above.

**No bare `deferred`, no "future run", no voluntary pauses.** The run executes start → completion gate in
one continuous push; never end a turn reporting remaining clusters. The only sanctioned stops are the
CRITICAL hard-stops and an unresolvable blocker.

## CRITICAL corrections — resolve first, block the run

A Correction is **CRITICAL** when its `rationale` carries the uppercase token `CRITICAL` (case-sensitive;
the pipeline surfaces it — `tune.py` banners it, `open[]`/`skipped[]` carry `"critical": true`,
`reports/blunders.html` badges it). Partition the CRITICAL cohort out first and **list it to the human up
front**. Work it **one at a time to a terminal outcome before any non-critical cluster**, presenting each.
**A CRITICAL that would be `refuted` or `capability-gap` is a HARD STOP** — present the proof (refutation
test / four artifacts) and get explicit human acknowledgement before recording it (the human flagged it
must-fix; overruling that is their call). The cohort never fans out.

## Rounds & reconciliation

One append-only log; each run re-featurizes the **whole** log against the **current** Strategy. A blunder
whose proposal was applied (by `/update-strategy`, committed) is no longer `missing_hypothesis` and drops
out next round. `refuted`/`covered`/capability-gap set-asides go in `data/corrections/reviewed.json` (so
they don't resurface); `tune.py` excludes them. Loop: tag → `/blunder-buster` (route to proposals) →
`/update-strategy` (apply + commit) → tag more → `/blunder-buster` again (applied clusters auto-drop).

## Steps

> Steps 2–3 (analysis + routing) run **per cluster**; step 4 emits the proposal or records the set-aside.

1. **Enumerate & cluster EVERY open proposal.** `python tools/train/tune.py --agent <deck> [--store <path>]`,
   then read `data/proposals/<deck>.json` (`open[]` = the `missing_hypothesis` proposals with
   category/episode/frame/`agent_build`; `skipped[]` = tactical/no-obs). Group all `open` by category +
   similar rationale into **clusters** (one blunder pattern each). Also cluster the **`UNSATISFIED`** lines
   `tune.py` prints (W-route corrections the fit couldn't honour — prime Hypothesis candidates). Build the
   full worklist; **partition out the CRITICAL cohort**. Refresh the dashboard:
   `python tools/train/blunder_report.py`. (`tune.py` also rewrites `tuned.json` — the deterministic
   Tier-0 weight deltas auto-apply, ADR-0018; commit alongside via `/update-strategy`.)

2. **Read the live trace to ROUTE the cluster (ADR-0019).** Each Correction embeds `live_trace` — the `@T`
   telemetry the shipped agent emitted (`opts[].score/tac/fired`, `chosen`, `margin`, `lethal`, `planned`,
   `posture`). This read **determines the proposal's `target_layer` + `verification_contract`**:
   - **Check the sparse reorder markers first** when `chosen` isn't top-`score`: `reordered`+`deferred`
     (attack-last resequencer — a *sequencing* decision, `planner-code`, not an under-weighted attack),
     `needy` (equal-score attach tie-break), `grabbed` (multi-pick set). Don't author a bogus rule to
     "fix" a by-design reorder.
   - **`live_trace.lethal` (ADR-0030)** — the Lethal Solver short-circuits scoring, so a lethal-shaped
     blunder is **`target_layer: planner-code`**, never a weight/`when()`. `null`-but-a-win-existed → the
     generator missed a win-shape; non-null-but-rejected → it over-fired.
   - **`live_trace.planned` (ADR-0031)** — the Turn Planner likewise short-circuits, so a this-turn
     multi-step-line blunder is **`planner-code`**. If the better line spans **>1 of my turns**, it's a
     **capability-gap** (don't bolt multi-turn onto the closed-form Planner —
     `docs/todo/deferred-multi-turn-criticals.md`).
   - **`live_trace.posture` (ADR-0041)** — a `posture_mismatch` (or a cluster sharing one
     `believed_archetype`) is a **matchup-doctrine** miss → **`target_layer: matchup-brief`**, never a
     deck-agnostic `when()`. Right-read-wrong-counterplay → a Brief data/lever change (proposal for the
     existing Brief). No Brief covers it → route to `/matchup-genie <slug>` (a named hand-off). Wrong
     *Read* (γ low) → a recognition gap → capability-gap.
   - Otherwise (no layer flag) → **`target_layer: general-hypothesis`**, `verification_contract: verifier`
     (the correction fixture is the re-measure gate).
   `tune.py` tags lines `[LETHAL]`/`[PLANNED]`/`[POSTURE≠ <arch>]` and the snapshot carries
   `lethal_locked`/`planner_committed`/`posture_mismatch`+`believed_archetype` — build the cohorts from
   those; the `null`-but-should-have half is your rationale read.

3. **Read the feature catalog to write an accurate `spec`** (author against LIVE source, never memory):
   `src/common/pilot.py` (`Context`/`Board` fields), `src/cg/api.py` (enums), `src/common/cards.py` +
   `card_functions.json` (tags), `baseline_*.py` + `src/agents/<deck>/strategy.py` (style), and
   `lethal.py`/`planner.py` for planner-code routes. If the sound fix needs a signal that doesn't exist,
   **say so in the `spec`** (`candidate_signal: "needs a new signal"` + which layer) — `/update-strategy`
   builds it at apply time; that is **not** a capability-gap.

4. **Emit the routed Strategy Proposal — or record the set-aside.**
   - For a **proposal-routed** cluster: write one record into `data/strategy/proposals/` (contract:
     [../update-strategy/references/strategy_proposal_contract.md](../update-strategy/references/strategy_proposal_contract.md)):
     `source: blunder-buster`, `target_layer` + `verification_contract` from step 2, `for: general|deck:<deck>|opponent:<archetype>`,
     `spec` = the cluster's rationales (the authoring spec) + any infra-to-build, `provenance` = the
     correction ids + the fixtured state (`tests/fixtures/corrections/<name>.json`), `status: open`. One
     proposal per cluster, covering **all** its members — not per-correction point-fixes.
   - For **covered/refuted**: `python tools/train/review_correction.py <ep>-<frame> <disp> "<reason>"`
     (refuted → prove with a retest first; covered → name the Hypothesis/Brief, confirm on the real Pilot).
   - For **capability-gap / matchup hand-off**: the four artifacts / the `/matchup-genie <slug>` route,
     ledgered `deferred` with the layer + todo-doc / slug.

5. **Completion gate — prove the open set is empty.** Re-run `python tools/train/tune.py --agent <deck>`:
   every open correction is now either **proposal-routed** (a queued record links its ids), **covered**,
   **refuted**, or an evidenced **capability-gap** (`reviewed (excluded)`). Produce a terminal-outcome
   ledger — one line per correction, its outcome + evidence (proposal id / named Hypothesis / refutation
   test / four artifacts). Refresh `reports/blunders.html`. Only then report the run finished. Then
   `/update-strategy` drains the queued proposals (authors + Verifier/gate + commits).

## Parallel mode (fan-out) — analysis only

Fanning out is now over **analysis** (cluster read + routing + set-aside adjudication), not authoring.
Spawn one agent per SOFT cluster to read its `live_trace`, decide the route, and draft the proposal
`spec`; a serial join dedups and queues the records. The heavy apply-side concurrency (parallel authoring,
`union_verify`) lives in `/update-strategy` (authoring-gates.md), where the writes actually happen. Use
the Workflow tool with the multi-agent opt-in; omit `opts.effort`/`opts.model` to inherit session effort.

## Rules
- **CRITICAL first** — resolved before any other cluster, one at a time; a CRITICAL headed for
  `refuted`/`capability-gap` hard-stops for human acknowledgement. Never fans out.
- **Route, don't author.** blunder-buster's product is a *routed proposal* (or a tested set-aside), never a
  committed `when()`/code. The routing (step 2) is its core value; the authoring is `/update-strategy`'s.
- **One proposal per cluster**, covering all members — not per-correction point-fixes.
- **Layer routing is load-bearing:** lethal/planned → `planner-code`; posture-mismatch → `matchup-brief`
  (or `/matchup-genie`); else → `general-hypothesis`. Never a deck-agnostic weight for a one-archetype
  misplay, never a `when()` for a Solver/Planner-driven decision.
- **Exhaustive or not finished** — every open correction reaches a terminal ANALYSIS outcome this session;
  no bare `deferred`, no "future run".
- **No voluntary pauses / no "say go"** — only the CRITICAL hard-stops and unresolvable blockers stop the run.
- **If you change how tuning/routing works, update `docs/tuning/methodology.md`** in the same change.
