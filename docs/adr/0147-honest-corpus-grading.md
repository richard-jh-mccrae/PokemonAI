# ADR-0147 — Honest corpus grading: the own-prize anchor and retired rulings

Status: Accepted (2026-08-20); BUILT. Follows ADR-0145.

## Context

The Ledger's training dashboard (`tools/train/ledger_corpus.py`, ADR-0145 step 7) graded under
two biases the live agent does not have.

First, 469 of 471 archived correction frames carry no `own_prizes`. Live, `make_agent` stamps
that anchor from the deck tracker before every decide; without it, `BoardState._deck_counts`
counts the 6 prized cards as still in the deck, while the offline cgpy provider prints the
determinized full truth into every successor (`engine.py` sets `own_prizes` unconditionally;
the native adapter only carries a parent's anchor forward). Every engine-previewed option
therefore paid a phantom deck loss — measured 0.14–0.21 prizes, uniform per frame — that the
pinned-zero End turn and the sampled-hand Refresh path never paid. 81 of 329 misses were
"Ledger chose End turn"; in all 81 every priced alternative was negative.

Second, the sweep never consulted `data/corrections/reviewed.json`: 24 rulings the owner had
already dispositioned (refuted / fixed / covered / deferred) still graded as misses — the
exact drift ADR-0082 exists to make loud, and 8 of them sat on the floor deck.

## Decision

- `common.engine.stamp_own_prizes(observation, decklist)`: when an archived observation lacks
  the anchor, stamp the SAME determinized prize split the provider will honor (via
  `_own_hidden_zones` on the pre-anchor pool). The split is a stand-in — the archive lost the
  real prizes; grading needs root and successors telling one story, not the lost truth.
  `_replay_one` stamps every frame before `runtime.decide` and marks the row
  (`stamped_prizes`).
- The sweep partitions through `reviewed.py:partition_reviewed`. Dispositioned rulings render
  in their own "Retired rulings" section with a per-deck `retired` column; they are never
  graded and never counted as misses.

## Consequences

- Generality floor 16.7% → 32.6% (dragapult 16.7→32.6, lucario 35.7→33.9, starmie 31.1→39.1)
  with zero live-brain changes; "chose End turn" misses 81 → 9. This dashboard is the tuning
  baseline; regressions are measured against it from now on.
- 22 frames "regressed" against the BIASED dashboard: 8 ruled-End frames that had agreed only
  by paralysis, 11 ruled-attack frames where a now-positive develop precedes the attack
  (spend-then-end plays non-enders first) — real tuning material, not scoreboard artifacts.
- The stamped split is deterministic but arbitrary within the unseen pool; prize-aware demand
  (a dead fetch whose target is prized) now grades, at stand-in accuracy.
