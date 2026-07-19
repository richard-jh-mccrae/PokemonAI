# S2b Design — Eval Harness: Pairing, Power, Verdict & the Position-Replay Spike (LOCKED)

**Status:** design locked 2026-07-19 (Fable 5 design grill; user-approved forks). The S2b build
session **executes** this — it does not re-derive the decisions. Deviations discovered during
build get recorded here with a reason, not silently applied. Emits the frozen C3 report
([ml-training-contracts.md](ml-training-contracts.md) §C3); G2 is measured on this harness.

**Grounding (verified at design time):**
- Contestant resolution exists: `tools/sim/battle.py` `resolve()` maps an all-digit spec → Build
  Ledger zip (extracted to a tempdir) and a name → working-tree agent; `name@overlay.json` adds an
  experiment config (`AGENT_OVERLAY`). Library surface reused as-is: `run_battle` (worker fan-out,
  persistent `AgentServer` pairs, crash = loss), `seat_plan`/`balanced_tally` (ADR-0021 seat
  balance), `wilson_ci`, `read_deck`.
- Stats core exists: `tools/sim/paired_ab.py` — per-matchup `matchup_delta` (binomial variance),
  `paired_delta` (equal-weighted cells, closed-form normal 95% CI), `flips_on` ship rule
  (`delta ≥ 0 ∧ ci_low ≥ −0.01 ∧ crashes == 0`). `gauntlet_ab.py` pairs only overlay-ON vs OFF of
  one agent — the generalization below subsumes it.
- Run mechanics exist: `tools/sim/corpus.py` — disk-authoritative manifest, crash-safe resume,
  `--max-games`/`--max-gb` caps, per-pairing persistent servers, gzip films (~28 KB/game).
- Films carry the fork seed: `MatchRecorder` stores the raw acting-seat obs (`record.py:53`),
  which retains `search_begin_input` — per-decision forks from corpus/eval films are fully
  specifiable offline (same fact S3b D1 relies on).
- Fork limits (`docs/pyeng/determinism.md` §4, `api.py:449`): a native `search_begin` fork
  **reshuffles** every predicted hidden zone (identical draw order is unreplayable); forks are
  call-to-call deterministic **only from a plain MAIN select**; fork observations carry
  `search_begin_input = None`, so agents inside a forked playout **cannot nest forks** — the
  Pilot's lethal-confirm and simulate-line tiers are silently OFF in playouts.
- Checkpoint provenance: `data/agent_history.jsonl` (committed) records submitted builds;
  `data/submissions/builds.jsonl` + zips (local, gitignored) hold every build.

## D1 — Pairing model: arbitrary specs, common-opponent paired design (user-locked)

`baseline` and `candidate` are each **any** `battle.py` spec (working-tree name or build id,
optional `@overlay`). Both arms play the **same opponent set, seat schedule, and N per cell** —
a common-opponent design, never head-to-head as the measurement (the protocol the research
verifies as misleading: Hearthstone c5-vs-b4, AlphaStar's ~3M RPS cycles).

**Standard cells** (each seat-balanced via `seat_plan`):
- **Cross:** contestant's deck vs each *other* working-tree deck.
- **Mirror:** contestant's deck vs its own deck (self-matchup regressions).
- **H2H (informational):** a small candidate-vs-baseline block (~200 games), reported in the
  C3 `matchups` list with `opponent: "h2h"` — **never enters the paired delta or verdict**.
- **Checkpoints:** the D3 pool, reported in C3 `checkpoints`, tripwire-only.

`gauntlet_ab.py` remains as a thin wrapper (overlay A/B = same agent spec ± overlay).

## D2 — Statistics & power: paired_ab reuse, 3%-delta default (user-locked)

Aggregation = `paired_delta` unchanged: equal-weighted matchup cells, closed-form normal 95% CI
(not bootstrap). Per-arm sample size from `n_total ≈ 0.5 · ((z_α/2 + z_β)/d)²` at 95%
confidence / 80% power (z = 2.80):

| Preset | Detectable delta d | Games per arm | Run total (2 arms) |
|---|---|---|---|
| `--quick` | 5% | ~1.6k | ~3.2k |
| **default** | **3%** | **~4.4k** | **~9k** |
| `--fine` | 2% | ~9.8k | ~20k |

The harness derives per-cell N from the preset and live cell count; the report records the
preset and achieved per-cell N. AIVAT (D5 seam) is the later ~10× lever — do not over-buy N now.

## D3 — Verdict & checkpoint tripwire (user-locked)

**Verdict rule = `flips_on`:** `pass` = `delta ≥ 0 ∧ ci_low ≥ −0.01 ∧ zero candidate crashes`;
`fail` = `ci_high < 0`; else `inconclusive`. Same "no evidence of harm beyond 1%" bar the repo
already ships features with. (G2's "beats current weights" is satisfied by pass + the human
gate; strict superiority `ci_low > 0` is reported implicitly by the CI, not a separate tier.)

**Checkpoint pool = regression tripwire.** Pool = builds in the committed
`agent_history.jsonl`, resolved to local ledger zips (missing zip → skipped with a named
warning in the report); `--checkpoints` pins extra build ids. Checkpoint cells never enter the
paired delta and can never make a verdict pass. But if the candidate's winrate vs any
checkpoint falls below the **baseline's** winrate vs that same checkpoint by more than the
cell's CI margin, the verdict is **capped at `inconclusive`** and the report carries a
`regression` flag naming the checkpoint — non-transitivity drift caught without letting frozen
history outvote live opponents.

## D4 — Spike: duplicate-POSITION replay, auxiliary mode only (user-locked)

The scoped "duplicate-deal" spike is reframed by the fork facts: identical deals are
impossible (reshuffle), identical opening **positions** are not. Timeboxed (~half a session):

1. **Opening capture:** from self-play films, take each seat's first **plain MAIN select**
   frame (the only fork-deterministic frame class). Reconstruct both sides' multisets offline —
   own deck/prizes via the anchored-tracker path (`backfill_seed.own_prizes_for` /
   `_deck_known_counts` precedents), opponent hand/deck from the opponent's own frames
   (self-play knows both seats), `opponent_active=[]` (post-setup, face-up).
2. **Playout driver:** `search_begin(...)` per arm per position, K playouts each; fork obs →
   `AgentServer.act` → `search_step`; `manual_coin=False`; max-step backstop.
3. **Success criteria (both required to ship as a mode):** (a) ≥95% of sampled openings drive
   to a terminal verdict without protocol error; (b) empirical variance of the paired
   per-position delta is measurably below the unpaired variance at equal game count (record
   the ratio in the report).

**Recorded caveats (why this is never the primary G2 instrument):** each playout reshuffles
unrevealed order; the recording agents' setup choices are baked into the position; and no
nested forks means both arms play **below live strength** (fork tiers off) — equally degraded,
but a different game. If it lands it ships as an auxiliary variance-reduced mode and a
skill-sensitivity classifier feeding D5 strata; live paired high-N remains the G2 measurement.
If it fails, record the verdict in the build plan and drop to fallback-only — the harness is
complete without it.

## D5 — Strata, AIVAT seam & run mechanics (user-locked)

- **Strata (v1) = value-swing proxy on live eval films:** replay each film through the
  committed seed value model; sensitivity score = max P(win) swing across own decisions;
  split at the run's median into `high-swing` / `low-swing` strata → C3 `strata` (per-stratum
  delta + CI). No forks needed; upgrades automatically when the G1 net replaces the seed.
  (Fork-classifier labels are a spike-conditional upgrade, not v1.)
- **AIVAT seam frozen now:** `tools/sim/eval_aivat.py`, one entry point
  `aivat(films, value_fn) -> {"variance_reduction": float, "corrected_delta": float} | None`;
  v1 ships the null implementation → C3 `aivat: null`. WP1's net plugs in with no harness
  rework (per-decision values come free from the value model — the report's stated synergy).
- **Run mechanics = the corpus pattern wholesale:** `reports/eval/<run_id>/` with a
  corpus-style disk-authoritative `manifest.json`, crash-safe resume, `--max-games`/`--max-gb`
  caps; **every eval game filmed** (`.json.gz`, ~28 KB/game — the strata proxy and AIVAT
  input); `report.json` (C3, `report_version: 1`) written at completion. `reports/` is already
  gitignored; `tools/sim/**`/`tests/sim/**` already map to the `sim` CI area.

**File layout (new files only, per the WP2 ownership rule):** `tools/sim/eval_run.py` (matrix
runner + CLI), `eval_report.py` (C3 emitter + verdict/tripwire), `eval_strata.py` (proxy),
`eval_spike.py` (D4), `eval_aivat.py` (seam). Tests mirrored in `tests/sim/test_eval_*.py`.

## Acceptance → exit mapping

The playbook's S2b exit ("end-to-end matrix eval of current agents producing a C3 report;
spike verdict recorded") is measured exactly as defined here: a default-preset run over the
three working-tree agents emitting a valid C3 report with verdict + strata populated and
`aivat: null`; the D4 spike verdict (success ratio + variance ratio, or the failure) recorded
in the build plan's ledger notes.

## Non-goals (v2 backlog, with triggers)

- AIVAT implementation — trigger: G1 passes (WP1 net exists); fills the D5 seam.
- Exploiter probe in the pool — WP5's unlock (shipped WP4 checkpoints); the checkpoint
  tripwire is the stand-in.
- Meta-deck opponents in the matrix — trigger: a generic driver bundle for bare decklists
  exists (same blocker recorded in S1); the opponent-set code takes a list, not a hardcode.
- Bootstrap/hierarchical CIs, game-weighted aggregation — trigger: cell counts grow uneven
  enough that equal-weighting visibly distorts (revisit with meta opponents).
- Elo/rating layer over the matrix — the pairwise C3 report is what G2 consumes; ratings only
  if the contestant pool grows past pairwise readability.
