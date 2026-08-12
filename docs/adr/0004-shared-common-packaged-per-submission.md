# Shared runtime packages, assembled into a self-contained submission at package time

**Status.** Accepted and BUILT — the repo ships `src/common/`, native `src/cg/`, and thin
`src/agents/<name>/`; `tools/submit/package.py` assembles all runtime
dependencies into the self-contained bundle (also carrying `brief.html`, ADR-0019).

**Context.** A submission is a single self-contained directory (`main.py` + any sibling
modules like `strategy.py` + `deck.csv` + native `cg/` + the deck-agnostic code). But the
deck-agnostic code (`common/`, including Scouting) and authoritative engine (`cg/`)
should be shared across *all* agent builds, not copied into and diverging per agent.

**Decision.** Lay the repo out with shared top-level packages and thin per-agent dirs:

```
src/
  common/      # shared deck-agnostic package — import as `common`
  cg/          # shared vendored engine — import as `cg` (do not edit)
  cgpy/        # offline diagnostics/testing/simulation only; NEVER packaged
  agents/<name>/{*.py, deck.csv}   # deck-specific only (main.py + e.g. strategy.py)
```

The shared packages stay **top-level packages in both layouts**, so imports
(`from common.scouting import Scout`, `import cg`) are identical in dev and in the
zip — only `sys.path` differs (dev: `src/`; submission: the agent dir,
which is the CWD and contains copies of `common/` and `cg/`). `cg` already proves this
works on the grader today.

`tools/submit/package.py <name>` assembles a submission: it copies the agent's `*.py`
(main.py + sibling modules such as `strategy.py`) + `deck.csv` + shared `common/`, `cg/`,
and the compiled `common/scouting/artifact.json` into `dist/<name>/` and zips it to
`dist/<name>_<YYYYMMDD>_<githash>.zip`. The staged `dist/<name>/` *is* the exact
shipped bundle; the stamp names the deploy artifact by build date + commit (`-dirty` when
the work tree has uncommitted changes), so each date+commit yields one artifact (a same-day
rebuild of the same commit overwrites). `--no-stamp` falls back to a stable `dist/<name>.zip`.
The bundle also carries a self-contained `brief.html` (the embedded decision-steering
**Manifest**) — see [ADR-0019](0019-submissions-are-traceable-and-tracked.md).

**Consequences.**
- One source of truth for shipped `common/` and native `cg/`; no per-agent drift. `cgpy/` remains
  source-only for diagnostics, tests, and simulation and is forbidden from Kaggle artifacts.
- The artifact gate scans both ZIP paths and every shipped file's bytes for `cgpy`; either form
  fails the build. Production Bellman transitions use only native `cg.search_begin/search_step`.
- All of an agent's top-level `*.py` ship (so `from strategy import …` works in the zip),
  plus `tuned.json` (when present) and a generated `brief.html` build card whose embedded
  Manifest carries the decklist + provenance (superseding the old `deck.txt`/`version_control.md`,
  ADR-0019).
- Imports are unchanged between dev, the local self-play harness, and the grader.
- A build step is required to produce a submittable zip (`dist/` is gitignored).
- Rejected: nesting `common/` per agent (duplication/drift); symlinks (fragile on
  Windows / in zips); pip-install or git submodule (heavier than copy-at-package-time
  for a single-directory submission).
