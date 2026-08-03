# Continuous Integration

Two workflows:

| Workflow | Trigger | What it does |
|---|---|---|
| [`ci.yml`](../.github/workflows/ci.yml) | push to `main`, PR, dispatch | the test suite (everything below) |
| [`leaf-gate-main.yml`](../.github/workflows/leaf-gate-main.yml) | **push to `main` only**, dispatch | ADR-0072's **Discrimination Gate**, watching main — see [Main watchdog](#main-watchdog-the-discrimination-gate) |

`.github/workflows/ci.yml` runs the test suite on every push to `main`, every pull
request, and on manual dispatch (`workflow_dispatch`). It runs on `ubuntu-latest` at
Python **3.12** (the most recent; the dev box runs 3.11). Every step runs under `bash`
(Git Bash on a Windows runner, if the matrix is ever widened) so the commands are
identical across OSes, and `PYTHONUTF8=1` gives Windows the same UTF-8 default as Linux —
both platforms stay first-class because the Kaggle grader is Linux and dev/build is on
Windows (the committed `cg/libcg.so` + `cg/cg.dll` let the engine load on either).

## Selective testing (what runs on a PR)

To keep pull-request feedback fast, a PR runs **only the test directories whose subsystem
its diff can affect** — not the whole suite. On **push to `main`** and **manual dispatch**
the **full** suite always runs (main must be green end-to-end).

A [`dorny/paths-filter`](https://github.com/dorny/paths-filter) step (*Detect changed
areas*) reads the declarative source-area → glob map from
[`.github/filters.yml`](../.github/filters.yml); the *Determine test plan* step in
[`ci.yml`](../.github/workflows/ci.yml) then turns those booleans into a concrete pytest
target list, applying the reverse-dependency unions. The map was derived from a **repo-wide
static import-graph walk** (every `import`/`from X import Y` in `src/`, `tools/`, `tests/`,
resolved transitively — including function-local imports, which is how the analysis caught
that `tests/conftest.py`'s session fixtures pull in `train.tune`/`sim.corpus`/
`meta_tracker.parse`/`common.value.model`), then **cross-checked against the three
subprocess/`importlib` "dynamic agent load" sites** that a plain import graph can't see but
real test behavior does depend on: `tools/sim/check_agent.py`, `tools/arena/worker.py`, and
`tools/submit/brief.py` each load an agent's `main.py`/`strategy.py` via
`importlib.util.spec_from_file_location` (or a worker subprocess) rather than a static
`import`. The map is deliberately **broad and fail-safe**: when a change *could* break a
test, that test runs.

### Which change runs which tests

| Change under… | Runs | Why |
| --- | --- | --- |
| `src/cg/**` | **full suite** | The native engine underlies everything except `meta_tracker` (which only ever parses recorded replay JSON, no live engine calls) |
| `src/common/*.py`, `src/common/scouting/**`, `src/common/strategy/**`, `src/common/value/**` (the `common_agent_core` filter) | `tests/agents`, `tests/arena`, `tests/blunder`, `tests/label`, `tests/scouting`, `tests/sim`, `tests/strategy`, `tests/submit`, `tests/train`, `tests/tuner`, `tests/value` | `common.pilot`/`common.runtime` import scouting+strategy+value directly, and `common.runtime.make_agent` is imported by every agent `main.py` — real ones AND the fixture agents dynamically loaded into sim/arena/submit matches. Narrower than the old blanket `src/common/**` only in that it skips `tests/meta_tracker`, `tests/cards` (folded into `cards` below), and the self-contained cgpy/parity twin |
| `src/agents/**` | `tests/agents` | Nothing imports agents at module load (sim battles use *fixture* agents, not `src/agents`) |
| `tools/arena/**` | `tests/arena` | Pure leaf — nothing imports arena |
| `tools/sim/**`, `src/common/attack_overrides.json`, `src/common/attack_overrides.provenance.json` | `tests/sim`, `tests/arena`, `tests/label`, `tests/submit` | `arena` imports `sim.selfplay`; `label`'s corpus fixture and `submit`'s `check_agent` import sim modules too. The two override stores are named here because `common_agent_core` matches `src/common/*.py` — **`.py` only** — so a table-only diff matched no filter and reached the suite via the `any` fail-safe. It ran, but by accident; `tests/sim` owns their generator and their provenance gate (ADR-0108), so now a table edit runs that gate by design |
| `tools/submit/**` | `tests/submit`, `tests/sim`, `tests/arena`, `tests/agents`, `tests/blunder`, `tests/label` | verified via the import graph |
| `tools/train/*.py`, `tools/train/blunder/**`, `tools/train/tuner/**` (the `train_wide` filter) | `tests/train`, `tests/tuner`, `tests/blunder`, `tests/value`, `tests/label`, `tests/sim`, `tests/strategy`, `tests/agents` | `tune.py` imports **both** `train.blunder.*` and `train.tuner.*` at module level and is the shared pilot-builder ~20 test files across those dirs import directly (see `conftest.py`'s `ms_pilot` fixture) — so a blunder or tuner change rides this one broad blast radius |
| `tools/train/value/**` | `tests/value`, `tests/label`, `tests/sim` | genuine leaf — narrower than `train_wide` |
| `tools/train/label/**` | `tests/label` | genuine leaf, nothing else imports it |
| `tools/train/probes/**` | `tests/train` | genuine leaf (exercised by `tests/train/test_gates.py`) |
| `tools/meta_tracker/**`, root card/meta tool scripts | `tests/meta_tracker`, `tests/cards`, `tests/agents`, `tests/arena`, `tests/blunder`, `tests/label`, `tests/scouting`, `tests/sim`, `tests/submit`, `tests/train` | `cards`/`archetype`/`parse` are imported widely, but **not** by `tuner`, `strategy`, `value`, or `parity` — verified via the import graph (a real narrowing; the old mapping also under-counted `agents`/`label`/`scouting`, a gap this fixes) |
| `src/common/cards.py`, `src/common/effects.py` (the `cards` filter) | `tests/cards` (plus `common_agent_core`'s broad set, since these two files are also in that glob) | `test_cards.py` imports `common.cards` directly; the rest of `tests/cards` exercises `tools/meta_tracker`'s independent card-parsing twin, already covered above |
| `src/cgpy/**`, `tests/parity/**`, `tests/fixtures/parity/**`, `data/engine/coverage.json` | `tests/parity` | The ADR-0050/59 pure-Python engine twin is self-contained — nothing else imports `src/cgpy` at runtime, so its heavy trace-replay gate runs *only* when cgpy files change (and an unrelated PR never pays for it) |
| shared test infra (`tests/conftest.py`, `tests/*_helpers.py`, `tests/fixtures/**` except `tests/fixtures/parity/**`), `requirements.txt`, `.coveragerc`, `pytest.ini`, `.github/workflows/**`, `data/**` except `data/engine/coverage.json`, root card-builder scripts | **full suite** | Can break anything |
| `tools/apply_seam_coverage.py`, and its inputs `src/agents/*/deck.csv`, `src/agents/*/STRATEGY.md`, `docs/plans/apply-seam-coverage.md` (the `strategy` filter) | `tests/strategy` | The POC-A2 apply-seam coverage census (Issue #269) is a `tools/` script whose only tests live in `tests/strategy`, because what it measures is `common/apply_option` + `common/snapshot_coverage`. Its inputs are named on the same filter deliberately: the census's rot-guard trips when a **deck** gains a card carrying Effect Clauses, but `agents` maps only to `tests/agents`, and the markers test reads a **`.md`**, which `docs` plans as nothing — so without these lines each guard would be skipped by exactly the change that breaks it |
| `tools/meta_tracker/probe_cards.py`, `tools/meta_tracker/probe_triggered_ability.py` (also on the `strategy` filter) | `tests/strategy` (plus `meta`'s broad set, since both files are under `tools/meta_tracker/**`) | Issue #305's triggered-Ability measurement lives in `tests/strategy` but is *driven* by the probe harness, which `meta` maps to `tests/meta_tracker` only — so without these lines an edit to the probe would never run the one test that re-drives it against the live engine |
| a single `tests/<area>/**` file with no matching source change | just `tests/<area>` | A pure test-file edit touches no source, so it stays narrow instead of paying for a broader filter's reverse-dependency add-list |
| docs / any `*.md` | **nothing** (job passes green) | No runtime surface |
| anything unmatched | **full suite** | A new top-level area is never silently skipped |

Every row above names test *directories*, which is why a selective run also appends the one
root-level test **file**, `tests/test_import_hygiene.py`, unconditionally. That file bans
`tests.*` package imports — shadowable by any installed distribution shipping a top-level
`tests` package, and therefore a failure CI can never reproduce on its own (see the file's
docstring, and *Scope & extending* below). Before it was appended, a PR touching only
`tests/strategy/**` planned exactly `tests/strategy` and skipped the guard — on precisely the
diffs that introduce the violation. It scans 555 files in 0.33 s, so it always runs.

The plan step unions the sets for a multi-area diff, and any *foundation* filter (or a
change that matches no filter — the `any`-but-nothing-recognised case) forces the full
suite. `.github/filters.yml` is the source-area map; the reverse-dependency unions (e.g.
`sim` → also `arena`) are the `add …` lines in the *Determine test plan* step of `ci.yml`.

On **push to `main`** (i.e. after a PR merges) the filter is skipped entirely and the full
suite always runs — `github.event_name` is `push`, not `pull_request`, so the plan step's
`if [ "$EVENT" != "pull_request" ]; then run_all=true; fi` branch fires unconditionally.
Main is never left validated only by a narrowed PR run.

### Conditional gates

Two gates only run when they are meaningful for the selected tests (both always run on a
full suite):

- **Scouting coverage gate** (`.coveragerc`, `fail_under = 80`, scoped to
  `common/scouting/*` + `compile_scouting.py`) — only when `tests/scouting` is in scope.
  Running it on a subset that excludes the scouting tests would measure 0 % and fail
  spuriously, so the plan step's `coverage` output gates it.
- **Attack-audit soundness gate** (`tools/sim/ci_audit_gate.py`, ADR-0032) — the bounded
  engine audit diffed against the shipped damage oracle; fails on any over-prediction
  (phantom-KO risk). Runs when attack/damage/effect code is in scope (`tests/sim`,
  `tests/meta_tracker`, or `tests/cards`).

### Determinism gates (#178, ADR-0072 amendment C)

Both run on every non-docs change, gating, and together they cost about 2 minutes.

- **Determinism backstop** — the seven live-native-engine modules, repeated **15×**. They are the
  only tests whose answer can ride the engine's RNG (a shuffle *inside* a simulated line is not
  reproducible — `docs/pyeng/determinism.md` §4), and the whole set runs in ~4 s, so repeating it
  is nearly free. A frame that answers differently between repeats is unstable by definition. This
  is the cheap net *underneath* the real guard, which is
  `tests/strategy/test_engine_admissibility.py`: that one measures whether a drive consumed
  randomness at all, so a sampled frame fails the day it is added rather than 1 run in 30 later.
- **cgpy twin arm** — the whole selected suite again under `CG_ENGINE=py`. cgpy's search is
  `SeededRng(0)`, so this arm is reproducible *by construction* and any flap in it is a real bug.
  Green as of 2026-07-27 (3883 passed / 8 skipped).

  A test the twin cannot answer is marked in the diff, never waved through by making the step
  non-gating: `@needs_live_board_search` (`tests/conftest.py`) for one that needs a live-board
  search round-trip, or a module-level skip stating why (the native determinism pins, the
  engine-audited effect probes). Those markers are the parity ledger — they disappear as cgpy
  parity grows, and a non-gating step would have hidden the same information.

## What runs (the suite itself)

The suite is offline and self-contained on Linux:

- **Native engine** — `src/cg/` ships both `libcg.so` (Linux, x86-64 ELF) and `cg.dll`
  (Windows); `sim.py` picks by `os.name`. A dedicated *Verify native engine loads* step
  prints the loaded library path and fails fast with a clear error if it can't load.
- **Simulator** — `kaggle-environments` (the `cabt` env) is a pip dependency; the
  playability/deployability tests run real matches in-process, no network.
- **Kaggle CLI** — the `fetch` / `pipeline` tests monkeypatch the CLI, so no Kaggle API
  token or network is needed.

Tests live in per-subsystem subdirs under `tests/` that mirror `src/` and `tools/`
(`tests/scouting` ↔ `src/common/scouting`, `tests/arena` ↔ `tools/arena`, …). A root
[`pytest.ini`](../pytest.ini) anchors `rootdir` at the repo root so the shared
`tests/conftest.py` (which puts `src/` and `tools/` on `sys.path`) loads for **any**
invocation — the full `pytest tests/` or a selective `pytest tests/arena tests/sim`.

JUnit XML and (when the coverage gate runs) `coverage.xml` upload as build artifacts named
`reports-<os>-py<version>`.

## Main watchdog: the Discrimination Gate

[`leaf-gate-main.yml`](../.github/workflows/leaf-gate-main.yml) runs
`tools/train/leaf_lab.py diff --baseline data/leaf_lab/baseline.json` on **every push to `main`**
and fails the run on any unruled `OK → MISS` frame flip. It is ADR-0072's Discrimination Gate,
pointed at main rather than at a branch.

**Why it exists.** The gate was only ever run by whoever happened to be doing a swap, so drift
accumulated unattributed. ADR-0072 recorded two `OK → MISS` frames on *untouched* main and could not
say whether they were real regressions landed unmeasured or a baseline needing re-capture; #186 then
hit the same false-red weeks later on an unrelated branch. That ADR's own prescription is *"run the
gate on `main` before the next swap, not after it"* — this workflow is that sentence as CI. A red is
attributable to the merge that triggered the run, while the diff is one commit wide.

**It never writes the baseline, by design.** Auto-recapturing on merge would redefine the "before"
picture to whatever just landed, so every regression would bless itself and the gate would pass
forever by construction. The baseline is a *ruling record*, not a cache. Re-capture is deliberate:

```bash
python tools/train/leaf_lab.py capture --out data/leaf_lab/baseline.json
```

and only after the flips it would absorb have been **ruled** with the user.

**That precondition is now ENFORCED, not just documented** (ADR-0094, Issue #259). `capture`
reads the outgoing baseline first and **refuses to write** if any frame would move in the fail
direction (`OK → MISS` here, `agree → disagree` for the Decision Gate) without carrying a ruling in
the Ruling Index. It names every offending frame and leaves the baseline untouched:

```
REFUSED: re-capture refused: 1 frame(s) would move in the FAIL direction with no ruling on
record -- 82226116|0|decision|94. A baseline is a RULING RECORD (CLAUDE.md): rule the flip
first (a wave packet), or use `restamp` if you only need the recorded revision moved.
```

Improvements and brand-new keys write freely — only the fail direction is guarded. A frame that is
**held out** or whose ruling is **voided** already carries a ruling, so it needs no second excuse.

**Honest scope:** this guard repairs nothing. Replaying every transition of
`data/leaf_lab/baseline.json` against the Ruling Index (2026-08-01) found three re-captures absorbing
an `OK → MISS`, five flips in total, and **every one carried a ruling** — the convention has held by
discipline for its whole history. What the guard removes is the *reliance* on that discipline, across
a six-track parallel build in which every track rebases against these baselines. Expect it never to
fire; a green run is not evidence it works (its unit tests and a doctored-baseline integration run
are).

**When a rebase orphans the SHA, re-stamp — do not re-capture.** Four of the twelve committed
re-captures moved nothing but `git_rev`. Going through `capture` for that means re-reading the build
(the ruling-bearing operation) to achieve a metadata edit:

```bash
python tools/train/leaf_lab.py restamp --baseline data/leaf_lab/baseline.json
```

It rewrites the recorded revision and nothing else, never re-reads the build, and so cannot move a
verdict. `decider_lab.py` carries the same subcommand.

**When it goes red**, the fix is a ruling, not a re-capture. Per frame, decide whether the new
ranking is wrong (fix the code) or right (hold the frame out via its fixture's `frame_key` +
Decision-Claim `owner`, ADR-0072 decision 4 — a reviewable claim in a diff, not a workflow flag).
The gate report uploads as the `leaf-gate-main` artifact.

**A shifted corpus warns, it does not fail.** The verdict is per-frame flips only, but
`CORPUS SHIFTED` means the two captures are no longer comparable — the run emits a `::warning::` so
the re-capture gets owned rather than passing unseen.

**A red caused by a RE-RULING says so.** `correct_is_top` is frozen into each capture and computed
under that capture's own `correct`, so when the human re-rules a frame the diff grades its two
halves under two different oracles and reports `REGRESSED ... OK → MISS` about a build that did not
move. Those flips are printed under their own `⚠️ STALE BASELINE` heading (ADR-0110). The shape,
against the case that motivated the rule — `84071010|0|decision|15`, whose ruling moved to `[0]` and
which the committed baseline has since absorbed, so this is a reconstruction, not a live red:

```
  ⚠️ STALE BASELINE (1) — the baseline predates a re-ruling on these frames. Their OK -> MISS
  below is the REFERENCE moving, not the build; they still gate:
    84071010|0|decision|15  correct [1] -> [0]   rank 1 -> 2
    -> re-capture at a commit carrying the ruling but NOT the change under test, then re-run.
```

**They still gate.** The section labels the red, it does not excuse it — every frame it names is
also listed as `REGRESSED` in the gate block that follows it. A gate getting quieter as a side effect is the
one direction a gate must never move (ADR-0085 Amendment I), and excusing these would give a real
regression somewhere to hide behind a same-commit re-ruling. The redness was always right — the
gate's reference is stale, so it cannot speak; only the *explanation* was wrong.

Measured 91 s over 267 frames (2026-07-28); main was verified green at `7d2a656` before this landed,
so it was not born red.

### Where to re-capture FROM

**A commit that carries the ruling change but none of the code change under test.** This applies to
both baselines and it is the rule the `⚠️ STALE BASELINE` line above names.

Capturing at `HEAD` after a code change bakes that change into its own reference, and the gate can
then never say anything about it — it will compare the change against itself and pass forever, which
is precisely how the old Decision Gate died (`gates.decider_lab_diff`). The ruling-gated `capture`
guard above does **not** catch this: it asks whether every fail-direction frame carries a *ruling*,
not whether the tree carries the *change*. So the capture point stays a human decision, and it is
written here rather than left tribal — it cost ADR-0110's own author one wrong answer first.

The two operations this leaves are both cheap and both already exist: `restamp` when only the
recorded revision is stale, and a ruling (`owner` on the fixture's Decision Claim) when the flip is
real and owned. Re-capture is the last resort, not the first.

### Baseline provenance

`data/leaf_lab/baseline.json` is currently pinned at **`d8ef7a0` (2026-08-02)**, **277 frames**
(247 gradeable — 21 carry a **Voided Ruling**, ADR-0088). Eleven deliberate re-captures and four
metadata-only `restamp`s. Each **capture** was taken only with **zero unruled `OK → MISS`**
outstanding — the ADR-0072 decision 2 precondition, *"only when a swap's flips have been ruled"*,
verified across the whole history by the full-history replay described above and, since Issue #259,
enforced by `capture` itself:

| capture | rev | absorbed | why |
|---|---|---|---|
| 2026-07-28 | `38ca76f` | 6 × `MISS → OK`, 3 × `OK → MISS` | move off the long-stale `81eac82` pin (details below) |
| 2026-07-29 | `fa86dcb` | 1 × `MISS → OK` (`85046350\|0\|decision\|21`) | the user re-ruling of that frame's `correct` (`[2] → [1]`) |
| 2026-07-29 | `e4c46ca` | 1 × `MISS → OK` (`82752604\|0\|decision\|88`) | rebase onto `96da320`; the gain is **main's** (Issue #172's `ENERGY_RECOVER` work), absorbed so it is protected |
| 2026-07-30 | `ac5b5b9` | **corpus 276 → 277** (`85709280\|1\|match\|` enters) + 1 × `OK → MISS` (`84071010\|0\|decision\|15`) which is a **Ruling Move, not a regression**: `correct [1] → [0]` | Issue #197's code-review pass. This is the exact frame the `⚠️ STALE BASELINE` reconstruction above names — *"whose ruling moved to `[0]` and which the committed baseline has since absorbed"* — and **this row is where it was absorbed**. Backfilled 2026-08-03 (Issue #339): a plain `git log -- data/leaf_lab/baseline.json` stops at the commit that introduced the path and hides this movement; `--full-history` shows it |
| 2026-07-31 | `e834272` | **19 frames VOIDED out of the rates** + 1 × `MISS → OK` (`83686860\|1\|decision\|13`) + 1 × ruled `OK → MISS` (`86091435\|0\|decision\|35`, owner `#165`) | Issue #239: a **Voided Ruling** leaves the agree rate. The two flips are **main's**, not this issue's — the baseline was stale by 32 rows of `values` drift, the `OK → MISS` was already held out, and zero unruled `OK → MISS` were outstanding |
| 2026-07-31 | `e138881` | **nothing — a field relabel (`graded` → `gradeable`) + `git_rev`, zero row changes** | the code review settled one word for one concept across both labs (Issue #239) |
| 2026-07-31 | `ff05403` | **1 more frame VOIDED (`86091435\|0\|turn\|14`), and it was an `OK`; zero unruled `OK → MISS`** | Issue #250: the same repaired refutation as the Decision Gate's last row. `leaf_correct 183/249 → 182/248`, voided `19 → 20`, rate 73.49% → **73.39%**. The leaf did not get worse — a frame it was scoring correctly is no longer a frame a human stands behind, so it stops counting. This is the honest half of the pair: one repair, one rate up, one rate down |
| 2026-07-31 | `31b1c28` | **nothing — `git_rev` only, zero row changes** | Issue #250: rebasing onto `main` (Issue #243's PR #252, plus an ADR renumber) orphaned the capture's SHA. Re-measured against the new base first: **zero** row changes, so #243's corpus-reader refactor is confirmed behaviour-preserving for this instrument as its PR claimed |
| 2026-07-31 | `aceb433` | **49 rows moved** — ADR-0091 Option Equivalence reaches the leaf: `top_tie` collapses on 44 frames, `class_asymmetry` appears on 4, `correct_is_unique_top` moves on 5, and **1 frame UN-VOIDED** (`86091435\|0\|turn\|14`). `gradeable 248 → 249`, voided `20 → 19`, `leaf_correct 182 → 183`, `avg_top_tie 3.012 → 2.751` | Issue #247 (Option Equivalence, ADR-0091). **This row read "nothing — zero row changes" until 2026-08-03 and that was false** — the commit's numstat is 108/61. Corrected under Issue #339 by re-measuring the two captures against each other, not by re-reading the commit subject |
| 2026-07-31 | `a8da62d` | **1 row moved** — `86091435\|0\|turn\|14` re-VOIDED, the frame `aceb433` had just un-voided. `gradeable 249 → 248`, voided `19 → 20`, `leaf_correct 183 → 182`. numstat 9/8 | Issue #247: the rebase moved the base again after the ADR renumber. **Also read "nothing — zero row changes" until 2026-08-03, also false** — and this is the very commit ADR-0094's first draft reasoned wrongly about, so the failure that ADR exists to prevent had been sitting inside this table. Neither this nor `aceb433` is a `restamp` case after all: the subcommand did not exist yet so both went through `capture`, but both moved rows, so neither was metadata-only (Issue #259, Issue #339) |
| 2026-08-02 | `f47a3ef` | **21 rows moved**: 2 × ruled `OK → MISS` (`85045840\|0\|decision\|10`, `85045840\|0\|decision\|12`) + 1 × `MISS → OK` (`86091435\|0\|decision\|35`) + **1 more frame VOIDED** (`86089120\|0\|decision\|14`) + `class_asymmetry 4 → 0`. `gradeable 248 → 247`, voided `20 → 21`, `leaf_correct 182 → 180` | Issue #261 wave-2 ruling, items 2e + 2h — **user verdict 2026-08-02: ACCEPT**. Both `OK → MISS` frames carry a `fixed` disposition in `data/corrections/reviewed.json`, which is **not** in `VOIDING_DISPOSITIONS` (`refuted`, `transposition`), so both still gate; the capture went through **`guarded_capture`**, so ADR-0094's precondition was enforced rather than asserted. The fourth movement is invisible to an `OK`/`MISS`-only reading and is what actually drives the three rate figures: `86089120-14` was ruled a **`transposition`**, which voids. `class_asymmetry 4 → 0` is the ADR-0103 tie-break landing |
| 2026-08-02 | `deec14a` | **nothing — `git_rev` only, zero row changes** | `restamp` after the rebase orphaned the capture's SHA (Issue #261) |
| 2026-08-02 | `36c736d` | **nothing — `git_rev` only, zero row changes** | `restamp` after the item-2d rebase (Issue #261) |
| 2026-08-02 | `beae831` | **nothing — `git_rev` only, zero row changes** | `restamp` after the second rebase (Issue #261) |
| 2026-08-02 | `d8ef7a0` | **nothing — `git_rev` only, zero row changes** | `restamp` after the commit re-author (Issue #261). **Mind the collision:** this is the revision recorded *inside* the file, written by commit `4e03c4d`; the commit whose SHA is `d8ef7a0` is the previous row, which recorded `beae831`. The `rev` column is always the captured-at revision, never the committing SHA |

**Two conventions this table follows**, stated because the two gate tables used to disagree about
them and a reader could not tell which was the rule (Issue #339):

1. **The `rev` column is the revision the capture was taken AT** — the `git_rev` written inside
   `baseline.json` — not the SHA of the commit that wrote the file. The two are almost never equal.
2. **A `restamp` gets its own row.** It is *not* folded into the preceding capture's row with that
   row's `rev` rewritten. Folding edits a historical row, and a historical row is a ruling record;
   appending one is the only operation that adds information without destroying any. This costs the
   four near-identical rows above and is worth it — `tests/test_baseline_provenance.py` relies on it
   to check that the pinned revision has a row at all.

`38ca76f`, `fa86dcb` and `e4c46ca` are older than this table's ability to check itself: `38ca76f` and
`fa86dcb` name capture points that **no reachable commit ever recorded** — rebases rewrote them away
before the work reached `main`, and `git log -1` cannot resolve either today. `e4c46ca` *is*
recoverable, but only with `git log --full-history`, because the file entered `main`'s first-parent
history through merge `ab55ff6` (PR #218). Their `absorbed` columns are therefore the one part of
this table that cannot be re-measured; every row from `ac5b5b9` down can be, and was, on 2026-08-03.

`e4c46ca` absorbs an improvement its branch did not produce. That is deliberate and follows the
same rule as the others — an un-baselined `OK` is unprotected, since a later regression back to
`MISS` would compare `MISS → MISS` and pass silently. Absorbing an *improvement* needs no ruling;
only an `OK → MISS` does, and there were none.

`fa86dcb` is the smaller story: re-ruling `85046350-21`'s `correct` to the Active Dreepy changed
what `leaf_lab` scores that frame against, so its verdict became `OK`. Aggregates moved with it —
shared-top 191 → 192, SOLE-top 35 → 36. Note what that is and is not: the leaf did not improve, the
**label** moved to match what the leaf already preferred. Baselining it protects the frame, since an
un-baselined `OK` would let a later regression back to `MISS` pass as a silent `MISS → MISS`.

`38ca76f`, the first re-capture, and its reasoning follow.

Why re-capture rather than leave it: six frames had improved `MISS → OK` since `81eac82`, and an
improvement is **not protected until it is baselined** — with the old pin still recording them as
`MISS`, a change undoing those wins would have compared `MISS → MISS`, produced no flip, and passed
**silently**. Re-capturing makes them the floor.

What it absorbed, recorded here because the gate will no longer re-report it. These three were
`correct_is_top=True` under `81eac82` and are `MISS` in the new capture, so they stop appearing in
the diff entirely (a `MISS → MISS` is not a flip):

| frame | rank drift | owner |
|---|---|---|
| `85163634\|1\|decision\|41` | 1 → 2 | #143 |
| `85164605\|1\|decision\|41` | 1 → 2 | #145 |
| `86091435\|0\|decision\|13` | 1 → 4 | #189 |

This is the real cost of the re-capture and it is in tension with ADR-0072 decision 4's reason for
the always-visible `HELD OUT` section — *"a frame broken for three phases must not become scenery."*
They remain owned by their issues and held out in the fixture ledger, and the pre-capture values stay
in this file's git history, but they are no longer surfaced on every run. If that visibility matters
more than protecting the six improvements, the re-capture is the thing to revert.

Aggregates moved both ways and do **not** gate (ADR-0072 decision 2): shared-top 188 → 191,
SOLE-top 36 → 35.

## Main watchdog: the Decision Gate

[`decider-gate-main.yml`](../.github/workflows/decider-gate-main.yml) runs
`tools/train/decider_lab.py diff --baseline data/decider_lab/baseline.json` on **every push to
`main`** and fails the run on any unruled `REGRESSION` — a frame whose DECISION moved away from the
human's ruling. It is ADR-0072's Decision Gate, as rebuilt by ADR-0085 Amendment I.

**Why it exists,** beyond the argument the leaf watchdog already makes. The Decision Gate was not
merely unwatched on main, it was **vacuous**. ADR-0072 defined it as *"the phase's
`probes/*_decider_sweep.py`"*, each comparing the shipped agent against its own kill-switch OFF —
correct at the swap, when OFF *was* the incumbent rung pile, and meaningless the moment each phase
deleted that pile. With no rungs left, OFF is an empty scorer whose argmax falls to option index, so
all four sweeps could only ever report `FIX`. They had been reporting `PASS` in that state for weeks.
Amendment I rebuilt the gate against a recorded baseline; this job is what stops the rebuilt one from
going unwatched the way the original did.

**Why both watchdogs.** They ask different questions, and the decision-level one is what a ladder
actually sees: the leaf lab asks *"does the leaf still RANK the human's option top?"*, this asks
*"does the agent still PLAY it?"* — end-to-end through the real Pilot, including the planner and
tiebreaks the leaf ranking never reaches.

**It is the cheaper of the two,** which was not the expectation. The rebuild's hand-off argued this
gate "replays 332 frames through a full Pilot and is materially slower than the leaf diff, so measure
the runtime before proposing it." Measured back-to-back on one box (2026-07-30, py3.12):

| gate | frames | wall |
|---|---|---|
| `decider_lab diff` | 332 | **31.6 s** |
| `leaf_lab diff` | 267 | 71.0 s |

~2.2× **faster** than the gate that already had a watchdog. The objection was a guess and the
measurement retired it.

Issue #241 widened the corpus to **372** frames (and the leaf lab's to 268), which scales the
decider figure to roughly 35 s on the same box. The ordering is unchanged and the margin is still
wide, so the conclusion above stands — but the numbers in the table are the 2026-07-30 measurement
over the pre-widening corpus, not a claim about today's.

**It never writes the baseline**, for exactly the reason the leaf watchdog doesn't: auto-recapture on
merge would redefine the "before" picture to whatever just landed, so every regression would bless
itself and the job would pass forever by construction — the same shape the old sweeps went vacuous
in. Re-capture is deliberate:

```bash
python tools/train/decider_lab.py capture --out data/decider_lab/baseline.json
```

and only after the flips it would absorb have been **ruled** with the user.

**When it goes red**, the fix is a ruling, not a re-capture — per frame, decide whether the new
decision is wrong (fix the code) or right (hold the frame out via its fixture's `frame_key` +
Decision-Claim `owner`). One ruling holds a frame out of **both** gates: `decider_lab` keys through
the same `frame_key_of` the leaf lab uses, deliberately, so the two cannot drift. The report uploads
as the `decider-gate-main` artifact.

**A shifted corpus warns, it does not fail** — same rule as the leaf gate. `decider_lab` prints
`corpus shape moved` with added/removed counts and the run emits a `::warning::`.

**What a green run does not mean.** It means nothing regressed against the last blessed build. It
does **not** mean the agent is right: the baseline records every frame it captured as the reference,
including the **98** where the agent contradicts a human ruling that still stands. (It was 101 over a
332-frame corpus, and the figure is now taken over the **gradeable** set — the 25 **Voided Rulings**
are neither agreement nor disagreement, ADR-0088.) Those are ranked in
[`docs/plans/decider-disagreement-triage.md`](plans/decider-disagreement-triage.md) and owned by the
correction rounds (Issue #146), not by this job.

### Baseline provenance

`data/decider_lab/baseline.json` is currently pinned at **`b3d6421` (2026-08-02)**, **372 frames**
(345 gradeable — 26 carry a **Voided Ruling**, ADR-0088). Thirteen movements — eleven captures and
two `git_rev`-only re-stamps — and every one now has a row. It follows the same two conventions the
Discrimination Gate's table states above; until 2026-08-03 it followed neither, which is how it came
to look current while two captures had no row at all (Issue #339).

| capture | rev | absorbed | why |
|---|---|---|---|
| 2026-07-30 | `6328ab7` | — (first capture) | the instrument's own build (ADR-0085 Amendment I) |
| 2026-07-30 | `e50735a` | **nothing — zero row changes** | move off a feature-branch commit onto `main`, + Amendment J's agree predicate |
| 2026-07-31 | *(relabel only)* | **nothing — zero row changes** | re-key 332 rows to the Correction's real identity; 163 keys were wrong (Issue #241) |
| 2026-07-31 | *(pre-rebase)* | **2 ruled `chosen` moves + 1 Ruling Move** | the corpus widened 332 → 372 (Issue #241) |
| 2026-07-31 | `7d0a97f` | **nothing — `git_rev` only, zero row changes** | rebase onto `main` orphaned the capture's SHA (Issue #241) |
| 2026-07-31 | `e138881` | **nothing — `git_rev` only, zero row changes** | re-captured beside its sibling after the code review (Issue #239) |
| 2026-07-31 | `e834272` | **25 frames VOIDED out of the rate; zero `chosen` moves, zero Ruling Moves** | Issue #239: a ruling the human took back can no longer grade, so it leaves the denominator and stops gating. Agree `253/371 → 248/346` — **5 of the 25 had been scored as agreements**, so this is not a one-way flatter of the number |
| 2026-07-31 | `ff05403` | **1 more frame VOIDED (`86091435\|0\|turn\|14`); zero `chosen` moves, zero Ruling Moves** | Issue #250: a **refutation that had been ruling on nothing** since 2026-07-19 finally reaches its record. Agree `248/346 → 248/345`, voided `25 → 26`. The frame was a **disagreement**, so the rate rises 71.68% → 71.88% — read that as the repair working, not the metric being flattered; see the sibling entry, where the same ruling costs the Leaf Gate an `OK` |
| 2026-07-31 | `31b1c28` | **nothing — `git_rev` only, zero row changes** | Issue #250: same rebase as the sibling entry. Re-measured before re-capturing — `248/345` unchanged, 0 picks moved, 0 Ruling Moves |
| 2026-07-31 | `4fcca7d` | **102 rows moved**: the `equiv` field enters the schema on 101 rows, and **2 frames UN-VOIDED** (`81905522\|0\|decision\|75`, `86091435\|0\|turn\|14`). **Zero `chosen` moves, zero Ruling Moves.** Agree `248/345 → 250/347`, voided `26 → 24` | Issue #247 (Option Equivalence, ADR-0091) — the sibling landing of the leaf's `aceb433` row. Both un-voidings are the equivalence collapse making a previously ungradeable ruling gradeable again; no decision moved. Backfilled 2026-08-03 (Issue #339) |
| 2026-07-31 | `a8da62d` | **1 row moved** — `86091435\|0\|turn\|14` re-VOIDED. Agree `250/347 → 250/346`, voided `24 → 25` | Issue #247: the rebase moved the base again after the ADR renumber — the same commit as the leaf's `a8da62d` row, and it moves the same one frame in both labs. Backfilled 2026-08-03 (Issue #339) |
| 2026-08-02 | `1c90fcc` | **11 `chosen` moves — 1 ruled REGRESSION, 5 FIX, 2 NEUTRAL, 3 non-reported; plus the 2 standing HELD-OUT regressions** — and **1 more frame VOIDED** (`86089120\|0\|decision\|14`, ruled a `transposition`). Agree `250/346 → 251/345`, voided `25 → 26` | Issue #261 item 2f, at the **user ruling** on `82225643\|1\|decision\|12` (`fixed`, non-voiding — the ADR-0095 boundary orders the dig ahead of the Hammer across two actions of one turn). **What else it absorbed is named rather than left to the `HELD OUT` block**, because a re-capture takes the whole file and this one silently baselines two frames that were regressions under a *prior* ruling: `83117367\|0\|decision\|34` (owner Issue #262) and `83661649\|0\|decision\|30` (owner Issue #272) now read as the baseline rather than as held-out regressions. Both owners stand and their fixtures keep their `owner` field, so deleting it still returns each to gating — but the comparison they return to is this file, not the pre-item-2f one. Three corrections on 2026-08-03 (Issue #339), each re-measured from the two captures: the frame is seat **1**, not seat 0; the agree figures were `249/345 → 251/345` and the measured pair is `250/346 → 251/345`; and the claim that the Leaf Gate reports `MISS → OK` on this frame is false — its `correct_is_top` is `False` in **both** leaf captures, so the leaf reports no flip on it at all. The voided frame is the same one the leaf's `f47a3ef` row records |
| 2026-08-02 | `b3d6421` | **nothing — `git_rev` only, zero row changes** | `restamp` after the rebase onto `main`. Split out of the row above on 2026-08-03 (Issue #339): it had been folded into that row with that row's `rev` rewritten to `b3d6421`, which is the convention this table now rejects — see the Discrimination Gate section's convention 2. Folding is why this table looked current while two movements above had no row at all |

The 2026-07-31 pair is the shape ADR-0087 decision 5 prescribes, and the reason it is two
entries rather than one. The Decision Gate's keys had been built by hand, reading `seat` off a
snapshot with no `seat` field, so only **169 of 372** frames were named correctly and four standing
Held-out Ledger rulings could not reach the gate at all. Re-keying and widening in one step would
have produced `+372 / −332` — a diff comparing **nothing**, at exactly the commit that most needed
comparing. Split, the relabel is provably a relabel (163 changed lines, every one a `"key"` line, no
Pilot run) and the widening then reads **`added: 40, removed: 0`**.

What the second entry absorbed, each ruled before the file moved:

- `86090147|0|decision|22` — `chosen [4] → [6]`, **NEUTRAL** (the human ruled `[7] Retreat`; both
  picks are bench plays, so the corpus does not adjudicate between them).
- `83661652|0|decision|44` — `chosen [2] → [0]`, a **REGRESSION held out to Issue #165**. Worth
  naming rather than letting the `HELD OUT` block absorb it: this is a *new* regression, shielded by
  a ruling made before it existed.
- `85709280|1|match|` — `correct [] → [0]`, a **Ruling Move**, not a decision change at all
  (re-ruled in `b6d7483`, ADR-0081 Amendment D).

Neither `chosen` move is caused by the widening. 24 commits touched `src/` between `e50735a` and
the widening capture (Issue #197's Deploy Marginal build), and `_build_pilot` is uncached, so the
reader's new key ordering cannot move a decision.

`7d0a97f` is the *other* shape of bookkeeping re-capture, and worth distinguishing from
`e50735a`. Rebasing this branch onto `main` rewrote the capture's own commit, leaving `git_rev` naming
a SHA `git show` could no longer resolve — a provenance pointer into nothing. The re-capture moved
**exactly one field** and **zero rows**, verified before committing. `main` had meanwhile changed
`src/common/pilot.py` and `src/common/snipe_relevance.py` (PR #242) and the gate ran silent against
them, so there was nothing to rule.

`e50735a` is the one worth reading, because it is what a *bookkeeping* re-capture looks
like and the contrast is the point. The first pin, `6328ab7`, was a commit on the Issue #188 feature
branch — a reference that could not be reasoned about from `main`. Re-running `capture` at `main`'s
tip changed exactly **two fields**:

- `git_rev`: `6328ab7` → `e50735a`
- `agree`: `220` → `230`

and **not one of the 332 rows**. No decision moved between the two commits, verified by running the
diff before capturing. So there was nothing to rule, which is the precondition ADR-0072 decision 2
sets for a re-capture; had the flip list been non-empty, each flip would have been a conversation
before the file moved.

The `agree` jump is **not** the agent improving — no decision changed. It is ADR-0085 Amendment J
correcting how agreement is *read*: a Correction's `correct` names the card the ruling was about, so
satisfaction is `correct ⊆ chosen`, not `correct == chosen`. Under equality, `DISCARD` scored 1/12
purely because the agent picks `[2, 3]` where the ruling says `[2]`; under satisfaction the same
corpus reads 10/12. Ten of the eleven recovered frames were that vocabulary mismatch.

## Reproduce locally

```bash
pip install -r requirements.txt

# The full suite (what push-to-main runs):
python -m pytest tests/ -q

# With the Scouting coverage gate (what a scouting/common change enforces):
python -m pytest tests/ \
  --cov=src/common/scouting --cov=tools/meta_tracker --cov-report=term-missing

# A selective subset the way CI does — pytest.ini keeps the shared conftest loading:
python -m pytest tests/arena tests/sim -q
```

Consult the mapping table above to see which dirs a given diff would run; the CI decision
itself is reproduced by the `filters:` + *Determine test plan* blocks in `ci.yml`.

## Scope & extending

CI is **tests, plus the two main-watchdog gates above** — the global Doxygen / Sphinx / GitHub Pages
/ PDF steps are still omitted until those toolchains exist in the repo (see `CLAUDE.md`). The
watchdogs are a deliberate, narrow widening of "tests only" (the Discrimination Gate 2026-07-28, the
Decision Gate 2026-07-30): each runs an existing deterministic instrument the repo already owed on
main, not a new toolchain. Neither ever re-captures its baseline — that is what would make them
vacuous, and ADR-0085 Amendment I is the record of a gate that went vacuous exactly that way.

One thing CI **cannot** gate, by construction: `tests/test_import_hygiene.py` exists because a
`from tests.<subdir>._helper import ...` resolves on a *clean* runner and raises
`ModuleNotFoundError` on a dirtier dev box, where an installed distribution (`kaleido`) ships its own
top-level `tests` package that outranks this repo's PEP 420 namespace one. The failure needs a
dirtier environment than CI's, so a green CI was never evidence — the guard is the substitute, which
is why a selective run appends it unconditionally. Its scan is driven by `git ls-files`, not a
filesystem walk: an earlier `REPO.rglob("*.py")` reached `.venv/` and the sibling checkouts under
`.claude/worktrees/`, taking 643 s and failing `main` on a *foreign branch's* file.

- **Add a new subsystem?** Add a filter to `.github/filters.yml` and a matching
  `add tests/<area>` line in the *Determine test plan* step of `ci.yml` (plus any
  reverse-dependency dirs). Until you do, changes there fall through to the fail-safe full
  run — correct, just not minimal.
- **Cover more interpreters / OSes?** Extend the `matrix` in `ci.yml`.
- **Run CI on feature branches without a PR?** Broaden `on.push.branches` (pushes always
  run the full suite).
