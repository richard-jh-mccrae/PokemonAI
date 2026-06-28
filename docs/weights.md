# Weight scale — what a Hypothesis weight means

`Score(option) = Σ effective_weight(firing Hypotheses)  +  tactical(option)`, and `decide()`
(see [agent-architecture.md](agent-architecture.md)) takes the argmax. Positional (Hypothesis)
points and the combat term share **one additive scale** — that is the whole trick to reading a
weight.

**Anchors — the combat term sets the scale:**

- Lethal KO → `KO_SCORE = 1000` (dominates everything).
- Non-lethal attack → its printed, weakness-adjusted **damage** (~10–300).
- Pure positional decision (play / attach / evolve) → `tactical = 0`, so **only weights decide**.

## Bands — seed here; the ladder tunes within ([ADR-0009](adr/0009-training-methodology.md))

| Weight | Meaning |
|---|---|
| 0–5 | faint tiebreaker — "all else equal, lean this way" |
| 10–20 | normal preference — a standard setup / tempo rule |
| 30–50 | strong preference — core doctrine (e.g. `open-cinderace` = 40) |
| 60–100 | near-imperative positional — rarely outweighed by other positional rules |
| >100 | combat-scale positional — rivals a chip attack; reserve |
| **1000** | `KO_SCORE` (not a Hypothesis) — game-deciding lethal |

**Two consequences:**

- Weights **stack** — three firing 20s (= 60) intentionally rival one 60; multiple reasons add up.
- No realistic positional sum beats a KO (1000) → Hypotheses **bias** combat, never override a
  lethal ([ADR-0008](adr/0008-pilot-is-a-layered-rules-pipeline.md)).

Set seeds by band as an interpretable prior; the linear-rank tuner refines the magnitude while
the band keeps it legible. Current deck seeds (`tutor` 25, `accel` 30, `open-cinderace` 40) sit
in the normal→strong range.

**Weights can be negative** — a penalty steers *away* from an option. General-Strategy energy/opening
seeds ([general-strategy.md](general-strategy.md), [ADR-0016](adr/0016-energy-attachment-is-a-layered-procedure.md)):
`power-up-attacker` +15 and `use-acceleration` +25 (normal tempo); `dont-feed-the-doomed` −30 (strong
penalty); `keep-a-startable-hand` −40 (strong — avoid a clear blunder); `attach-energy-last` −5 (faint
sequencing nudge). (The old `build-before-attack` / `dont-chip-with-a-doomed-active` chip penalties and
their `_CHIP_CEILING` value floor were **removed** — the Pilot's `_finish_turn_last` "attack last"
sequencing supersedes them; see [general-strategy.md](general-strategy.md).)
