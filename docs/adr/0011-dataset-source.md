# ADR-0011: Fetch from the daily top-episode dataset; drop the low band

Status: accepted (supersedes the acquisition mechanism of [ADR-0001](0001-data-source.md);
deck-extraction from the `visualize` field still holds)

The pipeline now sources episodes from the **official daily top-episode export**
(`kaggle/pokemon-tcg-ai-battle-episodes-index` → per-day datasets of `<id>.json`
replays) instead of scraping the competition API team-by-team
(`leaderboard → team-submissions → episodes → replay`). Replays are downloaded by
file name, only for episode IDs not already in the store; a fully-ingested day is
marked complete.

Rank **Bands** are now **contiguous percentile tiers over the top 50%** of the
ladder (Elite/High/Mid), banded by the participants' current leaderboard rating
(name→score join). The previous bottom band is dropped — the export is top-rated
by construction and we explicitly want refined decks/agents.

## Why

- The export is curated, stable, and far higher-volume than sampled scraping, and
  removes competition-API rate-limit risk. The replay format is identical, so
  `parse.py` is unchanged.
- Simpler control flow: no team/submission traversal; incremental dedup is just
  "skip episode IDs already stored."

## Consequences / trade-offs

- **Top-skew is intentional**, not a census — the bottom of the ladder is absent.
- Banding via *current* ratings drifts slightly for older episodes, and teams
  missing from the leaderboard become unrankable (dropped).
- Listing a day's ~5k files costs ~25 paged calls; with a small `--cap` the
  listing recurs until the day is complete (we don't persist the full id set).
- The legacy scraping helpers remain in `fetch.py` but are no longer wired into
  `run_daily`.
