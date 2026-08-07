# Eval harness (WP2)

Offline G2 instrument: a **candidate** vs a **baseline** over a shared opponent field, paired per
matchup×seat so the raw deck matchup cancels and only the candidate−baseline effect remains. Emits
the C3 report (`docs/plans/ml/ml-training-contracts.md`) the adoption gate reads. Design:
`docs/archive/plans/ml/ml-training-design-s2b.md`.

## Run

```bash
python tools/sim/eval_run.py <candidate> <baseline> [--opponents ...] [--preset quick|default|fine]
```

`<candidate>`/`<baseline>` = an agent name (working tree) or a build id (ledger zip). Opponents
default to all working-tree agents.

```bash
# learned-weights build vs the current agent, default power (3% detectable delta)
python tools/sim/eval_run.py mega_starmie 42 --preset default
```

| flag | default | meaning |
|---|---|---|
| `--preset` | `default` | detectable win-delta: `quick` 5% · `default` 3% · `fine` 2% |
| `--per-cell` | from preset | games per arm per opponent (overrides the preset) |
| `--h2h` | 200 | informational head-to-head games (never enters the verdict) |
| `--checkpoints` | — | build ids **added** to the submitted-build regression pool |
| `--no-checkpoints` | off | skip the checkpoint pool entirely |
| `--max-games` | — | hard game cap (disk safety valve) |
| `--max-gb` | — | hard film-bytes cap in GB |
| `--resume <run_id>` | — | continue a crashed run (cell-granular) |

Contestant specs accept `name@overlay.json` — the overlay (e.g. weights-on config) is applied to
that arm and recorded in the report's `config` descriptor.

## Output

`reports/eval/<run_id>/` — `manifest.json` (resumable, corpus-pattern), gzip films, and
`report.json` (C3). The CLI prints the win-delta, its 95% CI, and the `PASS`/`FAIL`/`INCONCLUSIVE`
verdict; a capped/partial run is tagged `[CAPPED]` and can never PASS. Resume a crashed run with
`--resume <run_id>` (the manifest flushes after every cell, so at most one cell is redone).
Checkpoint regressions cap a pass at inconclusive and name the culprit.

## TODO

- **Generate a corpus, then land the corpus-gated pieces.** The harness runs today on live games,
  but two things wait on a game corpus (`python tools/sim/corpus.py`): (1) the duplicate-**position**
  spike's variance-reduction *verdict* — the driver (`eval_spike.py`) works, but whether paired
  position-replay actually cuts variance enough to ship as an auxiliary mode must be *measured* over
  a pool of captured openings; record the verdict in the build-plan ledger. (2) the **AIVAT**
  implementation (`eval_aivat.py`, null seam today) — fills after WP1's value net passes G1.
