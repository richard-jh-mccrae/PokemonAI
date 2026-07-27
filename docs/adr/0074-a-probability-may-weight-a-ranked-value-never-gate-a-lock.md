# ADR-0074: A probability may WEIGHT a ranked value, never GATE a lock

**Status.** Grilled 2026-07-27 (`/grill-with-docs`, issue #175, split out of the #142 Phase-1d
grill as grill-item-3 Option 3). Decisions 1–5 locked; scope and verification still open at time of
writing. Extends [ADR-0067](0067-attach-budget-fails-closed-on-yield-open-on-deck-presence.md)
(the split epistemic and its 2026-07-27 leg-assignment amendment) and **amends
[ADR-0031](0031-turn-planner-is-goal-directed-engine-simulated-tier1-search.md) decision 3** (the hard-rung
invariant). Leaves [ADR-0030](0030-winning-this-turn-is-an-eager-engine-verified-lethal-solver.md)
/ [ADR-0037](0037-lethal-solver-is-the-turn-planners-top-rung.md) deliberately untouched — see
decision 1. Terms in [src/common/CONTEXT.md](../../src/common/CONTEXT.md): *Count Triple*
(`p_any`, the **Probability Leg**), **Leg Assignment**, *Attach Budget*, *Provable Budget*.

## Context

ADR-0067 ruled the Attach Budget's deck-fetch leg fails **OPEN** — a typed fetch counts unless the
deck is *provably* empty of that type. That leg's error rate is not constant. It scales with
depletion, and the sound alternative is uninformative for exactly the window that matters:

| unseen copies of the type | hidden prizes | P(fetch whiffs) | `floor` | `ceiling > 0` |
|---|---|---|---|---|
| 3 | 6 | ≈ **0.06 %** | 0 | true |
| 1 | 6 (~40-card deck) | ≈ **13 %** | 0 | true |

Fail-open is nearly free early and materially wrong late; the Provable leg is zero whenever
`unseen <= 6`, i.e. every realistic Energy suite before a deck-revealing search anchors the prizes
(ADR-0067's own amendment says so). Neither boolean tracks the ramp. ADR-0067 named the gap and
deferred it to #175 by name.

**The premise #175 inherited was wrong, and the grill corrected it at source.** The issue framed
this as "putting a probability threshold inside the eager lethal solver (ADR-0030)". The composed-line
accel is not in the Lethal Solver. `_composed_budget_units`
([planner.py](../../src/common/strategy/planner.py):2531) has exactly two call sites —
`_item_evolve_ko_candidate` (:2655) and `_rare_candy_ko_candidate` (:2717) — and both feed
`_ko_for_prizes_lines` (:1422, :1429), which emits a **ranked** `TurnLine` carrying a scalar
`value`. The Win Rung (`_win_line`, :465) never reads it, and already fails **CLOSED** on deck
fetches: tier 3 gates on `_tutor_energy_certain` — *"SOUND only when the deck DEFINITELY still holds
a reusable Energy … a probable fetch is never a win"* (:594) — and tier 4 on `deck_definitely_has`.

So the defect is a **mis-ranked** `ko_for_prizes` line, not a locked phantom win. That distinction
is what makes a probability admissible here at all, and it generalises into decision 1.

## Decision

### 1. Leg Assignment extends from *what is uncertain* → *who asks* → **what the output IS**

ADR-0067 split the epistemic by what is uncertain (yield vs deck presence); its amendment added who
is asking (a consumer about to stand down vs one about to spend). This ADR adds the third and
governing axis:

- A consumer whose output **GATES** — a boolean a lock turns on, where being wrong is catastrophic
  and unrecoverable — takes a sound leg (`floor`, or the fail-open `ceiling` where a false
  stand-down is the costly error) and **may never read a probability**. The Win Rung is the
  canonical lock and stays exactly as it is.
- A consumer whose output is a **SCALAR COMPARED** against sibling options **weights by the
  probability**, because a mis-ranked option costs a turn, not the match. The `ko_for_prizes`
  ladder is the canonical ranked consumer.

**There is no threshold anywhere.** A probability cut-off turns an estimate back into a boolean and
re-imports the error it exists to price; it is rejected as a shape, not merely as a value.

### 2. The probability is `p_contains`, and lives as a fourth leg on `CountTriple`

Not `readiness_p`. `readiness_p` ([combat.py](../../src/common/strategy/combat.py):939) returns
`draw_hit_probability(copies, pool, draws)` — P(*drawing* an enabler in this turn's remaining dig).
The composed line's uncertainty is a **tutor's deck search finding a type that may be entirely
prized**, which is `deck_odds.p_contains(unseen, prizes_hidden, deck_count)`
([deck_odds.py](../../src/common/deck_odds.py):116) — `1 − C(k,u)/C(h,u)`, reproducing the table
above exactly (u=3, k=6, h=60 → `1 − 20/34220`). **#175's title names the wrong instrument.**

`count_triple` gains `p_any` from the same `(unseen, prizes_hidden, deck_count)` it already takes,
and `MySide.deck_energy_p -> {EnergyType: float}` becomes the third projection of
`deck_energy_counts`, parallel to `deck_energy_types` (`ceiling > 0`) and
`deck_energy_types_provable` (`floor >= 1`). One derivation, four readings that cannot disagree —
the same reason `deck_energy_types` was restructured as a projection rather than a parallel read.

*Tension acknowledged:* ADR-0067 decision 3 says "the honest probability lives in `readiness_p`."
That ruling survives in substance — its purpose is that an estimate must never be smuggled into
sound math, and `CountTriple`'s discipline (a consumer must NAME the leg it reads) enforces exactly
that. `expected` is already estimate-math on the same type.

### 3. The weight prices what the KO actually eats — per realising assignment

`AttachUnit` gains a source marker; `_can_pay` gains a variant returning the **realising
assignment** (it already computes one internally and discards it for a bool); `best_affordable_ko_value`
gains a typed-`Budget` entry point beside the int one. The weight is `∏ p_any[T]` over the distinct
deck-sourced `(unit, type)` pairs *that assignment consumes*; everything certain — Energy in hand, a
discard-sourced attach over the public pile, an Item accel — contributes 1.0. Maximise over options
and assignments.

Rejected: one probability per Budget, or the min over its deck-sourced types. Both discount a KO
paid entirely from hand because a Crispin happened to sit beside it — a systematic **under**-claim
of my own reach, which is the f70 error class ADR-0067 exists to prevent. Fixing a phantom KO by
importing a milder famine is not a fix.

This also retires an independent latent weakness: `_composed_budget_units` currently collapses a
typed Budget to `Budget.size` and hands `best_affordable_ko_value` an **int**, discarding the types
before asking an affordability question — precisely the unsoundness `_can_pay` was written to
prevent.

**`∏` is deliberately conservative.** The events are negatively correlated: copies of {R} all
sitting in the prizes consumes prize slots and makes {P} *more* likely present, so the true joint
probability is slightly higher than the product. Under-claiming is the safe direction for a term
weighting a KO claim upward, so the product is taken and the correlation is left unmodelled.

### 4. The weight multiplies the PRIZE term, and the hard-rung invariant is restated in expectation

`KO_SCORE * prizes * p` in `_leaf_value`'s prize term, for weighted consumers only.

**This amends ADR-0031 decision 3.** Its invariant — *"a positional score can NEVER outrank a real
prize"* — becomes: **a positional score can never outrank a REALISABLE prize.** The comparison is
EV-vs-EV. A shaky 2-prize line can now legitimately lose to a solid 1-prize one, and a low-`p` KO
sits inside the positional band where development can beat it. That is the intended behaviour and
the point of the issue.

No explicit whiff branch is modelled. The pool is layer-on-top (`planner.py`:329 — it empties
entirely when the tuned machinery already reaches a KO), so a line whose weighted value loses its
pool falls back to the tuned scoring, which *is* "the KO didn't happen, play the normal game".
Rejected: an explicit `V_whiff + p·(V_ko − V_whiff)`, which needs cross-rung coupling the pool
deliberately does not have, to recover a term the fallback already supplies. Also rejected: leaving
the prize term alone and discounting via a capped sub-prize penalty — the cap sits below one prize
*by construction*, so a 2-prize line 13 % to whiff would still outrank a 1-prize certainty. That
option buys the appearance of a fix.

**Degeneracy is the regression guarantee:** at `p = 1` the term is byte-identical to today, so every
anchored or hand-paid frame is provably unchanged — which is what #175's "no regression to the
composed-line KO frames #142 leaves green" asks for.

### 5. The pool's floor becomes a dominance test against the deferral target

`_commit_best`'s veto is `if best_val < KO_SCORE: return None` (:364). Under weighting that is
wrong in both directions: a **1-prize KO at p = 0.87** scores `0.87 × KO_SCORE`, falls below the
floor, and is vetoed — an 87 %-likely prize is a good play.

The constant floor is replaced by a comparison against the thing the planner would otherwise defer
to (the tuned/greedy pick's score), and applied on the **closed-form path too** — today the floor
exists only under `planner_engine_rank` (armed `True` in [runtime.py](../../src/common/runtime.py):33;
the Pilot constructor default is False), so the closed-form path returns `max(candidates)` with no
floor at all. Comparing against the real alternative introduces no threshold, which decision 1
forbids.

**Largest known unknown, stated rather than implied.** This requires the tuned score and
`_leaf_value` to be commensurate. They share the `KO_SCORE` unit — the pool's own gate already
compares `t.tactical >= KO_SCORE` — but the **positional bands below one prize are not proven
comparable**, and a discounted line lives exactly there. That calibration is part of this issue, not
a follow-up, and must be measured before the build commits to the comparison.

## Consequences

- The Win Rung is untouched and now *stated* as untouchable: soundness there is a property of the
  rung, not an accident of which oracle it happened to call.
- `#177` (`_play_accel_extra`'s remaining call sites) and any future fail-open deck-leg consumer
  inherit the Leg Assignment rule rather than re-deriving it — #175's "rule once for the class".
- Ranked values shift on frames where a deck leg is thin, so a **Decision Gate sweep is mandatory**
  (ADR-0072), not optional.
- The build's centre of gravity is the assignment-returning matcher and the typed-Budget path
  through `best_affordable_ko_value` — groundwork counted as part of the decision, not deferred.
- `#175`'s title should be amended: `p_contains`, not `readiness_p`.
