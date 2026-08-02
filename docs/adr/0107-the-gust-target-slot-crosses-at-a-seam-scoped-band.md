# ADR-0107 — A prize-denominated marginal enters the Worth DP as a FRACTION of a band, not as a number; and the gust-target instrument was binding on one corpus frame in eighty

**Status:** Accepted; **BUILT** 2026-08-02. Build = **Issue #313 item 2g** (the target-side half),
carved out of Issue #261 (POC-T2) when that tracker closed. Discharges old Issue #189's target/keep
side and **ADR-0076 Amendment E's currency debt**, which **ADR-0080 decision 4** re-inherited here
with Amendment F reversed.

**Amends [ADR-0076](0076-the-opponent-target-slot-family-splits-by-instrument-shape.md)** (whose
decision 1 priced the `gust_target` slot in the wrong currency, and whose Amendment E recorded that
as a debt) and **[ADR-0078](0078-the-value-currencies-are-three-scales-bridged-by-derived-rates.md)**
(whose scale catalogue gains its first prize↔worth row). Follows
**[ADR-0086](0086-the-deploy-marginal-is-one-equation-over-the-needs-assignment.md) amendment C** and
**[ADR-0105](0105-the-free-item-hold-price-is-the-keep-machinery-floored.md) decision 3** in form: a
seam-scoped rate, stated plainly, carrying a reconciliation debt. Does **not** supersede anything.

**⚠️ Scope, per Issue #313's own instruction.** The five gust *whether-to-play* rungs
(`gust-for-the-ko` +50, `gust-for-the-loaded-equal-ko` +50, `gust-for-the-stall` +10,
`stall-gust-over-dev-when-starved` +95, `gust-to-strand-the-key-attacker` +20 — verified at source in
`doctrine_gust.py`, not recalled) are **untouched**. Their deletion is T4's differencing
(Issue #263) and the swap IS the deletion; deleting or tuning them here would be exactly the interim
rung-fitting ADR-0092 exists to prevent.

**Context issues:** Issue #313 (this build), Issue #261 (POC-T2, where 2g was specified), Issue #189
(S4-gust, absorbed), Issue #186 / ADR-0076 (the slot family and the debt), Issue #199 / ADR-0080 (the
underivability measurement this starts from, and decision 4's re-inheritance), Issue #197 / ADR-0086
(the ratio pattern), Issue #261 item 2f / ADR-0105 (the sibling seam rate, landed hours earlier),
Issue #259 / ADR-0097 (`POC_WORTH_PRIZE_RATE`, which owes the reconciliation), Issue #262 (POC-T3,
which owns authoring it).

## Context

ADR-0076 decision 1 gave held gust-effect Trainer cards their own slot kind, priced by the real
per-body `needs.opponent_target_value` instead of the flat disruption tier the `deny` kind uses. That
marginal is denominated in **prize-equivalents** (1.0 – 3.9). Every other slot kind in the same
*summed* `needs._keep_slot_dp` assignment is denominated in **card-worth points** — wincon 30,
`discard_eot` 30, `deny` 10, Energy 8 — and `needs.py`'s own module docstring says slots are valued
"in the ONE currency".

Amendment E recorded that mismatch, judged it *"latent, not firing — 331 corpus frames show 0 decision
flips because the general-worth floor absorbs the drop"*, and handed it to Issue #189. Amendment F
then moved it to the shared layer; ADR-0080 decision 4 moved it back, and ADR-0080's Consequences
predicted the wall it would hit — Issue #189, it says, *"will hit the same underivable-rate wall, and
it has no escape route of deny's kind — a gust card's value genuinely IS a magnitude."*

### Measured before anything was written (2026-08-02, 371 replayable corpus frames)

The "latent" reading is too kind, and the measurement says so plainly. **80 frames emit a
`gust_target` slot; 228 slots in all:**

```
slot value (prize-equivalents)   min 1.000   median 1.000   mean 1.202   max 3.192
```

The card that opens that slot — a Boss's Orders, `TAG_TIER["gust"]` 10.0 — also opens a `general`
latent-worth slot at `worth × deploy × _GENERAL_WORTH_W × liq`, which tops out at **4.5**. A card
takes at most one slot, so the DP compares the two and takes the larger. Asking whether the gust slot
ever WON that comparison is the question that matters, and it is asked directly — zero the
`gust_target` slots' value, re-run the assignment, and see whether `V` drops:

> **The assignment covered a `gust_target` slot on 1 frame in 80** (`86090164|1|turn|10`, `V` drop
> 1.900). Denominated, the same measurement reads **25 of 80**.

Amendment E's *"0 decision flips"* was not the instrument agreeing with the incumbent. It was the
instrument being all but **inert** — armed ON in the shipped PROFILE since 2026-07-27, reachable,
computed every decision, and reaching the answer once in eighty boards. The `keep_v2` reading agrees:
median **4.500** across 83 readings, the general slot's ceiling to three decimals, with a single
outlier at 1.900 — that one frame.

⚠️ **The tempting shortcut here is wrong, and it was caught in review rather than shipped.** An
earlier draft of this ADR argued the inertness *structurally*: "3.9 < 4.5 on every board there is, so
it can never win." That does not follow. The general slot is a PRODUCT — `worth × deploy ×
_GENERAL_WORTH_W × liq`, where `_general_liquidity` can return `_GENERAL_ILLIQUID_FLOOR` (0.15) —
so 4.5 is its **ceiling, not a floor**, and it can fall below the gust slot. That is precisely what
happens on `86090164|1|turn|10`. A de-duplicated `general` slot (one per distinct cid) also leaves a
SECOND copy of a gust card facing no general competitor at all. The claim survives only as the
measurement above, and it is stated that way everywhere it appears.

That reframes the item. It is not "a denomination is untidy"; it is "an armed instrument is very
nearly dead code, and the thing keeping it dead is a units error."

**Verified against the POST-ADR-0093 behaviour, as Issue #313's blast-radius note requires.** That
note warns that the `_planning` guard move restored the `gust_target` emission mid-sim, so 2g must
measure the new behaviour rather than the pre-PR one. Every reading here was taken on a tree at
`main` (8226a43), which carries ADR-0093 and item 2f; and the property itself is held down by
`test_gust_target_slot_resolver.py::test_the_gust_slot_survives_the_rollout_because_the_shared_rows_now_run_mid_sim`,
which asserts the emitted values are identical inside a rollout and at the root — so the conversion
lands on both readings or neither, and it passes with the conversion in place.

### What ADR-0080's measurement leaves available, taken as the starting point

ADR-0080 ran the Worth-Damage-Rate anchor gate and it **failed on the evidence**: the corpus's one
keep-side candidate prices `0.000` under both instruments, so the rate divides out. Issue #313 says to
take that measurement as the starting point, so no general rate is derived here and none is guessed.
`ADR-0097` has since voided the *structural* half of that finding and named
`state_value.POC_WORTH_PRIZE_RATE` as the constant that will settle it — but that constant is `None`,
T3 (Issue #262) owns authoring it, and T2 cannot honestly price against a number that does not exist.
ADR-0105 reached the identical fork hours earlier and rejected the same candidate for the same reason.

## Decision 1 — the marginal crosses as a FRACTION of its own ceiling, so no general rate is needed

```
worth(gust_target) = GUST_TARGET_BAND × min(1, opponent_target_value / TARGET_VALUE_CEILING)
```

`needs.TARGET_VALUE_CEILING` = `MAX_PRIZE_VALUE` (3, a Mega ex) + `_SURVIVAL_CAP` (0.9) = **3.9**.
Both terms are already shipped and both are bounds the marginal cannot exceed by construction, so the
ceiling is **derived, not chosen** — it is literally the number ADR-0076 Amendment E quotes when it
names the debt (*"max ~3.9 for a 3-prize body with 8 survival turns bought"*).

Dividing by it turns a prize-denominated magnitude into a dimensionless `[0, 1]` fraction. **The prize
scale therefore never escapes the marginal**, which is ADR-0086 amendment B's deploy argument reused
rather than re-derived: *"the Worth points cancel and the Worth scale never escapes the assignment.
That is what lets the equation exist without the constant."* Here it is the prize points that cancel.

`currency.py`'s own guard test — the one that fails the moment a `WORTH_DAMAGE_RATE` or a
`prize_to_worth` appears — is untouched and still passes. That is the check on this decision, not a
coincidence: a build that needed the general rate could not have left it standing.

**The consequence worth naming.** The two members of the opponent-target slot family are now the same
SHAPE. ADR-0080 decision 3 made the armed `deny` slot `TAG_TIER["gust"] × relevance∈[0,1]`; this makes
`gust_target` `TAG_TIER["gust"] × fraction∈[0,1]`. One family, one form, two different `[0,1]` reads
of "how good is this target" — which is what ADR-0076's *"splits by instrument SHAPE"* should have
produced in the first place and did not, because one instrument's read came pre-denominated.

## Decision 2 — the band is `TAG_TIER["gust"]`, a preservation choice with a measured incumbent

`currency.GUST_TARGET_BAND` is read off `card_worth.TAG_TIER["gust"]` at import — **not a new number,
and not a new authored constant**: it is the same disruption-Trainer band `deny` already fires at, the
same one `hold_value.ITEM_HOLD_FLOOR` is pinned to, read at import so a re-band of the tiers moves it
rather than silently re-scaling the slot. `GUST_TARGET_WORTH_RATE` = band ÷ ceiling ≈ **2.564 worth
points per prize-equivalent** is the *quotient*, named so a reviewer can dispute a rate instead of
reverse-engineering an arithmetic.

**A PRESERVATION CHOICE, never a derivation** (`DEPLOY_BAND`'s discipline, applied verbatim). The
incumbent it preserves is the routing ADR-0076 replaced: before the `gust_target` kind existed, a held
Boss's Orders opened a `deny` slot worth exactly `TAG_TIER["gust"] / 2**t`. Measured over the same 228
corpus slots:

| | median | mean | max |
|---|---|---|---|
| pre-ADR-0076 `deny` routing (`10 / 2**t`) | **2.500** | 2.695 | 10.000 |
| this band's denomination | **2.564** | 3.082 | 8.184 |

So the band is not merely asserted to sit in the incumbent's range — the distribution it reproduces
*is* the recorded one. That is the check `_PRIZE_UNIT = 12` (wrong by ~8×) never had, and it is a
stronger form of it than `DEPLOY_BAND`'s own, which brackets a range rather than matching a
distribution.

## Decision 3 — the crossing is NAMED in the catalogue, and its ~39× disagreement is recorded

`currency.py` catalogues the de-facto rates. Three rows exist (trainer ~1.0, energy ~6.7, deploy
~0.83), all on the **worth↔damage** pair. This opens a fourth row on a different pair —
**prize↔worth** — and it is stated in the file in the same words ADR-0086 amendment C and ADR-0105
decision 3 use: *stated plainly rather than buried: it IS a rate, scoped to one seam.*

Naming it exposes a disagreement that must not be smoothed over. Composing the two **shipped** legs:

```
PRIZE_DAMAGE_RATE 100 damage/prize  ÷  ITEM_HOLD_WORTH_RATE 1.0 damage/worth  =>  ~100 worth/prize
GUST_TARGET_WORTH_RATE                                                        =>   ~2.56 worth/prize
```

**~39×.** Both cannot be right, and the disagreement is evidence about the **Worth scale** rather than
about this seam: that scale's entire range is 0–30 by construction (`ROLE_TIER`), so a 100-point slot
would not *price* a held card — it would delete every other card's contribution from the assignment.
That is `_PRIZE_UNIT`'s failure mode with the sign reversed. Pricing the hand on its own scale is what
the DP is for.

Recorded here and in `currency.py` rather than reconciled, on exactly the terms `DEPLOY_BAND` and
`ITEM_HOLD_WORTH_RATE` set: **if `POC_WORTH_PRIZE_RATE` is authored, this must be checked against it,
and a disagreement is evidence about ONE of the two rather than automatically about this one.**
ADR-0097 decision 1 already requires that authoring to reconcile against `currency.py`'s catalogue; it
now has a fourth row to reconcile against, and the sharpest one.

## Decision 4 — the conversion lives at the CALL SITE, and the slot factory says so

`common.needs` imports `card_worth` and `strategy.context` (both leaves) and must never import
`common.currency`, because `currency` imports `needs` for the ceiling — one arrow, one direction. So
the crossing cannot live inside `needs.gust_target_slot` without inverting it.

It lives in `pilot._resolve_needs`, at the emission, exactly as `deploy_marginal`'s Worth-denominated
result is divided by `currency.DEPLOY_WORTH_SCALE` at *its* call site and for the same reason.
`gust_target_slot`'s docstring now carries the contract in its own words — including what happens when
it is broken, since that is this ADR's whole subject.

### The design doc that says the opposite, read and reconciled rather than overridden silently

`docs/plans/gusting-keepcost-design.md` states, under the 2026-07-19 denial-ceiling ruling: *"There
is NO worth-points↔prizes conversion: opponent-side value never re-enters `card_worth`'s unit; the two
currencies meet only at the prize scale."* Read at source before this build, and it is not violated:

* that ruling governs the **play-side** equation it appears in — `gust_value(T)`, where
  `their_keep_cost` is expressed *directly* in effective prizes and clamped at ~1, and where our own
  value is already prize-denominated so the two genuinely do meet at the prize scale. That equation is
  design-only and unbuilt, and this build does not touch it;
* what crosses here is **not opponent-side value as a magnitude**. It is a `[0, 1]` grade of a
  card-worth band we already own — the fraction says *"how good is the best target"*, the magnitude
  comes from `TAG_TIER["gust"]`, which is a fact about OUR card. A prize-denominated number never
  lands in `card_worth`'s unit; it is divided out first. That is the same distinction ADR-0086
  amendment B draws for the deploy legs and ADR-0080 decision 3 for deny's relevance.

The doc is left as written. Its ruling is about the play side and stays true there, and reversing a
recorded ruling by side effect of a keep-price fix is exactly the drift this repo keeps paying for.

**Rejected: hoisting `_SURVIVAL_CAP` into `currency` to invert the import.** It is a policy about the
opponent-value equation, not an exchange rate, and moving it would put half of one equation's bounds
in another module. `currency.py`'s contract is conversions (ADR-0105 decision 3's own split, applied
in the other direction).

**Rejected: `MAX_PRIZE_VALUE` read from `CardStat.prize_value`.** `common.scouting` must not depend on
`common.strategy` — the Provider is the card-facts leaf every strategy module reads. The constant is
homed in `strategy.context` beside `PRIZE_CARDS` (the same *kind* of fact, and `needs` already imports
from there), leaving two spellings of one fact, which ADR-0087 charges for. The net is therefore a
TEST rather than a shared import: `test_currency.py` walks the CSV's Rule column, resolves each Rule
**through `CardStat.prize_value` itself**, and asserts the constant is that population's maximum — so
neither reader can drift off the card set, and a future set introducing a fourth Rule fails loudly.

## Measured at the build (2026-08-02, against the committed baselines)

Baselines first, on the unmodified tree, so every number below is a delta and not a reading:

```
BEFORE   Decision Gate        PASS   0 unruled, 0 held out, 0 voided
                              agree 251/345, 0 picks moved
         Discrimination Gate  PASS   0 unruled, 2 held out (both owner=#262), 0 voided
                              agree 180/247 -> 179/247, 3 picks moved, 1 IMPROVED
                              (main's own uncaptured drift — ADR-0105 deliberately left it)

AFTER    Decision Gate        PASS   0 unruled, 0 held out, 0 voided
                              agree 251/345, 0 picks moved            <- IDENTICAL
         Discrimination Gate  PASS   0 unruled, the SAME 2 held out, 0 voided
                              agree 179/247, the SAME 3 picks, the SAME IMPROVED
```

**Zero decision movement and zero leaf movement, so there are no wave-2 flips to rule.** Stated
precisely rather than as a boast: the instrument became live, and the corpus holds no ruled frame
whose outcome turns on it.

What did move is the price, and it is the point of the item:

```
assignment COVERS a gust_target slot     before   1/80 frames     after   25/80 frames
                                                  (86090164|1|turn|10, V drop 1.900)

slot value      before  median 1.000  mean 1.202  max 3.192      above 4.5:   0/228 slots
                after   median 2.564  mean 3.082  max 8.184      above 4.5:  29/228 slots

gust keep_v2    before  min 1.900  median 4.500  p75 4.500  mean 5.931
                after   min 4.500  median 4.500  p75 5.128  mean 6.537
```

**1 → 25 of 80 frames** is the whole finding in one line: the slot ADR-0076 built now wins the
assignment on nearly a third of the boards where it is emitted, where before it won on one. The
`keep_v2` minimum rising from 1.900 to 4.500 is that same single frame from the card's side — its
cheapest shed is no longer under the card's own latent worth.

The three rows measure different things and are kept apart on purpose: the first is the property that
matters (did the DP CHOOSE it), the second is the price, the third is what the price does to the
card. Only the first licenses "the instrument decides"; the "above 4.5" row is a value comparison
against a ceiling and cannot, which is exactly the inference this ADR's own Context section flags.

**Suite:** **4544** passed, 5 skipped, 4 xfailed, 1 xpassed — main's 4540 plus this build's four new
tests. The `xpassed` is the pre-existing unruled one ADR-0103 recorded
(`test_counter_mover_attach.py`, `86091728-19`), unmoved by this build.

Neither baseline is re-captured. Both gates PASS with zero attributable movement, and re-capturing a
passing gate's baseline absorbs movement nobody ruled — ADR-0105's own reasoning, and the leaf
baseline's outstanding 3 picks are precisely what it declined to swallow.

## Consequences

- **An armed flag is not a live instrument, and nothing in the process caught it for six days.**
  `gust_target_slots` cleared a paired-A/B gauntlet, a 331-frame sweep and the Discrimination Gate,
  and all three reported clean *because the code they were measuring decided one frame in eighty*.
  The 0-flip sweep in ADR-0076 Amendment D is the same species of vacuous green its own Issue #243
  amendment already found in `threat_sweep --slots`. **Generalised: a flag that arms a new value into
  a MAX-shaped assignment needs one more check than a flag that arms a new term into a sum — "did the
  assignment ever CHOOSE it?" — and no standing instrument in this repo asks that.** The question was
  asked here with a throwaway probe (zero the kind's slots, re-run `assignment_value`, watch `V`
  drop), and its answer is this ADR, per ADR-0089 — but a *standing* coverage report for the DP is
  real work and this item did not do it. Any future slot kind arms blind unless someone builds it.
- **The blast radius is exactly one call site, and that is a measured fact rather than a hope.** The
  `value` key on an `_opponent_target_rows` row has precisely ONE live reader in `pilot.py` — this
  emission (the deny fire rung reads `relevance_fire`, the hand-size relief reads `survival_value`
  and converts through `prize_to_damage` itself, snipe reads its own instrument). So no other
  consumer's denomination could have been changed by this, and none was.
- **The `deny` and `gust_target` kinds are now commensurable**, which was ADR-0076's premise. Anything
  later comparing the two — T4's differencing most of all — reads one scale.
- **T4 (Issue #263) inherits a target-side price it can trust.** Issue #313 stages the five
  whether-to-play rungs' deletion behind that landing, and the swap replaces the *play* decision, not
  the keep price this ADR fixes. The two halves now speak the same currency at the seam where T4 will
  join them.
- **A fourth catalogue row, and the reconciliation debt sharpens.** `POC_WORTH_PRIZE_RATE` now owes a
  check against a ~39× disagreement rather than the ~6.7× spread ADR-0097 quotes. That is a harder
  question than the one it was chartered with, and it is better to meet it in the authoring note than
  after the constant ships.
- **No new authored number.** Both ends of the rate already shipped; `sound_rules`'
  `firing-equation-constants` entry names the band because a reader must be able to find it, not
  because the whitelist grew.

## Alternatives rejected

- **Convert at the composed rate (~100 worth per prize-equivalent).** The arithmetically "honest"
  answer from the shipped legs, and it makes the DP meaningless: a single gust slot at 100–390 points
  swamps a 30-point wincon and every other card's marginal becomes rounding error. The scale it is
  converting *into* has a 0–30 range by construction, so this is not a rate disagreement to resolve in
  the rate's favour — it is a category error about what `card_worth` is for.
- **Anchor the band at the incumbent's CEILING instead of a preserved distribution** (i.e. keep 10.0
  as the max, which is what this does) **but derive the fraction from a per-decision normaliser** (the
  best target on THIS board). Rejected on ADR-0086's recorded grounds for the deploy scale: a
  per-decision normaliser makes the best available target read 1.0 whether it is a Mega ex or a
  Dunsparce, and the keep price must mean the same thing on every board.
- **Delete the `gust_target` kind and route gust back to `deny`.** Byte-smallest, and it would end the
  denomination question by ending the instrument. It is a rollback of ADR-0076's ruling on grounds
  ADR-0076 already heard (*"a Boss's Orders doesn't strip Energy; pricing it through `deny`'s
  oracle-value/timing-grade shape never matched what it actually does"*), and it discards the real
  per-body read for a flat tier.
- **Leave it and let T4 subsume it.** The rungs are staged behind T4 for a stated reason — the swap IS
  their deletion. The *keep* price is not part of that swap; T4 replaces whether-to-PLAY. Waiting
  would leave a dead instrument armed across the whole POC and hand T4 a target-side price in a
  currency its own equation cannot read.
- **Author a general `prize_to_worth` now.** The gate for it ran and failed (ADR-0080), and the
  candidate that could supersede that failure is `None` with an owner (ADR-0097 / Issue #262). Adding
  it here would break `test_currency.py`'s guard, which is exactly what that guard is for.
- **Scale `_SURVIVAL_CAP` or the phase seeds instead**, so the marginal's range happens to land in the
  worth band. This is the fudge wearing its most convincing hat: it fixes the symptom by corrupting a
  derived sub-prize discipline that three other consumers read, and it leaves the units error in
  place — the number would still be prize-equivalents, merely ones that no longer *look* wrong.
