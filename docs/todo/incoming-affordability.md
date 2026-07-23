# TODO — make the Incoming / `active_doomed` estimate Energy-affordability-aware

> ✅ **The `active_doomed` follow-up landed 2026-07-23** (the doom-shadow grill —
> [`doom-shadow-grill-handoff.md`](../plans/doom-shadow-grill-handoff.md) RULED appendix): a
> **RELAX-ONLY matched-Read gate** (`Pilot.doom_matched_relax`, PROFILE ON, kill-switched). The
> boolean STAYS worst-case by default; behind a γ-matched Brief with no discard-recur fuel the
> charged curve (`Pilot._DOOM_CHARGED`, `base_attach: 2` — the +1 budgets the pool-generic
> Crispin/Waitress supporter attach) may CLEAR a worst-case cry, never add one. planner_6858 stays
> honored twice over: unmatched → worst-case, and Nebula Beam's ●●● stays charged-reachable via the
> Ignition burst. Pinned by `tests/strategy/test_doom_matched_relax.py`.

> 🔁 **AMENDED by [ADR-0064](../adr/0064-incoming-counts-the-opponents-next-development-step-budgeted-by-the-read.md)
> (2026-07-16).** The survival read behind `_incoming_worst`/`_survives_after_ko` becomes
> **charged-with-archetype-budget** (per-attack, typed-cost-shape affordability; energy budget =
> attached + 1 attach + a colorless-burst allowance derived from the matched Read's rep list),
> **defaulting to worst-case when the Read is unmatched** — so the planner_6858 hidden-Ignition lesson
> below stays honored (Nebula Beam's ●●● cost is colorless → burstable → still doomed).
> `active_doomed` itself STAYS worst-case per the original ruling until its own named follow-up behind
> a fixture re-baseline. The re-verification demanded below (`test_critical_0cbc_*`/`test_critical_6858_*`
> on real states) is ADR-0064's safety gate.

> ⛔ **RESOLVED as WON'T-FIX for the survival boolean (2026-07-07, ADR-0045 build).** Making
> `active_doomed` affordability-aware was built and **reverted**: it is **unsound** because it ignores the
> opponent's HIDDEN burst Energy. On the CRITICAL `planner_6858`/`planner_0cbc` states the opponent is a
> Mega Starmie **mirror** at 1 Energy holding an unseen **Ignition** (3-Energy burst) that fires Nebula
> Beam next turn — a 1-attach cap reads "not doomed" and **re-opens the blunder** (agent re-picks the
> attach). A survival read must never under-prepare against a possible burst, so **`active_doomed` stays
> worst-case** (Incoming reads the ceiling). The affordability-aware read instead lives in the **Threat
> Clock** (`_threat_clock`, ADR-0045), the MULTI-TURN PREP projection (off-by-a-turn is recoverable) — NOT
> the one-turn survival boolean. The f54 correction relied on seeing the opponent's hand (replay), which the
> agent cannot. See [ADR-0045](../adr/0045-match-scale-planning-is-a-closed-form-directive-game-plan.md)
> *Amendment*. The `_wins_now` half (below) already landed and stands.

**Status:** ~~open (2026-07-04)~~ **won't-fix (survival boolean); superseded by the Threat Clock's prep
read.** Split out of the ep83661649 f54 fix. The `_wins_now` half landed (a bench-snipe KO is no longer
mis-read as a game-winning Active KO); the affordability half is resolved as above.

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
