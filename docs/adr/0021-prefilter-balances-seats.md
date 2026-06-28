# ADR-0021: The self-play pre-filter balances seats; reproducibility is statistical, not seeded

**Context.** M1 adds a local self-play **Pre-filter** (extends `tools/sim/battle.py`) to cheaply
A/B two configs before spending a scarce real-ladder submission —
[ADR-0009](0009-training-methodology.md) Job C keeps the **real Kaggle ladder** as the authoritative
gate; this is triage, not selection. Two engine facts shape it:

- **First/second-player asymmetry.** The player going first cannot attack on turn 1; the player going
  second has a full turn ([docs/rules.md](../rules.md) §2). Measured at **~13 points** in a
  mega_starmie self-mirror (37/63, N=120, Wilson CI excludes 50%).
- **No engine seed.** `cg.game.battle_start(deck0, deck1)` takes no seed and `src/cg/` exposes no RNG
  control, so match outcomes are non-reproducible.

The asymmetry does not wash out on its own: locally the coin flip is effectively deterministic (the
same seat is prompted to choose every game), and — independently — the Pilot's `IS_FIRST` handling is a
fixed choice (tracked as a separate blunder). A naive fixed-seat A/B would therefore measure **seat,
not config**, since the ~13pt seat effect dwarfs a typical few-point config effect.

**Decision.**
- **Every Pre-filter Battle balances seats:** play N/2 matches with config-A as `deck0` and N/2 as
  `deck1`, then aggregate config-A's total win-rate. Any config-independent seat advantage cancels.
- **Reproducibility is statistical, not seeded:** the harness is RNG-free in what it controls, but
  outcomes are Monte Carlo — trust a result only through N + a Wilson CI. The Accept bar **drops
  "reproducible from a seed."**
- **The balanced mirror is the fairness gate:** a config battled against itself must return a win-rate
  whose CI contains 50%. (The glossary's "mirror ≈ 50%" holds only for the *balanced* harness.)

**Considered options.**
- **Rely on the engine's per-match coin flip to randomize seats** — rejected: empirically it doesn't
  (mirror 37/63, not 50%); the local flip is effectively deterministic.
- **Seed the engine for paired / common-random-number variance reduction** — impossible: no seed API.
- **Fix the Pilot's `IS_FIRST` blunder and skip balancing** — rejected: balancing is needed regardless
  (other seat-tied asymmetries may exist, and we must be able to A/B configs that *themselves* change
  first/second behavior). The Pilot fix is a separate strategy improvement.

**Consequences.** `tools/sim/battle.py` gains seat-balancing and an N split. A balanced run costs ~2×
the matches, but throughput is ample (~79 games/s at 8 jobs), so N≈400–800 (±3–5% CI) stays cheap. The
Pre-filter trusts **negative** signals (clearly worse → drop) more than positive ones; the real ladder
remains the gate. The `IS_FIRST` Pilot blunder surfaced by this work is tracked for a separate
`/blunder-buster` pass.

## Amendment — the pre-filter persists a Battle Result record

The Pre-filter's output must be captured for future analysis, not just printed (today `battle.py`
prints a text report and **discards** the per-Match results after `tally()`). Each run appends one
immutable, self-describing **Battle Result** to `data/battles.jsonl` — a committed JSONL log beside
`agent_history.jsonl` / `performance.jsonl` (verified committed; `.gitignore` excludes only
`data/{meta,submissions,replays,decks,probe}/` + `reports/`). Reuse `tools/submit/history.py`
append/next-id helpers. Structure:

- **Aggregate header:** `schema_version`, `battle_id`, `ran_at`, `run_git_hash`, `mode`,
  `params{n_requested,jobs,max_steps,seat_balanced,n_as_deck0,n_as_deck1}`,
  `reproducibility{seeded:false,kind:'statistical'}`, `tally`, `win_rate`, `wilson_ci`, `hypothesis`
  (intent); recommended `engine_fingerprint`, `delta_ab`, `mirror_fairness`, `harness_meta`,
  `expected_direction`.
- **`contestants[]`** (2): `side`, `kind`, `submission_id`, `agent`, `git_hash`, `deck_hash`,
  `overlay{overrides,params}`; recommended `artifact_stem`, `label`, `overlay_digest`.
- **`matches[]`** (per-Match — the **source of truth**; every aggregate recomputes from it):
  `match_index`, `a_seat`, `winner_seat`, `crashed_seats`; recommended `end_reason`, `turns`;
  optional `end_reason_code`, `replay_ref` (reserved for M1b `--save-replays`).

Resolved design calls: deck stored as a per-contestant **`deck_hash`** (a deck change shows as a hash
diff; full list recoverable via `git_hash`+agent); **`turns`** captured on win/draw, `null` on
crash/illegal/max_steps; **seat-swap is implemented here**, so `seat_balanced=true` is the default and
`a_seat` makes balancing auditable (the single biggest current gap — `a_seat` is unrecoverable today);
the **overlay is owned by `battle.py`** (parsed from the `agent@overlay.json` contestant spec, used to
set the subprocess env, recorded from the arg — no env round-trip); `matches[]` nested **inline** at
M1's N (spill to a sibling file only past thousands); **`verdict` is NOT stored** — it is
interpretation, derived on read from `win_rate`+CI, keeping the row append-once immutable. A SQLite
store + offline dashboard is a *derived* read-path, deferred.
