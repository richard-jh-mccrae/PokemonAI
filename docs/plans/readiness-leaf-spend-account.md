# readiness-leaf-spend-account (memory note) — v1 BUILT 2026-07-16

The MY-side board-state value function (**the readiness leaf**) + the **line account** (spend costs and
ability-fire credits), built into `src/common/strategy/planner.py`. This is the project-memory note the
grill spec ([board-state-valuation-grill.md](../archive/plans/board-state-valuation-grill.md)) and the T0 disposition
([t0-planner-disposition.md](t0-planner-disposition.md)) pointed at. Companion search spec:
[ply1-turn-search-grill-spec.md](../archive/plans/ply1-turn-search-grill-spec.md); pickup doc:
[develop-rung-handoff.md](../archive/plans/develop-rung-handoff.md).

## The one-paragraph summary

The engine-sim leaf (`_engine_leaf_value`) used to grade a develop-turn board with `_board_development`
(`10·bodies + 5·energy`, plan-tiered) — which collapsed the ~36 distinct end-boards the search reaches to
~5 values (SOLE-top ~5%). v1 replaces that positional term with **`_readiness(me)`** and adds a **signed
line account**: `turn_value = readiness(end) + Σ ability-fire credits − Σ spend costs`. Measured on the
267-frame leaf lab: **SOLE-top 5%→12%, shared-top 60%→72%, avg top-tie 3.7→3.1**. And **Gate 0 flips from
a wash to a PASS**: on the honest SOLE-top, exhaustive-search + this leaf beats the 1-ply rung **27% vs 18%**
(9 vs 6 of 33 lucario frames), tighter ties 2.24 vs 2.64 (`gate0_ab.py`, bounded `CAP=2500`).

## `readiness(me)` — the board term (my-side P(win) proxy)

```
readiness = min(CAP 300, floor + Σ_bodies min(BODY_CAP 120, contribution(b)))
floor            = 8 if a bench exists (binary — a KO doesn't lose the game)
contribution(b)  = max(attack_readiness, ability_readiness) × saturation      ← attack ∥ ability CO-EQUAL
attack_readiness = position_w × progress × (damage × 0.45) × 0.6^hops , else 0 (THE gate: no reachable atk ⇒ 0)
   · best over the body's OWN attacks (hops 0) + a REACHABLE evolution's (hop 1) — reachable = the payoff
     is DEPLOYABLE this turn (in hand or in play); NOT the whole decklist (the sim hides deck contents, so
     the decklist proxy is vacuous — every Riolu would read Mega-Lucario-ready). Deck-odds is v2.
   · progress = payable (TYPE-AWARE) energy / cost ∈ [0,1] — off-type energy earns nothing.
   · position_w = 1.0 Active / 0.45 Bench (the v2 mobility lift needs hand visibility).
   · a WEAK win-condition pre-evo (Riolu 30 ≤ ½ Mega Lucario) credits ONLY its reachable payoff's attack,
     not its own throwaway chip → payoff undeployable ⇒ 0 ("the attach's ~0 gain", scenario 1).
ability_readiness = value(best draw/dig/accel/tutor ability), precondition-gated, NO bench discount, else 0
   · value from a Function Tag, else 45 for an `engine`/`accel_source` Role the tags miss (Lunatone's
     Lunar Cycle is role-declared, UNTAGGED — verified: card_functions.json has no id 675).
   · precondition: a tag-named ability is self-sufficient (Drakloak Recon); a pure-utility `engine` body
     the tags miss (Lunatone) needs a DISTINCT engine/attacker partner in play (Lunar Cycle needs Solrock).
saturation(b)    = 1.0 for an attacker/Line body; 0.1 for a 2nd in-play body of the same utility/engine
                   CARD (a 2nd Lunatone is fodder — "we only ever need one"). Role-keyed via `_is_utility_body`.
```
All capped so max positional (readiness 300 + survival 50 + threat 100 + value 40 + line 100) = 590 <
1000 = KO_SCORE — the hard-rung invariant (no positional board ever outranks a real prize).

## The line account — `_line_account(traces, indices)` (the path term)

Reuses the LIVE tuned weights via `OptionTrace.fired`, summed along the simmed line (first step + each
greedy continuation step; opponent-reply steps excluded). The referent is always the **ACTION**, never the
resulting board (the disposition's guard against state-summing drift).
- **`_ABILITY_FIRE_IDS`** (POSITIVE fired weight): USING a beneficial setup ability — `fire-lunar-cycle`,
  `use-the-draw-engine-ability`, `lunar-cycle-the-weak-preevo-last-f`, `advance-the-accel-pieces`,
  `use-acceleration`, `bench-the-comeback-drawer`, `feed-the-firing-accelerator`. **Why a LINE credit and
  not only a board term:** greedy continuation CONVERGES the end-boards (all lines fire the draw ability
  eventually; the drawn cards play into the same board, hand → 0), so the value of *firing it* is invisible
  on the static end board. This is what flips scenarios 1 & 4.
- **`_CLASS_B_SPEND_IDS`** (NEGATIVE fired weight, magnitude subtracted): consuming a scarce resource —
  `dont-waste-discard-energy`, `dont-attach-discard-energy-turn1`, `dont-play-switch-for-no-gain`,
  `dont-lunar-cycle-away-the-last-attachable-f`, the hold-* / tool-hold family, etc. (t0 disposition class B).
- Capped: positive side ≤ `_LINE_CAP` 100 (invariant); negative side uncapped (only ever LOWERS a value).

## Named acceptance scenarios (measured on the leaf lab)

1. **Discard-to-draw** (mega_lucario ep85058574 f16, correct=[6] fire Lunar Cycle): **shared-top rank-1**;
   the attach blunder (chosen=[4], Solrock) is deprecated below top. The tied lines are equivalent
   non-blunders that also fire Lunar Cycle — SOLE-top would be overfitting. Mechanism: weak-preevo
   suppression zeroes the Riolu attach, `fire-lunar-cycle` (+15) lifts the ability line.
2. **Prize-math promote** / 3. **same, opp can't punish** — OUT of the leaf (opponent layer / 2-ply), as specced.
4. **Hold-the-evolve** (dragapult ep86091435, correct=[2] use Recon before evolving): **SOLE-top**.
   Mechanism: `use-the-draw-engine-ability` (+18) fires on the Recon line; evolving first loses Drakloak's
   ability, so its line never earns the credit.

## Where it lives

`src/common/strategy/planner.py`: `_readiness`, `_attack_readiness`, `_best_reachable_attack`,
`_reachable_forward_ids`, `_payable_energy`, `_ability_readiness`, `_ability_value`,
`_ability_precondition_met`, `_readiness_saturation`, `_line_account`; the `_READINESS_*` / `_LINE_CAP` /
`_ABILITY_FIRE_IDS` / `_CLASS_B_SPEND_IDS` constants; wired into `_engine_leaf_value` (+ the `line` param on
`_leaf_value`, + the 5-tuple `_simulate_line` return). Tests: `tests/strategy/test_readiness_leaf.py`.
Measurement: `tools/train/leaf_lab.py`; the Gate-0 A/B `tools/train/probes/gate0_ab.py` (both columns grade
the pure-readiness terminal leaf — `spend_account=False` — since the line account is a turn-value term, not
part of the search-structure A/B). `_board_development` is retained (auxiliary; its own tests still pass).

## v2 backlog (deferred, as specced)

Deck-odds evo-availability (hypergeometric-fetch-closure); the `position_w` mobility lift (switch-in-hand,
retreat-ease); the gated actionable-resource / held-tutor term (needs hand-visibility plumbing; AVOID raw
handCount — measured overfit). The cost note: the first-step line account adds one root `_evaluate` per
`_engine_leaf_value` call (phase-hysteresis-guarded); cache the root re-score if the rung's per-turn cost regresses.

## Related

[[board-state-valuation-grill]] · [[t0-planner-disposition]] · [[ply1-turn-search-grill-spec]] ·
[[develop-rung-handoff]] · [[turn-planner-develop-rung]] · [[leaf-lab-develop-rung]] ·
[[value-model-needs-nonmirror-gauntlet]] · [[ml-build-plan-adr-0053]]. ADRs: 0031 (Turn Planner), 0042
(value model, parked), 0053 (ML value net).
