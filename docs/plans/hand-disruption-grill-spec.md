# Hand disruption — grill ruling: the disruptor swing stays half-flat until evidence

**Status.** GRILLED and RESOLVED 2026-07-19; the two measured build items are **BUILT the same day**
(see "Build list" below, suite green 3084). **Design B — the damage-leg replacement — is BUILT
2026-08-02 as ADR-0102** (Issue #261 item 2c), which retired rather than met its evidence gate and
amended it in three places; read the box at the head of §B before the design text. **Design A — the
STRIP/GIFT flats — is PARKED on measurement** (ADR-0101). Round 0 measured first (below); four
rulings (user,
2026-07-19). Sibling of the gusting grill — same opponent-worth input layer, disruptor jurisdiction:
the two FLAT per-card prices on THEIR cards inside ADR-0060's closed-form refresh swing
(`_REFRESH_OPPONENT_HAND_STRIP = 4` / `_REFRESH_OPPONENT_HAND_GIFT = 8`, `pilot._refresh_swing_tactical`) and the
hand-size-attacker damage leg (`play-harlequin-vs-hand-size` +25, `disrupt-when-unfavored` +18,
`baseline_disruption.py`). **Nothing is built here** — build items go to a follow-up session under
the corpus + score-diff gate; evidence-gated designs wait for their gates to trip (the grab/pitch
precedent, ADR-0065; re-confirmed by the gusting Round 0). *That last clause is the one this doc got
wrong: ADR-0092's POC retired the wait-for-a-witness standard for rung piles a track is deleting
anyway. It stands as written because the reasoning it records is what ADR-0102 had to answer.*

## The shared layer — CONSUMED from the gusting grill, not designed

The gust-target grill (same day) ruled on the opponent-worth layer both consumers share
(`gusting-grill-spec.md` rulings; `gusting-keepcost-design.md`; ADR-0066 "what this deliberately
does NOT do"):

- **The layer is design-only.** No opponent role sheet, no their-closure/their-deadline inputs, no
  worth-points↔prizes conversion exists in code; each leg builds only when a correction-shaped
  evidence gate trips.
- **No new exchange rate is available to this consumer either** — and none is needed: the refresh
  swing already lives in tactical points, and ADR-0062 already fixed the damage↔points rate at
  `_DENIAL_PLAY_W = 1.0` (one point per damage-point denied). The damage-leg design below is fully
  priceable in existing currencies.
- **Derive-first, fail-live, haircut** (design §2–§4) govern any future their-hand expectation
  model. Requirements this consumer states on the layer for whenever it builds: the per-card
  strip/gift grading consumes the SAME rep (their decklist − tracker-observed) and the same
  derive-first role sheet — one layer, two consumers, never a parallel system.

## Round 0 — the measurement (results)

**Corpus family:** grep `judge|harlequin|stamp|iono|hand` over rationale + labels + category across
`data/corrections/` → **80 hits of 372** corrections ("iono" matches nothing — the card is not in
this pool; the known refreshes are Judge 1213, Harlequin 1223, Unfair Stamp 1080, Lillie's 1227,
Lacey 1199, `strategy/refresh.py`). `reviewed.json` joined; all 80 replayed through the real
`Pilot.explain()` with a FRESH pilot per replay (`train.tuner.retest.retest`, built via
`common.runtime.build_pilot` — the statefulness lesson honored). Every `fixed=False` disambiguated
by full option traces (scores, fired rules, `deferred` markers) against the `_finish_turn_last`
resequencing artifact, per the gusting Round-0 method notes.

**Headline: the cluster dissolved.** 80 → 57 pass outright → 23 `fixed=False` → **1 genuinely-open
disruptor failure**, plus one trace-observed gate defect. The corrections do NOT motivate grading
the flats or replacing the damage-leg rungs.

| bucket | count | keys |
|---|---|---|
| pass outright (`fixed=True`) | 57 | incl. ms f45 (83966968-45), f100 (84897262-100), the dragapult Judge/Stamp discard picks (83686860-18/-35) |
| refuted set-asides | 4 | 82523811-59, 82524455-6, 82756664-9, 83966968-78 (the gust KO-leg pin) |
| covered / fixed set-asides | 8 | 82224509-71, 82229122-33, 82750161-16, 82756664-74, 83054602-32, 83117367-34, 84071010-15, 85058574-109 |
| sequencing artifact — disruptor substance VERIFIED | 8 | 85709280-111 (Judge **−32.36** on my8/opp1 — the f111 pin holds), 82752045-94 (Lillie's **−21.69**, f94), 82753102-109 (Boss's 0.0 — gust-ruled, ADR-0066), 83037962-49 (Harlequin **−18.81**), 83038055-51 (Lillie's **−49.19**), 82522698-36 + 82523811-93 (Harlequin suppressed by `attach-before-hand-shuffle`), 82226759-64 (Harlequin **endorsed 83.96** vs Alakazam and played this turn — f64) |
| residual out of disruptor jurisdiction | 2 | 86091435-96 (off-type attach doctrine; Lillie's guard correct at −47.07), 83664991-43 (SHED-side: Lillie's +10.70 despite held Ignition Energy + strong hand — ADR-0065's axis, routed there) |
| **genuinely open** | **1** | **86088989-29** (CRITICAL, grab select — below) |

The six-correction regression net (ml f111, ms f60/f94/f45/f100/f64,
`tests/strategy/test_refresh_swing_pilot.py`) **holds in substance everywhere** — every pinned
score assertion reproduces; the `fixed=False` entries among them are tier-order artifacts only.

## The findings

### 1. `86088989-29` — grab-time refresh evaluation is FLAT (the one open failure)

A Team Rocket's Petrel grab select: live chose Judge, the human's correct is Lillie's ("Lillies
would have been far more helpful"). Both score a flat `grab-a-draw-supporter-in-setup` +10
(`doctrine_fetch.py:944`) — the grab context never consults the ADR-0060 swing oracle that already
knows Lillie's draws 8 early (at 6 prizes) while Judge nets 4 minus the gift. Today's replay picks
a SECOND Petrel via seam-C's `grab-the-chain-opener` +15 — an option the human never adjudicated.

### 2. `dont-gift-a-refresh-when-favored` (−15) is sign-blind to the gift

Its condition (`baseline_disruption.py:83`) fires on ANY `hand_disruption` play when favored — no
opponent-hand term — yet its rationale only justifies taxing GIFTS ("Judge/Harlequin refill the
LOSING opponent's hand too"). Observed at 83664991-43: it taxed a Harlequin that would STRIP an
8-card hand (opp_net −4, gifting nothing). Trace-observed; no correction's divergence was caused
by it (that frame's causal failure is SHED-side).

### 3. The latent `play-harlequin-vs-hand-size` refill hole — UNDEMONSTRATED

The +25 has no opponent-hand-size gate (`baseline_disruption.py:43`), so a Judge into a SMALL
Alakazam hand — which REFILLS them and arms Powerful Hand — would still be endorsed. Verified
latent at source; the Alakazam-corpus sweep (6 corrections mention hand-size/Alakazam) shows the
only live exercise of the rung (f64) endorsed CORRECTLY, and no correction demonstrates the
misfire. (The GIFT×8 side of the swing already taxes the refill's card count; what is unmodelled
is the DAMAGE armed.)

## Rulings (user, 2026-07-19)

1. **Scope — design-only, evidence-gated.** No build on the STRIP/GIFT flats or the damage-leg
   replacement. The flats stay flat; the priced designs below wait for their evidence gates (the
   grab/pitch precedent). The regression net stays the pin surface.
2. **`86088989-29` — build swing-informed grab grading** in the follow-up session: differentiate
   refresh-card grabs by their closed-form swing/draw count (`strategy/refresh.py` facts) instead
   of the flat +10 tie. Pin 86088989-29 as the fixture; the replay's unadjudicated
   Petrel-over-Lillie's pick goes back for human re-review.
3. **`dont-gift-a-refresh-when-favored` — gate it now** (follow-up build): fire only when the
   refresh actually REFILLS the opponent (opp_net > 0, i.e. their hand below the card's redraw
   count, from the same `refresh.py` facts). A sign-correctness gate inside a surviving lever —
   not a fold. Re-audit its pinned tests in the same motion.
4. **Doc home** — this file; `gusting-grill-spec.md` stays the gust record.

## Build list — BUILT 2026-07-19 (corpus + score-diff gate, suite green 3084)

Both items are shipped, `status="testing"`/tie-break scale, default ON. The 80-correction
disruption corpus re-replayed end-to-end: unchanged 57 pass / 23 residual (no regression); the six-pin
net holds; the full suite is green (the only failures are the pre-existing `plotly`-missing
meta_tracker dashboard tests, untouched by this change).

1. **Swing-informed grab grading** — BUILT. `pilot._grab_refresh_draw_tactical` + `refresh.own_draw_count`
   + `_GRAB_REFRESH_DRAW = 0.1`: at a setup TO_HAND draw-Supporter grab, a refresh's own-draw ceiling
   (prize-conditional — Lillie's 8 at six prizes) is a sub-point tie-break within the +10 band, never
   crossing the +15 chain opener. Pins: `test_grab_refresh_draw.py` (Lillie's ≻ Judge at 86088989-29;
   the tie-break stays below the chain band). **The pick stays Petrel** (seam-C chain opener) — the
   Petrel-vs-Lillie's residual is filed for human re-review, NOT pinned as chosen==correct.
2. **`dont-gift` opp_net gate** — BUILT. `refresh.refills_opponent` added to the `when`
   (`baseline_disruption.py`): the −15 fires only when the play grows the opponent's hand
   (`opp_net > 0`). Re-audited `test_posture_read.py`'s two pins to the corrected sign semantics
   (a strip at opp_hand 8 is now UNTAXED; the gift at opp_hand 2 fires). 83664991-43's trace was the
   motivating exhibit, not a chosen==correct pin (its `correct` is the attack — SHED jurisdiction).

## The fold list

**FOLDED 2026-08-02 (ADR-0102):** `play-harlequin-vs-hand-size` (+25) and `disrupt-when-unfavored`
(+18) — both REPLACED by the promoted survival term, never stacked beside it (currency-zone rule).
+18's unfavored-posture half did not survive separately, exactly as this list required; it returns
as a multiplier INSIDE the term, though as `needs.phase_scale` rather than the `_DENIAL_UNFAVORED`
this list names (design B's amendment 3, above).

**Also folded, on a different ground:** `strip-the-stacked-engine-hand` (+22), listed below as a
surviving forward contract. It survives as DOCTRINE — the entry below stands as the record — but not
as a live weight. No one-sided strip is in the pool, so it has never fired on a real board, and the
POC's standard is that a nonzero weight behind an unfired gate is an untested rung that will fire at
full strength the first time the set grows. Its weight-0 mirror `disrupt-the-tailored-hand` carries
the same contract inertly and stays.

**Survive on their own axes (do NOT fold — confirmed):**
- `dont-refresh-into-a-probable-miss` — draw quality, its own jurisdiction (the DRAW side of
  ADR-0060 stays flat by design).
- The posture levers as variance policy: `disrupt-when-unfavored`'s posture gating (until the
  damage term replaces the whole rung) and `dont-gift-a-refresh-when-favored` (with ruling 3's
  sign gate).
- `unfair-stamp-comeback-posture` — the double-inert prior.
- The one-sided-strip forward contracts `strip-the-stacked-engine-hand` /
  `disrupt-the-tailored-hand` — inert until a one-sided strip card (no `shuffle_hand`) enters the
  pool; the swing oracle has no card facts to read there, so the tag-driven rungs are correct.
- The STRIP/GIFT flats themselves — until design A's gate trips.

## Evidence-gated designs (priced, NOT built)

### A. Grading STRIP/GIFT — their expected keep-cost per hidden card

> **PARKED 2026-08-01 on measurement (ADR-0101, Issue #261 item 2b, discharging Issue #222 step 3).**
> The gate below is still untripped, and the design now has a second, measured blocker: its role
> values come from §2's derive-first sheet, which is unbuilt, so today's `_role_value` would supply
> them — and **59.4% of the cards in an opponent's representative build price `role_value` = 0**
> (measured at `ccd3a28` over the 115 of 132 refresh frames where a rep is reachable; `E[role_value]`
> = 5.67 against the flat GIFT anchor of 8.0). The blindness is not uniform: what survives is
> Energy / gust / recycle / ACE SPEC, what vanishes is exactly their attackers and wincons. Grading
> GIFT *down* because we cannot see their payoff line makes "Judge into their small hand" look cheap —
> ml f111's CRITICAL shape. **Prerequisite, named:** `gusting-keepcost-design.md` §2's shared role
> sheet, with §5's gust-side re-audit obligations, built once for both consumers. Until then
> `_REFRESH_OPPONENT_HAND_STRIP = 4` / `_REFRESH_OPPONENT_HAND_GIFT = 8` stay, typed `authored-scaffold` under the POC
> whitelist's `firing-equation-constants`.

`_REFRESH_OPPONENT_HAND_STRIP`/`_REFRESH_OPPONENT_HAND_GIFT` become E[keep_cost per card] over the opponent's HIDDEN hand,
where the expectation base is their rep's composition (decklist − tracker-observed — the shared
layer's rep) and the role values come from the shared derive-first role sheet
(`gusting-keepcost-design.md` §2) — one layer, two consumers. **Fail directions:** unknown/thin
rep → the flat 4/8 exactly, NEVER inflated; hidden hand → composition prior only, no card-level
claims; unrecognized opponent → flat. **Evidence gate:** a correction that turns on WHAT was
stripped or gifted (content, not count) — none exist today; every strip/gift correction in the
corpus is count-based and already priced by the closed-form swing.

### B. The signed hand-size damage term — **BUILT 2026-08-02 (ADR-0102, Issue #261 item 2c)**

> **The promotion gate at the foot of this section was RETIRED, not met.** It waited on *"a
> correction demonstrating the refill misfire or a mispriced strip"*, and none arrived. ADR-0092's
> POC replaced that standard: a track deletes its rung pile and lets the two deterministic gates rule
> the flips, rather than waiting for a blunder round to supply a witness. What shipped differs from
> the sketch below in three ways, each recorded in ADR-0102:
>
> 1. **The clock, not the boolean.** *"Whether my Active survives"* ships as Δ `turns_to_ko_me`
>    rather than a flip of `active_doomed`. The boolean is a cliff and it is blind on this doc's own
>    motivating frame: on ml f111 a refill need not flip a 200 HP Active from safe to doomed to be a
>    blunder — it moves the clock from ten turns to three and the boolean never moves. Doom is
>    `ko_me <= 1`, so this is the finer reading of the same oracle: price the quantity, don't
>    threshold it.
> 2. **BOTH hands.** This section reframes the leg as *incoming damage to me* and then prices only
>    THEIR hand. The set scales off mine too, and harder: **Mega Froslass ex** (861, Resentful
>    Refrain, *"50 damage for each card in your opponent's hand"*) and **Chandelure** (98, Mind
>    Ruler, 30/card) read MY hand at up to 50 a card against Powerful Hand's 20, and EVERY refresh
>    moves my hand — including the self-only Lillie's this doc excludes. The `def_hand` leg fires on
>    a real corpus board (83967840-54, opponent Active Mega Froslass ex, Lillie's at −46.67).
> 3. **Lever A returns as `phase_scale`, not as `_DENIAL_UNFAVORED`.** The fold list below is right
>    that the posture half must scale rather than re-add; it names the wrong scaler. ADR-0078
>    decision 6 rules that a path carrying both multiplies one race read by itself, and ADR-0080
>    decision 3 kept the Read-gated scaler for deny only because *"deny reads `phase_scale` on no
>    surface"* — a condition this term does not meet, since `phase_scale` IS its survival currency's
>    scaler.
>
> Measured: suite 4430 green; Decision Gate PASS, 0 unruled. Discrimination Gate 2 `OK → MISS`, both
> **held out onto Issue #262** by user ruling 2026-08-02 — measured in the gate's own process, both
> are caused by the +25's deletion alone (neutralising the new term leaves them in place; restoring
> the +25 clears the gate), and neither is a decision move: the agent still plays the human's ruled
> option on both frames.

#### The original design, as grilled 2026-07-19 (rulings 1a/2a)

**The reframe (verified at source).** The hand-size leg is NOT opponent-worth — Powerful Hand
(Alakazam MEG 743: *"Place 2 damage counters … for each card in your hand"* = **20 dmg/card in
THEIR hand, aimed at MY Active**; `parse_attack_hand_size` → `handSizeDamage = 20`) is **incoming
damage to me**, i.e. self-preservation. The incoming oracle ALREADY models it:
`combat.forward_incoming_damage` computes `handSizeDamage × (opp hand − 1)` over the opponent's
Active forward line and feeds `active_doomed`. So the term belongs in the **incoming/`active_doomed`
oracle, NOT the gust shared layer and NOT the STRIP/GIFT swing** (grill ruling 2a).

**Why the flat approach fails against Alakazam — three ways** (opp forward Alakazam, hand H;
Powerful Hand next turn ≈ 20·(H−1)):
1. **Undervaluation** — STRIP·4/card is ⅕ of the true 20/card; the +25 flat proxy papers over it.
2. **Sign hole (latent)** — at H=1 the current terms net ≈ +1 (`+25 rung − GIFT·8·3`), so the Pilot
   Judges an EMPTY Alakazam hand, refilling it 20→80 damage against its own Active. The +25 has no
   opp-hand gate; the GIFT tax can't fully cancel it.
3. **Flat 20/card is ALSO wrong** — 80 damage denied is worth ~0 if my Active survives either way
   (ADR-0063 pointed at ME), a whole attacker if it flips `active_doomed`. **The correct currency is
   MARGINAL vs my own KO** (grill ruling 1a) — which `active_doomed`/`forward_incoming_damage`
   already compute if re-run at the reduced hand.

**Ruling 1a/2a — the promotion form:** value = the change in whether my Active survives when their
hand drops to the redraw count, via the incoming oracle. Sign-correct by construction (a refill
raises incoming → negative → the H=1 hole closes for free). **Replaces +25 AND +18** (currency-zone;
+18's posture half returns as a multiplier, never a flat). STRIP/GIFT stay untouched as an
orthogonal *resource* axis (no double-count — against a hand-size deck the cards are fungible
count-ammo, low keep-cost, so design A grades that leg down while this term carries the damage).

**Fork-3 ruling (user, 2026-07-19): report the calculation NOW, inert.** The card/hand-value
calculations are meant to REPLACE the hard-coded rungs over time, so the signal must be VISIBLE
while it earns promotion — the house telemetry-only pattern (`play-safe-when-ahead` at weight 0).
**BUILT 2026-07-19** (suite green 3089):

- `pilot._hand_size_relief(obs, ctx)` — the signed *isolated* Powerful-Hand swing
  `handSizeDamage × (their hand now − redraw count)` over the opponent's ACTIVE forward line
  (+ = damage denied, − = a refill that arms them). Reports the raw physical quantity, NOT the
  worst-case `forward_incoming_damage` delta (which masks to 0 when a hand-independent forward threat
  dominates — that masking IS the marginal decision value, applied at promotion). Active-line-scoped:
  a BENCHED Alakazam (which the +25 rung over-fires on) reads 0, since it can't attack next turn.
- Surfaced on `OptionTrace.hand_size_relief` + telemetry `hs_relief`; **NEVER added to `score`**
  (pinned inert: `score == Σ fired weights + tactical`). Pins: `test_hand_size_relief.py`
  (+80 at hand 8, −60 at hand 1, 0 at redraw/no-attacker/self-only, inert).

**Promotion gate — RETIRED unmet, and discharged (2026-08-02, ADR-0102).** It read: *flip the inert
signal into `score` AND retire +25/+18 — waits on a correction demonstrating the refill misfire or a
mispriced strip.* No such correction ever arrived, and ADR-0092 replaced the standard (a POC track
deletes its rung pile and lets the deterministic gates rule the flips). The obligation this gate was
really protecting — **f64, the only live exercise of the +25, must stay endorsed without it** — is
MET and measured: on `82226759-64` (opponent Active Alakazam, their hand 21, the human's own words
*"opponents deck requires a large hand to deal heavy damage, therefore play harlequin to reduce their
handsize"*) the promoted term prices Harlequin at **+90.00**, the `_SURVIVAL_CAP` ceiling — 3.6× the
flat it replaces, on the frame the flat was right about. Across the whole committed corpus the term
is non-zero on 5 of 282 refresh-holding frames, and the Decision Gate moved none of them.

**Fail direction (unchanged, and now on both hands):** neither hand's size beyond the redraw count is
knowable → both clock reads use the deterministic redraw count only, never a speculative refill
projection.

## Re-baseline surface (whoever builds)

- `tests/strategy/test_refresh_swing_pilot.py` — the six-pin net (ml f111, ms f60/f94/f45/f100/f64)
  survives EVERY build above; f111 (Judge −32.36) is the refill counter-pin, f64 the
  strip-endorsement fixture that design B must reproduce without the +25. **Discharged 2026-08-02:**
  the net is green and f64 prices at +90.00 through the promoted term (see the promotion-gate note).
- Rung-pinned tests to re-point on any fold: `test_baseline_clusters.py`,
  `test_deferred_disruption_cluster.py`, `test_deferred_cluster_pins.py`,
  `test_posture_cardfacts.py`, `test_posture_read.py`, `test_shuffle_refresh.py`,
  `test_energy_denial_guards.py` (the ADR-0062 currency neighbors). **Re-pointed 2026-08-02** by
  ADR-0102, except the last two, which named the rungs only in prose. Three of them asserted the
  card fact through the `hand_size_attacker` LABEL and now carry the `handSizeDamage` scaler the
  clock actually reads.
- New pins: `test_grab_refresh_draw.py` (item 1, 86088989-29); `test_hand_size_relief.py` (the
  Design-B signal — the inertness test `score == Σ fired + tactical` MUST survive promotion's
  rewiring, re-pointed not deleted when the signal enters `score`. **It did:** the invariant is about
  the trace's shape, not about this term, and the relief now arrives inside `tactical`).
- Routed residuals (recorded, not disruptor work): 86091435-96 → attach doctrine (off-type attach
  nets +3 while `attach-before-hand-shuffle` counts it as a reason to hold Lillie's);
  83664991-43 → ADR-0065 SHED (held Ignition Energy + strong-hand keep-cost underpriced at +10.70);
  the 86088989-29 Petrel pick → human re-review.

## Fail directions (the standing hazards, restated once)

Endorser inflation (+76/ADR-0060) governs everything here: every opponent-side unknown moves
disruption credit TOWARD the flat or zero, never above it. The currency-zone rule governs every
fold: replace + re-audit, no bolt-ons. Anti-speculation is the standing verdict: Round 0 measured
80 corrections and found the flats sufficient — this doc's designs exist so no future session
re-derives them, and they build only when their gates trip in a future blunder round.
