# Phase 1c — the promote/retreat decider swap: the Decision Gate sitting

The batched review #136 standing directive 2 owes before the deletion commit is final: *every flip is
re-ruled with the user, never auto-conformed*. Companion to `attach-decider-swap-review.md` (1a) and
`evolve-decider-swap-review.md` (1b). Authority for every design choice is **ADR-0100**.

**Status: RULED by the user 2026-07-27.** The single `REGRESSION` is held out with owner **#165** (it
is a Maneuver), and the defect it exposed in `_deck_basic_energy_fuel` is filed as **#172**. ADR-0100
§4's exposure grading is exonerated. Nothing in the equation was tuned toward the frame — auto-
conforming it is the thing directive 2 forbids.

## The instrument

`tools/train/probes/promote_retreat_decider_sweep.py`, rebuilt for this phase. The shipped
`tools/train/promote_retreat_sweep.py` is **deleted, not merely stale**: it reads a
`promote_retreat_shadow` record and a `worth_it` SIGN BIT, and ADR-0100 decision 2 retires both —
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
gate   PASS  (the one REGRESSION is RULED — held out with owner #165, see below)
```

Deleting the `active_can_ko` recusal returned the frames the shadow used to withdraw from, as
ADR-0100 §12 predicted.

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

## The one flip that needed a ruling — 82756664-97 (RULED, held out to #165)

```
82756664-97  mega_starmie  pick   NEW=(5,1)  OLD=(5,0)  correct=(5,0)   REGRESSION
   correct_label: Cinderace (bench 1 · 30/130 · 1⚡)
   slot=(5,1) Mega Starmie ex   total=-30.0  [my_yield=120.0 exposure=150.0]
   slot=(5,0) Cinderace         total=-50.0  [my_yield= 50.0 exposure=100.0]
   slot=(5,2) Staryu            total=-80.0  [my_yield= 20.0 exposure=100.0]
```

Turn 9, forced promote. Their Active is on **20 HP**, so *every* candidate Knocks it Out —
`_promote_ko_tactical` fires on all three and the pick turns on the residual plus the KO oracle's
riders.

**What the human wants.** Take the Knock Out with the body that is dying anyway. Feeding a 3-prize
Mega Evolution Pokémon *ex* to gain a Knock Out available to a 1-prize chump is the prize-economy
mistake `interpose-the-cheap-attacker-to-preserve-the-wincon` (+50) existed to prevent.

**The board**, dumped in full (2026-07-27 — correcting a first pass that mis-read it):

```
ME (seat 1, mega_starmie) — Active EMPTY (just Knocked Out), 5 prizes left, 25 cards in deck
  BENCH[0] Cinderace         30/130   1x {W}
  BENCH[1] Mega Starmie ex  330/330   1x {W}   (over Staryu)
  BENCH[2] Staryu            70/70    1x {W}
  HAND (10): Ultra Ball · 2x Harlequin · 2x Cinderace · Night Stretcher ·
             Buddy-Buddy Poffin · 3x Basic {W} Energy
  DISCARD (13): 3x Crushing Hammer · 2x Lillie's Determination · 2x Ignition Energy ·
             Buddy-Buddy Poffin · Mega Signal · Wally's Compassion · Hilda ·
             Mega Starmie ex · Staryu          [NO Basic {W} Energy]

OPPONENT (seat 0) — 3 prizes left, 9 cards in deck, 7 in hand
  ACTIVE   Mega Lucario ex   20/440   3x {F}  + Hero's Cape   <-- one hit from a Knock Out
  BENCH[0] Lunatone         110/110   -
  BENCH[1] Mega Lucario ex  290/340   5x {F}
  BENCH[2] Solrock          110/110   1x {F}
  DISCARD (24): 4x Fighting Gong · 3x Lillie's Determination · 3x Dusk Ball ·
             3x Premium Power Pro · 3x Poké Pad · 2x Hariyama · Solrock · Riolu ·
             Switch · Mega Lucario ex · Basic {F} Energy · Carmine
  STADIUM: 1252 (theirs)
```

Every benched body of mine carries exactly **one** {W}, so nothing is "already powered".

**Why the equation disagrees — and the cause is NOT the exposure grading.** A first pass recorded the
accel dividend as correctly zero "because every bench body is already fully powered." **That was
wrong on both counts** and is corrected here. The three legs, re-measured:

1. **The accel dividend is zero because of the FUEL leg, not the NEED leg.** `_recover_units` is
   `min(recoverN, deck fuel, recipient need)` = `min(3, 0, 4)`. Recipient need is **4** — the bodies
   genuinely want Energy. The binding bound is `_deck_basic_energy_fuel` returning **0**, and the
   arithmetic is: the decklist runs **9** Basic {W}, **6** are already visible (3 attached, 3 in
   hand), leaving 3 unseen — against **5** face-down prizes. The pre-anchor read is the SOUND
   PIGEONHOLE FLOOR, `max(0, unseen − prizes_hidden) = max(0, 3 − 5) = 0`: it cannot *prove* a single
   Water is still in the deck rather than prized, so an endorser claims nothing. Its own docstring
   assumes the floor "typically saturates … (9 Water unseen − 6 prizes ≥ 3)"; here two thirds of the
   suite is already on the board, and the assumption fails.
2. **`my_yield` is otherwise correct.** No `wall_progress` discount applies because no wall stands —
   their Active is on 20 HP and every candidate Knocks it Out.
3. **Exposure is the ruled arithmetic.** Cinderace `1 × 100 × halve(0)` = 100; the Mega
   `3 × 100 × halve(1)` = 150.

**The counterfactual that identifies the cause.** Feed the fuel leg the 3 UNSEEN copies instead of
the provable floor and nothing else changes — the frame lands on `correct`, decisively:

| body | `my_yield` | exposure | total | with fuel = 0 |
|---|---|---|---|---|
| Cinderace | **275** (50 + 3×75) | 100 | **+175** | −50 |
| Mega Starmie ex | 120 | 150 | −30 | −30 |
| Staryu | 20 | 100 | −80 | −80 |

So the regression is an artefact of a conservative EPISTEMIC read collapsing, not of §4's grading.

## The ruling — user, 2026-07-27: **correct = Cinderace, and the frame is a MANEUVER**

The user supplied the intended line, which settles both the verdict and the cause. Verified against
the card text and the board before recording (Gravity Mountain is why Cinderace reads 30/**130** —
it is a Stage 2 and the stadium is theirs; Mega Starmie ex is Stage 1 and untouched at 330):

> Opponent needs 3 prizes, we need 5. We must Knock Out this Lucario **and** their backup Lucario; it
> helps that the backup is already weakened. To shield our Starmie from a revenge attack **and to
> Energy-accelerate**, promote Cinderace. Then, on our turn: Night Stretcher fetches the Mega Starmie
> ex from the discard · evolve the Staryu · attach Energy to the benched Starmie · Buddy-Buddy Poffin
> to thin the deck · Harlequin (their hand is 7 — that is the disruption). Now attack: Turbo Flare
> Knocks Out their Active and distributes its 3 Energy so that **both** benched Starmies end the turn
> on **3**. We end with Cinderace up front, **2 prizes remaining**, and two full-HP Starmies benched.

Every step checks out. Turbo Flare costs `●` and Cinderace holds its `{W}`; 50 damage against a
20 HP Active is a Knock Out; **Mega Lucario ex is a Mega ex, so that Knock Out takes 3 prizes** —
5 → 2, exactly as stated.

**The Energy lands 3 / 3, and that is the point of the line.** The benched Staryu already carries
1 `{W}`, and evolution keeps attached cards (`rules.md` §4), so the evolved body starts on 1 rather
than 0 — and Turbo Flare attaches "to your Benched Pokémon **in any way you like**", so its 3 split
1 / 2 rather than 0 / 3:

| body | before | manual attach | Turbo Flare | **end** |
|---|---|---|---|---|
| Mega Starmie ex (standing) | 1 `{W}` | +1 | +1 | **3** |
| Mega Starmie ex (just evolved) | 1 `{W}` (kept from Staryu) | — | +2 | **3** |

Three is the number that matters: **Nebula Beam costs `●●●`**, so BOTH benched Starmies end the turn
able to swing 210 — damage unaffected by Weakness or Resistance, or by any effect on their Active. A
2 / 4 split would strand one body on Jetting Blow's 120 and waste an Energy on the other.

**What this settles.** The Knock Out is available to every candidate and yields the same 3 prizes, so
it cancels — the decision is entirely about what else the promoted body does. Cinderace does two
things the Mega cannot: it **shields** the 3-prize win-condition from the revenge attack, and its
attack **accelerates**. The equation prices the first (exposure, 100 vs 150 — correctly, just not
decisively) and is blind to the second, because the accel dividend is zeroed by the fuel leg.

**And the fuel leg is worse than under-read — it is out of phase.** `_deck_basic_energy_fuel` reads
the deck as it stands AT THE PROMOTE. The line plays **Harlequin** before attacking, which shuffles
the hand — including its Basic `{W}` — back INTO the deck, manufacturing the very fuel Turbo Flare
then searches for. No decision-time read of the deck can see that; it is a property of the step
ORDER. So there are two distinct defects behind this one frame:

* **(i) the floor is over-pessimistic.** `max(0, unseen − prizes_hidden) = max(0, 3 − 5) = 0` refuses
  to claim fuel that is very probably there. This is reading **D** below, and the counterfactual shows
  it alone flips the frame.
* **(ii) the value is a dependent STEP-CHAIN.** promote → fetch → evolve → attach → thin → disrupt →
  attack-with-accel is a **Maneuver** in this project's vocabulary, and ADR-0070 amendment J puts
  those with **#165**. A per-option equation structurally cannot price a chain whose payoff lands on
  later steps — which is the same argument that kept `retreat-to-wall-the-line` alive.

**Disposition.** The frame is **HELD OUT with owner #165** (defect ii — the Maneuver), and defect (i)
is filed as **#172** against `_deck_basic_energy_fuel`, which is ADR-0061's, pre-existing, and shared
with the attack option, so it is not 1c's to change unilaterally. ADR-0100 §4's exposure grading is
**exonerated** — reading A is withdrawn as treating a symptom.

### The readings, for the record

* ~~**A — grade exposure on a shallower curve than `_halve`.**~~ WITHDRAWN: the counterfactual shows
  the exposure arithmetic was never the cause.
* **B — a judgement call.** Superseded: the user gave a concrete winning line, so it is not a
  toss-up.
* **C — it belongs to another layer.** ADOPTED for the frame → owner **#165** (the Maneuver).
* **D — fix the fuel READ.** ADOPTED, filed as **#172**. The closure term already faced this exact
  fork and took the other road: ADR-0070 §3 rules income *"an ODDS read, never a tier"*, which is why
  `_promote_closure` uses `CountTriple.expected`. An expected-value leg (or letting the deck tracker
  anchor) would make the two consistent.

## What the gate does NOT cover

* **The Discrimination Gate** (leaf-lab `OK → MISS` flips) and the **paired A/B tripwire**
  (`--stage mid-build`, crashes == 0 and `ci_lo >= −5pp`) are ADR-0072's, unchanged, and both need
  the live engine harness — they are owed before merge, not before the sitting.
* ADR-0100 §12 adds **no gate of its own**, which supersedes the issue's grill agenda item 4: there is
  no disagreement-*rate* pass mark, only "zero unruled regressions, every flip ruled".

## Two build-time findings worth carrying forward

* **`hold-position-in-setup` was NOT refuted.** ADR-0100 flags its deletion as the weakest claim in
  the ruling — an emergence argument with no worked frame behind it — and expects a regression there.
  One appeared (83007714-8, the turn-1 setup frame the issue named) and turned out to be a bug of
  mine, not a refutation: the equation credited turn-1 attack damage, which `docs/rules.md` §2 L71-72
  forbids for the player going first. With the rule honoured the frame converts to a FIX, and the
  deletion stands with a worked frame behind it at last (`tests/strategy/test_baseline_retreat.py`).
* **Finding B2's stay-to-develop term is NOT needed.** ADR-0100 decision 2 said to measure before
  authoring it. Measured: of the three named residual regressions, 83007714-8 now converts, and no
  frame in the sweep regresses in the B2 shape. No term authored.

## The Discrimination Gate, run late (2026-07-28) — two frames, both RULED

Owed "before merge, not before the sitting" per the section above, and not actually run before this
swap merged. Diagnosed while investigating #178's follow-up (the pinned `data/leaf_lab/baseline.json`
showed 2 unruled `OK → MISS` on `main`, both bisected to this swap's commit `e9853d8`). Neither
frame's `correct_value` moved — a sibling option gained instead, which is exactly ADR-0072 finding 2's
continuation-collateral shape: `_engine_leaf_value` re-runs `decide` for the greedy continuation, so a
changed promote/retreat policy moves the leaf behind a first action the swap never touched.

### `85163634|1|decision|41` (mega_starmie) — REGRESSION, ruled by the user

Turn 6: Active Mega Starmie ex full HP with 3 {W} attached, opponent's only-energised body about to
be KO'd. Human ruling: play Lillie's Determination (`[0]`), dig for energy for the second bench
Starmie — *"we are going to KO the active, no other opp pokemon has energy, so why waste the crushing
hammer?"* Wasting the Hammer here does nothing, since the KO sends the opponent's lone energy to
discard for free regardless.

Before this swap, `[0]` and Retreat (`[6]`) tied at 2207.5 in a 5-way tie with 3 other options. After,
`[6]` alone rose to 2231.8 and broke the tie.

Traced: **both lines reach the identical end-of-turn board** — 2 prizes banked, Active unchanged,
hand emptied to 0 either way. The only difference is which benched body ends up holding one spare
Energy: Cinderace (`[0]`'s line) vs. the second Mega Starmie (`[6]`'s line). `readiness()` rates an
Energy on the second Mega above one on Cinderace, worth +24.3 — a real per-body preference, but here
it is retreating the fully-loaded live Active in order to move one spare Energy onto a *bench* copy of
the same attacker, immediately after the turn's own KO has already happened.

**Ruled (user, 2026-07-28): retreat is not a consideration on this frame at all and should score
NEGATIVE, not top.** `[0]` (Lillie's, then attack) is correct; recorded as a **REGRESSION**, held
against this swap — not conformed, not re-baselined away.

**A second, sharper finding the frame surfaced.** The 5-way tie it broke ({`[0]` `[1]` `[2]` `[3]`
`[5]`}) is not merely a scoring tie — every one of those five options reaches a **byte-identical**
end-of-turn board (same prizes, same Active, same empty hand). The frame's actual content — did you
burn your only disruption Item, or dig for Energy you needed — leaves **no trace on the board the leaf
scores**, because the greedy continuation always ends in Nebula Beam and empties the hand regardless
of what got played first. `leaf_hand_value` (WP-N5b, armed OFF) would not fix this either: both
branches end at 0 cards in hand, so a hand-quality term has nothing left to distinguish. This is a
leaf-discrimination gap that predates this swap and that the tie was hiding — filed for #145/#165 to
pick up, not fixed here.

### `86091435|0|decision|13` (dragapult_ex) — commented on #189, not this issue's fix

Turn 2 setup, no KO reachable by either side. Human ruling: Retreat (`[3]`) — *"wasted Boss's Orders
here. doesnt really make a difference."* Before this swap `[3]` was top at 62.5 (tied with the
correct-flagged decision); after, three siblings gained +2.70 to 64.75 and outscored it by 2.25.

The DECISION is already fixed on `main`, independent of this leaf finding — a separate rung
(`stall-gust-over-dev-when-starved` → `stall_swap_pointless`, ADR-0066) now stands down on this exact
board (its own rationale names `ep86091435 f13` verbatim), so the agent no longer plays the gust the
correction flagged. Full detail commented on **#189** (the gust-marginal repoint issue this frame
touches), since that repoint does not reach this frame's KO-less gust path and should not be read as
covering it.

The residual leaf-level gap (2.25 points on a board where nothing is powered) is left **unruled** —
plausibly below this leaf's resolution rather than a real regression, and not the shape #165's
Maneuver layer targets either. Flagged, not fixed.

### Correction to ADR-0072 amendment C's "9 frames" claim

Amendment C states widening `_engine_leaf_value`'s dominant-win short-circuit from `coins`-gated to
the full `stream` bit costs "9 corpus frames `OK → MISS`" and cites that as the reason not to do it in
PR #184. **Re-measured 2026-07-28: it costs 0, not 7 of those 9** (the other 2 are the pair above,
real). The 7 were an artifact of using `_rng_probe`'s `prize=True` (board) flavour on what the
short-circuit actually asks — a VERDICT question ("did this line win?"). Under `prize=False` (the
flavour `_engine_confirms_win` already uses, per ADR-0050: a win's verdict is invariant to which prize
is taken) all 7 are unchanged, because a winning line always takes its prizes and that reveal alone
was tripping the wider bit on every one of them. ADR-0072 needs a correcting note; the "widen the
short-circuit" item can be reopened as free rather than a 9-frame cost.
