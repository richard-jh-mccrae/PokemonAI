# Continuous Integration

`.github/workflows/ci.yml` runs the test suite on every push to `main`, every pull
request, and on manual dispatch (`workflow_dispatch`). It is a **2-job matrix**: runners
`ubuntu-latest` **and** `windows-latest`, both on Python **3.12** (the most recent; the dev
box runs 3.11). Both platforms are first-class — dev/build is on Windows, the Kaggle grader
is Linux. Every step runs under `bash` (Git Bash on the Windows runner) so the commands are
identical on both, and `PYTHONUTF8=1` gives Windows the same UTF-8 default as Linux.

## What runs

The **entire** `pytest` suite — it is offline and self-contained on Linux:

- **Native engine** — `src/cg/` ships both `libcg.so` (Linux, x86-64 ELF) and
  `cg.dll` (Windows); `sim.py` picks by `os.name`, so the engine-backed legality/playability
  tests load it on either runner. A dedicated *Verify native engine loads* step prints the
  loaded library path and fails fast with a clear error if it can't load (e.g. a missing
  system lib on Linux).
- **Simulator** — `kaggle-environments` (the `cabt` env) is a pip dependency; the
  playability/deployability tests run real matches in-process, no network.
- **Kaggle CLI** — the `fetch` / `pipeline` tests monkeypatch the CLI, so no Kaggle API
  token or network is needed.

One test skips on a clean checkout: `test_real_limitless_deck_hard_fails_on_absent_card`
needs a real Limitless decklist under `data/` (gitignored), so it `pytest.skip`s when the
file is absent. Result on the runner: **249 passed, 1 skipped**.

## Coverage gate

The run enforces the Scouting coverage gate from `.coveragerc` (`fail_under = 80`, scoped
to `common/scouting/*` + `compile_scouting.py`) — currently ~95%. JUnit XML and
`coverage.xml` upload as build artifacts named `reports-py<version>`.

## Reproduce locally

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
# with the coverage gate (what CI enforces):
python -m pytest tests/ \
  --cov=src/common/scouting --cov=tools/meta_tracker --cov-report=term-missing
```

## Scope & extending

CI is **tests only** — the global Doxygen / Sphinx / GitHub Pages / PDF steps are omitted
until those toolchains exist in the repo (see `CLAUDE.md`). To run CI on feature branches
without opening a PR, broaden `on.push.branches`. To cover more interpreters, add to the
`python-version` matrix.
