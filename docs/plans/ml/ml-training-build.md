# ML Training Pipeline — Build Plan (living playbook)

**Governing docs:** [ADR-0053](../adr/0053-ml-training-pipeline-build-plan.md) (decisions —
read first) · [research report](../research/ml-training-system.md) (evidence base).
This doc is the operational plan: per-session scopes, gate checklists, and the status ledger.

**How a fresh session uses this doc:** read ADR-0053 + this file; check the status ledger;
take the next unblocked session (respect the gates); work in a worktree owning only that
track's files; at session end update the ledger below, tick deliverables, and record gotchas
in the session-notes column and auto-memory. Parallel-phase sessions (P2a∥P2b, P3a∥P3b) run
as separate concurrent worktree sessions.

## Status ledger

| Session | WP | Scope | Status | Notes |
|---------|----|-------|--------|-------|
| S1 | WP0 | Corpus v2 + contract freeze + background gen | ☑ built 2026-07-13 | `tools/sim/corpus.py`; contracts frozen → [ml-training-contracts.md](ml-training-contracts.md); C2 `provenance` field built; ~0.028 GB-comp/game (30k games ≈ 0.84 GB) |
| S2a | WP1 | Value net v2 | ☐ blocked on S1 | design LOCKED → [ml-training-design-s2a.md](ml-training-design-s2a.md) |
| S2b | WP2 | Eval harness | ☐ blocked on S1 | |
| — | G1 | Value-net gate | ☐ | measure per s2a design D3/D4 |
| S3a | WP3 | Blunder labeler | ☐ blocked on G1 | design LOCKED → [ml-training-design-s3a.md](ml-training-design-s3a.md); detector core in s3b D1/D2; detector code lives in `tools/train/label/` |
| S3b-1 | WP4 | Expert-iteration plumbing | ☐ blocked on G1 | design LOCKED → [ml-training-design-s3b.md](ml-training-design-s3b.md); outer-loop re-detection invokes the S3a labeler CLI — land S3a first (fit-extension plumbing may parallelize) |
| S3b-2 | WP4 | Matchup tables + integration | ☐ blocked on S3b-1 | design LOCKED → same doc, D3/D4 |
| — | G2 | Adoption gate | ☐ | |
| S4 | WP6 | Rotation-loop glue + orchestration | ☐ blocked on G2 | |
| — | WP5 | League/exploiter | ☐ deferred (unlock: WP4 checkpoints shipped) | |

## Dependency diamond

```
WP0 corpus v2 ──┬─→ WP1 value net ──[G1]──┬─→ WP3 blunder labeler → corrections flow (exists)
 (bg from S1)   │                         └─→ WP4 expert-iteration ──[G2]─→ shipped weights
                └─→ WP2 eval harness ─────────(G2 measured on WP2)─────↑
```

Plumbing parallelizes; **integration waits for gates** — WP3 thresholds and WP4 targets are
meaningless against an unvalidated net.

---

## S1 — WP0: corpus v2 + contract freeze (serial, 1 session) — ☑ BUILT 2026-07-13

**Built:** `tools/sim/corpus.py` (matrix + seat-balanced + `MatchRecorder` capture, gzip films,
per-run manifest, crash-safe resume, `--max-games`/`--max-gb` caps, `prune_runs`); contracts
frozen in [ml-training-contracts.md](ml-training-contracts.md); C2 `provenance` field built on
`Correction` (behavior-neutral, default `"human"`); tests `tests/sim/test_corpus.py` +
`tests/blunder/test_blunder_correction.py::test_provenance_*`. No `filters.yml` change needed —
`tools/sim/**` + `tests/sim/**` already map to the `sim` area. Measured ~0.028 GB-compressed per
game (30k games ≈ 0.84 GB; the game cap binds first, not the byte cap).

**Deviations from the scope below (recorded):**
- **Meta-deck opponents deferred.** The matrix is our-agents × our-agents (3×3, cross + mirror)
  today. `data/meta/decks/` is gitignored/absent AND no generic driver bundle exists to *play* a
  bare decklist, so meta opponents can't be driven yet. The runner accepts an `--opponents` slot
  (manifest `opponents: []`) so they drop in with no rewrite once a driver exists. v1 archetype
  variety = our 3 decks, which is a valid S2a posterior-block start (design caps vocab ~16, folds
  the rest into unknown-mass); extend the corpus later with `--resume`.
- **Serial, not `--jobs` fan-out.** Per-pairing persistent servers (gauntlet lifecycle) amortize
  import; a 30k run is a few hours single-threaded and keeps the machine usable. `--jobs` is a
  later optimization if wall-clock bites.
- **Rotation → caps + `prune_runs`.** A corpus is one growing set, not a time series; the byte cap
  bounds a run and `prune_runs --prune-to-gb` reclaims oldest *complete* runs. Same disk-safety
  intent as the scoped "rotation."

**S2a consumes it:** `python tools/train/value/train.py <agent> --replays data/replays/corpus`
(`load_replay` reads the `.json.gz` films transparently; archetype per seat is in each film's
`info.TeamNames`).

<details><summary>Original scope (for reference)</summary>

**Scope:**
1. **Corpus runner** (new, `tools/sim/` — e.g. `corpus.py`): round-robin matchup matrix over
   all working-tree agents (`src/agents/*/main.py`) × (same agents + exported meta decks in
   `data/meta/decks/` driven by the generic Pilot). Combines `battle.py`'s worker fan-out
   (`_battle_worker.py`, `_agent_server.py`, seat balancing per ADR-0021) with
   `MatchRecorder` replay capture (`tools/sim/record.py`) — today parallelism and recording
   live in different tools (`battle.py` vs `selfplay.py`/`gauntlet.py`).
2. **Manifest + rotation:** per-run JSON manifest (pairs, game counts, git rev, agent
   versions, schema version) under `data/replays/` (gitignored); disk-cap + rotation policy.
3. **Background entrypoint:** resumable, capped, restartable (precedent:
   `tools/meta_tracker/run_daily.py` cursor pattern). Kick it off at session end — corpus
   accumulates while P2 builds.
4. **Freeze the three contracts** (write `docs/plans/ml-training-contracts.md`):
   - **C1 — feature/schema versioning:** corpus manifest schema version + `value_model.json`
     meta version; name-list drift → null model already enforces runtime safety.
   - **C2 — auto-Correction provenance:** how machine-flagged Corrections are distinguished
     from human-tagged (decide: new `source` value vs. attribution field). Must not break
     `tune.py`'s `source=="own"` filter or the `reviewed.json` flow silently — pick the
     encoding deliberately.
   - **C3 — eval report format:** JSON the WP2 harness emits and G2 consumes (per-matchup ×
     seat W/L, paired deltas + CIs, stratum breakdown, checkpoint-pool results).

**Exit / deliverables:** corpus runner + manifest + tests (`tests/sim/`), `.github/filters.yml`
entry, contracts doc, background generation running, ledger updated.

</details>

## S2a — WP1: value net v2 (parallel with S2b)

**Owns:** `tools/train/value/`, `src/common/value/`, `requirements-train.txt` (new).

> **Design is LOCKED in [ml-training-design-s2a.md](ml-training-design-s2a.md)** (Fable design
> grill, 2026-07-13): matchup encoding = replayed-Read posterior block; capacity =
> measure-then-ship-MLP with distill fallback; episode-level holdout split. Execute it — the
> scope below is the summary, the design doc is the specification.

**Scope:**
1. **Features:** grow past the 17-name vector (`src/common/value/features.py`) and add
   matchup conditioning. Train-time opponent identity = true deck (self-play knows it);
   runtime = the Read's belief (γ-weighted archetype), so choose an encoding that degrades
   with Read uncertainty (candidates: archetype one-hots × γ, favorability-style scalars).
   Keep the fail-open property.
2. **Trainer v2** (offline numpy/torch per ADR-0053 D5): logistic baseline first on the new
   corpus, then the 2×64 MLP. Label = terminal win/loss, γ=1.0. Export weights to
   `value_model.json` (versioned format); runtime forward pass stays hand-rolled stdlib in
   `src/common/value/model.py`.
3. **Runtime cost check:** the net is evaluated at planner leaves. Measure per-call cost of
   the pure-Python MLP forward; if it materially slows the planner, distill to
   logistic+interactions or cap leaf evaluations. Record the measurement.
4. **Validation suite:** extend `tools/train/value/sanity.py` + holdout tooling for G1.

**Exit:** G1 checklist below, run and recorded.

### G1 — value-net gate (checklist)

- ☐ Held-out logloss/AUC beats the committed seed model and the 0.69 entropy floor.
- ☐ Calibration curve acceptable (predicted P(win) tracks empirical winrate by bucket).
- ☐ Cross-deck generalization: a whole held-out deck pair scores comparably.
- ☐ Sanity probes: P(win) monotone in prize diff; captured known-lethal states → high P;
  symmetric mirror openings → ~0.5.
- ☐ Runtime cost measured and within planner budget.

Fail → iterate WP1. WP3/WP4 **integration** stays blocked; their plumbing may proceed.

## S2b — WP2: eval harness (parallel with S2a)

**Owns:** `tools/sim/eval*` (new files only).

**Scope:**
1. **Matrix runner:** contestant set = working-tree agents + Build-Ledger build zips
   (`battle.py` already resolves both); matchup × seat balanced; paired-delta stats reusing
   `gauntlet_ab.py`/`paired_ab.py`; emits the C3 report.
2. **Checkpoint opponent pool:** frozen past builds from the Build Ledger as standing
   opponents (the deferred-WP5 stand-in; catches regressions and non-transitivity drift).
3. **Duplicate-deal spike (timeboxed, ~half a session):** the engine has NO deal seed. Try
   fork-replay: capture the full opening state from a self-play game (both sides known),
   re-enter it via `search_begin(obs, your_deck, your_prize, opponent_deck, opponent_prize,
   opponent_hand, opponent_active, manual_coin=...)` and drive repeated playouts from the
   identical deal. If it holds → duplicate-deal eval + skill-sensitivity stratification
   (replay same deal under both contestants). If not → document and fall back to paired
   high-N; stratify by a proxy (e.g. seed-model value swing across the game).
4. **AIVAT plug-in point:** stub interface taking per-decision value estimates over logs;
   fills in after WP1 lands. Not required for the harness to be usable.

**Exit:** end-to-end matrix eval of current agents producing a C3 report; spike verdict
recorded here.

## S3a — WP3: blunder labeler (parallel with S3b, after G1)

**Owns:** new labeler package under `tools/train/` (e.g. `tools/train/label/`).

> **Design is LOCKED in [ml-training-design-s3a.md](ml-training-design-s3a.md)** (Fable design
> grill, 2026-07-19): detector core per s3b D1/D2, detector code homed in `tools/train/label/`
> (S3b consumes via store/CLI/thresholds, never an import); triage Φ-deltas rank but never emit;
> θ set by a stratified precision review (≥ 0.80 gate, committed `thresholds.json`); machine
> Corrections go direct-to-fit via gitignored `data/corrections/machine/` with caps + new
> `value_delta` category; shared per-decision-P(win) reader (`vread`) also feeds S2b's AIVAT
> stub; played-well-lost = report view over lost games. Execute it — the scope below is the
> summary, the design doc is the specification.

**Scope:**
1. **v1 — consecutive-state deltas (no simulation):** re-derive V(s) per own MAIN decision
   offline (extraction machinery: `tools/train/value/extract.py` / `pilot._board`); flag
   drops ≥ threshold between consecutive own decisions (Suphx Φ-delta shape).
2. **v2 — counterfactual alternatives:** at flagged decisions, fork via `search_begin`
   (self-play logs know hidden state; `backfill_seed.py` content-join recovers fork strings),
   evaluate top-k alternative options, ΔP(win) vs best alternative → precise label.
3. **Output:** auto-Corrections with C2 provenance into `data/corrections/` rails
   (store → `reviewed.json` → `tune.py`). Decide at build time whether auto-corrections
   enter the W-fit directly or only post-review (start conservative: review-gated).
4. **Threshold tuning:** sample flagged decisions, human-review via the existing
   blunder-inspector flow, measure precision, set threshold before mass production.
5. **Played-well-lost report:** lost games with zero flags → report artifact (not
   corrections) — the "played perfectly but lost" detector.

**Exit:** labeler run over the corpus with measured precision at the chosen threshold;
played-well-lost report produced.

## S3b — WP4: expert-iteration tuner (2 sessions, after G1)

**Owns:** `tools/train/tuner/`.

> **Design is LOCKED in [ml-training-design-s3b.md](ml-training-design-s3b.md)** (Fable design
> grill, 2026-07-13): expert = one-step fork lookahead + G1 net with terminal override; loss =
> disagreement constraints through the existing `fit.py` rails (unifies WP3+WP4); matchup
> tables = γ-scaled per-archetype deltas, ±30 clamp, `γ_min` shared train/runtime. Execute it.

**S3b-1 — plumbing:**
- Expert = Turn Planner + value-net one-step lookahead over each logged decision's legal
  options (offline; engine fork where the planner needs it).
- Target = expert's option ranking/score distribution; extend `tuner/fit.py` from
  correction ranking-constraints to per-decision expert-target SGD (ranking loss or
  cross-entropy over softmax of linear option scores). Per-deck weights first.
- Verify path: `tuner/verify.py` + `retest.py` rails; `score_diff.py` for neutrality checks.

**S3b-2 — matchup tables + integration:**
- Learned matchup-conditioned weight tables: per-archetype weight deltas, applied at runtime
  where Briefs apply boosts (archetype-keyed like `match_brief`; distinct from per-deck
  Hypothesis-id `weight_overrides` seeds — this adds the archetype axis).
- Adoption run against G2. Compound-feature construction (Soemers co-active pairs) is
  explicitly **v2 backlog**, not this session.

### G2 — adoption gate (checklist)

- ☐ WP4 weights beat current hand-tuned weights on the WP2 harness (paired, matchup × seat
  balanced, checkpoint pool included).
- ☐ `score_diff.py` neutrality where behavior should not move.
- ☐ Ship default-ON with kill-switch (existing doctrine); `strategy.params["value_model"]`
  default flips ON here too.
- ☐ Kaggle ladder watch after ship — ladder stays the final arbiter.

## S4 — WP6: rotation-loop glue

**Owns:** `tools/train/pipeline.py` (new), docs.

Orchestration CLI chaining the loop: corpus → train → G1 validate → label → expert-retune →
G2 eval; scheduled-run wiring (meta-tracker precedent); docs for the rotation/meta-shift
workflow (new deck → deck-genie doctrine seeds → corpus regen → fine-tune → retune → labeler
surfaces residuals). Update `docs/architecture/tier-5-value-model.md` and `docs/tuning/` to
reflect the new pipeline.

## WP5 — league/exploiter (deferred)

**Unlock:** WP4 has shipped checkpoints + corpus mature. Scope then: behavior-clone the
current main agent from its own logs, PPO fine-tune as exploiter probe (report Stage 4 /
ByteRL recipe); exploiter winrate spike = robustness alarm. Torch offline-only. Until then
the WP2 checkpoint pool is the stand-in.

---

## Ground rules (all sessions)

- **Never touch `src/cg/`** (native-engine wrapper). Engine facts: no deal seed; fork-replay
  only via `search_begin`.
- Runtime/shipped agent stays **pure stdlib**; numpy/torch only in `tools/train/` via
  `requirements-train.txt` (never imported by `src/`).
- Cross-platform: `pathlib`, `encoding="utf-8"`, no OS-only assumptions (CI = windows +
  ubuntu).
- Every WP lands tests in the mirrored `tests/` area + a `.github/filters.yml` entry.
- Kill-switch doctrine: big features ship default-ON with a kill-switch — except the value
  model + learned weights, which flip default at **G2**, not before.
- Rules/card facts for any strategy reasoning: verify at `docs/rules.md` /
  `docs/rulebook.txt`, never from memory.
- ADR numbering: the unpushed arch-review branch holds 0052 (KO Oracle), 0054 (provider split),
  0055 (agent runtime), 0056 (Stat Provider seam, renumbered from 0051 to clear the MatchupPlan
  collision); **next free is 0063**.
- End of every session: update the status ledger + notes here, and auto-memory.

## Execution notes — model & effort (2026-07-13)

Build sessions run on **Claude Opus 4.8** (Fable 5 trial expiring). Settings and
compensations:

- **Effort:** `xhigh` for every build session and both gates (S1, S2a, S2b, S3a, S3b, G1,
  G2); `high` for S4 glue; `max` only to re-run a gate that failed twice. Mechanical
  subagent fan-outs (test authoring, sweeps, verify votes) run at `low`.
- **Session kickoff prompts must say to fan out:** Opus 4.8 under-reaches for subagents by
  default. Each kickoff includes: *"Fan independent verification, test authoring, and
  sweeps out to parallel subagents; work the main thread on design and integration."*
- **Spend the price gap on verification** (Opus ≈ half Fable per token): run `/code-review`
  at the end of S2a and S3b before marking the ledger; hold G1/G2 strictly — the gates are
  the quality backstop for the builder tier.
- **Remaining Fable 5 budget, if any, goes to design, not plumbing:** ✅ DONE 2026-07-13 —
  both design grills ran on Fable 5; decisions locked in
  [ml-training-design-s2a.md](ml-training-design-s2a.md) and
  [ml-training-design-s3b.md](ml-training-design-s3b.md). Opus executes the locked designs.
