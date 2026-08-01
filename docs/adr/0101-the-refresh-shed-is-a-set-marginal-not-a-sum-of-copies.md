# ADR-0101 — The refresh SHED is a SET marginal over the hand, not a sum over the copies

**Status:** Accepted; **BUILT** 2026-08-01. Build = **Issue #261 (POC-T2) item 2b**, the refresh v2
swap. **Amends [ADR-0065](0065-card-worth-is-one-marginal-oracle-with-a-closure-graph-backend.md)**
(WP-N4b's verdict — *"the refresh site does NOT swap"* — is discharged: it does now, on the POC's
terms rather than on WP-N4b's own bar) and **[ADR-0060](0060-hand-refresh-value-is-a-closed-form-card-swing.md)**
(whose SHED leg this re-denominates for the second and last time). Does not supersede anything.

**Context issues:** Issue #261 (POC-T2, this build), Issue #220 (the refresh v2 swap, absorbed into
T2 item 2b), Issue #222 (STRIP/GIFT keep-cost grading, absorbed into the same item — see
§"STRIP/GIFT"), ADR-0092 (the POC plan: *"the swap IS the deletion"*, flips batch into wave rulings),
ADR-0072 / ADR-0094 (the two gates and the ruling-gated baseline), ADR-0089 (Probe Fate — why the
retired diagnostic's script is deleted rather than left runnable).

## Context

`pilot._refresh_swing_tactical` prices a shuffle-refresh as a closed-form card swing (ADR-0060). Its
SHED leg — *what shuffling my own hand away costs* — has been graded since ADR-0065 as
`Σ keep_cost` over the held copies (`planner._hand_keep`), the same summation the gamble keep-floor
reads.

**A sum is the wrong quantity for a move that sheds the hand jointly.** Two copies of a wincon are
charged twice by a sum, but shuffling both loses *one* plan piece plus its backup — and shuffling
*either alone* loses nothing at all, because the sibling still covers the line. The assignment
successor (`needs.set_keep_v2`, ADR-0065 WP-N2) states exactly that: `V(hand) − V(∅)` under an exact
bitmask-DP assignment of held cards to the board's resolved needs, so duplicates price marginally and
a card covering no live need costs 0 however dear its catalog worth.

WP-N4b built that comparison as a MAGNITUDE shadow (`_refresh_shed_shadow`) and set itself an arming
bar of *"sign-flips ≈ 0"*. The bar was never met — 18 flips at N4b, 13 after WP-N5, 11 after WP-N8,
**16 at this build over a corpus that had meanwhile grown 83 → 96 refresh decisions**. Under the
pre-POC regime that meant "do not swap", and the shadow stayed.

**ADR-0092 replaced that regime.** A POC track does not clear a private bar and then swap; it swaps,
and every frame that moves is ruled by the user in a wave packet against a recorded baseline. The
shadow's arming bar is therefore not the question any more — which is the only reason this swap
happens now, and it is stated plainly rather than dressed up as the bar finally being met. It was
not met. It was retired.

## Decision

**1. The SHED leg IS `needs.set_keep_v2` over the whole shuffled hand.** `_refresh_shed_keepcost`
resolves the held rows (`_needs_hand_rows`, minus one copy of the played refresh — it is discarded,
not shuffled), resolves the board's needs through the shared `_resolve_needs`, discounts each slot by
the closure's odds of re-supplying it inside the refresh's own draw window
(`_refresh_slot_resupply`), and returns the set marginal. The v1 `Σ keep_cost` path at this site is
DELETED. `planner._hand_keep` survives untouched as the gamble keep-floor's own summation — a
different question (one card's floor, not the hand's joint price).

**2. The shadow dies with the swap, and so does its diagnostic.** `_refresh_shed_shadow`,
`Decision.refresh_shadow` and the `refresh_shadow` telemetry key are deleted; `needs_sweep.py` loses
its REFRESH half. Per ADR-0089's Probe Fate the retired half was a RULING, not a re-runnable
diagnostic: it existed to answer *"should the SHED swap?"*, the answer is this ADR, and a probe that
reads a shadow which no longer exists can only report on itself. Its final reading is recorded in
§"As measured" so the deletion loses no evidence.

**3. `_refresh_cycle_adaptive` + `_REFRESH_BENCH_BODY` are deleted as newly-dead surface.** The
adaptive draw credit ("CYCLE should scale to the open bench-deploy need", ep83038055 f40) was
reported *inside the shadow* and decided nothing, so the shadow's deletion left it with no reader at
all. Its promotion question is not lost, it is **re-homed**: a starved bench is priced by T3's
`development` term family, not by a second credit bolted inside this equation. Recording that
re-homing is the point of this decision — an unconsumed reporter left in the tree is the "runnable
script nobody watches" failure one layer down.

**4. Nothing is tuned to make a corpus frame green.** The three regressions all present the same way
— the swing lands within ±3 of zero and `_finish_turn_last`'s `score > 0` promotion turns that sign
into *play before attacking* — and an early draft of this ADR concluded from that they were ONE
mechanism, the near-zero band. **They are not, and the amendment below records what each actually
turned out to be**: an insurance mis-pricing (fixed), a certainty-vs-expectation gap (held out to
#262), and a fitted constant 7% inside its own margin (held out to #272). The shared symptom hid three
different causes, which is exactly why each was dissected rather than threshold-tuned. The standing
rule survives the correction: a threshold moved to make three frames green is what the POC exists to
stop.

## STRIP/GIFT (old Issue #222) — **PARKED, rationale recorded**

Issue #261 item 2b asks the STRIP/GIFT keep-cost-per-hidden-card grading to land in the same swap
*"so the swing's three legs share one grading"*. Issue #222's own charter offers three outcomes —
grill for scope, build, or **park with the rationale recorded**. The third is taken, on measurement.

**This was RULED BY THE USER, not decided by the build.** Issue #222 step 1 is *"grill with the user:
in scope now, or parked for later?"* and ADR-0092 §5 gives a track hitting a doctrine fork exactly one
move — file ONE question. That question was put to the user during the build, with the three options
below and the measurement that motivates the recommendation; the user chose to park. The escape-hatch
budget (≤2 across the POC) is therefore spent once here. The consequence is stated plainly rather than
buried: **item 2b's "the swing's three legs share one grading" is NOT delivered**, and cannot be until
the shared opponent role sheet exists.

Design A (`hand-disruption-grill-spec.md` §"Evidence-gated designs") makes
`_REFRESH_OPPONENT_HAND_STRIP`/`_REFRESH_OPPONENT_HAND_GIFT` an `E[keep_cost per card]` over the opponent's hidden hand, with role
values from the derive-first role sheet (`gusting-keepcost-design.md` §2). That role sheet is
**design-only and unbuilt**, and the consequence is measurable rather than theoretical
(measured at `ccd3a28`, 132 refresh frames):

* the opponent's representative build IS reachable on **115/132** frames (87%) — so the design is not
  vacuous for want of a rep;
* but **59.4% of the cards in that rep price `role_value` = 0**. `_role_value` reads *our* deck's
  declared roles plus the global tag / ACE-SPEC / typed-Energy fallbacks; an opponent's attackers and
  wincons carry none of ours. `E[role_value]` over the rep is **5.67** against the flat GIFT anchor of
  8.0, and that gap is very nearly the missing 59%.

The blindness is **asymmetric in the unsafe direction.** What survives on their side of the ledger is
Energy / gust / recycle / ACE SPEC; what vanishes is exactly their attackers and wincons. Grading
GIFT down by 30% because we cannot see their payoff line makes "Judge into their small hand" look
cheap — which is precisely ADR-0060's CRITICAL correction (ml f111, *"such an enormous blunder"*).
Building the graded leg on this oracle would trade a flat constant for a biased one.

So: the flats stay, and they stay **typed**. They are covered by the ratified
`firing-equation-constants` whitelist entry (`authored-scaffold`, "tolerated for the POC … retires
into the post-POC learning phases") — constants inside an equation whose shape is right, scaling an
answer rather than deciding one. The retirement path is unchanged and now has a named prerequisite:
**design A is buildable the day the shared opponent role sheet exists**, and that layer is
`gusting-keepcost-design.md` §2's, with §5's gust-side re-audit obligations attached — one layer, two
consumers, built once for both rather than half-built here for one.

### The flats are RENAMED to say whose hand they price (review, 2026-08-01)

Parking them is not the same as leaving them as they were. `_REFRESH_STRIP` / `_REFRESH_GIFT` /
`_REFRESH_FRESH` never said *whose hand*, and the natural misreading of "STRIP" is "cards stripped
from ME" — which inverts the sign of the term. They become
**`_REFRESH_OPPONENT_HAND_STRIP` / `_REFRESH_OPPONENT_HAND_GIFT` / `_REFRESH_OPPONENT_HAND_FRESH`**,
and the equation's docstring is re-laid-out by SIDE rather than as a flat list of four lines.

The rename is behaviour-free (both gates and the suite are bit-identical across it), and it records
the structural fact the parking rests on: **the two sides are priced by different means because one
hand is face-up and one is not.** My hand's leg can interrogate each held card; theirs can only ever
be `count × rate`, because `handCount` is all the engine gives us. Two further facts fall out of the
same reading and are now stated in the code rather than left to be re-derived:

* STRIP and GIFT are **one leg split by sign**, not two terms — both read the single signed
  `opp_net`, so `max(-opp_net, 0)` and `max(opp_net, 0)` can never both be non-zero;
* a **one-sided** refresh (Lillie's, Lacey — they shuffle only my hand) zeroes `opp_net` outright, so
  the opponent legs vanish and the swing is exactly `CYCLE − SHED`. That is why frame
  `83969481|0|decision|55` below turns purely on the shed: `20 − 17.8 = +2.2`, with no opponent-side
  term in it at all.

## As measured (2026-08-01, this build)

**The shadow's final reading, before deletion** (96 refresh decisions, at `ccd3a28`): 16 sign-flips;
v2 under-prices the shed on 53, over-prices on 39. The full per-frame table is preserved in this
build's PR body.

**Gates, at `ccd3a28`:**

```
Discrimination Gate   PASS   0 frames moved, 0 unruled          (the leaf never calls this equation)
Decision Gate         2 FIX, 3 REGRESSION — 5 picks moved       agree 250/346 -> 249/346
discard agree_v2      12/12 — unmoved                            (the resolver is shared; it did not drift)
```

Every moved frame is a shadow-measured sign-flip — the swap moved what it was predicted to move and
nothing else:

| frame | old → new | human | mechanism |
|---|---|---|---|
| `83038055\|0\|decision\|40` | `[5] → [0]` | `[0]` | **FIX** — a dead hand sheds cheaper (31.3 → 12.8); the refresh clears |
| `83665798\|1\|decision\|39` | `[3] → [4]` | `[4]` | **FIX** — the hand prices UP (16.4 → 22.5); refresh declined, attack taken |
| `83117367\|0\|decision\|34` | `[2] → [3]` | `[2]` | REGRESSION — shed 30.0 → 33.0 puts Harlequin at −1.0; the attack preempts |
| `83661649\|0\|decision\|30` | `[2] → [0]` | `[2]` | REGRESSION — shed 29.4 → 26.1 lifts Harlequin to +1.9; it preempts the attack |
| `83969481\|0\|decision\|55` | `[4] → [1]` | `[4]` | REGRESSION — shed 21.6 → 17.8 lifts Lillie's to +2.2; it preempts the attack. **Also a committed PIN** — dissected below |

The three regressions go to the **wave-2 ruling packet** exactly as ADR-0092 §5 prescribes; the
Decision Gate baseline is NOT re-captured until they carry verdicts (ADR-0094 enforces the refusal).

**`83969481|0|decision|55` was dissected, because it is the one frame the swap reaches from two
directions** — it is a Decision-Gate regression *and* a committed PIN in
`test_hyperclosure_corpus.py`, whose stated premise is *"Lillie's stands down holding the Wally's
that answers next-turn Nebula — `clutch_heal` worth 20"*. The slot resolution on that board:

```
my_bench=0  active_doomed=FALSE  my_hand=5  opp_hand=7  prizes me/opp = 5/2
  Wally's Compassion (worth 20)  ->  general:1229   value 9.00   keep_v2 9.00
  Mega Signal        (worth 10)  ->  supply_wincon  value 10.00  keep_v2 4.50   resupply 0.73
  Salvatore          (worth 10)  ->  draw_engine    value  8.00  keep_v2 4.28   resupply 0.47
  Cinderace          (worth 12)  ->  (no slot)                   keep_v2 0.00   deploy 0.00
```

v1 charged the Wally's its full tier-20 keep. **v2 gives it a `general` slot at
`20 × _GENERAL_WORTH_W (0.45) = 9.0`** — latent worth, not a live answer — because
`board.active_doomed` is **FALSE**: the `answer_doom` slot reads the CURRENT board, and the threat
the pin names is *next* turn's. So the divergence is real and located, and it is **not** the near-zero
noise the other two regressions are.

Whether it is *wrong* turns on a question this item must not answer alone: **should `answer_doom`
carry a one-turn lookahead?** `_resolve_needs` is the SHARED resolver, so changing it also moves the
discard decider's 12/12 — that is the keep-value resolver's own bench, not a refresh swap's. The pin
is therefore demoted to a strict-xfail TARGET **provisionally**, carrying that question by name, and
the wave-2 verdict decides: *reject* ⇒ fix the resolver and re-promote; *accept* ⇒ delete the TARGET
entry and re-capture. Recording it as a TARGET rather than deleting it keeps the strict-xfail
ratchet: if the frame starts passing again, the suite goes red rather than quietly green.

**Performance, since the shed moved onto the hot path** (it now runs per refresh PLAY option and
inside the develop rollout, where the shadow was `_planning`-guarded out): measured 0.25 ms per call
against v1's 0.32 ms on `ms_…_f94` — the assignment DP is *cheaper* than the per-copy closure
summation it replaced, because the resolver emits few slots (3 on that board) while `_hand_keep`
walks every copy. No guard was needed and none was added.

## Amendment — the wave-2 rulings, and what they bought (2026-08-01)

The user ruled all three regressions **REJECT**. One is fixed here; two are left standing, each for a
reason that is itself a finding.

### `83969481|0|decision|55` — FIXED. A heal insuring the last wincon is not latent worth

The user's ruling, in their words: *"preserve our healer when we only have a single wincon
remaining."* The board bears it out exactly — Mega Starmie ex is Stage 1 from Staryu, **both Staryu
are in the discard and none remain in deck, hand or play**, so the spare Mega Starmie ex in the deck
is stranded and the Active is the last playable wincon; the Bench is empty, so its loss is terminal
(`docs/rules.md` §7 case 2).

`_GENERAL_WORTH_W` (0.45) is a **latency** discount — *"a hand card is ~one deploy away, like a
benched body."* A `clutch_heal` covering an irreplaceable Active is not one deploy away from
mattering; it is the survival plan. `_heal_insures_the_last_wincon` gives it an insurance slot at its
full tier, deadline 1, and the frame goes `Lillie's +2.2 → −8.8` — the agent attacks.

Deadline **1**, not 0, on purpose: the threat is next turn, which is precisely why `answer_doom`
correctly stays shut (`reviewed.json` rules exactly that). The slot nonetheless carries the
answer-doom **kind**, so `_refresh_slot_resupply` gives it **no re-access credit** — the closing
edge, deliberately, which makes the deadline documentary rather than load-bearing here. That is the
point rather than an oversight: the ruling is about **certainty**, and a heal you are relying on to
survive may not be priced at *"I'll probably redraw it."* An earlier draft of this ADR, of the code
comment and of the test all claimed the opposite (that re-access stayed open); the code always did
this, and the prose is now corrected to match it. `needs.insure_wincon_slot` carries the reasoning
so a reader meets it at the constructor rather than three files away. The four gate clauses are in the helper's docstring;
clause 3 (no other wincon body in play) is what keeps `83661649|0|decision|30` — two Mega Starmie ex
in play — out of this slot. **It is deliberately not keyed on an empty Bench**: that fact already
carries `empty-bench-filter` and `_predicted_loss`, and §6 names putting it on the list a third time
as the double-counting error to avoid. This is a different fact, and it prices a held card rather
than gating a move.

The corpus fixture went `PIN → TARGET → PIN` inside this build: demoted when the swap broke it,
XPASSed the strict-xfail once the insurance slot landed, promoted back. That is the ratchet doing its
job, and it is why the demotion was recorded rather than deleted.

### `83117367|0|decision|34` — HELD OUT. The shed is risk-neutral; the ruling is about certainty

**Resolved 2026-08-01 by user ruling: held out onto T3/T4** (`ms_heldout_refresh_certainty_vs_
expectation_f34.json`). The verdict is REJECT — the agent should play Harlequin — and the finding is
that no setting of the refresh SHED can deliver it without breaking `ep83037962 f49`.

**The two frames are the same board to the shed.** Opponent hand 7 on both ⇒ STRIP +12 on both ⇒
both decline iff `shed > 32`. The user ruled them opposite ways. Two fixes were built and reverted,
and neither holds both:

| | f34 | f49 |
|---|---|---|
| succession value `30 → 15` | 33.0 → 16.5, **plays** ✓ | **plays** ✗ |
| succession re-access `0 → 0.77` | 33.0 → 16.5, **plays** ✓ | 46.1 → 24.1, **plays** ✗ |

The two Basic `{W}` do not rescue f49, and the model is not miscounting them: they price `2.49` each
because 8 Energy outs in a 43-card pool over 5 draws is a 66% recovery, so the fund-attack slot
discounts to 31% of tier.

**The axis is certainty, not magnitude.** The shed is a **risk-neutral expectation** — it prices a
79%-recoverable Mega Starmie ex at 79% recovered. The user's f49 reasoning is a **risk** calculation:
*"in our hand is what we need to respond to the possible KO with a new Starmie with energy, that
GUARANTEE is what we risk."* The odds confirm the preference rather than the pricing: ~40% to redraw
both pieces, against ~15pp of KO reduction (their Ignition → Nebula Beam 210 is exact lethal on a
210 HP Active; 3 unseen in a pool of 45 ⇒ 45.2% at hand 8 vs 30.4% at hand 5). The old
`resupply = 0.0` closing edge was a crude proxy for that preference — it over-fires on f34, where the
card has 8 outs at 67% and the rest of the hand is dead.

Expressing *guaranteed vs expected under an imminent KO* is variance, which belongs to the gamble
machinery (ADR-0039) and T3's `state_value`, not to a slot's resupply term.

**A doom-read theory was tested and REFUTED**, recorded so nobody re-runs it: `active_doomed` is True
on f34 and is *not* a worst-case artifact. The opponent is Kyogre / Mega Abomasnow ex (Read
confident, 2× Kyogre benched), Hammer-lanche `{W}{W}` is payable with the 2 already attached, and the
representative build puts **29 Basic `{W}` in 44 unseen (66%)** — so its *expected* roll is ~300–395
against a 330 HP Active. Both frames are genuinely doomed; doom does not separate them.

The historical conflict this replaces is kept below, because the reasoning that led here matters.

#### (superseded) The ruling conflict as first diagnosed

The measured defect is real: the held Mega Starmie ex takes the URGENT succession slot at full tier
30 with `resupply = 0.0` — the slot **asserts P(re-access) = 0** where the closure counts **8 outs**
(3× Mega Signal, Ultra Ball, Hilda, plus the card itself) at **67.3%** this turn / 74.4% by next
turn's draw. Both benched Staryu arrived this turn, so the card cannot legally be played at all
(`docs/rules.md` §4; the engine offers no option for it).

Narrowing the spike to a base evolvable **this turn** was built, and it works — f34 flips to the
human's `[2]` Harlequin, and Harlequin (+15.5) beats Lillie's (+2.8) on the merits rather than by
assertion. **It was then reverted**, because `line_slots`' own docstring rules the turn-fresh case
head-on for `ep83037962 f49`: *"don't Harlequin away the second Mega Starmie **the turn its Staryu
hit the bench**."* Both frames have a doomed Active, a second Mega Starmie ex in hand, and a Staryu
benched this turn. The rulings disagree, and the distinction — f49's Active is at 210/330 and
genuinely dying, f34's is undamaged at 330/330 — is not one `active_doomed` can express, since the
worst-case ceiling reads both as doomed.

**This is a ruling conflict, not a defect**, so it is recorded rather than patched. Resolving it
means either distinguishing the two frames on a fact the model can see (a graded doom, not a
boolean), or re-ruling one of them. `reviewed.json` already disposes f34 `covered` on the grounds
that *"Harlequin-vs-Lillie's is a supporter-priority value judgment… not the blunder"*, which argues
the conflict may dissolve on re-reading rather than needing new machinery.

### `83661649|0|decision|30` — HELD OUT. A fitted constant sitting 7% inside its own margin

**Resolved 2026-08-01 by user ruling: held out onto the joint `W`+`r` re-measure**
(`ms_heldout_refresh_general_worth_margin_f30.json`). The verdict is REJECT — attack with Jetting
Blow, as the correction states.

All three held cards cover exactly one `general` slot each, so the shed **is** the haircut sum:

```
Ignition Energy  30 x 0.45 = 13.5
Basic {W}         8 x 0.45 =  3.6
Wally's          20 x 0.45 =  9.0
                            -----
                             26.1   <- the shed, exactly   (v1 charged 29.4)
```

The whole `−1.4 → +1.9` flip is `_GENERAL_WORTH_W = 0.45`. The swing declines iff `shed > 28.0`, i.e.
`58 × W > 28`, i.e. **`W > 0.483`** — the frame sits **7% away from a fitted number**.

**Not re-fitted here, deliberately.** `_GENERAL_WORTH_W` was measured (WP-N5: under-pricing 46→19
came from W alone) and `_refresh_slot_resupply`'s docstring carries the standing instruction *"Re-open
only as a JOINT re-measure of W and r, never r alone."* Moving W to satisfy one frame is the
rung-fitting this POC exists to delete, and it would move every keep-value site including the discard
decider's 12/12.

**Two theories tested and refuted**, recorded so the owner need not re-run them:

- the deferred **non-Active fund bodies** leg — the bench holds a 2nd Mega Starmie ex on 1 `{W}`
  needing 3, so fund slots were prototyped for benched bodies: `shed 26.10 → 26.10`, **no movement**.
  The Energy already sit on general slots worth more than `ENERGY_TIER` 8, so the assignment does not
  re-route them.
- the **insurance slot** (which fixes f55) — correctly declines here: a second Mega Starmie ex sits
  undamaged on the Bench, so the line survives the Active's KO and nothing irreplaceable is insured.

An earlier draft of this section blamed `_finish_turn_last`'s information-before-commitment boundary.
That was wrong and is retracted: the boundary is what converts a positive swing into a pre-attack
play, but the *sign* is the constant's, and the constant is the thing 7% off.

## Consequences

- **The refresh and the forced discard now share one price.** `_resolve_needs` had two consumers with
  two verdicts (v2 decides the discard, v1 decided the refresh); it has one. A future slot
  adjudication moves both together, which is the point of a shared resolver and was not true before.
- **The near-zero band is now visible and owned.** Three of five moved frames turn on a swing within
  ±3 of zero being read as a play/don't-play sign by `_finish_turn_last`. T4's differencing replaces
  that promotion outright; until then the band is a named, ruled property rather than an unexamined one.
- **`Σ keep_cost` no longer has two jurisdictions.** `planner._hand_keep` is the gamble keep-floor and
  only that. ADR-0065's "one summation for both sites" claim is retired by this ADR, deliberately: the
  sites were asking different questions and sharing an answer.
- **One acceptance line of Issue #261 is discharged early**: the refresh contributes zero shadow
  emitters and zero OFF value flags.

## Alternatives rejected

- **Hold the swap until sign-flips reach ≈ 0.** WP-N4b's bar, and it has now failed four measurements
  across three amendments while the corpus grew under it. ADR-0092 replaced the bar with wave rulings
  precisely because a private arming bar defers indefinitely and answers to nobody.
- **Keep the shadow after the swap, as a v1-vs-v2 regression witness.** It would compare the decider
  against a deleted path — the shape ADR-0072 killed for `*_decider_sweep.py` ("a gate must diff
  against a RECORDED baseline, never a live switch"). The Decision Gate is the witness.
- **Tune `_finish_turn_last`'s promotion floor, or add a dead band to the swing, to recover the three
  regressions.** Fits a threshold to three corpus frames, and would silently re-price every other
  equation the floor gates. Named in decision 4 instead, and left for T4.
- **Build STRIP/GIFT design A on today's `_role_value`.** Rejected on the 59.4% measurement above —
  it swaps a flat constant for a biased one, in the direction of ADR-0060's CRITICAL correction.
