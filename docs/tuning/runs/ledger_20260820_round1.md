# Ledger tuning — round 1 (2026-08-20), adoption record

Continues `ledger_20260820_145141.md` (the automated greedy pass). Method: plan §7 nudge /
keep-best / adoption-gate; gate = generality floor holds, total agreement rises, ZERO
previously-right frames flip.

## Adopted

- **General** (`LedgerWeights` defaults edited):
  - `active_unready_fraction` 0.30 → **0.15** (from the automated pass; +2, clean).
  - `demand_dead` 0.40 → **0.25** — dead cards decay harder; fetches/holds stop out-pricing
    live plays.
  - `kind.special_energy` 0.10 → **0.05** — breaks the Ignition ≡ basic-{W} exact ties that
    decided fetches arbitrarily; "save Ignition" falls out of demand.
- **mega_starmie dissent** (`ledger_overrides` in its strategy.py): keeps `demand_dead` 0.40
  and `kind.special_energy` 0.10. Measured: the general values flip four of its rulings
  (`81903490-27`, `85163634-41`, `83664340-24`, `81904451-50`) while dragapult_ex and
  mega_lucario only gain (probe: drag+luc under both = +2, zero regressions).

Result: floor 0.3478 → **0.3696**, agrees 187 → **189** of 447, zero regressions.

## Blocked candidates worth revisiting (all blocked by mega_starmie-only flips)

| candidate | would score | flips | note |
|---|---|---|---|
| starmie also takes `kind.special_energy` 0.05 | starmie +4 net (152) | 2 | blocked by the two knife-edge frames below |
| `zone_in_hand` 0.5 | +7..+9 agrees | 9–10 | cheap hand → wasteful plays the rulings hate (Pokégear-first, hammer-waste) |
| `tag.draw` 0.25 | floor +, ±0 | 4 | Harlequin-disruption frames flip |
| `demand_dead` 0.25 + `tag.draw` 0.25 + special 0.05 | 196 agrees | 6 | best raw total seen |

## Knife-edge frames (flagged for the owner's next sitting)

- `mega_starmie 85163634-41` and `83664340-24` — "we are going to KO this turn, so the hand
  is free" rulings. They flip under nearly EVERY hand-value candidate; the judgment is
  lethal-aware sequencing, which a 1-ply price cannot see. Candidates: turn-planner scope, or
  a lethal-aware ordering rule (a +win_value ender exists → hand spend is free).
- `mega_starmie 81904451-50` — "never attach a 2nd energy to Cinderace; Hilda fetches the
  Mega" — attach-cap doctrine vs fetch pricing.

These three block ~4–7 further agrees across otherwise-clean candidates.
