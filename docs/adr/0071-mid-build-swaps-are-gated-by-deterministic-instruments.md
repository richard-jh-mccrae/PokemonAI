# ADR-0071 — A mid-build decider swap is gated by deterministic instruments; the paired A/B becomes a crash-and-catastrophe tripwire

**Status:** Accepted (grilled 2026-07-26, `/grill-with-docs` on #167 — five locked decisions). Amends
**#136 standing directive 6**. Build = #167.

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
- 1b's six `OK → MISS` flips are inherited debt, ruled by **decision 5**: a one-sitting review before
  the baseline is pinned, so Phase 1c does not inherit a red gate it did not cause.
- Finding 2 is independent corroboration of ADR-0070 amendment H's term diagnosis: the deploy
  re-banding moves behaviour through the greedy continuation, on decks and lanes the evolve sweep
  never looked at. If #165's planner does not absorb the f32/f82 class, this is the first place to
  look.

## Decision 3 — a corpus fixture declares its claims; axis ordering joins whole-decision

Today every fixture asserts exactly one thing: `pilot.explain(obs).chosen == correct`. That is a
**cross-lane** claim, and #140 showed it discards real signal. Measured on `ac2271f`:

| fixture | chosen | correct | shape |
|---|---|---|---|
| `dp_hold_evolve_until_typed_ready_f35` | `[1]` @ 20.0 | `[2]` @ 18.0 | evolve option `i=0` @ **0.0** — the evolve axis is RIGHT (45 → 0); the frame fails by 2 points between two **non-evolve** options |
| `dragapult_hammer_over_develop_f32` | `[1]` @ 37.5 (the evolve) | `[3]` @ 30.0 (retreat → item-lock wall) | the evolve axis **wins the frame and shouldn't** — the defect is cross-lane by nature |

These are two different failures wearing one red mark. f35's swap-side improvement scored as nothing;
f32's is genuinely a composition defect (#165).

**Ruled:** a fixture carries an explicit `claims` block and the harness asserts exactly what is
declared.

- **Decision Claim** — `{"decision": [2]}`: given the whole board, the agent picks this. The
  end-to-end composition assertion, unchanged in meaning from today.
- **Axis Claim** — `{"axis": {"option_type": 9, "prefer": <slot>, "over": [<slot>, ...]}}`: within
  ONE lane, this option outranks those. Resolved by `OptionType` and body slot
  `(inPlayArea, inPlayIndex)` — the same comparison basis `evolve_decider_sweep.py` already uses —
  **never** the raw option index.

A fixture with no `claims` block keeps today's whole-decision behaviour, so nothing breaks on day one
and back-fill is incremental. One shared assertion helper serves both claim types.

**Why ordering and not scores.** 1a's precedent is the general rule: f29 was deliberately rewritten
*from* a score claim *to* a decision claim because raw scores are not comparable across a currency
change. Ordering *within* a lane survives re-banding; cross-lane *scores* do not. So the corpus stops
decaying every time a currency changes, and the equation is tested at the seam where it is
responsible.

**What this does NOT fix, deliberately.** f32 gets no axis rescue — an axis claim on the evolve lane
would pass, because the evolve equation does rank the right body. Its defect is only visible
cross-lane, and it stays a Decision-Claim failure owned by #165. *(Amendment B corrects the further
claim made here at the time — that f32's reframed fixture cannot map to a leaf frame. It can: the
`select` payloads match exactly, and only the label was reframed.)* That is the correct outcome: axis
claims must not be able to launder a composition defect into green.

**Accepted costs.** A fixture schema addition and a shared helper; back-filling axis claims across
~130 fixtures, incrementally and with a per-frame judgement each time; and a frame can now be wrong
in two ways. The sharpest risk is presentational — a passing Axis Claim beside a deferred Decision
Claim must never *read* as "OK". Reporting has to distinguish "axis OK, decision owned by #165" from
"OK", or decision 3 re-creates the contamination it removes in a new place.

## Decision 4 — a re-ruling is a state on the frame, not prose in a review doc

**The gap, verified.** `evolve_decider_sweep.py` has **no exclusion list**: it computes `REGRESSION`
for every labelled frame, including frames whose `correct` is a non-evolve play. So "0 REGRESSION
partly by definition" (#167 item 4) is not a code-level exclusion — it is the *human ruling step*. A
flip ruled to #165 is written up as out-of-scope prose in the swap-review doc, and nothing in code
ever learns it happened. `xfail(strict)` covers part of this (f82 would fail loudly if it started
passing) but lives in pytest — a surface neither the sweep's tally nor the Leaf Lab's report reads —
and it is binary, so it cannot show "still broken, the same way, three phases later."

**Ruled:** the ruling becomes data on the frame. Decision 3's `claims` block gains
`{"owner": "#165", "ruled": "2026-07-25", "why": "..."}`. Both the **Decision Gate** and the
**Discrimination Gate** keep running held-out frames and print a `HELD OUT (n)` section carrying
their current verdicts — **always visible, never gating**. Deleting `owner` returns the frame to
gating. CI asserts the field's *shape* only: the suite runs offline (CLAUDE.md), so issue-liveness
cannot be checked there and belongs on the phase checklist.

This also discharges the presentational risk decision 3 introduced: `HELD OUT` is where "axis OK,
decision owned by #165" is displayed, so it can never read as plain "OK".

**Correcting item 4's stated rationale.** #167 argues "a held-out set that still reports would have
predicted #140's A/B result." **It would not have.** The held-out frames (f2 = ep86091728, f32, f82)
are *not* among the six `OK → MISS` flips measured above; the only dragapult episode that flipped was
ep86091435 (f35). What predicted the A/B was the **Discrimination Gate**, on five `mega_starmie`
frames nobody had re-ruled. The accountability argument for the ledger stands on its own; the
predictive one does not and is not relied on here.

**Accepted costs.** A field that rots if a ruling is made without updating it. CI can check shape but
not that `#165` is still open, so a closed issue can leave a frame parked until someone reads the
checklist. And the section is only useful while it stays small — past roughly a dozen frames a
permanently-visible held-out block becomes wallpaper, which is the failure mode it exists to prevent.

## Decision 5 — the six inherited flips are ruled before the baseline is pinned

Decision 2 needs a pinned reference, and 1b's six `OK → MISS` flips are on `main` now. Whatever seeds
the baseline decides whether Phase 1c starts red for damage it did not cause.

**Ruled:** the six are put in front of the user in **one sitting**, as part of #167's build, using the
same protocol a decider swap's flips already get. Each gets an outcome — **fixed**, **held out with a
named owner**, or **accepted as a real regression**. The baseline is captured at that ruling commit,
so from 1c onward every red the gate shows is caused by the swap being measured.

The before/after data already exists (`25fa8e5` vs `ac2271f`, same corrections store, `SeededRng(0)`,
reproducible) — see the evidence table above. The sitting needs each frame's board read and its card
facts verified at source (CLAUDE.md), so it is build work, not a grill tail.

**Why not pin the debt away.** The six are the only evidence in the repo that the Discrimination Gate
works at all: one-directional, five on a deck the swap never reviewed, two on frames no fixture pins.
Pinning them away at birth discards the measurement that justified building the gate — and exempting
ourselves from the standard decision 2 imposes on every future phase would establish it as
negotiable.

**Accepted cost.** A six-frame ruling sitting blocks #167 closing, and some frames may turn into real
work rather than a one-line held-out entry.

**Sitting progress (2026-07-26).**

| # | frame | ruling |
|---|---|---|
| 1 | `86091435\|0\|decision\|35` (f35) | **re-ruled** — `correct` `[2]` → `[1]`, Poké Pad first; Endorsement Claim credits the evolve decline (amendment A) |
| 2 | `81785223\|0\|decision\|44` | **REAL REGRESSION** — the bare-body evolve floor; recorded as ADR-0070 amendment J. No `owner`; stays gated |
| 3–5 | `81905522\|0\|decision\|64`, `82226116\|0\|decision\|48`, `82229122\|0\|decision\|17` | share frame 2's cause (every menu evolve at 0.0, leaf top is an evolve-first) — grill pending |
| 6 | `83968638\|1\|decision\|17` | no evolve on the menu; a different defect — grill pending |

The cost of ruling frame 2 as a regression is that **the baseline cannot be pinned yet**: capturing
now would bake four frames of it into the gate's own reference.

## Amendment A — the Endorsement Claim, and f35 re-ruled (2026-07-26, build)

Decision 3 shipped two claim types. Building it surfaced a case neither can express, and the user's
ruling on that case changed what f35 asserts.

**The gap: a single-option lane.** f35 has **exactly one** evolve option on the menu (active Drakloak
→ Dragapult ex; the other four are PLAY, ABILITY, RETREAT, END). "Prefer X over Y within the lane" is
inexpressible with one option — and it is trivially top. Yet the swap's real fix on that frame is
that the premature evolve went **45.0 → 0.0 with no rule firing at all.** Decision 3 as written could
not credit it.

**Ruled: a third claim type, the Endorsement Claim** — *this slot is (or is not) taken at all*,
evaluated against ``score > 0``, the endorsement floor `_finish_turn_last` already gates on. Zero is
a **structural** boundary (act / don't act), not a tuned magnitude, so it survives a currency
re-banding exactly as ordering does; no magnitude is ever compared, so it is not the score claim 1a's
f29 rewrite rejected. A claim whose slot is absent from the menu returns **unprovable**, never
vacuously true — that is how a stale claim would otherwise outlive the board it described.

**f35 re-ruled (user, the decision-5 sitting).** The frame's `correct` moves from `[2]` (Recon
Directive first) to **`[1]` (Poké Pad first)** — the agent's own pick. Verified at source:

| the line | verification |
|---|---|
| Poké Pad fetches the 2nd Drakloak | deck runs **4× Drakloak** (1 in play, 0 in discard); Drakloak has **no Rule Box**, so it is a legal target |
| a bench Dreepy evolves into it | **both bench Dreepy carry `appearThisTurn=False`** — legal (`rules.md:96`) |
| that yields **2× Recon Directive** | "once during your turn" is **per body** — two Drakloak, two digs (see 4, keep 2) |
| the {P} out is real | deck runs **3× Basic {P} Energy** (plus 3× Crispin) |
| the fallback branch | Drakloak **Retreat 1** → discard the dead {D}; Budew **Itchy Pollen, No cost** → 10 dmg + *"opponent can't play any Item cards next turn"* |

Two reasons the tutor goes first, and the second is the sharper one: the tutor is **deterministic**,
so waiting reveals nothing; and resolving it **thins the deck by a known non-{P} card**, improving
both subsequent digs. **Deterministic tutor before stochastic dig.**

f35's Decision Claim is therefore `[1]` (passes today), plus an Endorsement Claim that the sole
evolve is **not** endorsed (passes today, and is what credits 1b). The full conditional maneuver —
Poké Pad → evolve a Dreepy → Recon ×2 → branch on whether a {P} appeared → *either* attach/evolve/
Phantom Dive *or* retreat/promote Budew/item-lock — is recorded on the fixture as `turn_plan` owned
by **#165**.

**Two corrections this forces to the record:**

1. **f35 and f32 are the same maneuver class.** f35's fallback branch *is* f32's retreat-to-
   sacrificial-item-lock-wall (`docs/plans/turn-planner-retreat-to-item-lock-wall.md`, and the
   `can_wall_line_with_disruptor` stand-down `hold-position-in-setup` already carries). Two
   independent frames landing on one maneuver is a stronger signal for #165 than this ADR recorded.
2. **The 20-vs-18 "weight collision" was not a defect.** During the investigation `dig-before-commit`
   (w=20, fires on the Poké Pad) looked wrongly ranked above `use-the-draw-engine-ability` (w=18,
   fires on Recon), since the Ability is free and the Item costs a card. Flipping them **would have
   broken this frame** — the 20 produces the correct first action. What remains true is far narrower:
   the agent reaches `[1]` for a *generic* reason ("free search before commitments") rather than the
   deck-specific one (manufacture a second Recon body, thin the deck). Right answer, weak reason —
   not a bug, and no weight change is warranted.

## Amendment B — what the build's code review changed (2026-07-26)

Two findings were defects in the build rather than in the design, and both are worth recording
because the design reads fine either way — the record should not imply the first attempt worked.

**The Held-out Ledger shipped INERT.** Decision 4's mechanism was built and unit-tested, but every
fixture carrying an `owner` had been given no `frame_key`, each for an individually defensible
reason. The net effect was that **no frame could enter either gate's `HELD OUT` section** — the exact
defect this ADR's decision 4 exists to remove would have survived the fix. Each ruling's frame is now
identified by an **exact `select`-payload match** to its source Correction, and the Ledger is live:

| fixture | frame | owner |
|---|---|---|
| f32 | `85046350\|0\|decision\|32` | #165 |
| f82 | `85785609\|0\|turn\|8` | #165 |
| f2 | `86091728\|0\|decision\|2` | #161 |

This also **overturns amendment A's aside** that f32's reframed fixture cannot map 1:1 to a leaf
frame. Its `select` payload matches the Correction exactly; only the *label* was reframed
(`correct=[3]` vs the record's `[1]`). The board — and therefore the frame a ruling holds out — is
the same. A test now asserts the Ledger is non-empty and names all three, so it cannot silently go
inert again.

Verified end to end on 33 real dragapult frames, one run, two identical regressions:
`85785609|0|turn|8` (held out) printed under `HELD OUT` and excluded from the verdict, while
`86091728|0|decision|19` (unruled) gated — `GATE: FAIL`, exit 1, "gated on 32, held out 1".

**A `ruled` date is now required beside every `owner`**, shape-checked `YYYY-MM-DD`, with `why`
mandatory alongside. Decision 4 listed the field; the first implementation parsed only `owner`/`why`
and buried the date in prose, which is the undated-ruling problem it was meant to prevent.

**Smaller corrections, all from the same review:** the mid-build verdict was printed as `FLIP`, a
phrase on the Tripwire's own `_Avoid_` list; each stage now carries its own label (`TRIPWIRE` /
`FLIP`). `--stage` is **required**, so a post-composition run can never be silently graded by the
looser mid-build bound. The lane constants are pinned to `cg.api`'s enums **by a test** rather than
imported — verified that a bare `import cg.api` maps the native library (`libcg` in
`/proc/self/maps`), which would drag the DLL into the offline unit path that `planner.py` keeps lazy
for the same reason.

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
- **(Decision 3) Keep whole-decision claims only** and manage contamination by re-ruling frames to
  the owning issue as `xfail(strict)`: the status quo, and the reason f35's clean fix scored as
  nothing.
- **(Decision 3) Move to axis-ordering claims only**: gives up the repo's only end-to-end assertion,
  and f32's defect — visible *only* cross-lane — would become unrepresentable.
- **(Decision 3) Assert raw per-option scores**: rejected once already by 1a's f29 rewrite; scores
  are not comparable across a currency change, which is the whole reason re-banding decays the
  corpus.
- **(Decision 4) Rely on `xfail(strict)` alone**: correct as far as it goes, but invisible to both
  gates and binary — it cannot show a frame has been broken the same way for three phases.
- **(Decision 4) Move re-ruled fixtures to a separate directory**: makes "held out" a location rather
  than a property. A frame held out for #165 on the evolve axis is still live for every other axis,
  which a directory cannot express.
