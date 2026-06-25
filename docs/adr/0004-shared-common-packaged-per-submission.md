# Shared `common/` + `cg/`, assembled into a self-contained submission at package time

**Context.** A submission is a single self-contained directory (`main.py` + any sibling
modules like `strategy.py` + `deck.csv` + the vendored `cg/` engine + the deck-agnostic
code). But the deck-agnostic code (`common/`, including Scouting) and the engine (`cg/`)
should be shared across *all* agent builds, not copied into and diverging per agent.

**Decision.** Lay the repo out with shared top-level packages and thin per-agent dirs:

```
src/
  common/      # shared deck-agnostic package — import as `common`
  cg/          # shared vendored engine — import as `cg` (do not edit)
  agents/<name>/{*.py, deck.csv}   # deck-specific only (main.py + e.g. strategy.py)
```

`common` and `cg` stay **top-level packages in both layouts**, so imports
(`from common.scouting import Scout`, `import cg`) are identical in dev and in the
zip — only `sys.path` differs (dev: `src/`; submission: the agent dir,
which is the CWD and contains copies of `common/` + `cg/`). `cg` already proves this
works on the grader today.

`tools/package_agent.py <name>` assembles a submission: it copies the agent's `*.py`
(main.py + sibling modules such as `strategy.py`) + `deck.csv` + shared `common/` +
`cg/` + the compiled `common/scouting/artifact.json` into `dist/<name>/` and zips it to
`dist/<name>_<YYYYMMDD>_<githash>.zip`. The staged `dist/<name>/` *is* the exact
shipped bundle; the stamp names the deploy artifact by build date + commit (`-dirty` when
the work tree has uncommitted changes), so each date+commit yields one artifact (a same-day
rebuild of the same commit overwrites). `--no-stamp` falls back to a stable `dist/<name>.zip`.
The in-bundle `version_control.md` still records the full date **and** time of the build.

**Consequences.**
- One source of truth for `common/` and `cg/`; no per-agent drift.
- All of an agent's top-level `*.py` ship (so `from strategy import …` works in the zip),
  plus its human-readable `deck.txt` (when present) and a generated `version_control.md`
  build card (agent + date + time + git hash) for provenance.
- Imports are unchanged between dev, the local self-play harness, and the grader.
- A build step is required to produce a submittable zip (`dist/` is gitignored).
- Rejected: nesting `common/` per agent (duplication/drift); symlinks (fragile on
  Windows / in zips); pip-install or git submodule (heavier than copy-at-package-time
  for a single-directory submission).
