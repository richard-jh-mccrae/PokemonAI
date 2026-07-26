# Phase 1b — the evolve decider swap: the paired A/B

Merge evidence for #140 / PR #166 (ADR-0070), owed by #136 standing directive 6: every decider swap
runs a paired A/B before merge. Companion to `attach-decider-swap-review.md`, which is 1a's.

**Verdict: FLIP is False. The swap is NOT cleared to merge, and it is NOT demonstrated to regress.**
The rule fails, but the run is under-powered for an effect of the size 1b actually has. The ruling on
what to do about that is the user's (directive 2 — a regressing swap is re-ruled WITH the user); this
document records the measurement and the diagnosis, and proposes nothing.

## The instrument

`tools/sim/gauntlet_swap_ab.py`, reused from 1a. A flag A/B would be the wrong instrument: five rungs
are deleted, so `evolve_value` OFF is degraded mode (evolve endorsements go silent and only the
surviving `dont-rush-evolve-without-target` Gate speaks), not the incumbent. This A/Bs two BUILDS —
candidate `a8b6127` against `origin/main` `25fa8e5` — staged as self-contained bundles via
`submit.package`, opponent held FIXED at the incumbent so the raw deck matchup subtracts out. Both
arms seat-balanced (ADR-0021). The branch's 11 commits are exactly the swap; main's 3 extra commits
are test-only de-flakes, so the build delta is the swap and nothing else.

## Run 1 — the headline, n=200 per arm per directed matchup

| matchup | candidate | incumbent | delta |
|---|---|---|---|
| dragapult_ex vs mega_lucario | 55/200 = .275 | 74/200 = .370 | **−9.5 pp** |
| dragapult_ex vs mega_starmie | 22/200 = .110 | 25/200 = .125 | −1.5 pp |
| mega_lucario vs dragapult_ex | 128/200 = .640 | 113/200 = .565 | **+7.5 pp** |
| mega_lucario vs mega_starmie | 65/200 = .325 | 70/200 = .350 | −2.5 pp |
| mega_starmie vs dragapult_ex | 179/200 = .895 | 179/200 = .895 | +0.0 pp |
| mega_starmie vs mega_lucario | 133/200 = .665 | 135/200 = .675 | −1.0 pp |

**AGGREGATE delta −1.17 pp, 95% CI [−4.59, +2.25] pp, 0 crashes in 2400 games (36.0 min).**

**FLIP: False** — fails two of the three clauses (`delta >= 0`; `CI-lo >= −1%`). The crash gate is a
hard pass: **0 crashes across 2400 games** on the real engine, every deck pairing, both seats.

## Run 2 — a deep re-measure of the cell that drove it, n=600 per arm

The aggregate was carried by one cell at −9.5 pp (≈2.0 SE at n=200). Re-measured at 3× depth, as
diagnosis — the headline verdict above stands as measured and is not reissued from this run:

| matchup | candidate | incumbent | delta (n=600) | was (n=200) |
|---|---|---|---|---|
| dragapult_ex vs mega_lucario | 223/600 = .372 | 210/600 = .350 | **+2.2 pp** | −9.5 pp |
| mega_lucario vs dragapult_ex | 380/600 = .633 | 400/600 = .667 | **−3.3 pp** | +7.5 pp |

0 crashes in a further 2400 games (55.0 min). **Both cells changed sign.** Per-cell signs at n=200
are not stable; the −9.5 pp that produced the verdict was substantially sampling noise.

## The best available estimate

Pooling both runs for the two re-measured cells (n=800 each) and keeping n=200 elsewhere:

| matchup | delta |
|---|---|
| dragapult_ex vs mega_lucario | −0.75 pp (278/800 vs 284/800) |
| dragapult_ex vs mega_starmie | −1.50 pp |
| mega_lucario vs dragapult_ex | −0.62 pp (508/800 vs 513/800) |
| mega_lucario vs mega_starmie | −2.50 pp |
| mega_starmie vs dragapult_ex | +0.00 pp |
| mega_starmie vs mega_lucario | −1.00 pp |

**Aggregate −1.06 pp, 95% CI [−3.90, +1.78] pp. 0 crashes in 4800 games total.**

No cell is individually significant. What is mildly suggestive is the **sign pattern**: 5 negative,
1 exactly zero, 0 positive. Under a true null that is roughly a 3% coincidence — weaker than it
looks, since the cells are not independent of a shared build, but it is the one thing in the data
pointing at a real effect, and it points slightly NEGATIVE at about −1 pp.

## Why the rule cannot settle this at any affordable n

1a passed the identical rule at ±3.4 pp because its true effect was clearly positive (+2.92 pp); it
passed on the DELTA, never on precision. 1b's true effect looks like roughly −1 pp to 0. Two
consequences, both structural:

- Clearing `CI-lo >= −1%` with a true delta near 0 needs a half-width under 1 pp, i.e. **n ≈ 2270 per
  arm per matchup — about 27,000 games**, on the order of 8–10 hours on this box.
- Even then, `delta >= 0` is a **coin flip** on a truly-neutral swap. No amount of n fixes that, and
  re-running until the sign lands is p-hacking, not evidence.

So "run it bigger" is not a guaranteed path to a pass, and that is a fact about the rule meeting a
behaviour-improving-but-win-rate-neutral swap, not about this build.

## Which term moved it — ranked, with the evidence

Measured by replaying every Dragapult corpus fixture that carries an EVOLVE option through both
builds and reading the evolve option's score (OptionType 9, `src/common/strategy/context.py:12`):

| frame | incumbent evolve | candidate evolve | inc. correct? | cand. correct? |
|---|---|---|---|---|
| f29 charge the line | 20 / 15 / 20 / 15 | **50 / 0 / 50 / 0** | ✓ | ✓ |
| f40 evolve the draw engine | 0 | 8.75 | ✗ | **✓** |
| f35 hold until typed-ready | 45 | **0** | ✗ | ✗ (non-evolve lane) |
| doom_guard f35 | 45 | **0** | ✗ | ✗ (non-evolve lane) |
| f82 energized body first | 20 / 15 | 30 / **37.5** | ✓ | **✗** (#165) |
| f32 hammer over develop | 20 | **37.5** | ✓ | **✗** (#165) |
| dx f32 forward form guard | 20 | 37.5 | ✗ | **✓** |

**1. The deploy re-banding (§2 + amendment A) — the leading candidate.** Evolves moved from 15–20 in
Needs to 30–50 in damage. The two frames that flip correct→incorrect do so because the evolve now
out-scores a **non-evolve** option: f32's correct answer is *Retreat Dreepy → promote Budew
(sacrificial item-lock wall)*, and the candidate takes the 37.5 evolve instead. Both were user-ruled
to #165 / Turn-Planner scope, which is why the decider sweep scored 0 REGRESSION — **the sweep honours
the re-ruling and the A/B does not.** That is exactly the unknown-unknown gap directive 6 exists to
catch. Against mega_lucario in particular, giving up the item-lock wall line is a plausible cost.

**2. §7's income discount / the deleted −46 hold — pre-registered, and REFUTED as the cause.** ADR-0070
§7 warned the honest discount is a LOWER bar than the deleted rung, so the agent might hold too
little. The measurement says the opposite happened: on both f35 frames the candidate scores the
premature evolve **0.0 where the incumbent scored 45.0** — it holds MORE. The deleted rung was not
even firing on those frames (its `when` needs `evolve_body_energy < 2`, and the body holds 2
wrong-typed Energy); amendment B's `typed=` fix is what declines the evolve. On the evolve axis f35
is a clean improvement, and it still fails only on a PLAY beating the Recon dig 20 vs 18, outside
this equation's lane.

**3. Bare-body evolves going to exactly 0 (amendment E).** f29 shows the shape: the incumbent gave
every line piece a nonzero pull (20/15/20/15), the candidate is bimodal (50/0/50/0). Correct by
ruling — information before commitment — but it means a class of evolves that used to be endorsed at
+15 now never clears `_finish_turn_last`'s `score > 0`.

**Standing caveat on term 1:** #163 (shared spread budget) inflates every bench survival delta, and
that survival weighting is inside the deploy term this section fingers. The bias is parked
deliberately, but it sits in the suspect term.

## The ruling (user, 2026-07-26) — MERGE

Option 2 of the three below was taken: the instrument, not the build, is what failed. A Phase-1
decider swap makes one axis correct in one currency so #165 and #145 can compose the axes; grading it
by whole-agent win rate measures it through the weakest consumer it will ever have. Recorded as
ADR-0070 amendment H. The general re-scope of directive 6, and the leaf-lab discrimination gate that
should replace it mid-build, is **#167**.

The options as they stood:

- Spend the ~27,000-game run and pre-commit to its result, accepting the coin-flip clause.
- **Re-rule the flip rule for a swap whose design intent is corpus-correctness rather than win rate.**
  ← taken
- Treat −1 pp as a real regression and investigate term 1 (which would put #165 on the critical path
  rather than deferred).

Not discharged by the merge, and carried to #167: term 1's diagnosis stands, and the sign pattern
still points at it. If #165's planner does not absorb the f32/f82 class, this is where to look first.

Raw: `swap_paired_ab.json` from each run (`reports/` is gitignored, so the numbers are transcribed
here rather than committed).
