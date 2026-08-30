# ADR-0195 — Replay roots start a new randomness epoch

Native replays can certify observations and full-information frames but cannot expose the native
random-number generator state. A single recorded frame also cannot prove every internal engine
marker needed for an exact counterfactual root.

An exact replay-derived Experiment Root is reconstructed sequentially through verified cgpy replay.
At the selected start-of-turn boundary it begins a recorded cgpy Randomness Epoch; sources that
cannot establish complete engine truth are rejected instead of approximated.

Every compared method receives the same complete state and initial random state. Divergent action
paths may consume randomness differently, so experiments never claim identical native continuation
or identical downstream randomness after policies diverge.
