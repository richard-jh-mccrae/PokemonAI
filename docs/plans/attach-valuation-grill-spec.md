# Attach valuation — grill-session seed: one equation for the Energy attach

**Status (updated 2026-07-19, post-rebase).** SEED for a grill session — NOT designed, NOT built —
but the landscape moved and the blockers SOFTENED:
- **The shadow ruling applies** (`docs/plans/shadow-equations-ruling.md`): the equation gets BUILT
  and emitted in shadow (the gamble-trace pattern) once the grill settles the design — a passing
  rung ladder no longer blocks construction, only the swap. Round 0 below now classifies
  replacement PRIORITY rather than gating construction.
- **The exchange-rate inheritance is partially IN**: the gusting grill resolved (ADR-0066) with a
  ruled ceiling — denial may override at most ~1 effective prize — and the `their_keep_cost`
  design (`gusting-keepcost-design.md`) owns the offensive rate. The hand-disruption build (in
  flight) is landing the damage↔worth leg. Inherit both; a shadow oracle may emit in its own units
  meanwhile.
- **Seam A LANDED** (built & promoted): a general role-keyed stand-down of
  `prefer-active-attach-in-setup` (off-Line Active, benched un-powered Line member → develop the
  line), pinned in `test_attach_target_priority.py`. It is now a FOLD CANDIDATE of this grill, not
  a coordination risk — the oracle's P-term should subsume it and its pin must survive the fold.
- **Seam B LANDED** (held-card risk, fetch-late at a concrete deadline) — the deadline-term
  precedent outside the gate library; agenda §2 should read its shipped shape before choosing a
  home. Seam C's chain machinery also extended `fetch_closure` (the `trainer` branch).

## Why this is the flagship remaining convergence (survey, 2026-07-19)

Largest remaining rung mass × third-largest correction mass × machinery mostly built:
- **22 general rungs** in `baseline_energy.py` — plus deck-layer attach rungs (mega_lucario's
  `attach-solrock-over-line-base` family) that are ADR-0034 fold candidates once a general oracle
  prices what they hand-encode.
- **41 `misattachment` corrections** (plus a share of the 111 `sequencing_error` and 27
  `slow_setup`) — and their rationales all articulate the SAME quantity in different words:
  "needed only a single energy more to be fully powered", "don't attach more than it needs",
  "fully load one attacker over spreading", "attach toward Nebula Beam", "never Ignition when a
  Basic is available / never on Cinderace". Grep `"category": "misattachment"` for the full set;
  exemplars: 82749168-61, 82224509-31/40, 82752045-97, 82756664-35, 81904451-6/50, 82523811-59.
- This is also ADR-0065's **fourth shadow** — the develop-leaf / plan-tier credit, the one value
  shadow left staged after the gamble, refresh, and grab/pitch investigations.

## The hypothesis (one sentence)

An Energy attach's value is the **marginal progress it buys toward a USABLE attack by that body's
deadline**, priced by the attack it advances:

```
attach_value(energy E → body B) =
    [ P(B lands a valued attack by its deadline | attach) − P(… | don't) ]   ← the marginal, again
    × value(B's best attack it advances)                                     ← the existing KO/damage oracle
    − resource_cost(E)                                                       ← E's own worth (TAG_TIER:
                                                                               a burst spent ≈ its keep-cost)
```

The 22 rungs are shadows and premise-gates of this one quantity: concentration
(`concentrate-energy-on-wincon`, `build-active-wincon`, `spread-attach-to-the-needy`,
`concentrate-accel-on-one-line-body`) = the P-term maximised per-body, not spread; target choice
(`power-up-attacker`, `dont-fund-the-non-attacking-body`, `dont-power-the-draw-engine`) = value=0
for a body with no valued attack; type fit (`dont-waste-off-type-energy`) = the payable slot;
doomed modifiers (`dont-feed-the-doomed` / `arm-the-doomed-active` — a SIGNED pair) = the deadline
term (a body dying next turn has deadline NOW: an attach either arms tonight's attack or is worth
0); resource class (`prefer-reusable-over-burst`, `conserve-burst-when-no-ko`,
`dont-waste-discard-energy`, the whole Ignition family) = `resource_cost(E)` via the worth oracle
(TAG_TIER `discard_eot` already prices the burst); over-attach ("more than it needs") =
the marginal term going to 0 once `maxDamageCost` is met.

## Machinery that already exists (verify at source, then reuse — don't rebuild)

- Per-attack damage/KO oracle (`predicted_damage`, ADR-0032/0052) and `_attack_type_payable` /
  `maxDamageCost` / `minAttackCost` (the "fully powered" facts).
- The deadline substrate: `active_doomed` / `incoming_active_damage` (ADR-0064) and the gate
  library seam (ADR-0065 Stage 1) — **the quota gate's first real consumer is HERE**: 1 attach per
  turn means a body needing k more Energy has deadline ≥ k turns; that is the spec's Round 8 §2
  quota intuition, derived not asserted.
- Accel riders (`_recover_units`, `recoverTarget`/`recoverSource`) — attach-from-hand competes
  with accel coverage (`feed-the-firing-accelerator`, `advance-the-accel-pieces` are premise-gates
  on which SOURCE fills the slot).
- `card_worth` (role/TAG tiers) for both the target's worth and `resource_cost(E)`.

## Round 0 — the measurement pass (DO THIS FIRST; the combat-tempo lesson)

Replay all 41 misattachment corrections (join `reviewed.json`; FRESH pilot per replay) through the
real `explain()`. Classify: already-passing (a large fraction is expected — several of these boards
predate ADR-0062/0064/0065 and the 2026-07 tuning rounds) / target-choice / over-attach /
resource-class (Ignition) / spread-vs-concentrate / doomed-sign / timing-only (sequencing —
`attach-energy-last` is structural, NOT this grill's). Only the legs the survivors actually flag
get converged. Build the corpus family (pins + xfail targets) in the hyperclosure-corpus style.

## The grill agenda

1. **The unit.** Damage? P(KO)? "attacks enabled"? Inherit the exchange-rate ruling from the
   gust/disruption grills; if they punted, THIS grill must settle at least the local rate
   (attach-value band vs the tuned rung weights it replaces — the ADR-0060 calibration-anchor
   pattern: seed the mid case at the old currency).
2. **The deadline term.** Quota-derived (k Energy short → k turns) × threat-derived
   (`active_doomed` ⇒ deadline now). Is the gate library's `deploy_odds` seam the right home
   (extend with a quota gate), or a local closed form first?
3. **Spread vs concentrate is a PORTFOLIO question** — sets not sums, again: the value of this
   attach depends on planned NEXT attaches (concentrating 3-on-one beats 1-on-three for a 3-cost
   wincon). The `_greedy_grab` virtual-board re-scoring is the in-repo precedent shape.
4. **The doomed SIGN.** `dont-feed-the-doomed` (−) vs `arm-the-doomed-active` (+) flip on whether
   the attach enables an attack THIS turn — the oracle computes the sign from deadline × payable;
   grill that both corrections' fixtures survive the fold.
5. **resource_cost(E).** Ignition/burst via TAG_TIER's `discard_eot`; typed-Basic via
   `ENERGY_TIER`; is spending-cost just keep_cost of the spent card (the clean answer), or does
   attach-vs-hold need its own term (held-card-risk seam B overlaps — coordinate)?
6. **Fold list.** Which of the 22 fold into the oracle; which SURVIVE as structure
   (`attach-energy-last` = sequencing tier; `use-acceleration` = source selection;
   `feed-the-line-for-disruptor-lock` = a lock maneuver, ADR-0061's family) — and which DECK rungs
   fold per ADR-0034 (the mega_lucario attach family; note ml f87: the `attach_is_energy` gate —
   Tools ride the ATTACH option type too, the oracle must not price a Tool as Energy).
7. **Where it lands.** A tactical (`_attach_value_tactical`, the ADR-0062 shape: signed, replaces
   the endorsement band) vs re-pointed rung magnitudes — the same migration-path question as the
   discard convergence (seam D); their ruling is precedent.

## Hazards (paid for — don't re-buy)

- The +76 shape: seed the calibration at the old currency's mid-band; full-family re-audit — the
  attach pins span `test_blunder_*`, the deck-strategy tests, the six ADR-0060 pins (attach
  ordering feeds `attach-before-hand-shuffle`), and now seam A's `test_attach_target_priority.py`.
- ml f87 (a Tool attached as if Energy) — option-type discipline.
- Anti-speculation, AS AMENDED by the shadow ruling: Round 0 no longer gates BUILDING the oracle —
  it gates each family's SWAP. If the ladder already satisfies most of the 41 (plausible — it is
  the most-tuned family in the repo), the oracle still ships as a shadow emitter; the passing
  families swap last (or never), the failing legs swap first, and shadow/rung DISAGREEMENT rows on
  live telemetry become the discovery channel for latent ladder bugs the corpus never caught.
- Held-card-risk (B, now shipped) overlap on hold-vs-spend — read its landed shape first.

## Sibling — promote/retreat (its own seed: `promote-retreat-grill-spec.md`)

RETRACTED (2026-07-19): this section originally called promote/retreat "a cheap composition of two
existing oracles" — the user's counterexamples refuted that (a zero-Energy Cinderace with a fetcher
in hand beats an energized benched wincon; the alternating sacrifice ladder). The real shape is a
prize-trade DIFFERENTIAL with closure-aware readiness — seeded properly in
`docs/plans/promote-retreat-grill-spec.md`. The two grills share the readiness machinery (the
gamble's one-attach-short Outcome Classes) and the currency; ideally one session owns both
agendas' readiness question.

## Build shape (per the shadow ruling)

**Phase 1 — the shadow oracle (after the grill settles the design; no swap gate needed):** build
`attach_value` computing at the real decision point, emitting per-option in the trace (the
gamble-trace pattern: inner terms — P-delta, deadline, the valued attack, `resource_cost` — plus
the output and the AGREEMENT bit vs the rungs' pick). Mid-sim guard; memoise the deck-fixed legs.
**Phase 2 — staged swaps:** Round-0 corpus family + shadow-telemetry disagreements rank the fold
order (failing legs first, agreeing families last); each swap under corpus + score-diff + the
currency-zone rule (the oracle REPLACES the rungs it shadowed). Deck-rung folds via /deck-align
(ADR-0034). Earns its own ADR (the fourth shadow's) at the first swap.
