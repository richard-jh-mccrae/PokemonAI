# M1 — trace harness + vanilla game loop ✅ DONE

**Status:** complete 2026-07-10 (commit `a509725`): 12/12 vanilla traces replay CLEAN
end-to-end (byte-equal obs every frame) covering setup incl. the full mulligan machine,
evolutions, retreats (energy-discard cascade), attacks with Weakness ×2 / Resistance −30,
KOs, facedown prize picks, promotions, win/draw adjudication. As-built record + the machinery
a resuming session builds on.

## The machinery (all committed)

- **Capture** — `tools/parity/capture_match.py` (needs DLL): plays native matches under a
  seeded chaos policy (YES-biased, bench-eager, occasional retreat) and writes
  `parity-trace/1` gz files: per select the mover's verbatim obs + `choice` + the aligned god
  frame (visualize `selected` +1 offset realigned and asserted at capture).
- **Replay** — `src/cgpy/verify/replayer.py`: binds randomness from the record —
  draw identities from the mover's own full DRAW logs (a seat's draws only ever land in its
  own next window, in order), coins per-seat likewise, prize identities from the first god
  frame with a prize row, deck order re-synced (multiset-asserted) from each frame's god deck.
  Hands are NEVER synced — identity-tracked and asserted (a hand mismatch is a real bug).
- **Diff** — `verify/differ.py`: parsed-JSON compare, NO normalization (array order is
  contract; bool≠int guarded), first divergence as a JSON path.
- **Gate** — `tests/parity/test_replay_fixtures.py` over `tests/fixtures/parity/*.trace.json.gz`
  (12 committed vanilla traces), DLL-free; named CI step in `.github/workflows/ci.yml`.
- **Vanilla decks used** (legal, textless, ability-less): A = 4×Beldum 274 + 4×Metang 275 +
  52×Psychic-energy 5; B = 4×Sandile 830 + 4×Krokorok 831 + 52×Darkness-energy 7
  (Darkness→Psychic weakness exercised). Deck files are trivially regenerable (see 01 doc or
  build inline).

## Behavior pins M1 established (beyond the M0 list — all trace-derived)

- **Setup machine:** deal 7/7 fp-order → per-seat `HasBasicPokemon` checks (BASICS ONLY — an
  Explosiveness starter does not satisfy it) → paired auto-redraw rounds while both fail →
  SetupActive posed the moment a seat checks True (starters ARE offered: Cinderace 666, a
  Stage 2, may start — `CardDB.is_setup_starter`) → prizes dealt right after a placement if
  the other seat is unresolved, else batched fp-order → **DrawCount = 0..(net mulligan
  difference), lower-count seat only, none on ties** → SetupBench per seat with benchable
  basics (a SKIPPED empty bench-ask still bumps `turnActionCount`) → actives reveal (no log)
  → turn 1.
- **The `Mulligan` YesNo** = keep-or-redraw choice, posed ONLY to a basic-less hand holding an
  Explosiveness-class starter (YES = mulligan anyway; NO = keep + start it). The NO branch has
  never been observed in a trace — its CHK-log shape is a GUESS (see 03 queue).
- Mulligan hand returns to deck **LIFO**, revealed to both; KO energy discards LIFO; KO stack
  discards top-first, Pokémon before energies before tools.
- `appearThisTurn` = `entered_turn >= current turn` (setup entries count as turn 1) — it is a
  turn-NUMBER fact, not owner-relative clearing.
- KO flow: ATTACK log → HP_CHANGE (negative `value`) → discards → **the KO'er picks facedown
  prize slot(s): CARD select ctx TO_HAND over PRIZE area** → adjudication (reason 3
  NO_POKEMON outranks the prize win; simultaneous win = DRAW result 2) → promotion select
  (ctx TO_ACTIVE) posed to the defender → turn end.
- Terminal frame: `result` set AND a **degenerate empty select** (type 0, context = last
  posed context, min/max 1, zero options) — not `select: null`.
- `retreated` flips at RETREAT-choice time (before the energy/switch cascade resolves).
- Retreat cascade: DISCARD_ENERGY selects one energy at a time (`remainEnergyCost` counts
  down) → SWITCH select over the bench → SWITCH log (`cardIdActive` = the one leaving).

## Regen commands

```bash
# vanilla decks (one-liners) — or reuse any legal textless pair
printf '%s\n' 274 274 274 274 275 275 275 275 $(for i in $(seq 52); do echo 5; done) > /tmp/vanilla_a.csv
printf '%s\n' 830 830 830 830 831 831 831 831 $(for i in $(seq 52); do echo 7; done) > /tmp/vanilla_b.csv
python tools/parity/capture_match.py --decks /tmp/vanilla_a.csv /tmp/vanilla_b.csv -n 8 --seed 4000 --prefix vanilla2
python tools/parity/replay_diff.py --all
```
