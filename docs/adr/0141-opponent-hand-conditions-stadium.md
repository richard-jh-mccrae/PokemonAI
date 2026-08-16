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

**Board parity scales the term.** `board_parity` is our `_board_resources` Worth over the positive
magnitude of `opponent_roles`, clamped to `[0, 1]`, multiplying both the `opponent_hand` family and
the `refresh_opponent_hand` ledger row. A player losing on board cannot afford to protect the
leader's card economy — they have to dig. The parity is **pinned to the root observation** rather
than recomputed per successor: how far behind we are is a read of the position being decided from,
and letting successors move it would price board development and damage partly through a hand term.

The denominator is role pressure rather than the opponent's own `_board_resources` because that
call is **not** symmetric in the matchup that matters. `_board_resources` is side-agnostic and card
Worth floors at `KNOWN_CARD_FLOOR` for any id in our registry, so against a mirror it returns a
real figure (measured 0.50–0.67 across three `mega_starmie_*` stores) — but against any unregistered
deck it returns exactly `0.0`, which reads as *infinitely ahead* precisely when we are losing to an
unknown list. `opponent_roles` covers both, because the runtime seeds generic roles for every
recognised opponent body: at `496a7657096f`, where the opponent's `_board_resources` is `0.0`, role
pressure still reads `0.910` against our `0.375`.

**The magnitude is a tenth of the known-card floor.** Scaling alone does not carry these frames:
every line that ends the turn also hands the opponent their draw, so shrinking the term shrinks the
attack line's own charge too, and the gap at `496a7657096f` closes only from 0.071 to 0.022 prizes.
Measured parity is 0.412 at `496a7657096f` and 0.509 at `baede6accfac`, so `share = 0.1` charges an
effective 0.041 and 0.051 there. Forcing `_root_board_parity` to a constant (one value per process;
a loop of `runtime()` builds in one process exceeds the decision clock) brackets the flip: the ruled
line returns below ~0.15 effective at `496a7657096f`, and between 0.05 and 0.10 at `baede6accfac`.
`value.opponent_hand_share = 0.1` is the largest share landing inside both brackets, and both ruled
picks were then confirmed by decision, not by extrapolation.

On the corrections corpus, armed fails seven where the same suite on the same tree dark fails eight,
and `tests/bellman` acceptance fails three against four pre-change. **Both deltas are 1, inside the
3-to-5 flake floor recorded below — the count is not the evidence.** What carries is set inclusion:
each armed failure set is a strict subset of its dark counterpart, so no frame fails that did not
already fail without the term.

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
