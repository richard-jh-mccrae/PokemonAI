# ADR-0196 — Search state separates engine truth from policy view

The Turn Search Environment belongs to cgpy experiments and privately retains exact `GameState`
while policy and value consumers receive only `ObservationState` for the fixed Perspective Seat.
Search State Keys omit random-generator state; Chance Sample Keys identify reproducible randomness,
while Chance Branch Keys and transitions record hidden-safe resolution identities. Issue #603 leaves
the live one-ply Ledger's forced-chain policy unchanged.
