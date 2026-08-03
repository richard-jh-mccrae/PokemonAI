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

So the answer is: **landing after #281/#284/#285 did not rescue any of the five named frames, and
/3.9 costs one improvement more than /3.0 did.** That is the direction the issue body predicted —
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

Two legs re-measured with severance controls (the leg forced to `0.0`, per-call values diffed):

| leg | before the anchor | after |
|---|---|---|
| Issue #284's bench widening | moved `threat` on **13** frames, every one `0.0 -> 0.1` | moves it on **336** calls by 0.023–0.077 prizes; **58** of those are boards where the Active leg already read something |
| Issue #285's denial credit | moved `threat` on **0** | changes 327 of 614 inputs, moves the OUTPUT on **296** calls by 0.000115–0.002192 prizes |

### One question for the developer, if 7.3% is judged too high

The runaway guard still bites on 45 of 614 non-empty inputs. That is structural, not residual:
`threat` is a SUM over up to six targets while `TARGET_VALUE_CEILING` is ONE target's ceiling, so a
board where a 3-prize Mega ex *and* a 2-prize body are both reachable sums to 5.0 — 1.28x the divisor.
Five prizes of simultaneously-reachable exposure is exactly the extreme board a runaway guard is for,
so **no change is recommended**. The honest alternatives, if the developer disagrees, are (a) divide
by `_MAX_BODIES x TARGET_VALUE_CEILING`, which is derived but flattens the common single-target case
to near-nothing, or (b) change the composition from a sum to a max-with-discount, which is a
frozen-composition change. **Neither is taken here, and no new constant was invented.**

### One further consequence, recorded because it is not a gate flip and would otherwise be invisible

`tests/strategy/test_state_value.py::test_PLAYING_the_boost_card_is_priced_as_a_gain_and_not_as_the_hand_loss`
(Issue #282) asserted that playing Premium Power Pro is a net gain on the `_PLAY` transition. Its
+0.016667 margin was `0.1` of saturated `threat` against a `0.083333` hand hold. Under the anchor a
2-prize Dragapult ex prices `_THREAT_W x 2 = 0.051282` and the positional half of that transition
reads **−0.032051**.

That is not a regression; it is the double-count `_THREAT_CAP` exists to prevent. `threat` prices the
exposure STANDING on the board and the prize for CONVERTING it is `attack_ev`'s, under
`score = state_value(end board) + EV(terminal action)`. A boost played and never cashed genuinely is a
spent card for a position; the old form paid the conversion prize twice and called the difference a
gain. The test is renamed `..._is_priced_as_the_BOOST_and_not_as_the_hand_loss` and made stronger — it
now pins the positional half to the float, asserts the boost recovers 0.051282 of the card's cost
where an unpriced effect recovers none (the epic's actual sentence), and asserts the play is a gain
outright on the full sequence score. **Recorded here in case the developer reads the sign of that
positional half as a calibration finding between `hand`'s `POC_WORTH_PRIZE_RATE` denomination and
`threat`'s positional band** — a gust-tier held card is worth 0.083333 prizes, which exceeds `threat`'s
entire SINGLE-target range (max 0.076923). Nothing was retuned to accommodate it.

## Neither baseline was recaptured

`data/leaf_lab/baseline.json` and `data/decider_lab/baseline.json` are untouched by this run. Verified
with `git status`.
