# ADR-0127: A truncated sequence carries the turn's REMAINING terminal EV, not zero

**Status.** Accepted (Issue #400 Phase 1, measured and built 2026-08-06). BUILT.

**Context issue.** Issue #400 (POC-T4), which blocks Issue #386 (T4/5, the arming swap). Ships in the
same PR as **ADR-0125** (Phase 2, the `hand` ledger) and **ADR-0126** (the selection tie-break's
float-noise floor), because the three were found in one drill and the first two are what let this one
matter.

> ⚠️ **Numbered 0127, not 0126.** Issue #400's body reserves *"ADR-0126"* for this ruling; that number
> was taken the same day by the tie-break floor found during the same flip review. The issue body's
> reference is stale, not a duplicate.

## Context

`score(sequence) = state_value(end board) + EV(terminal action)` — Issue #263's own equation. The
second summand was defined for the two ways a turn ENDS:

```
_ATTACK  -> that attack's EV        (composer.terminal_ev)
_END     -> 0                       (ending the turn buys nothing beyond the board already scored)
```

and every other line the composer stopped at also carried **0**, by omission. That includes the
lines it did not end but **CUT**: a play that reveals information makes the engine re-present the
menu, so the beam stops there and replans.

**A sequence the composer CUT is not one that ENDED.** The attack allowance is untouched, the Active
is still standing, and the turn will still spend it. Pricing that line's terminal summand at 0 puts a
partial line head-to-head against a full attack line carrying a prize, and the partial line loses by
the size of the prize — every time, on every board, regardless of what the reveal was worth.

The composer's own header already named this ceiling and deferred it, which is the reason it went
unpriced rather than unnoticed: *"such a candidate carries `EV(terminal) = 0` and is compared
head-to-head against full attack lines that carry a prize … deliberately NOT fixed in this module."*
A declared ceiling records that a limitation is KNOWN. It does not say what to do once it is measured.

## Decision

**1. A truncated (reveal) candidate carries `continuation_ev(node.model)` as its terminal summand.**

```python
def continuation_ev(model) -> float:
    return max((float(attack_ev(**leg.kwargs).total) for leg in attack_ev_legs(model)), default=0.0)
```

**This is differencing, not a rung.** No constant is added and no new math is written: it composes
the *same* `attack_ev_legs` / `attack_ev` pair `terminal_ev` already composes for an `_ATTACK`
option, read at a **second seam** — the truncation point. That is the shape of the `_refresh_swing`
extraction (the PLAY-side equation read at the GRAB seam), and the opposite of a flat bonus.

Floored at 0 by `default=0.0` because ending the turn is always available and `EV(end-turn) = 0`, so
a board whose only attacks price negative continues at 0 rather than below it.

**2. `_stop_here` is EXCLUDED, and that is a soundness property rather than a preference.** The
uniform-credit arm was measured first and is **unsound**: `attack_ev_legs` answers from the BOARD, not
from the menu, so it prices attacks the engine never offered; the root stop-here has
`first_index is None`, so crediting it lets *"commit nothing"* win a decision outright — **4 of 270**
corpus frames produced no pick at all. The credit is for a line the composer CUT, never for one it
declined to start.

**3. A REFUSAL is EXCLUDED, and the exclusion is measured rather than argued.** A refused option's
board never moved and its value is UNKNOWN — a different claim from *"the turn continues"*. Crediting
it too is **byte-identical**, because `selection_key`'s first leg is `bool(candidate.coverage_gap)`,
which sorts every gap candidate behind every scored one whatever its score. The narrow spelling is
taken and the wider one recorded as equivalent.

**4. `_Ranked.delta` does NOT change.** The 1-ply ordering stays uniform differencing for every kind,
so `order` / `fanned` / `Margin` keep meaning what Issue #263 says they mean. The continuation enters
at candidate construction only.

## The board it is read on, and the ONE residual — identified, not smoothed away

`continuation_ev` reads the **PRE-reveal** `node.model`. The justification is structural:
`board_expectation` refuses every `dest` other than the hand, so a reveal writes hand and deck and
nothing else, while `attack_ev_legs` reads the Active, its attached Energy, the special conditions and
the defender.

**Measured over every outcome class the corpus produces: 125 classes across 38 frames, and exactly
ONE differs.** It is named here rather than rounded off:

```
83966336|0|decision|27   agent mega_lucario, turn 3, option 0 (_PLAY, hand index 0), class 3, p=0.0802

  played   1219 Team Rocket's Petrel — Supporter: "Search your deck for a Trainer card, reveal it,
           and put it into your hand."
  active   677 Riolu — Basic {F}, HP 80, Accelerating Stab {F} for 30. ZERO Energy attached.
  class 3  fetches 1142 Fighting Gong — Item: "Search your deck for a Basic {F} Energy card or a
           Basic {F} Pokemon, reveal it, and put it into your hand."

  pre-reveal   attack 981 affordable=False   legs []
  class 3      attack 981 affordable=True    legs [981]  damage 30.0, target_hp 80.0, prizes 1.0
```

*(Card text read from `data/EN_Card_Data.csv`, not recalled.)*

**So the mechanism is real and it is not about the Active at all.** Affordability counts the manual
attach still unspent this turn, and holding an Energy FETCHER makes an Energy reachable — so a reveal
that puts one in hand really does change what the turn can afford. The 124 other classes fetch cards
that do not.

**The error direction is CONSERVATIVE, which is why this is a recorded residual and not a blocker.**
Reading the pre-reveal board UNDER-credits such a class (0.0 against a real value), so a truncated
line can never be inflated above a genuine attack line by this defect — the failure mode the whole
ruling exists to remove. **If the census grows, the exact alternative is on the record:** rank the
Expectation by `max over classes of (state_value(class) + continuation_ev(class))`, which needs
`Expectation.best` to surface the winning class the way `rank_targets` already does.

> ⚠️ **The control on that census was BROKEN on its first run and the first number was discarded.**
> The `_ATTACH` positive control — the transition that MUST move the attack legs if anything does —
> read **0 of 793**, which is what a null result and a dead instrument look like from the outside. The
> cause was in the probe: `apply_option` returns FOUR shapes and a MODELLED transition is *the
> StateModel itself*, not an object carrying `.model`, so `getattr(res, "model", None)` discarded
> every single one. Fixed, the control reads **238 of 793**. Only then is *"1 of 125"* a measurement.
> Issue #400's filed body recorded this census as *"109 of 110, 1 differs"* with a control of *"9 of
> 154"*; the populations differ because the corpus and the rulings moved, and the finding is the same.

## Consequences

**Measured over the 270 MAIN single-pick corpus frames carrying a ruling, paired per frame, at
`abdfe46c` — i.e. ON TOP of ADR-0125 and ADR-0126 and the developer's 2026-08-06 re-rulings:**

| kind | human | base | **+ Phase 1 (shipped)** |
|---|---|---|---|
| `_PLAY` | **95** | 9 | **15** |
| `_ATTACH` | 80 | 100 | 99 |
| `_ATTACK` | 45 | 98 | 93 |
| `_END` | 18 | 23 | 23 |
| `_EVOLVE` | 16 | 26 | 26 |
| `_RETREAT` | 12 | 14 | 14 |
| `_ABILITY` | 4 | 0 | 0 |
| **agreement** | — | **90** | **92** |

```
first-step flips 8    FIXED 2    BROKE 0    neutral 6
  FIXED    83662396|1|decision|19   ruled [0](_PLAY)     1(_ATTACK) -> 0(_PLAY)
  FIXED    85058574|1|decision|114  ruled [1](_ATTACH)   4(_ATTACH) -> 1(_ATTACH)
  neutral  83038055|0|decision|40   ruled [0](_PLAY)     5(_ATTACK) -> 3(_PLAY)
  neutral  83667237|0|decision|120  ruled [3](_PLAY)     7(_ATTACK) -> 4(_PLAY)
  neutral  85163634|1|decision|41   ruled [0](_PLAY)     5(_ATTACK) -> 2(_PLAY)
  neutral  83969481|0|decision|55   ruled [4, 0](_ATTACK) 4(_ATTACK) -> 0(_PLAY)   <- inside the ruling
  neutral  82752604|0|decision|14   ruled [0](_ATTACH)   1(_ATTACH) -> 4(_PLAY)
  neutral  84071010|0|decision|15   ruled [0](_PLAY)     4(_ATTACH) -> 3(_ATTACH)
```

**ZERO regressions, and the neutral column is the more informative half.** Three of the six neutral
flips move an `_ATTACK` pick to a `_PLAY` pick on a frame where the human ruled a `_PLAY` — the right
KIND, the wrong card. That is the ruling working and the remaining error living somewhere else, and it
is recorded rather than counted as a win. `83969481|0|decision|55` is the developer's own re-ruling
(*"playing mega signal is fine enough for deck thinning, then attack"*, correct `[4, 0]`); Phase 1
moves the pick from the attack to the play, both inside the ruling.

**Cost: none, and this is asserted rather than eyeballed.** `leaf_evals` is **3040 against 3040** —
byte-identical, because `attack_ev_legs` is not a `state_value` call and no new board is scored. Per
decision, median 13.2 ms → 13.7 ms and max 898 ms → 867 ms, which is run-to-run noise on a non-idle
box; `BEAM_WIDTH`'s own recorded caution says to cross-check the leaf count for exactly this reason,
and the leaf count did not move at all.

**The shipped code reproduces the measured arm exactly**, verified by re-running the paired harness
against the built module: both arms read 92/270 with `_PLAY` 15 and **0 flips** between them.

**Both ADR-0072 gates are BYTE-IDENTICAL, verified by an asserted revert rather than assumed.**
The Discrimination Gate reads 34034 bytes and the Decision Gate 2112 bytes, character-for-character
the same with and without the change — `gated on 197 / held out 67 / voided 3 / PASS` and
`agree 251/340 -> 255/343 (1 picks moved, 2 rulings moved, 31 voided) / gated 0 / PASS`. The revert
was ASSERTED before the control runs (`git diff HEAD --name-only` must not name the file, and the
file on disk must not contain the string `continuation_ev`), and the restore asserted after, because
a stash stack is shared across worktrees and a "reverted" measurement can silently run its own diff.

The composer is still DARK — nothing in production calls `compose` — which is why that identity is
expected rather than surprising, and it is a fact to re-check the moment Issue #386 arms it. Neither
`data/leaf_lab/baseline.json` nor `data/decider_lab/baseline.json` is re-captured, and neither ever
is: a baseline is a ruling record.

**One shipped invariant was narrowed, and the narrowing is the interesting part.**
`test_attack_ev_is_called_by_the_COMPOSER_and_by_nothing_else` (Issue #384's acceptance, kept when
the composer landed) asserted that every `attack_ev` CALL in `src/` and `tools/` lives in
`composer.py`. `continuation_ev` is a second call site, and the test failed — correctly, because the
claim it defends is *"the terminal leg has EXACTLY ONE consumer"* and a second consumer would be a
second opinion on the same prize.

There are now two call SITES inside that ONE consumer, and the difference is structural rather than
rhetorical: `_terminal_candidate` and `_gap_or_reveal_candidate` are different branches of `_expand`,
so **no `Candidate` can ever carry both** — a terminal candidate has `terminal` SET and a truncated
one has it None. The test therefore asserts by **(file, enclosing function)** rather than by file
alone, pinned to exactly `{terminal_ev, continuation_ev}`; a third site, or either of these moving to
a new function, still fails, which a bare *"the file list is [composer.py]"* would not. The
exclusivity itself is asserted directly in `tests/strategy/test_composer.py`, through the shipped
constructors rather than through hand-made Candidates.

## What this does NOT do — the `_PLAY` gap is now a COVERAGE ceiling, not a valuation one

The human rules a `_PLAY` on 95 frames and the composer picks one on 15. Of the 91 it still misses,
by the ruled option's own fate:

```
77  REFUSED by the seam       no valuation ruling reaches these — `selection_key` sorts a gap
                              candidate last whatever EV a truncated line carries
 9  priced as an expectation node
 4  priced and lost on the merits
 2  no candidate at all
```

Every refusal has an owner and a frame with no owner is a finding: RNG-class refusals are structurally
permanent under Issue #178's no-sampled-shuffle doctrine (the engine has no deal-seed);
`board_expectation` enumeration gaps (`amount` > 1, `dest` in_play, conjunctions, `cost`,
`fetch_is_unconditional`) belong to Issues #301 / #302; `board_delta` choice-key gaps (`gust`, `heal`,
`accel`) to Issues #303 / #304 / #403 / #410.

**It also does not settle the bench `fund_attack` slot**, ADR-0125's own recorded residual — built,
measured a WASH, preserved at `docs/plans/issue-400-bench-funding-slot.patch` and owed a developer
ruling.

## Prior art

`common/composer.py`'s own declared ceiling names this exact mechanism and defers it; that paragraph
is REWRITTEN by this ADR from a deferral into a ruling plus its measurement. **ADR-0121** is the shape
precedent — a structural zero dissolved rather than admitted to the beam — and **ADR-0122** the
counter-precedent, a spec'd equation rejected on measurement; this lands between them, which is why
the fallback (*"if Phase 2 cannot hold, Phase 1 ships alone with flat agreement"*) was written down
before either was measured. **ADR-0126** is why the 2 fixed frames are 2 and not 3: the tie-break
floor already recovered `82226116|0|decision|70`, which the pre-ADR-0126 arm had counted here.

*Positive control on the measurement instrument*, because a paired A/B that silently fails to arm
reports a clean +0: the armed arm moved the winning SCORE on 14 frames and the first step on 8, and
after the build the same harness reports 0 flips against itself. Both directions asserted, neither
assumed. The `_ATTACH` census control's own failure is recorded above, in the section it invalidated.
