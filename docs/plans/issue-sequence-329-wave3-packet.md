# Wave-3 packet — issue-sequence run (329, 332, 362, 351, 350, 349, 374, 375, 372)

> **RULED 2026-08-04.** Every frame in this packet now carries a developer verdict. The answers
> live in [`data/leaf_lab/pr359-rulings.md`](../../data/leaf_lab/pr359-rulings.md) - 1 REFUTED,
> 5 REVERT. Neither baseline was re-captured. Note two corrections recorded there: this packet's
> flip list is NOT the gate's unruled list (it records only flips this batch caused), and
> `83661649|0|decision|54` was never unruled - it already carried a standing `covered` ruling.

Gate flips from this batch, pending developer ruling. None conformed into either baseline.json —
a baseline is a ruling record, not something a sub-issue may recapture on its own recognisance.

## Flips

| frame | gate | issue | old | new | recommendation |
|---|---|---|---|---|---|
| `82752604\|0\|decision\|88` | leaf (Discrimination) | Issue #329 | OK, rank 1/n | MISS, rank 2/n | **RULE, do not conform.** Predicted by the issue body from the reverted /3.0 measurement; reproduced under /3.9. |
| `85785606\|0\|decision\|19` | leaf (Discrimination) | Issue #329 | OK, rank 1/n | MISS, rank 2/n | **RULE, do not conform.** Same class; the reverted measurement's worked example. |
| `85785606\|0\|decision\|21` | leaf (Discrimination) | Issue #329 | OK, rank 1/n | MISS, rank 2/n | **RULE, do not conform.** Same class. |
| `82752045\|1\|decision\|94` | leaf (Discrimination) | Issue #329 | `IMPROVED MISS -> OK` | back to the baseline's `MISS` | **Informational — not a regression against the baseline.** A windfall improvement lost. NOT predicted by the stale measurement; this is the one frame the re-take found that /3.0 did not. |
| `85058574\|1\|decision\|88` | leaf (Discrimination) | Issue #329 | `IMPROVED MISS -> OK` | back to the baseline's `MISS` | **Informational.** Predicted; reproduced. |
| `85785609\|0\|turn\|8` | leaf (Discrimination) | Issue #329 | `IMPROVED MISS -> OK` | back to the baseline's `MISS` | **Informational.** Predicted; reproduced. |
| `82229122\|0\|decision\|17` | leaf (held out, `owner=#263`) | Issue #329 | resolved by Issue #284, passing | REGRESSED again, rank 1 -> 2 | **No action — and it VINDICATES the ruling.** Issue #284's L1 recommended KEEPING this `owner=#263` ruling rather than retiring it because the frame had started passing; the developer ruled **KEEP both**. It now fails again, so retiring it would have been wrong. |
| `82228017\|0\|decision\|4` | leaf (held out, `owner=#263`) | Issue #329 | REGRESSED, rank 1 -> 2 | REGRESSED, rank 1 -> 3 | **No action.** Already ruled and held out; only the rank deepened. |
| `81904451\|0\|decision\|9` | leaf (Discrimination) | Issue #332 | OK, rank 1/n | MISS, rank 2/n | **RULE, do not conform.** A body the discount newly refuses to fund. |
| `83457493\|1\|decision\|20` | leaf (Discrimination) | Issue #332 | OK, rank 1/n | MISS, rank 2/n | **RULE, do not conform.** Same class. |
| `83661649\|0\|decision\|54` | leaf (Discrimination) | Issue #332 | OK, rank 1/n | MISS, rank 5/n | **RULE, do not conform.** Same class, and the deepest of the three. |
| `82228640\|0\|decision\|53` | leaf (Discrimination) | Issue #332 | `IMPROVED MISS -> OK` | back to the baseline's `MISS` | **Informational — not a regression against the baseline.** A windfall improvement lost. |
| `82525741\|0\|decision\|58` | leaf (Discrimination) | Issue #332 | `IMPROVED MISS -> OK` | back to the baseline's `MISS` | **Informational.** Same class. |
| *(not a frame)* `test_PLAYING_the_boost_card_…` | **no gate** — a sibling issue's acceptance test | Issue #329 vs Issue #282 | `total_after > total_before` (+0.016667) | positional half is **−0.032051** | **RULING DISCHARGED 2026-08-04 — ACCEPT the rewrite.** Temporary underplay of enabling cards is accepted; no ladder submission before Issue #263's turn composer lands. |
| `82749168\|1\|decision\|88` | leaf (held out, `owner=#332`) | Issue #362 | REGRESSED, rank 1 -> 4 | **FIXED**, back to the baseline's `OK` rank 1 | **No ruling owed — it is a build.** The issue's headline frame. Recommend the held-out entry STAY (Issue #284's L1 precedent: `82229122\|0\|decision\|17` started passing, was kept, and now fails again). |
| `82523164\|1\|decision\|75` | leaf (held out, `owner=#263`) | Issue #362 | REGRESSED, rank 1 -> 5 | **FIXED** | **No ruling owed.** Same cause, same class — see the four measured frames below. |
| `82524455\|1\|decision\|55` | leaf (held out, `owner=#263`) | Issue #362 | REGRESSED, rank 1 -> 2 | **FIXED** | **No ruling owed.** Same class. |
| `82522698\|1\|decision\|62` | leaf (held out, `owner=#263`) | Issue #362 | REGRESSED, rank 1 -> 2 | **FIXED** | **No ruling owed.** Same class, the narrowest margin of the four (400.7). |
| `85046350\|0\|decision\|85` | leaf (Discrimination) | Issue #351 | OK, rank 1/10 | MISS, rank 3/10 | **RULE, do not conform.** The ONE unruled flip this issue adds. An all-Bench attach menu (`dragapult_ex` t8, 5 attach targets); the legality gate zeroes the now-leg on every benched body, so the five are now ranked by the FORWARD clock alone — which is also where Issue #332's survivability discount rides. First frame where both corrections compose. Margin is **1.12 leaf points** (correct -249.1139 vs top -247.9933), against a pre-gate margin of 0. |
| `82752604\|0\|decision\|88` | leaf (Discrimination) | Issue #351 | MISS (Issue #329's unruled flip, row 1 of this table) | **FIXED**, back to `OK` | **No ruling owed — it is a build.** The gate RETIRES one of Issue #329's three unruled flips. Recommend the row above stay on the ledger anyway (Issue #284's L1 precedent: a frame that starts passing may fail again). |

**Decision Gate: PASS, and the before/after reports are byte-identical** — `agree 250/347 -> 250/347`,
**0 picks moved, 0 rulings moved**, 24 voided. No shipped decision changes; this is the leaf's
isolated ranking, which Issue #263 (T4) is what makes live.

## Issue #329 — the anchor, and the measurement the issue body asked for

### Gate arithmetic

| | before | after |
|---|---|---|
| unruled `OK -> MISS` | 1 | **4** |
| ruled / held out | 65 | 66 |
| voided | 3 | 3 |
| `IMPROVED MISS -> OK` | 17 | **14** |
| leaf picks `correct` (SOLE top) | 34/249 (14%) | 30/249 (12%) |
| shared-top | 130/249 (52%) | 123/249 (49%) |
| Decision Gate | PASS, 0 picks moved | **PASS, 0 picks moved, byte-identical** |

The `1` in the before column is Issue #280's `81906755|1|decision|9`, already ruled **REVERT** in the
closed packet (`docs/plans/issue-sequence-281-wave3-packet.md`, and Batch 8 of
`data/leaf_lab/wave3-rulings.md`). It is not this issue's and is not re-tabled above. So this issue's
own contribution is **+3 unruled and −3 improvements**.

### The open question the stale measurement could no longer answer

Issue #329's body records a first attempt on branch `claude/issue-262-w0l5xt` that implemented the
anchor as `_THREAT_CAP / _MAX_PRIZE_VALUE` (3.0) and was reverted:

```
unruled OK -> MISS   65 -> 68     (+3: 85785606|19, 85785606|21, 82752604|88)
MISS -> OK           18 -> 16     (-2: 85058574|88, 85785609|turn|8)
```

That measurement predated Issues #281, #284 and #285, and the body required it to be **re-taken**
rather than trusted. Re-taken here, under the **/3.9** divisor that actually shipped:

| | reverted /3.0 attempt | this build, /3.9 |
|---|---|---|
| new unruled `OK -> MISS` | +3 | **+3 — the same three frames, by name** |
| `MISS -> OK` lost | −2 | **−3** |
| named frames that reproduced | — | 5 of 5 |
| frames the old measurement did not name | — | **1: `82752045\|1\|decision\|94`** |

So the answer is: **landing after Issues #281, #284 and #285 did not rescue any of the five named
frames, and /3.9 costs one improvement more than /3.0 did.** That is the direction the issue body
predicted —
*"3.9 scales harder than the 3.0 that produced those numbers (a 1-prize target reads 0.0256 rather
than 0.0333), so the windfall is removed more aggressively, not less."* Predicted, then measured, then
found to hold.

### Why these frames flip, and why removing the windfall is still right

Each was winning by a margin **smaller than the threat advantage the saturation was handing it**. Under
the un-anchored form every reachable target — a 1-prize Basic or a 3-prize Mega ex alike — priced at
the full `_THREAT_CAP` 0.1. Under the anchor a 1-prize target reads 0.0256, a 2-prize 0.0513, a
3-prize 0.0769. A frame carried by a 1-prize target therefore loses 0.0744 prizes of phantom credit.

The information being removed was never real: measured over one full leaf pass, **614 non-empty
inputs spanning 33 distinct sums produced exactly 2 distinct outputs**. The equation was destroying
the discrimination at the call. Removing that is correct **and** it costs rulings, and an equation
does not get to write its own verdicts — which is why these are tabled rather than conformed.

### What was measured, and the controls

Every number above is reproducible. The instrument is a module-global rebind of `state_value.threat`
(`state_value.py` calls it by name), with `assert CALLS` as the positive control — a leaf pass that
never reached `threat` would otherwise report a clean zero.

| | |
|---|---|
| `threat()` calls, one leaf pass | 2061 |
| non-empty inputs | 614 |
| distinct OUTPUT values — **before** | **2** (`0.0` x1447, `0.1` x614) |
| distinct OUTPUT values — **after** | **29** (28 non-zero + `0.0`) |
| distinct INPUT sums | 33 (min 1.0, max 5.0) |
| cap binds — before / after | **614/614** / **45/614 (7.3%)** |
| target-count distribution | `{0: 1447, 1: 540, 2: 72, 3: 2}` |

Two legs re-measured with severance controls (the leg forced to `0.0`, per-call values diffed).
**Both columns are in `threat()` CALLS over the same 2061-call pass, so they are comparable.** The
before-column is derived exactly rather than re-run: under `min(_THREAT_CAP, sum)` a call's output is
`0.1` for every non-empty input and `0.0` otherwise, so a leg could move the OUTPUT only by changing
whether the input was empty at all.

⚠️ Issue #284's own published figures — 904 asks, 338 live reaches, **13 moves** — are denominated in
corpus FRAMES, not calls. They are not the before-column here and must not be read as `13 -> 336`.

| leg | before (calls) | after (calls) |
|---|---|---|
| Issue #284's bench widening | **278** of 2061 — every one an empty input becoming non-empty, i.e. `0.0 -> 0.1` | **336** of 2061, by 0.023–0.077 prizes. The extra **58** are exactly the boards where the Active leg already read something — the case the cap erased |
| Issue #285's denial credit | **0** of 2061 — a credit cannot make an empty input non-empty, so the cap erased this leg completely | **296** of 2061, by 0.000115–0.002192 prizes (327 of 614 inputs change; 31 are absorbed by the guard) |

**`tests/strategy/test_leaf_profile.py` confirmed rather than assumed**, as the issue asked: its three
`<=` ceilings are on declared READ FIELDS (the `theirs.bench.*` block), not on any family's output
range, and `threat`'s output range is unchanged at `[0, _THREAT_CAP]`. Nothing to move; file
untouched. Positive control for that sweep: `threat` does appear in the file (3 times), so the
instrument was not silently looking at nothing.

### One question for the developer, if 7.3% is judged too high

The runaway guard still bites on 45 of 614 non-empty inputs. That is structural, not residual:
`threat` is a SUM over up to six targets while `TARGET_VALUE_CEILING` is ONE target's ceiling, so a
board where a 3-prize Mega ex *and* a 2-prize body are both reachable sums to 5.0 — 1.28x the divisor.
Five prizes of simultaneously-reachable exposure is exactly the extreme board a runaway guard is for,
so **no change is recommended**. The honest alternatives, if the developer disagrees, are (a) divide
by `_MAX_BODIES x TARGET_VALUE_CEILING`, which is derived but flattens the common single-target case
to near-nothing, or (b) change the composition from a sum to a max-with-discount, which is a
frozen-composition change. **Neither is taken here, and no new constant was invented.**

### A sibling issue's acceptance assertion inverted — RULING DISCHARGED 2026-08-04

**No gate reports this, which is exactly why it is tabled.** Flagged by `/code-review`'s Spec axis as
the one thing in this run that resembles conforming rather than ruling.

`tests/strategy/test_state_value.py::test_PLAYING_the_boost_card_is_priced_as_a_gain_and_not_as_the_hand_loss`
(Issue #282) asserted that playing Premium Power Pro is a net gain on the `_PLAY` transition. Its
+0.016667 margin was `0.1` of saturated `threat` against a `0.083333` hand hold. Under the anchor a
2-prize Dragapult ex prices `_THREAT_W x 2 = 0.051282` and the positional half of that transition
reads **−0.032051**. So Issue #282's headline acceptance — *"a Trainer damage-boost must not price as
a hand loss"* — is now **false on `state_value` alone**, and true only once the terminal action is
included.

That is not a regression; it is the double-count `_THREAT_CAP` exists to prevent. `threat` prices the
exposure STANDING on the board and the prize for CONVERTING it is `attack_ev`'s, under
`score = state_value(end board) + EV(terminal action)`. A boost played and never cashed genuinely is a
spent card for a position; the old form paid the conversion prize twice and called the difference a
gain. The test is renamed `..._is_priced_as_the_BOOST_and_not_as_the_hand_loss` and made stronger — it
now pins the positional half to the float, asserts the boost recovers 0.051282 of the card's cost
where an unpriced effect recovers none (the epic's actual sentence), and asserts the play is a gain
outright on the full sequence score.

**Three dispositions are available and the ruling should name one:**

1. **ACCEPT the rewrite** (recommended) — the sign is correct and the old margin was a windfall of
   exactly the class this issue removes. Nothing further changes.
2. **Treat the sign as a cross-family calibration finding.** A gust-tier held card is worth 0.083333
   prizes, which exceeds `threat`'s entire SINGLE-target range (max 0.076923), so under the anchor no
   single-target reachability gain can pay for a gust-tier card out of hand on the positional half
   alone. That is a `hand`-vs-`threat` banding question. **Not acted on here**: `hand`'s equation is
   corpus-ruled and `threat`'s divisor was just settled, so this track may retune neither.
3. **REVERT the anchor** if the developer judges Issue #282's acceptance the stronger commitment.

**Nothing was retuned to accommodate any of this**, and the rewritten test is strictly stronger than
the one it replaces — it would fail under a boost that stopped being priced, which is the property
Issue #282 actually exists to guard.

**Developer ruling 2026-08-04:** Option 1, **ACCEPT the rewrite**. `state_value` must not include the
prize value of cashing an attack boost; that belongs to `attack_ev` under Issue #263's
`score(sequence) = state_value(end board) + EV(terminal action)` composer. The temporary gap is
accepted: enabling cards such as Boss's Orders or Premium Power Pro may be underplayed until Issue
#263 can rank the whole turn line, and the agent will not be submitted to ladder before that lands.

## Issue #332 — `readiness` funded the Active over the benched successor

### What was built

`_readiness_odds`' FORWARD leg is now discounted by the body's own survival clock —
`1 - halve(turns_to_ko_me - 1)`, the exact complement of the grade `survival` already puts on the
same clock, through the same newly-extracted `_survival_clock` call so the two families cannot come
to disagree about when a body dies. The NOW leg is untouched: a payoff cashed on MY turn happens
before the opponent's, so a body about to fall still swings and owes no discount. Nothing was
retuned; `attach_value` (ADR-0069) is structurally unreachable from this module and its own suites
(`test_attach_decider.py`, `test_attach_bands.py`, `test_attach_discipline.py`) pass unchanged.

### Gate arithmetic — attributed against a BEFORE control, not against Issue #329's table

The before column is a real re-run with `_survives_to_spend` forced to `1.0`, so these three flips
are this issue's own and not inherited.

| | before (Issue #329's end state) | after |
|---|---|---|
| unruled `OK -> MISS` | 4 | **7** (+3, named above) |
| `IMPROVED MISS -> OK` | 14 | **12** (−2, named above) |
| held-out set | 80 | **80 — unchanged, no frame gained or lost an owner** |
| leaf agree | 123/249 | 122/249 |
| Decision Gate | PASS, 0 picks moved | **PASS, 0 picks moved, 0 rulings moved** |

`⚠️ corpus shape moved: +1 / -1` appears on BOTH columns and is not this issue's: it is
`85709280|1|match|` → `85709280|1|decision|51`, the re-scope committed at `819ffc4e` before this
branch started. **No baseline was re-captured for it.**

### The two frames the issue was filed on

| frame | before | after |
|---|---|---|
| `83037962\|0\|decision\|48` | `OK -> MISS` — `readiness` the SOLE decider at −0.0184 | **FIXED.** No family is a decider; the leaf no longer prefers the doomed Active. |
| `81906755\|1\|decision\|93` | `OK -> MISS`, `readiness` −0.0118 | **STILL MISS**, `readiness` −0.0063. Improved by 47% and not flipped. |

**Frame 93 is not the same decision as frame 48, and the issue body's *"they are the same decision
twice"* does not survive re-measurement.** Frame 48's Active reads `turns_to_ko_me == 1` and the
developer's rationale is explicitly a survivability argument (*"active doomed mega starmie … therefor
should start powering up our reserve benched staryu"*). Frame 93's Active is **undamaged at 330 HP
with a clock of 3**, and the developer's rationale is the generic *"attach energy when able and
pokemons need it"* — a ruling against the AGENT's choice, which was to **attack** (option 10), not
against attaching to the Active. Both of the leaf's candidates on that frame are attaches, so the
ruling does not discriminate between them at all. What remains is a geometric-decay effect with no
survivability content: one attach moves a body already at `halve(2)` more than one at `halve(3)`,
and the Active's payoff is 2.1 prizes against the Staryu's 0.2. **Recommend RULING frame 93 rather
than chasing it** — the acceptance criterion allows either, and no survivability reading can flip it.

### The two frames NO family explained — both answered

* **`86089617\|1\|decision\|4`** (`End` vs `Gravity Mountain`) — the issue's hypothesis is
  **CONFIRMED and is not the whole story**. `development` reads exactly `0.0000` across the Stadium
  play, which is precisely what `development.blind_to` says (*"`model.stadium` has a supplier and no
  reader"*, owner Issue #263). What actually decided the frame was a sub-floor `readiness` wobble of
  −0.0022 — below `family_diag`'s 0.005 decider floor, which is why the run reported no decider. The
  survivability discount removes it, `readiness` now reads `+0.0000`, and **the frame is FIXED.**
* **`82749168\|1\|decision\|88`** (`Nebula Beam 210` vs `Harlequin`) — **not noise, and not a term at
  all.** The ruled option's line **WINS THE GAME** in the sim, so it never reaches the board branch of
  `_engine_leaf_value`: it takes the dominant-win short-circuit `KO_SCORE * (start_prizes + 1)` and
  scores a flat **2000**, tied with the eight other options that also win once the rollout finishes
  the turn. `Harlequin` scores **6789.9** through the ordinary board branch, because
  `state_value`'s `prize_race` lead leg is UNIT-SLOPE and deliberately uncapped. The winning board's
  own `state_value` is **6.909985 prizes = 6910**, which would have ranked it FIRST. So the
  short-circuit is not failing to help — **it is what causes the misranking**, and its comment still
  reads *"dominant"*.

  Swept over the corpus: **26 of 361 frames reach a coin-free simulated win** (the positive control),
  and on **4** of those a non-winning option out-scores it, by up to 4789.9 leaf points. Spun off as
  **Issue #362** rather than built here — different module, its own magnitude decision to derive
  (`LOSS_PRIZES` is the mirror constant and there is no `WIN_PRIZES`), and bundling it would have made
  these three flips unattributable. **No ruling is owed on this one; it is a build.**

### The double-count question, argued rather than assumed

Issue #332's first acceptance criterion. `readiness_odds` now consults `turns_to_ko_me`, which
`survival` prices, and the one-fact-one-family rule is `state_value`'s headline. The call is made and
recorded in three places (`_survives_to_spend`'s docstring, `readiness.composition`, and
`test_the_clock_consultation_is_not_a_second_claim_on_a_priced_fact`):

* The two families price two different **consequences** of the one fact in two different currencies —
  `survival` charges the `prize_at_risk` handed over when the body falls, this discounts the
  damage-denominated `payoff` that dies with it. Removing the body raises one family and lowers the
  other, so it is not one quantity added twice.
* The registry fact stays `readiness_odds`, already in `readiness.reads`; the clock is an INPUT to
  that probability exactly as `turns_to_afford` is. `double_counted()` stays empty and MEANS it.
* This is `survival`'s own shipped precedent applied to the mirror case: its `_predicted_loss`
  consults `prize_race`'s `their_prizes_remaining` as a win-condition TEST and keeps `predicted_loss`
  as the registry fact. **Splitting the clock into a second fact string to make the read visible is
  the move both places reject** — `sound_rules.SCHEDULED_PAIRS` records the same temptation and the
  same answer, because a fact renamed to dodge a detector makes the detector pass vacuously.

### One thing the developer may want to overrule

The discount reaches **exactly 0** at a clock of 1, and a term with no derivative is never explored
under 1-ply differencing — a hazard this module names four separate times. It is argued as a PRICED
zero rather than a pruning one: the zero is on one leg of one body, every play that arms that body
THIS turn still moves the now-leg, and a play that only advances a doomed body's future arming
genuinely buys nothing. **Measured consequence on a sibling's test:** Issue #286's
`test_the_going_first_shape_an_IGNITION_onto_a_BASIC_now_buys_nothing_forward` runs on a 70 HP Staryu
against a funded Phantom Dive — clock 1 — so its `ign == bare` equality now holds at `0.0 == 0.0`
rather than at `0.000375`. The test still passes and its non-vacuity guard (`bare < water`, carried by
the now-leg) still fires, **and it was not edited**. If the developer prefers a strictly-positive
grade, `1 - halve(clock)` is the one-character alternative — and it was MEASURED rather than argued
about: under it `83037962|0|decision|48` reads `readiness −0.0064` and stays a MISS,
`81906755|1|decision|93` reads −0.0090 (against −0.0063 as shipped), and `86089617|1|decision|4`
reads −0.0011 instead of flat. **It fixes none of the three.** The shipped grade is the one that
buys the two fixes, which is why the zero is taken rather than softened.

## Issue #362 — the leaf's dominant-WIN short-circuit was out-scaled by the board scalar

### What was built

`_engine_leaf_value`'s coin-free-win short-circuit paid `KO_SCORE * (start_prizes + 1)` — prizes
already BANKED when the line began, plus one. It now pays `KO_SCORE * state_value.WIN_PRIZES`, a
constant DERIVED the way `LOSS_PRIZES` is: the largest sum the families can express on any legal
board, plus one strict prize of headroom. `survival` and its `_MAX_BODIES x _MAX_PRIZE_VALUE` bound
are the two summands the loss side has and this one does not — `survival` is non-positive by
construction, so it can never push a board UP toward the win band, and the terminal charge here
REPLACES the scalar rather than sitting inside a family that has to out-dominate its own sum.
`WIN_PRIZES` = 10.9 prizes = 10900 on the leaf axis, against `LOSS_PRIZES` 28.9.

`gate0_ab.py` and `transposition_probe.py` both re-implemented the old magnitude and now IMPORT the
constant. Their **non-win** branch is still the retired hand-composed `_leaf_value`, so both of their
columns have been grading a leaf the agent stopped using at the POC-T3 swap; the comment says so
rather than letting the import imply otherwise. Not fixed here — a different subsystem, not this
issue's, and bundling it would have made this gate diff unattributable.

`sound_rules.py`'s ratified `ko-score-band` entry gained the win half. Its own closing sentence —
*"a whitelist that describes a band the code abandoned is worse than one that says so"* — is why:
the band now has TWO terminal constants and the entry named one.

### Gate arithmetic — attributed against a BEFORE control on the same tree

The before column is a real `leaf_lab diff` run at `5f44bd86` (Issue #332's end state), not a
remembered table.

| | before (Issue #332's end state) | after |
|---|---|---|
| unruled `OK -> MISS` | 7 | **7 — the SAME seven frames, by name. Zero new flips.** |
| held-out `OK -> MISS` | 63 | **59** (−4: the four named above) |
| total `ok_to_miss` rows | 74 | **70** |
| `IMPROVED MISS -> OK` | 12 | **12 — unchanged** |
| held-out SET / voided SET | 80 / 24 | **80 / 24 — unchanged, no frame gained or lost an owner** |
| leaf agree | 122/249 | **126/249** (+4 — exactly the four fixed frames) |
| Decision Gate | PASS, 0 picks moved | **PASS, `agree 250/347 -> 250/347`, 0 picks moved, 0 rulings moved** |

So this issue costs the packet nothing and pays four frames back. Everything above the gate line is
Issues #329's and #332's, already tabled.

### The premise, re-verified at `HEAD` before any edit

Issue #362 is SELF-FILED (the Issue #332 subagent wrote it), so its numbers were re-measured rather
than trusted. Re-implementing both branches of `_engine_leaf_value` around the real `_simulate_line`:

| claim | verdict |
|---|---|
| `82749168\|1\|decision\|88` win short-circuit = **2000.0** | reproduced exactly |
| out-scored by opt 1 (`Harlequin`) at **6789.9** | reproduced (6789.9421) |
| the winning board's own `state_value` = **6910** | reproduced (opt 8, 6909.9849 = 6.909985 prizes) |
| **4** frames out-scored by a non-win | reproduced — the same four, same margins |
| **26** frames reach a coin-free simulated win | reproduced |
| **361** frames swept | **did NOT reproduce — the number is 371** (372 corrections carry an obs; one agent, `SkiChu`, has no `strategy.py`). Off by 10; changes no conclusion, since both numerators reproduce. |
| *"tied at exactly 2000 with **eight other** options"* | **off by one — there are 8 winning options, so 7 others.** The `8` is the BASELINE row's `top_tie`, not the current count. |
| *"the leaf ranks it 10th of 11"* | reproduces only under an index-tiebreak read (3 options score above 2000; the ruled option is the 7th of the 8 tied at 2000). `leaf_lab`'s own `correct_rank` is **4**. |
| *"`start_prizes` is prizes **already banked** when the line began"* | **FALSE, and it is the one error that reached shipped prose.** See below. |

Positive control on every sweep: the win-frame count is asserted non-zero, because a sweep that never
reached the win branch would report "0 of N out-scored" and be indistinguishable from a fix. The
sweep is now a committed instrument — `tools/train/probes/win_band_sweep.py`, which carries that
assertion in code and whose `--legacy` mode re-derives all four failures by name, so the headline
numbers are re-runnable rather than remembered.

### The one FALSE claim in the self-filed issue, and what it changes

Caught by `/code-review`'s Spec axis on the brief this repo's self-filed-issue rule requires. Issue
#362 asserts *"`start_prizes` is prizes **already banked** when the line began"*, and the first draft
of this build copied it into four shipped docstrings. It is backwards. `_simulate_line` computes
`start_prizes = len(me.get("prize") or [])` — the face-down zone — which is the identical expression
`state_model.prizes_remaining` uses (*"Prizes this side still needs to take"*); `prizes_taken` is a
separate accessor with a different formula, and both probes' own `taken = start_prizes - len(end
prize)` only type-checks under the REMAINING reading.

So the retired magnitude was not merely too small, it ran **BACKWARDS**: it paid a win 7000 with six
prizes still to take and 1000-2000 with the win one turn from landing. That is why the worst frame in
the table is `82749168|1|decision|88` — one prize remaining, the position closest to victory, drawing
the second-smallest payout the formula could produce. The verdict is unchanged and the fix is
unchanged; the shipped REASON was stating the reverse of the code and now does not.

### The magnitude decision, MEASURED rather than argued

Issue #362 scope 1 offered two candidates and asked for an argument. Candidate (b) — *drop the
short-circuit and let the won board score itself, since a board where the opponent has no Pokémon
left already reads well* — is **REFUTED by measurement**: on **8 of the 26** win frames a non-winning
option's board is `>=` the weakest winning option's board, which fails acceptance criterion 2
outright.

| frame | weakest WIN board | a NON-win at |
|---|---|---|
| `84897262\|1\|decision\|110` | **−29063.1** | −28896.7 |
| `82749168\|1\|decision\|88` | 6706.6 | 6789.9 |
| `82524455\|1\|decision\|55` | 6064.5 | 6191.2 |
| `82522698\|1\|decision\|62` | 4164.3 | 4400.7 |
| `83663053\|1\|decision\|22` | 3690.6 | 3690.6 (exact tie) |
| `82752604\|0\|decision\|106` | 2326.2 | 2463.9 |
| `83455356\|0\|decision\|11` | 1919.3 | 1919.3 (exact tie) |
| `83007714\|1\|decision\|135` | 1583.7 | 1703.7 |

The first row is the argument in one number: a board on which **I have already won** scores −29 prizes,
because `survival`'s `_predicted_loss` fires on a game that is over. A won board is not a board.

### Acceptance, measured on the SHIPPED leaf

* 26 of 26 win frames, **0 out-scored by a non-win** (the sweep's positive control still fires: 26 > 0).
* `82749168|1|decision|88`'s ruled option ranks **1st**, matching the committed baseline row exactly
  (`correct_is_top: true`, `rank 1`, `top_tie 8`).
* Max board-branch value observed anywhere in the corpus: **7101.4** (7.101 prizes), against the
  derived band's 10900 — so the bound holds empirically as well as by construction.

### The flat tie — taken as an OWNED zero, with the measurement that makes it free

Scope 3 allowed either. Every winning line in a frame still prices identically, and **so did the old
formula**: `_simulate_line` reads `start_prizes` off the ROOT observation, before the first step, so
it is one number per FRAME that every option carries. It could never separate two winning lines; all
it varied was the flat value's per-frame scale (2000 here, 5000 there), which no within-frame ranking
can use. Measured on frame 88: eight winning options, all `start_prizes 1`, all 2000. Asserted by
test through the real `_simulate_line` rather than quoted.

Nor is there anything to separate: the sim stops at MY turn end, so every one of these lines wins
THIS turn. What does differ — how far the heuristic sim had to predict — is already governed by the
`coins` bit (which demotes an RNG-won line out of this branch entirely) and by
`_develop_rollout_line`'s refusal to rank anything that rode `stream`. Ordering two equally-winning,
equally-coin-free lines is Issue #263's, which owns ordering and inherits this leaf.

### The soundness guard was checked, not assumed

*A phantom sim win must never beat the sound win rung.* It still cannot: `_develop_rollout_line`
defers on any leaf `>= KO_SCORE`, and a win short-circuit was already `>= KO_SCORE` at the old
magnitude — raising it to 10900 keeps it above the same threshold, so no new commit path exists.
`_pool_floor_fails`' `< KO_SCORE` premise check is likewise cleared at both magnitudes. What changed
is RANKING among candidates the rung was already willing to consider, which is the defect.

## Neither baseline was recaptured

`data/leaf_lab/baseline.json` and `data/decider_lab/baseline.json` are untouched by this run. Verified
with `git status`.

## Issue #351 — the now-leg credited a body that could not attack, masking Issue #286

### What was built

`_readiness_odds`'s NOW leg is asked only of a body that may LEGALLY attack this turn
(`state_value._may_attack_now` — `BodyView.is_active` AND `not MySide.attack_blocked`). The oracle
itself is untouched: `readiness_p` is shared with `promote_retreat_value` (ADR-0073), whose whole
question is what a benched body would do once promoted, so an area-aware oracle would break it. The
gate therefore lives in the consumer that asks about a body standing still.
`test_the_gate_leaves_readiness_p_ITSELF_byte_identical` pins that the incumbent did not move.

Issue #351's **option 2** — stripping the expiring Energy from the now-leg too — was REJECTED, and
the corpus is why (below): on 21 of the 25 affected bodies the Energy really is spendable this turn.

### Gate arithmetic — attributed against a BEFORE control on the same tree

Measured by forcing `_may_attack_now` to `return True` and re-running, so main's own 10 commits are
held constant and only this change moves.

| | before (gate forced off) | after |
|---|---|---|
| unruled `OK -> MISS` | 7 | **7** |
| — membership | — | **one FIXED, one ADDED** (see the two rows above) |
| Decision Gate | PASS | **PASS, 0 picks moved, 0 rulings moved** |

The count is unchanged and the membership is not: `82752604\|0\|decision\|88` (Issue #329's) leaves,
`85046350\|0\|decision\|85` arrives. Net ledger effect on this batch is therefore **zero new unruled
flips**, with one of Issue #329's three retired.

**Developer follow-up 2026-08-04 (Issue #376 Item 2):** direct-build the generalized Meowth sentence
rather than send it through the stale proposal queue. The rule is narrow: a spent on-play
supporter-tutor ex body banks no attack, mobility, or ability-fuel value while a real attacker can
receive the Energy; the desperation floor still exists when no attacker alternative exists. This
lands in `Pilot._attach_value` as `spent_utility_gated`, backed by source-verified card 1071 Meowth ex
(`supporter_tutor`, on-play Bench ability, Tuck Tail for 3 Energy / 60 damage, ex liability).

The other six unruled flips are all present with the gate OFF and are NOT this issue's:
`81904451\|0\|decision\|9`, `83457493\|1\|decision\|20`, `83661649\|0\|decision\|54` (Issue #332,
tabled above), `85785606\|0\|decision\|19`, `85785606\|0\|decision\|21` (Issue #329, tabled above),
and `81906755\|1\|decision\|9` (Issue #280's, already ruled **REVERT** in the closed
`issue-sequence-281-wave3-packet.md`).

### The measurement, with its positive control

Swept over the committed corrections corpus through the shipped Pilot at this commit — **372 frames,
1018 of my bodies**. Positive control asserted rather than assumed: **536** bodies read
`readiness_p == 0.0`, so a silent 1.0 everywhere is not what the counts below are measuring.

| | before | after |
|---|---|---|
| bodies holding a `discard_eot` Energy | 25 | 25 |
| ...where the FORWARD clock moves once it is stripped | 25 | 25 |
| ...where `_readiness_odds` moves | **0** | **4** |

The 4 are exactly the bodies the rules forbid an attack to: **1 benched** — `83664991|43`, a Mega
Starmie ex, the frame the issue was filed on, `1.0000 -> 0.1245` — and **3 `attack_blocked`**
(first player on turn 1): `81903490|8` and `81903490|10` at `1.0000 -> 0.4922`, and `81904451|9` at
`1.0000 -> 0.0000`. That last one is the two corrections composing: the gate removes the phantom
now-leg and Issue #332's `_survives_to_spend` then zeroes the forward leg behind it.

Episode `81903490` is the very episode `docs/rules.md` cites as its worked example of a reason-only
rule (*"don't attach Ignition T1-going-first — you can't attack, so it's discarded for nothing"*,
correction `ep81903490 f5`), so three of the four defect bodies are the documented misplay itself.

### The issue's tripwire prediction was WRONG, and the test stayed green deliberately

Issue #351's acceptance criteria named
`test_the_NOW_leg_keeps_the_evaporating_energy_and_therefore_MASKS_the_fix` as *"the tripwire; it was
written to fail here"*. **It did not turn red, and it should not have.** Its fixture is the ACTIVE
body on `turn=5` — a body that may legally attack, whose `{C}{C}{C}` pays Nebula Beam outright — so
`readiness_p == 1.0` is TRUE of it and the masking is the family answering correctly. The 21 corpus
bodies in the same position are the general case.

The test was kept and its docstring rewritten to record that, and it now serves as the ANTI-regression
against option 2: a change that gated the now-leg hard enough to fail it would be telling an armed
Active attacker it cannot swing.

This is the second self-filed issue in this batch to carry a claim verification did not support (Issue
#362's `start_prizes` was the first), and it is reported here rather than quietly resolved.

## Neither baseline was recaptured (Issue #351)

`data/leaf_lab/baseline.json` and `data/decider_lab/baseline.json` are untouched by this issue's work
as well. Verified with `git status`.

## Issue #349 — the board-scaled magnitude: ZERO gate flips, proven against a BEFORE control

**No rows were added to the Flips table, and that is a measurement rather than an omission.** The
issue mints two clause PARAMETERS (`amount_per`, `each_of`) and re-authors five compendium entries;
it changes no scoring code at all.

### Gate arithmetic

| gate | before | after |
|---|---|---|
| leaf (Discrimination) | 7 unruled, 59 held out, 4 voided; agree 182/249 -> 126/249, 82 picks moved | **identical**, frame for frame and rank for rank |
| decider (Decision) | — | **PASS**, 0 unruled, 0 ruled; agree 250/347 -> 250/347, **0 picks moved** |

The 7 unruled leaf flips are the batch's standing set and not one of them is this issue's: three are
Issue #332's (`81904451|0|decision|9`, `83457493|1|decision|20`, `83661649|0|decision|54`), two are
Issue #329's (`85785606|0|decision|19`, `|21`), one is Issue #351's (`85046350|0|decision|85`), and
`81906755|1|decision|9` predates the batch entirely — `docs/plans/issue-sequence-339-wave3-packet.md`
records it at that batch's base, and Issue #280 already ruled it REVERT.

### How the BEFORE control was taken

Not by `git stash`: that shares one stack across worktrees, so a "reverted" measurement can silently
still be running the diff. Instead the four changed runtime files plus `CONTEXT.md` were checked out
from the HEAD blobs (`git checkout -- src/...`), and the revert was **proved** by `git diff --stat --
src/` printing nothing at all before the gate ran. The saved copies were restored afterwards and
verified by SHA-256, with a CRLF count of 0 on each — this repo has no `.gitattributes` (Issue #367).

### Why zero was the expected result, and what it would have taken to be wrong

`src/common/card_effects.json` is the one live artifact this issue touches. **The Pilot's readers do
reach some of these cards** — 1242 Community Center is in the census pool and now carries `each_of`
on a `heal` clause, so `_heal_candidate` reaches it; the earlier phrasing "cards the readers provably
cannot reach" was wrong and `/code-review`'s Spec axis caught it. The true statement is narrower and
enough: on every edited card, the value the reader takes is **the correct one**, unchanged by the new
field.

* 1187 Morty's Conviction gains `amount: 1` on a `draw` clause. The compendium's ONLY `draw`-amount
  consumer is `planner._draw_engine_window`, gated on `condition == "once_per_turn_ability"` **and**
  an `evolvesFrom` body — a Supporter satisfies neither.
* 1222 Fennel and 1242 Community Center gain `each_of` + `target`. `planner._heal_candidate` and
  `_heal_averts_doom` read `kind` / `condition` / `restriction` / `amount` / `rider` and never
  `target`, and `each_of` widens the SET rather than the per-body amount — so the Active's credit is
  the SAME 40 (or 10) either way, and it is the right number, not a number that got lucky. Asserted
  in both directions, with a positive control, in
  `test_a_per_body_heal_credits_my_active_the_PRINTED_amount_not_amount_times_bodies`.
* 1089 Reboot Pod gains an `accel` clause whose `target: "future"` is an unmodelled target class, and
  `combat._accel_target_ok` returns `False` on exactly that — it funds no body rather than every one.
* 1085 Awakening Drum is not in the census pool at all.

## Neither baseline was recaptured (Issue #349)

`data/leaf_lab/baseline.json` and `data/decider_lab/baseline.json` are untouched by this issue's work
as well. Verified with `git status`.

## Issue #372 — the playability gate: ZERO gate flips, and this was the batch's likeliest flipper

**No rows were added to the Flips table.** That matters more here than it did for Issue #349,
because this issue was sequenced LAST specifically on the expectation that it *would* flip something:
it adds `cost_required: true` to 1121 Ultra Ball, which our decks run **17 copies** of across five of
our six agent decks, plus 1092 Secret Box (2 copies) and 1233 Canari (0). `card_effects.json` is read
live by `planner.py` / `combat.py` / `pilot.py`. A flip here would have been cleanly attributable to
this one cause, which is why it went last. It produced none.

### Gate arithmetic

| gate | before | after |
|---|---|---|
| leaf (Discrimination) | 7 unruled, 59 held out, 4 voided; `agree 182/249 -> 126/249`, 82 picks moved | **byte-identical output**, frame for frame and rank for rank |
| decider (Decision) | PASS, 0 unruled; `agree 250/347 -> 250/347`, 0 picks moved | **byte-identical output** |

`diff` over the two gates' FULL stdout — not just the summary lines — reports zero differing lines
in both directions.

### The 7 unruled leaf flips are unchanged and none of them is this issue's

`81904451|0|decision|9` · `81906755|1|decision|9` · `83457493|1|decision|20` ·
`83661649|0|decision|54` · `85046350|0|decision|85` · `85785606|0|decision|19` · `|21`

That is the same standing set Issue #349's section lists, measured here from a BEFORE control taken
at the tip of the batch — i.e. **after** Issues #350, #374 and #375 had all landed. So the batch's
whole compendium-and-registry half (Issue #350's `cost` vocabulary, Issue #349's board-scaled
magnitudes, Issue #374's selector values, Issue #375's retired `stall` tag, Issue #372's playability
gate) contributed **zero** unruled flips between them; every outstanding flip belongs to the T3.5
`state_value` track (Issues #329, #332 and #351) or predates the batch.

### How the BEFORE control was taken

Issue #349's recipe exactly, and for its reason — **not `git stash`**, which shares one stack across
worktrees so a "reverted" measurement can silently still run the diff. The three files under `src/`
(`card_effects.json`, `snapshot_coverage.py`, `CONTEXT.md`) were checked out from the HEAD blobs and
the revert **proved** by `git diff --stat -- src/` printing nothing at all before either gate ran.
The saved copies were restored afterwards and verified byte-for-byte by SHA-256, each still at a CRLF
count of 0 — this repo has no `.gitattributes` (Issue #367).

### Why zero was the expected result

`cost_required` **has no runtime reader.** Measured by parsing, not grepping: an `ast` walk over
every `.py` under `src/` (excluding `src/cg/`) collecting string constants used as dict subscripts,
`.get()` arguments or `in` tests finds **0** sites for `cost_required`, against **5** each for `kind`
/ `target` / `zone` and **3** for `amount` as the positive control. `apply_option()` raises
`NotImplementedError` — T0 freezes the contract — so nothing prices the field today. The exposure
that made a flip plausible is real and is why the issue was worth doing; it simply lands at T4, where
this stops being a pricing error and becomes a LEGALITY one.

Census re-run: **zero movement**, which is likewise a measurement and not a skipped step.
`cost_required` is a boolean PARAMETER, so it enters neither the write-set-health table (which counts
VOCABULARY values) nor the selector-value table, and all three edited cards were already
`covers: full`.

## Neither baseline was recaptured (Issue #372)

`data/leaf_lab/baseline.json` and `data/decider_lab/baseline.json` are untouched by this issue's work
as well, and so is `data/corrections/reviewed.json` — no correction was ruled, refuted or otherwise
reviewed by this issue. Verified with `git status` and an empty `git diff --stat data/`.
