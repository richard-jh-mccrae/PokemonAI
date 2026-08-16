# ADR-TEMP: The Bellman potential prices the opponent's hand (dark), special conditions, and the stadium zone

Status: Accepted; built from the 2026-08-16 src/ crash-and-valuation audit.

## Context

The audit that followed PR #531/#532 found three mechanics the live valuation could not see:

1. **Opponent hand size.** `RefreshEvaluator.evaluate` computed the ADR-0060 strip/gift swing per
   branch and shipped it into diagnostics rows only; no `BoardPotential` family read either hand
   count on the opponent side. Judge, Unfair Stamp, and Harlequin therefore priced as pure
   self-refreshes — ADR-0060's six human corrections (swings to ±13 in its table) could not be
   reproduced by the shipped agent.
2. **Special conditions.** The observation renders `poisoned/burned/asleep/paralyzed/confused` per
   player and nothing in `src/common` read any of them: a paralyzed opponent Active still priced as
   a full incoming threat, Munkidori's Mind Bend rider was worth zero, and the poison tick never
   entered damage progress.
3. **The stadium zone.** `_board_resources` walked only Pokémon stacks, so a Stadium in play carried
   no Worth and playing one was a strict ledger loss (hand cost, no board credit): Risky Ruins ×2
   and Gravity Mountain ×2 were structurally never played.

## Decision

All three become facts of the absolute potential (ADR-0136 shape — priced once, differenced
everywhere):

- **`opponent_hand` family, shipped dark.** Value `-share × worth_to_prizes(KNOWN_CARD_FLOOR) ×
  opponent hand count`; the refresh ledger's new `refresh_opponent_hand` row prices the same swing
  with the same constant and the same share, so the closed-form and engine-stepped paths cannot
  disagree. `value.opponent_hand_share` (PilotProfile, default **0.0**) arms both at once — a
  kill-switch that covers every consumer of the term.
- **Condition shares.** The Active's conditions scale its forecast attack value: incoming
  `asleep 0.5 / paralyzed 0.0 / confused 0.5` (checkup and rules facts, not tuning), own-side
  `asleep 0.75 / confused 0.5` (paralysis clears before our next attack window and menus already
  enforce this turn). Poison (10) and expected burn (20 × cure coin) enter `_damage_progress` as
  pending checkup damage, both sides, capped by remaining HP.
- **Stadium Worth.** Our own Stadium in `current["stadium"]` joins `_board_resources` as a
  one-card stack, making a Stadium play value-neutral statically so its printed effect (visible
  through successor HP and readiness) decides.

## Why the opponent-hand share ships at zero

Armed at full share the term deterministically flips two ruled corpus frames whose margins were
graded without it: `496a7657096f` (opponent at 2 cards — the gift charge of 2 × floor flips a
0.017-prize margin off the ruled Harlequin line) and `baede6accfac` (opponent at 8 — the strip
credit detours the ruled attack). The corpus on the build box also carries a 3-to-5-test
load-dependent flake floor (the same class as the known CI determinism flake), so per-frame
re-grading at full share is not honest evidence either way. The term is real (ADR-0060's table),
its magnitude is not yet ratified in prize units; arming is a measurement round:
`tools/train/bellman_corpus.py` A/B at candidate shares plus a ladder result, then flip the default
in one commit. ADR-0060's ratified STRIP:GIFT asymmetry (4:8) is noted for that round; the dark
implementation is symmetric at the known-card floor until the round says otherwise.

## Consequences

- Every potential carries the `opponent_hand` family (zero while dark) and its FAMILY_OWNERS entry.
- Condition and stadium pricing are live immediately; neither moved a deterministic corpus verdict
  (no shipped frame carries a condition flag; the stadium term is own-side only).
- `RefreshEvaluator` accepts an explicit `opponent_hand_share` and otherwise inherits the board
  potential's share, keeping one authority for the constant.
