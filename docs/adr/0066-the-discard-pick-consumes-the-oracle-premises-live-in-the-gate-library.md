# ADR-0066: The discard pick consumes the oracle; premises live in the gate library

**Status.** Accepted (grilled with the user 2026-07-19, the seam-discard-convergence build;
ruling: **full replacement**, confirmed after the replay-arithmetic refutation of the staged and
re-point alternatives below). Amends ADR-0065's §grab/pitch "already-subsumed" finding — the
residual gaps identified there are now closed by converging the ladder itself. Builds on ADR-0065
(the one worth oracle), ADR-0023 (the shared fetch comparator), and the gate-library scope
(`docs/plans/gate-library-scope.md`).

## Context

The forced-discard pick (`_DISCARD`, e.g. Ultra Ball's cost) was the last keep-value site still
priced by a private system: a mature 12-rung ladder in `doctrine_fetch.py` (flat per-id weights,
premise-gated `when=` routing) rather than the ADR-0065 keep-cost equation the refresh SHED and
gamble keep-floor already consume. ADR-0065 §grab/pitch had judged the ladder "effectively already
converged" — its two residual gaps deferred to the gate library.

The seam's acceptance PAIR (`docs/plans/seam-discard-convergence.md`) forced the question:

- `86091435-68` (xfail target): don't pitch a Drakloak that can evolve the Active Dreepy THIS turn.
- `83686860-18` (pin): a Drakloak with no this-turn-evolvable target is still correctly pitched.

**Replay arithmetic (2026-07-19, the grill's evidence).** Replaying `86091435-68` through the
shipped Pilot: hand = [Risky Ruins, Lillie's, Lillie's, Rosa's, Crushing Hammer, Drakloak], my deck
EMPTY, human's pick = {Lillie's, Crushing Hammer}. Ladder scores: Drakloak +20
(`discard-the-redundant` — a benched Drakloak exists), Lillie's +4 each, everything else 0.0. The
pick is independent top-2 with an ascending-index tie-break (`_DISCARD` ∉ `_GRAB_CONTEXTS`). Three
independent defects follow:

1. **The spike alone cannot flip the target.** Floor Drakloak and the top-2 is the two Lillie's
   (+4, +4) — both pitched, wrong. The pair must be valued as a SET: after committing one Lillie's,
   the second re-prices as the sole remaining draw card.
2. **Even with set semantics the second slot fails.** Risky Ruins, Rosa's and Crushing Hammer all
   score exactly 0 in both the ladder AND the worth oracle; the index tie-break pitches Risky Ruins
   (the deck's engine Stadium, kept by the human) over the coin-flip Hammer. The currency must
   COVER these cards.
3. **The spike has nothing to multiply.** `role_value(Drakloak) = 0` — no declared Role, and its
   `draw`/`dig` tags are not in `TAG_TIER`. Any deadline factor × 0 = 0.

## Decision

**The discard pick becomes a consumer of the one keep-cost equation. All 12 discard rungs retire.**

```
pitch_score(card) = − role_value(card) × role_met_bracket(card)      [+ zone sign]
role_met_bracket  = P(role met by its deadline | keep) − P(met | pitch)
```

- **`gate_library` owns the bracket** (`role_met_odds`-shaped factors, PARAMETERS of the equation,
  never rungs): the **deploy-now spike** (an in-play body this hand card can evolve THIS turn —
  `_fetched_playable_this_turn`'s rules-verified predicate — with no other hand copy covering →
  bracket 1, full worth: re-access cannot help a this-turn deadline), the **job-done gates**
  (a `rush_evolve`/`tutor_mega` tutor with the wincon already in hand; an `opener` once the game is
  under way; a `discard_eot` burst with the Active fully powered → bracket 0), the **starved-energy
  gate** (a typed Basic Energy is floored only while my Active carries zero Energy — surplus Energy
  cycles freely, ep83686860 f11's premise), and the existing **undeployable-evolution discount**
  (Stage 1). The **covered-in-play discount** (a non-Line copy already in play does the job →
  bracket → 0) replaces `discard-the-redundant`; Line bases (`_BASE_ROLES`) are exempt from cover
  discounts — each copy is a LINE, per-copy jobs don't cover each other (ep83686860 f18).
- **The closure supplies the rest of the bracket:** `P(met | pitch)` = re-access odds
  (`fetch_closure.reaccess_outs` over the anchored/pre-anchor deck counts, a fixed draw window) —
  an empty deck makes every card fully irreplaceable, which is exactly the `86091435-68` board.
- **The pick goes greedy for multi-discard** (the `_greedy_grab` virtual-board precedent): commit
  the best pitch, re-score the remainder with the committed copy gone — the second copy of a
  duplicate re-prices (sets not sums; `discard-the-hand-duplicate` retires into this marginal).
  `_shed_signals`' naive independent top-2 predictor moves to the same joint form, and its
  key-shed flag becomes a band test (`keep_cost ≥` the key band) instead of a rung-id probe.
- **Zone sign:** a `discard_fodder` Role scores POSITIVE to pitch (the bin is where its value is
  realised) — `prefer-good-in-discard` retires into the sign, not a rung.

**Currency coverage added (arbitrated by correction `86091435-68`, the currency-zone rule):**

- `TAG_TIER["draw"] ≈ 8` — the `keep-engine-supporter-at-discard` −8 band written into the one
  currency; **excludes `hand_disruption` cards** (Judge/Harlequin are symmetric disruption, not
  engine fuel — the rung's own exclusion, preserved). Also what the spike multiplies for Drakloak.
- `TAG_TIER["energy_accel"] ≈ 10` — Rosa's Encouragement's live comeback-accel claim.
- **Risky Ruins gets a deck-DECLARED worth** in `dragapult_ex` ROLES (amending that file's
  "not a Role" comment stance): the deck's engine Stadium, kept over a coin-flip Hammer by the
  human. `energy_denial` deliberately gets **no band** — the Hammer prices 0 and is the cheapest
  pitch, which is the human's ruling.

### Verification stance (why full replacement is safe HERE)

- **The corpus recordings are the untouched ground truth** — they replay real states through the
  real Pilot and assert PICKS, not mechanisms. The acceptance pair is the flagship; the discard
  subset pins are the regression net.
- **The synthetic discard tests re-author to behaviour** (drop rung-id `fired` probes, keep the
  `decide()` set asserts), each rewrite justified against the recording its rung cited.
- **No training is lost.** No fitted overrides exist on the dragapult discard family;
  mega_lucario's two fitted deltas (`discard-the-hand-duplicate` 9.46,
  `keep-engine-supporter-at-discard` −10.54) are dropped with the rungs and re-fittable from the
  same stored recordings.
- The `fetch_sheds_junk` predicate redefines from "both sheds score > 0" to "no shed carries a
  positive keep_cost" — under the equation junk prices AT 0 (free), not above it.

## Alternatives rejected (the grill's record)

- **Spike-only / one new floor rung.** Arithmetically insufficient (defects 1–2 above survive it),
  and it is the "more if/else instead of the one held-value equation" shape the user rejected
  2026-07-18. Refuted by replay, not taste.
- **Magnitude re-point (keep `when=` routing, derive the constants).** A rung's weight is ONE
  constant shared by every card it matches (`_weight` resolves per id); the equation's value is a
  per-card, per-board number — there is no channel for it in a rung weight. Unrunged cards stay at
  0 and the acceptance pair still fails. The in-repo precedent for graded currency terms is the
  computed channel (`_refresh_shed_keepcost`), which is what this ADR uses.
- **Staged replacement (equation + transient rung survivors).** Viable, and the builder's initial
  recommendation — rejected by the user's ruling for the cleaner invariant: with no fitted tuning
  at stake and behaviour verified against recordings, a transient double-system (and its
  double-counting hazard: `keep-key-cards` −30 AND `TAG_TIER["discard_eot"]` 30 both firing) buys
  risk, not safety.

### Consequences

- One currency, four consumers (fetch grab/pitch, discard, refresh SHED, gamble keep) — the last
  private valuation dies; every future discard behaviour argues about worth bands, gate premises,
  or closure facts, never a new rung.
- Cards with NO worth claim price 0 and fall to the index tie-break — the equation refuses to
  invent preferences no recording has arbitrated.
- The re-access window for a pitched card is a fixed constant (documented at the definition);
  corrections arbitrate it like any band.
