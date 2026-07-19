# S3a Design — Blunder Labeler: Residual Decisions (LOCKED)

**Status:** design locked 2026-07-19 (Fable 5 design grill). The S3a build session **executes**
this — deviations get recorded here with a reason. **The detector core is NOT here:** the expert
(one-step value lookahead, terminal override, single-pick v1, frame sampling) and the
θ-disagreement → machine-Correction emission are locked in
[ml-training-design-s3b.md](ml-training-design-s3b.md) §D1/§D2 and are not restated or re-derived.
This doc locks only what S3b delegated or left open: the no-fork triage pass, the θ precision
protocol, the emission rails and gating, the shared per-decision-P(win) reader, and the
played-well-lost report.

> **Parallel-grill coordination:** the S2b (eval harness) design is being grilled concurrently and
> its AIVAT plug-in consumes the same per-decision-P(win) reader locked in §D5. §D5's record shape
> is the coordination point — if S2b's locked doc names a different shape, reconcile in
> [ml-training-contracts.md](ml-training-contracts.md) (additive C4) before either session builds.

**Grounding (verified at design time):**
- Film alignment: the Decision prompted at film frame `i` stores its choice in frame `i+1`'s
  `selected` and its **aligned agent obs** in frame `i+1`'s `obs`
  (`tools/train/blunder/decisions.py:64-85`); `tools/train/value/extract.py:29-40` computes value
  rows on that same aligned obs via `pilot._board` — the reader in §D5 reuses this path verbatim
  (zero skew vs training extraction).
- Fork seeds: **corpus films carry `search_begin_input` directly on the recorded obs**
  (`src/cg/game.py:15` attaches it to the obs `MatchRecorder` stores; the s3b grounding). Ladder
  films do NOT (fixture: 0/61 film obs vs 121 steps-level) — there it needs the
  `backfill_seed.py:37` content-join. This is why v1 labels corpus films only (§Non-goals).
- Correction rails: store tree unions every `<dir>/corrections.jsonl` under `data/corrections/`
  (`tools/train/blunder/store.py:81`), dedup keyed by (identity, chosen, correct, category)
  (`store.py:27-44`); `tune.py:118` filters `source=="own"` only — no provenance filter;
  `build_correction` validates `category` against the closed vocab
  (`tools/train/blunder/categories.py`); `reviewed.json` dispositions exclude by subject key and
  `refuted` also drops from the fit (`tools/train/blunder/reviewed.py:33-37`); the blunder shell
  serves any `(replays, store_path)` pair (`tools/train/blunder/shell.py:160-177`).
- Value runtime: `ValueModel.load(path)` is name-pinned and **fail-open** (null model → 0.5,
  `src/common/value/model.py:36-51`); v2 format + grown features per S2a design §D3.
- Corpus identity: episode ids are globally unique by construction — `selfplay.py:19-23` documents
  that the dedup/review keys assume it. Corpus `info.TeamNames` entries are
  **`{stem}#<seat>-<agent>`** (`tools/sim/corpus.py:226-229`), NOT bare agent names — the bare
  name is the substring after `#<seat>-`.

## D1 — Package home, shared-detector ownership, sequencing

New package `tools/train/label/` (tests `tests/label/`, `.github/filters.yml` entry per ground
rules). **The detector lives here** — `label/expert.py` (the s3b-D1 one-step lookahead) +
`label/detect.py` (θ-disagreement emission) + `label/vread.py` (§D5) + `label/triage.py` (§D2) +
`label/run.py` (CLI). The labeler IS the disagreement detector (s3b D2); S3b consumes it through
**file-level interfaces only** — the machine store (§D4), `thresholds.json` (§D3), and the CLI for
outer-loop re-detection — never a build-time import into `fit.py`.

**Sequencing locks:**
1. S3a lands before S3b-1's outer loop runs (S3b-1 fit-extension plumbing may parallelize; its
   re-detection rounds invoke the S3a CLI). Ledger note updated accordingly.
2. **S3a never live-fits machine records.** The C2 human-wins collision rule and the
   satisfied-rate regression guard are S3b fit extensions; until they land, S3a's only tune
   contact is a `--dry-run` smoke (§Acceptance). Emissions sit in the gitignored store until
   S3b-1 consumes them.

**Detector missions — one knob:** the detector takes a *choice provider*: `recorded` (the film's
`chosen` — blunder-mining: judge what the build that played actually did) or `replayed` (the
current pilot's pick on the aligned obs — s3b's expert-iteration mission). Same expert, same θ,
same emission; nothing else differs.

## D2 — Triage pass: full-coverage Φ-deltas rank, never label

For every own MAIN decision of each seat (both corpus seats are ours), compute
`V_k` on the aligned obs via §D5; triage drop at decision `k` = `V_k − V_{k+1}` over consecutive
same-seat decisions (turn boundaries included). Crossing a boundary folds the opponent's response
and draw/coin luck into the drop — **that is why triage never emits Corrections**: it is a ranking
signal only (the Suphx Φ-delta shape used as a prefilter, not as credit).

Uses, both locked:
1. **Fork-budget ranking for blunder-mining:** the CLI spends the counterfactual budget on frames
   in descending triage-drop order, ≥ `theta_triage` (§D3). This is a *third stratum added for the
   labeler mission*; s3b D1's two strata (apprentice-ambiguity first, uniform residual) stand
   unchanged for the expert-iteration mission — strata weights are CLI parameters recorded in the
   run manifest.
2. **Played-well-lost coverage** (§D6): triage is the cheap full-coverage screen that makes "zero
   flags" a meaningful claim without forking every frame.

The detector is **outcome-blind**: wins, losses, and draws are all labeled (a blunder in a won
game still trains; "bad play, good outcome" is covered for free). Outcome enters only §D6's view.

## D3 — θ protocol: the human precision review (delegated by s3b D2)

1. **Review run:** detector at permissive `θ₀ = 0.05`, `recorded` choices, over a corpus slice
   (per-agent game count is a CLI budget, recorded in the manifest; all agents represented).
   Flags land in the machine store with the manifest marked `mode: "review"` (an explicit
   `--theta` is required and permitted only in this mode, see §D4 gate).
2. **Stratified human review** in the existing blunder shell over `(corpus replays, machine
   store)`: buckets by ΔV `[0.05,0.10) / [0.10,0.20) / [0.20,0.40) / [0.40,1.0]`, ≥ 12 flags per
   bucket, ≥ 60 total. Verdicts via the existing disposition flow (`review_correction.py`):
   `refuted` = false positive; left active = agreed. Precision per bucket = 1 − refuted fraction.
3. **Set θ** = the lowest bucket edge whose cumulative precision at-and-above is ≥ **0.80**. No
   edge qualifies → the labeler does not ship emissions (report-only); iterate the net/expert
   first and re-run the review — never lower the bar.
4. **Set `theta_triage`** from the same run: on the uniform stratum, the largest value catching
   ≥ **90%** of confirmed (≥ θ) blunders' triage drops. Inconclusive (too few confirmed) →
   default 0.03 and record that it is a default, not a measurement.
5. **Commit `tools/train/label/thresholds.json`:**
   `{"theta": ..., "theta_triage": ..., "review": {"round", "n_reviewed", "per_bucket":
   {bucket: {n, precision}}, "triage_recall"}}` — the single source both the labeler and S3b's
   detector runs read (same share-the-value pattern as s3b's `γ_min`).
6. **Ongoing guard:** every mass `--emit` run lists a fresh random sample of 20 flags in its
   report as the spot-check queue. A periodic human spot-check below **0.70** precision → delete
   the machine store, re-run this protocol from step 1. Global θ in v1 (per-agent: §Non-goals).

## D4 — Emission rails: direct-to-fit with guardrails, no per-record gate

**Decision (closes the build plan's "review-gated vs direct" question):** machine Corrections
enter the fit **directly** — the θ precision gate is the human review, amortized. Per-record
approval at machine volume defeats the pipeline; the safety net is layered instead: the 0.80
gate + 0.70 alarm (§D3), the C2 human-wins collision rule and s3b D4's satisfied-rate regression
guard (both enforced at S3b's fit), `refuted` dispositions, and the caps below.

- **Store:** `data/corrections/machine/corrections.jsonl` — matches the store glob
  (`store.py:81`), so every consumer (tuner, `find_conflicts`, reports) unions it with the
  human tree automatically; C2 consumers opt in to *distinguish*, not to *see*. Gitignore
  `/data/corrections/machine/` (regenerable artifact; the committed human tree stays gold; a
  fresh clone/CI sees none). **Rewritten wholesale per run** — no append-compact for a
  regenerable file; re-runs cannot duplicate.
- **Manifest sidecar** `data/corrections/machine/manifest.json`: run id, mode
  (`review`/`emit`), git rev, corpus manifest ids, value-model meta + sha256, θ used, choice
  provider, strata weights, budgets, per-agent emitted/dropped counts.
- **Emit gate:** default `--emit` **requires** committed `thresholds.json` and uses its θ;
  `--theta` override is allowed only with `mode: "review"` manifests (§D3 step 1). No
  thresholds file and no explicit review mode → report-only. Fail-safe by construction.
- **Caps:** ≤ 200 emissions per agent per run, descending |ΔV| (VIPER critical-state
  concentration); the report prints how many qualifying flags were dropped (no silent caps).
- **Record fields:** `source="own"` (both self-play seats are ours — flows through
  `tune.py:118` untouched), `provenance="machine"` (C2), `category="value_delta"` — a **new
  term appended to `CATEGORIES`** (machine-only, engine-measured kind; keeps machine records
  separable in every report and off the `other` vocab-gap signal; humans never use it),
  `chosen`=[recorded pick], `correct`=[expert best], rationale auto-generated with ΔV and the
  per-option V table (s3b D2), `obs`= the aligned agent obs (carries `search_begin_input` in
  corpus films — cascade-ready), `agent` = the **bare agent name parsed from the corpus
  TeamNames** (`{stem}#<seat>-<agent>` → `<agent>`; must match `src/agents/<agent>` so
  `tune.py`'s per-agent grouping and `_build_pilot` resolve), `agent_version` from the corpus
  manifest's `agent_versions`, `agent_build=None` (corpus games are not submission builds; dest
  file is explicit so store routing never consults it).

## D5 — `vread`: the shared per-decision-P(win) reader (S2b coordination point)

`tools/train/label/vread.py` — `iter_values(pilot, replay, model)` yields one record per own
MAIN decision frame, computed on the **aligned obs** (`film[i+1].obs`) via
`features_from_board(pilot._board(obs))` — exactly `extract.py`'s replay path, so the labeler,
the S2b AIVAT plug-in, and value-net training all see identical V(s) for identical frames.

**Frozen record shape** (S2b's AIVAT stub consumes this; duck-typed dicts, no import needed
until integration — AIVAT fills in after WP1 anyway):

```
{"episode_id": int, "frame": int, "seat": int, "turn": int, "agent": str, "v": float}
```

Additive fields are non-breaking; renames/removals require the contracts-doc amendment (§header
note). Pilot = the film seat's own agent pilot (as `tune.py`'s `_build_pilot`); model = the
G1-passed artifact, explicit `--model` path (default the packaged `value_model.json`), meta +
sha256 recorded in the manifest.

**Null-model rule (inverse of runtime):** `ValueModel` is fail-open at runtime by design; offline
a null model would silently emit `v=0.5` everywhere — zero signal presented as data. `vread`
**raises** on a null/absent model. Offline tools fail loud.

## D6 — Played-well-lost report

**Definition:** a *lost* (not drawn) game for seat `s` is **played-well-lost** iff after full
triage over all of `s`'s decisions and counterfactual confirmation of every triage hit
≥ `theta_triage`, no confirmed blunder with ΔV ≥ θ exists. (Confirmation-sampling makes "zero
flags" claimable only because triage is full-coverage — §D2.)

**Artifact:** `reports/played_well_lost/<run_id>.json` (`/reports/` already gitignored) + a
printed summary. Per lost episode-seat: `{episode_id, seat, agent, opponent, n_decisions,
n_triage_hits, n_confirmed, max_confirmed_delta, verdict: "clean"|"blundered"}`; aggregate
clean-loss rate per agent × opponent (true `TeamNames` identity — evaluation stratification
only, per S2a D1's training-input ban). Consumers: the human ("is this deck losing on doctrine
or on dice") and WP6's rotation loop — a high clean-loss rate in a matchup is a
doctrine/matchup-table signal, not a weight signal; it must NOT feed corrections.

## Acceptance → build-plan exit mapping

The S3a exit ("labeler run over the corpus with measured precision at the chosen threshold;
played-well-lost report produced") is met by: the §D3 review artifact (committed
`thresholds.json` with per-bucket precision), one mass `--emit` run at the locked θ with its
manifest, the §D6 report over the same run, and a `tune.py --dry-run` smoke showing machine
records load through the rails (per-record gate absent by design; live fitting waits for S3b-1
per §D1 sequencing). Tests land in `tests/label/` with a corpus-film fixture.

## Non-goals (v2 backlog, with triggers)

- **Ladder/peer film labeling** — seeds need the `backfill_seed.py:37` content-join and peer
  records are outside `tune.py`'s `source=="own"` fit anyway. Trigger: corpus precision holds
  and we want own-ladder audits or opponent-modeling data (WP5 feeds).
- **Per-agent θ** — trigger: the §D3 review shows a per-agent precision spread > 15 points.
- **Positive-surprise mining** (opponent V jumps = their blunders → exploiter/counterplay
  fodder) — WP5 territory.
- **Machine turn/match-scope Corrections** — decision scope only in v1.
- Inherited from s3b unchanged: multi-pick selects, expectimax over coin outcomes, multi-turn
  expert rollouts.
