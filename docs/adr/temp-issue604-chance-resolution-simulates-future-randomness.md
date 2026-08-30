# ADR-TEMP-604 — Chance resolution simulates future randomness

An Experiment Snapshot retains exact hidden current state, but search must not treat stored random
continuation or an unknown future deck order as decision evidence. Chance Expansion therefore
enumerates or key-samples future outcomes on engine forks, exposing only legal observations; full
information-set marginalization remains separate work.
