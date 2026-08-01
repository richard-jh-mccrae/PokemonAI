# ADR-0102 — Hand-size relief is the SURVIVAL a refresh buys, on BOTH hands

**Status:** Accepted 2026-08-02; **BUILT**. Promotes the reporting-only design-B signal of
`docs/plans/hand-disruption-grill-spec.md` (grilled 2026-07-19, rulings 1a/2a) into `score` and
deletes the three flat rungs it replaces. Build = **Issue #261 item 2c** (POC-T2), absorbing old
Issue #221.

**Context issues / ADRs:** [ADR-0092](0092-the-value-system-poc-builds-by-differencing-tracks-with-wave-rulings.md)
(the POC and its directive 1 — the swap IS the deletion),
[ADR-0060](0060-hand-refresh-value-is-a-closed-form-card-swing.md) (the refresh swing this term sums
beside, and the +76 endorser-inflation guard),
[ADR-0062](0062-energy-denial-is-what-the-strip-actually-takes-away.md) /
[ADR-0063](0063-a-booster-scales-the-oracle-and-a-doomed-body-denies-nothing.md) (price the quantity,
don't threshold it; a booster SCALES, never adds),
[ADR-0064](0064-incoming-is-one-threat-clock-curve.md) (the Threat Clock and its per-consumer
conservatism), [ADR-0071](0071-the-promotion-gate-and-the-accumulating-clock.md) (the accumulating
survival clock and the promotion gate),
[ADR-0078](0078-the-value-currencies-are-three-scales-bridged-by-derived-rates.md) **decision 6**
(one path may not carry both race scalers), [ADR-0080](0080-deny-is-a-categorical-relevance-instrument-not-a-magnitude-one.md)
**decision 3** (which withdrew that retirement, and why it does not apply here),
[ADR-0101](0101-the-refresh-shed-is-a-set-marginal-not-a-sum-of-copies.md) (item 2b, and the PARKED
design A this term deliberately does not wait for).

## Context

Three flat rungs stood in for one unmodelled quantity — the damage an attacker scales off a hand:

| rung | weight | gate |
|---|---|---|
| `play-harlequin-vs-hand-size` | +25 | `hand_disruption` play AND `opp_has_hand_size_attacker` |
| `disrupt-when-unfavored` | +18 | the same, AND the Read says unfavored |
| `strip-the-stacked-engine-hand` | +22 | a ONE-SIDED strip on a stacked hand facing a draw engine |

The grill measured 80 corrections against them and found the cluster dissolved — no correction
demonstrated a misfire — so it ruled the promotion **evidence-gated** and shipped the calculation
REPORTING-ONLY (`Pilot._hand_size_relief`, `OptionTrace.hand_size_relief`, telemetry `hs_relief`),
so that the signal would be visible while it earned its way into `score`. ADR-0092's POC changes what
the gate is: a track deletes its rung pile and lets the deterministic gates rule the flips, rather
than waiting for a correction to arrive. Item 2c is that promotion.

The grill also recorded, at source, exactly why a flat cannot do this job (design B):

1. **Undervaluation.** The refresh swing prices their cards at `_REFRESH_OPPONENT_HAND_STRIP` = 4
   apiece; Alakazam's Powerful Hand (MEG 743, *"2 damage counters … for each card in your hand"*) is
   **20 damage** a card. The +25 papered over a fifth of the quantity.
2. **A sign hole.** At their hand 1 the terms netted ≈ +1, so the Pilot Judged an EMPTY Alakazam hand
   and refilled it from 20 to 80 damage aimed at its own Active — the shape of the human's CRITICAL
   on ml 85709280 f111, *"such an enormous blunder"*. The +25 had no opponent-hand gate at all.
3. **Flat 20/card is also wrong.** 80 damage denied is worth ~0 if my Active survives either way and
   a great deal if it does not. *"The correct currency is MARGINAL vs my own KO."*

## Decision

### 1. The value is the SURVIVAL the refresh buys, off the clock that already measures survival

`Pilot._hand_size_relief_tactical` asks `turns_to_ko_me` twice — once at the hands as they stand,
once at the hands the card leaves both players on — and prices the difference:

```
relief = prize_to_damage( survival_value( turns_to_ko_me(after) − turns_to_ko_me(now), phase ) )
```

Nothing new is introduced. The counterfactual is two keys of the Damage Formula's own
opponent-as-attacker context (`atk_hand` / `def_hand`), which is where every hand scaler already
reads its count; the two redraw numbers are `strategy/refresh.py`'s own branch facts, averaged over
the coin exactly as `net_change` averages them; the survival→prize conversion is the sub-prize leg
the deny / gust / snipe / promote family already shares; and the crossing to the damage scale is the
derived `currency.PRIZE_DAMAGE_RATE`.

All three failures close as arithmetic rather than as gates. Denial that does not move the Knock Out
reads 0 because both clocks agree. A refill SHORTENS my clock, so the shift is negative and the term
declines — sign-correct by construction. And a benched hand-size line, which the +25 paid full price
for, is graded by its real distance through the same promotion gate (`opp_active` +
`switch_enabler`) every other threat read uses.

**Why the graded clock rather than the `active_doomed` boolean the grill's wording names.** A
boolean flip is a cliff, and it is BLIND on exactly the frame the design was written around: on ml
f111 the refill need not flip my Active from safe to doomed to be a blunder — against a 200 HP Active
it moves the clock from ten turns to three and the boolean never moves. `turns_to_ko_me` is the same
oracle read at a finer resolution (doom is `ko_me <= 1`), so this is the ADR-0060 rule applied to the
grill's own wording: price the quantity, don't threshold it.

### 2. BOTH hands, because the card moves both and the set scales off both

`atk_hand` is THEIR hand and moves only for a symmetric refresh — the `opponent_shuffles`
discriminator, applied for the same reason `net_change` applies it. `def_hand` is MY hand, and every
refresh in the table moves it, including the self-only ones.

That leg is not hypothetical. Verified at `data/EN_Card_Data.csv`: **Mega Froslass ex** (861,
Resentful Refrain — *"This attack does 50 damage for each card in your opponent's hand"*) and
**Chandelure** (98, Mind Ruler, 30/card). Fifty a card is more than twice Powerful Hand's twenty, so
a term named for the hand-size damage swing that priced only the opponent's hand would have left the
BIGGER of the two scalers in the set unmodelled. It also produces a discrimination no flat rung could
express: against a Froslass, holding ten cards is 500 incoming, and **Judge (redraw 4) is the
survival play while Lillie's at exactly six prizes (redraw 8) is not** — off the two cards' own
printed draw counts.

### 3. Lever A returns as `phase_scale`, NOT as a second multiplier

`disrupt-when-unfavored`'s posture half survives as a MULTIPLIER and never as a flat — the ADR-0062
discipline, which the grill restated. It returns as `needs.phase_scale` rather than
`_DENIAL_UNFAVORED`, because **ADR-0078 decision 6** ruled that both say *"when the race is going
badly this is worth more"* and a path carrying both multiplies one race read by itself. ADR-0080
decision 3 withdrew that retirement for deny on the stated grounds that *"under this ADR deny reads
`phase_scale` on no surface, so the substitution justifying it no longer exists"* — a condition that
is false here: this term reads `phase_scale` directly, as its survival currency's own scaler. So the
substitution ADR-0078 chose is taken, and it is the better instrument on its own terms: board-derived
rather than Read-gated, bounded [0, 1] rather than unbounded, and live without matchup coverage.

### 4. The energy policy is `UNCHARGED`, the doom policy — named, not inherited

The opponent-target rows take the CEILING (`charged=None`); this term does not, and the difference is
not cosmetic. Under the ceiling an unresolvable attack cost is read through `can_pay_cheapest`, which
is **fail-CLOSED** — `CombatMath._affords` says outright that pointed at the opponent this means *"I
cannot tell what this costs, so assume it cannot reach me"*, which is the one thing a survival read
must never say. This term is the graded generalisation of `_active_doomed`, so it fails the way doom
fails: `UNCHARGED`, where an unresolvable cost counts as payable and the current form is charged no
affordability at all. Threading the Read's own budget instead would let a matched Brief quietly relax
a survival read. The `doom-ceiling-fail-direction` whitelist entry is the policy; ADR-0064 decision 1
is why it is a per-consumer choice and therefore has to be stated at the call.

### 5. No card-fact gate in front of the clock

An earlier cut guarded the two clock reads with *"does any line here scale off a hand"*, read off
`CardStat.handSizeDamage`. It was deleted before merge: it is a second enumeration of the Damage
Formula's scaler families, free to disagree with the oracle it guards — the exact drift
`combat.card_level_damage` was extracted to end, and the same defect in miniature as the
`hand_size_attacker` TAG the retired rungs gated on. The clock is the authority. On a board where
nothing scales off a hand the two reads are equal and the term is 0, which is the answer a guard
would have given and cannot fall out of step with the table.

### 6. Deletions

- `play-harlequin-vs-hand-size` (+25), `disrupt-when-unfavored` (+18) — replaced by this term.
- `strip-the-stacked-engine-hand` (+22) and `_STACKED_HAND` = 6, its last reader. ADR-0060 kept it as
  a forward contract for a ONE-SIDED strip; no such card is in the pool, so it has never fired on a
  real board and its three tests had to mint a card that does not exist to exercise it. A live weight
  behind an unfired gate is not a dormant contract — it is an untested rung that fires at full
  strength the first time the set grows, which is how `disrupt-when-unfavored`'s own stale gate came
  to play a Hammer into a Knock Out turn (ms 83968638 f17). The doctrine is kept where doctrine
  belongs: the grill spec's fold list, and the weight-0 `disrupt-the-tailored-hand` mirror, which
  decides nothing and so cannot surprise a future pool.
- `mega_starmie/tuned.json`'s `disrupt-when-unfavored: 17.15` override.
- `OptionTrace.hand_size_relief` and telemetry `hs_relief` — the reporting-only pair existed to make
  the calculation visible while it earned promotion. Promoted, a second differently-shaped copy of a
  live term's own summand would be a shadow of it.
- `Board.opp_has_hand_size_attacker` + `Pilot._opp_has_hand_size_attacker`, and
  `Board.opp_draw_engine_in_play` — unconsumed the moment their rungs left. POC-T0's rule is that an
  unconsumed Board signal is an unbuilt feature; leaving two behind would have been the dead surface
  T1's purge exists to prevent. `_draw_engine_ids` survives (the Read still consumes it).

## Consequences

**Currency.** `needs.opponent_target_value`'s survival leg is extracted as `needs.survival_value`,
SIGNED and symmetrically capped at `±_SURVIVAL_CAP`. `opponent_target_value` keeps its `max(0, …)`
floor at its own call site, where the reason for it is legible — removing an opponent body can only
raise my clock, so a negative reading there is a bench-harvest redirect artefact. The hand-size
counterfactual has no such guarantee, and the sign IS the term.

**Magnitude.** One turn of survival is `phase × 0.5` prize; at the 0.3 phase base that is **15
damage**, rising toward the `_SURVIVAL_CAP` 90 as the race sharpens. The rungs it replaces summed to
at most +43, so the swap starts in the same band early and outgrows it exactly where the grill said
it should — when the Knock Out is close.

**A recorded residual, not hidden.** Against a hand-size deck this term and the swing's GIFT leg both
price a refill: the swing charges `_REFRESH_OPPONENT_HAND_GIFT` = 8 per card handed back, and the
relief charges the damage those cards arm. The grill anticipated exactly this and answered it —
design A grades the GIFT leg DOWN against a hand-size deck, because there the cards are fungible
count-ammo with low keep-cost, *"so design A grades that leg down while this term carries the
damage."* Design A is **PARKED on measurement** (ADR-0101: 59.4% of an opponent's representative
build prices `role_value` 0), so the double-charge stands until its named prerequisite —
`gusting-keepcost-design.md` §2's shared opponent role sheet — exists. It is bounded, it lands only
on refills, and it errs toward DECLINING one, which is the fail direction ADR-0060's +76 guard
demands of every opponent-side unknown.

**Whitelist.** No new constant. Every magnitude the term reads (`_SURVIVAL_PER_TURN`,
`_SURVIVAL_CAP`, `_PHASE_*`) is already covered by the `firing-equation-constants` entry's *"planner
sub-prize constants"*, and `PRIZE_DAMAGE_RATE` is derived.

**Tests.** `test_hand_size_relief.py` is re-pointed, not deleted — the grill's re-baseline surface
requires the `score == Σ fired + tactical` invariant to survive the rewiring, and it does: the relief
now arrives inside `tactical`. Three synthetic fixtures gained the card fact they had been asserting
through a label (`handSizeDamage` on the Alakazam stand-ins); `test_posture_read.py`'s three
`strip-the-stacked-engine-hand` tests are deleted with the rung and deliberately not re-pointed onto
a successor, because there is none and inventing one would misrecord what happened.
