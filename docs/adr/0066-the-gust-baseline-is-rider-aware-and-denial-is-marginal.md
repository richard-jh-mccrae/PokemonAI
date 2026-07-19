# ADR-0066: The gust baseline is rider-aware, and gust denial is marginal

**Status.** Accepted and **BUILT 2026-07-19**, default ON — the gusting Round-0 build
(`docs/plans/gusting-round0-measurement.md`; grill rulings recorded in
`docs/plans/gusting-grill-spec.md`). Amends ADR-0022 (the gust doctrine); applies ADR-0062/0063's
marginality rulings and finishes ADR-0052's expensive-attack patch on the bench side. Suite green
(3051), the 29-correction gust sweep re-run end-to-end.

## Context

The gusting grill seed hypothesised a full opponent-keep-cost equation. Round 0 measured first:
all 29 gust-adjacent corrections replayed through the real `Pilot.explain()` with a fresh pilot per
replay. The cluster dissolved — 19 pass, the set-asides hold, and exactly THREE failures survive,
one per leg. Each got a targeted fix to the EXISTING equations; the full keep-cost machinery stays a
design (`docs/plans/gusting-keepcost-design.md`), per the anti-speculation hazard the seed doc
itself carried.

## Decision — three amendments, one widened oracle

### 1. The whether-to-play baseline counts what the menu already collects (ep86091435 f119)

`gust-for-the-ko` compared the gust-KO only against the DIRECT Active KO (+ the condition Checkup).
Phantom Dive's 60 bench spread already KO'd the 40-HP Relicanth — and the gate, blind to riders,
spent Boss's Orders dragging that same body up for the same prize. Two new Board signals restore the
with-vs-without comparison:

- `menu_attack_total_prizes` — the best ONE-attack total without a gust: its main KO of the current
  Active plus its own snipe/spread rider KOs.
- `gust_best_total_prizes` — the gust line's full take: the dragged target's prize plus the SAME
  attack's rider on the bench that remains (the ep82523164 f55 drag-and-snipe, now spread-aware too
  — ep85046350 f81's gust-Roserade + spread-Gible line demanded it).

The gate is `gust_best_total_prizes > menu_attack_total_prizes` (∨ condition baseline). Both sides
of the comparison carry the riders, so the 2-prize drag-and-finish still fires and the redundant
gust stands down.

**Threat-forfeit premium.** Widening the oracle exposed 2-prize gust lines on boards where the menu
KO removes the very body DOOMING my Active (ep82753102 f109: bench the hand-size Alakazam safely
for +1 prize?). When `active_doomed` and an Active KO is on the menu, the gust must beat the menu by
MORE than one prize — the ~1-effective-prize threat premium the grill's denial-ceiling ruling
allows, pointed in the defensive direction.

**The widened bench oracle.** All of this exposed that the bench-side KO test still used only the
cheapest-attack summary — the exact blindness `_active_ko_prizes` was patched for (Nebula Beam 210
vs 190 HP, ADR-0052). `_gust_can_ko` (cheapest ∨ any per-attack prediction) now feeds the play
gate, the totals, the energy swing AND the target pick, so the play-reason and the picked target
keep agreeing by construction.

### 2. The famine stall is marginal — a wall-for-equal-wall swap denies nothing (ep86091435 f13)

`stall-gust-over-dev-when-starved` (+95) fired on turn 2 to drag an energyless Duraludon up… in
front of an identical energyless Duraludon. ADR-0062/0063's ruling — denial is with-vs-without,
never a flat bounty — applied to TEMPO: `stall_swap_pointless` is True when the opponent's current
Active is itself an energyless, high-retreat strand body and no stall candidate is strictly less
dangerous in place (`_forward_danger`: own ceiling ∨ the evolution line's — a body evolves in the
Active Spot without retreating, so a Riolu-shaped wall is not a wall). The famine rule stands down
on a pointless swap; ep83457493 f20 (a REAL famine stall — the freed Active was the forward-lethal
Riolu line) still fires because its Active held Energy.

Per the grill's stall ruling, the stall legs deliberately STAY a separate small tactical
(retreatCost + EX bonus) — the measured fix was this gate, not a currency conversion.

### 3. An equal-prize KO tie breaks toward the loaded body (ep85163079 f30)

Every denial term lived on the SWITCH target-pick side — reachable only AFTER deciding to play the
card — so the play side could not tell a 4-Energy Staryu one turn from Mega Starmie ex apart from
any bare 1-prize body, and the strict `>` gate ate the tie. Two additions, both ADR-0062's marginal
strip pointed across the table (a KO destroys everything attached):

- Play side: `gust-for-the-loaded-equal-ko` (+50, testing) — fires on an exact prize TIE when
  `gust_ko_energy_swing` (target's sunk Energy − what the baseline Active KO already destroys)
  is ≥ 2. The swing floor is sized by the ep82224509 f46 refutation: an equal KO of a BARE pre-evo
  must never burn the Supporter (its board yields swing −1). Same threat-forfeit guard and
  Supporter-economy damping as `gust-for-the-ko`; sequenced tier-0 with it.
- Target side: `_gust_energy_denial` — 0.2/Energy capped at 0.8, a sub-prize tie-break that never
  overrides a real prize difference, keeping the target pick agreeing with the play reason.

## What this deliberately does NOT do

- No worth-points↔prizes exchange rate, no opponent role sheet, no their-closure/their-deadline
  inputs — the corpus does not demand them. The grill ruled "design the full equation, build on
  evidence": that design is `docs/plans/gusting-keepcost-design.md`.
- `gust_best_ko_prizes` (the lethal gust + stall `== 0` gates) keeps its original semantics; only
  its KO test widened. The lethal gust (`_gust_tactical`) still counts target-only prizes — a
  rider-completed lethal is a design-doc item, unforced by any correction.
- ep86091435 f119's residual divergence was ADJUDICATED in the follow-up grill (same day):
  refuted-by-better-line in `reviewed.json` — the widened oracle's 2-prize drag-and-spread line
  (gust Duraludon → Phantom Dive KOs it AND Relicanth, banking 2 of the 4 needed prizes and
  killing a future Assemble-Alloy accel body) supersedes the human's 1-prize development line.
  Pinned as the ADJUDICATED case in `test_gust_round0_corpus.py`.

## Consequences

- The three failing legs flip or die: f30 chosen==correct; f109/f13's Boss's blunders score 0 and
  are not chosen (substance-pinned). 19→20 of 29 sweep-fixed; zero regressions across the other 28
  and the full suite.
- Test surface: `test_gust.py` +6 (REQ-GUST-0015 — rider baseline, spread synergy, threat premium,
  pointless swap, loaded tie ± controls, loaded target pick); `test_gust_round0_corpus.py`
  (REQ-CORPUS-0002 — 1 pin, 2 substance pins, 1 refuted guard). The ladder A/B remains the ship
  gate for the weight (`gust-for-the-loaded-equal-ko` status: testing).
