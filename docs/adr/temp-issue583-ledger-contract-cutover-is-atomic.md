# ADR-TEMP-583 — The Ledger contract cutover is atomic

The normal live path switches atomically to Decision Coordinator and the Ledger adapters; the old
decider survives only as an offline Decision Parity oracle, never a production selector or shadow
authority. #583 proves forced and degraded contract capability, while #584 owns complete runtime
routing and bypass removal; every intentional parity flip requires an ADR-linked ruling.
