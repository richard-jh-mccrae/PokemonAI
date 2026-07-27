# Continuous Integration

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
| `tools/sim/**` | `tests/sim`, `tests/arena`, `tests/label`, `tests/submit` | `arena` imports `sim.selfplay`; `label`'s corpus fixture and `submit`'s `check_agent` import sim modules too |
| `tools/submit/**` | `tests/submit`, `tests/sim`, `tests/arena`, `tests/agents`, `tests/blunder`, `tests/label` | verified via the import graph |
| `tools/train/*.py`, `tools/train/blunder/**`, `tools/train/tuner/**` (the `train_wide` filter) | `tests/train`, `tests/tuner`, `tests/blunder`, `tests/value`, `tests/label`, `tests/sim`, `tests/strategy`, `tests/agents` | `tune.py` imports **both** `train.blunder.*` and `train.tuner.*` at module level and is the shared pilot-builder ~20 test files across those dirs import directly (see `conftest.py`'s `ms_pilot` fixture) — so a blunder or tuner change rides this one broad blast radius |
| `tools/train/value/**` | `tests/value`, `tests/label`, `tests/sim` | genuine leaf — narrower than `train_wide` |
| `tools/train/label/**` | `tests/label` | genuine leaf, nothing else imports it |
| `tools/train/probes/**` | `tests/train` | genuine leaf (exercised by `tests/train/test_gates.py`) |
| `tools/meta_tracker/**`, root card/meta tool scripts | `tests/meta_tracker`, `tests/cards`, `tests/agents`, `tests/arena`, `tests/blunder`, `tests/label`, `tests/scouting`, `tests/sim`, `tests/submit`, `tests/train` | `cards`/`archetype`/`parse` are imported widely, but **not** by `tuner`, `strategy`, `value`, or `parity` — verified via the import graph (a real narrowing; the old mapping also under-counted `agents`/`label`/`scouting`, a gap this fixes) |
| `src/common/cards.py`, `src/common/effects.py` (the `cards` filter) | `tests/cards` (plus `common_agent_core`'s broad set, since these two files are also in that glob) | `test_cards.py` imports `common.cards` directly; the rest of `tests/cards` exercises `tools/meta_tracker`'s independent card-parsing twin, already covered above |
| `src/cgpy/**`, `tests/parity/**`, `tests/fixtures/parity/**`, `data/engine/coverage.json` | `tests/parity` | The ADR-0050/59 pure-Python engine twin is self-contained — nothing else imports `src/cgpy` at runtime, so its heavy trace-replay gate runs *only* when cgpy files change (and an unrelated PR never pays for it) |
| shared test infra (`tests/conftest.py`, `tests/*_helpers.py`, `tests/fixtures/**` except `tests/fixtures/parity/**`), `requirements.txt`, `.coveragerc`, `pytest.ini`, `.github/workflows/**`, `data/**` except `data/engine/coverage.json`, root card-builder scripts | **full suite** | Can break anything |
| a single `tests/<area>/**` file with no matching source change | just `tests/<area>` | A pure test-file edit touches no source, so it stays narrow instead of paying for a broader filter's reverse-dependency add-list |
| docs / any `*.md` | **nothing** (job passes green) | No runtime surface |
| anything unmatched | **full suite** | A new top-level area is never silently skipped |

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

CI is **tests only** — the global Doxygen / Sphinx / GitHub Pages / PDF steps are omitted
until those toolchains exist in the repo (see `CLAUDE.md`).

- **Add a new subsystem?** Add a filter to `.github/filters.yml` and a matching
  `add tests/<area>` line in the *Determine test plan* step of `ci.yml` (plus any
  reverse-dependency dirs). Until you do, changes there fall through to the fail-safe full
  run — correct, just not minimal.
- **Cover more interpreters / OSes?** Extend the `matrix` in `ci.yml`.
- **Run CI on feature branches without a PR?** Broaden `on.push.branches` (pushes always
  run the full suite).
