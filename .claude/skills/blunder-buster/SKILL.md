---
name: blunder-buster
description: Bust a round of blunder corrections into verified Strategy improvements — exhaustively. Reads the correction log, clusters EVERY still-open missing_hypothesis blunder, authors a general when() trigger per cluster (building any missing Context/tag/enum infra in-session when a rule needs it), gates each with the deterministic Verifier, and presents diffs to commit. Every open correction is resolved in-session to fixed / covered / refuted — nothing is punted to a future run or "deferred". Corrections whose rationale carries the uppercase CRITICAL marker are surfaced first and resolved one at a time, blocking the rest of the run until each reaches a terminal outcome. Optionally fans file-and-behavior-independent clusters out to parallel worktree agents at the spawning session's effort, then a serial join union-verifies the merged result so rules don't step on each other. Refreshes the reports/blunders.html trend dashboard at the round boundaries. Invoke as /blunder-buster [corrections.jsonl] (defaults to data/corrections/corrections.jsonl). Use after a round of manual blunder tagging (ADR-0018).
---

# blunder-buster — corrections → verified Strategy improvements

Convert a **round** of blunder Corrections into committed agent improvements. The **Verifier** is
the accuracy gate; the human commits. Never write executable `when()` code into a Strategy without
the Verifier passing **and** human review. See `docs/blunder-tuner.md`, ADR-0017, ADR-0018.

**One run resolves the WHOLE open set.** You walk through, consider, test, and act on **every**
still-open correction in this session — start to finish. You do **not** stop after one cluster, and
you do **not** punt anything to a "future run." See the completion mandate below.

## Exhaustive completion mandate (read this first)

A `/blunder-buster` run is **finished only when the open set is empty** — when every still-open
correction has reached exactly one **terminal outcome**, with evidence:

- **fixed** — a verified `when()` Hypothesis now fires it (Verifier `passed` + retest `fixed`), diff placed.
- **covered** — an existing Hypothesis already handles it; you **name** that Hypothesis, confirmed
  against the **real Pilot `decide()`** (not the W-route).
- **refuted** — a bad correction (forgoes a KO / high-value attack), **proven with a test**; dropped
  from the weight fit. See [[forgo-ko-corrections-are-refuted]].

"Open" = every `missing_hypothesis` proposal in `data/proposals/<deck>.json` `open[]` **plus** every
`UNSATISFIED` line `tune.py` prints. Each lands in exactly one cluster and is carried through to one
of the three outcomes above.

**There is no `deferred`, no "future run", no "leave for later".** If the *only* blocker is a missing
signal — a `Context`/`Board` field, a function tag, or an enum the `when()` would need but that
doesn't exist yet — you **build that infra in-session** (step 4b), then author the rule. "Needs infra"
is a reason to **build**, never to skip. Do **not** report blunder busting finished while any
correction is still unresolved.

> **Why no defer:** every prior round's "deferred" pile silently became permanent backlog. The
> Verifier + real Pilot make in-session resolution cheap, and a missing signal is usually one
> `Context` field. Resolve it now.

(Legacy `deferred` entries already in `data/corrections/reviewed.json` are **debt** under this
mandate: any run that re-surfaces or touches one must re-resolve it to fixed / covered / refuted.)

## CRITICAL corrections — resolve first, block the run (read this second)

A Correction is **CRITICAL** when its `rationale` carries the uppercase token `CRITICAL` (the human
writes it at tag time; the marker is **case-sensitive** — lowercase "critical" prose is *not* a
flag). It means: **this blunder must be resolved before any other work this run.**

**You do not hand-grep for it — the pipeline surfaces it.** Step 1's `tune.py` prints a
`*** N CRITICAL correction(s) flagged … FIRST (blocking) ***` banner and tags each `PROPOSE` /
`UNSATISFIED` line `[CRITICAL]` (with its rationale); `data/proposals/<deck>.json` `open[]` and
`skipped[]` entries carry `"critical": true`; and `reports/blunders.html` badges each one
`⚠ CRITICAL`. Read all three to build the cohort — a CRITICAL correction can land on **any** worklist
source (H proposal, W-route `UNSATISFIED`, or `skipped`/tactical).

**The gate (serial, blocking, per-item):**

1. **Partition the CRITICAL cohort out** of the step-1 worklist before touching anything else, and
   **list it back to the human up front** — each critical correction's id, episode/frame, and
   rationale. This is the "pause": you surface the cohort and start on it, not on the rest.
2. **Work the cohort first, one at a time.** Carry each critical correction through steps 2–10 to a
   **terminal outcome** (fixed / covered / refuted) **before starting the next critical one, and
   before *any* non-critical cluster.** No batching the cohort with normal clusters; no interleaving
   non-critical work "while you think about it."
3. **Checkpoint each.** When a critical correction reaches its outcome, **stop and present it**
   explicitly — the authored `when()` + Verifier `passed` + retest `fixed`, or the **named** covering
   Hypothesis (confirmed against the real Pilot), or the refutation test — and confirm it's resolved
   before moving on. "Pay special attention" = each critical item is its own reviewed checkpoint, not
   a line in a batch summary.
4. **A CRITICAL that would be `refuted` is a HARD STOP.** If the only sound outcome is `refuted` (it
   forgoes a KO / is dominated — [[forgo-ko-corrections-are-refuted]]), do **not** silently file it.
   Present the refutation proof and **stop for explicit human acknowledgement** before recording it:
   the human flagged this must-fix, so "your critical correction is actually wrong" is *their* call,
   not the skill's. (A non-critical correction still auto-records `refuted` per step 10.)

**Parallel mode:** the CRITICAL cohort **never fans out.** Resolve it **serially in Phase 1, ahead of
the parallel batch** — Phase 1 setup → drive every CRITICAL correction to terminal (steps 4–11 each,
serial) → only then spawn the Phase-2 fan-out over the *remaining* SOFT clusters. A blocking cohort
can't be scheduled into concurrent authoring.

This does **not** weaken the exhaustive-completion mandate — the run still ends only when the **whole**
open set is empty (step 11). CRITICAL changes **order + gating**: critical first, blocking, one
reviewed checkpoint each.

## Rounds & reconciliation

There is **one append-only log**; you don't manage per-round files. Each run re-featurizes the
**whole** log against the **current** Strategy, so reconciliation is automatic:

- A blunder you addressed last round is no longer `missing_hypothesis` — the Hypothesis you
  committed now fires on it, so it drops out (becomes weight-tunable or already satisfied).
- Only **still-uncovered** blunders surface as new `missing_hypothesis` clusters.

**The reviewed ledger — set-asides that stay set aside.** Auto-reconciliation only drops a blunder
once a rule *satisfies* it. A `refuted` or `covered` correction you resolved by judgement (not by a
firing rule) would otherwise resurface every run, so record it in `data/corrections/reviewed.json`
(step 10); `tune.py` then excludes it from `open[]` / `UNSATISFIED` and lists it under
`reviewed (excluded)`. **`refuted` and `covered` are the only set-aside outcomes** — both are
terminal resolutions reached by **testing**, not punts.

So the loop is: tag corrections → `/blunder-buster` → **resolve every open correction** (author +
verify + **commit**, or test + **record refuted/covered**) → tag more (appended to the same log) →
`/blunder-buster` again (prior clusters auto-drop; reviewed ones stay excluded; only the new patterns
appear). **Commit authored Hypotheses before the next round** so re-featurization sees them.

## Progress narration (required checkpoints)

Every run — serial or parallel — prints these checkpoints as they happen (caveman-lite, per user
style; skip only the ones that don't apply to serial mode):

1. **Start.** First line of the run: `working` (or `working on <deck>` if deck name known).
2. **After clustering** (end of step 1). Print the category breakdown — one line per category with
   its blunder count, e.g. `categories: bad-target x3, sequencing_error x2, missed_evolution x1`.
3. **Before fan-out** (parallel mode Phase 2 start only). State that agents spawn now, one per SOFT
   cluster/category, working independently: e.g. `spawning N agents, one per category, working
   independent`.
4. **Per-agent finish** (parallel mode, as each Phase-2 agent returns). Name the category/cluster
   that just finished: e.g. `bad-target done` / `sequencing_error done`.
5. **All done** (step 11 completion gate passes, open set empty). One final line, e.g. `all done —
   open set empty`.

## Steps

> Steps 2–10 run **per cluster**. After step 1 builds the full cluster worklist, loop 2–10 over
> **every** cluster on it — you are not done until all are resolved (step 11).

1. **Enumerate & cluster EVERY open proposal.** `python tools/train/tune.py --agent <deck>
   [--store <path>]`, then read the durable snapshot it writes: **`data/proposals/<deck>.json`**
   (`open[]` = the `missing_hypothesis` proposals, each with category/episode/frame/`agent_build`;
   `skipped[]` = tactical/no-obs). Group **all** `open` proposals by category + similar rationale into
   patterns (e.g. the three `bad-target` "snipe the highest threat" corrections form ONE pattern).
   Each pattern's ids are a **cluster**. Build the **full cluster worklist now** — every open proposal
   lands in exactly one cluster (a singleton if it shares no pattern); **none is left off the list**.
   Then **partition out the CRITICAL cohort** — any member whose rationale carries the uppercase
   `CRITICAL` token (`tune.py` banners it; `open[]`/`skipped[]` carry `"critical": true`). These are
   worked first and **block** the rest — see *CRITICAL corrections* above.
   (The same `tune.py` run also (re)writes `src/agents/<deck>/tuned.json` — the deterministic Tier-0
   weight deltas; commit it alongside the authored Hypothesis.) **Refresh the trend dashboard to
   eyeball the incoming surface:** `python tools/train/blunder_report.py` rebuilds
   `reports/blunders.html` (local, gitignored) — a by-category / submission / build / **resolution** /
   **avg-blunders-per-game** view that badges each blunder fixed / covered / refuted / deferred / open
   / skipped (from the reviewed ledger + the proposals snapshot you just regenerated).
   - **Also mine the `UNSATISFIED` lines** `tune.py` prints: these are *W-route* corrections whose
     `correct ≻ chosen` the weight fit could **not** honour (a conflict between corrections, or a gap
     no existing Hypothesis discriminates). They are prime **H** candidates — treat them like `open`
     proposals and cluster them too. A `tuned.json` of `{}` is normal and honest: it means the round's
     leverage is entirely in new rules, not reweighting (the fit ships weights only when they satisfy
     strictly more corrections than the seeds; lower `--reg` only if you *want* clean corrections to
     move weights more aggressively — the ladder is the real gate).

2. **See how the agent actually decided** (the live trace, ADR-0019). Each Correction may embed
   `live_trace` — the `@T` Decision Telemetry the **shipped** agent emitted at that exact decision
   (`opts[].score / tac / fired:[[hyp_id, weight]]`, `chosen`, `margin`, and **`lethal`**). Read it per
   cluster member to ground authoring in the agent's *real* reasoning: which hypotheses fired on the
   chosen vs the correct option, and by what margin. (If `live_trace` is null, run
   `python tools/train/backfill_obs.py` once the game's `episode-<id>-agent-<seat>-logs.json` is
   collected, or rely on the obs re-derivation.)

   **Read `live_trace.lethal` FIRST — it can pre-empt the whole analysis (ADR-0030).** It is the
   **Lethal Solver**'s verdict: `null` when no guaranteed this-turn win was locked, else
   `{step, kind, why}` (`kind` ∈ `direct` / `unlock` / `evolve`). The Solver runs **before** Hypothesis
   scoring and **short-circuits** it — `pilot.py` `_evaluate` returns early on a lock, so on a lethal
   decision `opts[].fired` / `score` did **not** drive the choice (don't be misled by them). A lethal
   blunder is therefore **NOT weight-tunable, and no `when()` Hypothesis can fix it** — the Solver
   overrides scoring; the fix lives in the Solver (`src/common/strategy/lethal.py`). Two shapes:
   - **`lethal: null` but a win existed** (typically `missed_win` / `missed_ko`) → `find_lethal_line`
     failed to detect it: extend the closed-form generator (a missing win-shape / unlock kind) or its
     soundness gate.
   - **`lethal` non-null but the human rejects the pick** → the Solver over-fired (a false / wrong
     lock): tighten `_attack_wins` / the win-gate.
   Resolve it in-session by editing the Solver **plus a focused unit test in `tests/test_lethal.py`** (a
   step-4b-style infra fix, **not** a Hypothesis). The **retest** (step 6, which re-runs `explain()` and
   now carries `lethal`) is the before/after proof; suite-green (step 7) is the guard. The Hypothesis
   **Verifier (step 5) does not gate a Solver-code fix** — skip it for these clusters; the retest + suite
   are the gate. Terminal outcome is still `fixed` (Solver now handles it, with its test) / `covered`
   (the Solver already handles it — name the branch, confirm with the real Pilot) / `refuted` (the
   "missed win" is a KO-forgoing mislabel — [[forgo-ko-corrections-are-refuted]]).

3. **Read the feature catalog** (author against the LIVE source, never memory):
   - `src/common/pilot.py` — the `Context` / `Board` fields a `when(ctx)` may read.
   - `src/cg/api.py` — `SelectContext` / `OptionType` / `AreaType` / `EnergyType` enums.
   - `src/common/cards.py` + `card_functions.json` — the function **tags**.
   - `src/common/strategy/baseline/baseline_*.py` (deck-agnostic rules, clustered by decision-context;
     ADR-0025) + `src/agents/<deck>/strategy.py` — existing Hypotheses as **style examples** (mirror
     their shape).
   - `src/common/strategy/lethal.py` — the **Lethal Solver** (ADR-0030). Where a lethal-layer blunder
     (`live_trace.lethal` set, or `null` on a missed win — step 2) is fixed: `find_lethal_line` (win
     detection + unlock kinds) and `_attack_wins` (soundness). The Solver short-circuits scoring, so
     these are **code fixes here + a `tests/test_lethal.py` test**, never a `when()` Hypothesis.

4. **Author the candidate `when()`** from the cluster's RATIONALES (the authoring spec):
   - Prefer **universal features** (`tags`, `roles`, `board`, `stat`) over hard-coded `card_id`s.
   - Pure + total predicate; seed `weight` in-band (`docs/weights.md`); `status="assumed"`.

4b. **Missing signal? Build the infra in-session — never defer.** If the `when()` you need must read
   a signal that doesn't exist yet (a `Context`/`Board` field, a function tag, an enum/select-context
   exposure), **add it now** — this is the *only* place a "needs infra" correction goes, and it goes
   *forward*, not into the ledger:
   - Pick the layer: a derived board/decision signal → `Context`/`Board` in `src/common/pilot.py`; a
     card-behavioral property → a tag in `card_functions.json` (+ wiring in `src/common/cards.py`);
     engine vocabulary → `src/cg/api.py`.
   - Compute it from sources already available to the Pilot; keep it **pure + total**; mirror the shape
     of an existing signal (e.g. `target_energy`). Verify every card/rule fact **at source**
     (`docs/rules.md`, `docs/rulebook.txt`, `data/EN_Card_Data.csv`), never from memory.
   - Add a **focused unit test** for the new signal under `tests/`, then author the `when()` that reads
     it and continue to step 5. Worked example of the kind of signal this unblocks: the snipe
     **"evolves-into-attacker"** lookahead ([[snipe-threat-two-signals]], frame 75) — previously
     deferred for lack of this exact `Context` signal; under this skill you **build and ship it**.
   - If the signal is genuinely large (a multi-file subsystem), still **resolve the correction this
     session**: build the **smallest correct version** the rule actually needs. That is still building,
     not punting — the correction must reach a terminal outcome before the run ends.

5. **Verify** — the gate; iterate until it passes:
   - Build the deck's Pilot (mirror `tools/train/tune.py:_build_pilot`) wrapped as
     `pilot_with(extra) -> Pilot(..., hypotheses=base + extra, ...)`.
   - Load the cluster's Corrections; call `verify(candidate, corrections, pilot_with, seeds,
     cluster)` from `train.tuner.verify`. Require `result.passed` (cluster satisfied + empty
     `regressed`). Too narrow → cluster unsatisfied (broaden); too broad → `regressed` (tighten).

6. **Retest — "see the log after the fix"** (ADR-0019, closes the loop). For each cluster member,
   `retest(correction, pilot_with([candidate]))` from `train.tuner.retest` re-derives the decision
   in the **same `@T` format** as the live log and diffs it against the embedded `live_trace`:
   show `chosen_before → chosen_after`, `margin_before → margin_after`, and require `fixed` (the
   `correct` option is now chosen). This is the before/after proof the blunder is addressed.

7. **Suite-green.** `python -m pytest tests/ -q` — must not break Playability / existing behavior
   (and must include any new signal's test from step 4b).

8. **Place + present a diff** (the human commits):
   - universal trigger → append into the matching cluster's `HYPOTHESES` in
     `src/common/strategy/baseline/baseline_<decision-context>.py` (energy / snipe / promote / retreat /
     bench / tool / evolution / heal / opening / sequencing / disruption; ADR-0025) — `baseline/__init__`
     + `general_strategy.py` pick it up automatically (a brand-new cluster also adds one line to
     `baseline/__init__.py`). A rule that needs one card archetype's closed-form Pilot code goes in its
     `src/common/strategy/doctrines/doctrine_*.py` instead.
   - deck-specific (`roles`/`lines`/`card_id`s) → `src/agents/<deck>/strategy.py`
   - Set `status="testing"` once the Verifier passed; mark `confirmed`/`refuted` later from ladder A/B.

9. **Write the run report** (the human-readable record + showcase). Step 1's `tune.py` already wrote
   `docs/tuning/runs/<deck>_<timestamp>.md` (what was tuned/why/how much, proposals, unsatisfied) —
   it prints `report -> <path>`. **Append** to that same file an `## Authored this round` section: for
   each Hypothesis you committed, a bullet with its id, the cluster it fixes, the rationale, the seed
   weight + band, and the **retest before/after** from step 6 (`chosen_before → after`,
   `margin_before → after`, `fixed`). Also record any **new infra built** in step 4b (the signal, its
   layer, its test). This is the per-run learning/progress artifact; keep it succinct and explain
   *why*, not just *what*. The math itself lives once in `docs/tuning/methodology.md` — link it, don't
   re-explain it.

10. **Record the set-asides** (so they never resurface). For every `open` proposal / `UNSATISFIED`
    correction you resolved **without** authoring a firing rule, record its terminal disposition —
    `python tools/train/review_correction.py <episode>-<frame> <disposition> "<reason>"`:
    - `refuted` — a bad correction (e.g. it forgoes a **KO** / a high-value attack; `tactical ≈ 1000`).
      **Prove it first** (retest shows the agent's pick is the KO), then record. Also dropped from the
      weight fit so the bad label stops pressuring weights. (See [[forgo-ko-corrections-are-refuted]].)
    - `covered` — already handled by an existing Hypothesis; **name it**, and confirm with the real
      Pilot `decide()` that it actually fires (not just the W-route).
    There is **no `deferred`.** A correction blocked only by a missing signal is **not** set aside —
    you built the infra in step 4b and authored the rule. Next `tune.py` run excludes the recorded
    set-asides (shown under `reviewed (excluded)`), so the next round only surfaces genuinely new work.

11. **Completion gate — prove the open set is empty.** Re-run `python tools/train/tune.py
    --agent <deck>` and confirm that **no unresolved correction remains**: every line is either one you
    committed a fix for (drops on this reconciliation) or one recorded `refuted`/`covered` in the
    ledger (`reviewed (excluded)`). Produce a **terminal-outcome ledger** — one line per open
    correction, its outcome (fixed / covered / refuted) and the evidence (Verifier+retest id / named
    Hypothesis / refutation test). **Only when every correction has an outcome may you report blunder
    busting finished.** If any correction is still unresolved, you are **not** done — return to step 2
    for it. Do not say "the rest are for a future run."
    - **Refresh the trend dashboard.** `python tools/train/blunder_report.py` rebuilds
      `reports/blunders.html` (local, gitignored) so it reflects this round's outcomes: each blunder
      is badged with its terminal disposition — **fixed** (a committed rule satisfies it; reconciliation
      dropped it from `open[]`) / **covered** / **refuted** / **deferred** (reviewed ledger) / **open**
      / **skipped** — and the header splits resolved vs open. `fixed` is derived from the proposals
      snapshot, so the dashboard is accurate to the **last `tune.py` run** (step 1 / this gate just
      refreshed it). Parallel mode reaches this step too (Phase 3 runs steps 8–11).

## Parallel mode (fan-out) — same gates, different schedule

Parallel mode changes **only how clusters are scheduled** — every gate is unchanged (Verifier
non-negotiable; no `deferred` / build-infra-in-session per step 4b; exhaustive completion per step 11;
human commits). It busts a multi-cluster round faster by authoring **independent** clusters
concurrently, then proving at a serial join that they didn't step on each other. **Default is serial**
(steps 1→11). Fan out only when **both** hold: (a) the session is orchestration-capable — parallel
mode uses the **Workflow tool**, which needs the multi-agent opt-in (ultracode on, or the user asked
for it); and (b) **≥2 clusters classify SOFT** (below). One cluster, an all-HARD round, or no opt-in →
run serial.

### Eligibility — SOFT vs HARD (file-disjoint AND behavior-disjoint)

A cluster is **parallel-eligible (SOFT)** only if its *entire* planned write-set is **append-only into
a shared list/map**:

| Write-set | SOFT (parallel-safe) | HARD (serialize) |
|---|---|---|
| Universal Hypothesis | append into the matching `strategy/baseline/baseline_<context>.py` `HYPOTHESES` (ADR-0025; different contexts → different files, so even more disjoint) — order-independent (`pilot.py` sums all fired weights) | — |
| Deck Hypothesis | append into deck `strategy.py` `HYPOTHESES` (`:31-58`) | edits the same deck `ROLES` dict (`:20-29`) / `STRATEGY` ctor (`:60-68`) |
| Function tag | tag a card **no other concurrent cluster touches** (`card_functions.json`) | two clusters tag the **same** card id |
| Context/Board signal (step 4b) | — | **always HARD** — co-edits the dataclass body **and** its single `_context`/`_board` return (`pilot.py:92-120`/`:301-309`, `:62-89`/`:371-390`) |
| Enum / mirror constant | — | two clusters edit the same mirror block (`strategy/context.py`, `pilot.py:16-34`) |

**Rule of thumb:** append-to-a-list/map = parallel-safe; edit-a-shared-structured-region = serialize.
**Every step-4b new signal is HARD by construction.** File-disjoint ≠ behavior-disjoint (two new
Hypotheses can both fire on one option and fight in the summed score), so also apply a **conservative
static pre-filter**: if two SOFT clusters target the **same `SelectContext` + `OptionType` + an
overlapping card set**, route the later one to the serial tail. Residual behavior-overlap *is* allowed
into the parallel batch — the join's union-verify is the net that catches it.

### Phase 1 — serial setup & classify (steps 1–3, once)

Run `tune.py --agent <deck>` **exactly once** — it is the **single shared writer** of `tuned.json` /
`data/proposals/<deck>.json` / the run report; never run it inside a fan-out worktree (it desyncs the
durable snapshot). Cluster **every** open correction into the full worklist (step 1), read `live_trace`
+ the feature catalog (steps 2–3). Then **classify each cluster SOFT/HARD** and partition into a
**parallel batch** (pairwise-disjoint SOFT clusters) + a **serial HARD tail**. **Record the full
worklist of cluster ids** — the join reconciles against *this*, not against whatever agents return.

### Phase 2 — parallel authoring (steps 4–7 per cluster, isolated)

Spawn one **authoring agent per SOFT cluster** via the **Workflow tool**, each with
**`isolation: 'worktree'`** (per-agent edits + pytest never collide on disk). **Same effort:** with the
Workflow tool, **omit `opts.effort` and `opts.model`** → the agent inherits this session's effort+model
— that *is* the "same effort as the spawner" guarantee. *(If you ever fall back to `spawn_task`/Task
tooling, effort is **not** inherited by omission — pass parent effort+model explicitly, have the agent
echo them back in its result, and reject/re-spawn any downgraded run.)*

Each authoring agent runs steps 4→5→6→7 to completion **in its worktree**: author the `when()` (4),
Verifier `passed` against `pilot_with([candidate])` (5), retest each member `fixed` (6),
`pytest tests/ -q` green incl. any new test (7). It does **not** commit/merge — it **returns structured
data**: cluster ids, the authored Hypothesis **source text** + target file/region, `VerifyResult`,
per-member retest before/after, suite status, and its echoed effort/model. **If it discovers it needs
step-4b infra**, that reclassifies the cluster **HARD** — it returns `needs-serialization` instead of
editing shared `pilot.py`, and the cluster drops to the serial tail. Read-only **adjudication** of
`covered`/`refuted` (step 10) may also fan out — no worktree (no writes) but **still at full effort**
(covered/refuted are terminal judgements, not cheap).

### Phase 3 — serial join, union-verify & completion gate (steps 7–11 over the union)

1. **Run the HARD tail** now, one cluster at a time under its file/region lock (steps 4–7 each).
2. **Structural re-apply, not git merge.** Take each agent's returned Hypothesis source text and
   **insert it programmatically** before the target list's closing bracket; do **not** rely on git
   auto-merge (every parallel pair textually conflicts on the `]` line). Immediately run an
   **`ast.parse` / `py_compile` gate** on each touched file — a malformed concatenation fails **here**,
   naming the offending cluster, before any verify.
3. **Collect `all_authored`.** Gather each agent's authored Hypothesis from its structured result
   into one `all_authored` list — it feeds both the structural re-apply (above) and `union_verify`
   (below). You do **not** hand-build the union seeds: `union_verify` derives them and **raises on
   duplicate authored ids** (ids are `category-episode-frame`, so two clusters sharing episode+frame
   collide and a dict-merge would silently drop one — a completion-mandate breach). If it raises,
   namespace the colliding id before proceeding.
4. **Union-verify — the interference detector.** Call
   **`union_verify(all_authored, corrections, pilot_with, seeds, clusters)`** (`train.tuner.verify`) —
   the join-only gate that encodes the correct wiring so a hand-rolled join can't reintroduce the two
   classic bugs. It injects **every** authored Hypothesis **once** against a **seeds-only** baseline
   and returns `regressed` across the whole corpus + per-cluster `clusters_satisfied`. It does **not**
   route the union through `verify()`'s single-`candidate` path (that double-counts — `verify.py:33`
   layers `[candidate]` on top and `pilot.py:219-221` sums fired weights with no dedupe), and it
   **raises** if `pilot_with([])` is not seeds-only (a contaminated baseline makes `regressed` a no-op,
   `verify.py:32,36`) or if two clusters' authored ids collide. **`corrections` must include the
   previously-`covered` ones**, not just parallel-batch members — a new rule can steal a covered
   Correction's option. **Require** `result.passed` (every cluster satisfied in the union **and**
   `result.regressed` empty). A non-empty `regressed` names the exact Correction one agent's rule broke
   for another → reconcile (below).
5. **Full suite + union-retest.** Re-run `pytest tests/ -q` once on the merged tree — this catches
   over-firing on **non-correction** Playability states the corpus-only verify can't see; it is
   **load-bearing, not optional**. Then `retest(member, pilot_with(all_authored))` for every cluster
   member **and every previously-`covered` correction** (a new union Hypothesis can steal the option a
   `covered` correction relied on; `refuted` KO-dominated ones are immune — `KO_SCORE` swamps any
   band-≤100 weight). All must still be `fixed`/satisfied.
6. **Steps 8–11 over the union.** Place each diff (8), append the run report incl. any new infra (9),
   record `refuted`/`covered` set-asides (10), and run the **step-11 completion gate** — re-run
   `tune.py`, prove the open set empty. **Reconcile against the Phase-1 full worklist:** every cluster
   id maps to exactly one terminal outcome — `fixed` (diff present **and** union-verified) / `covered`
   / `refuted` / `re-queued-serial`. A missing / null / timed-out / `needs-serialization` result is
   **re-queued to the serial tail, never dropped** — do not let "all *reported* clusters passed"
   vacuously pass over a dead agent. Human commits.

### Loop-safe reconciliation (when the join regresses)

If union-verify reports `regressed` (or a union-retest flips a member, or the suite breaks on a
union-only over-fire), the two clusters are proven **behavior-dependent** despite being file-disjoint.
**Merge them into one cluster**, hand to a **single serial** authoring agent that makes the triggers
mutually exclusive (tighten one `when()` to exclude the overlap, or fold both under one broader
Hypothesis), re-run steps 5–7, and **re-enter the FULL join review** (never a partial check).
**Termination:** merges are **one-way** (clusters only combine, never re-split), so each pass strictly
decreases the cluster count over a fixed finite open set — worst case collapses to one serial cluster,
i.e. today's guaranteed-terminating path. The run is finished only when one **full** join review passes
clean **and** step 11 shows the open set empty — the same exhaustive-completion mandate, reached by a
fan-out-then-converge schedule.

## Rules
- **CRITICAL first.** A correction whose rationale carries the uppercase `CRITICAL` token is resolved
  before any other cluster, **one at a time**, each to a terminal outcome with a reviewed checkpoint;
  a CRITICAL that would be `refuted` **hard-stops for human acknowledgement** (see *CRITICAL
  corrections*). The cohort never fans out — it runs serially ahead of the parallel batch.
- One Hypothesis per cluster, verified against **all** its members — not per-correction point-fixes.
- **Parallel mode is scheduling only.** Fanning clusters out (see *Parallel mode*) never weakens a
  gate: the Verifier still gates every cluster, the join's **union-verify + full `pytest` + step-11**
  must pass over the **merged** tree, and a dead/failed agent **re-queues serial** — never a silently
  dropped correction.
- The Verifier is non-negotiable: **no commit without `passed`**.
- **Exhaustive or not finished.** Every open correction must reach a terminal outcome
  (fixed / covered / refuted) **this session**; the run is finished only when the open set is empty
  (step 11). No `deferred`, no "future run", no leaving a correction unanalyzed.
- **Don't invent `ctx` features in a `when()`** — read only what `Context` / `Board` actually expose.
  If a rule genuinely needs a signal that isn't there, **add it to the proper layer first** (step 4b,
  with a test) — never fabricate a field the Pilot doesn't compute.
- **If you change how tuning works, update the explainer.** Any change to the method itself — the fit
  objective/optimiser, attribution (W vs H), the regularisation/`reg`, the pocket, the adoption gate,
  the verifier/retest — must be reflected in `docs/tuning/methodology.md` (the graded, educational
  write-up) in the same change. Keep the math there in sync with `tools/train/tuner/`.
