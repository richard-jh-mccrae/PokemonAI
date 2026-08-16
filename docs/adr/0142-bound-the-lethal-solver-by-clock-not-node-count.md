# ADR-0142: Bound the Lethal Solver by wall clock, not by node count

Status: accepted

## Context

`tools/sim/strategy_bench.py` mirror runs were losing one match in two to
`decision timed out after 10s`, on `main` as well as above it. The Lethal Solver was consuming
**48-54% of all decision time** (383s of 796s, and 431s of 801s, across two arms of a
`mega_lucario` mirror at 10s per decision).

The cause was not the prover's appetite but a lifted clock. `BellmanRuntime.__init__` raised
`terminal.max_seconds` from its 0.25s default to **60s** whenever `AGENT_DECISION_SECONDS` was
pinned, deliberately, so that a replay would stop on node/decision caps rather than on a wall clock
that varies with machine load. The bench pins that variable, so every bench run had an effectively
unbounded prover: it exceeded 3s on 54 of 205 and 53 of 165 decisions, worst case 9.28s of a 10s
budget.

## Decision

**Bound the prover by a wall-clock ceiling that no layer can lift, and leave the node cap alone.**

- `terminal.max_seconds` is **1.2**, and its `maximum` equals its default. `PilotProfile.resolve`
  raises on an out-of-bounds global or authored value and clamps a learned delta, so 1.2 is a
  ceiling against every layer rather than a default any layer can raise.
  `BellmanTurnPlanner` additionally takes `min(epoch_seconds, ...)`, so the prover can never
  outlive its own decision.
- The `terminal.max_seconds` override in `runtime.py` and in `tools/train/strategy_lab.py` is
  **removed**.
- `terminal.max_nodes` **stays at 1024**.

## Evidence

165 recorded `mega_lucario` frames, prover called directly so the measurement is not diluted by the
Bellman search that follows it, with the shipped 1.2s ceiling in place:

| node cap | proofs found | abstentions ending at the node cap | total prover time |
| --- | --- | --- | --- |
| 1024 | 7 | **0 of 158** | 84s (0.51s per frame) |
| 512 | 7 | 10 (6%) | 79s |
| 256 | 7 | 24 (15%) | 81s |
| 128 | 7 | 67 (42%) | 46s |
| 64 | 7 | 83 (53%) | 21s (0.13s per frame) |

Lowering the node cap to 64 saves **0.38s per decision** and converts **53% of refutations into
guesses** — the prover stops on budget rather than establishing that no win exists. No proof was
lost anywhere down to 32 on this sample, but the sample is 8 proofs from one deck across two
matches, and `TerminalProver._state` counts one node per expanded state, so node cost scales with
the width of the legal menu (hand size, Bench slots, attach targets) and not with depth alone. A
16-decision proof — `terminal.max_decisions` is still 16 — on a wide board cannot fit in 64 nodes.
Eight proofs cannot bound that tail, and a node-capped abstention is recorded only as
`reason: "node_cap"`; nothing else marks the answer as unverified.

The clock is what was expensive. With it restored, 1024 costs 0.51s of a 10s decision.

## Consequences

- A pinned clock no longer makes replays node-bound. The 1.2s ceiling is a wall-clock stop, so an
  extremely loaded machine could in principle stop a prover earlier than a quiet one. Accepted:
  before this change the same runs varied by 9 seconds, and `reason` distinguishes `time_cap` from
  `node_cap` in telemetry when it matters.
- Any future request for a longer prover clock now raises rather than silently applying. Changing
  the ceiling means changing `maximum` here, which is a visible edit.
- The earlier claim that the prover's node cap was the cost driver is **withdrawn**: it rested on a
  measurement taken with the clock lifted to 60s, which is not a configuration that ships.
