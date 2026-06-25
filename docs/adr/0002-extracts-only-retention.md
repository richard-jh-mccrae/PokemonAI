# ADR-0002: Extracts-only retention — discard raw replays

Status: accepted

The daily job parses each replay in memory, writes a compact per-Episode record
(both 60-card decklists, archetypes, winner, the sampled submission's
rating + maturity, and band) to SQLite, then **deletes the raw replay**. Raw
replays compress ~33× (≈250 MB/day if kept), so this is a deliberate choice for
minimal footprint, not a forced one.

## Consequence (important, hard to reverse)

Kaggle rotates Episodes off over time. Once a raw replay is discarded, **any
signal not captured in the extract is gone forever** — in particular the
44-frame play-by-play. That means **no future RL / imitation / behaviour-cloning**
from this data and no in-game metrics (who attacked, mulligans, energy curves).

Decklists *are* retained, so archetype/main-line logic can be recomputed later
without re-scraping. If replay-level training data becomes desirable, switch to
gzipped-raw retention **before** the Episodes of interest rotate out — see the
"Retention" option discussion in CONTEXT.md history.

## Amendment (blunder inspector, [ADR-0009](0009-training-methodology.md) / ADR-0015)

The daily pipeline still discards. Replays selected for **blunder review are deliberately
retained** as a separate review set, and each **Correction** embeds a self-contained Decision
snapshot — so per-decision imitation labels survive without keeping the daily firehose.
