# ADR-TEMP-259b — Information precedes commitment, and the apply-seam cannot derive it

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

Wave-1 packet item 2 reported that arming `deny_relevance` regresses
`82225643|1|decision|11` (`OK -> MISS`, rank 1 -> 3) and diagnosed it as the free-Item hold price:
"a FREE Item still spends a card." The user ruled the frame directly:

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
ruled correct [0] Play Pokegear 3.0     today's agent (deny OFF) chooses [3] Play Crushing Hammer
```

Card text verified at `data/EN_Card_Data.csv`: Crushing Hammer is *"Flip a coin. If heads, discard an
Energy from 1 of your opponent's Pokémon"*; Ignition Energy is *"discard it at the end of your turn"*.

The coin is **already** priced — `coin_odds(ctx.card_id) * weight * value - _DENIAL_ITEM_COST`
(`pilot.py:5609`). That suspected defect is refuted.

The real mechanism is in the sequencer. `_finish_turn_last` states the doctrine as its own purpose —
*"take the most informative, reversible actions first and the irreversible ones last"* — but
`_tier()` ends on a bare `return 0` (`pilot.py:1981`), so **every endorsed free `_PLAY` lands in
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

**4. Deny arms only after the sequencing fix, not before it.** Issue #212's generalization of
`_DENIAL_ITEM_COST` (`pilot.py:141`, currently Hammers-only) and this tier split both land before
`deny_relevance` / `deny_strip_delta` flip ON. T2's deny item gains an internal ordering; it is no
longer independently parallel. No regression is ruled-and-shipped in exchange for arming.

## Consequences

- Expected on re-measure: `82225643|1|decision|11` returns to rank 1 on the Discrimination Gate and
  the Decision Gate's `chosen [3]` moves to `[0]`. Neither is assumed — both are re-run.
- `83686860|1|decision|13` (the second, unlisted deny regression found 2026-08-01) is **not ruled
  now**. It is re-measured after this lands; if it clears, no ruling is spent, and if it persists it
  becomes a wave item on its own merits. Ruling a frame that may not flip is exactly the waste
  packet item 1 turned out to be.
- A Function Tag audit is owed: every Item must classify as informative or committing. Untagged
  defaults to committing — the conservative direction, since a mis-tagged commitment sequencing
  early is the error that costs a card.
- Other frames will move in both gates when the boundary lands. Each is a wave item.
- Decision 3 is a **stated limitation of the POC**, not a defect to fix inside it: contingent-policy
  planning is depth-2 search, which ADR-0092 scoped OUT (post-POC Issue #150).
