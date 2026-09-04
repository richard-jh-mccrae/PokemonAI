# Simulation and agent checks

These tools exercise packaged agents through the competition environment and native engine.

- `check_agent.py`: deck legality, playability, and deployability.
- `kaggle_cabt.py`: limits Kaggle's eager environment discovery to the CABT competition
  environment; unrelated native libraries such as OpenSpiel never load.
- `battle.py`: generic local head-to-heads and the persistent process-isolated agent server.
- `correction_run.py`: owns repeatable focal-agent evidence batches for human Ledger review.
- `strategy_bench.py`: timing diagnostics only; it is not a Correction Run or corpus builder.
- `artifacts.py`: legacy replay tags and inspector-log compatibility for Arena/bench artifacts.
- `strategy_bench.py`'s `--no-emit` runs the contestants
  with `AGENT_NO_TELEMETRY=1`; the harness-side `round_trip_seconds` is measured either way,
  so the same run with and without the flag prices the telemetry path.
- `audit_attacks.py`, `generate_attack_overrides.py`: measured attack facts.
- `record.py`, `result.py`, `paired_ab.py`: replay and experiment records.

Agents loaded here all enter `common.runtime.AgentRuntime`. Replays retain per-frame observations so
offline evaluators can reconstruct decisions from each player's legal view.
