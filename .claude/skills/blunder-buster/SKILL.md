---
name: blunder-buster
description: Route every open blunder Correction (all agents) to a Strategy Proposal — barrier Workflow fan-out, one agent per correction, uncertainty-gated CRITICAL-first human pass, join clusters. /update-strategy applies. Run after blunder tagging.
disable-model-invocation: true
---

# blunder-buster — corrections → routed Strategy Proposals

Convert a **round** of blunder Corrections — **across every agent in the log** (all decks) — into
**routed Strategy Proposals** for `/update-strategy` to apply. blunder-buster is an **analysis producer**
([ADR-0046](../../../docs/adr/0046-strategy-authoring-splits-analysis-proposes-one-skill-applies.md)): it
reads the live trace, decides *which layer* each blunder's fix belongs in, clusters, and emits fodder. It
**does not** author `when()`/code, run the Verifier, or commit — that is `/update-strategy`
([../update-strategy/references/authoring-gates.md](../update-strategy/references/authoring-gates.md)).
See `docs/blunder-tuner.md`, ADR-0017, ADR-0018.

**Scope = ALL agents by default.** `/blunder-buster` sweeps every agent with `own` corrections (`tune.py`
with no `--agent`). `/blunder-buster <deck>` narrows to one agent when you deliberately want just one;
optional `--store <path>`. The CRITICAL cohort, the worklist, and the completion gate span **every** agent
unless narrowed.

**One run resolves the WHOLE open set — for every agent** — to terminal outcomes, start to finish, no
punting. "Open" = every entry in every tuner ledger `data/corrections/tuner/*.json` `open[]` (the
`missing_hypothesis` proposals **plus** every scoped turn/match Correction, ADR-0049) **plus** every
`UNSATISFIED` line `tune.py` prints for any agent.

## Terminal outcomes (definition of done)

Every open correction reaches **exactly one**, with evidence. The run is finished only when the open set
is empty for **every** agent.

- **proposal-routed** — a well-formed Strategy Proposal is queued (its cluster's record in
  `data/strategy/proposals/`). Done = the proposal *exists*, not that code shipped — `/update-strategy`
  ships it.
- **covered** — an existing Hypothesis/Brief already handles it; **name** it, confirmed against the real
  Pilot `decide()` (not the W-route). No proposal.
- **refuted** — a bad correction (forgoes a KO / high-value attack), **proven with a test**; dropped from
  the fit. See [[forgo-ko-corrections-are-refuted]]. No proposal.
- **capability-gap** — the sound fix is a designed-but-unbuilt roadmap layer (multi-turn search, opponent
  prize-trajectory, the M4 value model). **Evidenced, not punted** — four artifacts: (1) re-measure
  through the real Pilot first (may already be covered); (2) fixture the state
  `tests/fixtures/corrections/<name>.json`; (3) a `docs/todo/` entry with a definition-of-done; (4) ledger
  it: `python tools/train/review_correction.py <key> deferred "capability-gap: <layer> — see docs/todo/<file>"`.
  **A missing signal/tag/enum is NOT a capability-gap** — carry it in the proposal's `spec` as
  infra-to-build; `/update-strategy` builds it.

## The pipeline — barrier fan-out

**0. Enumerate.** `python tools/train/tune.py [--store <path>]` with **no `--agent`** → processes every
agent, rewrites each `data/corrections/tuner/<deck>.json`. Read **all** `open[]` + the printed
**`UNSATISFIED`** lines → the **worklist**, one item per correction (**no clustering yet** — clustering is
the join). Partition the **CRITICAL cohort** (any correction whose `rationale` carries the uppercase token
`CRITICAL`). Refresh the dashboard: `python tools/train/blunder_report.py`. (This Enumerate run WRITES —
it rewrites each `data/corrections/tuner/<deck>.json` ledger, and also each `tuned.json` with a fresh
deterministic Tier-0 re-fit — committed via `/update-strategy`. Every *other* `tune.py` invocation in this
skill is a CHECK, so pass **`--dry-run`** there — `tune.py` has no other read-only mode, so a bare re-run
recompiles + clobbers the committed `tuned.json`.)

**1. Fan out — one agent per correction (Workflow; the barrier).** Spawn one leaf per worklist item.
Each leaf reads its correction's scope + `live_trace` + fixture, follows
[`references/routing.md`](references/routing.md), and returns the **leaf contract** (below): a
provisional route, a drafted mini-spec, a plain-terms explanation + board state, and **one terminal
outcome OR an `uncertain` flag**. Leaves run **headless** — no human mid-run; the Workflow **completing IS
the barrier**. Pass the worklist as the Workflow `args` (arrives JSON-stringified — `JSON.parse` it) and
validate each return against the leaf `schema`. The CRITICAL cohort fans out too — the human gate is
step 2, not here.

**2. Intervention pass — serial, CRITICAL-first (main loop).** After the barrier, the intervention set =
`{leaf flagged uncertain}` ∪ `{a CRITICAL a leaf routed to refuted/capability-gap}` (the invariant below).
Work it **CRITICAL-first, one at a time**: present the leaf's plain explanation + board/game-state + the
specific uncertainty; **your call assigns the terminal outcome**. Sibling-uncertainty ("is this part of a
bigger cluster?") is **not** raised here — it resolves at the join.

**3. Join — cluster + finalize route (main loop).** Every correction is now routed + resolved. Cluster by
**same target_layer + same fix**: a `general-hypothesis` / `planner-code` / `matchup-brief` pattern MAY
pool members **across decks** into ONE cross-agent proposal (the fix is deck-agnostic); a `deck-strategy`
pattern **stays within its deck**. Consume `sibling_hint`s (members sharing one `believed_archetype` → one
matchup-brief cluster; a turn bug + its inner decision bugs → one cluster). Dedup.

**4. Emit + gate.** Per cluster, a proposal or a recorded set-aside (mechanics below), then the completion
gate.

## Leaf return contract & uncertainty

Each leaf returns:

```
{ correction_id, agent, scope, target_layer, verification_contract,
  mini_spec, plain_explanation, board_state,
  outcome: proposal-routed | covered | refuted | capability-gap | uncertain,
  question,        // required when outcome == uncertain
  sibling_hint }   // suspected cross-correction cluster key, else null
```

A leaf returns **`uncertain`** (with `question`) whenever it cannot confidently reach a terminal outcome —
an ambiguous route, a shaky refute/covered claim, a correction whose validity it can't settle. It never
guesses. `plain_explanation` + `board_state` must make the item resolvable **at a glance** in the serial
pass.

**CRITICAL invariant.** A leaf that routes a **CRITICAL** to **refuted or capability-gap** surfaces it in
the intervention pass **even if certain** — the human flagged it must-fix; dropping or deferring it is
their call. Everything else — including a confidently **proposal-routed** CRITICAL — flows straight
through.

## Emit — proposal or set-aside

- **proposal-routed:** one record into `data/strategy/proposals/` (contract:
  [../update-strategy/references/strategy_proposal_contract.md](../update-strategy/references/strategy_proposal_contract.md)):
  `source: blunder-buster`, `target_layer` + `verification_contract` from routing,
  `for: general | deck:<deck> | opponent:<archetype>`, `spec` = the cluster's merged mini-specs + any
  infra-to-build, `provenance` = the correction ids (may span **multiple agents**) + the fixtured state
  (`tests/fixtures/corrections/<name>.json`), `status: open`. **One proposal per cluster, covering all
  members** — not per-correction point-fixes.
- **covered / refuted:** `python tools/train/review_correction.py <key> <disp> "<reason>"` — `key` is the
  snapshot entry's own `key` field (`<ep>-<frame>` / `<ep>-t<turn>s<seat>` / `<ep>-m<seat>`), never
  hand-built (refuted → prove with a retest first; a turn cluster's proof is `retest_span`, not `retest`).
- **capability-gap:** the four artifacts, ledgered `deferred` with the layer + todo-doc (or the
  `/matchup-genie <slug>` hand-off for an uncovered matchup miss).

## Completion gate

Re-run `python tools/train/tune.py --dry-run` (no `--agent`) — the completion gate is a **read-only
CHECK**, so pass `--dry-run` (prints the fit/proposals/`UNSATISFIED` but writes nothing; a plain re-run
here would recompile + clobber the `tuned.json` the Enumerate step already produced). For **every** agent,
every open correction is now **proposal-routed** (a queued record links its ids), **covered**, **refuted**,
or an evidenced **capability-gap** (`reviewed (excluded)`). Confirm no agent's block still lists an un-routed
`open`/`UNSATISFIED`. Produce a single terminal-outcome ledger spanning all agents — one line per
correction, its outcome + evidence (proposal id / named Hypothesis / refutation test / four artifacts),
grouped by agent. Refresh `reports/blunders.html`. Only then report finished. Then `/update-strategy`
drains the queue (authors + Verifier/gate + commits).

## Rounds & reconciliation

One append-only log; each run re-featurizes the **whole** log against the **current** Strategy. A blunder
whose proposal was applied + committed drops out next round (no longer `missing_hypothesis`).
`refuted`/`covered`/capability-gap set-asides go in `data/corrections/reviewed.json` (`tune.py` excludes
them). Loop: tag → `/blunder-buster` (route) → `/update-strategy` (apply + commit) → tag more →
`/blunder-buster` again.

## Rules

- **All agents by default** — `<deck>` narrows to one. A general/planner/matchup cluster may pool members
  across decks into one proposal; a deck-strategy cluster stays in its deck.
- **Route, don't author.** The product is a *routed proposal* (or a tested set-aside), never a committed
  `when()`/code. Routing is the value; authoring is `/update-strategy`'s.
- **One proposal per cluster**, covering all members — not per-correction point-fixes.
- **Layer routing is load-bearing:** scope turn/match → `planner-code` (prior; verify against the trace);
  lethal/planned → `planner-code`; posture-mismatch → `matchup-brief` (or `/matchup-genie`); else →
  `general-hypothesis`. Never a deck-agnostic weight for a one-archetype misplay, never a `when()` for a
  Solver/Planner-driven decision, **never a weight for a scoped blunder** (it never entered the fit).
- **CRITICAL** flows headless unless a leaf routes it to refuted/capability-gap — then it hard-stops for
  human acknowledgement in the intervention pass (the invariant above). Resolve the CRITICAL interventions
  before any other.
- **Exhaustive or not finished** — every open correction reaches a terminal outcome this session; no bare
  `deferred`, no "future run", no voluntary pauses. The only sanctioned stops are the CRITICAL
  interventions and an unresolvable blocker.
- **If you change how tuning/routing works, update `docs/tuning/methodology.md`** in the same change.
