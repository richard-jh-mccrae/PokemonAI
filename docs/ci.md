# Continuous integration

`.github/workflows/ci.yml` first applies `.github/filters.yml`, then runs only the affected
independent jobs in parallel: per-tool tests, correction contracts, source, cgpy, documentation, and
developed-agent mirrors. Unknown non-documentation paths fail closed to all jobs; pushes to `main`
and manual dispatches run all jobs.

Correction contracts also run whenever `src/common/` or any `src/agents/` implementation changes.

Tool tests are selected independently: arena, meta tracker, simulator, and submission. A PR runs a
tool suite only when that tool's implementation, adapter, or tests changed. Shared test
infrastructure runs every tool suite; CI configuration changes do not. Each selected suite has a
twelve-minute job budget and reports the twenty slowest tests.

The agent-skills synchronisation check is selected separately when its tool, canonical skills,
Codex adapters, or its test changes.

Each developed agent gets an entry in the mirror matrix. The current entry, `mega_starmie`, plays
five seat-balanced mirrors in parallel inside one CI job. Each Match extracts the same exact artifact
into an isolated directory, runs native `cg`, and has an independent ten-minute timeout. Every result
is printed even if another match fails, followed by total/min/max/average and parallel batch wall
time.

Run the same primary check locally with:

```bash
python -m pytest tests -q
python tools/sim/mirror_gate.py mega_starmie --games 5 --workers 5 --max-match-seconds 600
```

The former decider, leaf, tuner, composer, and value-stack gates were deleted with those systems.
