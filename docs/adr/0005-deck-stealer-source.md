# ADR-0005: deck_stealer copies decks from a replay file, not the leaderboard or meta store

**Status.** Accepted and BUILT — `tools/deck_stealer.py` is the shipped tool and sources decks from
a downloaded replay, exactly as decided here.

`deck_stealer` takes a downloaded replay plus a team name and writes that team's
exact 60-card deck to `src/agents/<name>/deck.csv`. We source from the
**replay** — not a team-name lookup against the leaderboard or the meta store —
because a replay is full-information and pins the *exact* list a team ran in *that*
game; choosing which replay to download is itself the disambiguation when a team
runs more than one deck. Offline, exact, zero ambiguity.

## Considered options

- **Team-name → meta store (`meta.db`)**: convenient browse-by-name, but the store
  keys only `(team → deck)` per sampled episode — 21% of stored teams show ≥2
  distinct decks, it can't pin *which* one you meant, and it may not have sampled
  the deck at all.
- **Live Kaggle pull** (leaderboard → submissions → episodes → replay): adds
  submission-level identity, but needs a token + network + rate-limit handling,
  re-implements the scrape chain, and *still* recovers the 60 cards from replays
  ([ADR-0001](0001-data-source.md)) — so it lands on the same deck data wearing
  submission labels.
- **Replay file (chosen)**: the only cost is obtaining the replay, which is a
  deliberate per-deck choice the user is already making.
