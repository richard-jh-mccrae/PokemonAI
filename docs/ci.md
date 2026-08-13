# Continuous integration

`.github/workflows/ci.yml` first applies `.github/filters.yml`, then runs only the affected
independent jobs in parallel: tools, correction contracts, source, cgpy, documentation, and
developed-agent mirrors. Unknown non-documentation paths fail closed to all jobs; pushes to `main`
and manual dispatches run all jobs.

Correction contracts also run whenever `src/common/` or any `src/agents/` implementation changes.

Each developed agent gets an entry in the mirror matrix. The current entry, `mega_starmie`, plays
ten seat-balanced mirrors in parallel inside one CI job. Each Match runs in its own process and its
wall time is measured; a crash or any completed Match above five minutes fails the job.

Run the same primary check locally with:

```bash
python -m pytest tests -q
python tools/sim/mirror_gate.py mega_starmie --games 10 --workers 10 --max-match-seconds 300
```

The former decider, leaf, tuner, composer, and value-stack gates were deleted with those systems.
