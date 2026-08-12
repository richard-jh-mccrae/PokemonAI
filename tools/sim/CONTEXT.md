# Simulation and agent checks

These tools exercise packaged agents through the competition environment and native engine.

- `check_agent.py`: deck legality, playability, and deployability.
- `battle.py`, `selfplay.py`, `corpus.py`: local matches and replay corpora.
- `audit_attacks.py`, `generate_attack_overrides.py`: measured attack facts.
- `record.py`, `result.py`, `paired_ab.py`: replay and experiment records.

Agents loaded here all enter `common.runtime.BellmanRuntime`. Replays retain per-frame observations so
the Bellman correction corpus can re-evaluate decisions offline.
