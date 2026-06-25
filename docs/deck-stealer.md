# deck_stealer

Copy a top team's **exact 60-card deck** out of a replay into a new submission dir,
so you can run it under your own agent. Offline — no Kaggle token.

```bash
python tools/deck_stealer.py <replay.json|.json.gz> <team-name> <dir-name> [--force]

# keidroid's Cinderace / Mega Starmie ex, from a hand-downloaded replay
python tools/deck_stealer.py data/replays/starmie_keidroid.json keidroid mega_starmie
```

Writes `my_submissions/agents/<dir-name>/deck.csv` (60 card ids, one per line,
sorted by id so re-stealing the same list from any replay is byte-identical) and
prints a provenance line:

```
stole keidroid's Cinderace / Mega Starmie ex (episode 81475913, won vs uuji-qvp)
  -> my_submissions\agents\mega_starmie\deck.csv
```

## How it works

A replay is full-information: both teams' decks live in the agent-0-only
`visualize` frame ([ADR-0001](adr/0001-data-source.md)). The tool reuses
`meta_tracker.parse` to read the frame, selects the side whose `TeamName` you
named, and writes its deck. **Picking which replay to download is the
disambiguation** — if a team runs several decks, grab a replay from the game
showing the one you want ([ADR-0005](adr/0005-deck-stealer-source.md)).

## Notes

- **Where to get a replay / episode id:** there's no "replay id" — it's the
  **Episode id**. It's in the downloaded file name (`episode-<id>-replay.json`),
  inside the JSON (`info.EpisodeId`), and in the Kaggle episode-view URL. It is
  *not* on the leaderboard or the meta dashboard (those are aggregate).
- **Team name** is matched exactly (quote names with spaces/unicode). If it isn't
  in the replay, the tool prints both team names and exits.
- **Just the deck:** no `main.py` is written — you're stealing the deck, not the
  agent. Add your own `main.py` to the dir before `package_agent.py` will build it.
- **Collisions** are refused unless `--force`, so a hand-edited list is never
  silently clobbered.
