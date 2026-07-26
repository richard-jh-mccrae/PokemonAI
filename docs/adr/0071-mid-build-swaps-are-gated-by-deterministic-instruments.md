# ADR-0071 — A mid-build decider swap is gated by deterministic instruments; the paired A/B becomes a crash-and-catastrophe tripwire

**Status:** Accepted (grilled 2026-07-26, `/grill-with-docs` on #167). Amends **#136 standing
directive 6**. Build = #167. Decisions 3 and 4 are open at the time of writing and land as
amendments to this ADR.

**Context issues:** #167 (this re-scope), #136 (the Value System build tracker that carries
directive 6), #140 / PR #166 (the swap whose A/B motivated it), ADR-0070 amendment H (the ruling
that merged 1b on a `FLIP: False`), ADR-0069 §8 (the decider-swap sweep protocol this promotes).

## Context

Directive 6 requires every decider swap to run a paired A/B before merge, passing
`tools/sim/paired_ab.py:44` — `flips_on(...) → delta >= 0 and ci_lo >= -0.01 and crashes == 0`.

Phase 1b returned **FLIP: False**: −1.17 pp, 95% CI [−4.59, +2.25], 0 crashes / 2400 games. The
verdict rested on one cell at −9.5 pp; re-measured at n=600 **both** dragapult/lucario cells changed
sign. Pooled over 4800 games the best estimate is −1.06 pp, 95% CI [−3.90, +1.78], 0 crashes. The
run demonstrated neither a regression nor a non-regression — the instrument's resolution and the
effect's size are simply mismatched. Full working: `docs/plans/evolve-decider-swap-review.md`.

Two structural facts, not defects of that run:

- **Precision is unaffordable.** Achieved half-width was 3.42 pp at n=200/arm/directed matchup
  (2400 games, ~36 min). Half-width scales as 1/√n, so clearing `ci_lo >= -1%` near a zero delta
  needs n ≈ 2340/arm/matchup — **~28,000 games, 8–10 h per phase**, and #149's Slowking takes the
  matrix from 6 to 12 directed matchups.
- **`delta >= 0` is a coin flip** on a truly-neutral swap, at any n. Re-running until the sign lands
  is p-hacking. The clause can only be passed by a swap with a positive *win-rate* effect.

A Phase-1 decider swap is not trying to have a positive win-rate effect. It makes one axis correct in
one currency so that #165 (Turn Planner) and #145 (`state_value`) can compose the axes. Grading it by
whole-agent win rate measures it through the weakest consumer it will ever have.

Variance reduction cannot rescue this now: `tools/sim/eval_aivat.py` is a frozen **null seam** that
returns `None` until #147's value net exists — the same phase after which a win-rate gate becomes
meaningful anyway. And the native engine is unseedable (`src/cgpy/rng.py`), so common-random-numbers
pairing is unavailable.

## Evidence — the leaf lab would have caught what the A/B could not

Measured 2026-07-26 during the grill. `tools/train/leaf_lab.py` run at `25fa8e5` (the A/B's
incumbent) and `ac2271f` (post-1b) against the **same** `data/corrections` store. cgpy-backed and
deterministic (`src/cgpy/search.py:326` defaults to `SeededRng(0)`), so the delta is exact — no
sampling, no confidence interval, ~20 min per arm.

| | SOLE-top | shared-top | avg top-tie |
|---|---|---|---|
| `25fa8e5` incumbent | 36/267 | 188/267 (70%) | 3.105 |
| `ac2271f` post-1b | 35/267 | 182/267 (68%) | 3.071 |
| delta | −1 | **−6** | −0.034 |

**6 frames flipped `OK → MISS`; 0 flipped `MISS → OK`** — strictly one-directional.

| episode | agent | pinned fixture | rank | top-tie | correct's value |
|---|---|---|---|---|---|
| 86091435 | dragapult_ex | f35 (+f30, doom_guard f35) | 1→3/5 | 1→1 | 123.03 (top rose 123.03→186.03) |
| 81785223 | mega_starmie | ms_snipe_energized_bench_f39 / _f45 | 1→2/8 | 3→1 | 2191.3 → 2181.58 |
| 81905522 | mega_starmie | ms_snipe_evolving_wincon_preevo_f75 | 1→3/19 | 8→2 | 1176.8 → 1167.08 |
| 82226116 | mega_starmie | **none** | 1→3/15 | 9→2 | 2231.8 → 2222.08 |
| 82229122 | mega_starmie | **none** | 1→3/8 | 4→2 | 1167.0 → 1113.0 |
| 83968638 | mega_starmie | ms_hammer_unfavored_override_f17 | 1→2/11 | 7→1 | 2167.0 → 1113.0 |

Three findings drive the decisions below.

**1. Tie-reduction is not a merit metric — here it is anti-correlated.** Avg top-tie *fell*
(3.105 → 3.071; shrank on 6 frames, grew on 7 — noise), and ties collapsed on precisely the frames
that broke (3→1, 8→2, 9→2, 4→2, 7→1). The leaf got sharper and sharpened the wrong way. #167's item-2
premise — "a value equation that sharpens the leaf should move those" — is falsified by its own
motivating swap. A gate keyed on tie counts or distinct-value counts would have scored 1b **green**.

**2. The regressions are continuation collateral on a deck the swap never targeted.** Five of six are
`mega_starmie`, on **snipe and hammer** frames, not evolve frames. In five of six the top value is
unchanged and the human's option simply lost value. `_engine_leaf_value`
(`src/common/strategy/planner.py:3009`) contains no evolve term — the coupling is
`_simulate_line` (`:3424`), which re-runs `decide` to build the greedy continuation. So a changed
evolve policy alters the rollout *behind a non-evolve first action*. `evolve_decider_sweep.py`
compares resolved evolve body slots and is structurally blind to this; it scored 0 REGRESSION
honestly.

**3. Two of the six have no pinned fixture.** Invisible to the corpus, invisible to the sweep, and
unresolvable by 2400 games. That is exactly the unknown-unknown slot directive 6 exists to fill.

## Decision 1 — directive 6 splits by build stage, and the mid-build A/B drops its merit clause

A **mid-build swap** (Phase 1a–1g) and a **post-composition swap** (#145 onward, once `state_value`
and the Turn Planner consume the equations) owe different things.

**Mid-build**, the paired A/B is a **tripwire**, not a merit instrument. It must return:

```
crashes == 0            AND     ci_lo >= -0.05
```

at the standing n=200/arm/directed matchup (2400 games, ~36 min). **The `delta >= 0` clause is
deleted.** The point estimate, the CI and the achieved half-width are recorded in the swap-review
doc; none of them gate.

**Post-composition**, `flips_on` stands verbatim — `delta >= 0 AND ci_lo >= -0.01 AND crashes == 0`.
Once the equations have their real consumers, a positive win-rate delta is a meaningful thing to
demand.

Implementation: a sibling verdict function in `tools/sim/paired_ab.py` beside `flips_on`, selected by
a `--stage {mid-build,post-composition}` flag on `tools/sim/gauntlet_swap_ab.py`, so both rules live
in code and a run names which one it was graded under. `flips_on` is not modified.

**Why −5 pp and not tighter.** The bound must be one the affordable instrument can actually
adjudicate. At half-width 3.42 pp a truly-neutral swap clears −5 pp with margin, while a −3 pp bound
would need ~7,100 games (2–3 h) per phase and a −1 pp bound ~28,000 (8–10 h). The cost of the wide
bound is stated plainly: **this only excludes catastrophes.** It is not a claim of non-regression, and
merit does not live here any more — it lives in decision 2.

## Decision 2 — merit is two deterministic gates, both mandatory, both per-frame

Every mid-build swap owes both. Both are offline, engine-free or cgpy-backed, exactly reproducible,
and answer in minutes with no statistics.

**The Decision Gate** — the phase's `tools/train/probes/*_decider_sweep.py`: **zero unruled
`REGRESSION` frames**, every flip ruled with the user in the swap-review doc before the deletion
commit. This is ADR-0069 §8's existing protocol, promoted from convention to a merge gate.

**The Discrimination Gate** — `tools/train/leaf_lab.py` captured before and after across all 267
scorable frames: **zero unruled `OK → MISS` frame flips.** Aggregate SOLE-top / shared-top / avg
top-tie are **reported beside it and do not gate**.

Three properties of that pass condition, each earned from the evidence above:

- **Per-frame, not aggregate.** 1b nets to −6 and −1, which invites argument; the per-frame view is
  6-for-0 one-directional, which does not, and it *names the frames* so they become rulings.
- **Verdict flips, not tie counts.** Finding 1: the tie metrics would have passed 1b.
- **All agents, all frames.** Finding 2: the collateral landed on a deck the swap never targeted, and
  finding 3: on frames no fixture pins.

The gate needs a pinned baseline artifact — a `capture` / `diff` split on `leaf_lab.py` modelled on
`tools/sim/score_diff.py`, so the reference is committed rather than remembered, and re-captured
deliberately when `data/corrections` grows.

**Accepted costs.** A before/after leaf-lab capture per phase (~40 min of offline compute). A
baseline that must be re-pinned as the corpus grows. And a gate that will sometimes go red for
reasons unrelated to the swap's merit — passing then requires an explicit user ruling, which is the
point: the escape is visible and recorded, not an aggregate that quietly absorbs it.

## Consequences

- Directive 6 in #136 is rewritten to the mid-build / post-composition split and gains the two gates.
- `flips_on` keeps its meaning; the mid-build rule is a new, separately-named function. No existing
  post-composition behaviour changes.
- 1b's six `OK → MISS` flips are **not** retroactively ruled by this ADR — they are inherited debt.
  The baseline capture that seeds the gate must either rule them or record them as a known-red
  starting point, or the first gated phase inherits a red gate it did not cause.
- Finding 2 is independent corroboration of ADR-0070 amendment H's term diagnosis: the deploy
  re-banding moves behaviour through the greedy continuation, on decks and lanes the evolve sweep
  never looked at. If #165's planner does not absorb the f32/f82 class, this is the first place to
  look.

## Alternatives rejected

- **Pay for the real bound** (`ci_lo >= -1%`, ~28,000 games, 8–10 h/phase): buys a tightening from
  3 pp to 1 pp that changes no decision, at 20× the compute, ×2 again once Slowking lands.
- **Crash soak only** (drop the win-rate clause entirely mid-build): honest about win rate's limits
  but gives up the catastrophe tripwire, and 1b's sign pattern (5 negative, 1 zero, 0 positive) is a
  reminder that near-zero is not nothing.
- **Discrimination gate only when the diff touches the leaf**: measurably the weakest option — 1b
  touched no leaf term and produced six one-directional regressions through the continuation,
  exempting exactly the case that motivated this ADR.
- **Require SOLE-top to strictly increase**: 36/267 is too small and too coarse a base to carry a
  merge decision, and demanding an increase from a swap with no leaf-side merit claim turns the gate
  into an override ritual.
- **AIVAT variance reduction**: unavailable — `eval_aivat.py` is a null seam until #147.
