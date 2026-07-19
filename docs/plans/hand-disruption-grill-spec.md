# Hand disruption — grill ruling: the disruptor swing stays half-flat until evidence

**Status.** GRILLED and RESOLVED 2026-07-19; the two measured build items are **BUILT the same day**
(see "Build list" below, suite green 3084). The flats and the damage-leg replacement stay
evidence-gated designs. Round 0 measured first (below); four rulings (user,
2026-07-19). Sibling of the gusting grill — same opponent-worth input layer, disruptor jurisdiction:
the two FLAT per-card prices on THEIR cards inside ADR-0060's closed-form refresh swing
(`_REFRESH_STRIP = 4` / `_REFRESH_GIFT = 8`, `pilot._refresh_swing_tactical`) and the
hand-size-attacker damage leg (`play-harlequin-vs-hand-size` +25, `disrupt-when-unfavored` +18,
`baseline_disruption.py`). **Nothing is built here** — build items go to a follow-up session under
the corpus + score-diff gate; evidence-gated designs wait for their gates to trip (the grab/pitch
precedent, ADR-0065; re-confirmed by the gusting Round 0).

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

**Fold ONLY when the damage-term evidence gate trips (design B):** `play-harlequin-vs-hand-size`
(+25) and `disrupt-when-unfavored` (+18) — both REPLACED by the signed damage term, never stacked
beside it (currency-zone rule). Note +18's unfavored-posture half does not survive separately: per
the ADR-0062 precedent, posture SCALES the oracle (`_DENIAL_UNFAVORED`-style multiplier inside the
term), it is never re-added as a flat.

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

`_REFRESH_STRIP`/`_REFRESH_GIFT` become E[keep_cost per card] over the opponent's HIDDEN hand,
where the expectation base is their rep's composition (decklist − tracker-observed — the shared
layer's rep) and the role values come from the shared derive-first role sheet
(`gusting-keepcost-design.md` §2) — one layer, two consumers. **Fail directions:** unknown/thin
rep → the flat 4/8 exactly, NEVER inflated; hidden hand → composition prior only, no card-level
claims; unrecognized opponent → flat. **Evidence gate:** a correction that turns on WHAT was
stripped or gifted (content, not count) — none exist today; every strip/gift correction in the
corpus is count-based and already priced by the closed-form swing.

### B. The signed hand-size damage term — replaces both rungs

    damage_leg = _DENIAL_PLAY_W × handSizeDamage_rate × Δ(their expected hand size)

Signed by construction: positive stripping a big hand, NEGATIVE when the refresh refills a small
one (the latent hole closes for free). Marginal with-vs-without (ADR-0062); a hand-size attacker I
am about to KO denies nothing (the ADR-0063 doomed discount); posture scales multiplicatively.
Lives inside `_refresh_swing_tactical` (a property of the refresh play; the swing already owns the
card-count legs), gated on the board-visible, γ-free `opp_has_hand_size_attacker`
(`pilot.py:4491` — function-tag + forward-line, no Read required). `handSizeDamage` is engine
vocabulary (`CardStat`, provider) — the rate is computable, no proxy. **Replaces +25 AND +18;
re-audit, never stack** — and mind the double-tax: GIFT×8 already prices the refill's card count,
so the term prices only the DAMAGE armed/denied. **Fail direction:** their next-turn hand size
unknowable beyond the visible count → use the deterministic redraw count only, no speculation.
**Evidence gate:** a correction demonstrating the refill misfire (a Judge/Stamp into a small hand
vs a hand-size attacker endorsed and punished) or a mispriced strip against one — none exist
today; f64, the only live exercise, is endorsed correctly.

## Re-baseline surface (whoever builds)

- `tests/strategy/test_refresh_swing_pilot.py` — the six-pin net (ml f111, ms f60/f94/f45/f100/f64)
  survives EVERY build above; f111 (Judge −32.36) is the refill counter-pin, f64 the
  strip-endorsement fixture that design B must reproduce without the +25.
- Rung-pinned tests to re-point on any fold: `test_baseline_clusters.py`,
  `test_deferred_disruption_cluster.py`, `test_deferred_cluster_pins.py`,
  `test_posture_cardfacts.py`, `test_posture_read.py`, `test_shuffle_refresh.py`,
  `test_energy_denial_guards.py` (the ADR-0062 currency neighbors).
- New pin on build item 1: 86088989-29.
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
