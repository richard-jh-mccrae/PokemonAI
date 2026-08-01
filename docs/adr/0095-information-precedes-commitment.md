# ADR-0095 — Information precedes commitment, and the apply-seam cannot derive it

**Status:** Accepted (grilled 2026-08-01, `/grill-with-docs` on Issue #259, wave-1 packet item 2).
**Build = Issue #259 (POC-T0), with the sequencer change owned by T2 and the contract note by T0.**
**Amends [ADR-0069](0069-attach-energy-last-is-a-sequencing-tier-not-a-weight.md) §7** (which made
the attach a sequencing tier rather than a weight — this applies the same reasoning one tier up, to
the free band 0069 left undifferentiated) and **narrows the whitelist entry** ratified under
[ADR-0092](0092-the-value-system-poc-builds-by-differencing-tracks-with-wave-rulings.md) §6.
Does **not** supersede anything.

⚠️ **Temp-named, not numbered.** Real number assigned at `/open-pr` rebase time. Cite the issue.

**Context issues:** Issue #259 (this grill), Issue #228 (owner of the deny flips), Issue #212
(the free-Item hold price), Issue #165 / POC-T4 (the Turn Planner this constrains).

## Context

Wave-1 packet item 2 reported that arming `deny_relevance` regressed
`82225643|1|decision|11` and diagnosed it as the free-Item hold price: "a FREE Item still spends a
card." **That framing did not survive** — PR #265 / ADR-0093 armed deny on a different diagnosis and
the regression does not exist (see the re-measurement below). What survives is the user's ruling on
the frame, which was never about deny at all:

> "This goes into the box of 'Collect information before committing'. Do PokeGear first. Then, most
> likely, you'll also play Hammer and Ignition Energy in this same turn."

That reframes the frame. It is **not a selection** among competing plays — all three plays are legal
in the same turn (`docs/rules.md` §3: Items unlimited, attach 1/turn; the engine re-presents the
menu after each non-ending action). It is an **ordering**.

### Measured 2026-08-01, not recalled

Board (`tools/train/frame_view.py 82225643-11`), turn 2, us = `mega_starmie`:

```
ACTIVE  Cinderace 160/160, NO energy, Turbo Flare {C} 50    BENCH  Staryu (entered this turn)
HAND 6  Ignition Energy · Crushing Hammer x2 · Pokegear 3.0 x2 · Hero's Cape
        no basic Energy in hand; 8 Basic {W} in deck
OPP     Riolu active carrying their ONLY energy in play (1x Basic {F})
        bench Riolu / Solrock / Makuhita, all bare
ruled correct [0] Play Pokegear 3.0     today's agent chooses [3] Play Crushing Hammer
```

⚠️ **Re-measured 2026-08-01 after rebasing onto `27b1c00`** (PR #265 / ADR-0093, *"an ABSENT read is
not a measured zero"*, which ARMED deny for real). The first draft of this ADR rested on "arming
deny regresses this frame". **That evidence is gone**, and the correction matters more than the
conclusion:

```
deny now armed by DEFAULT in PROFILE
Discrimination Gate  PASS  0 moved      Decision Gate  PASS  0 moved
83686860|1|decision|13   correct [1]  chosen [1]   <- fully RESOLVED, no longer disagrees
82225643|1|decision|11   correct [0]  chosen [3]   <- still wrong, and NOT a regression
```

So the frame is a **standing disagreement**, not a regression: the baseline records the same wrong
pick, so no gate flags it, and my "two unruled regressions" were artifacts of a stale base.

**The doctrine survives on different, weaker, still-sufficient evidence:**

1. the user ruled it directly — *"This goes into the box of 'Collect information before committing'.
   Do PokeGear first. Then, most likely, you'll also play Hammer and Ignition Energy in this same
   turn"*;
2. the agent still picks `[3]` where the ruling says `[0]` — an uncorrected misplay, merely one the
   gates cannot see because the baseline shares it;
3. the code fact below is unchanged on the fixed tree.

What it is NOT is a blocker on arming deny. Deny is armed and both gates are green.

Card text verified at `data/EN_Card_Data.csv`: Crushing Hammer is *"Flip a coin. If heads, discard an
Energy from 1 of your opponent's Pokémon"*; Ignition Energy is *"discard it at the end of your turn"*.

The coin is **already** priced — `coin_odds(ctx.card_id) * weight * value - _DENIAL_ITEM_COST`
(`pilot.py:5609`). That suspected defect is refuted.

The real mechanism is in the sequencer. `_finish_turn_last` states the doctrine as its own purpose —
*"take the most informative, reversible actions first and the irreversible ones last"* — but
`_tier()` ends on a bare `return 0` (`pilot.py:1986` on the rebased tree), so **every endorsed free `_PLAY` lands in
tier 0**, and tier 0 is "stable -> within a tier, score order":

```
Pokegear 3.0     free, INFORMATIVE   -> tier 0
Crushing Hammer  free, COMMITTING    -> tier 0     <- same band; score decides
```

Arm deny, the Hammer's score passes Pokégear's, and the Hammer sequences first. **Tier 0 conflates
*free* with *informative*.** Tier 0's own docstring says "Free, and reveals a better target before
you commit" — a Hammer is free and reveals nothing.

## Decision

**1. The free band splits on information, not on cost.** `_finish_turn_last` gains a boundary
inside its free band: options that ENLARGE the information set (draw / search / dig, Bench fill,
benched evolve) sequence strictly ahead of endorsed free plays that COMMIT a card at a target. The
classification is keyed off a behavioural Function Tag (`src/common/card_functions.json`), never a
card name.

**2. The whitelist entry is narrowed to name the boundary.** ADR-0092 §6's
"`_finish_turn_last` sequencing tiers" becomes the *information-before-commitment* boundary
explicitly. A whitelist line that says only "the tiers are sound" is unfalsifiable; this one is
testable and was in fact false in the free band.

**3. The apply-seam does NOT capture information value, and T0 records that.** Playing Pokégear
before the Hammer versus after reaches the **same end state**. A planner that ranks a *fixed
sequence* by `state_value(end)` is therefore blind to information ordering by construction: the
value of digging first is that later choices can *condition on what was revealed*, which appears
only when the planner evaluates a contingent policy rather than a committed sequence. POC-T4
commits "the argmax sequence's first action" and the apply-seam returns EXPECTATION nodes that
average over reveals rather than branching on them. **Therefore information-first sequencing is not
derivable by the machinery T0 freezes, and stays structural.** The `apply_option` docstring states
this limitation rather than leaving it to be discovered.

**4. ~~Deny arms only after the sequencing fix~~ — WITHDRAWN, moot.** The first draft sequenced deny
arming behind this tier split and Issue #212's free-Item hold price, so that no regression was
ruled-and-shipped in exchange for arming. PR #265 / ADR-0093 armed deny on a different and better
diagnosis (an ABSENT read misread as a measured zero), and both gates are green with 0 moved. There
is no regression to trade, and T2's deny item is **not** sequenced behind this work. Recorded as
withdrawn rather than deleted: a decision that shaped a track's ordering should leave a trace when it
stops applying.

## Consequences

- **Re-measured, not predicted.** `83686860|1|decision|13` is fully resolved by PR #265 (`correct [1]`,
  `chosen [1]`) and needs no ruling — the caution about not spending a ruling on a frame that may not
  flip was right, and the frame indeed did not flip. `82225643|1|decision|11` still picks `[3]` where
  the ruling says `[0]`: a standing disagreement the gates cannot flag, which is what this boundary
  is expected to correct when T2 lands it. That correction is the falsifiable prediction this ADR
  leaves behind.
- A Function Tag audit is owed: every Item must classify as informative or committing. Untagged
  defaults to committing — the conservative direction, since a mis-tagged commitment sequencing
  early is the error that costs a card.
- Other frames will move in both gates when the boundary lands. Each is a wave item.
- Decision 3 is a **stated limitation of the POC**, not a defect to fix inside it: contingent-policy
  planning is depth-2 search, which ADR-0092 scoped OUT (post-POC Issue #150).
