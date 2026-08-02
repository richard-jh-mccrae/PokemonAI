# ADR-TEMP-294 — Deadness RANKS a discard; it does not price one

**Status:** Accepted (ruled by the user 2026-08-02 on Issue #294, option 1 of two offered); **BUILT**.
**Amends [ADR-0065](0065-card-worth-is-one-marginal-oracle-with-a-closure-graph-backend.md)** — it
corrects a WP-N3 build note whose claim was never true in shipped play. **Applies
[ADR-0103](0103-the-tie-break-is-class-identity-not-menu-position.md) decision 1 one layer up**, at
the needs assignment's removal ranking rather than the Pilot's option ordering. Supersedes nothing.

**Context issues:** Issue #294 (this build), Issue #261 item 2h / ADR-0103 Amendment A (the deletion
pass that made the gap unobservable and committed the two strict-xfail TARGETs that owned it),
Issue #238 (the failure shape those TARGETs exist to prevent), ADR-0092 (the POC doctrine that
deletes rung-fitting), ADR-0080 / ADR-0085 / ADR-0093 (a categorical instrument is not a magnitude
one).

## Context

The forced discard is decided by `needs.cheapest_removal` over the keep-value v2 assignment. Its
rows carry a `pitch` term — the deadness count the seam-D grill's Finding 3 built, because
*"keep-cost is a KEEP floor and cannot RANK a discard: a dreg, a duplicate and a DEAD card all price
keep 0."* The rows price it correctly. **The assignment never reads it.**

Measured on `85e57a9`, through the shipped decider, on the two RULED cases:

| | dead-opener (seam-D Finding 3) | spent burst (`83454549-36`) |
|---|---|---|
| `removal_score` | `0.0` vs `0.0` | `0.0` vs `0.0` |
| residual-worth tiebreak | `0.0` vs `0.0` | filler **`0.0`** vs Ignition **`30.0`** |
| shipped pick | `[0]` — the menu index | `[0]` — worth-first keeps the corpse |

Two mechanisms, not one, and the second is the more damaging:

* the dead-opener case is an **exact tie** falling through to hand position — an ADR-0103 defect one
  layer up from where that ADR fixed it;
* the spent-burst case is the residual-worth tiebreak **inverted**. Residual worth is `worth ×
  deploy`, and a card's `worth` is its CATALOG tier, which a corpse still carries: a spent Ignition
  prices 30 against a role-less spare's 0, so worth-first sheds the live card and keeps the dead one.

Item 2h is what made this worth an issue rather than a note. It deleted `_discard_shadow`'s `eq_pick`
column and the v1/ladder fallback — the last two places in the tree that computed the ruled-correct
pick — so after it landed nothing could show a reader that the shipped answer was wrong. That is the
Issue #238 shape, and the two strict-xfail TARGETs committed with 2h are the ratchet against it.

### What WP-N3 believed it had built

ADR-0065's WP-N3 build note (`keep-value-needs-assignment-grill-spec.md` §3) records the tiebreak's
purpose as *"the deploy-dead Cinderace sheds before a live spare."* That sentence describes this
ADR's outcome and has been false since the day it was written: `_deploy_odds` knows about dead
evolutions, dead fetchers and need-met tutors, and about none of the five expired-role facts
`_apply_pitch_terms` derives. The design intent was always that deadness rides the RANKING; only the
signal it rode was wrong.

## Decision 1 — deadness is a lexicographic leg of the ranking key, not a term in the score

`needs.cheapest_removal`'s key becomes

```
(removal_score, −Σ deadness, Σ residual_worth, indices)
```

The alternative the issue itself preferred — *"a dead card's keep is not 0, it is negative; you are
paid to shed it"* — was offered as option 2 and **not taken**. Three reasons, in order.

**The equation genuinely yields zero, so a signed credit has nothing to derive its magnitude from.**
The pitch term's own definition is `P(met | pitch) − P(met | keep)`. For a dead card no slot is met
either way, so the honest answer is exactly `0` — the same `0` a worthless live spare prices.
ADR-0065's primitive says the same thing structurally: `keep_cost = Worth × Odds × Gates` is a
product of clamped non-negative factors (`card_worth.py:71-81`) and cannot be negative. A credit
would therefore be an invented constant, and the only anchor on offer is the retired ladder's
`discard-the-dead-opener` **+20** — a weight ADR-0065 deliberately mirrors *"at SOURCE, never their
weights."* Picking a bar against two frames is the rung-fitting ADR-0092 exists to delete; ADR-0103
Amendment A refused precisely that move on the `live` band and sent it to a wave packet instead.

**Deadness is categorical, and this repo has a doctrine about categorical instruments** — ADR-0080,
ADR-0085, and ADR-0093's own general lesson that a categorical fact handed magnitude semantics
changes frequency class and breaks the branches that rested on the old shape.

**The lexicographic form carries a property a credit cannot promise.** The leg is consulted only
where `removal_score` ties, so no amount of deadness can make a removal look cheaper than one that
genuinely costs more. `test_deadness_is_ordering_only_and_never_beats_a_real_cost` pins it. That
matters because `dead_opener` fires on the `opener` tag unconditionally — faithfully mirroring the
retired rung's own `when=`, which was equally unconditional — so a card that is both a spent opener
and a live engine keeps whatever keep value the assignment gives it, and only the tie moves.

**This is not v1's sort restored.** What item 2h deleted was `_discard_equation_rows`' second return
value: a `(keep asc, pitch desc, worth asc, index)` ranking living BESIDE `needs.cheapest_removal` as
a second definition of "cheapest to lose." The objection was two definitions, not the ordering. v1's
`worth asc` leg already lives inside `cheapest_removal` as the sanctioned `tiebreak` parameter; this
puts the last leg in the same one place, which is the opposite of re-creating the drift.

### Why deadness sits ABOVE residual worth

Because residual worth reads the catalog tier a corpse still carries — the spent-burst inversion
above. The worth leg keeps deciding wherever nothing is dead, which is the `83967840-54` ruling
(`test_cheapest_removal_ties_break_by_residual_worth`, unmoved).

## Decision 2 — the row carries TWO counts, and `fuel` is in only one of them

`_apply_pitch_terms` now writes `dead` (the five expired-role bits: `dead_opener`,
`redundant_tutor`, `stranded`, `fodder`, `spent_burst`) alongside `pitch` (`dead` + the `fuel` zone
sign). `dead` ranks the discard; `pitch` keeps its two existing jobs — gating LATENT worth
(`_resolve_needs` withholds a general slot from a pitch-flagged row) and the shed predictor's junk
band.

**This was found by building it, not by reasoning about it, and it is the trap in this issue.** The
first cut passed the whole `pitch` count as the deadness leg, on the argument that fuel is harmless
there because `pitch_gain` always makes a fuel shed score strictly lower. That argument is false when
the fuel card ALSO covers a keep-side slot: the pitch gain and the keep loss cancel, the score ties,
and the second count then decides the tie toward shedding it. Measured on
`83966336|0|decision|27` — a Basic `{F}` Energy that was the only card covering the `fund_attack`
slot, `removal_score` `0.0` either way, and the deadness leg shed the attack's only funder:

```
Discrimination Gate   FAIL   REGRESSED 83966336|0|decision|27   OK -> MISS   rank 1 -> 3
                             leaf agree 178/247 -> 177/247
```

Fuel is not deadness. It is a discard that FILLS a slot, and `needs.pitch_gain` already prices it in
the score; counting it again in the ranking double-prices it. `test_a_fuel_card_that_also_funds_the_attack_is_not_dead_weight`
pins both halves — the tie, and the pick each count produces.

## Measured at the build (2026-08-02)

Both gates are **byte-identical to the clean tree**, before and after:

```
Decision Gate         PASS   372 frames vs a8da62d   agree 249/345 -> 251/345
                             0 unruled, 2 held out, 1 voided   (unchanged)
                             context 8 (DISCARD)  10/11 agree   (unchanged)
Discrimination Gate   PASS   268 frames vs d8ef7a0   agree 180/247 -> 178/247
                             0 unruled, 2 held out (both owner=#262)   (unchanged)
suite                 4419 green
```

**Issue #294's own scope item 2 does not survive measurement.** It states that a fix *"moves every
forced discard in the corpus, so it needs its own measurement and a wave ruling."* It moves **zero**
corpus frames on either gate, so **no ruling is owed and none was made** — the same outcome as
ADR-0093 decision 1, where an adjudication scope item evaporated once the mechanism was located. The
only decisions that move are the two the issue was filed about, and both move onto the human's
answer.

The `discard agree_v2` number the issue asks to re-read **cannot be re-read and is not owed either**:
`needs_sweep.py` computed it by comparing v2 against the live v1 decider, and both the probe and v1
died with item 2h (ADR-0089's rule — a RULING's script dies with its answer). The live instrument for
that population is the Decision Gate's context-8 slice, quoted above.

## Consequences

* The two strict-xfail TARGETs are **deleted, not flipped to green** — their assertions were
  `chosen == [1]` on exactly the two boards the two row-pricing tests above already build, so folding
  them up removes a ruling stated twice. The deletion is recorded in a comment at the site, because a
  deleted xfail and a deleted ruling look the same in a diff.
* `cheapest_removal` gains one optional parameter and both of its production callers pass it —
  `_needs_v2` (the decider) and `doctrine_fetch._shed_signals` (the shed predictor). The predictor
  must take it or it stops predicting what the decider does, which is the contract ADR-0103
  Amendment A extracted `needs.removal_score` to keep. `removal_score` itself is **untouched**, so
  the predictor's junk / live / key bands read the same numbers they did yesterday; only which set it
  prices can move.
* Runtime is unchanged in order: the key is built from two sums over an already-enumerated subset,
  inside the same `C(n, picks)` loop.
* **Not addressed, and stated rather than folded in silently:** `Pilot.needs_keep_value` is read
  nowhere in `src/`, `tests/` or `tools/` — item 2h made the discard path unconditional and left the
  kill-switch vestigial while three docstrings (`pilot.py`, `runtime.py`) still describe it as the
  gate. And `docs/general-strategy.md` still documents `discard-the-fodder` /
  `discard-the-redundant` / `discard-the-hand-duplicate` as live rungs that item 2h deleted. Both are
  Issue #261 residue, both were put to the user and neither was taken into this issue's scope.
