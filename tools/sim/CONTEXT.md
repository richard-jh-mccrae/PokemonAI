# Simulation and agent checks

These tools exercise packaged agents through the competition environment and native engine.

- `check_agent.py`: deck legality, playability, and deployability.
- `kaggle_cabt.py`: limits Kaggle's eager environment discovery to the CABT competition
  environment; unrelated native libraries such as OpenSpiel never load.
- `battle.py`, `selfplay.py`, `corpus.py`: local matches and replay corpora.
- `strategy_bench.py`: timed matches with per-decision CSV. `--no-emit` runs the contestants
  with `AGENT_NO_TELEMETRY=1`; the harness-side `round_trip_seconds` is measured either way,
  so the same run with and without the flag prices the telemetry path.
- `audit_attacks.py`, `generate_attack_overrides.py`: measured attack facts.
- `record.py`, `result.py`, `paired_ab.py`: replay and experiment records.

Agents loaded here all enter `common.runtime.BellmanRuntime`. Replays retain per-frame observations so
the Bellman correction corpus can re-evaluate decisions offline.
