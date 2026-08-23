# ADR-0183 — Ledger telemetry is strict, self-contained, and framed

Each Ledger Decision Record carries the legal observation, complete typed Decision Result, effective
configuration, and provenance needed to replay it without another stream record. A strict versioned
codec rejects missing or unknown structure; legacy Bellman records remain diagnostic-only because
their missing alternatives and outcomes cannot be reconstructed. Deterministic compressed frames
with checksums preserve complete large records without truncating candidates or components.

## Offline cost

The accepted format favors independently self-contained records over transport interning. On the
2026-08-23 Windows development machine, a seeded Mega Starmie mirror produced 29 Decisions:
building plus strict validation took 316 ms total, framing took 392 ms total, and uncached framing
had 34.5 ms p95 (48.3 ms max). Exact native-observation replays with telemetry disabled/enabled
measured 13–15% additional offline match time, including final queue drain. These are recorded
benchmarks, not runtime gates; telemetry emission remains asynchronous so a record cannot discard or
replace the already-computed engine choice.
