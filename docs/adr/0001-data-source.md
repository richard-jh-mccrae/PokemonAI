# ADR-0001: Source the deck Meta from Simulation-competition replays

Status: accepted

The deck Meta is mined from the **Simulation** competition (`pokemon-tcg-ai-battle`)
match replays, downloaded with the Kaggle CLI (`team-submissions` → `episodes` →
`replay`) — not the **Strategy** competition (a write-up track with no match data,
though it shares the ladder/rating). Each player's full 60-card deck is read from
the replay's **agent-0-only `visualize` field**, because the agent Observation
deliberately hides the opponent and does not list either deck.

## Why this is non-obvious

The natural place to look — each step's `observation` — never contains decks
(only `deckCount`). Full state lives only at
`steps[i][0].visualize[*].current.players[*].deck`. A future reader will inspect
`observation`, see counts, and wrongly conclude decks aren't recoverable.

## Considered alternatives

- **Promised "daily top-episode export"** dataset (to be posted in the comp
  forums for BC/RL/IL) — not yet live and limited to top episodes. Revisit as a
  lower-effort source once published.
- CLI scraping is the only currently-available full-coverage path.
