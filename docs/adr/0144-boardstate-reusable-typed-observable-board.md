# ADR-0144 — BoardState: the observable board as reusable typed pieces

Status: Accepted (2026-08-19); BUILT dark — no production consumer is rewired yet.

## Context

Every search edge rebuilt the whole observation from scratch: one walk flattening the engine's
answer to plain dicts, a second building the sorted canonical copy `DecisionState` stores, a
third feeding the identity hash, plus a fresh Counter pass for remaining-deck arithmetic — for a
board ~95% identical to its parent. Nothing incremental exists on that path; the previous
incremental design (`StateModel`) was deleted whole in #515, and the engine (`src/cg/`,
off-limits) offers no delta API — its output is always a complete reprint.

## Decision

`src/common/board/` is one deep module, `BoardState.root(printout, decklist)` and
`parent.advance(printout)`, its only two doors.

- **Delta source is the engine's own reprints.** `advance` C-compares each piece's new raw
  subtree against the one the parent piece was built from and rebuilds only the unequal pieces.
  Both sides of every comparison are engine output, so drift is impossible by construction;
  `logs` may later *hint* which pieces to check first but never replaces the compare.
- **Two-level granularity.** Coarse pieces per side (active, bench, hand, discard, scalars) plus
  turn / stadium / looking / select / extras; within a rebuilt bench, each in-play body is its
  own node, realigned by engine serial and reused when its raw dict is unchanged.
- **Facts pin at first sight.** A node resolves its card id against ADR-0143's `card_store()`
  once and keeps the record; an id the store lacks pins None. This is the store's first consumer
  outside its own tests.
- **The type is the information boundary.** An opponent's hand contents and any deck order are
  unrepresentable — construction never reads them, even off a full-truth frame — while the
  legally-known channels (`own_prizes`, `known_top`, `attack_locks`) are explicit fields.
- **The lock ledger folds inside the build.** `attack_locks` derives from the parent's ledger
  plus the printout's log delta (a printout carrying its own ledger stays authoritative), so no
  upstream enrichment has to mutate a reprint in place. The deck-tracker channels remain a
  printout contract.
- **`key` is semantic identity**: blake2b over per-piece digests; serials, owner stamps, render
  order of unordered zones, and select menu material (options, deck listing) never enter —
  the same equivalence `common.state` applies to whole observations.
- **`changed` ships from day one**: the set of piece labels differing from the parent, produced
  by the diff for free, so a later value-family reads-registry can subscribe without board rework.
  `deck_counts` already consumes it, reused unless a contributing piece changed.

## Measured

`python -m tools.board_bench --steps 300` (300 synthetic search edges over 301 snapshots, every
edge mutating a piece, warm store, one dev box, load-noisy — re-measure paired before quoting
elsewhere): fresh `root` ~0.19 ms/step, `advance` 0.043–0.047 ms/step across repeats, incumbent
`DecisionState.from_observation` + `plan_key` 0.44–0.46 ms/step (~10x advance),
`advance == root` mismatches 0 of 301 snapshots. The bench exits nonzero on any mismatch.

## Consequences

No consumer is rewired: `DecisionState`, the solver, and the value stack are untouched, so this
ships with zero behavioral delta and needs no kill switch. Value-side reuse (families skipping
unchanged pieces) is deliberately deferred; `changed` is the seam it will consume.
`tests/board/` pins construction, both select dialects, the boundary, piece reuse identity,
advance-equals-root equivalence, and key invariances.
