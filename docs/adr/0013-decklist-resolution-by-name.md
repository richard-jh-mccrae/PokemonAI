# ADR-0013: Convert Limitless decklists by resolving card *names*, not (set, number)

`deck_convert` maps a Limitless `.txt` to a competition `deck.csv` by matching each
line's **card name** (normalized for case, accents, and straight/curly apostrophes)
to a pool id — *not* by the `(set, number)` printed in the file. Limitless lets you
pick any printing, but the competition pool catalogs each card under its own single
canonical printing (e.g. `Ultra Ball MEG 131` → the pool's `Ultra Ball SVI 196`), so
the name is the only reliable bridge. `(set, number)` is used **only** as a tiebreaker
for the ~14% of names that map to several ids (Eevee = 43/145/317).

Conversion **hard-fails** (writes nothing, lists every problem) when a card is absent
from the pool or stays ambiguous, or when any of the 5 construction rules is violated —
a silently-partial deck.csv is worse than a clear failure.

## Consequences

- We deliberately **substitute the pool's printing** for the user's chosen one. For
  functionally-identical cards (trainers, energy, single-print Pokémon) this is
  invisible and correct; it is the right behavior for a play-the-same deck.
- A Limitless deck can be **unconvertible** — `Special Red Card` simply isn't in the
  pool, so that deck can't be built without a swap. The tool says so explicitly.
- Basic energy is resolved by **element** (`Psychic Energy` → `Basic {P} Energy`),
  since Limitless and the pool disagree on energy set/number.
