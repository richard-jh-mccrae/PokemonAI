# Arena — human-vs-agent web app

Public web app where a **Visitor** plays a live **PvC Match** against one of our
agents on the real cabt engine, then leaves a **Rating**. Every game is captured as
a Tuner-usable replay. Glossary: [tools/arena/CONTEXT.md](../tools/arena/CONTEXT.md);
capture-path decision: [ADR-0033](adr/0033-arena-captures-pvc-on-cabt-env-path.md).

## Run

```bash
pip install -r requirements.txt
cd tools
python -m uvicorn arena.server:app --host 0.0.0.0 --port 8000
```

Open `http://<host>:8000/` — welcome screen → deck screen → board. Point a QR code
at the public URL (any generator; the URL is the only input).

## Architecture (one screen)

```
browser ── REST /api/* ──────────┐
        ── WS /ws/<table> ── server.py ── tables.py ──(stdio JSON)── worker.py ── cabt env
                                  │                                     │            │
                             view.py (obs → render model)        human bridge     agent seat
                                                                        │
                                                     replay_store.py → data/replays/PvC/*.json
```

- One **Table** = one worker subprocess = one live match (engine holds one battle
  per process). Capped (`cap=4` default); overflow gets a friendly 409.
- **Board interactions are sugar over the option list**: drag a hand card onto a
  lit-up Pokémon (attach/evolve) or onto your side of the board (play it); tap a
  dash-outlined Pokémon to pick it (snipe targets, promotions); every gesture
  resolves to the same option index a panel tap would send. Attached energy renders
  as typed pips; the stats line's Discard count opens either player's discard pile
  (public info, like a real table — hands and decks stay counts). Fetch/reveal picks
  (deck search, discard fetch, look-at-top) swap the text panel for a card carousel:
  wheel or drag to scroll, the centered scan is the candidate, tap it to take it.
- The **human bridge** wraps the Visitor as an env agent callable: obs out over the
  WebSocket, option indices back in (ADR-0033). Env timeouts are overridden at
  `env.make` — the cabt defaults would forfeit a slow human.
- **Forfeit**: concede button, or ~10 min idle → the sweeper forfeits the Table.
  Partial replays are kept, flagged `abandoned` (still taggable). A worker that
  ignores the forfeit is force-killed after a grace period; finished Tables are
  evicted ~30 min after the game (the Rating window).
- The Visitor always holds **seat 0**; the engine's own coin still decides who goes
  first. `info.TeamNames` = `[visitor, agent]`.
- **Opponent selection is random** over the playable agents (any `src/agents/<name>/`
  with `main.py` + `deck.csv`), so every bot collects Visitor games; the play header
  shows which bot was drawn. `POST /api/tables` takes an explicit `"agent"` override.
- **Pre-warm pool**: one standby worker is kept booted (agent drawn randomly at warm
  time — the standby *is* the matchmaking draw); claiming it makes click-to-first-frame
  near-instant (~0.05 s vs ~3–8 s cold). Two-phase worker protocol (warm → ready →
  start); explicit-agent mismatches and back-to-back starts fall back to a cold spawn.
- **Rating** (misplay + early/mid/late + comments, no numeric grade) is patched into
  the replay's `info.pvc` after the game — one self-contained file per match.

## Deck entry

Three paths, easiest first:

1. **In-app builder** (`build.html`): clone a preset (or start empty) and edit
   against the real competition pool — search/browse with card detail (attacks,
   effect text), live 60-count and legality feedback. Legal by construction; the
   server re-validates the id list at table creation (`validate_ids`).
2. **Presets** as-is: `tools/arena/presets/*.txt` (Limitless format — drop a file
   in to add one).
3. **Limitless paste/upload** ("Deck Text", the Share → Copy as Text export);
   resolution/legality reuse `tools/deck_convert.py` (ADR-0013) and reject whole
   with every problem listed.

## Card images

One-time per host:

```bash
python tools/arena/images.py
```

Downloads the official scan of every pool card (~1260 files @ ~50 KB) from the
Limitless CDN into `tools/arena/static/cards/<id>.png` (gitignored), keyed by the
pool's canonical printing (`EN_Card_Data.csv` set/number; promos remap to SVP).
The server snapshots what exists at startup (`img` flag on `/api/cards`) and
serves `/cards/{id}.png` locally — visitors never touch the CDN. A few cards have
no recorded set and stay imageless; every view falls back to text chips. Restart
the server after fetching new images.

## Getting replays back (the SSH pull)

On the dev box:

```bash
python tools/arena/pull.py rich@workbox /srv/PokemonAI
```

Copies `data/replays/PvC/*.json` from the Arena host into the local repo
(gitignored). The blunder inspector ingests them like Self-play Corpus replays;
`info.pvc.rating` triages which games to tag first.

## Requirements trace

| REQ | Behavior | Tests |
| --- | --- | --- |
| REQ-ARENA-0001 | Deck Text resolves whole or rejects whole with every problem; preset gallery lists only playable decks; the builder's pool catalog + id-list validation enforce the construction rules | tests/test_arena_decks.py |
| REQ-ARENA-0002 | PvC replays saved Self-play-Corpus-shaped with `info.pvc` metadata; Rating patched in post-game | tests/test_arena_replay_store.py |
| REQ-ARENA-0003 | The view-model labels every option, carries tap coordinates, renders bot events, types attached energy, lists both (public) discards, hides hidden info | tests/test_arena_view.py |
| REQ-ARENA-0004 | The worker hosts one PvC Match: bridge protocol, concede/forfeit, no-clock overrides, replay on every end | tests/test_arena_worker.py |
| REQ-ARENA-0005 | Tables are capped, freed on end, idle-swept to Forfeit | tests/test_arena_tables.py |
| REQ-ARENA-0006 | REST funnel + match WebSocket + rating endpoint behave per contract | tests/test_arena_server.py |
| REQ-ARENA-0007 | Full stack: browser-shaped client plays a real match; replay is Tuner-shaped | tests/test_arena_system.py |
| REQ-ARENA-0008 | One-command SSH pull of PvC replays | tests/test_arena_pull.py |
| REQ-ARENA-0009 | Card images: pool-printing scan URLs, skip-existing fetch, imageless fallback | tests/test_arena_images.py |

## Ops notes

- The server process loads the native engine read-only (card names for the
  view-model); matches run in workers.
- No auth by design: anonymous Visitors, optional display name, size-capped inputs
  (64 KB request bodies, count-guarded deck text); the table cap is the rate limit.
  Don't put anything secret on this host.
- Windows + Linux both work (CI runs the suite on both); the Arena host is the
  always-on Linux box.
