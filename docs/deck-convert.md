# deck_convert

Convert between a **Limitless decklist** (`.txt`, as exported from the Limitless deck
builder) and the competition's **`deck.csv`** (60 bare card ids). Offline — no token.

```bash
# Limitless .txt  ->  agents/<name>/deck.csv   (resolve + assert legality; hard-fail on any problem)
python tools/deck_convert.py to-csv <deck.txt> <dir-name> [--force]

# deck.csv  ->  Limitless .txt   (render only; paste back into Limitless)
python tools/deck_convert.py to-txt <deck.csv> [-o out.txt]
```

`to-csv` writes `my_submissions/agents/<dir-name>/deck.csv` (60 ids, sorted — same
format as `deck_stealer`); attach your own `main.py` to run/package it. `to-txt`
prints to stdout by default.

## How cards are matched

A replay/Limitless card is identified by **name**, not `(set, number)` — Limitless
lets you pick any printing, but the pool stores one canonical printing per card
(`Ultra Ball MEG 131` → pool's `Ultra Ball SVI 196`). Names are normalized for case,
accents (`Poké`), and straight/curly apostrophes (`Boss's` ↔ `Boss’s`). Basic energy
maps by element (`Psychic Energy` → `Basic {P} Energy`, id 5). For names with several
printings (Eevee = 43/145/317) the file's `(set, number)` is used as a tiebreaker.
See [ADR-0013](adr/0013-decklist-resolution-by-name.md).

## Legality (asserted on `to-csv`)

All five must hold or the build hard-fails, listing every violation (nothing is written):

1. **Exactly 60 cards.**
2. **≤ 4 copies of any card, counted by name** (across printings).
3. **Basic energy only** is exempt from the 4-copy cap; **special** energy (Legacy,
   Mist, …) is still capped at 4.
4. **≤ 1 ACE SPEC** card total.
5. **≥ 1 Basic Pokémon.**

## Failure modes

- **absent** — the card isn't in the competition pool (e.g. `Special Red Card`); swap it.
- **ambiguous** — a multi-printing name whose `(set, number)` matches no pool printing.
- **illegal** — any of the 5 rules above.

`to-txt` is render-only (a `deck.csv` is already 60 legal ids). Round-trip is stable:
`to-txt` then `to-csv` yields the same ids — basic energy is emitted by element with the
pool's `SVE` printing so it re-resolves cleanly. The Pokémon section is grouped by
evolution line (basic → stage 1 → stage 2), lines ordered by total count.
