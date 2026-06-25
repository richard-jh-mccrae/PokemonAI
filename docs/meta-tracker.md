# Meta Tracker

Daily pipeline that pulls match replays from the **official daily top-episode
datasets**, extracts the deck **Meta** per **Rank Band**, and renders a
self-contained HTML dashboard so you can see *which decks you'll be matched
against*. The export is top-rated-skewed by design — we want refined decks/agents,
so the bottom of the ladder is intentionally dropped.

Glossary: [CONTEXT.md](../CONTEXT.md). Key decisions: [ADR-0001](adr/0001-data-source.md)
(decks live in the `visualize` field), [ADR-0002](adr/0002-extracts-only-retention.md)
(extracts-only), [ADR-0011](adr/0011-dataset-source.md) (dataset source + drop low band).

## Data flow

```
episodes-index manifest ──▶ daily dataset slugs (newest first)   [fetch.episodes_index]
     │
     ▼  list <id>.json files; keep ids not already in the store   [fetch.dataset_episode_ids]
  download <id>.json ──▶ replay JSON                              [fetch.download_dataset_episode]
     │     │
     │     ▼  decks from steps[i][0].visualize[*].current.players[*].deck
     │   parse.py ──▶ archetype.py (evolution lines, ≤3 main lines, sub lines)
     │     │
     │     ▼  band via leaderboard name→rating join (bands.py); drop below-range
     ▼     ▼
  discard raw  EpisodeRecord ──▶ SQLite store (dedup by episode_id; days marked complete)
                                        │
                                        ▼
                              dashboard.py ──▶ reports/meta_dashboard.html
```

Incremental: only `<id>.json` files not already in the store are downloaded, and
a fully-ingested day is marked complete so it's skipped on later runs. Every
metric is **per-episode (encounter-weighted)** — see CONTEXT.md → *Play rate*.

## Modules (`tools/meta_tracker/`)

| File | Role |
|---|---|
| `config.py` | bands, download cap, paths, archetype/engine knobs |
| `fetch.py` | Kaggle CLI wrappers (episodes-index manifest, dataset file-listing + per-file download, leaderboard) with retry/backoff/timeout |
| `bands.py` | rating → band (contiguous percentile tiers) |
| `parse.py` | replay JSON → `EpisodeRecord` (keeps both decklists, discards play-by-play) |
| `archetype.py` | evolution-line reconstruction, main/sub split, archetype naming |
| `cards.py` / `cards.json` | card metadata (stage/ex/`evolvesFrom`/damage), portable cache |
| `store.py` | SQLite extract store + episode dedup + dataset-complete state |
| `dashboard.py` | self-contained Plotly HTML (archetype merge + decklists) |
| `run_daily.py` | orchestration |
| `dump_cards.py` | regenerate `cards.json` from the native `cg` engine |

## Run

```bash
# pull new episodes (up to the cap), re-band, rebuild dashboard
# auth via KAGGLE_API_TOKEN or ~/.kaggle/access_token
python tools/run_meta_tracker.py

# smaller pass / one band only
python tools/run_meta_tracker.py --cap 300
python tools/run_meta_tracker.py --bands Elite High

# regenerate the card cache after a pool update
python tools/meta_tracker/dump_cards.py

# tests (uses the gzipped sample replay; no network)
python -m pytest tests/ -q
```

Re-running is safe and incremental — already-ingested episodes are skipped, so
each run just tops up with new ones. Listing a day's ~5k files costs ~25 paged
calls (~40 s) before downloads begin; finished days are marked complete and
skipped thereafter. Outputs: `data/meta/meta.db` and `reports/meta_dashboard.html`
(opens offline).

## Dashboard

Per Rank Band: a deck-**Archetype** play-rate bar chart (one bar per deck, bar
colour = win rate), with the archetype list directly beneath it. Each archetype
is **click-to-expand** (native `<details>`) revealing its **full most-common
60-card decklist** grouped by card type (Pokémon / Items / Tools / Supporters /
Stadiums / Energy), how many decks ran that exact list, and the **flex slots**
(cards that vary 15–85% across the archetype's lists). A trend panel tracks
archetype play rate over time across all bands.

**Variant merge.** For display, archetypes that share their primary main line and
are subset-related are merged into one cluster (e.g. the ±Cramorant Hop's
Trevenant builds), labelled by the cluster's *most common* member. This is a view
transformation (`dashboard._merge_map`) — the store keeps the precise ≤3-main
labels, so it can be tuned or disabled without re-scraping.

## Schedule (Windows)

```powershell
pwsh -File tools/meta_tracker/register_task.ps1 -Time 03:30
```

Registers a daily Scheduled Task (`-StartWhenAvailable` covers missed starts).
Put the token at `%USERPROFILE%\.kaggle\access_token` so the run-as user
authenticates non-interactively.

## Tuning

- **Download cap / bands** — `config.py` (`DAILY_EPISODE_CAP`, `BANDS`,
  `EPISODES_INDEX`). `BANDS` are contiguous percentile tiers; lower the last
  band's `hi` to keep more of the ladder, raise it to be stricter.
- **Main-line sensitivity** — `MAIN_LINE_MIN_COPIES` / `MAX_MAIN_LINES`.
- **Engine list** — `config.ENGINE_POKEMON` holds consistency/tech Pokémon
  (Dudunsparce, Budew, Munkidori, …) that are never treated as Main lines. Add a
  name here when a non-win-condition keeps naming archetypes. After editing, run
  `store.reclassify(connect())` to re-label existing history (decklists are kept,
  so **no re-download is needed**), then rebuild the dashboard.
- **Settled threshold** — `SETTLED_MIN_EPISODES` (σ proxy for Top Deck).

## Known limitations

- The daily export is **top-rated-skewed** by design; the bottom of the ladder
  is intentionally dropped (we want refined decks). Not a full-ladder census.
- Banding uses each team's **current** leaderboard rating joined by name, while
  the episode may be a few days old — ratings drift slightly, and a team absent
  from the current leaderboard makes its episodes unrankable (dropped).
- Raw replays are discarded (ADR-0002) — no RL/play-by-play re-analysis later.
- A day's full file list is re-fetched until that day is complete; with a small
  `--cap` the same listing recurs across runs (the trade-off for not storing the
  full id set).
