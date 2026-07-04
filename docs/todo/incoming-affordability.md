# TODO — make the Incoming / `active_doomed` estimate Energy-affordability-aware

**Status:** open (2026-07-04), split out of the ep83661649 f54 fix. The `_wins_now` half landed (a
bench-snipe KO is no longer mis-read as a game-winning Active KO); this is the second half.

## The bug

`Pilot._predicted_max_damage` (the shared magnitude behind every Incoming estimate, and so behind
`Board.active_doomed` / `incoming_active_damage` / `_active_doomed` / `_forward_incoming_damage`) takes
the **max over ALL the attacker's attacks with no Energy-affordability check**. So a 1-Energy opponent
Active is credited with its 3-Energy Nebula Beam (210) it cannot pay for — falsely dooming my Active.

At f54 this made the Pilot feed the **bench** Mega (`concentrate-energy-on-wincon`) instead of the
**active** Mega the human labeled: `dont-overbuild-the-doomed-wincon` (−45) fired on the active because
it read as doomed, when the opponent (1 Energy, +1 attach = 2) can only afford Jetting Blow (120) < my
active's 210 HP — it **survives**.

## Why it wasn't landed in-session

The one-line fix (cap `_predicted_max_damage` to attacks costing ≤ `opp_current_energy + 1`, mirroring
the Tool doctrine's `_opp_best_attack_vs`) is **correct** and made f54 fully green (Pilot attaches to the
active Mega). But `active_doomed` is a **load-bearing shared signal**, and the change broke **19 tests**,
including two **real-state planner CRITICAL gates**
(`test_planner_engine.py::test_critical_0cbc_*` / `test_critical_6858_*` — the `stabilize_then_ko`
fixes). Most of the 19 are synthetic fixtures that give an opponent a big attack but no Energy (fine
under the old assume-affordable model); the two planner gates must be re-verified as **not** regressed
on their real states before the change can land. That is a focused subsystem pass, not a safe tail-end
patch, so it was reverted (a note left in `_predicted_max_damage`).

## Definition of done

1. Add an `energy_budget` param to `_predicted_max_damage` (drop attacks whose KNOWN cost exceeds it;
   keep unknown costs conservatively; empty → 0). Pass `len(opp_active.energies)+1` from
   `_incoming_active_damage` only (leave `active_maxed_kos` etc. unbudgeted).
2. Re-baseline the ~17 synthetic doomed-fixtures to give the opponent enough Energy to afford the
   attack they're meant to threaten with (so they stay genuinely doomed) — or assert the new,
   more-accurate not-doomed behavior where that's the correct outcome.
3. **Re-verify `test_critical_0cbc_*` / `test_critical_6858_*` on their REAL states** — the
   `stabilize_then_ko` planner fixes must still hold (their opponents must still afford the attack that
   dooms my body, or the planner's heal-then-KO must remain correct). This is the gate that decides
   whether the change is safe.
4. Re-point the f54 fixture test (`test_incoming_affordability.py`) at the exact human-correct option
   (`chosen == [4]`, the Active attach) instead of the current "an Attach, not the snipe" assertion.
