# Phase 1c — the promote/retreat decider swap: the Decision Gate sitting

The batched review #136 standing directive 2 owes before the deletion commit is final: *every flip is
re-ruled with the user, never auto-conformed*. Companion to `attach-decider-swap-review.md` (1a) and
`evolve-decider-swap-review.md` (1b). Authority for every design choice is **ADR-0073**.

**Status: ONE frame needs a user ruling.** The Decision Gate is at `FAIL` with exactly one unruled
`REGRESSION`, which is the gate working as designed rather than a defect to route around. Nothing in
the equation has been tuned toward this frame — auto-conforming it is the thing directive 2 forbids.

## The instrument

`tools/train/probes/promote_retreat_decider_sweep.py`, rebuilt for this phase. The shipped
`tools/train/promote_retreat_sweep.py` is **deleted, not merely stale**: it reads a
`promote_retreat_shadow` record and a `worth_it` SIGN BIT, and ADR-0073 decision 2 retires both —
deleting `stay_forgone` turns the whether-site verdict from a sign test into a per-option score, so
there is no sign left to agree with.

Two pilots per frame, built fresh (pilots are stateful):

* **NEW** — `promote_retreat_value` ON with the eleven retired rungs forced to weight 0. That is
  exactly the post-deletion agent; zeroing rather than deleting is what lets the probe run before the
  deletion commit.
* **OLD** — `promote_retreat_value` OFF with every rung at its shipped weight.

Compared by resolved **body slot**, never raw option index. Two site families, because the family's
mass lives in both: **pick** (a TO_ACTIVE forced promote or a SWITCH destination, lane `PROMOTE_LANE`)
and **whether** (a MAIN menu carrying a native RETREAT, a membership test on `chosen` — a slot
comparison cannot express "stayed").

## The tally

```
frames 133   (pick 9 · whether 124)
agree  117
flip    16   FIX 15 · REGRESSION 1 · DIVERGENT 0 · unlabelled 0 · error 0
```

Deleting the `active_can_ko` recusal returned the frames the shadow used to withdraw from, as
ADR-0073 §12 predicted.

## The fifteen FIX frames

Ten of the fifteen are one pathology, and it is the one that opened the grill — *"insanely retreat
happy."* The old agent retreated; the human said don't:

| frame | agent | site | NEW | OLD | correct |
|---|---|---|---|---|---|
| 81785223-12 | mega_starmie | whether | stay | RETREAT | End turn |
| 81903490-10 | mega_starmie | whether | stay | RETREAT | End turn |
| 81904064-9 | mega_starmie | whether | stay | RETREAT | End turn |
| 81904451-9 | mega_starmie | whether | stay | RETREAT | End turn |
| 81905522-10 | mega_starmie | whether | stay | RETREAT | End turn |
| 81906755-9 | mega_starmie | whether | stay | RETREAT | End turn |
| 83007714-8 | mega_starmie | whether | stay | RETREAT | End turn |
| 83053965-6 | mega_starmie | whether | stay | RETREAT | Play Mega Signal |
| 83054602-32 | mega_starmie | whether | stay | RETREAT | End turn |
| 84890060-12 | mega_lucario | whether | stay | RETREAT | End turn |
| 86090164-67 | dragapult_ex | whether | stay | RETREAT | Evolve Dudunsparce |

Two mechanisms account for them. `stay_forgone` is deleted (§2), so the Active's attack competes as
its OWN option instead of being double-charged at a band proxy; and `retreat_cost` is now the BUILD
the discard destroys (§8) rather than 16 points of card Worth — a Mega paying retreat 2 off a full
Nebula Beam build gives up **187 damage** of progress.

The remaining four are pick-site frames where the new decider brings up the right body:

| frame | agent | NEW | OLD | correct |
|---|---|---|---|---|
| 83007714-92 | mega_starmie | (5,1) | (5,0) | (5,1) — the 3-Energy copy |
| 83007714-104 | mega_starmie | (5,1) | (5,0) | (5,1) — the 3-Energy copy |
| 85046350-31 | dragapult_ex | (5,1) | (5,0) | (5,1) — Budew |
| 86088989-50 | mega_lucario | (5,1) | (5,0) | (5,1) — Mega Lucario ex |

f104/f92 are the "first-bench-slot blindness" pair, now EMERGENT from reachable damage rather than
`is_best_promote_target` plus a `+5` tie-break bonus.

## The one frame needing a ruling — 82756664-97

```
82756664-97  mega_starmie  pick   NEW=(5,1)  OLD=(5,0)  correct=(5,0)   REGRESSION
   correct_label: Cinderace (bench 1 · 30/130 · 1⚡)
   slot=(5,1) Mega Starmie ex   total=-30.0  [my_yield=120.0 exposure=150.0]
   slot=(5,0) Cinderace         total=-50.0  [my_yield= 50.0 exposure=100.0]
   slot=(5,2) Staryu            total=-80.0  [my_yield= 20.0 exposure=100.0]
```

**The board.** Turn 9, forced promote. Their Active is a Mega Lucario ex on **20 HP**, so *every*
candidate Knocks it Out — `_promote_ko_tactical` fires on all three and the pick turns on the
residual plus the KO oracle's riders. Our Bench: a Cinderace at **30/130** (1 prize, badly damaged),
a fresh Mega Starmie ex at 330 (3 prizes), a Staryu at 70.

**What the human wants.** Take the Knock Out with the body that is dying anyway. Feeding a 3-prize
Mega Evolution Pokémon *ex* to gain a Knock Out available to a 1-prize chump is the prize-economy
mistake `interpose-the-cheap-attacker-to-preserve-the-wincon` (+50) existed to prevent.

**Why the equation disagrees, and it is not a bug.** Three legs were checked at source before
bringing this here:

1. **The accel dividend is correctly zero.** Cinderace's Turbo Flare has `recoverN=3, source=deck`,
   but `_recover_units` bounds it by the recipients' remaining NEED — and *every* benched body is
   already at 3 Energy. The rider would fire blanks, so §3b credits nothing. Correct.
2. **`my_yield` is correct.** No `wall_progress` discount applies because there is no wall — they all
   Knock Out at 20 HP. 120 is Jetting Blow, 50 is Turbo Flare, 20 is Staryu's chip.
3. **Exposure is correct arithmetic.** Cinderace `1 × 100 × halve(0)` = 100; the Mega
   `3 × 100 × halve(1)` = 150. The Mega yields three times the prizes but one turn later, and §4's
   halving — REUSED from `evolve_value`, deliberately no new constant — discounts that to a
   50-point gap, which the 70-point damage gap then out-votes. On top, the KO oracle credits Jetting
   Blow's +50 bench-snipe rider, which Turbo Flare has no answer to.

So ADR-0073 §11's claim that interpose is *emergent from Exposure* holds where its premise holds —
"exposure 100 vs 300", i.e. when they can take the 3-prize Knock Out **next turn**. Here they need
two, the ruled grading halves it to 150, and the emergence is not strong enough to carry the frame.

**The ruling is the user's.** The three readings that seem live:

* **A — the frame is right and the equation is wrong.** A prize the opponent takes one turn later is
  worth much more than half, because prizes do not decay the way damage does. That is an argument for
  grading `exposure` on a shallower curve than `_halve`, and it re-opens §4's "no new constants".
* **B — the equation is right and the label is a judgement call.** Jetting Blow takes the prize AND
  snipes 50 off their Bench; the Mega survives a hit where the 30 HP Cinderace does not. Record the
  frame as a ruled flip and move on.
* **C — the frame belongs to another layer.** "Take the available Knock Out with the cheapest body
  that can" is a KO-selection rule, not a sub-lethal one, and the residual is not where it should
  live. That would hold it out with an owner (#165 or #145) rather than change §4.

No option is taken here. Until it is ruled, the Decision Gate stays `FAIL` and this document is the
sitting's material.

## What the gate does NOT cover

* **The Discrimination Gate** (leaf-lab `OK → MISS` flips) and the **paired A/B tripwire**
  (`--stage mid-build`, crashes == 0 and `ci_lo >= −5pp`) are ADR-0072's, unchanged, and both need
  the live engine harness — they are owed before merge, not before the sitting.
* ADR-0073 §12 adds **no gate of its own**, which supersedes the issue's grill agenda item 4: there is
  no disagreement-*rate* pass mark, only "zero unruled regressions, every flip ruled".

## Two build-time findings worth carrying forward

* **`hold-position-in-setup` was NOT refuted.** ADR-0073 flags its deletion as the weakest claim in
  the ruling — an emergence argument with no worked frame behind it — and expects a regression there.
  One appeared (83007714-8, the turn-1 setup frame the issue named) and turned out to be a bug of
  mine, not a refutation: the equation credited turn-1 attack damage, which `docs/rules.md` §2 L71-72
  forbids for the player going first. With the rule honoured the frame converts to a FIX, and the
  deletion stands with a worked frame behind it at last (`tests/strategy/test_baseline_retreat.py`).
* **Finding B2's stay-to-develop term is NOT needed.** ADR-0073 decision 2 said to measure before
  authoring it. Measured: of the three named residual regressions, 83007714-8 now converts, and no
  frame in the sweep regresses in the B2 shape. No term authored.
