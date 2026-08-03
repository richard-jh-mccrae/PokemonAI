# Wave-3 packet — issue-sequence run (329, 332, 351, 350, 349)

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
| *(not a frame)* `test_PLAYING_the_boost_card_…` | **no gate** — a sibling issue's acceptance test | Issue #329 vs Issue #282 | `total_after > total_before` (+0.016667) | positional half is **−0.032051** | **RULING OWED — read this one even though no gate reports it.** See *"A sibling issue's acceptance assertion inverted"* below. It was rewritten rather than left failing, which is the one thing in this run that resembles conforming; the developer may direct otherwise. |

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

### A sibling issue's acceptance assertion inverted — RULING OWED

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

## Issue #332 — `readiness` funded the Active over the benched successor

### What was built

`_readiness_odds`' FORWARD leg is now discounted by the body's own survival clock —
`1 - halve(turns_to_ko_me - 1)`, the exact complement of the grade `survival` already puts on the
same clock, through the same newly-extracted `_survival_clock` call so the two families cannot come
to disagree about when a body dies. The NOW leg is untouched: a payoff cashed on MY turn happens
before the opponent's, so a body about to fall still swings and owes no discount. Nothing was
retuned; `attach_value` (ADR-0069) is structurally unreachable from this module and its own suites
(`test_attach_decider.py`, `test_attach_bands.py`, `test_attach_discipline.py`) pass unchanged.

### Gate arithmetic — attributed against a BEFORE control, not against #329's table

The before column is a real re-run with `_survives_to_spend` forced to `1.0`, so these three flips
are this issue's own and not inherited.

| | before (#329's end state) | after |
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

## Neither baseline was recaptured

`data/leaf_lab/baseline.json` and `data/decider_lab/baseline.json` are untouched by this run. Verified
with `git status`.
