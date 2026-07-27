# ADR-0074 — The opponent-target slot family splits by instrument shape: held-card keep pricing extends the Needs assignment; target-ranking reads the marginal directly

**Status:** Accepted (grilled 2026-07-27, `/grill-with-docs` on #186 — three locked decisions). Build
= #186 (S2 + S3b), consumed by #187 (S4-deny), #188 (S4-snipe), #189 (S4-gust), #190 (S5). #186 is one
of five sub-issues split from #143 (tracker #136) — see #143's closing comment.

**Context issues:** #186 (this grill), #143 (the un-split original, closed), #136 (the Value System
build tracker), `docs/plans/opponent-value-equation-unification.md` (the design this ADR turns into a
build ruling), ADR-0065 (the Needs / `keep_v2` precedent this extends).

## Context

The unification design doc's O1 ruling (2026-07-22, "Option B: the assignment") says the
opponent-target marginal should be realized as ONE board-wide Needs slot assignment: every opponent
body is a slot, and "my available removal instruments this turn (snipe rider, gust, Hammer,
forced-promo chip) are the cards being assigned to those slots." Read literally, that implies
extending `needs.py`'s existing bitmask-DP solver — today `deny_slot` (`needs.py:182`), consumed only
by the keep/discard resolver (`src/common/CONTEXT.md`'s Card-Worth Oracle entry: Needs is "WHAT the
position requires: deadline-tagged slots + the exact-assignment marginal `keep_v2`") — uniformly
across all four instruments.

Reading the live code surfaced a mismatch: `baseline_snipe.py` and
`strategy/doctrines/doctrine_gust.py` (the snipe/gust target-pickers) import `needs.py` **nowhere**
today. They are independent play-time deciders answering "which opponent body do I hit," with no
held-card keep/discard question involved. Only `deny_slot` genuinely fits the DP's shape, because a
Hammer (or a gust/forced-promo Trainer card) is a scarce HELD CARD whose keep-vs-play value the DP
prices; a snipe rider is not a held card at all — it rides an attack already committed to, and the
DAMAGE select just offers a target choice among already-available options.

## Decision

The opponent-target family splits along what each instrument actually *is*, rather than one uniform
DP extension:

1. **Held-card instruments (deny, gust, forced-promo)** — extend the existing DP assignment
   (`needs.py`'s `Slot` / `assignment_value` / `keep_v2` family) to keep-price these Trainer cards
   against the same per-body opponent-target slots `deny_slot` already occupies. This requires
   **migrating** `needs.SUPPLIES`'s current `"gust"` tag routing — today aliased into the `"deny"`
   kind (the `deny_tags` eligibility set built at `pilot.py:3678`) — onto its own slot kind, and
   adding a `"promo_chip"` kind for forced-promotion cards. Not an addition beside deny; a schema
   split of existing eligibility.
2. **Snipe** — does **not** enter the DP. It reads the shared per-body value function
   (`needs.opponent_target_value` + `needs.phase_scale`) directly, bypassing the assignment entirely,
   because there is no scarce held card whose keep-value competes for the slot.
3. **The sweep/adjudication is centralized in #186.** The same per-body number feeds all three
   downstream S4 swaps (#187/#188/#189), so #186 runs the corpus sweep (23 DAMAGE frames + the gust
   frames + the Hammer frames, the design doc's own S3b acceptance bar) and adjudicates disagreements
   with the user itself — even though #186 ships nothing live except the S2 piece below — rather than
   letting each S4 issue re-litigate the same shared value through its own instrument's lens.

**Decision 0 (S2 scope, prerequisite to the above).** `discard_recur_fuel` goes live only on the
`incoming()` ceiling-policy path (survival: `active_doomed` / the doom-relax gate), because raising a
threat number is the fail-scared, safe direction. It does **not** go live on `turns_to_afford` (the
deny/posture clock): lowering that turn count is the fail-slow, unsafe direction the design doc itself
flags as needing calibration this issue doesn't yet have — over-crediting it would over-spend a scarce
Hammer/Guzma on a refueler that isn't actually that close. That adoption is explicitly deferred, owned
by #187 or a dedicated follow-up, not silently dropped.

## Consequences

- `baseline_snipe.py` gains its first-ever dependency on the Needs module family
  (`opponent_target_value` / `phase_scale`) — but not on the DP assignment itself.
- `doctrine_gust.py`'s Trainer-card holding logic and the deny-slot emission both route through the
  generalized DP; `needs.SUPPLIES`'s `"gust"` tag entry is **migrated**, not just extended, so existing
  eligibility behavior for held Guzma-class cards changes shape even before any live decider swap
  fires — #186's own test coverage should call this out explicitly so it isn't an invisible side
  effect of "shadow, decides nothing."
- #187 (S4-deny), #188 (S4-snipe), #189 (S4-gust) each inherit an adjudicated, corpus-validated
  per-body value and only grill their own slot-kind wiring + kill-switch; none re-opens the
  shared-value question.
- #186 ships an intentionally asymmetric Threat Clock read: more cautious about survival immediately,
  unchanged for deny/posture until a calibrated follow-up lands.

## Alternatives rejected

- **Flat shared value function, no DP extension for gust/forced-promo.** Simpler — one function, four
  independent callers — but reopens O1's already-locked ruling (2026-07-22) without saying so, and
  gives up the no-double-spend / cross-repricing guarantee across a held Hammer and a held Guzma that
  O1 specifically chose the assignment to buy.
- **Full live adoption of S2 on both clocks now.** Faster — one flag instead of a split — but ships
  the deny-side change in a direction the design doc itself calls unsafe, with no derived discount to
  calibrate it: the "magic-number fudge" ADR-0065's standing discipline forbids.
- **Defer sweep adjudication to each S4 issue.** Less up-front work, but risks the same per-body
  number being ruled differently by three separate instrument-scoped grills looking at the same
  corpus frame.
