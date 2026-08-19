# Arena (`tools/arena/`)

The public-facing web app where a human plays a live game against one of our agents on
the real cabt engine. Visitors arrive via a QR code, bring or pick a deck, play on a
phone-first board, and leave a Rating. Every game is captured as a full cabt replay —
PvC games are **training data** (taggable + Tuner-usable), not keepsakes.

Reuses the engine vocabulary of [Agent Checks](../sim/CONTEXT.md) (cabt env, seat) and
feeds the [Training](../train/CONTEXT.md) context (its replays are blunder-taggable like
the Self-play Corpus).

## Language

**Arena**:
The whole hosted app — server, board UI, deck funnel, rating capture — running on the
always-on Linux box. The thing the QR code points at.
_Avoid_: web app (generic), simulator (that's the engine), Battle harness (Agent Checks)

**PvC Match**:
One game on the cabt engine between a **Visitor** (human seat) and one of our agents.
The human-seat sibling of Agent Checks' **Match** (which seats two agents). Always
captured via the cabt-env path so the replay carries per-frame agent `obs`
(Tuner-usable, ADR-0022).
_Avoid_: game, match (bare — Agent Checks owns that for agent-vs-agent), Episode
(reserved for Kaggle-recorded artifacts)

**Visitor**:
The human player. Anonymous by default; may enter an optional display name. Plays from
a phone or desktop browser; no account, no auth.
_Avoid_: user, player (ambiguous — the agent is also a player), opponent (seat-relative)

**Table**:
A live-match slot on the Arena server — one engine subprocess hosting one PvC Match.
Capped (config, default ~4); when all Tables are taken new Visitors wait.
_Avoid_: session (HTTP-flavored, overloaded), room, lobby (the waiting state, not the slot)

**Preset Deck**:
A curated `deck.txt` in the Arena's deck gallery that a Visitor can pick instead of
bringing their own — our agents' decks plus selected meta Representative Builds.
_Avoid_: default deck, starter deck

**Deck Text**:
The bring-your-own input the Arena accepts — the Limitless Deck Builder export
(Share → Copy as Text): count + name + set/number lines in Pokémon/Trainer/Energy
sections, pasted or uploaded as `.txt`. Resolved to competition card ids by *name*
(ADR-0013); an unresolvable deck
is rejected whole, with every problem listed back to the Visitor.
_Avoid_: deck.txt (a filename, not the format), decklist (generic), deck.csv (the
resolved id form the engine eats)

**Rating**:
The Visitor's post-game qualitative feedback on the agent: what it misplayed + roughly
when (early/mid/late game) + open comments. No numeric grade. Embedded in the replay
JSON's `info` block, so it travels with the replay file. Its job is **triage** — it
points the blunder inspector at the PvC replays (and regions) worth tagging first.
_Avoid_: score, review, stars (there is no numeric grade), Correction (that's the
tagged artifact a Rating may lead to)

**Forfeit**:
How a PvC Match ends without being played out: the Visitor concedes, or idles past the
timeout (~10 min without acting) and the Table is reclaimed. The agent is recorded as
winner-by-forfeit; the partial replay is **kept**, flagged `abandoned` in its metadata
(partial games still hold taggable agent decisions).
_Avoid_: disconnect (a network event, not the outcome), abandon (use as the flag name,
not the term)
