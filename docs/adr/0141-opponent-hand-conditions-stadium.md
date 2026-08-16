# ADR-0141: The Bellman potential prices the opponent's hand (dark), special conditions, and the stadium zone

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
  enforce this turn). Poison (10) and burn (20 — the counters land unconditionally; the coin only
  decides the cure, docs/rules.md L161) enter `_damage_progress` as pending checkup damage, both
  sides, capped by remaining HP.
- **Stadium Worth.** Our own Stadium in `current["stadium"]` joins `_board_resources` as a
  one-card stack, making a Stadium play value-neutral statically so its printed effect (visible
  through successor HP and readiness) decides.

## Amendment 2026-08-16: armed at a tenth, scaled by board parity

The measurement round below was held as a live adjudication session. Both flipped frames were
re-ruled and both rulings stand: `496a7657096f` plays Harlequin (the hand is Wally's Compassion, a
Harlequin, two Salvatore and a Mega Signal, of which only Harlequin does anything — our only
Pokémon is a Stage 2 Cinderace with no evolution above it and no Staryu anywhere on board), and
`baede6accfac` attacks. Two things follow.

**Board parity scales the term.** The potential prices our own in-play strength (`board`) but has
no comparable reading of the opponent's, because card Worth is registry-keyed and their stacks
carry none; their scouted role pressure is the only symmetric figure. `board_parity` is our board
Worth over that pressure, clamped to `[0, 1]`, and multiplies both the `opponent_hand` family and
the `refresh_opponent_hand` ledger row. A player losing on board cannot afford to protect the
leader's card economy — they have to dig. The parity is **pinned to the root observation** rather
than recomputed per successor: how far behind we are is a read of the position being decided from,
and letting successors move it would price board development and damage partly through a hand term.

**The magnitude is a tenth of the known-card floor.** Scaling alone does not carry these frames:
every line that ends the turn also hands the opponent their draw, so shrinking the term shrinks the
attack line's own charge too, and the gap at `496a7657096f` closes only from 0.071 to 0.022 prizes.
Sweeping the effective rate puts the ruled line back in front below roughly 0.15 at that frame and
below 0.05 at `baede6accfac`; `value.opponent_hand_share = 0.1` is the largest share holding both
once parity is applied. On the corrections corpus this is not a regression: armed fails seven, dark
on the same tree fails eight, and the armed set is a strict subset of the dark one.

ADR-0060's ratified 4:8 STRIP:GIFT asymmetry remains unbuilt; the term stays symmetric.

## Why the opponent-hand share shipped at zero

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
