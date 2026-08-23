# ADR-0184 — The Episode owner finalizes Ledger outcomes

The Agent Runtime emits Decision Records but never receives the engine's terminal frame. The Episode
owner therefore appends exactly one Outcome Record after play and links every emitted Decision Record.
Inferring the result from the final chosen successor was rejected because search is not engine truth.
