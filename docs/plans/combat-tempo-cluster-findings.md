# Findings: the combat/tempo corpus cluster (investigated 2026-07-18)

**Status.** Investigation COMPLETE; corpus reclassified accordingly (substance pins + corrected
diagnoses, `tests/strategy/test_hyperclosure_corpus.py`). One identified build follow-up (worth
tag-fallbacks, below) — NOT yet built.

## Method

Replayed every remaining corpus target through the shipped `explain()`, resolving each pick's card,
score, fired rungs, tier (`_finish_turn_last`), and planner disposition (`Decision.gamble` /
`TurnLine`). Measured, not assumed — the cluster label ("agent plays a marginal utility instead of
attacking") survived for NONE of the targets in its original form.

## The decomposition (9 targets → 4 causes + 4 dead)

**A. Tagged blunder DEAD; residue separately adjudicated/designed → SUBSTANCE PINS (4).**
The recorded blunder now scores ≤ 0 and is not chosen; strict `correct`-equality fails only because
the *alternative* line differs from the human's label:
- `83038055-51`, `82752045-94` — Lillie's dead (−34/−10); the agent ATTACKS. Residue =
  Jetting-vs-Nebula, already adjudicated in the agent's favour (reviewed.json ep83661649 f30,
  ep83116501 f60; the f94 precedent test declines to pin it).
- `83037962-49` — Harlequin dead (−11, the SHED convergence); the pick is Night Stretcher via
  `recover-to-refill-bench`, whose OWN rationale designs "refill THEN attack" sequencing.
- `82754241-12` — Poffin dead (−25, `dont-search-an-empty-deck`); the pick is a PRICED refresh-first
  gamble (52 %, EV 525 > det 8 + keep 16) that postdates the correction. The human compared Poffin
  vs Ultra Ball, never vs the gamble.

**B. The worth-coverage gap → the identified BUILD (2, stay xfail).**
`82749168-65` (Lillie's +15 shuffles back the Ignition burst before a KO), `83969481-55` (Lillie's
+10 shuffles back Wally's Compassion that answers next-turn Nebula). Root cause: the DISCARD ladder
prices these cards (`keep-key-cards-at-discard` −30 covers `discard_eot`; `dont-waste-clutch-heal`)
but the WORTH oracle does not — `role_value` = 0 for a role-less Trainer / special Energy, so the
graded refresh shed cannot charge for them and the refresh stays positive (tier 3, before the
deferred attack). **Fix shape: tag-derived worth fallbacks** in `card_worth.role_value` (the Round 9
"engine from Function Tags" derivation, mirroring the ladder's floors into worth points —
`discard_eot` burst, `clutch_heal`, `gust`, `recycle`). One currency, no new rungs; calibrate
against the six ADR-0060 pins + the corpus before flipping. This is ADR-0060's explicitly-parked
"hand QUALITY" seam made concrete.

**C. Separate small axes (2, stay xfail with corrected diagnoses).**
- `85163634-17` — fetch one turn early = Judge exposure: the held-card-risk tier-2 seam (spec
  §Round 8 §5), explicitly deferred there.
- `86091728-19` — Ultra Ball substance FIXED; residue is attach-target priority ({P} to the Active
  via `prefer-active-attach-in-setup` +8 vs the benched 2nd-line Dreepy).

**D. Unchanged (1).** `85059103-9` — the Petrel tutor-chain grab value (closure-reachable worth,
Round 9 §3). `86091435-68` — the discard-side deploy-now spike (gate-library scope doc).

## Instrument finding (fixed)

The Pilot is STATEFUL across `explain()` calls (the deck tracker accumulates one game's
observations). Sharing one pilot across corrections from different games made replay verdicts
order-dependent — measured: the same Harlequin option scored **+8.1 polluted vs −6.9 clean**. The
corpus now builds a fresh pilot per replay (~5 s total, sound). No verdict flipped, but any future
one could have.

## What was NOT the cause

- The `_finish_turn_last` tiering ("utilities before the deferred attack") is working as designed —
  including for a +1002 KO with a positive utility on the menu; the failures trace to the utility's
  SCORE being wrongly positive (group B), not to the ordering.
- No lethal-forfeit bug: `_wins_now` already fast-tracks a game-winning KO to tier 0.
- No score-order inversion: the one apparent inversion (`82754241-12`) was the planner's gamble
  line overriding score order — by design, and priced.

## Recommended next build

The **worth tag-fallbacks** (group B): extend `card_worth.role_value`'s fallback leg to read the
same behavioural tags the discard ladder already trusts, so the ONE currency covers situational
Trainers/special Energy. Small surface (one function + calibration), two live corpus targets as the
acceptance gate, the six ADR-0060 pins as the regression net.
